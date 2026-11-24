from math import sqrt

import pytest

from reports.ALGO08.v3.calibration_prediction_check import assess, predictive_mse
from reports.ALGO08.v3 import calibration_prediction_audit as audit


def arm(conditional_rms, prediction_mse):
    return dict(conditional_count=2, predictive_count=1, conditional_rms_hz=conditional_rms,
                all_owned_rms_hz=sqrt((2*conditional_rms**2 + prediction_mse)/3))


def test_worsening_prediction_under_improved_conditional_fit():
    good = {"c0": arm(5., 16.), "fitted_c": arm(4., 16.)}
    bad = {"c0": arm(5., 16.), "fitted_c": arm(4., 60.)}
    assert assess(good, True)["status"] == "pass"
    assert assess(bad, True)["status"] == "suspect"
    bad["fitted_c"] = arm(5., 60.)
    assert assess(bad, True)["status"] == "pass"


def test_unmatched_owners_or_missing_out_of_fit_data_abstain():
    arms = {"c0": arm(5., 16.), "fitted_c": arm(4., 60.)}
    assert assess(arms, False)["status"] == "unavailable"
    arms["fitted_c"]["predictive_count"] = 0
    assert assess(arms, True)["status"] == "unavailable"
    arms["fitted_c"] = arm(4., 60.) | {"all_owned_rms_hz": None}
    assert assess(arms, True)["status"] == "unavailable"


def test_role_weighting_and_bad_residual_authority():
    assert predictive_mse(5., arm(5., 16.)["all_owned_rms_hz"], 2, 1) == pytest.approx(16.)
    assert predictive_mse(0., 0., 2, 1) == 0
    with pytest.raises(ValueError, match="incompatible"):
        predictive_mse(5., 1., 2, 1)


def test_archived_roles_bind_the_runtime_observable(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, "TMPFS", tmp_path)
    monkeypatch.setitem(audit.SCOPES, "test", ("capture", "witness.json"))
    root = tmp_path / "capture"
    terminal_path = root / "fast-scan-automatic-work/run/terminal.json"
    terminal_path.parent.mkdir(parents=True)
    terminal = dict(decision="ok", native_sha256="signed-input",
                    arms={key: dict(latlon=[0., 1.], rf_rms_hz=rms)
                          for key, rms in (("c0", 10.), ("fitted_c", 9.))})
    audit.seal(terminal_path, terminal)
    rows = [["a", 1, "conditional"], ["b", 2, "predictive"]]
    preview = dict(associated_points=2, owner_sha256=audit.canonical({"a": 1, "b": 2}), endpoint_latlon=[0., 1.])
    figure = root / "fast-scan-standard-v2/run/final-error-v7/manifest.json"
    figure.parent.mkdir(parents=True)
    audit.seal(figure, dict(terminal_sha256=audit.canonical(terminal), input_sha256="signed-input",
                          arms={key: dict(preview, residual_rms_hz=rms)
                                for key, rms in (("c0", 10.), ("fitted_c", 40.))}))
    proof = root / "witness.json"
    audit.seal(proof, {"selected_rows": {arm: rows for arm in audit.ARMS}})
    assert audit.evidence("test")["status"] == "suspect"
    proof.unlink()
    audit.seal(proof, {"selected_rows": {"c0": rows, "fitted_c": rows[::-1]}})
    assert audit.evidence("test")["status"] == "unavailable"
    proof.unlink()
    audit.seal(proof, {"selected_rows": {arm: [["a", 99, "conditional"], rows[1]] for arm in audit.ARMS}})
    with pytest.raises(ValueError, match="ordered rows"):
        audit.evidence("test")
