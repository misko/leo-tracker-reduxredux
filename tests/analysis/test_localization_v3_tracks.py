from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.localization_v3.tracks import (
    active_curvature,
    graph_tracks,
    prepare_tracks,
    winning_observations,
)
from leo.analysis.polynomial_tracklets import TrackConfig


def native_document():
    def peak(cfo, rank=1, margin=.3, passed=True):
        return dict(fractional_tracking_cfo_hz=cfo, candidate_rank=rank,
                    fractional_margin=margin, passed_fractional_margin_gate=passed,
                    integer_epoch_sample=10, fractional_epoch_offset_samples=.1)

    probes = [dict(receiver_id=rx, channel=ch, valid_start_counter=i * 1_000_000,
                   actual_rf_hz=11e9 + ch * 1e6,
                   candidates=[peak(100_000 - 700*i + 4*i*i)])
              for rx, ch in [(0, 1), (1, 8)] for i in range(41)]
    return dict(source=dict(session_id='synthetic', sample_rate_hz=1_000_000,
                            probe_ms=20, probes=probes),
                clock_anchor=dict(sample_counter=0,
                                  before=dict(realtime_ns=1_000_000_000, monotonic_ns=0),
                                  after=dict(realtime_ns=1_100_000_000, monotonic_ns=100_000_000)),
                delivery_clocks=[], last_sample_counter=41_000_000, provenance={})


def test_peak_tie_break_and_gate_use_original_observation_identity():
    document = native_document()
    first = document['source']['probes'][0]
    base = first['candidates'][0]
    first['candidates'] = [dict(base, candidate_rank=3, fractional_tracking_cfo_hz=111),
                           dict(base, candidate_rank=2, fractional_tracking_cfo_hz=222),
                           dict(base, fractional_margin=.9, passed_fractional_margin_gate=False)]
    rows, _ = winning_observations(document)
    assert rows[0]['measured_cfo_hz'] == 222
    identity = rows[0]['observation_id']
    first['candidates'].reverse()
    again, _ = winning_observations(document)
    assert again[0] == rows[0]
    first['candidates'] = [base]
    assert winning_observations(document)[0][0]['observation_id'] == identity


def test_preparation_is_pure_and_retains_both_bands():
    document = native_document()
    before = deepcopy(document)
    result = prepare_tracks(document, TrackConfig(max_slope_hz_s=8000))
    assert document == before
    assert result['status'] == 'tracks_prepared'
    assert result['graph_points'] == 82
    assert {t['bank'] for t in result['tracks']} == {'CH1-4', 'CH5-8'}
    assert result['metadata']['causal_cutoff_utc_ns'] == 1_000_000_000
    ids = [oid for t in result['tracks'] for oid in t['observation_ids']]
    assert len(ids) == len(set(ids))
    assert all(t['source_id'] == 'SCAN' for t in result['tracks'])


def test_actual_rf_lanes_cannot_merge_even_on_the_same_curve():
    rows, _ = winning_observations(native_document())
    rows = [r for r in rows if r['receiver'] == 1]
    rows += [dict(r, observation_id=r['observation_id']+'other', actual_rf_hz=12e9)
             for r in rows]
    tracks, count = graph_tracks(rows, TrackConfig(max_slope_hz_s=8000))
    assert count == 82
    assert len(tracks) == 2
    assert len({t['key'] for t in tracks}) == 2
    assert {t['rf_hz'] for t in tracks} == {11.001e9, 12e9}


def test_linear_track_does_not_supply_curvature():
    t = np.linspace(0, 40, 81)
    assert not active_curvature(dict(times=t, values=1000 - 10*t))
    assert active_curvature(dict(times=t, values=1000 - 10*t + 4*t*t))


def test_empty_gated_population_is_not_a_position_success():
    doc = native_document()
    for p in doc['source']['probes']:
        p['candidates'][0]['passed_fractional_margin_gate'] = False
    result = prepare_tracks(doc, TrackConfig())
    assert result['status'] == 'no_active_curvature'
    assert result['tracks'] == []
    assert result['graph_points'] == 0


@pytest.mark.parametrize('broken', ['clock', 'overlap', 'nonfinite'])
def test_native_input_validation_remains_in_force(broken):
    doc = native_document()
    if broken == 'clock':
        doc['clock_anchor'] = None
    elif broken == 'overlap':
        doc['source']['probes'].append(deepcopy(doc['source']['probes'][0]))
    else:
        doc['source']['probes'][0]['candidates'][0]['fractional_margin'] = float('nan')
    with pytest.raises(ValueError):
        prepare_tracks(doc, TrackConfig())
