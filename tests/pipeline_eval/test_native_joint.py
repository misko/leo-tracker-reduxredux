import pytest

from tools.pipeline_eval.qualification import native_joint_trial as trial
from tools.pipeline_eval.qualification import native_joint_worker as splice
from tools.pipeline_eval.variants import joint_orbits, robust_orbit_fit


def test_native_splice_uses_the_joint_infer_and_restores_the_frozen_frontend(monkeypatch):
    original = robust_orbit_fit.infer
    monkeypatch.setattr(splice, "setrlimit", lambda *args: None)

    def graph(request):
        assert request == {"mode": "native"}
        assert robust_orbit_fit.infer is joint_orbits.infer
        return dict(
            stages={
                "same_exact_backend": {"cpu_s": 0.1, "wall_s": 0.2},
                "backend_import": {"cpu_s": 0.0, "wall_s": 0.0},
            },
            result={},
        )

    monkeypatch.setattr(splice.native, "worker", graph)
    out = splice.worker({"mode": "native"})
    assert out["result"]["boundary"] == splice.BOUNDARY
    assert out["stages"]["joint_backend"] == {"cpu_s": 0.1, "wall_s": 0.2}
    assert robust_orbit_fit.infer is original
    with pytest.raises(ValueError, match="complete native factors"):
        splice.worker({"mode": "prepared"})


def test_added_confirmation_is_disjoint_and_alternate_tile_has_same_native_inputs():
    frames = [q for q, _ in trial.jobs(trial.phase.frozen_inputs())]
    joint = trial.phase._read(trial.JOINT / "source-lock.json")["cases"]
    confirmation = [q["id"] for q in frames if q["cohort"] == "confirmation"]
    assert confirmation == ["DS26-0231", "DS26-0223", "DS29-0316"]
    assert not set(confirmation) & (set(joint) | set(trial.native.CASES))
    base, wrong = (frames[index]["packet"] for index in (0, -1))
    assert wrong["offer"]["id"] == "r0"
    assert {k: v for k, v in base.items() if k != "offer"} == {
        k: v for k, v in wrong.items() if k != "offer"
    }
