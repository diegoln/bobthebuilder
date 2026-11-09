"""bob — command line entry point.

    bob design "follow a black line and stop at a red marker" --out out/
    bob validate spec.json
    bob library
    bob lessons
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bobthebuilder.codegen.pybricks import generate
from bobthebuilder.loop import Lessons, Trace, run_design_loop
from bobthebuilder.modules.library import describe_library
from bobthebuilder.spec import RobotSpec
from bobthebuilder.validators.base import validate

TRACE_PATH = Path(".bob/trace.jsonl")


def _print_errors(errors) -> None:
    for e in errors:
        print("  " + str(e))


def cmd_library(_: argparse.Namespace) -> int:
    print(describe_library())
    return 0


def cmd_validate(a: argparse.Namespace) -> int:
    spec = RobotSpec.model_validate_json(Path(a.spec).read_text())
    rs = validate(spec)
    _print_errors(rs.errors)
    hard = [e for e in rs.errors if e.severity == "error"]
    print("OK" if not hard else f"{len(hard)} error(s)")
    return 0 if not hard else 1


def cmd_lessons(_: argparse.Namespace) -> int:
    trace = Trace(TRACE_PATH)
    rules = Lessons(trace).rules()
    print(f"{len(trace.attempts)} attempts in trace; {len(rules)} lessons:")
    for r in rules:
        print("  - " + r)
    return 0


def cmd_design(a: argparse.Namespace) -> int:
    from bobthebuilder.proposers import ClaudeProposer

    trace = Trace(TRACE_PATH)
    proposer = ClaudeProposer(model=a.model)
    result = run_design_loop(a.task, proposer, kit=a.kit, max_iters=a.iters, trace=trace)
    for att in result.history:
        hard = [e for e in att.errors if e.severity == "error"]
        print(f"iteration {att.iteration}: {'ok' if att.ok else f'{len(hard)} error(s)'}")
        _print_errors(att.errors)
    if not result.ok or result.spec is None or result.resolved is None:
        print("no valid design", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(result.spec.model_dump(mode="json"), indent=2))
    (out / "main.py").write_text(generate(result.resolved))
    bom = result.resolved.total_parts()
    (out / "bom.json").write_text(json.dumps(bom, indent=2, sort_keys=True))
    print(f"wrote {out}/spec.json, main.py, bom.json after {result.iterations} iteration(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bob")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("library", help="print the module library")
    s.set_defaults(fn=cmd_library)

    s = sub.add_parser("validate", help="validate a spec.json")
    s.add_argument("spec")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("lessons", help="show lessons distilled from the trace")
    s.set_defaults(fn=cmd_lessons)

    s = sub.add_parser("design", help="run the design loop with Claude")
    s.add_argument("task")
    s.add_argument("--kit", default="31313")
    s.add_argument("--iters", type=int, default=6)
    s.add_argument("--model", default=None)
    s.add_argument("--out", default="out")
    s.set_defaults(fn=cmd_design)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
