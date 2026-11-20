import pytest

from tools.pipeline_eval.qualification.causal_track_scout_trial import prospective
from tools.pipeline_eval.variants.causal_track_scout import MAX_TRACKLETS, TrackScout
from tools.pipeline_eval.variants.coherent_peak_filter import FOLD_HZ, Peak

RATE = 10_000_000
LANE = (0, 1, 12e9, "upper")
ORIGIN = 23_000_000_000_000


def test_linear_counter_phase_carries_two_prior_peaks_and_folded_cfo():
    scout = TrackScout(RATE)
    for visit, epoch in enumerate((100.0, 102.0)):
        t = ORIGIN + visit * RATE
        assert scout.propose(LANE, t) == []
        scout.observe(LANE, t, Peak(visit, t, epoch, 600 + visit * FOLD_HZ))
    target = ORIGIN + 2 * RATE
    before = scout.propose(LANE, target)
    assert before == [(104, pytest.approx(104.0))]
    with pytest.raises(ValueError, match="already|advancing"):
        scout.propose(LANE, target + 1)
    with pytest.raises(ValueError, match="out-of-order"):
        scout.observe(LANE, target + 1, None)
    scout.observe(LANE, target, None)
    assert before == [(104, pytest.approx(104.0))]


def test_separate_past_tracklets_and_fixed_center_limit():
    scout = TrackScout(RATE)
    for visit in range(10):
        t = ORIGIN + visit * RATE // 10
        family = visit % 5
        scout.propose(LANE, t)
        scout.observe(LANE, t, Peak(visit, t, 100 + family * 2000, family * 20_000))
    t = ORIGIN + 12 * RATE // 10
    assert len(scout.tracks[LANE]) == 5
    assert [c for c, _ in scout.propose(LANE, t)] == [8100, 6100, 4100, 2100]
    scout.observe(LANE, t, None)
    later = ORIGIN + 5 * RATE
    assert not scout.propose(LANE, later)
    scout.observe(LANE, later, None)


def test_unlinked_tracks_cannot_exceed_lane_bound():
    scout = TrackScout(RATE)
    for visit in range(11):
        t = ORIGIN + visit * RATE // 10
        scout.propose(LANE, t)
        scout.observe(LANE, t, Peak(visit, t, visit * 1000, 10_000 * visit))
    assert len(scout.tracks[LANE]) == MAX_TRACKLETS
    assert scout.tracks[LANE][0].latest.visit == 3


def test_stereo_proposals_precede_either_current_candidate_read():
    published = []

    class Window(dict):
        def __getitem__(self, key):
            if key == "candidates":
                assert len(published) == 2 * (self["visit_index"] + 1)
                assert [r["receiver_id"] for r in published[-2:]] == [0, 1]
            return super().__getitem__(key)

    rows = [
        Window(
            visit_index=visit,
            receiver_id=rx,
            channel=1,
            actual_rf_hz=12e9,
            edge="upper",
            valid_start_counter=ORIGIN + visit * RATE,
            candidates=[
                dict(
                    candidate_rank=0,
                    passed_fractional_margin_gate=True,
                    fractional_margin=0.5,
                    integer_epoch_sample=100 + visit,
                    fractional_epoch_offset_samples=0.0,
                    fractional_tracking_cfo_hz=300.0,
                )
            ],
        )
        for visit in range(3)
        for rx in (0, 1)
    ]
    document = dict(
        source=dict(probes=rows, sample_rate_hz=RATE),
        provenance=dict(excluded_windows=[]),
    )
    scores = prospective("fixture", document, published.append)
    assert scores["center_counts"] == {0: 4, 1: 2}
    assert [row["centers"] for row in published[-2:]] == [[102], [102]]
