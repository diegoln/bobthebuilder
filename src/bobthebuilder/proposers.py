"""Proposers: things that turn a ProposalContext into a RobotSpec.

* ScriptedProposer — replays a fixed list of specs. For tests and for
  replaying a trace.
* ClaudeProposer — calls the Anthropic API. Imported lazily so the core has
  no SDK dependency.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence

from bobthebuilder.loop import ProposalContext, render_prompt
from bobthebuilder.spec import RobotSpec


class ScriptedProposer:
    def __init__(self, specs: Sequence[RobotSpec | str]):
        self._specs = list(specs)
        self.contexts: list[ProposalContext] = []

    def propose(self, ctx: ProposalContext) -> RobotSpec | str:
        self.contexts.append(ctx.model_copy(deep=True))
        idx = min(ctx.iteration, len(self._specs) - 1)
        return self._specs[idx]


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_json(text: str) -> str:
    m = _JSON_BLOCK.search(text)
    if m:
        return m.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


class ClaudeProposer:
    def __init__(self, model: str | None = None, max_tokens: int = 2000):
        import anthropic  # lazy

        self._client = anthropic.Anthropic()
        self.model = model or os.environ.get("BOB_MODEL", "claude-sonnet-5-5")
        self.max_tokens = max_tokens
        self.last_raw: str | None = None

    def propose(self, ctx: ProposalContext) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": render_prompt(ctx)}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        self.last_raw = text
        return extract_json(text)


def spec_to_json(spec: RobotSpec) -> str:
    return json.dumps(spec.model_dump(mode="json"), indent=2)
