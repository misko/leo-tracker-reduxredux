import io
import json

import numpy as np
import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import clock_transfer as trial
from tools.pipeline_eval.qualification import clock_transfer_figures as figures
from tools.pipeline_eval.qualification import clock_transfer_inputs as inputs
from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.reference.native_archive import NativeArchive
from tools.pipeline_eval.scoring import ARMS, distance_km


def test_native_factor_generator_matches_incremental_archive_and_probe_clock():
    first, anchor = 1_980_021, 1_794_932_375_000_000_000
    counter_elapsed = int(inputs.cold.RATE * (inputs.cold.SECONDS - 0.030))
    samples = [
        inputs.cold._probe_row(0, 0, 1, first, []),
        inputs.cold._probe_row(1, 1, 2, first + counter_elapsed, []),
    ]
    packet = inputs._native("opaque", anchor, first, samples)
    archive = NativeArchive(io.StringIO(encoded(packet).decode()))
    read = list(archive)
    assert [json.loads(raw) for _, raw in read] == samples
    assert [t for t, _ in read] == pytest.approx([0.010, 299.980], abs=1e-9)
    assert archive.meta == dict(causal_cutoff_utc_ns=anchor, anchor_utc_ns=anchor, duration_s=300.0)
    inputs.cold._check_probe_times(samples, first, inputs.cold.RATE, 20, 300)


@pytest.mark.parametrize("site", [(33.5, 139.7), (-29.0, -70.5)])
def test_offer_pairs_span_matching_physical_tile_margins(site):
    offers = dict(inputs._offers(site, np.random.default_rng(9471)))
    assert all(tile["width_km"] == 25 for tile in offers.values())
    assert len({tile["id"] for tile in offers.values()}) == 4
    inside = inputs.roi_margin(site, offers["near-inside"])
    outside = inputs.roi_margin(site, offers["near-outside"])
    assert outside == pytest.approx(-inside, abs=1e-7)
    assert 1 <= inside <= 2
    assert 8 <= distance_km(offers["original"]["center"], site) <= 10
    assert -65 <= inputs.roi_margin(site, offers["far-outside"]) <= -35


def test_sealed_transfer_cards_keep_all_offers_and_both_arms():
    cards = screening_figures.charts(evidence=trial.REPORT)
    assert {card.method for card in cards} == set(trial.METHODS)
    for card in cards:
        assert len(card.cases) == 25
        assert len(card.references) == 25
        assert sum(ref["truth"] is None for ref in card.references.values()) == 1
        for arm in ARMS:
            marks = [mark for mark in card.page(arm).rows if mark.series == "candidate"]
            assert len(marks) == 25
            assert {mark.dataset for mark in marks} == set(figures.LABELS.values())
