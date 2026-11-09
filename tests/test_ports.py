from bobthebuilder.spec import ModuleInstance, Port, RobotSpec
from bobthebuilder.validators.base import check_port_conflicts


def _spec(*modules: ModuleInstance) -> RobotSpec:
    return RobotSpec(name="t", task="t", modules=list(modules))


def test_no_conflict():
    spec = _spec(
        ModuleInstance(
            id="drive",
            module="drivebase.2wd",
            ports={"left_motor": Port.B, "right_motor": Port.C},
        )
    )
    assert check_port_conflicts(spec) == []


def test_conflict_detected():
    spec = _spec(
        ModuleInstance(id="drive", module="drivebase.2wd", ports={"left_motor": Port.B}),
        ModuleInstance(id="arm", module="arm.lift", ports={"motor": Port.B}),
    )
    errors = check_port_conflicts(spec)
    assert [e.code for e in errors] == ["PORT_CONFLICT"]
