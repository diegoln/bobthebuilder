"""The built-in module library.

Part lists here are deliberately simple and conservative: enough to make the
inventory validator meaningful, not a faithful LDraw assembly yet. Each
module's docstring is the LLM-facing explanation.
"""

from __future__ import annotations

from typing import Any

from bobthebuilder.modules.base import (
    Device,
    DeviceKind,
    GearPair,
    Module,
    ModuleInfo,
    ModuleParamError,
    ParamSpec,
    ResolvedModule,
    Socket,
)

# ldraw ids used below (see data/parts.json)
BRICK = "95646c01"
MOTOR_L = "95658c01"
MOTOR_M = "99455c01"
COLOR = "95650c01"
TOUCH = "95648c01"
IR = "95654c01"
ULTRA = "95652c01"
GYRO = "99380c01"
BEAM5, BEAM7, BEAM9, BEAM11, BEAM13 = "32316", "32524", "40490", "32525", "41239"
BEAM_L35 = "32526"
PIN, PIN3, AXLEPIN = "2780", "6558", "43093"
AXLE3, AXLE5, AXLE7 = "4519", "32073", "44294"
BUSH, HALFBUSH = "3713", "32123b"
WHEEL_43 = "56145c02"
CASTER_BALL, CASTER_SOCKET = "32474", "92911"
G8, G12, G20, G24, G36 = "3647", "32270", "32269", "3648", "32498"

GEAR_BY_TEETH = {8: G8, 12: G12, 20: G20, 24: G24, 36: G36}

# Rough EV3 numbers used for torque/speed sanity checks (Pybricks docs / LEGO specs).
MOTOR_SPECS = {
    DeviceKind.MOTOR_LARGE: {"rated_torque_ncm": 20.0, "free_speed_rpm": 170.0},
    DeviceKind.MOTOR_MEDIUM: {"rated_torque_ncm": 8.0, "free_speed_rpm": 250.0},
}


# --------------------------------------------------------------------------
# drivebase.2wd — two large motors driving two wheels, caster at the rear.
# --------------------------------------------------------------------------
def _drivebase_2wd(p: dict[str, Any]) -> ResolvedModule:
    """Classic differential drive. Direct drive (ratio 1) or a reduction
    through a gear pair between motor and wheel axle."""
    ratio_choice = p["gear_ratio"]
    parts = {
        BRICK: 1,
        MOTOR_L: 2,
        WHEEL_43: 2,
        CASTER_BALL: 1,
        CASTER_SOCKET: 1,
        BEAM13: 2,
        BEAM7: 2,
        BEAM_L35: 2,
        PIN: 16,
        PIN3: 4,
        AXLE5: 2,
        BUSH: 2,
    }
    gear_pairs: list[GearPair] = []
    ratio = 1.0
    if ratio_choice != "1:1":
        driver_t, driven_t = (int(x) for x in ratio_choice.split(":"))
        parts[GEAR_BY_TEETH[driver_t]] = parts.get(GEAR_BY_TEETH[driver_t], 0) + 2
        parts[GEAR_BY_TEETH[driven_t]] = parts.get(GEAR_BY_TEETH[driven_t], 0) + 2
        parts[AXLE3] = 2
        gear_pairs.append(
            GearPair(
                driver_ldraw=GEAR_BY_TEETH[driver_t],
                driven_ldraw=GEAR_BY_TEETH[driven_t],
                center_distance_studs=p["gear_center_distance_studs"],
            )
        )
        ratio = driven_t / driver_t  # >1 means slower & more torque at wheel
    track = float(p["axle_track_mm"])
    return ResolvedModule(
        module_id="drivebase.2wd",
        parts=parts,
        sockets=[
            Socket(name="front", kind="front_mount", load_capacity="medium"),
            Socket(name="top", kind="beam_face", load_capacity="heavy"),
            Socket(name="rear", kind="beam_face", load_capacity="light"),
        ],
        mounts_on=None,
        devices=[
            Device(role="left_motor", kind=DeviceKind.MOTOR_LARGE),
            Device(role="right_motor", kind=DeviceKind.MOTOR_LARGE),
        ],
        gear_pairs=gear_pairs,
        geometry={
            "wheel_diameter_mm": 43.2,
            "axle_track_mm": track,
            "drive_gear_ratio": ratio,
            "mass_g": 620.0,
        },
        load="heavy",
    )


