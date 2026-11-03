import importlib.util
import sys
from pathlib import Path


PATH = Path(__file__).with_name("features.py")
SPEC = importlib.util.spec_from_file_location("sacramento_features", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_epochs_and_receiver_labels_do_not_fabricate_features():
    audit = MODULE.audit_evidence_documents(
        [{"tracks": [{"receiver_id": 1, "times_utc_ns": [1, 2], "measured_hz": [3, 4], "aliases": [], "discontinuities": []}]}]
    )
    assert audit.observations == 2
    assert audit.toa_observations == 0
    assert audit.calibrated_rx_likelihoods == 0
    assert audit.relative_timing_observations == 0
    decisions = MODULE.model_decisions(audit)
    assert all(row["status"].startswith("not_evaluated") for row in decisions.values())


def test_explicit_qualified_features_pass_their_structural_gates():
    track = {
        "times_utc_ns": [1, 2, 3],
        "toa_s": 0.01,
        "toa_doppler_covariance": [[1.0, 0.0], [0.0, 1.0]],
        "receiver_membership_calibration": {"status": "calibrated"},
        "tdoa_s": 1e-7,
        "timing_covariance_s2": 1e-16,
    }
    audit = MODULE.audit_evidence_documents([{"tracks": [track]}])
    decisions = MODULE.model_decisions(audit)
    assert {key: row["status"] for key, row in decisions.items()} == {
        "M6": "feasible",
        "M7": "feasible",
        "M10": "feasible",
    }


def test_zero_or_malformed_covariance_does_not_pass():
    audit = MODULE.audit_evidence_documents(
        [{"tracks": [{"times_utc_ns": [1], "toa_s": 0.1, "tdoa_s": 0.2, "timing_covariance_s2": 0.0}]}]
    )
    decisions = MODULE.model_decisions(audit)
    assert decisions["M6"]["status"] == "not_evaluated_missing_qualified_input"
    assert decisions["M10"]["status"] == "not_evaluated_missing_qualified_input"
