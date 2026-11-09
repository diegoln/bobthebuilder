"""Validator contract: pure functions returning actionable errors."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from bobthebuilder.spec import RobotSpec


class ValidationError(BaseModel):
    code: str  # e.g. "PORT_CONFLICT", "INVENTORY_SHORT"
    message: str
    module: str | None = None  # offending ModuleInstance.id
    hint: str | None = None  # what the LLM should change


class Validator(Protocol):
    def __call__(self, spec: RobotSpec) -> list[ValidationError]: ...


def check_port_conflicts(spec: RobotSpec) -> list[ValidationError]:
    """Two devices may not share a brick port."""
    seen: dict[str, str] = {}
    errors: list[ValidationError] = []
    for m in spec.modules:
        for role, port in m.ports.items():
            key = port.value
            if key in seen:
                errors.append(
                    ValidationError(
                        code="PORT_CONFLICT",
                        message=f"{m.id}.{role} and {seen[key]} both use port {key}",
                        module=m.id,
                        hint="Assign a free port.",
                    )
                )
            else:
                seen[key] = f"{m.id}.{role}"
    return errors
