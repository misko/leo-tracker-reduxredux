import json
from dataclasses import dataclass
from types import SimpleNamespace

import full_incumbent_merge_study as study
import numpy as np
import pytest

from leo.analysis.regional_position_bootstrap import PositionBootstrap


@dataclass
class ObservationFixture:
    measured_hz: np.ndarray
    rf_hz: np.ndarray
    margin: np.ndarray


def prepared():
    return SimpleNamespace(
        candidate_ids=("a", "b"),
        observations=ObservationFixture(
            np.array([100.0, 200.0]), np.array([11.2e9, 12.05e9]), np.array([0.5, 0.1])
        ),
    )


def test_mismatched_rf_or_candidate_identity_cannot_enter_comparison():
    original, joined = prepared(), prepared()
    study.matched_observations(original, joined)
    joined.observations.rf_hz[1] += 850e6
    with pytest.raises(ValueError, match="rf_hz"):
        study.matched_observations(original, joined)
    joined = prepared()
    joined.candidate_ids = ("b", "a")
    with pytest.raises(ValueError, match="candidate inventory"):
        study.matched_observations(original, joined)


def test_compact_audit_preserves_selected_bank_order_and_all_events():
    packets = [PositionBootstrap((2, 0), np.arange(8.0), ())]
    receipt = {
        "selected": 0,
        "candidate_packets": packets,
        "events": [{"status": "failed", "reason": "timeout"}],
        "complete_path": False,
        "timed_out": True,
    }
    result = study.compact_audit(receipt, SimpleNamespace(numbers=np.array([501, 502, 503])))
    assert result["selected_satellites"] == [503, 501]
    assert result["selected_vector"] == list(np.arange(8.0))
    assert result["events"] == receipt["events"]
    assert result["timed_out"] and not result["complete_path"]
    assert "candidate_packets" not in result
    assert receipt["candidate_packets"] is packets


@pytest.mark.parametrize("role", ["development", "validation"])
def test_freeze_discards_earlier_selected_point_and_enforces_recording_role(
    tmp_path, monkeypatch, role
):
    parent, old = tmp_path / "parent", tmp_path / "original"
    parent.mkdir()
    (old / "positions").mkdir(parents=True)
    bank = old / "positions/bank.npz"
    bank.write_bytes(b"frozen bank")
    (old / "positions/experiment.json").write_text(json.dumps({"bank_sha256": study.sha(bank)}))
    (old / "census.json").write_text(json.dumps({"member": {"role": role}}))
    for name in ("baseline.json", "replace-guard.json"):
        (old / name).write_text("{}")
    (parent / "protocol.json").write_text(
        json.dumps(
            {
                "bindings": {},
                "cases": [
                    {
                        "dataset": "DS20",
                        "session_id": "recording",
                        "original_case": str(old),
                        "calibrations": ["raw"],
                        "point": [123, 456],
                        "point_source": "forbidden",
                    }
                ],
                "modes": {"original-control": ["none", "baseline"]},
                "configuration": {},
                "fixed_band_offsets_hz": [0, 0],
            }
        )
    )
    monkeypatch.setattr(study, "PARENT", parent)
    monkeypatch.setattr(study, "OUTPUT", tmp_path / "output")
    monkeypatch.setattr(study, "load_prepared", lambda path: prepared())
    monkeypatch.setattr(study, "verify", lambda bindings: None)
    if role == "validation":
        with pytest.raises(ValueError, match="development panel role"):
            study.freeze()
        assert not (study.OUTPUT / "protocol.json").exists()
        return
    study.freeze()
    protocol = json.loads((study.OUTPUT / "protocol.json").read_bytes())
    case = protocol["cases"][0]
    assert "point" not in case and "point_source" not in case
    assert case["role"] == "development"
    assert protocol["configuration"] == study.configuration()
    assert "400-point" in protocol["scope"]
    with pytest.raises(ValueError, match="already frozen"):
        study.freeze()
