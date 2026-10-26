"""Development-only baseline inventory and previous receipt reuse; no refits."""

import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
PREVIOUS=Path('/srv/bulk/leo/research/ds24-ch58-continuity-r01/validation')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(name,value):
    with (HERE/name).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def observation_id(session,rx,counter):
    return 'sha256:'+hashlib.sha256(f'{session}:{rx}:{counter}'.encode()).hexdigest()


def native_row(document,probe,receivers=None):
    source=document['source'];fs=source['sample_rate_hz']
    rx=receivers if receivers is not None else sorted({p['receiver_id'] for p in source['probes']})
    start=probe['valid_start_counter'];count=round(source['probe_ms']*.001*fs)
    return dict(observation_id=observation_id(source['session_id'],probe['receiver_id'],start),
        recording_id=source['session_id'],stream_generation=source['stream_generation'],
        raw_authority_digest=source['raw_recording_authority_digest'],
        source_input_sha256=source['input_manifest_sha256'],
        native_receiver_id=probe['receiver_id'],receiver=rx.index(probe['receiver_id'])+1,
        channel=probe['channel'],edge=probe['edge'],actual_rf_hz=probe['actual_rf_hz'],
        sample_rate_hz=fs,start_counter=start,stop_counter=start+count,
        time_s=(start-document['clock_anchor']['sample_counter'])/fs+source['probe_ms']*.0005,
        visit_index=probe['visit_index'],probe_index=probe['probe_index'])


def metadata_inventory(case):
    document=read(SOURCE/case/'tracking.json')
    receivers=sorted({p['receiver_id'] for p in document['source']['probes']})
    rows=[native_row(document,p,receivers) for p in document['source']['probes']]
    owners={r['observation_id']:r for r in rows}
    if len(owners)!=len(rows):
        raise ValueError('duplicate native owners')
    original=read(SOURCE/case/'observations.json')
    for row in original:
        native=owners[row['observation_id']]
        if any(row[k]!=native[k] for k in ('receiver','native_receiver_id','channel','actual_rf_hz','time_s')):
            raise ValueError('native observation metadata drift')
    return document,rows,original


def main():
    split=read(ROOT/'split.json')
    previous=read(PREVIOUS/'source_receipt.json')
    for path,digest in previous['files_sha256'].items():
        if sha(path)!=digest:
            raise ValueError('prior source/input no longer reusable: '+path)
    files={str(ROOT/'split.json'):sha(ROOT/'split.json'),str(HERE/'PROTOCOL.md'):sha(HERE/'PROTOCOL.md'),
        str(HERE/'TIMING_INTERFACE.md'):sha(HERE/'TIMING_INTERFACE.md'),
        str(HERE/'SUPPORT_CLARIFICATION.md'):sha(HERE/'SUPPORT_CLARIFICATION.md'),
        str(Path(__file__)):sha(__file__)}
    sources=[SOURCE/'protocol.json',SOURCE/'engine/ds24_engine.py',
        Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery/recovery.py'),
        REPO/'tools/algo02_scan.py',REPO/'tools/evaluate_ds22_merged_tracks.py',
        REPO/'tools/evaluate_ds22_public_tracks.py',REPO/'tools/localize_merged_track_catalogue.py',
        REPO/'src/leo/analysis/graph_tracklets.py',REPO/'src/leo/analysis/polynomial_tracklets.py',
        REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json']
    files.update({str(p):sha(p) for p in sources})
    rows=[]
    for case in split['development']:
        _,inventory,original=metadata_inventory(case)
        tracks=read(SOURCE/case/'tracks.json')
        receipt=read(SOURCE/'causal_prior'/case/'receipt.json')
        if receipt['reference_position_used'] is not False:
            raise ValueError('noncausal/geographic reference')
        if receipt['search_center']!=[37.906,-122.545] or receipt['search_box_width_km']!=25.:
            raise ValueError('regional authority differs')
        point_ids=[oid for t in tracks for oid in t['observation_ids']]
        if len(point_ids)!=len(set(point_ids)):
            raise ValueError('baseline graph duplicates owners')
        for name in ('tracking.json','observations.json','tracks.json','prepared.json','radio_noise.json',
                     'nominal_elements.json','receipt.json','bank.npz','algo02_result.json','result.json'):
            path=SOURCE/case/name;files[str(path)]=sha(path)
        for path in [SOURCE/'family_cavity/position'/f'{case}.json',
                     SOURCE/'causal_prior'/case/'receipt.json',
                     SOURCE/'causal_prior'/case/'previous_receipt.json',
                     SOURCE/'causal_prior'/case/'previous.tle',
                     SOURCE/'causal_phase_history'/f'{case}.json',
                     SOURCE/'causal_phase_history'/f'{case}_forecast.json']:
            files[str(path)]=sha(path)
        reused=PREVIOUS/(case+'_receipt.json')
        rows.append(dict(case=case,native_cells=len(inventory),existing_winners=len(original),
            original_tracks=len(tracks),original_graph_points=len(point_ids),
            c_arms=['c0','fitted_c'],regional_center=[37.906,-122.545],box_width_km=25.,
            previous_endpoint_replay_reused=reused.exists(),
            previous_replay_receipt_sha256=sha(reused) if reused.exists() else None,
            lane_winner_counts={f'CH{ch}-RX{rx}':sum(o['channel']==ch and o['receiver']==rx for o in original)
                for ch in range(1,9) for rx in (1,2)}))
    write('baseline_source_receipt.json',dict(files_sha256=files,
        previous_source_inputs_verified=len(previous['files_sha256']),
        previous_replay_receipts_reused=[r['case'] for r in rows if r['previous_endpoint_replay_reused']],
        validation_target_outcomes_opened=False,geographic_errors_opened=False,
        baseline_algorithm='ALGO02-v1 + qualified causal signed phase prior + equal-prior family cavity'))
    config=read(sources[-1])['config']
    write('baseline_readiness.json',dict(development=rows,development_cases=len(rows),
        held_validation_cases=len(split['validation']),unavailable_cases=sum(not r['available'] for r in split['rows']),
        new_endpoint_replays=0,new_position_fits=0,
        original_graph_config=config,
        raw_curvature_gate=dict(minimum_span_s=20.,minimum_detrended_RMS_hz=250.),
        four_fraction_panel_limit='At most four distinct targets per channel/RX; cannot form an eight-point new graph track alone. It can correct or augment existing dense tracks.',
        integration_next='Rebuild the original actual-RF graph on staged observations, then requalify against the full causal catalogue; no forced incumbent identity.'))
    print(json.dumps(dict(status='ready',development_cases=len(rows),reused_replays=4,
        source_hashes=len(files),new_fits=0,validation_outcomes_opened=False)))


if __name__=='__main__':
    main()
