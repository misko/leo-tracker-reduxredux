"""Input causality and regional-grid checks need no radio corpus or GPS."""

import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "tools/dsx01_inference_audit.py"
SPEC = importlib.util.spec_from_file_location("dsx01_inference_audit_test", PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


@pytest.mark.parametrize(
    "record",
    [
        {"element_epoch_utc_ns": 11, "collected_utc_ns": 9},
        {"element_epoch_utc_ns": 9, "collected_utc_ns": 11},
        {"element_epoch_utc_ns": 9},
    ],
)
def test_epoch_and_actual_availability_both_required(record):
    with pytest.raises(ValueError):
        audit.causal_record(record, 10)


def test_cutoff_is_inclusive():
    assert audit.causal_record({"element_epoch_utc_ns": 10, "collected_utc_ns": 10}, 10)


def test_unknown_history_fields_cannot_hide_diagnostics():
    with pytest.raises(ValueError, match="unexpected field"):
        audit.validate_history({"1": [{"following": {}}]}, 10)


def test_radius_is_centered_on_regional_origin_and_inside_box():
    axis, points = audit.disk_grid()
    assert axis[0] == -10 and axis[-1] == 10
    assert (0, 0) in points and (10, 0) in points and (10, 10) not in points
    assert all(max(abs(e), abs(n)) <= audit.BOX_HALF_WIDTH_KM for e, n in points)


@pytest.mark.parametrize(
    "name",
    [
        "endpoints.json",
        "seed_bundle.json",
        "following/element.tle",
        "oracle_only/state.json",
        "shared_phase_center.json",
    ],
)
def test_runtime_guard_rejects_old_estimates_and_following_diagnostics(name):
    guard = audit.InferenceReadGuard(audit.ROOT / "reports/new_clean")
    with pytest.raises(ValueError, match="forbidden"):
        guard.check_path(str(audit.ROOT / "reports/old" / name))


def test_runtime_guard_records_raw_inputs_and_own_checkpoints():
    guard = audit.InferenceReadGuard(audit.ROOT / "reports/new_clean")
    path = str(audit.ROOT / "reports/raw/bank.npz")
    guard.check_path(path)
    assert path in guard.read_paths


@pytest.mark.parametrize(
    "name", ["following.tle", "position_and_gradient_summary.csv", "gps_invariance.json"]
)
def test_even_own_postfit_diagnostics_cannot_become_inference_inputs(name):
    guard = audit.InferenceReadGuard(audit.ROOT / "reports/new_clean")
    with pytest.raises(ValueError, match="forbidden"):
        guard.check_path(str(audit.ROOT / "reports/new_clean" / name))


def test_unreviewed_fixed_site_results_cannot_enter_through_an_innocent_filename():
    guard = audit.InferenceReadGuard(audit.ROOT / "reports/new_clean")
    with pytest.raises(ValueError, match="forbidden"):
        guard.check_path(str(audit.ROOT / "reports/old_fixed_site/trimmed/results.json"))


def test_early_provenance_cannot_authorize_future_epoch_in_actual_element_bytes(monkeypatch):
    monkeypatch.setattr(audit, "element_epoch_ns", lambda lines: 20)
    row = dict(
        lines=["line1", "line2"], provenance=dict(element_epoch_utc_ns=1, collected_utc_ns=2)
    )
    with pytest.raises(ValueError, match="future element epoch"):
        audit.validate_elements(row, 10)


def test_isolated_loader_has_no_mixed_catalogue_fallback(tmp_path):
    with pytest.raises(ValueError, match="export isolated"):
        audit.load_isolated_catalogue(tmp_path / "missing.json", {}, [1])


def test_isolated_loader_cannot_accept_preselected_subset_or_other_scan(tmp_path):
    receipt = dict(cutoff_utc_ns=10, origin_utc_ns=11, bank_sha256="bank")
    path = tmp_path / "elements.json"
    path.write_text(json.dumps(dict(receipt, satellites={"1": {}})))
    with pytest.raises(ValueError, match="complete regional"):
        audit.load_isolated_catalogue(path, receipt, [1, 2])
    path.write_text(json.dumps(dict(receipt, origin_utc_ns=12, satellites={"1": {}})))
    with pytest.raises(ValueError, match="another scan"):
        audit.load_isolated_catalogue(path, receipt, [1])
