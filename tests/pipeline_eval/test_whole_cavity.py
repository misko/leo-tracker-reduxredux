from pathlib import Path

import pytest

from tools.pipeline_eval.qualification import cavity_lifetime_worker
from tools.pipeline_eval.qualification import whole_cavity_worker as candidate
from tools.pipeline_eval.qualification.whole_cavity_scores import arm_scores


def test_only_the_position_exec_is_rebound_to_the_lifetime_worker(monkeypatch):
    recorded = []
    old_script = str(Path(candidate.raw.__file__))
    target = ("python", "-B", old_script, "position", "output-folder", "unused-worker")
    environment = {"ONE_THREAD": "1"}

    def execute(executable, args, env):
        recorded.append((executable, args, env))

    def assemble(*args):
        assert args == ("ordinary inputs",)
        candidate.os.execve("python", target, environment)

    monkeypatch.setattr(candidate.os, "execve", execute)
    monkeypatch.setattr(candidate, "raw_assemble", assemble)
    candidate.assemble("ordinary inputs")
    executable, args, env = recorded[0]
    assert executable == "python"
    assert args == [
        "python",
        "-B",
        str(Path(candidate.__file__)),
        "position",
        "output-folder",
        str(Path(cavity_lifetime_worker.__file__)),
    ]
    assert env is environment
    assert candidate.os.execve is execute


def test_unrecognized_exec_cannot_redirect_an_unrelated_program(monkeypatch):
    def unexpected(*args):
        candidate.os.execve("python", ["python", "unknown"], {})

    monkeypatch.setattr(candidate, "raw_assemble", unexpected)
    with pytest.raises(ValueError, match="unrecognized"):
        candidate.assemble()


def test_export_retains_each_measured_cavity_rms():
    row = {
        "id": "test",
        "result": {
            "status": "ok",
            "metrics": {"c0_conditional_rms_hz": 999},
            "arms": {
                "c0": {"latlon": [38, -122], "rf_rms_hz": 101.5},
                "fitted_c": {"latlon": [38, -122], "rf_rms_hz": 102.75},
            },
        },
    }
    rows = arm_scores(row, [38, -122])
    assert [item["conditional_rms_hz"] for item in rows] == [101.5, 102.75]
