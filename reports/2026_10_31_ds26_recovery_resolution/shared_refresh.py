"""Bounded shared-posterior test; identical physical priors and exact gates."""
import argparse
import hashlib
from pathlib import Path
import signal
import time
from types import SimpleNamespace
import numpy as np
from debug_fast_graph_unassociated import read, write
from phase_reference_checks import phase_refresh, reference_domain

BASE = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030/cases')
PREVIOUS = Path('/srv/bulk/leo/research/ds26-recovery-validation-20261031')
TARGETS = {'DS26-0265':'36f621d91e81526b1ce4', 'DS26-0223':'3c60fb41d56d1333bfc4'}

def check_domain(p, phases):
    from ds23_predictive_linear import linear_geometry
    checks = {'curved':reference_domain(p.sky['time_s'],p.flat_times,p.flat_labels,phases)}
    if p.linear_entries:
        view,*_=linear_geometry(p,p.linear_entries)
        checks['predictive']=reference_domain(p.sky['time_s'],view.flat_times,view.flat_labels,phases)
    if not all(v['in_domain'] for v in checks.values()):raise ValueError('phase refresh outside causal bank')
    return checks

def run(case,out):
    import include_predictive_annotations as inclusion
    import audit_shared_predictive_inclusion as audit
    source=BASE/case/'candidate-v2/recovery'
    inventory=next((source/'all-large-track-recovery').glob('*/inventory.json'))
    annotation=(PREVIOUS/'phase0265/matched-run01/reference30/annotation') if case=='DS26-0265' else source/TARGETS[case]/'annotation'
    start=time.monotonic()
    write(out/'protocol.json',dict(case=case,inventory=str(inventory),annotation=str(annotation),
        variants=['unchanged','shared_posterior'],reference_limit_s=30,
        same_physical_priors_candidates_observations_starts_budgets=True,
        GPS_used=False,new_TLE=False,new_RF=False,receiver_updates_from_target=False,
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [inventory,annotation/'result.json',annotation/'protocol.json',Path(__file__)]}))
    make_original=inclusion.make_event_problem; refresh_original=inclusion.phase_refresh; current={}
    def capture(*a,**k):
        p=make_original(*a,**k);current['p']=p;return p
    def refresh(actual,reference):
        phases,checks=phase_refresh(actual,reference,limit_s=30)
        checks['next_reference_domain']=check_domain(current['p'],phases)
        return phases,checks
    inclusion.make_event_problem=capture;inclusion.phase_refresh=refresh
    rows=[]
    try:
        for name,shared in [('unchanged',False),('shared_posterior',True)]:
            folder=out/name
            inclusion.run(SimpleNamespace(output=folder,inventory=inventory,validation=[annotation],
                native_branches=None,native_from_validation=False,predictive_member=True,
                noise_policy='original',position_fit='regional_unconstrained',
                orphan_phase_refresh=False,orphan_orbit_prior=False,target_orbit_prior=False,
                shared_satellite_refresh=shared,conditional_satellite_refresh=False,joint_only=False))
            previous=audit.phase_refresh
            audit.phase_refresh=lambda actual,reference:phase_refresh(actual,reference,limit_s=30)
            try:audit.run(SimpleNamespace(trial=folder,study=source,output=folder/'exact_owner_replay.json'))
            finally:audit.phase_refresh=previous
            for role in ['control','target_0']:
                saved=read(folder/(role+'.json'))
                for arm,v in saved['arms'].items():
                    exact=next(r for r in read(folder/'exact_owner_replay.json')['rows'] if r['role']==role and r['arm']==arm)
                    rows.append(dict(case=case,variant=name,role=role,arm=arm,
                        paired_valid=saved['paired_valid'],exact_verified=exact['verified'],
                        endpoint_latlon=v['endpoint_latlon'],endpoint_east_north_km=v['endpoint_east_north_km'],
                        added_points=v['added_points'],lost_points=v['lost_points'],final_phase_change_s=v['final_phase_change_s'],
                        target_diagnostics=v.get('target_diagnostics',[]),
                        shared_satellite_replay=v.get('shared_satellite_replay'),
                        failed_slacks={k:value for r in exact['exact_family_replays'] for k,value in r['all_gate_slacks'].items() if value<0},
                        objective=v['negative_twice_elbo'],curved_RMS_hz=v['RMS_hz'],
                        maximum_exact_orbit_difference_hz=max(r['maximum_linearization_difference_hz'] for r in exact['exact_family_replays']),
                        owner_changes=exact['incumbent_ownership_changes'],
                        stop_reasons=[h['fit']['stopped'] for h in v['history']]))
    finally:inclusion.make_event_problem=make_original;inclusion.phase_refresh=refresh_original
    write(out/'summary.json',dict(rows=rows,GPS_used=False,seconds=time.monotonic()-start))
    paths=list(out.rglob('*.json'))
    write(out/'inference_seal.json',dict(GPS_used=False,artifacts_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))
    write(out/'terminal.json',dict(completed=True,seconds=time.monotonic()-start))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',choices=list(TARGETS),required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    def timeout(*unused):raise TimeoutError('590-second research budget')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(590)
    try:run(a.case,a.output)
    except Exception as exc:
        write(a.output/'failure.json',dict(type=type(exc).__name__,message=str(exc)));raise
