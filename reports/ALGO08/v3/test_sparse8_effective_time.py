from copy import deepcopy

import pytest

from leo.analysis.localization_v3 import tracks
from leo.contracts.digests import canonical_digest
from sparse8_effective_time import binding, source_rows
from sparse8_time_math import graph_rows


@pytest.fixture
def packet():
    from empty_bootstrap import CONTINUATION, EXTRA_SOURCES
    from eight_ms_native_receiver import SAVED_SELECTOR
    from full_short_run import SPARSE_EIGHT_MS_SHA
    from full_short_raw import recipe
    from held_anchor_route_publication import SELECTOR_SOURCES, SETTINGS

    parent = dict(recipe(), shortened_sha256=SPARSE_EIGHT_MS_SHA, aperture_samples=[200_000, 80_000])
    selected = dict(parent, held_native_8ms=dict(
        wrapper_sha256=SAVED_SELECTOR, held_selector=SETTINGS, selector_sources=SELECTOR_SOURCES,
        continuation=EXTRA_SOURCES[CONTINUATION],
        measurement="original signed 8 ms native CFO, no subsequent fixed-epoch 20 ms remeasurement"))
    pin = canonical_digest(selected)
    factor = dict(integer_epoch_sample=100, fractional_epoch_offset_samples=.25,
                  fractional_tracking_cfo_hz=100., candidate_rank=0,
                  passed_fractional_margin_gate=True, fractional_margin=.2)
    probes = [dict(visit_index=visit, receiver_id=rx, valid_start_counter=visit*1_000_000,
                   edge="lower", channel=1, actual_rf_hz=1e10,
                   candidates=[factor] if visit in (0, 7, 8) else [])
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
    assert sum(shift == 0 for _, shift, _ in corrections.values()) == 4
    assert [round(shift*1e6, 4) for _, shift, _ in corrections.values() if shift] == [-6666.6733]*2


@pytest.mark.parametrize("changed", ["unbound", "unsupported_route", "remeasured", "unknown_recipe"])
def test_ineligible_recipe_leaves_winning_observations_untouched(packet, changed):
    native, witness = packet
    if changed == "unbound":
        witness["native_sha256"] = "mismatch"
    elif changed == "unsupported_route":
        witness["choice"]["route"] = "some other selection"
    elif changed == "remeasured":
        witness["refinement_calls"] = 1
    else:
        witness["receiver_recipe"]["aperture_samples"] = [200_000, 120_000]
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
        assert tracks.winning_observations(native) == (adjusted, metadata)
    assert audit["applied"] and support is metadata
    assert adjusted == graph_rows(rows, factors)
    assert native == original


def test_first_unsupported_graph_packet_sticks_to_nominal_for_the_whole_solver(packet, monkeypatch):
    native, witness = packet
    _, factors = source_rows(native, witness)
    rows = [dict(observation_id=oid, time_s=time, measured_cfo_hz=hz, receiver=1, channel=1)
            for oid, (time, _, hz) in factors.items()]
    metadata = dict(anchor_utc_ns=1234, receiver_factors=len(rows))
    monkeypatch.setattr(tracks, "winning_observations", lambda _: (rows, metadata))
    audit = {}
    with binding(native, witness, audit):
        assert tracks.winning_observations({}) == (rows, metadata)
        assert tracks.winning_observations(native) == (rows, metadata)
    assert not audit["applied"]


def test_different_packet_after_correction_fails_instead_of_mixing_graph_times(packet, monkeypatch):
    native, witness = packet
    _, factors = source_rows(native, witness)
    rows = [dict(observation_id=oid, time_s=time, measured_cfo_hz=hz, receiver=1, channel=1)
            for oid, (time, _, hz) in factors.items()]
    monkeypatch.setattr(tracks, "winning_observations", lambda _: (rows, {}))
    with binding(native, witness, {}):
        assert tracks.winning_observations(native)[0] != rows
        with pytest.raises(ValueError, match="different signed packet"):
            tracks.winning_observations({})
