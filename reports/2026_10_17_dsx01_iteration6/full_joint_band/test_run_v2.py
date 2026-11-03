"""Component checks for the all-source harness; model algebra owned by B's tests."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from numpy.testing import assert_array_equal

SPEC = importlib.util.spec_from_file_location(
    "full_joint_driver", Path(__file__).with_name("run_v2.py")
)
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)


def test_c0_changes_only_c_and_retains_complete_fitted_seed():
    seed = dict(vector=list(np.arange(20, dtype=float)), nuisance=[2.0, 3.0, 4.0])
    v, n = run.seed_for(seed, "zero-c")
    expected = np.arange(20, dtype=float)
    expected[6] = 0
    assert_array_equal(v, expected)
    assert_array_equal(n, seed["nuisance"])
    v[0] = 999
    n[0] = 999
    assert seed["vector"][0] == 0 and seed["nuisance"][0] == 2
    fit_v, fit_n = run.seed_for(seed, "fitted-c")
    assert_array_equal(fit_v, seed["vector"])
    assert_array_equal(fit_n, seed["nuisance"])
    with pytest.raises(ValueError):
        run.seed_for(seed, "unknown")


def test_source_bindings_reject_mutation(tmp_path):
    path = tmp_path / "input.json"
    path.write_text("original")
    bound = {str(path): run.digest(path)}
    run.verify_bindings(bound)
    path.write_text("changed")
    with pytest.raises(ValueError, match="Frozen source/input changed"):
        run.verify_bindings(bound)


def test_exclusive_receipts_never_overwrite(tmp_path):
    path = tmp_path / "receipt.json"
    run.save(path, dict(vector=np.array([1.0, 2.0]), accepted=False))
    with pytest.raises(FileExistsError):
        run.save(path, dict(accepted=True))
    assert not run.read(path)["accepted"]


def test_full_matrix_and_original_model_modules_are_exact():
    assert len(run.SOURCES) * len(run.ARMS) * len(run.METHODS) == 20
    assert Path(run.fit_free.__code__.co_filename).resolve() == run.JOINT / "fit.py"
    assert Path(run.free_context.__code__.co_filename).resolve() == run.JOINT / "model.py"


def test_selector_retains_lower_objective_nonstrict_and_rejects_infeasible():
    points = {
        label: dict(audit=dict(training_objective=j, feasible=feasible, accepted=strict))
        for label, j, feasible, strict in [
            ("old", 10.0, True, True),
            ("new", 8.0, True, False),
            ("bad", 1.0, False, False),
        ]
    }
    label, point = run.choose(points)
    assert label == "new" and not point["audit"]["accepted"]
    with pytest.raises(ValueError):
        run.choose({"bad": points["bad"]})


def test_real_seed_optional_mode_and_exact_source_authority():
    item = dict(job_id="j", tracking_input_sha256="i", terminal_sha256="t", tle_sha256="e")
    seed = dict(source_id="S01", arm="fitted-c", method="profile", source=item.copy())
    run.validate_seed(seed, "S01", item)
    seed["mode"] = "full"
    run.validate_seed(seed, "S01", item)
    seed["mode"] = "early_to_late"
    with pytest.raises(ValueError):
        run.validate_seed(seed, "S01", item)
    del seed["mode"]
    seed["source"]["job_id"] = "wrong"
    with pytest.raises(ValueError, match="source authority mismatch"):
        run.validate_seed(seed, "S01", item)
