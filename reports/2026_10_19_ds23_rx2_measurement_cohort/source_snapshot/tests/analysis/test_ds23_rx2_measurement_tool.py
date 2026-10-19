"""Selection is independent of GPS, fit residuals, and public row sort order."""

from copy import deepcopy
import numpy as np
import pytest
from leo.analysis.research.public_tracking_points import public_tracking_points
from remeasure_ds23_rx2_cohort import selected_points, qualification_points


def example():
    timing=dict(session_id='capture',qualified=True,sample_rate_hz=1000,session_start_device_sample_counter=0,
        begin_before_realtime_ns=10000000000,begin_before_monotonic_ns=0,
        begin_after_realtime_ns=10100000000,begin_after_monotonic_ns=100000000,
        terminal_realtime_ns=12000000000,terminal_monotonic_ns=2000000000,
        first_sample_earliest_utc_ns=10000000000,first_sample_latest_utc_ns=10100000000,
        first_sample_estimate_utc_ns=10050000000)
    probes=[]
    for visit,channel in [(0,2),(1,1)]:
        probes.append(dict(receiver_id=1,visit_index=visit,probe_index=0,channel=channel,edge='lower',
            actual_rf_hz=11e9,valid_start_counter=1000+visit*1000,payload_start_sample=visit*20,probe_start_ms=120,
            candidates=[dict(candidate_rank=0,fractional_margin=.1,fractional_tracking_cfo_hz=123+visit,
                             passed_fractional_margin_gate=True)]))
    return dict(session_id='capture',qualified=True,sample_rate_hz=1000,probe_ms=20,
                input_manifest_sha256='sha256:example',timing=timing,probes=probes)


def test_sorted_adapter_rows_are_joined_by_physical_id_and_keep_visit_offset():
    doc=example();rows,_=public_tracking_points(doc)
    assert rows[0]['visit_index']==1
    period=1/4.4e-6
    tracks=[dict(key=str(k),channel=r['channel'],rf_hz=r['actual_rf_hz'],
                 observation_ids=[r['observation_id']],values=[r['measured_cfo_hz']+2*period]) for k,r in enumerate(rows)]
    _,points=selected_points(doc,tracks)
    assert [p['visit_index'] for p in points]==[1,0]
    assert points[0]['visit_start_counter']==2000 and points[0]['probe_start_ms']==120
    assert points[0]['peak']['fractional_tracking_cfo_hz']==124
    tracks[0]['values'][0]+=1
    with pytest.raises(ValueError,match='canonical'):selected_points(doc,tracks)


def test_duplicate_physical_votes_fail_instead_of_inflating_coverage():
    doc=example();rows,_=public_tracking_points(doc);r=rows[0]
    track=dict(key='a',channel=r['channel'],rf_hz=r['actual_rf_hz'],observation_ids=[r['observation_id']],values=[r['measured_cfo_hz']])
    with pytest.raises(ValueError,match='exclusive'):selected_points(doc,[track,deepcopy(track)])


def test_qualification_is_fixed_even_spacing_within_each_channel():
    points=[dict(channel=ch,visit_index=k,probe_index=0,observation_id=f'{ch}:{k}') for ch in (1,5) for k in range(11)]
    result=qualification_points(points[::-1])
    assert [(p['channel'],p['visit_index']) for p in result]==[(1,0),(1,5),(1,10),(5,0),(5,5),(5,10)]
