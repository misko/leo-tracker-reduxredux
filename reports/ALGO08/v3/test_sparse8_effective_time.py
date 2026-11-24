from copy import deepcopy

import pytest

from leo.analysis.localization_v3 import tracks
from leo.contracts.digests import canonical_digest
from sparse8_cfo_epoch_saved import correction_rows, graph_rows
from sparse8_effective_time import binding, source_rows


@pytest.fixture
def packet():
    from empty_bootstrap import CONTINUATION, EXTRA_SOURCES
    from eight_ms_native_receiver import SAVED_SELECTOR
    from full_short_run import SPARSE_EIGHT_MS_SHA
    from full_short_raw import recipe
    from held_anchor_route_publication import SELECTOR_SOURCES, SETTINGS
    from test_sparse8_cfo_epoch import factor

    parent = dict(recipe(), shortened_sha256=SPARSE_EIGHT_MS_SHA, aperture_samples=[200_000, 80_000])
    selected = dict(parent, held_native_8ms=dict(
        wrapper_sha256=SAVED_SELECTOR, held_selector=SETTINGS, selector_sources=SELECTOR_SOURCES,
        continuation=EXTRA_SOURCES[CONTINUATION],
        measurement="original signed 8 ms native CFO, no subsequent fixed-epoch 20 ms remeasurement"))
    pin = canonical_digest(selected)
    probes = [dict(visit_index=visit, receiver_id=rx, valid_start_counter=visit*1_000_000,
                   edge="lower", channel=1, actual_rf_hz=1e10,
                   candidates=[factor()] if visit in (0, 7, 8) else [])
              for visit in range(9) for rx in range(2)]
    native = dict(source=dict(probes=probes, session_id="signed", qualified=True, sample_rate_hz=10_000_000,
                              probe_ms=20),
                  clock_anchor=dict(sample_counter=0), delivery_clocks=[], last_sample_counter=9_000_000,
                  provenance=dict(excluded_windows=[], detector_sha256=pin, window_count=9,
                                  invalid_capture=0, processed_windows=9))
    receipt = dict(receiver_recipe=selected, native_sha256=canonical_digest(native),
                   detector_recipe_sha256=pin, parent_detector_sha256=canonical_digest(parent),
                   refinement_calls=0, choice=dict(route="history"), selected=6)
    return native, receipt


@pytest.mark.parametrize("route", ["history", "unfiltered"])
def test_original_port_matches_frozen_arithmetic_with_empty_history_lanes(packet, route):
    native, witness = packet
    witness["choice"]["route"] = route
    admitted, corrections = source_rows(native, witness)
    assert admitted == route
    assert corrections == correction_rows(native)
    assert sum(shift == 0 for _, shift, _ in corrections.values()) == 4


@pytest.mark.parametrize("changed", ["unbound", "unsupported_route", "remeasured"])
def test_ineligible_recipe_leaves_winning_observations_untouched(packet, changed):
    native, witness = packet
    if changed == "unbound":
        witness["native_sha256"] = "mismatch"
    elif changed == "unsupported_route":
        witness["choice"]["route"] = "some other selection"
    else:
        witness["refinement_calls"] = 1
    original = tracks.winning_observations
    audit = {}
    with binding(native, witness, audit):
        assert tracks.winning_observations is original
    assert audit["requested"] and not audit["applied"]


def test_source_bound_port_preserves_raw_document_and_corrects_only_graph(packet, monkeypatch):
    native, witness = packet
    original = deepcopy(native)
    _, factors = source_rows(native, witness)
    rows = [dict(observation_id=oid, time_s=time, measured_cfo_hz=hz, receiver=1, channel=1)
            for oid, (time, _, hz) in factors.items()]
    metadata = object()
    monkeypatch.setattr(tracks, "winning_observations", lambda _: (rows, metadata))
    audit = {}
    with binding(native, witness, audit):
        adjusted, support = tracks.winning_observations(native)
    assert audit["applied"] and support is metadata
    assert adjusted == graph_rows(rows, factors)
    assert native == original
