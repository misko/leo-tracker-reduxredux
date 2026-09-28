"""Read-only source continuity audit of four fixed failure tracks."""
import argparse
from collections import Counter
import json
from pathlib import Path
import pickle
import time
import run_disjoint as runner

HERE=Path(__file__).resolve().parent
base=runner.base


def transitions(rows):
    ordered=sorted(rows,key=lambda r:(r['utc_ns'],r['observation_id']))
    changes=[]
    for a,b in zip(ordered,ordered[1:]):
        delta=b['normalized_cfo_hz']-a['normalized_cfo_hz'];dt=(b['utc_ns']-a['utc_ns'])/1e9
        changes.append({'before':a['observation_id'],'after':b['observation_id'],'dt_s':dt,
            'delta_normalized_hz':delta,'delta_source_hz':b['source_cfo_hz']-a['source_cfo_hz'],
            'channel_changed':a['channel']!=b['channel'],'edge_changed':a['edge']!=b['edge'],
            'actual_rf_changed':a['actual_rf_hz']!=b['actual_rf_hz'],
            'partition_changed':a['partition']!=b['partition'],
            'normalization_change_hz':b['normalization_hz']-a['normalization_hz']})
    return {'observations':len(ordered),'span_s':(ordered[-1]['utc_ns']-ordered[0]['utc_ns'])/1e9,
            'receiver_counts':dict(Counter(r['receiver_id'] for r in ordered)),
            'channel_edge_counts':dict(Counter(f"{r['channel']}:{r['edge']}" for r in ordered)),
            'actual_rf_hz':sorted({r['actual_rf_hz'] for r in ordered}),
            'partition_counts':dict(Counter(r['partition'] for r in ordered)),
            'channel_transitions':sum(r['channel_changed'] for r in changes),
            'edge_transitions':sum(r['edge_changed'] for r in changes),
            'rf_transitions':sum(r['actual_rf_changed'] for r in changes),
            'largest_gaps':sorted(changes,key=lambda r:-r['dt_s'])[:5],
            'largest_frequency_steps':sorted(changes,key=lambda r:-abs(r['delta_normalized_hz']))[:5],
            'rows':ordered,'transitions':changes}


def run(sid):
    start=time.monotonic();target=HERE/f'source-audit-{sid}.json'
    if target.exists():raise FileExistsError(target)
    contract=json.loads((HERE/'contract.json').read_text())
    for path,expected in contract['files'].items():
        if base.digest(Path(path).read_bytes())!=expected:raise ValueError('contract changed')
    selected=json.loads((HERE/f'failure-components-{sid}.json').read_text())
    tids={r['track_id'] for r in selected['tracks']}
    saved=json.loads((HERE/f'disjoint-{sid}.json').read_text())
    saved_rows={r['track_id']:r for r in saved['records'] if r['direction']=='X_to_Y'}
    entry=next(r for r in json.loads((HERE/'inventory.json').read_text()) if r['session_id']==sid)
    raw=pickle.loads(Path(entry['cache_file']).read_bytes())
    prepared=base.prepare_adaptive_tle_position_inputs(sid,inputs=base.frequency_helpers.CachedInput(raw),archive=base.TleArchiveReader(Path('/var/lib/leo/tle')))
    links=base.resolve(raw);prepared,topology=base.filter_prepared(prepared,links)
    source={c.candidate_id:c for c in base.project_scanner_candidates(raw)}
    link={(r['track_id'],r['observation_id']):r['candidate_ids'] for r in links}
    results=[]
    for track in prepared.tracks:
        if track.track_id not in tids:continue
        train=set(saved_rows[track.track_id]['training_observation_ids']);held=set(saved_rows[track.track_id]['held_observation_ids'])
        if set(track.observation_ids)!=train|held:raise ValueError('observation membership changed')
        rows=[]
        for oid,frequency in zip(track.observation_ids,track.measured_hz):
            ids=link[track.track_id,oid]
            if len(ids)!=1:raise ValueError('ambiguous source')
            c=source[ids[0]]
            rows.append({'observation_id':oid,'source_candidate_id':c.candidate_id,
                'utc_ns':int(c.support_center_utc_ns),'source_group_id':c.source_group_id,
                'receiver_id':c.receiver_id,'visit_index':c.visit_index,'probe_index':c.probe_index,
                'channel':c.channel,'edge':c.edge.value,'actual_rf_hz':c.actual_rf_hz,
                'source_cfo_hz':c.measured_cfo_hz,'normalized_cfo_hz':float(frequency),
                'normalization_hz':float(frequency)-c.measured_cfo_hz,
                'source_uncertainty_hz':c.standard_uncertainty_hz,'margin':c.margin,
                'sample_start':c.source_sample_start,'sample_end':c.source_sample_end,
                'partition':'X' if oid in train else 'Y'})
        results.append({'track_id':track.track_id,**transitions(rows)})
    if len(results)!=2:raise ValueError('missing fixed tracks')
    out={'scope':'Posthoc source continuity diagnostic, no physical identity truth or model changes.',
         'session_id':sid,'tracks':results,'elapsed_s':time.monotonic()-start,
         'source_sha256':base.digest((HERE/f'disjoint-{sid}.json').read_bytes()),
         'cache_sha256':entry['cache_sha256'],'contract_sha256':base.digest((HERE/'contract.json').read_bytes()),
         'code_sha256':base.digest(Path(__file__).read_bytes())}
    with target.open('x') as stream:json.dump(base.json_value(out),stream,indent=2,allow_nan=False);stream.write('\n')
    print('SOURCE_AUDIT_DONE',sid,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--session-id',required=True,choices=['scan-fw-127d8fc36e804ae2','scan-fw-8f4f960d9db67798'])
    run(parser.parse_args().session_id)
