"""Parts catalog: what a LEGO part *is* (geometry), independent of any kit.

Geometry is what validators reason about. The LDraw id is what the
assembler emits. Dimensions are in LEGO units: 1 stud = 8 mm, 1 "M"
(Technic beam pitch) = 1 stud.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PartKind(str, Enum):
    BEAM = "beam"  # straight Technic liftarm, N holes
    BEAM_ANGLED = "beam_angled"
    PIN = "pin"  # friction / frictionless pin, 2 or 3 long
    AXLE = "axle"  # N studs long
    AXLE_PIN = "axle_pin"  # half pin / half axle
    CONNECTOR = "connector"  # axle/pin connectors, perpendicular blocks
    GEAR = "gear"  # spur / double-bevel, N teeth
    GEAR_WORM = "gear_worm"
    GEAR_RACK = "gear_rack"
    WHEEL = "wheel"  # rim + tire as one unit
    BALL_CASTER = "ball_caster"
    MOTOR_LARGE = "motor_large"
    MOTOR_MEDIUM = "motor_medium"
    SENSOR_COLOR = "sensor_color"
    SENSOR_TOUCH = "sensor_touch"
    SENSOR_IR = "sensor_ir"
    SENSOR_ULTRASONIC = "sensor_ultrasonic"
    SENSOR_GYRO = "sensor_gyro"
    BRICK = "brick"  # the EV3 programmable brick
    CABLE = "cable"
    OTHER = "other"


class Part(BaseModel):
    ldraw_id: str = Field(description="LDraw part number, e.g. '32524' (beam 7)")
    name: str
    kind: PartKind
    # Geometry fields: only those relevant to the kind are set.
    length: float | None = Field(default=None, description="Studs (beams, axles, pins)")
    teeth: int | None = Field(default=None, description="Gear tooth count")
    diameter_mm: float | None = Field(default=None, description="Wheel outer diameter")
    width_mm: float | None = None
    holes: int | None = Field(default=None, description="Pin holes on a beam/connector")
    tags: list[str] = Field(default_factory=list)

    # --- derived helpers used by validators ---

    @property
    def pitch_radius_studs(self) -> float | None:
        """LEGO gears: center distance (studs) between two meshing gears is
        (t1 + t2) / 32, so each gear's pitch radius is teeth / 32 studs."""
        if self.teeth is None:
            return None
        return self.teeth / 32


class InventoryLine(BaseModel):
    ldraw_id: str
    qty: int = Field(ge=0)


class Inventory(BaseModel):
    """A concrete kit: which parts and how many."""

    id: str
    name: str
    source: str = Field(description="Where the counts come from; verify before trusting")
    lines: list[InventoryLine]

    def qty(self, ldraw_id: str) -> int:
        return sum(l.qty for l in self.lines if l.ldraw_id == ldraw_id)
