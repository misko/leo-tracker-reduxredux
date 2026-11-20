from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import hinted_whole
from tools.pipeline_eval.qualification import hinted_whole_raw as raw
from tools.pipeline_eval.qualification import hinted_whole_results as results
from tools.pipeline_eval.qualification import recording_to_v5 as recording


def test_two_receivers_request_hints_before_committing_either(monkeypatch):
    issued, commits = [], []

    def provide(lane, counter):
        issued.append((lane, counter))
        return [(910 + lane[0], 910.5 + lane[0])]

    def observe(lane, counter, winner):
        assert len(issued) == 2
        commits.append((lane, counter, winner))

    state = raw.Feedback()
    state.scout = SimpleNamespace(propose=provide, observe=observe)
    window = SimpleNamespace(
        acquisition={"sample_start": 500, "global_visit": 7, "actual_if_center_hz": 2e9},
        target={"channel": 2, "edge": "lower", "lnb_lo_hz": 9e9},
        sample_rate_hz=10_000_000,
    )
    state.begin(window, (0, 1))
    assert state.hints() == (910, 911)
    assert all(entry[0][1:] == (2, 11e9, "lower") for entry in issued)
    assert not commits
    monkeypatch.setattr(recording, "_from_native", lambda _i, candidate: candidate)
    candidate = dict(
        passed_fractional_margin_gate=True,
        candidate_rank=0,
        fractional_margin=0.3,
        integer_epoch_sample=77,
        fractional_epoch_offset_samples=0.125,
        fractional_tracking_cfo_hz=8.5,
    )
    output = {
        "rows": [dict(receiver_id=0, candidates=[candidate]), dict(receiver_id=1, candidates=[])]
    }
    state.commit(
        output,
        [
            {"ordinary": [1, 2, 3, 4], "selected": [1, 2, 3, 910]},
            {"ordinary": [1, 2, 3], "selected": [1, 2, 3]},
        ],
    )
    assert commits[0][2].epoch == 77.125
    assert commits[1][2] is None
    assert state.counts["applied"] == 1
    with pytest.raises(ValueError, match="past receiver"):
        state.begin(window, (0, 1))


def test_serial_archive_keeps_each_segment_and_terminal_for_verified_handoff(tmp_path):
    rows = (
        dict(kind="visit", segment=0, visit=0),
        dict(kind="segment", segment=0, count=1),
        dict(kind="visit", segment=1, visit=1),
        dict(kind="segment", segment=1, count=1),
        dict(kind="worker", worker=0),
    )
    (tmp_path / "chronological.jsonl").write_text(
        "".join(recording.encoded(r) + "\n" for r in rows)
    )
    hinted_whole.partition(tmp_path)
    for i in (0, 1):
        assert (tmp_path / f"replayed-{i}.jsonl").read_text().splitlines() == [
            *(recording.encoded(r) for r in rows[2 * i : 2 * i + 2]),
            recording.encoded(dict(kind="worker", worker=i)),
        ]


def test_retrospective_peak_match_uses_frozen_epoch_and_folded_cfo_tolerances():
    first = dict(
        integer_epoch_sample=1, fractional_epoch_offset_samples=0, fractional_tracking_cfo_hz=123
    )
    second = dict(
        integer_epoch_sample=13_332,
        fractional_epoch_offset_samples=0,
        fractional_tracking_cfo_hz=123 + results.ALIAS_HZ,
    )
    assert results.matches(first, second, 13_333)
    assert not results.matches(first, dict(second, fractional_epoch_offset_samples=-0.01), 13_333)
    assert not results.matches(first, dict(second, fractional_tracking_cfo_hz=2000), 13_333)


def test_sealed_full_iq_position_and_resource_tables_rebuild_offline(tmp_path):
    source = results.trial.REPORT
    results.score(source, tmp_path)
    assert all(
        row["exact_science"]
        for row in results.read(source / "independent-stock.json")["matches"].values()
    )
    for filename in ("resources.csv", "scores.csv"):
        assert (tmp_path / filename).read_bytes() == (source / filename).read_bytes()
