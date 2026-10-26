"""Matched cold full-channel fixed-assignment CFO intervention, no GPS access."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
import numpy as np

from prepare import HERE, REPO, RECOVERY, SOURCE, load, sha, write, module

sys.path[:0]=['/tmp/algo03-feasible-deps',str(REPO/'src'),str(REPO/'tools'),str(RECOVERY)]
import recovery as r
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import summary

PREVIOUS=Path('/srv/bulk/leo/research/ds24-complete-owner-refinement-r01/position')
FROZEN=Path('/srv/bulk/leo/research/ds24-cfo-precision-factorial-r01/solver/model.py')
replacement=module('proven_native_delta',PREVIOUS/'replacement.py')
model=module('proven_full_precision_packet',FROZEN)
OUT=HERE/'position'


def save(path,value):
    p=OUT/path;p.parent.mkdir(parents=True,exist_ok=True);write(p,value)


def alarm(seconds):
    if seconds<=0:
        raise TimeoutError('fixed solver budget exhausted')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('solver deadline')))
    signal.setitimer(signal.ITIMER_REAL,seconds)


def freeze():
    manifest=load(HERE/'nomination_manifest.json')
    controls=[];packets={}
    started=time.monotonic()
    for case in manifest['cases']:
        d=r.context(case);ids=[p['native_id'] for o in manifest['owners'] if o['case']==case for p in o['points']]
        obs={o['observation_id']:o for o in d['observations']}
        zero=[dict(native_observation_id=i,original_cfo_hz=obs[i]['measured_cfo_hz'],corrected_cfo_hz=obs[i]['measured_cfo_hz'],numerical_frequency_qualified=True) for i in ids]
        injected,receipt=replacement.inject(d,zero,ids)
        for arm in ('c0','fitted_c'):
            saved=d['arms'][arm];x=np.asarray(saved['endpoint_east_north_km'])
            p=r.build(d,arm,saved['phase_reference']);c=p.calculate(x)
            q=r.build(injected,arm,saved['phase_reference']);cz=q.calculate(x)
            assert c['negative_twice_elbo']==cz['negative_twice_elbo']
            assert abs(c['negative_twice_elbo']-saved['negative_twice_elbo'])<1e-3
            packet=dict(case=case,arm=arm,noise_precision=c['noise_precision'],coefficient_prior_precision=c['coefficient_prior_precision'],
                        source_endpoint=x,final_phase_reference=saved['phase_reference'],layout=model.layout(p))
            f=model.build(d,arm,saved['phase_reference'],packet);fc=f.calculate(x)
            ce=float(np.max(abs(fc['coefficient']-c['coefficient'])));re=float(np.max(abs(fc['conditional_residual_hz']-c['conditional_residual_hz'])))
            assert np.allclose(fc['coefficient'],c['coefficient'],atol=1e-6,rtol=1e-8) and re<=1e-3
            member=r.membership(d,arm,saved)
            assert set(ids)<=set(member['curved_observation_ids'])
            packets[case+'_'+arm]=packet
            controls.append(dict(case=case,arm=arm,zero_delta_exact=True,source_endpoint=x,source_objective=saved['negative_twice_elbo'],
                frozen_diagonal_max_coefficient_error=ce,frozen_diagonal_max_residual_error_hz=re,
                source_membership=member,injection=receipt,source_noise_precision=c['noise_precision'],source_prior_precision=c['coefficient_prior_precision']))
    save(Path('packets.json'),packets);save(Path('preparation.json'),dict(controls=controls,seconds=time.monotonic()-started,GPS_used=False))
    paths=[Path(__file__),HERE/'PROTOCOL.md',HERE/'ADDENDUM_01.md',HERE/'nomination_manifest.json',HERE/'protocol.json',
           OUT/'packets.json',OUT/'preparation.json',PREVIOUS/'replacement.py',FROZEN,RECOVERY/'recovery.py']
    paths += [REPO/'tools'/n for n in ('ds23_frozen_precision.py','probe_ds23_frequency_events.py','ds23_frequency_events.py',
        'investigate_dsx01_localization_failures.py','run_ds23_combined_recovery_full.py','audit_ds23_algo01_coverage.py',
        'evaluate_ds23_phase_refreshed.py','dsx01_joint_marginal.py','dsx01_hierarchical_bound.py','ds23_predictive_linear.py')]
    for case in manifest['cases']:
        paths += [SOURCE/'family_cavity/position'/(case+'.json')]
    save(Path('protocol.json'),dict(files={str(p):sha(p) for p in paths},cases=manifest['cases'],arms=['c0','fitted_c'],
        models=['ordinary_VI','fixed_original_full_precision_packet'],methods=['original','refined'],fits=16,
        start_km=[0.,0.],phase_reference='zero',phase_rounds=5,iterations=48,per_fit_seconds=45.,per_case_seconds=145.,
        outer_job_seconds=160.,maximum_cumulative_worker_seconds=300.,region_km=[25,25],center_lat_lon=[37.906,-122.545],
        initialization='cold_zero_position_and_phase_fixed_assignments_with_original_likelihood_mask',
        interpretation='full_channel_measurement_intervention_not_global_regional_association_rerun',
        ordinary_precision='unchanged_Gamma_updates',fixed_precision='both_noise_and_full_nuisance_prior_frozen_from_original_same_arm',
        paired_qualification='both_c_arms_original_gates_phase_Gamma_and_all_original_accepted_IDs_preserved',GPS_used=False))
    print('LOCALIZATION_FROZEN',sha(OUT/'protocol.json'),flush=True)


def solve(d,arm,kind,method,packet,baseline,deadline):
    started=time.monotonic();alarm(min(45.,deadline-started));x=np.zeros(2);reference=np.zeros(len(d['means']));history=[]
    for epoch in range(5):
        p=r.build(d,arm,reference) if kind=='ordinary_VI' else model.build(d,arm,reference,packet)
        fit_result=fit(p,x,iterations=48);x=np.asarray(fit_result['parameters'])
        phase=p.state(x)['phases'][p.labels];change=float(np.max(abs(np.clip(phase,-15,15)-reference)))
        history.append(dict(epoch=epoch,fit=fit_result,phase_reference=reference,unclipped_phase_s=phase,phase_change_s=change))
        save(Path(d['case'])/kind/method/arm/f'epoch{epoch}.json',history[-1]);reference=np.clip(phase,-15,15)
    c=p.calculate(x);record=summary(p,x,d['entries']);record.update(final_phase_change_s=change,history=history)
    if kind=='ordinary_VI':
        member=r.membership(d,arm,record)
    else:
        member,_=model.membership(p,x,d)
        assert np.array_equal(c['noise_precision'],packet['noise_precision'])
        assert np.array_equal(c['coefficient_prior_precision'],packet['coefficient_prior_precision'])
    original=baseline['source_membership']
    assert set(member['curved_observation_ids'])==set(original['curved_observation_ids'])
    assert set(member['predictive_observation_ids'])==set(original['predictive_observation_ids'])
    lost=sorted(set(original['accepted_observation_ids'])-set(member['accepted_observation_ids']))
    gate=bool(r.valid({a:record for a in ('c0','fitted_c')}))
    gamma=kind!='ordinary_VI' or c['final_log_precision_change']<=1e-5
    raw=dict(case=d['case'],arm=arm,kind=kind,method=method,summary=record,objective=c['negative_twice_elbo'],
        conditional_residual_hz=c['conditional_residual_hz'],noise_precision=c['noise_precision'],coefficient=c['coefficient'],
        coefficient_prior_precision=c['coefficient_prior_precision'],membership=member,lost_original_accepted_IDs=lost,
        final_log_precision_change=c.get('final_log_precision_change'),Gamma_updated=kind=='ordinary_VI',GPS_used=False)
    save(Path(d['case'])/kind/method/arm/'raw_endpoint.json',raw)
    row=dict(case=d['case'],arm=arm,kind=kind,method=method,status='complete',endpoint_east_north_km=x,
        objective=c['negative_twice_elbo'],conditional_RMS_hz=record['RMS_hz'],single_arm_valid=gate,Gamma_converged=bool(gamma),
        final_phase_change_s=change,maximum_unclipped_phase_s=float(np.max(abs(record['state']['phases']))),
        postfit_IDs_lost=len(lost),all_original_accepted_IDs_preserved=not lost,
        associated_IDs=member['associated'],likelihood_points=member['likelihood_points'],
        original_endpoint_difference_km=float(np.linalg.norm(x-baseline['source_endpoint'])) if method=='original' else None,
        original_objective_difference=float(c['negative_twice_elbo']-baseline['source_objective']) if method=='original' and kind=='ordinary_VI' else None,
        seconds=time.monotonic()-started,GPS_used=False)
    save(Path(d['case'])/kind/method/(arm+'_result.json'),row)
    print(d['case'],kind,method,arm,'complete',flush=True)
    return row


def case_job(case):
    began=time.monotonic();deadline=began+145.;rows=[]
    try:
        alarm(deadline-time.monotonic());d=r.context(case)
        corrections=[r for r in load(HERE/'corrections.json')['rows'] if r['case']==case]
        updated,receipt=replacement.inject(d,corrections,[r['native_observation_id'] for r in corrections])
        save(Path(case)/'injection.json',receipt)
        controls={(v['case'],v['arm']):v for v in load(OUT/'preparation.json')['controls']}
        packets=load(OUT/'packets.json')
        for kind in ('ordinary_VI','fixed_original_full_precision_packet'):
            for method in ('original','refined'):
                for arm in ('c0','fitted_c'):
                    try:
                        row=solve(d if method=='original' else updated,arm,kind,method,packets[case+'_'+arm],controls[(case,arm)],deadline)
                    except Exception as exc:
                        row=dict(case=case,kind=kind,method=method,arm=arm,status='failed',error=repr(exc),traceback=traceback.format_exc(),GPS_used=False)
                        save(Path(case)/kind/method/(arm+'_result.json'),row)
                    finally:
                        signal.setitimer(signal.ITIMER_REAL,0)
                    rows.append(row)
    except Exception as exc:
        save(Path(case)/'failure.json',dict(error=repr(exc),traceback=traceback.format_exc()))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
    return dict(case=case,rows=rows,seconds=time.monotonic()-began,GPS_used=False)


def run():
    for path,digest in load(OUT/'protocol.json')['files'].items():
        assert sha(path)==digest,'frozen inference source changed '+path
    seal=load(HERE/'RF_seal.json')
    for path,digest in seal['files'].items():
        assert sha(path)==digest,'RF sealed file changed '+path
    assert seal['coverage_complete'],'complete available-owner correction required'
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        assert os.environ.get(key)=='1'
    save(Path('launch.json'),dict(protocol_sha256=sha(OUT/'protocol.json'),RF_seal_sha256=sha(HERE/'RF_seal.json'),GPS_used=False))
    with ProcessPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(case_job,load(OUT/'protocol.json')['cases']))
    save(Path('execution.json'),dict(results=results,cumulative_worker_seconds=sum(x['seconds'] for x in results),GPS_used=False))
    files={str(p):sha(p) for p in OUT.rglob('*.json') if p.name!='RF_seal.json'}
    save(Path('RF_seal.json'),dict(files=files,GPS_used=False))
    print('INFERENCE_SEALED',sha(OUT/'RF_seal.json'),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'));args=parser.parse_args()
    freeze() if args.action=='freeze' else run()
