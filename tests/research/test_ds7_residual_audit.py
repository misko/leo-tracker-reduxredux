import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))

import ds7_residual_audit as audit  # noqa: E402


def test_held_predictive_uses_training_posterior_weights():
    train = np.log([0.8, 0.2])
    held = np.log([0.25, 0.75])
    expected = np.log(0.8 * 0.25 + 0.2 * 0.75)
    np.testing.assert_allclose(
        audit.held_predictive_log_density(train, held), expected, rtol=1e-14
    )


def test_held_values_cannot_change_training_candidate_state(monkeypatch):
    mask = np.array([True, True, False])
    visible = np.array([True, True])

    def fake_profile(residual, supplied_mask):
        np.testing.assert_array_equal(supplied_mask, mask)
        training = residual[:, supplied_mask]
        score = -np.sum(training**2, axis=1)
        offsets = np.mean(training, axis=1)
        return score, score, [{"converged": True}] * 2, offsets

    monkeypatch.setattr(audit.solver, "profile", fake_profile)
    first = np.array([[1.0, 2.0, 10.0], [2.0, 4.0, 20.0]])
    changed_held = first.copy()
    changed_held[:, 2] = [-1e9, 1e9]
    state_a = audit.candidate_training_state(first, mask, visible)
    state_b = audit.candidate_training_state(changed_held, mask, visible)
    for left, right in zip(state_a[:3], state_b[:3], strict=True):
        np.testing.assert_array_equal(left, right)
    assert state_a[3] == state_b[3]


def test_sealed_response_rejects_session_reordering(tmp_path):
    unit = tmp_path / "single-001"
    unit.mkdir()
    request = unit / "request.json"
    response = unit / "response.json"
    request.write_text(json.dumps({"unit": {"unit_id": "single-001", "session_ids": ["a"]}}))
    response.write_text(json.dumps({"unit_id": "single-001"}))

    def digest(path):
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    (tmp_path / "seal.json").write_text(
        json.dumps(
            {
                "schema": "ds7-run-seal/v1",
                "files": {
                    "single-001/request.json": digest(request),
                    "single-001/response.json": digest(response),
                },
            }
        )
    )
    try:
        audit.load_sealed_response(response, "single-001", ["b"])
    except ValueError as exc:
        assert "session order mismatch" in str(exc)
    else:
        raise AssertionError("session reorder was accepted")
