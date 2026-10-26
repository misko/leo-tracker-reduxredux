"""Source-bound old-parent replay only. No discovery, optimizer or new scans."""
import time
STARTED=time.monotonic()
import argparse
import hashlib
import json
import math
from pathlib import Path
import signal
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
OLD=Path('/srv/bulk/leo/research/ds25-20261024')
INFLUENCE=Path('/srv/bulk/leo/research/ds24-detector-response-r01/influence')
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
RECOVERY=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
sys.path[:0]=['/tmp/algo03-feasible-deps',str(REPO/'src'),str(REPO/'tools'),str(RECOVERY)]
import recovery as r


def equal_prior_selection(saved):
    valid=[t for t in saved['trials'] if t['paired_valid']]
    best=min(valid,key=lambda t:t['arms']['c0']['corrected_selection_loss']) if valid else None
    accepted=bool(best and best['arms']['c0']['corrected_selection_loss']<saved['baseline_corrected_loss']['c0'])
    return accepted,best if accepted else None


def nominate(families,owners):
    ranked=sorted([f for f in families if f['has_eligible_owner']],key=lambda f:(-f['paired_score'],f['family']))
    if not ranked:return None,None
    target=sorted([o for o in owners if o['eligible'] and o['family']==ranked[0]['family']],key=lambda o:(-o['paired_score'],o['owner']))[0]
    low=sorted([f for f in ranked if f['family']!=target['family'] and f['paired_score']>0],key=lambda f:(f['paired_score'],f['family']))
    low=low[:max(1,math.ceil(len(low)/4))];scores={f['family']:f['paired_score'] for f in low}
    controls=sorted([o for o in owners if o['eligible'] and o['family'] in scores],key=lambda o:(o['receiver']==target['receiver'],scores[o['family']],o['paired_score'],o['owner']))
    return target,controls[0] if controls else None


def write(name,value):r.write_new(HERE/name,value)


def freeze():
    paths=[Path(__file__),HERE/'test_replay.py',HERE.parent/'COORDINATOR_PLAN.md',OLD/'protocol.json',
        OLD/'engine/ds24_engine.py',OLD/'engine/run_baseline.py',OLD/'family_cavity/position/DS24-0010.json',
        OLD/'DS24-0010/algo02_result.json',OLD/'DS24-0010/result.json',OLD/'DS24-0010/observations.json',
        OLD/'DS24-0010/tracks.json',INFLUENCE/'panel.py',INFLUENCE/'results.json',RECOVERY/'recovery.py']
    paths +=[REPO/'tools'/n for n in ('algo02_scan.py','run_algo01_ds23_sample.py','probe_ds23_family_cavity_nominations.py',
        'probe_ds23_family_cavity_position.py','probe_ds23_frequency_events.py','ds23_frequency_events.py')]
    write('replay_protocol.json',dict(files={str(p):r.sha(p) for p in paths},case='DS24-0010',arms=['c0','fitted_c'],
        maximum_numerical_seconds=60,workers=1,BLAS_threads=1,optimizer_calls=0,new_scan_baselines=0,
        scope='equal-prior adoption replay plus old final-state full-objective/gate replay and old RF-only owner-rule parity; not full rediscovery',
        endpoint_objective_tolerance_absolute=1e-3,endpoint_objective_tolerance_relative=1e-8))


def run():
    protocol=r.read(HERE/'replay_protocol.json')
    for p,h in protocol['files'].items():
        if r.sha(p)!=h:raise ValueError('bound old input/source changed: '+p)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('60-second old replay cap')))
    remaining=60-(time.monotonic()-STARTED)
    if remaining<=0:raise TimeoutError('setup exhausted old replay cap')
    signal.setitimer(signal.ITIMER_REAL,remaining)
    result=dict(case='DS24-0010',status='failed',new_scan_baselines=0,optimizer_calls=0,GPS_read=False)
    try:
        authority=r.read(OLD/'protocol.json')['inference_sources_sha256']
        for p,h in authority.items():
            if r.sha(p)!=h.removeprefix('sha256:'):raise ValueError('authoritative DS24 engine source differs')
        saved=r.read(OLD/'family_cavity/position/DS24-0010.json');accepted,best=equal_prior_selection(saved)
        if accepted!=saved['accepted'] or (best is not None and best!=saved['selected']):raise ValueError('fresh equal-prior selection did not reproduce')
        d=r.context('DS24-0010');arms=[]
        for arm in ('c0','fitted_c'):
            s=d['arms'][arm];p=r.build(d,arm,s['phase_reference']);x=np.asarray(s['endpoint_east_north_km']);c=p.calculate(x)
            difference=float(c['negative_twice_elbo']-s['negative_twice_elbo']);relative=abs(difference)/max(1,abs(s['negative_twice_elbo']))
            if abs(difference)>1e-3 or relative>1e-8:raise ValueError('old full parent objective does not replay')
            member=r.membership(d,arm,s)
            arms.append(dict(arm=arm,objective_difference=difference,relative_objective_difference=relative,
                curved_IDs=member['curved_points'],predictive_IDs=member['predictive_points'],accepted_IDs=member['associated'],
                all_active_curved_gates_pass=all(t['compatible'] for t in member['gates']['tracks']),
                current_phase_reference_is_saved_last_fit_input=True))
        old=r.read(INFLUENCE/'results.json');owner_parity=[]
        for selected in old['selection']:
            case=selected['case'];target,control=nominate([f for f in old['families'] if f['case']==case],[o for o in old['owners'] if o['case']==case])
            if target['owner']!=selected['target']['owner'] or (control['owner'] if control else None)!=(selected['control']['owner'] if selected['control'] else None):raise ValueError('RF-only owner selection differs')
            owner_parity.append(dict(case=case,target=target['owner'],control=control['owner'] if control else None,
                complete_target_IDs=target['points'],complete_control_IDs=control['points'] if control else 0))
        result.update(status='complete',all_passed=True,arms=arms,equal_prior_adoption_exact=True,
            reconstructed_fresh_reference=saved['reconstructed_fresh_reference'],owner_rule_parity=owner_parity,
            method_scope=protocol['scope'])
    except Exception as exc:result.update(error=repr(exc),all_passed=False)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result['cumulative_numerical_seconds']=time.monotonic()-STARTED
    write('replay.json',result)
    write('replay_seal.json',dict(protocol_sha256=r.sha(HERE/'replay_protocol.json'),files={str(HERE/n):r.sha(HERE/n) for n in ('replay.py','test_replay.py','replay_protocol.json','replay.json')}))
    print(result,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'));a=parser.parse_args();{'freeze':freeze,'run':run}[a.action]()
