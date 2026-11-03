import json

import pytest
from cohort_run import digest, find_unit, load_rough_seed, run_unit


def test_find_unit_preserves_dataset_and_children():
    unit = {"unit_id": "DS10-D01", "session_ids": ["first", "second"]}
    selection = {"datasets": {"DS10": {"units": [unit]}}}
    assert find_unit(selection, "DS10-D01") == ("DS10", unit)
    with pytest.raises(ValueError, match="exactly once"):
        find_unit(selection, "absent")
    selection["datasets"]["DS11"] = {"units": [unit]}
    with pytest.raises(ValueError, match="exactly once"):
        find_unit(selection, "DS10-D01")


@pytest.mark.parametrize("run_id", ["", "..", ".", "../escape", "/absolute"])
def test_run_id_cannot_escape_output_directory(run_id):
    with pytest.raises(ValueError, match="path component"):
        run_unit("unused", run_id)


def test_alternative_optimizer_requires_annealed_mode():
    with pytest.raises(ValueError, match="requires annealed"):
        run_unit("unused", "test", rough_only=True, optimizer="gauss-newton")


def test_rough_cache_binds_inputs_selection_and_solver_without_evaluation(tmp_path):
    (tmp_path / "selection.json").write_text("{}")
    (tmp_path / "track_seed.py").write_text("frozen solver")
    unit = {"unit_id": "test-unit", "size": 1}
    folder = tmp_path / "runs" / "baseline" / "test-unit"
    folder.mkdir(parents=True)
    receipt = {
        "stage": "rough",
        "unit": unit,
        "inputs": {"scan": "digest"},
        "selection_sha256": digest(tmp_path / "selection.json"),
        "source_hashes": {"track_seed.py": digest(tmp_path / "track_seed.py")},
        "fit": {"position_km": [1, 2]},
    }
    path = folder / "fit.json"
    path.write_text(json.dumps(receipt))
    fit, bound_digest = load_rough_seed(tmp_path, "baseline", unit, {"scan": "digest"})
    assert fit == receipt["fit"]
    assert bound_digest == digest(path)
    with pytest.raises(ValueError, match="input bindings"):
        load_rough_seed(tmp_path, "baseline", unit, {"scan": "changed"})
    (tmp_path / "track_seed.py").write_text("changed solver")
    with pytest.raises(ValueError, match="different rough solver"):
        load_rough_seed(tmp_path, "baseline", unit, {"scan": "digest"})
