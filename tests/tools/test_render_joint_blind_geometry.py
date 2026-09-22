import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


def module():
    path = (
        Path(__file__).parents[2] / "reports/2026_09_22_joint_blind_geometry/render_validation.py"
    )
    spec = importlib.util.spec_from_file_location("render_joint_blind_geometry", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def make_run(path, **overrides):
    path.mkdir()
    result = dict(
        complete=True,
        position_truth_used=False,
        region={"width_km": 5000},
        spacing_km=50,
        full_region_grid=True,
    )
    result.update(overrides)
    (path / "result.json").write_text(json.dumps(result))
    (path / "history.json").write_text(json.dumps([{"session_id": "a"}, {"session_id": "b"}]))
    np.savez(path / "grid.npz", latitude_deg=[0.0, 0.0], longitude_deg=[0.0, 10.0])
    for name, train in (("a", [10.0, 0.0]), ("b", [0.0, 4.0])):
        np.savez(path / f"{name}.npz", train_logbf=[train], heldout_logbf=[[0.0, 1e6]])


@pytest.mark.parametrize(
    "overrides",
    [{"complete": False}, {"position_truth_used": True}, {"prior_matched_norads_used": True}],
)
def test_unqualified_inputs_fail_before_truth_is_read(tmp_path, overrides):
    make_run(tmp_path / "run", **overrides)
    with pytest.raises(ValueError):
        module().evaluate([tmp_path / "run"], "a", tmp_path / "missing-truth", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_seal_precedes_reveal_and_heldout_does_not_select_position(tmp_path, monkeypatch):
    make_run(tmp_path / "run")
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps({"latitude_deg": 0.0, "longitude_deg": 10.0}))
    original_read = Path.read_text

    def guarded_read(path, *args, **kwargs):
        if path == truth:
            assert (tmp_path / "out/inference-seal.json").exists()
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    receipt = module().evaluate([tmp_path / "run"], "a", truth, tmp_path / "out")
    for row in receipt["results"]:
        assert row["longitude_deg"] == 0.0
        assert row["heldout_score_at_training_best"] == 0.0
        assert row["horizontal_error_km"] > 1100
    assert (tmp_path / "out/regional-training-maps.png").stat().st_size > 1000


def test_changed_refinement_is_rejected_before_reveal(tmp_path):
    make_run(tmp_path / "run")
    refinement = tmp_path / "refined"
    refinement.mkdir()
    (refinement / "result.json").write_text(
        json.dumps(
            {
                "complete": True,
                "position_truth_used": False,
            }
        )
    )
    (refinement / "result.sha256").write_text("invalid-old-digest")
    with pytest.raises(ValueError, match="seal mismatch"):
        module().evaluate(
            [tmp_path / "run"], "a", tmp_path / "missing-truth", tmp_path / "out", [refinement]
        )
    assert not (tmp_path / "out").exists()