DRIVEBASE_2WD = Module(
    info=ModuleInfo(
        id="drivebase.2wd",
        summary="Differential drive: 2 large motors, 2 x 43.2mm wheels, rear ball caster. "
        "Root module; carries the EV3 brick. Optional gear reduction.",
        params=[
            ParamSpec(
                name="axle_track_mm",
                type="float",
                description="Distance between wheel centers. Wider = more stable turns.",
                default=120.0,
                min=80.0,
                max=200.0,
            ),
            ParamSpec(
                name="gear_ratio",
                type="enum",
                description="motor_teeth:wheel_teeth. '1:1' is direct drive.",
                default="1:1",
                choices=["1:1", "12:20", "12:36", "20:12", "20:36", "36:12"],
            ),
            ParamSpec(
                name="gear_center_distance_studs",
                type="float",
                description="Center distance of the gear pair in studs; must equal (t1+t2)/32. Ignored for 1:1.",
                default=1.0,
                min=0.5,
                max=3.0,
            ),
        ],
        mounts_on=None,
        provides_sockets=["front:front_mount", "top:beam_face", "rear:beam_face"],
    ),
    resolve=_drivebase_2wd,
    tags=["drive", "root"],
)


# --------------------------------------------------------------------------
# sensor.color_down — color sensor pointing at the floor for line following.
# --------------------------------------------------------------------------
def _sensor_color_down(p: dict[str, Any]) -> ResolvedModule:
    h = float(p["height_mm"])
    if not 5.0 <= h <= 15.0:
        raise ModuleParamError(
            "sensor.color_down: the EV3 color sensor reads reflected light reliably "
            "only ~5-15 mm above the surface"
        )
    return ResolvedModule(
        module_id="sensor.color_down",
        parts={COLOR: 1, BEAM5: 1, BEAM_L35: 1, PIN: 4, PIN3: 2},
        mounts_on="front_mount",
        devices=[Device(role="color", kind=DeviceKind.SENSOR_COLOR)],
        geometry={"sensor_height_mm": h, "mass_g": 45.0},
        load="light",
    )


SENSOR_COLOR_DOWN = Module(
    info=ModuleInfo(
        id="sensor.color_down",
        summary="Color/reflected-light sensor pointing down at the floor, mounted in front. "
        "Needed for line following.",
        params=[
            ParamSpec(
                name="height_mm",
                type="float",
                description="Sensor face height above the floor (5-15mm works).",
                default=8.0,
            )
        ],
        mounts_on="front_mount",
    ),
    resolve=_sensor_color_down,
    tags=["sensor", "line"],
)


# --------------------------------------------------------------------------
# sensor.ir_front / ultrasonic — distance sensing forward.
# --------------------------------------------------------------------------
def _sensor_forward(kind: DeviceKind, ldraw: str, mid: str):
    def resolve(p: dict[str, Any]) -> ResolvedModule:
        return ResolvedModule(
            module_id=mid,
            parts={ldraw: 1, BEAM5: 1, PIN: 4},
            mounts_on="beam_face",
            devices=[Device(role="distance", kind=kind)],
            geometry={"mass_g": 40.0},
            load="light",
        )

    return resolve


SENSOR_IR_FRONT = Module(
    info=ModuleInfo(
        id="sensor.ir_front",
        summary="Infrared sensor facing forward (proximity ~5-70cm, also IR beacon). Retail 31313 has this.",
        params=[],
        mounts_on="beam_face",
    ),
    resolve=_sensor_forward(DeviceKind.SENSOR_IR, IR, "sensor.ir_front"),
    tags=["sensor", "distance"],
)

SENSOR_ULTRASONIC_FRONT = Module(
    info=ModuleInfo(
        id="sensor.ultrasonic_front",
        summary="Ultrasonic sensor facing forward (3-250cm). Education 45544 kit only.",
        params=[],
        mounts_on="beam_face",
    ),
    resolve=_sensor_forward(DeviceKind.SENSOR_ULTRASONIC, ULTRA, "sensor.ultrasonic_front"),
    tags=["sensor", "distance"],
)


