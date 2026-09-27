"""Freeze four RX-unused DS6 recordings using metadata only."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
DATASET=Path('/home/mouse9911/gits/leo-ds6/reports/2026_09_27_ds6_roof')
SEED=20260928


def sha(raw):return 'sha256:'+hashlib.sha256(raw).hexdigest()


def select(captures,excluded,count=4,seed=SEED):
    if len({c['session_id'] for c in captures})!=len(captures):raise ValueError('duplicate capture')
    candidates=[];accounting=[]
    for c in sorted(captures,key=lambda r:r['session_id']):
        reasons=[]
        if c['session_id'] in excluded:reasons.append('previous_RX_membership')
        if c.get('tracking_status_observed_at_inventory')!='complete':reasons.append('tracking_not_complete')
        if not c.get('source_span_attested'):reasons.append('unattested_source_span')
        priority=hashlib.sha256(f'{seed}:{c["session_id"]}'.encode()).hexdigest()
        accounting.append({'session_id':c['session_id'],'exclusion_reasons':reasons,'priority':priority})
        if not reasons:candidates.append((priority,c))
    if len(candidates)<count:raise ValueError('insufficient eligible recordings')
    return [c for _,c in sorted(candidates,key=lambda p:p[0])[:count]],accounting


def main():
    excluded=set();bindings={}
    for name in ('2026_09_27_roof_direction_subset/manifest.json',
                 '2026_09_27_roof_direction_subset/evaluation_manifest.json',
                 '2026_09_27_roof_geometry_confirmation/manifest.json',
                 '2026_09_27_roof_balanced_confirmation/manifest.json'):
        raw=(REPORTS/name).read_bytes();bindings[name]=sha(raw);d=json.loads(raw)
        excluded.update(s['pose']['session_id'] for s in d['sessions'])
        excluded.update(d.get('development_session_ids',[]))
    name='2026_09_27_roof_geometry_evaluation/verified_results.json'
    raw=(REPORTS/name).read_bytes();bindings[name]=sha(raw);d=json.loads(raw)
    for key in ('complete_calibration_sessions','excluded_incomplete_calibration_sessions',
                'complete_holdout_sessions','excluded_incomplete_holdout_sessions'):
        excluded.update(d[key]) # membership fields only, no scores used
    raw=(DATASET/'manifest.json').read_bytes();ds=json.loads(raw)
    captures,accounting=select(ds['captures'],excluded)
    sessions=[]
    for c in captures:
        pose_bytes=(DATASET/c['pose_path']).read_bytes()
        if sha(pose_bytes)!=c['pose_file_sha256']:raise ValueError('pose file binding changed')
        sessions.append({'capture':c,'pose':json.loads(pose_bytes)})
    out={'scope':'Recording-disjoint RX experiment; not universally unseen across other DS6 research.',
         'seed':SEED,'selection':'four lowest SHA256(seed:session_id), eligible frozen DS6 metadata',
         'dataset_sha256':sha(raw),'membership_source_sha256':bindings,'excluded_session_ids':sorted(excluded),
         'accounting':accounting,'sessions':sessions,'selection_code_sha256':sha(Path(__file__).read_bytes())}
    with (HERE/'manifest.json').open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print('FROZEN',[(s['capture']['session_id'],s['capture']['sample_rate_msps']) for s in sessions])
    print('Eligible',sum(not a['exclusion_reasons'] for a in accounting),'of',len(accounting),'excluded RX IDs',len(excluded))


if __name__=='__main__':main()
