import json
from pathlib import Path

import pytest


@pytest.fixture
def crossover(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import full_short_crossover

    return full_short_crossover


def native(session, cfo, epoch=15):
    chosen = dict(candidate_rank=1, fractional_tracking_cfo_hz=cfo, fractional_margin=12.,
                  passed_fractional_margin_gate=True, integer_epoch_sample=epoch, fractional_epoch_offset_samples=.125)
    alternative = dict(chosen, candidate_rank=2, fractional_tracking_cfo_hz=999.)
    probe = dict(receiver_id=0, valid_start_counter=123, channel=1, edge="upper", actual_rf_hz=11e9,
                 candidates=[alternative, chosen])
    return {"source": {"session_id": session, "probes": [probe]}}


def test_owner_join_uses_original_counter_and_exact_cfo_across_observation_ids(crossover):
    first, other = ("sha256:" + crossover.digest(f"{s}:0:123".encode()) for s in ("before", "after"))
    a = crossover.normalized_owners(native("before", 134.), {"c0": [[first, 42, "conditional"]]})
    same = crossover.normalized_owners(native("after", 134.), {"c0": [[other, 48, "predictive"]]})
    new_cfo = crossover.normalized_owners(native("after", 135.), {"c0": [[other, 48, "predictive"]]})
    changed_epoch = crossover.normalized_owners(native("after", 134., epoch=16), {"c0": [[other, 42, "conditional"]]})
    exact = crossover.compare_owners(a, same)["c0"]
    assert exact["same_counter_cfo"] == exact["same_fractional_factor"] == 1
    assert exact["norad_changed_same_cfo"] == exact["role_changed_same_cfo"] == 1
    assert crossover.compare_owners(a, new_cfo)["c0"]["shared_counter_changed_cfo"] == 1
    assert crossover.compare_owners(a, new_cfo)["c0"]["norad_changed_same_cfo"] == 0
    assert crossover.compare_owners(a, changed_epoch)["c0"]["same_fractional_factor"] == 0
    assert crossover.compare_owners(a, None) is None


def test_failed_preflight_blocks_crossover_before_any_physical_input(crossover, tmp_path):
    path = tmp_path / "gate.json"
    path.write_text(json.dumps({"passed": False}))
    with pytest.raises(ValueError, match="no saved crossover"):
        crossover.check_gate(path)


def test_gate_requires_original_two_receiver_early_proof(crossover, tmp_path):
    path = tmp_path / "gate.json"
    guard = dict(complete=True, would_withhold=True,
                 receivers={str(rx): {"unique_exterior": True} for rx in (1, 2)})
    witness = dict(passed=True, proof=[{"result": guard}], result=dict(status="withheld", attempts=[], ranks=[]))
    path.write_text(json.dumps(witness))
    assert crossover.check_gate(path) == crossover.digest(path.read_bytes())
    guard["receivers"].pop("2")
    path.write_text(json.dumps(witness))
    with pytest.raises(ValueError, match="original early exterior proof"):
        crossover.check_gate(path)
