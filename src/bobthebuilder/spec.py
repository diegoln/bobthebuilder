"""RobotSpec: the single artifact the LLM produces.

Design (LDraw) and code (Pybricks) are both derived from it.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Port(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"


class ModuleInstance(BaseModel):
    """A placed module from the library, with its parameters."""

    id: str = Field(description="Unique name within this robot, e.g. 'drive'")
    module: str = Field(description="Library module id, e.g. 'drivebase.2wd'")
    params: dict[str, float | int | str] = Field(default_factory=dict)
    attach_to: str | None = Field(
        default=None, description="'<instance_id>.<socket>' this module mounts on"
    )
    ports: dict[str, Port] = Field(
        default_factory=dict,
        description="Device role -> brick port, e.g. {'left_motor': 'B'}",
    )


class RobotSpec(BaseModel):
    name: str
    task: str = Field(description="The user's task description")
    kit: str = Field(default="31313", description="Inventory id")
    modules: list[ModuleInstance]