# --------------------------------------------------------------------------
# sensor.touch_bumper — touch sensor behind a beam bumper.
# --------------------------------------------------------------------------
def _touch_bumper(p: dict[str, Any]) -> ResolvedModule:
    return ResolvedModule(
        module_id="sensor.touch_bumper",
        parts={TOUCH: 1, BEAM7: 1, BEAM5: 1, PIN: 4, AXLEPIN: 2},
        mounts_on="front_mount",
        devices=[Device(role="bumper", kind=DeviceKind.SENSOR_TOUCH)],
        geometry={"mass_g": 50.0},
        load="light",
    )


SENSOR_TOUCH_BUMPER = Module(
    info=ModuleInfo(
        id="sensor.touch_bumper",
        summary="Touch sensor with a wide beam bumper, mounted in front. Good for sumo / collision.",
        params=[],
        mounts_on="front_mount",
    ),
    resolve=_touch_bumper,
    tags=["sensor", "touch"],
)


# --------------------------------------------------------------------------
# arm.gripper — medium motor driving a two-jaw gripper via a gear pair.
# --------------------------------------------------------------------------
def _gripper(p: dict[str, Any]) -> ResolvedModule:
    driver_t, driven_t = (int(x) for x in p["gear_ratio"].split(":"))
    return ResolvedModule(
        module_id="arm.gripper",
        parts={
            MOTOR_M: 1,
            GEAR_BY_TEETH[driver_t]: 1,
            GEAR_BY_TEETH[driven_t]: 2,
            BEAM7: 2,
            BEAM5: 2,
            BEAM_L35: 2,
            AXLE5: 1,
            AXLE3: 2,
            PIN: 10,
            HALFBUSH: 4,
        },
        mounts_on="front_mount",
        devices=[Device(role="gripper_motor", kind=DeviceKind.MOTOR_MEDIUM)],
        gear_pairs=[
            GearPair(
                driver_ldraw=GEAR_BY_TEETH[driver_t],
                driven_ldraw=GEAR_BY_TEETH[driven_t],
                center_distance_studs=p["gear_center_distance_studs"],
            )
        ],
        geometry={
            "gripper_gear_ratio": driven_t / driver_t,
            "jaw_opening_mm": float(p["jaw_opening_mm"]),
            "mass_g": 160.0,
        },
        load="medium",
    )


ARM_GRIPPER = Module(
    info=ModuleInfo(
        id="arm.gripper",
        summary="Two-jaw gripper driven by the medium motor through a gear pair. Mounts in front. "
        "Picks up ~50mm objects like a cube.",
        params=[
            ParamSpec(
                name="gear_ratio",
                type="enum",
                description="motor_teeth:jaw_teeth; bigger second number = stronger, slower grip.",
                default="12:36",
                choices=["12:20", "12:36", "20:36"],
            ),
            ParamSpec(
                name="gear_center_distance_studs",
                type="float",
                description="Center distance of the gear pair in studs; must equal (t1+t2)/32.",
                default=1.5,
            ),
            ParamSpec(
                name="jaw_opening_mm",
                type="float",
                description="Max opening between jaws.",
                default=60.0,
                min=30.0,
                max=120.0,
            ),
        ],
        mounts_on="front_mount",
    ),
    resolve=_gripper,
    tags=["arm", "manipulator"],
)


