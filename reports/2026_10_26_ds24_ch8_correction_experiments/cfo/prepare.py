"""Freeze RF-only complete-owner nomination before any new IQ/refinement."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
PRIOR = Path('/srv/bulk/leo/research/ds24-detector-response-r01')
COMPLETE = Path('/srv/bulk/leo/research/ds24-complete-owner-refinement-r01/measurement')
DEPLOYED = Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')
HISTORICAL_PYTHON = '/opt/leo-fast-auto/20261010-r1/venv/bin/python'
RECOVERY = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def encode(value):
    if hasattr(value, 'tolist'):
        return value.tolist()
    raise TypeError(type(value).__name__)


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, default=encode, allow_nan=False)
        stream.write('\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def quantile_ids(owner):
    points = sorted(owner['points'], key=lambda p: (p['time_s'], p['native_id']))
    lo, hi = points[0]['time_s'], points[-1]['time_s']
    return [min(points, key=lambda p: (abs(p['time_s']-(lo+q*(hi-lo))), p['time_s'], p['native_id']))['native_id']
            for q in (1/3, 2/3)]


def nominate(tracks, curved_indices, arm_curved_ids, require_all=True):
    candidates = []
    for i in curved_indices:
        track = tracks[i]
        if track['receiver'] not in (1, 2) or track['channel'] not in (7, 8):
            continue
        ids = track['observation_ids']
        times = list(map(float, track['times']))
        eligible = len(ids) == len(set(ids)) and all(set(ids) <= set(v) for v in arm_curved_ids.values())
        candidates.append(dict(owner=track['key'], track_index=i, receiver=track['receiver'], channel=track['channel'],
            count=len(ids), start_s=min(times), end_s=max(times), span_s=max(times)-min(times), eligible=eligible,
            missing_by_arm={a:sorted(set(ids)-set(v)) for a,v in arm_curved_ids.items()},
            points=[dict(native_id=oid, time_s=t) for oid,t in zip(ids,times,strict=True)]))
    selected = []
    for rx in (1,2):
        for channel in (7,8):
            ranked = sorted((c for c in candidates if c['receiver']==rx and c['channel']==channel and c['eligible']),
                            key=lambda c:(-c['span_s'],-c['count'],c['owner']))
            if not ranked:
                if require_all:
                    raise ValueError(f'no eligible complete retained curved owner RX{rx} CH{channel}')
                continue
            selected.append(dict(ranked[0], initial_quantile_native_ids=quantile_ids(ranked[0])))
    return selected,candidates


def main():
    started=time.monotonic()
    sys.path[:0]=['/tmp/algo03-feasible-deps',str(REPO/'src'),str(REPO/'tools'),str(RECOVERY)]
    import recovery as r
    templates={x['case']:x for x in load(PRIOR/'influence/window_requests.json')}
    owners=[];rankings={};requests=[];inputs={}
    for case in ('DS24-0010','DS24-0011'):
        d=r.context(case);curved={}
        for arm in ('c0','fitted_c'):
            p=r.build(d,arm,d['arms'][arm]['phase_reference'])
            curved[arm]=[oid for i,sl in zip(p.members,p.slices,strict=True)
                         for oid,on in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if on]
            assert list(p.lower)==[-12.5,-12.5] and list(p.upper)==[12.5,12.5]
        chosen,candidates=nominate(d['scan'].tracks,d['scan'].curved,curved,require_all=False)
        rankings[case]=candidates
        tracking=load(SOURCE/case/'tracking.json');source=tracking['source'];fs=source['sample_rate_hz']
        origin=tracking['clock_anchor']['sample_counter'];obs={o['observation_id']:o for o in d['observations']}
        for owner in chosen:
            owner=dict(owner,case=case);owners.append(owner)
            for point in sorted(owner['points'],key=lambda p:(p['time_s'],p['native_id'])):
                o=obs[point['native_id']]
                probes=[p for p in source['probes'] if p['receiver_id']==o['native_receiver_id'] and p['channel']==o['channel']
                        and abs((p['valid_start_counter']-origin)/fs+p['probe_start_ms']/1000+source['probe_ms']/2000-o['time_s'])<1e-8]
                assert len(probes)==1
                p=probes[0];passing=[c for c in p['candidates'] if c['passed_fractional_margin_gate']]
                candidate=max(passing,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
                assert candidate['fractional_tracking_cfo_hz']==o['measured_cfo_hz'] and candidate['fractional_margin']==o['fractional_margin']
                requests.append(dict(request_id=case+'_'+point['native_id'].split(':')[1],case=case,role='CH7_control' if o['channel']==7 else 'CH8_target',
                    complete_owner=owner['owner'],native_observation_id=point['native_id'],original_observation=o,
                    initial_panel=point['native_id'] in owner['initial_quantile_native_ids'],
                    tracking=dict(path=str(SOURCE/case/'tracking.json'),sha256=sha(SOURCE/case/'tracking.json')),
                    **{k:templates[case][k] for k in ('source_input','source_session_id','recording_id','raw_recording_authority_digest')},
                    probe=dict(visit_index=p['visit_index'],probe_index=p['probe_index'],receiver_id=p['receiver_id'],channel=p['channel'],actual_rf_hz=p['actual_rf_hz'],
                        time_s=o['time_s'],window_start_counter=p['valid_start_counter']+round(p['probe_start_ms']*fs/1000),origin_counter=origin,duration_samples=round(source['probe_ms']*fs/1000)),
                    original_candidate=candidate,acquired_cfo_hz=None))
        for name in ('tracking.json','observations.json','tracks.json','receipt.json','nominal_elements.json'):
            inputs[str(SOURCE/case/name)]=sha(SOURCE/case/name)
        inputs[str(SOURCE/'family_cavity/position'/(case+'.json'))]=sha(SOURCE/'family_cavity/position'/(case+'.json'))
    assert len(requests)==len({r['native_observation_id'] for r in requests})
    unavailable=[dict(case=case,receiver=rx,channel=channel,status='no_complete_retained_curved_owner')
                 for case in ('DS24-0010','DS24-0011') for rx in (1,2) for channel in (7,8)
                 if not any(o['case']==case and o['receiver']==rx and o['channel']==channel for o in owners)]
    manifest=dict(schema='ch8-complete-owner-nomination/v1',owners=owners,ranking=rankings,total_native_points=len(requests),
                  cases=['DS24-0010','DS24-0011'],selection='span_desc_count_desc_key_asc_complete_both_arm_curved',
                  initial_quantiles=[1/3,2/3],max_native_points=1200,inputs=inputs,GPS_used=False,corrections_used=False,exposed_development_scans=True,
                  expected_owner_cells=8,available_owner_cells=len(owners),unavailable_owner_cells=unavailable,
                  expected_eight_owner_panel_complete=not unavailable)
    if (HERE/'nomination_manifest.json').exists():
        assert load(HERE/'nomination_manifest.json')==manifest, 'frozen nomination changed'
    else:
        write(HERE/'nomination_manifest.json',manifest)
    if unavailable:
        if not (HERE/'failed_expected_eight_nomination.json').exists():
            write(HERE/'failed_expected_eight_nomination.json',dict(status='expected_eight_owner_panel_unavailable',
                manifest_sha256=sha(HERE/'nomination_manifest.json'),unavailable=unavailable,
                no_IQ_reads=True,no_corrections=True,no_replacements=True))
        assert (HERE/'ADDENDUM_01.md').exists(), 'explicit missing-cell continuation addendum required'
    if len(requests)>1200:
        raise ValueError('panel exceeds 1200; manifest preserved without truncation')
    write(HERE/'requests_before_authority.json',requests)
    command=['sudo','-n','-u','leo','env','PYTHONPATH='+str(DEPLOYED),'PYTHONDONTWRITEBYTECODE=1','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1',HISTORICAL_PYTHON,'-B',str(PRIOR/'influence/raw_metadata.py')]
    result=subprocess.run(command,input=json.dumps(requests),capture_output=True,text=True,timeout=90)
    write(HERE/'metadata_receipt.json',dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,IQ_reads=0))
    if result.returncode:
        raise ValueError('public metadata authority failed')
    authority={x['request_id']:x['raw_authority'] for x in json.loads(result.stdout)}
    for req in requests:
        req['raw_authority']=authority[req['request_id']]
        if req['raw_authority']['status']!='metadata_ready_IQ_and_detector_parity_unverified':
            raise ValueError('raw authority unavailable '+req['request_id'])
    write(HERE/'requests.json',requests)
    paths=[Path(__file__),HERE/'PROTOCOL.md',HERE/'ADDENDUM_01.md',HERE/'failed_expected_eight_nomination.json',HERE/'test_cfo.py',HERE/'run_rf.py',HERE/'nomination_manifest.json',HERE/'requests.json',
           PRIOR/'recorded/replay.py',PRIOR/'measurement/refiner.py',PRIOR/'recorded/authority.json',PRIOR/'influence/raw_metadata.py',
           COMPLETE/'complete.py',RECOVERY/'recovery.py']
    paths += list(map(Path,inputs))
    write(HERE/'protocol.json',dict(schema='ch8-continuous-cfo/v1',files={str(p):sha(p) for p in paths},
        nominal_points=len(requests),initial_slots=sum(r['initial_panel'] for r in requests),max_job_seconds=600,
        max_cumulative_worker_seconds=1150,initial_max_seconds=90,workers=2,BLAS_threads=1,preparation_seconds=time.monotonic()-started,
        same_correction_both_c_arms=True,expected_owner_cells=8,available_owner_cells=len(owners),unavailable_owner_cells=unavailable,GPS_used=False))
    print(json.dumps(dict(points=len(requests),owners=[{k:v for k,v in o.items() if k not in ('points','missing_by_arm')} for o in owners],protocol_sha256=sha(HERE/'protocol.json')),indent=2))


if __name__=='__main__':
    main()
