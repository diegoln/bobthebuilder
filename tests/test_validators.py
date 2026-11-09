from bobthebuilder.spec import ModuleInstance, Port, RobotSpec
from bobthebuilder.validators.base import hard_errors, validate


def codes(rs):
    return sorted(e.code for e in hard_errors(rs))


def line_follower(**drive_params):
    return RobotSpec(
        name="liner",
        task="follow a black line",
        modules=[
            ModuleInstance(
                id="drive",
                module="drivebase.2wd",
                params=drive_params,
                ports={"left_motor": Port.B, "right_motor": Port.C},
            ),
            ModuleInstance(
                id="eye",
                module="sensor.color_down",
                attach_to="drive.front",
                ports={"color": Port.S3},
            ),
        ],
    )


def test_clean_line_follower_passes():
    rs = validate(line_follower())
    assert codes(rs) == []


def test_port_conflict_and_wrong_kind():
    spec = line_follower()
    spec.modules[0].ports["right_motor"] = Port.B  # same as left
    assert "PORT_CONFLICT" in codes(validate(spec))
    spec = line_follower()
    spec.modules[1].ports = {"color": Port.A}  # sensor on a motor port
    assert "PORT_WRONG_KIND" in codes(validate(spec))


def test_missing_port():
    spec = line_follower()
    spec.modules[1].ports = {}
    assert codes(validate(spec)) == ["PORT_MISSING"]


def test_gear_mesh_distance_hint_is_actionable():
    rs = validate(line_follower(gear_ratio="12:36", gear_center_distance_studs=1.0))
    errs = [e for e in rs.errors if e.code == "GEAR_MESH_DISTANCE"]
    assert errs and "1.5" in errs[0].hint


def test_correct_gear_distance_passes():
    rs = validate(line_follower(gear_ratio="12:36", gear_center_distance_studs=1.5))
    assert "GEAR_MESH_DISTANCE" not in codes(rs)


def test_attach_errors():
    spec = line_follower()
    spec.modules[1].attach_to = None
    assert "ATTACH_MISSING" in codes(validate(spec))
    spec.modules[1].attach_to = "drive.nowhere"
    assert "ATTACH_UNKNOWN_SOCKET" in codes(validate(spec))
    spec.modules[1].attach_to = "drive.top"  # beam_face, needs front_mount
    assert "ATTACH_KIND_MISMATCH" in codes(validate(spec))


def test_unknown_module_is_an_error_not_a_crash():
    spec = line_follower()
    spec.modules.append(ModuleInstance(id="x", module="jetpack.v1"))
    assert "UNKNOWN_MODULE" in codes(validate(spec))


def test_inventory_short_when_two_drive_bases():
    spec = line_follower()
    spec.modules.append(
        ModuleInstance(
            id="drive2",
            module="drivebase.2wd",
            ports={"left_motor": Port.A, "right_motor": Port.D},
        )
    )
    c = codes(validate(spec))
    assert "INVENTORY_SHORT" in c  # only 2 large motors / 1 brick in the kit
    assert "ROOT_COUNT" in c


def test_task_coverage_asks_for_gripper():
    spec = line_follower()
    spec.task = "pick up a cube and bring it back"
    assert "TASK_NEEDS_MANIPULATOR" in codes(validate(spec))


def test_lift_torque_check():
    spec = line_follower()
    spec.task = "lift things"
    spec.modules[1] = ModuleInstance(
        id="arm",
        module="arm.lift",
        params={"arm_length_holes": 13, "gear_ratio": "1:1", "payload_g": 600,
                "gear_center_distance_studs": 0.5},
        attach_to="drive.front",
        ports={"lift_motor": Port.A},
    )
    c = codes(validate(spec))
    assert "TORQUE_INSUFFICIENT" in c
