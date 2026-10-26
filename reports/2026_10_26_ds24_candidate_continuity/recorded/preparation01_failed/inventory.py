"""One frozen read-only export inventory; no detector, catalogue or position port."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import numpy as np
from continuity import CFO_PERIOD, global_phase, identity, linear_path, wrap

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024/DS24-0011')
sys.path.insert(0, str(REPO/'tools'))
from ds23_frame_registration import unique_peaks


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text())
def dump(path, value): Path(path).write_text(json.dumps(value, indent=2, default=encode)+'\n')
def encode(x): return x.item() if isinstance(x, np.generic) else x.tolist() if isinstance(x,np.ndarray) else str(x)


def csv_write(path, rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader();writer.writerows(rows)


def window(probe, source, origin, observation=None, owner=''):
    fs=source['sample_rate_hz']; offset=probe['probe_start_ms']*fs/1000
    if abs(offset-round(offset)) > 1e-6: raise ValueError('nonintegral probe offset')
    start=int(probe['valid_start_counter'])+round(offset); duration=round(source['probe_ms']*fs/1000)
    wid=identity([source['session_id'],source['input_manifest_sha256'],probe['receiver_id'],start,start+duration])
    candidates=probe['candidates']; dedup=unique_peaks(candidates,fs); retained={q['rank'] for q in dedup}
    passing=[q for q in candidates if q['passed_fractional_margin_gate'] is True]
    best=max(passing,key=lambda q:(q['fractional_margin'],-q['candidate_rank'])) if passing else None
    if observation is not None:
        assert observation['observation_id']==wid
        assert observation['measured_cfo_hz']==best['fractional_tracking_cfo_hz']
        assert observation['fractional_margin']==best['fractional_margin']
    out=dict(window_id=wid,physical_window_id=identity([source['stream_generation'],start,start+duration,probe['actual_rf_hz']]),
        observation_id=None if observation is None else observation['observation_id'], receiver_id=probe['receiver_id'],
        receiver=probe['receiver_id']+1,channel=probe['channel'],actual_rf_hz=probe['actual_rf_hz'],
        time_s=(start-origin)/fs+source['probe_ms']/2000,window_start_counter=start,origin_counter=int(origin),
        valid_start_counter=int(probe['valid_start_counter']),probe_start_ms=probe['probe_start_ms'],
        duration_samples=duration,visit_index=probe['visit_index'],probe_index=probe['probe_index'],
        original_owner=owner,candidates=[])
    ledger=[]
    for q in candidates:
        local=q['integer_epoch_sample']+q['fractional_epoch_offset_samples']
        row=dict(candidate_id=identity([wid,q['candidate_rank']]),window_id=wid,observation_id=out['observation_id'],
            receiver_id=out['receiver_id'],receiver=out['receiver'],channel=out['channel'],actual_rf_hz=out['actual_rf_hz'],
            time_s=out['time_s'],original_owner=owner,candidate_rank=q['candidate_rank'],
            cfo_hz=q['fractional_tracking_cfo_hz'],global_epoch_samples=global_phase(start,origin,local,fs),
            local_epoch_samples=local,integer_epoch_sample=q['integer_epoch_sample'],
            fractional_epoch_offset_samples=q['fractional_epoch_offset_samples'],margin=q['fractional_margin'],
            fractional_exact_score=q['fractional_exact_score'],fractional_control_score=q['fractional_control_score'],
            acquired_cfo_hz=None,acquired_cfo_status='unavailable_in_original_contract',
            gate_passed=q['passed_fractional_margin_gate'],dedup_retained=q['candidate_rank'] in retained,
            original_winner=best is not None and q['candidate_rank']==best['candidate_rank'],
            window_start_counter=start,origin_counter=int(origin),visit_index=probe['visit_index'],probe_index=probe['probe_index'])
        if best is None:
            row.update(winner_CFO_gap_Hz=None,winner_epoch_gap_samples=None,nearby_alternative=False)
        else:
            row.update(winner_CFO_gap_Hz=float(wrap(row['cfo_hz']-best['fractional_tracking_cfo_hz'],CFO_PERIOD)),
                winner_epoch_gap_samples=float(wrap(local-best['integer_epoch_sample']-best['fractional_epoch_offset_samples'],fs/750)))
            row['nearby_alternative']=bool(row['dedup_retained'] and not row['original_winner'] and
                abs(row['winner_epoch_gap_samples'])<=3 and 250<abs(row['winner_CFO_gap_Hz'])<=5000)
        ledger.append(row)
        if row['dedup_retained']:out['candidates'].append(row)
    return out,ledger


def prepare():
    if (HERE/'protocol.json').exists(): raise FileExistsError('do not overwrite freeze')
    tick=time.monotonic()
    document=load(SOURCE/'tracking.json');obs=load(SOURCE/'observations.json');tracks=load(SOURCE/'tracks.json')
    source=document['source'];origin=document['clock_anchor']['sample_counter'];probe=source['probes'][0]
    row=next(r for r in obs if r['native_receiver_id']==probe['receiver_id'] and r['channel']==probe['channel'] and r['time_s']==.01)
    w,ledger=window(probe,source,origin,row)
    assert w['window_start_counter']==origin and w['candidates'] and len(obs)==3754 and len(tracks)==117
    dump(HERE/'smoke.json',dict(seconds=time.monotonic()-tick,first_window=w,all_exported_candidates=ledger,
        metadata_only=True,no_path_outcomes=True,original_winner_count=len(obs),original_owner_count=len(tracks)))
    testtick=time.monotonic()
    test=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(HERE/'test_continuity.py')],cwd=HERE,capture_output=True,text=True)
    dump(HERE/'test_receipt.json',dict(returncode=test.returncode,seconds=time.monotonic()-testtick,stdout=test.stdout,stderr=test.stderr))
    if test.returncode:raise RuntimeError('owned tests failed')
    paths=[SOURCE/n for n in ('tracking.json','observations.json','tracks.json')]
    paths += [HERE/n for n in ('continuity.py','inventory.py','test_continuity.py','PROTOCOL.md','smoke.json','test_receipt.json')]
    paths += [ROOT/'COORDINATOR_PLAN.md',ROOT/'CLOCK_AND_EXPORT_REVIEW.md',REPO/'tools/ds23_frame_registration.py',REPO/'src/leo/analysis/research/public_tracking_points.py',REPO/'src/leo/processing/fast_scan.py']
    protocol=dict(schema='recorded-candidate-persistence/v1',bindings={str(p):sha(p) for p in paths},
        prior_metadata_read_charge_seconds=1.,preparation_seconds=load(HERE/'smoke.json')['seconds'],test_seconds=load(HERE/'test_receipt.json')['seconds'],
        cap_worker_seconds=180,numerical_workers=1,BLAS_threads=1,original_winners=3754,original_owners=117,
        path_outcomes_not_viewed=True,policy_document='PROTOCOL.md',acquired_CFO_available=False)
    dump(HERE/'protocol.json',protocol);print('FROZEN',sha(HERE/'protocol.json'),flush=True)


def run():
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if os.environ.get(key)!='1':raise RuntimeError('single BLAS thread required')
    if (HERE/'RF_seal.json').exists():raise FileExistsError('one run only')
    protocol=load(HERE/'protocol.json')
    for path,value in protocol['bindings'].items():
        if sha(path)!=value:raise ValueError('changed freeze: '+path)
    approval=load(ROOT/'audit/recorded_preflight.json')
    if not approval['all_passed'] or approval['protocol_sha256']!=sha(HERE/'protocol.json'):raise ValueError('independent preflight mismatch')
    before=protocol['prior_metadata_read_charge_seconds']+protocol['preparation_seconds']+protocol['test_seconds']
    tick=time.monotonic();remaining=180-before
    if remaining<=0:raise TimeoutError('preparation exhausted budget')
    def deadline(*_):raise TimeoutError('frozen cumulative 180-second cap')
    signal.signal(signal.SIGALRM,deadline);signal.setitimer(signal.ITIMER_REAL,remaining)
    document=load(SOURCE/'tracking.json');obs=load(SOURCE/'observations.json');tracks=load(SOURCE/'tracks.json')
    source=document['source'];fs=source['sample_rate_hz'];origin=document['clock_anchor']['sample_counter']
    index={(r['native_receiver_id'],r['channel'],round(r['time_s'],9)):r for r in obs}
    memberships={}
    for track in tracks:
        for oid in track['observation_ids']:
            if oid in memberships:raise ValueError('duplicate original graph ownership')
            memberships[oid]=track['key']
    windows=[];ledger=[];seen=set()
    for probe in source['probes']:
        start=probe['valid_start_counter']+round(probe['probe_start_ms']*fs/1000)
        t=(start-origin)/fs+source['probe_ms']/2000
        row=index.get((probe['receiver_id'],probe['channel'],round(t,9)))
        w,rows=window(probe,source,origin,row,memberships.get(row['observation_id'],'') if row else '')
        if row:seen.add(row['observation_id'])
        windows.append(w);ledger.extend(rows)
    assert len(seen)==len(obs)==3754 and len(tracks)==117
    assert len({w['window_id'] for w in windows})==len(windows)
    port=dict(schema='rf-candidate-window-port/v1',sample_rate_hz=fs,frame_rate_hz=750,windows=windows,
        acquired_CFO_available=False,counter_phase_authority='device counter relative common origin, exact rational period')
    dump(HERE/'all_windows.json',port);csv_write(HERE/'all_candidate_rows.csv',ledger)
    owner_rows=[];failure=None
    byowner={t['key']:[] for t in tracks}; winowner={t['key']:[] for t in tracks}
    for r in ledger:
        if r['original_owner'] in byowner:
            if r['nearby_alternative']:byowner[r['original_owner']].append(r)
            if r['original_winner']:winowner[r['original_owner']].append(r)
    for tr in tracks:
        key=tr['key'];orig=sorted(winowner[key],key=lambda r:(r['time_s'],r['observation_id']))
        assert {r['observation_id'] for r in orig}==set(tr['observation_ids'])
        times=np.asarray([r['time_s'] for r in orig]);nflag=len({r['observation_id'] for r in byowner[key]})
        owner_rows.append(dict(owner=key,receiver=tr['receiver'],channel=tr['channel'],actual_rf_hz=tr['rf_hz'],
            start_s=tr['start_s'],end_s=tr['end_s'],original_points=len(orig),quality_status=tr['quality_status'],
            original_native_ids=tr['observation_ids'],pointwise_flagged_windows=nflag,nearby_alternative_rows=len(byowner[key]),
            control_eligible=bool(len(orig)>=5 and times[-1]-times[0]>=3 and np.max(np.diff(times))<=2 and nflag==0),
            status='not_attempted',persistent=False,path=None))
    try:
        for row in owner_rows:
            row['status']='in_progress';row['path']=linear_path(byowner[row['owner']],fs)
            row['persistent']=row['path'] is not None;row['status']='complete'
    except Exception as exc:
        failure=dict(type=type(exc).__name__,message=str(exc))
        for row in owner_rows:
            if row['status']=='in_progress':row['status']='unavailable'
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    order=lambda r:(r['start_s'],r['receiver'],r['channel'],r['owner'])
    positives=sorted([r for r in owner_rows if r['status']=='complete' and r['persistent']],key=order)
    controls=sorted([r for r in owner_rows if r['control_eligible']],key=order)
    selected=dict(positive=positives[0]['owner'] if positives else None,control=controls[0]['owner'] if controls else None,
        no_replacement=True,rule='First chronological eligible original owner; no label/position use')
    dump(HERE/'owners.json',owner_rows)
    csv_write(HERE/'owners.csv',[{k:(json.dumps(v) if isinstance(v,(list,dict)) else v) for k,v in r.items()} for r in owner_rows])
    dump(HERE/'selection.json',selected)
    for label in ('positive','control'):
        selected_windows=[w for w in windows if w['original_owner']==selected[label]] if selected[label] else []
        dump(HERE/(label+'_port.json'),dict({k:v for k,v in port.items() if k!='windows'},owner=selected[label],windows=selected_windows,
            all_original_owner_windows_preserved=True,not_independent_physical_source_claim=True))
    summary=dict(probes=len(windows),raw_candidate_rows=len(ledger),gatepassing_candidate_rows=sum(r['gate_passed'] is True for r in ledger),
        deduplicated_candidate_rows=sum(r['dedup_retained'] for r in ledger),original_winners=len(obs),original_owners=len(tracks),
        original_winners_without_owner=sum(not r['original_owner'] for r in ledger if r['original_winner']),
        flagged_windows=len({r['window_id'] for r in ledger if r['nearby_alternative']}),nearby_alternative_rows=sum(r['nearby_alternative'] for r in ledger),
        completed_owners=sum(r['status']=='complete' for r in owner_rows),persistent_owners=len(positives),control_eligible_owners=len(controls),
        selection=selected,failure=failure,run_worker_seconds=time.monotonic()-tick,cumulative_worker_seconds=before+time.monotonic()-tick,
        no_detector_IQ_catalogue_GPS_or_position=True,no_new_observations=True,original_owners_unchanged=True)
    dump(HERE/'summary.json',summary)
    files=[p for p in HERE.iterdir() if p.is_file() and p.name!='RF_seal.json']
    dump(HERE/'RF_seal.json',dict(protocol_sha256=sha(HERE/'protocol.json'),preflight_sha256=sha(ROOT/'audit/recorded_preflight.json'),
        files={str(p):sha(p) for p in sorted(files)}))
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run']);args=parser.parse_args()
    prepare() if args.action=='prepare' else run()
