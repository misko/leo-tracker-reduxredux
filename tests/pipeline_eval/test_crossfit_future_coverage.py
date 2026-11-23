from importlib import import_module
from pathlib import Path


def coverage(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("crossfit_future_coverage")


def test_chronological_blocks_purge_both_neighbours_across_radios(monkeypatch):
    tool = coverage(monkeypatch)
    rows = [dict(time_s=t, receiver=i % 2) for i, t in enumerate((0., 9.999, 10., 19.999, 20., 30., 39.999, 40.))]
    groups = tool.by_block(rows)
    assert list(groups) == [0, 1, 2, 3, 4]
    assert [r["time_s"] for r in tool.training_rows(groups, 2)] == [0., 9.999, 40.]


def test_forward_selection_can_use_rejected_future_only_rows(monkeypatch):
    tool = coverage(monkeypatch)
    from full_short_raw import RECIPE_SHA

    probes = [dict(receiver_id=0, channel=1, actual_rf_hz=11e9, valid_start_counter=i*2_000_000,
                   candidates=[dict(fractional_tracking_cfo_hz=10_000+100*i, candidate_rank=0,
                                    fractional_margin=.5, integer_epoch_sample=0,
                                    fractional_epoch_offset_samples=.2, passed_fractional_margin_gate=True)])
              for i in range(7)]
    packet = dict(source=dict(probes=probes, raw_recording_authority_digest="sha256:"+"5"*64,
                              session_id="session", sample_rate_hz=10_000_000, probe_ms=20),
                  provenance=dict(detector_sha256="sha256:" + RECIPE_SHA),
                  clock_anchor=dict(before=dict(realtime_ns=100, monotonic_ns=0),
                                    after=dict(realtime_ns=110, monotonic_ns=10), sample_counter=0),
                  delivery_clocks=[], last_sample_counter=13_000_000)
    forward, future = tool.selection(packet)
    owner_ids = {tool.identifier("session", row) for row in forward["source"]["probes"] if row["candidates"]}
    assert len(future) == 3 and len(owner_ids) == 4
    fold, = tool.count_blocks(packet, forward, future, {}, dict.fromkeys(owner_ids).keys())
    assert fold["forward_changed"] == fold["forward_owners_affected"] == 3
    assert not fold["eligible"]
    assert all(row["candidates"] for row in packet["source"]["probes"])


def test_ceiling_grants_only_unambiguous_satellite_and_role(monkeypatch):
    tool = coverage(monkeypatch)
    base = dict(receiver=1, channel=1, actual_rf_hz=11e9)
    native = {"a": dict(base, time_s=1.), "b": dict(base, time_s=2.), "c": dict(base, time_s=40.)}
    chosen = [("a", 10, "conditional"), ("b", 10, "predictive"), ("c", 11, "conditional")]
    future = [dict(base, observation_id="ambiguous", time_s=0.), dict(base, observation_id="unique", time_s=32.),
              dict(base, observation_id="other_rf", time_s=32., actual_rf_hz=12e9)]
    assert tool.eligible_metadata(future, chosen, native) == {"unique": (11, 1, "conditional")}
