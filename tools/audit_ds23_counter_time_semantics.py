"""Trace GLRT times to immutable hardware-counter metadata, without IQ reads."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

from export_ds23_support_audit import index_rows,MANIFEST
from run_algo01_ds23_sample import ROOT,read,write,sha
from probe_algo03_frame_peak_recovery import SOURCE

OUT=ROOT/'reports/2026_10_20_ds23_counter_time_audit'


def audit_rows(rows,document,observations):
    source=document['source'];fs=source['sample_rate_hz'];anchor=document['clock_anchor']
    if fs!=2500000 or source['probe_ms']!=20:raise ValueError('unexpected fast-window sample geometry')
    rows=sorted(rows,key=lambda r:r['acquisition']['global_visit'])
    by_visit={r['acquisition']['global_visit']:r for r in rows}
    if sorted(by_visit)!=list(range(len(rows))):raise ValueError('missing or duplicate original visits')
    generations=set();sessions=set();anchors=[];deliveries=[];gaps=[];previous_end=None
    for row in rows:
        a=row['acquisition'];receipt=json.loads(a['retune_receipt'])
        if a['counter_authority']!='hardware' or receipt['source_rate_hz']!=fs:
            raise ValueError('unqualified hardware counter or sample-rate declaration')
        if (receipt['valid_start'],receipt['valid_end'])!=(a['sample_start'],a['sample_end']):
            raise ValueError('provider and persisted sample support differ')
        if receipt['visit']!=a['global_visit'] or receipt['session']!=a['device_session'] or receipt['generation']!=a['generation']:
            raise ValueError('provider identity or visit does not match capture')
        if previous_end is not None:
            if a['sample_start']<previous_end:raise ValueError('hardware counter regressed or overlapped')
            gaps.append(a['sample_start']-previous_end)
        previous_end=a['sample_end'];generations.add(a['generation']);sessions.add(a['device_session'])
        if 'utc_clock_bracket' in receipt:anchors.append(receipt['utc_clock_bracket'])
        deliveries.append(receipt['host_delivery_clock'])
    if len(generations)!=1 or len(sessions)!=1 or anchors!=[anchor]:
        raise ValueError('stream restart or UTC anchor mismatch')
    if deliveries!=document['delivery_clocks']:
        raise ValueError('public delivery clocks do not preserve original visits')
    clocks=[anchor['before'],anchor['after'],*deliveries]
    offset=[c['realtime_ns']-c['monotonic_ns'] for c in clocks]
    expected={}
    for probe in source['probes']:
        a=by_visit[probe['visit_index']]['acquisition']
        if probe['valid_start_counter']!=a['sample_start']:
            raise ValueError('tracking replaced hardware counter with payload indexing')
        text=f"{source['session_id']}:{probe['receiver_id']}:{a['sample_start']}"
        oid='sha256:'+hashlib.sha256(text.encode()).hexdigest()
        expected[oid]=(a['sample_start']-anchor['sample_counter'])/fs+.010
    discrepancies=[]
    for observation in observations:
        if observation['observation_id'] not in expected:
            raise ValueError('GLRT observation lacks original counter support')
        discrepancies.append(abs(expected[observation['observation_id']]-observation['time_s']))
    maximum=max(discrepancies,default=0.)
    if maximum>1e-9:raise ValueError('GLRT time differs from hardware-counter window midpoint')
    return dict(original_windows=len(rows),winning_GLRT_observations_checked=len(observations),
        maximum_timestamp_difference_s=maximum,hardware_generations=len(generations),device_sessions=len(sessions),
        original_UTC_anchors=len(anchors),host_clock_offset_spread_ns=max(offset)-min(offset),
        smallest_interwindow_counter_gap_samples=min(gaps,default=0),
        largest_interwindow_counter_gap_samples=max(gaps,default=0),
        nonuniform_retune_gaps_preserved=True,
        nominal_elapsed_time_from_hardware_counter_not_delivery=True,
        sample_rate_error_independently_measured=False)


def main():
    OUT.mkdir(exist_ok=True)
    frozen=read(SOURCE/'protocol.json')
    if sha(MANIFEST)!=frozen['dataset_manifest_sha256']:raise ValueError('sealed dataset changed')
    cohort=read(ROOT/'reports/2026_10_20_ds23_excluded_catalogue/calibration_protocol.json')
    cases=cohort['development_cases']+cohort['confirmation_cases']
    metadata=read(MANIFEST)['members'];members={m['dataset_label']:m for m in metadata}
    receipts=[]
    for case in cases:
        tracking=read(SOURCE/case/'tracking.json')
        if 'source' not in tracking:continue
        with ThreadPoolExecutor(max_workers=8) as pool:
            parts=list(pool.map(index_rows,members[case]['raw_recording']['chunks']))
        rows=[r for part,_ in parts for r in part]
        result=audit_rows(rows,tracking,read(SOURCE/case/'observations.json'))
        result.update(case=case,index_bindings=[b for _,b in parts],tracking_sha256=sha(SOURCE/case/'tracking.json'))
        write(OUT/(case+'.json'),result);receipts.append(result)
    write(OUT/'evaluation.json',dict(cases=[r['case'] for r in receipts],fast_scans=len(receipts),
        total_original_windows=sum(r['original_windows'] for r in receipts),
        total_winning_observations=sum(r['winning_GLRT_observations_checked'] for r in receipts),
        maximum_timestamp_difference_s=max(r['maximum_timestamp_difference_s'] for r in receipts),
        all_metadata_checks_passed=True,no_new_timing_coordinate_justified_by_this_audit=True,
        conditional_on_original_counter_and_nominal_sample_rate_declarations=True,
        GPS_IQ_future_TLE_or_position_fit_used=False,
        dataset_sha256=sha(MANIFEST),source_sha256=sha(Path(__file__)),
        metadata_reader_sha256=sha(ROOT/'tools/export_ds23_support_audit.py'),
        source_semantics_sha256={str(p.relative_to(ROOT)):sha(p) for p in (
            ROOT/'src/leo/acquisition/continuous_window_ppu.py',ROOT/'src/leo/analysis/glrt_frequency_input.py')}))
    print('Counter audit complete',len(receipts),'fast scans',sum(r['original_windows'] for r in receipts),'windows',flush=True)


if __name__=='__main__':
    main()
