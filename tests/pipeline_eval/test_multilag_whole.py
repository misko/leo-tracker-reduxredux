import json

import pytest

from tools.pipeline_eval.qualification import multilag_whole_results as whole


def test_reverse_lane_binding_validates_and_retains_actual_entry_affinity(tmp_path, monkeypatch):
    ident = "DS29-0519"
    entry = tmp_path / ident / "candidate/start.json"
    entry.parent.mkdir(parents=True)
    observed = {"cpus": [4, 5], "phase": "whole entry"}
    entry.write_text(json.dumps(observed))
    (entry.parent / "service.json").touch()
    lock = {"cases": {ident: {"cpus": [5, 4]}}}

    def shared_receipt(work, case, role, plan, *, method):
        actual = whole.whole_iq.read(work / case / role / "start.json")
        assert actual["cpus"] == plan["cases"][case]["cpus"]
        return {"method": method}, {"stages": [actual, {"cpus": [5]}]}, None

    monkeypatch.setattr(whole.measured, "attempt", shared_receipt)
    _, proof, _ = whole.attempt(tmp_path, ident, lock)
    assert proof["stages"] == [observed, {"cpus": [5]}]
    assert json.loads(entry.read_bytes()) == observed
    lock["cases"][ident]["cpus"][1] = 6
    with pytest.raises(ValueError, match="entry affinity"):
        whole.attempt(tmp_path, ident, lock)


def test_native_physical_match_keeps_clock_and_tuned_rf_bound():
    def packet(phase, cfo, rf=12_000_000_000):
        candidates = (
            []
            if phase is None
            else [
                dict(
                    integer_epoch_sample=phase,
                    fractional_epoch_offset_samples=0.0,
                    fractional_tracking_cfo_hz=cfo,
                    fractional_margin=0.08,
                    passed_fractional_margin_gate=True,
                    candidate_rank=0,
                )
            ]
        )
        return dict(
            clock_anchor=1,
            delivery_clocks=[2],
            last_sample_counter=3,
            provenance={},
            source=dict(probes=[dict(actual_rf_hz=rf, candidates=candidates)]),
        )

    original, missed = packet(150, 1400), packet(None, None)
    recovered = packet(151, 1420)
    found = whole.physical_counts(original, missed, missed, recovered)
    assert found["old_common_original_misses"] == 1
    assert found["recoveries_from_both_old_misses"] == 1
    with pytest.raises(ValueError, match="tuned RF differs"):
        whole.physical_counts(original, missed, missed, packet(151, 1420, rf=11_000_000_000))
