"""Validator contract.

Validators are pure functions over a ResolvedSpec. They return errors that an
LLM can act on: a stable `code`, the offending module instance, and a `hint`
saying what to change. Nothing here calls a model.
"""

from __future__ import annotations

import math
from typing import Protocol

from pydantic import BaseModel, Field

from bobthebuilder.inventory.catalog import Catalog, load_catalog, load_inventory
from bobthebuilder.inventory.parts import Inventory, PartKind
from bobthebuilder.modules.base import DeviceKind, ModuleParamError, ResolvedModule
from bobthebuilder.modules.library import LIBRARY, MOTOR_SPECS
from bobthebuilder.spec import ModuleInstance, Port, RobotSpec


class ValidationError(BaseModel):
    code: str
    message: str
    module: str | None = Field(default=None, description="Offending ModuleInstance.id")
    hint: str | None = Field(default=None, description="What the proposer should change")
    severity: str = Field(default="error", description="error | warning")

    def __str__(self) -> str:  # LLM-facing one-liner
        where = f" [{self.module}]" if self.module else ""
        hint = f" -> {self.hint}" if self.hint else ""
        return f"{self.severity.upper()} {self.code}{where}: {self.message}{hint}"


class ResolvedSpec(BaseModel):
    """A RobotSpec with every module expanded. Validators consume this."""

    spec: RobotSpec
    resolved: dict[str, ResolvedModule]  # instance id -> resolved
    errors: list[ValidationError] = Field(default_factory=list)  # resolution-time errors

    def total_parts(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for r in self.resolved.values():
            for pid, q in r.parts.items():
                totals[pid] = totals.get(pid, 0) + q
        return totals


def resolve_spec(spec: RobotSpec) -> ResolvedSpec:
    """Expand modules. Unknown modules / bad params become errors, not crashes."""
    resolved: dict[str, ResolvedModule] = {}
    errors: list[ValidationError] = []
    seen_ids: set[str] = set()
    for inst in spec.modules:
        if inst.id in seen_ids:
            errors.append(
                ValidationError(
                    code="DUPLICATE_INSTANCE_ID",
                    message=f"instance id {inst.id!r} used twice",
                    module=inst.id,
                    hint="Give each module instance a unique id.",
                )
            )
            continue
        seen_ids.add(inst.id)
        mod = LIBRARY.get(inst.module)
        if mod is None:
            errors.append(
                ValidationError(
                    code="UNKNOWN_MODULE",
                    message=f"no module {inst.module!r} in the library",
                    module=inst.id,
                    hint=f"Use one of: {', '.join(sorted(LIBRARY))}",
                )
            )
            continue
        try:
            resolved[inst.id] = mod.resolve_with_defaults(dict(inst.params))
        except ModuleParamError as e:
            errors.append(
                ValidationError(
                    code="BAD_PARAMS", message=str(e), module=inst.id, hint="Fix the parameter."
                )
            )
    return ResolvedSpec(spec=spec, resolved=resolved, errors=errors)


class Validator(Protocol):
    def __call__(self, rs: ResolvedSpec) -> list[ValidationError]: ...


# --------------------------------------------------------------------------
# Individual validators
# --------------------------------------------------------------------------

_MOTOR_PORTS = {Port.A, Port.B, Port.C, Port.D}
_SENSOR_PORTS = {Port.S1, Port.S2, Port.S3, Port.S4}


def check_ports(rs: ResolvedSpec) -> list[ValidationError]:
    """Every device has a port, of the right kind, used once."""
    errors: list[ValidationError] = []
    used: dict[Port, str] = {}
    for inst in rs.spec.modules:
        r = rs.resolved.get(inst.id)
        if r is None:
            continue
        declared = {d.role: d for d in r.devices}
        for role, dev in declared.items():
            port = inst.ports.get(role)
            if port is None:
                errors.append(
                    ValidationError(
                        code="PORT_MISSING",
                        message=f"{inst.id}.{role} ({dev.kind.value}) has no port",
                        module=inst.id,
                        hint=f"Add ports[{role!r}] = one of "
                        f"{'A/B/C/D' if dev.kind.is_motor else 'S1/S2/S3/S4'}",
                    )
                )
                continue
            ok_set = _MOTOR_PORTS if dev.kind.is_motor else _SENSOR_PORTS
            if port not in ok_set:
                errors.append(
                    ValidationError(
                        code="PORT_WRONG_KIND",
                        message=f"{inst.id}.{role} is a {dev.kind.value} but is on {port.value}",
                        module=inst.id,
                        hint="Motors go on A-D, sensors on S1-S4.",
                    )
                )
                continue
            if port in used:
                errors.append(
                    ValidationError(
                        code="PORT_CONFLICT",
                        message=f"{inst.id}.{role} and {used[port]} both use {port.value}",
                        module=inst.id,
                        hint="Assign a free port.",
                    )
                )
            else:
                used[port] = f"{inst.id}.{role}"
        for role in inst.ports:
            if role not in declared:
                errors.append(
                    ValidationError(
                        code="PORT_UNKNOWN_ROLE",
                        message=f"{inst.id} has no device role {role!r}",
                        module=inst.id,
                        hint=f"Valid roles: {sorted(declared) or 'none'}",
                        severity="warning",
                    )
                )
    return errors


def check_attachments(rs: ResolvedSpec) -> list[ValidationError]:
    """Exactly one root; every other module attaches to an existing socket of
    the right kind; no socket overloaded."""
    errors: list[ValidationError] = []
    roots = [i for i in rs.spec.modules if i.id in rs.resolved and rs.resolved[i.id].mounts_on is None]
    if len(roots) != 1:
        errors.append(
            ValidationError(
                code="ROOT_COUNT",
                message=f"expected exactly one root module (a drive base), found {len(roots)}",
                hint="Include one drivebase.* module and make everything else attach to it.",
            )
        )
    sockets: dict[str, tuple[str, str]] = {}  # "inst.socket" -> (kind, capacity)
    for inst in rs.spec.modules:
        r = rs.resolved.get(inst.id)
        if r is None:
            continue
        for s in r.sockets:
            sockets[f"{inst.id}.{s.name}"] = (s.kind, s.load_capacity)
    rank = {"light": 0, "medium": 1, "heavy": 2}
    occupancy: dict[str, list[str]] = {}
    for inst in rs.spec.modules:
        r = rs.resolved.get(inst.id)
        if r is None:
            continue
        if r.mounts_on is None:
            if inst.attach_to:
                errors.append(
                    ValidationError(
                        code="ROOT_ATTACHED",
                        message=f"root module {inst.id} must not have attach_to",
                        module=inst.id,
                        hint="Remove attach_to from the drive base.",
                    )
                )
            continue
        if not inst.attach_to:
            errors.append(
                ValidationError(
                    code="ATTACH_MISSING",
                    message=f"{inst.id} ({inst.module}) needs a socket of kind {r.mounts_on!r}",
                    module=inst.id,
                    hint="Set attach_to='<instance>.<socket>' e.g. 'drive.front'.",
                )
            )
            continue
        target = sockets.get(inst.attach_to)
        if target is None:
            errors.append(
                ValidationError(
                    code="ATTACH_UNKNOWN_SOCKET",
                    message=f"{inst.id} attaches to {inst.attach_to!r}, which does not exist",
                    module=inst.id,
                    hint=f"Available sockets: {sorted(sockets)}",
                )
            )
            continue
        kind, capacity = target
        if kind != r.mounts_on:
            errors.append(
                ValidationError(
                    code="ATTACH_KIND_MISMATCH",
                    message=f"{inst.id} needs a {r.mounts_on!r} socket but {inst.attach_to} is {kind!r}",
                    module=inst.id,
                    hint=f"Pick a socket of kind {r.mounts_on!r}: "
                    f"{[k for k, (kd, _) in sockets.items() if kd == r.mounts_on]}",
                )
            )
        if rank[r.load] > rank[capacity]:
            errors.append(
                ValidationError(
                    code="ATTACH_OVERLOADED",
                    message=f"{inst.id} is {r.load} but socket {inst.attach_to} takes {capacity}",
                    module=inst.id,
                    hint="Mount it on a stronger socket (e.g. the drive base top).",
                )
            )
        occupancy.setdefault(inst.attach_to, []).append(inst.id)
    for sock, users in occupancy.items():
        if len(users) > 1 and sockets[sock][0] == "front_mount":
            errors.append(
                ValidationError(
                    code="SOCKET_CROWDED",
                    message=f"socket {sock} has {len(users)} modules: {users}",
                    hint="A front mount fits one module. Move one to another socket or drop it.",
                )
            )
    return errors


def check_inventory(rs: ResolvedSpec, inventory: Inventory | None = None) -> list[ValidationError]:
    """Total parts must fit the kit."""
    inv = inventory or load_inventory(rs.spec.kit)
    catalog = load_catalog()
    errors: list[ValidationError] = []
    for pid, need in sorted(rs.total_parts().items()):
        have = inv.qty(pid)
        if need > have:
            name = catalog.get(pid).name if pid in catalog else pid
            culprits = [i for i, r in rs.resolved.items() if pid in r.parts]
            errors.append(
                ValidationError(
                    code="INVENTORY_SHORT",
                    message=f"need {need} x {name} ({pid}), kit {inv.id} has {have}",
                    module=culprits[0] if len(culprits) == 1 else None,
                    hint=f"Used by {culprits}. Change a param (e.g. gear_ratio) or drop a module.",
                )
            )
    return errors


def _is_buildable_distance(d: float) -> bool:
    """Center distances you can realise on Technic beams: whole/half studs
    along a beam, or diagonals between hole grids (sqrt(a^2+b^2) with a, b in
    half-stud steps) within a small tolerance LEGO gears tolerate."""
    tol = 0.03
    if abs(d * 2 - round(d * 2)) < tol:
        return True
    for a2 in range(0, 13):  # half-studs
        for b2 in range(1, 13):
            if abs(math.hypot(a2 / 2, b2 / 2) - d) < tol:
                return True
    return False


def check_gears(rs: ResolvedSpec) -> list[ValidationError]:
    """Meshing gears must sit at (t1+t2)/32 studs, and that distance must be
    realisable on a beam."""
    catalog = load_catalog()
    errors: list[ValidationError] = []
    for inst_id, r in rs.resolved.items():
        for gp in r.gear_pairs:
            g1, g2 = catalog.get(gp.driver_ldraw), catalog.get(gp.driven_ldraw)
            if g1.teeth is None or g2.teeth is None:
                continue
            required = (g1.teeth + g2.teeth) / 32
            if abs(gp.center_distance_studs - required) > 0.01:
                errors.append(
                    ValidationError(
                        code="GEAR_MESH_DISTANCE",
                        message=f"{g1.teeth}t + {g2.teeth}t gears need {required:g} studs between "
                        f"axles, got {gp.center_distance_studs:g}",
                        module=inst_id,
                        hint=f"Set gear_center_distance_studs={required:g}.",
                    )
                )
            elif not _is_buildable_distance(required):
                errors.append(
                    ValidationError(
                        code="GEAR_DISTANCE_UNBUILDABLE",
                        message=f"{required:g} studs cannot be placed on a Technic beam grid",
                        module=inst_id,
                        hint="Choose a pair whose tooth sum is a multiple of 16 (e.g. 12:20, 12:36, 20:36).",
                    )
                )
    return errors


def check_torque(rs: ResolvedSpec) -> list[ValidationError]:
    """Cheap physics sanity: can the lift motor hold its payload, and is the
    drive geared so the robot still moves at a useful speed?"""
    errors: list[ValidationError] = []
    g = 9.81
    for inst_id, r in rs.resolved.items():
        geo = r.geometry
        if r.module_id == "arm.lift":
            ratio = float(geo["lift_gear_ratio"])
            arm_m = float(geo["arm_length_mm"]) / 1000
            payload_kg = float(geo["payload_g"]) / 1000
            needed_ncm = payload_kg * g * arm_m * 100  # N·m -> N·cm
            avail = MOTOR_SPECS[DeviceKind.MOTOR_MEDIUM]["rated_torque_ncm"] * ratio
            if needed_ncm > avail:
                errors.append(
                    ValidationError(
                        code="TORQUE_INSUFFICIENT",
                        message=f"lift needs ~{needed_ncm:.1f} N·cm at the pivot, medium motor x{ratio:g} "
                        f"gives ~{avail:.1f}",
                        module=inst_id,
                        hint="Use a higher gear_ratio (12:36), a shorter arm, or a lighter payload.",
                    )
                )
        if r.module_id.startswith("drivebase"):
            ratio = float(geo["drive_gear_ratio"])
            wheel_m = float(geo["wheel_diameter_mm"]) / 1000
            rpm = MOTOR_SPECS[DeviceKind.MOTOR_LARGE]["free_speed_rpm"] / ratio
            speed = math.pi * wheel_m * rpm / 60  # m/s
            if speed < 0.08:
                errors.append(
                    ValidationError(
                        code="DRIVE_TOO_SLOW",
                        message=f"top speed ~{speed*100:.0f} cm/s with ratio {ratio:g}",
                        module=inst_id,
                        hint="Reduce the gear ratio (closer to 1:1).",
                        severity="warning",
                    )
                )
            if speed > 0.6:
                errors.append(
                    ValidationError(
                        code="DRIVE_TOO_FAST",
                        message=f"top speed ~{speed*100:.0f} cm/s; hard to control and low torque",
                        module=inst_id,
                        hint="Use 1:1 or a reduction like 12:20.",
                        severity="warning",
                    )
                )
    return errors


def check_task_coverage(rs: ResolvedSpec) -> list[ValidationError]:
    """Very light heuristic: does the robot carry what the task implies?"""
    task = rs.spec.task.lower()
    kinds = {d.kind for r in rs.resolved.values() for d in r.devices}
    errors: list[ValidationError] = []
    if "line" in task and DeviceKind.SENSOR_COLOR not in kinds:
        errors.append(
            ValidationError(
                code="TASK_NEEDS_COLOR_SENSOR",
                message="line following needs a downward color sensor",
                hint="Add sensor.color_down on drive.front.",
            )
        )
    if any(w in task for w in ("pick", "grab", "grip", "cube")) and not any(
        r.module_id.startswith("arm.") for r in rs.resolved.values()
    ):
        errors.append(
            ValidationError(
                code="TASK_NEEDS_MANIPULATOR",
                message="picking things up needs an arm or gripper",
                hint="Add arm.gripper or arm.lift on drive.front.",
            )
        )
    if "sumo" in task and not (
        {DeviceKind.SENSOR_IR, DeviceKind.SENSOR_ULTRASONIC} & kinds
    ):
        errors.append(
            ValidationError(
                code="TASK_NEEDS_DISTANCE_SENSOR",
                message="sumo needs to find the opponent",
                hint="Add sensor.ir_front (31313) or sensor.ultrasonic_front (45544).",
                severity="warning",
            )
        )
    return errors


DEFAULT_VALIDATORS: list[Validator] = [
    check_ports,
    check_attachments,
    check_inventory,
    check_gears,
    check_torque,
    check_task_coverage,
]


def validate(spec: RobotSpec, validators: list[Validator] | None = None) -> ResolvedSpec:
    """Resolve + run every validator. Errors accumulate on the ResolvedSpec."""
    rs = resolve_spec(spec)
    for v in validators or DEFAULT_VALIDATORS:
        rs.errors.extend(v(rs))
    return rs


def hard_errors(rs: ResolvedSpec) -> list[ValidationError]:
    return [e for e in rs.errors if e.severity == "error"]
