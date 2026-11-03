"""Matched phase-initialization basin tests on unchanged original DS23 evidence."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_RF_phase_seeds import seed_vectors
from ds23_frequency_events import make_event_problem,attach_event_predictive
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached,summary
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha

PARENT=ROOT/'reports/2026_10_22_ds23_exact_differential_phase'
OUT=PARENT/'phase_initialization'
SEEDS=['prior_mean','negative_prior_mean','RF_median','RF_consensus']


def prepare():
    OUT.mkdir(exist_ok=True);source=read(PARENT/'refined/execution.json');assert source['all_terminal']
    cases=sorted({r['case'] for r in source['rows'] if r['status']=='complete'})
    protocol=dict(cases=cases,seeds=SEEDS,source_sha256=sha(PARENT/'refined/execution.json'),
        local_nomination_gap=2*np.log(20),consensus_groups_at_least=2,consensus_MAD_s_at_most=.25,
        only_regional_centre_RF_phase_proposals_used=True,original_satellite_labels_masks_and_aliases_unchanged=True,
        original_phase_radio_orbit_fragment_noise_priors_unchanged=True,no_new_likelihood_observations=True,
        all_position_starts=[0,0],regional_width_km=25,phase_rounds=5,steps_per_round=48,
        matched_c0_fitted_c=True,per_pair_seconds=180,workers=12,
        virtual_policy_budget='three starts each: zero+prior_mean+negative_prior_mean versus zero+prior_mean+one RF seed',
        branch_selection='same branch in both c arms, passing original gates and phase change<=.01s; improve both normalized losses',
        no_GPS_future_TLE_new_RF_or_identity_adoption=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_RF_phase_seeds.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('phase-initialization protocol changed')
    if not path.exists():write(path,protocol)
    for case in cases:
        path=OUT/(case+'_seeds.json')
        if path.exists():continue
        scan,node,mask,powers,means,hyper,entries,signed,binding=context_signed(case)
        base=make_event_problem(scan,node,mask,'c0',np.zeros(len(means)),powers,means,hyper,[])
        groups=[r for r in source['rows'] if r.get('case')==case and r['status']=='complete']
        seeds=seed_vectors(base.labels,means,groups)
        write(path,dict(case=case,labels=base.labels,seeds=seeds,signed_sha256=sha(binding)))
    return protocol


def one(case,name):
    path=OUT/(case+'_'+name+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s phase-initialization pair cap')));signal.alarm(180)
    try:
        scan,node,mask,powers,means,hyper,entries,signed,binding=context_signed(case)
        plan=read(OUT/(case+'_seeds.json'));assert sha(binding)==plan['signed_sha256']
        initial=np.asarray(plan['seeds'][name]);arms={};replay={}
        if not np.any(initial):
            result=dict(case=case,seed=name,status='exact_zero_seed_fallback',arms=signed['policy_arms'],paired_valid=True,
                phase_converged=True,no_new_observations_priors_or_identity=True)
        else:
            for arm,old in signed['policy_arms'].items():
                p=make_event_problem(scan,node,mask,arm,np.asarray(old['phase_reference']),powers,means,hyper,[])
                attach_event_predictive(p,entries,powers)
                delta=p.calculate(np.asarray(old['endpoint_east_north_km']))['negative_twice_elbo']-old['negative_twice_elbo']
                assert abs(delta)<1e-6;replay[arm]=delta
                x=np.zeros(2);reference=initial.copy();history=[]
                for _ in range(5):
                    p=make_event_problem(scan,node,mask,arm,reference,powers,means,hyper,[])
                    attach_event_predictive(p,entries,powers);cached(p)
                    fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
                    phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                    history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
                r=summary(p,x,entries);r.update(history=history,final_phase_change_s=history[-1]['phase_change_s']);arms[arm]=r
            result=dict(case=case,seed=name,status='complete',arms=arms,paired_valid=bool(valid(arms)),
                phase_converged=all(r['final_phase_change_s']<=.01 for r in arms.values()),
                incumbent_replay=replay,signed_sha256=sha(binding),initial_phase_s=initial,
                no_new_observations_priors_or_identity=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,seed=name,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(case,name,result['status'],result.get('paired_valid'),result.get('phase_converged'),result.get('error'),flush=True);return result


def main():
    protocol=prepare()
    with ProcessPoolExecutor(max_workers=12) as pool:rows=[f.result() for f in as_completed([pool.submit(one,c,s) for c in protocol['cases'] for s in SEEDS])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,no_position_accuracy_evaluation_yet=True))


if __name__=='__main__':main()
