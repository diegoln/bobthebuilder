"""Module library contract.

A Module is a parametric, pre-validated sub-assembly. Given parameters it
*resolves* into a ResolvedModule: concrete parts, sockets it offers, the
socket it needs to mount on, the devices it brings (motors/sensors needing
ports), and the geometry numbers codegen and validators care about.

The LLM only ever picks modules and parameters. It never places parts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field


class DeviceKind(str, Enum):
    MOTOR_LARGE = "motor_large"
    MOTOR_MEDIUM = "motor_medium"
    SENSOR_COLOR = "sensor_color"
    SENSOR_TOUCH = "sensor_touch"
    SENSOR_IR = "sensor_ir"
    SENSOR_ULTRASONIC = "sensor_ultrasonic"
    SENSOR_GYRO = "sensor_gyro"

    @property
    def is_motor(self) -> bool:
        return self.value.startswith("motor")


class Device(BaseModel):
    role: str = Field(description="Name the module uses, e.g. 'left_motor'")
    kind: DeviceKind


class Socket(BaseModel):
    """A place another module can attach. `kind` is matched against the
    attaching module's `mounts_on`."""

    name: str
    kind: str  # e.g. "beam_face", "axle_out", "front_mount"
    load_capacity: str = Field(
        default="light", description="light | medium | heavy — what can hang here"
    )


class GearPair(BaseModel):
    """Two gears that must mesh. Validators check the center distance."""

    driver_ldraw: str
    driven_ldraw: str
    center_distance_studs: float


class ParamSpec(BaseModel):
    name: str
    type: str  # "int" | "float" | "str" | "enum"
    description: str
    default: Any = None
    choices: list[Any] | None = None
    min: float | None = None
    max: float | None = None


class ModuleInfo(BaseModel):
    """What the LLM sees when choosing modules."""

    id: str
    summary: str
    params: list[ParamSpec]
    mounts_on: str | None = Field(
        default=None, description="Socket kind this module needs, or None if it is a root"
    )
    provides_sockets: list[str] = Field(default_factory=list)


class ResolvedModule(BaseModel):
    module_id: str
    parts: dict[str, int] = Field(description="ldraw_id -> qty")
    sockets: list[Socket] = Field(default_factory=list)
    mounts_on: str | None = None
    devices: list[Device] = Field(default_factory=list)
    gear_pairs: list[GearPair] = Field(default_factory=list)
    geometry: dict[str, float | str] = Field(
        default_factory=dict,
        description="wheel_diameter_mm, axle_track_mm, gear_ratio, mass_g, ...",
    )
    load: str = Field(default="light", description="How heavy this module is on its socket")


class ModuleParamError(ValueError):
    """Raised by a module when parameters are invalid. Message is LLM-facing."""


@dataclass
class Module:
    info: ModuleInfo
    resolve: Callable[[dict[str, Any]], ResolvedModule]
    tags: list[str] = field(default_factory=list)

    def resolve_with_defaults(self, params: dict[str, Any]) -> ResolvedModule:
        merged = {p.name: p.default for p in self.info.params if p.default is not None}
        merged.update(params)
        for p in self.info.params:
            if p.name not in merged:
                raise ModuleParamError(f"{self.info.id}: missing required param {p.name!r}")
            v = merged[p.name]
            if p.choices is not None and v not in p.choices:
                raise ModuleParamError(
                    f"{self.info.id}: {p.name}={v!r} not in {p.choices}"
                )
            if p.min is not None and v < p.min:
                raise ModuleParamError(f"{self.info.id}: {p.name}={v} below min {p.min}")
            if p.max is not None and v > p.max:
                raise ModuleParamError(f"{self.info.id}: {p.name}={v} above max {p.max}")
        unknown = set(merged) - {p.name for p in self.info.params}
        if unknown:
            raise ModuleParamError(f"{self.info.id}: unknown params {sorted(unknown)}")
        return self.resolve(merged)
