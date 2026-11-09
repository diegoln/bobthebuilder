from pathlib import Path

from bobthebuilder.codegen.pybricks import generate
from bobthebuilder.loop import Lessons, Trace, render_prompt, run_design_loop
from bobthebuilder.proposers import ScriptedProposer
from bobthebuilder.spec import ModuleInstance, Port, RobotSpec


def bad_then_good():
    bad = RobotSpec(
        name="r",
        task="follow a line",
        modules=[
            ModuleInstance(
                id="drive",
                module="drivebase.2wd",
                params={"gear_ratio": "12:36", "gear_center_distance_studs": 1.0},
                ports={"left_motor": Port.B, "right_motor": Port.B},
            ),
            ModuleInstance(id="eye", module="sensor.color_down", ports={"color": Port.S3}),
        ],
    )
    good = bad.model_copy(deep=True)
    good.modules[0].params["gear_center_distance_studs"] = 1.5
    good.modules[0].ports["right_motor"] = Port.C
    good.modules[1].attach_to = "drive.front"
    return bad, good


def test_loop_converges_and_feeds_errors_back(tmp_path: Path):
    bad, good = bad_then_good()
    proposer = ScriptedProposer([bad, good])
    trace = Trace(tmp_path / "trace.jsonl")
    result = run_design_loop("follow a line", proposer, trace=trace, max_iters=4)

    assert result.ok and result.iterations == 2
    # second call saw the first attempt's errors
    second_ctx = proposer.contexts[1]
    assert second_ctx.previous_spec is not None
    assert {e.code for e in second_ctx.previous_errors} >= {
        "PORT_CONFLICT", "GEAR_MESH_DISTANCE", "ATTACH_MISSING"
    }
    # trace persisted both attempts
    assert len(Trace(tmp_path / "trace.jsonl").attempts) == 2


def test_loop_gives_up_after_max_iters():
    bad, _ = bad_then_good()
    result = run_design_loop("follow a line", ScriptedProposer([bad]), max_iters=3)
    assert not result.ok and result.iterations == 3


def test_invalid_json_becomes_error_not_crash():
    _, good = bad_then_good()
    result = run_design_loop("x", ScriptedProposer(["not json", good]), max_iters=2)
    assert result.ok
    assert result.history[0].errors[0].code == "SPEC_INVALID_JSON"


def test_lessons_surface_repeated_mistakes_in_next_prompt(tmp_path: Path):
    bad, good = bad_then_good()
    trace = Trace(tmp_path / "trace.jsonl")
    # two runs that make the same mistake
    for _ in range(2):
        run_design_loop("follow a line", ScriptedProposer([bad, good]), trace=trace)
    rules = Lessons(trace).rules()
    assert any("GEAR_MESH_DISTANCE" in r for r in rules)

    # a third run gets those lessons in its context
    proposer = ScriptedProposer([good])
    run_design_loop("follow a line", proposer, trace=trace, lessons=Lessons(trace))
    prompt = render_prompt(proposer.contexts[0])
    assert "LESSONS FROM PAST RUNS" in prompt and "1.5" in prompt


def test_codegen_uses_design_geometry():
    _, good = bad_then_good()
    result = run_design_loop("follow a line", ScriptedProposer([good]))
    code = generate(result.resolved)
    assert "Motor(Port.B)" in code and "Motor(Port.C)" in code
    assert "ColorSensor(Port.S3)" in code
    assert "DRIVE_DRIVE_GEAR_RATIO = 3.0" in code
    assert "DriveBase(" in code
