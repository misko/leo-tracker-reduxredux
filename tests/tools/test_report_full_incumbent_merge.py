import json

import numpy as np
import pytest
import report_full_incumbent_merge as report
from report_full_incumbent_merge import latest_common_stage, seal_terminals


def fit(converged=True, coefficient=0, length=9):
    vector = [0.0] * length
    vector[6] = coefficient
    return {"converged": converged, "vector": vector}


def test_latest_common_stage_keeps_a_stationary_fallback_pair():
    attempts = {
        "B7": {"fitted-c": fit(coefficient=4), "zero-c": fit(converged=False)},
        "C6": {"fitted-c": fit(coefficient=3), "zero-c": fit()},
        "B5": {"fitted-c": fit(), "zero-c": fit()},
        "removed_satellites": [123],
    }
    assert latest_common_stage(attempts) == "C6"
    assert latest_common_stage({"B7": attempts["B7"]}) is None


def test_unmatched_parameter_inventory_and_nonzero_locked_terms_are_rejected():
    for zero, message in (
        (fit(length=10), "inventories"),
        (fit(coefficient=1), "RF coefficient"),
        ({**fit(), "rf_drift_coefficients": [0.0, 1.0]}, "RF drift"),
    ):
        with pytest.raises(ValueError, match=message):
            latest_common_stage({"B7": {"fitted-c": fit(), "zero-c": zero}})


def test_seal_can_extend_but_cannot_accept_changed_existing_numerical_data(tmp_path):
    protocol, a, b, seal = [tmp_path / name for name in ("protocol", "a", "b", "seal")]
    protocol.write_bytes(b"protocol")
    a.write_bytes(b"first terminal")
    b.write_bytes(b"second terminal")
    seal_terminals(seal, protocol, [a])
    seal_terminals(seal, protocol, [a, b])
    assert set(json.loads(seal.read_bytes())["terminals"]) == {str(a), str(b)}
    a.write_bytes(b"changed terminal")
    with pytest.raises(ValueError, match="terminal changed"):
        seal_terminals(seal, protocol, [a, b])


def test_control_oracle_compares_catalogue_identity_before_seed_vectors(tmp_path, monkeypatch):
    previous = tmp_path / "previous"
    positions = previous / "local/DS20/recording/positions"
    (positions / "baseline").mkdir(parents=True)
    (positions / "experiment.json").write_text(json.dumps({"original_case": "/original/case"}))
    np.savez(positions / "bank.npz", numbers=np.array([101, 202]))
    points = {
        f"point:{index}:0": {
            "result": {
                "bootstrap": {
                    "vector": [0.0] * 8,
                    "satellite_indices": [1 if index == 0 else 0],
                }
            }
        }
        for index in range(2)
    }
    (positions / "baseline/terminal.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "result": {"points": points},
            }
        )
    )
    output = tmp_path / "output"
    (output / "bootstrap-audits").mkdir(parents=True)
    for index in range(2):
        (output / "bootstrap-audits" / f"{index}.json").write_text(
            json.dumps(
                {
                    "point": [index, 0],
                    "selected_satellites": [202],
                    "selected_vector": [0.0] * 8,
                }
            )
        )
    monkeypatch.setattr(report, "PREVIOUS", previous)
    result = report.control_oracle(
        {"dataset": "DS20", "session_id": "recording", "original_case": "/original/case"}, output
    )
    assert result["shared_points"] == 2
    assert result["different_bank"] == 1
    assert result["different_vector"] == 0
    assert result["maximum_shared_vector_difference"] == 0
    assert len(result["input_bindings"]) == 5