# --------------------------------------------------------------------------
# arm.lift — medium motor lifting a forward beam arm (forklift style).
# --------------------------------------------------------------------------
def _lift(p: dict[str, Any]) -> ResolvedModule:
    driver_t, driven_t = (int(x) for x in p["gear_ratio"].split(":"))
    length = int(p["arm_length_holes"])
    beam = {7: BEAM7, 9: BEAM9, 11: BEAM11, 13: BEAM13}[length]
    parts = {MOTOR_M: 1, beam: 2, BEAM5: 2, AXLE7: 1, PIN: 8, BUSH: 2}
    gear_pairs: list[GearPair] = []
    if p["gear_ratio"] != "1:1":
        parts[GEAR_BY_TEETH[driver_t]] = 1
        parts[GEAR_BY_TEETH[driven_t]] = parts.get(GEAR_BY_TEETH[driven_t], 0) + 1
        parts[AXLE3] = 1
        gear_pairs.append(
            GearPair(
                driver_ldraw=GEAR_BY_TEETH[driver_t],
                driven_ldraw=GEAR_BY_TEETH[driven_t],
                center_distance_studs=p["gear_center_distance_studs"],
            )
        )
    return ResolvedModule(
        module_id="arm.lift",
        parts=parts,
        mounts_on="front_mount",
        devices=[Device(role="lift_motor", kind=DeviceKind.MOTOR_MEDIUM)],
        gear_pairs=gear_pairs,
        geometry={
            "lift_gear_ratio": driven_t / driver_t,
            "arm_length_mm": length * 8.0,
            "payload_g": float(p["payload_g"]),
            "mass_g": 140.0 + length * 6,
        },
        load="medium",
    )


ARM_LIFT = Module(
    info=ModuleInfo(
        id="arm.lift",
        summary="Forklift-style lifting arm on the medium motor. Mounts in front. "
        "Declare the payload so torque can be checked.",
        params=[
            ParamSpec(
                name="arm_length_holes",
                type="enum",
                description="Beam length of the arm in holes.",
                default=9,
                choices=[7, 9, 11, 13],
            ),
            ParamSpec(
                name="gear_ratio",
                type="enum",
                description="motor_teeth:arm_teeth.",
                default="12:36",
                choices=["1:1", "12:20", "12:36", "20:36"],
            ),
            ParamSpec(
                name="gear_center_distance_studs",
                type="float",
                description="Center distance of the gear pair in studs; must equal (t1+t2)/32.",
                default=1.5,
            ),
            ParamSpec(
                name="payload_g",
                type="float",
                description="Mass the arm must lift at its tip.",
                default=50.0,
                min=0.0,
                max=1000.0,
            ),
        ],
        mounts_on="front_mount",
    ),
    resolve=_lift,
    tags=["arm", "lift"],
)


# --------------------------------------------------------------------------
# sensor.gyro_top — gyro on top for heading control.
# --------------------------------------------------------------------------
def _gyro(p: dict[str, Any]) -> ResolvedModule:
    return ResolvedModule(
        module_id="sensor.gyro_top",
        parts={GYRO: 1, PIN: 2},
        mounts_on="beam_face",
        devices=[Device(role="gyro", kind=DeviceKind.SENSOR_GYRO)],
        geometry={"mass_g": 25.0},
        load="light",
    )


SENSOR_GYRO_TOP = Module(
    info=ModuleInfo(
        id="sensor.gyro_top",
        summary="Gyro sensor mounted flat on a beam face for precise turns. Education kit only.",
        params=[],
        mounts_on="beam_face",
    ),
    resolve=_gyro,
    tags=["sensor", "gyro"],
)


LIBRARY: dict[str, Module] = {
    m.info.id: m
    for m in [
        DRIVEBASE_2WD,
        SENSOR_COLOR_DOWN,
        SENSOR_IR_FRONT,
        SENSOR_ULTRASONIC_FRONT,
        SENSOR_TOUCH_BUMPER,
        ARM_GRIPPER,
        ARM_LIFT,
        SENSOR_GYRO_TOP,
    ]
}


def describe_library() -> str:
    """Compact text the LLM sees when choosing modules."""
    lines = []
    for m in LIBRARY.values():
        i = m.info
        lines.append(f"- {i.id}: {i.summary}")
        lines.append(f"    mounts_on={i.mounts_on or 'ROOT'} provides={i.provides_sockets or '-'}")
        for p in i.params:
            extra = f" choices={p.choices}" if p.choices else ""
            rng = (
                f" range=[{p.min},{p.max}]" if p.min is not None or p.max is not None else ""
            )
            lines.append(f"    param {p.name} ({p.type}, default={p.default!r}){extra}{rng}: {p.description}")
    return "\n".join(lines)
