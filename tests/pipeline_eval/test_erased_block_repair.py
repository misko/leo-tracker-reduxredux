from importlib import import_module
from pathlib import Path

import pytest


def load(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("erased_block_repair")


def test_lower_median_depends_only_on_ordered_occupied_block_indices(monkeypatch):
    core = load(monkeypatch)
    rows = [dict(block=i, held=held) for i, held in [(7, 5), (1, 10), (9, 0), (4, 1), (12, 20)]]
    assert core.central_block(rows)["block"] == 4
    with pytest.raises(ValueError, match="No occupied"):
        core.central_block([dict(block=1, held=0)])


def test_enrolment_binds_the_sealed_coverage_bytes_and_fixed_blocks(monkeypatch):
    load(monkeypatch)
    driver = import_module("erased_block_repair_trial")
    weak, transfer = (driver.enrol(case) for case in driver.CASES)
    assert weak["seconds"] == [10, 20] and len(weak["held_ids"]) == 9
    assert transfer["seconds"] == [50, 60] and len(transfer["held_ids"]) == 21


def test_held_erasure_precedes_history_and_guards_all_future_training_lanes(monkeypatch):
    core = load(monkeypatch)
    probe = dict(visit_index=10, receiver_id=0, channel=1, actual_rf_hz=11e9, valid_start_counter=100_000_000,
                 candidates=[{"never_read_for_fit": True}])
    source = dict(session_id="s", probes=[probe], sample_rate_hz=10_000_000, probe_ms=20)
    native = dict(source=source, clock_anchor={"sample_counter": 0})
    oid = core.identifier("s", probe)

    def select(masked):
        assert masked["source"]["probes"] == [dict(probe, candidates=[])]
        offsets = [2., 22.5, 31.]
        return masked, [dict(observation_id=str(time), time_s=time, receiver=i) for i, time in enumerate(offsets)]

    monkeypatch.setattr(core, "selection", select)
    forward, training, items, original = core.guarded_selection(native, dict(block=1, held_ids=[oid]))
    assert forward["source"]["probes"][0]["candidates"] == []
    assert [r["time_s"] for r in training] == [31.]
    assert original == 3 and items == [dict(observation_id=oid, time_s=10.01, receiver=1, actual_rf_hz=11e9, channel=1, visit=10)]
    assert native["source"]["probes"][0]["candidates"]


def test_integer_lift_is_inherited_from_earliest_nearby_kept_anchor(monkeypatch):
    core = load(monkeypatch)
    track = dict(times=[7., 8., 12.], observation_ids=["unkept", "a", "b"], values=[0., 110., -90.])
    known = {oid: dict(measured_cfo_hz=10., fractional_margin=.25) for oid in ("a", "b")}
    assert core.anchor_lift(track, {"a", "b"}, known, 10., 100.) == (1, "a", .25)
    assert core.anchor_lift(track, {"b"}, known, 10., 100.) == (-1, "b", .25)
    assert core.anchor_lift(track, {"a", "b"}, known, 40., 100.) is None


def test_paired_scores_share_identical_held_values_and_keep_visibility_losses(monkeypatch):
    core = load(monkeypatch)
    before = dict(signed_cfo_hz=-10., elevation_deg=10.)
    later = dict(signed_cfo_hz=-2., elevation_deg=-.1)
    rows = [dict(observation_id="one", forward={arm: before for arm in core.ARMS},
                 updated={arm: later for arm in core.ARMS})]
    scores = core.paired_rf_scores(rows, {"one": -4.})
    for arm in core.ARMS:
        assert scores[arm]["forward"]["signed_residual_hz"] == [6.]
        assert scores[arm]["updated"]["signed_residual_hz"] == [-2.]
        assert scores[arm]["updated_minus_forward_squared_hz2"] == -32.
        assert scores[arm]["updated_below_horizon"] == 1
