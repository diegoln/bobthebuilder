"""The design loop.

    task ──► Proposer ──► RobotSpec ──► validate ──► clean? ──► done
                ▲                         │
                └──── errors (+ lessons) ─┘

Two feedback loops run at different speeds:

* **Inner loop (seconds):** the proposer gets the validator errors for its
  own last attempt and tries again. Bounded by `max_iters`.
* **Outer loop (across runs):** every attempt is appended to a JSONL trace.
  `Lessons` distils the trace into short rules ("12:20 gears need 1.0 studs")
  that are prepended to the next run's prompt, so the proposer stops making
  the same mistake on day two.

The Proposer is a Protocol so tests can use a scripted one and production can
use an LLM. Nothing in this module imports an LLM SDK.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError as PydanticError

from bobthebuilder.modules.library import describe_library
from bobthebuilder.spec import RobotSpec
from bobthebuilder.validators.base import ResolvedSpec, ValidationError, hard_errors, validate


# --------------------------------------------------------------------------
# Proposer
# --------------------------------------------------------------------------
class ProposalContext(BaseModel):
    """Everything a proposer may look at. Serialisable so it can be logged."""

    task: str
    kit: str
    library_text: str
    lessons: list[str] = Field(default_factory=list)
    previous_spec: RobotSpec | None = None
    previous_errors: list[ValidationError] = Field(default_factory=list)
    iteration: int = 0


class Proposer(Protocol):
    def propose(self, ctx: ProposalContext) -> RobotSpec | str:
        """Return a RobotSpec, or a JSON string that parses into one."""


# --------------------------------------------------------------------------
# Trace: every attempt, append-only
# --------------------------------------------------------------------------
class Attempt(BaseModel):
    run_id: str
    iteration: int
    task: str
    kit: str
    spec: RobotSpec | None
    errors: list[ValidationError]
    ok: bool
    ts: float


class Trace:
    def __init__(self, path: Path | None):
        self.path = path
        self.attempts: list[Attempt] = []
        if path and path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    self.attempts.append(Attempt.model_validate_json(line))

    def record(self, a: Attempt) -> None:
        self.attempts.append(a)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(a.model_dump_json() + "\n")


# --------------------------------------------------------------------------
# Lessons: distil the trace into prompt-sized rules
# --------------------------------------------------------------------------
class Lessons:
    """Turns repeated validator errors into short standing rules.

    Deliberately dumb: count (code, hint) pairs that have fired across runs and
    surface the most frequent ones. A hint that keeps firing is, by
    definition, something the proposer keeps getting wrong.
    """

    def __init__(self, trace: Trace, min_count: int = 2, max_lessons: int = 8):
        self.trace = trace
        self.min_count = min_count
        self.max_lessons = max_lessons

    def rules(self) -> list[str]:
        counter: Counter[tuple[str, str]] = Counter()
        for a in self.trace.attempts:
            for e in a.errors:
                if e.severity == "error" and e.hint:
                    counter[(e.code, e.hint)] += 1
        out = []
        for (code, hint), n in counter.most_common():
            if n < self.min_count:
                break
            out.append(f"[{code}] {hint}")
            if len(out) >= self.max_lessons:
                break
        return out


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------
@dataclass
class LoopResult:
    ok: bool
    spec: RobotSpec | None
    resolved: ResolvedSpec | None
    iterations: int
    history: list[Attempt] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationError]:
        return self.resolved.errors if self.resolved else []


def _coerce(raw: RobotSpec | str) -> tuple[RobotSpec | None, list[ValidationError]]:
    if isinstance(raw, RobotSpec):
        return raw, []
    try:
        return RobotSpec.model_validate_json(raw), []
    except PydanticError as e:
        return None, [
            ValidationError(
                code="SPEC_INVALID_JSON",
                message=str(e)[:500],
                hint="Return only a JSON object matching the RobotSpec schema.",
            )
        ]
    except Exception as e:  # noqa: BLE001
        return None, [
            ValidationError(code="SPEC_UNPARSEABLE", message=repr(e)[:300], hint="Return valid JSON.")
        ]


def run_design_loop(
    task: str,
    proposer: Proposer,
    *,
    kit: str = "31313",
    max_iters: int = 6,
    trace: Trace | None = None,
    lessons: Lessons | None = None,
    run_id: str | None = None,
) -> LoopResult:
    trace = trace or Trace(None)
    lessons = lessons or Lessons(trace)
    run_id = run_id or f"run-{int(time.time())}"
    rules = lessons.rules()
    ctx = ProposalContext(task=task, kit=kit, library_text=describe_library(), lessons=rules)

    history: list[Attempt] = []
    last_rs: ResolvedSpec | None = None
    for i in range(max_iters):
        ctx.iteration = i
        spec, parse_errors = _coerce(proposer.propose(ctx))
        if spec is None:
            errors = parse_errors
            rs = None
        else:
            spec.kit = spec.kit or kit
            rs = validate(spec)
            errors = rs.errors
        hard = [e for e in errors if e.severity == "error"]
        attempt = Attempt(
            run_id=run_id, iteration=i, task=task, kit=kit, spec=spec,
            errors=errors, ok=not hard, ts=time.time(),
        )
        trace.record(attempt)
        history.append(attempt)
        last_rs = rs
        if not hard:
            return LoopResult(ok=True, spec=spec, resolved=rs, iterations=i + 1, history=history)
        ctx.previous_spec = spec
        ctx.previous_errors = hard
    return LoopResult(
        ok=False,
        spec=history[-1].spec if history else None,
        resolved=last_rs,
        iterations=len(history),
        history=history,
    )


# --------------------------------------------------------------------------
# Prompt rendering (shared by any LLM-backed proposer)
# --------------------------------------------------------------------------
def render_prompt(ctx: ProposalContext) -> str:
    schema = json.dumps(RobotSpec.model_json_schema(), indent=None)
    parts = [
        "You design LEGO MINDSTORMS EV3 robots by composing modules from a library.",
        "You never place individual parts. Output ONLY a JSON RobotSpec.",
        "",
        f"TASK: {ctx.task}",
        f"KIT: {ctx.kit}",
        "",
        "MODULE LIBRARY:",
        ctx.library_text,
        "",
        "RULES:",
        "- Exactly one root module (drivebase.*). Everything else sets attach_to='<id>.<socket>'.",
        "- Every device role gets a unique port: motors A-D, sensors S1-S4.",
        "- Meshing gears sit at (t1+t2)/32 studs; set gear_center_distance_studs accordingly.",
    ]
    if ctx.lessons:
        parts += ["", "LESSONS FROM PAST RUNS (these mistakes keep happening):"]
        parts += [f"- {r}" for r in ctx.lessons]
    if ctx.previous_spec is not None:
        parts += [
            "",
            f"YOUR PREVIOUS ATTEMPT (iteration {ctx.iteration - 1}):",
            ctx.previous_spec.model_dump_json(),
            "",
            "IT FAILED VALIDATION:",
        ]
        parts += [f"- {e}" for e in ctx.previous_errors]
        parts += ["", "Fix every error above. Change as little else as possible."]
    parts += ["", "JSON SCHEMA:", schema]
    return "\n".join(parts)
