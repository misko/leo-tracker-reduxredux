"""Bounded synthetic comparison of marginal-score mode and spatial mean.

Uses original causal priors and identical RF evidence. Fractional likelihoods
and variational bounds define a score measure, not calibrated probabilities.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
import signal
import time
import numpy as np

from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_spatial_score_integration import local_covariance, score_integral
from probe_ds23_frequency_events import cached, summary
from probe_ds23_synthetic_known_nuisance import setup, OUT as KNOWN, SOURCE, prepare_protocol
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT=ROOT/'reports/2026_10_20_ds23_spatial_score_mean'


def run(case, site):
    path=OUT/(case+'.json')
    if path.exists(): return read(path)
    began=time.monotonic(); results={}
    def timeout(*_): raise TimeoutError('180 second spatial integration pilot budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(180)
    try:
        scan,node,mask,powers,means,hyper,entries,truth,baseline=setup(case,site)
        for arm in ARMS:
            old=baseline['arms'][arm]; anchor=np.asarray(old['endpoint_east_north_km'])
            @lru_cache(maxsize=512)
            def fixed(point):
                x=np.asarray(point); reference=np.asarray(old['phase_reference']); change=np.inf
                for epoch in range(5):
                    p=make_event_problem(scan,node,mask,arm,reference,powers,means,hyper,[])
                    attach_event_predictive(p,entries,powers); cached(p)
                    c=p.calculate(x); phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                    change=float(np.max(abs(phase-reference))); reference=phase
                    if epoch>=1 and change<1e-5: break
                if change>.01: raise ValueError('fixed-position phase refresh did not converge')
                score=float(c['negative_twice_elbo']+np.sum((np.minimum(c['elevation'],0)/2)**2))
                return score,p,change
            score=lambda x: fixed(tuple(x))[0]
            control_delta=score(anchor)-old['negative_twice_elbo']
            if abs(control_delta)>.01: raise ValueError('fixed-position likelihood does not reproduce mode')
            covariance=local_covariance(score,anchor)
            coarse=score_integral(score,anchor,covariance,5)
            fine=score_integral(score,anchor,covariance,9)
            change=float(np.linalg.norm(fine['mean']-coarse['mean']))
            mass_change=float(abs(fine['log_relative_mass']-coarse['log_relative_mass']))
            qualified=change<=.025 and mass_change<=.01 and fine['outer_ring_mass']<.01
            endpoint=fine['mean']; _,p,phase_change=fixed(tuple(endpoint))
            r=summary(p,endpoint,entries); r['final_phase_change_s']=phase_change
            r['synthetic_position_error_km']=float(np.linalg.norm(endpoint-site))
            results[arm]=dict(mean_arm=r,baseline_error_km=old['synthetic_position_error_km'],
                numerically_qualified=qualified,mean_change_km=change,log_mass_change=mass_change,
                baseline_objective_difference=control_delta,local_covariance_km2=covariance,
                coarse=coarse,fine=fine,evaluated_positions=fixed.cache_info().misses)
        accepted=all(v['numerically_qualified'] for v in results.values()) and valid({a:v['mean_arm'] for a,v in results.items()})
        record=dict(case=case,status='complete',arms=results,paired_accepted=accepted,
            synthetic_site_east_north_km=site,real_GPS_used=False,
            same_causal_priors_masks_labels_aliases_noise_and_fractional_powers=True,
            generalized_score_measure_not_calibrated_posterior=True,real_DS23_accuracy_gain=False)
    except Exception as exc:
        record=dict(case=case,status='failed',error=repr(exc),arms=results)
    finally: signal.alarm(0)
    record['seconds']=time.monotonic()-began; write(path,record)
    print(case,record['status'],record.get('error'),{a:(v['mean_arm']['synthetic_position_error_km'],v['numerically_qualified'],v['mean_change_km'],v['log_mass_change']) for a,v in results.items()},flush=True)
    return record


def main():
    previous=prepare_protocol(); cases=previous['cases'][:2]
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(cases=cases,source_protocol_sha256=sha(KNOWN/'protocol.json'),
        orders=[5,9],mean_convergence_km=.025,log_mass_convergence=.01,maximum_outer_ring_mass=.01,
        regional_half_width_km=12.5,curvature_step_km=.1,workers=2,per_case_seconds=180,
        same_physical_priors_and_RF_evidence=True,synthetic_only=True,
        numerical_qualification_chosen_without_geographic_errors=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_spatial_score_integration.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol: raise ValueError('spatial pilot protocol changed')
    if not target.exists(): write(target,protocol)
    with ProcessPoolExecutor(max_workers=2) as pool:
        rows=[f.result() for f in as_completed([pool.submit(run,c,previous['site_by_case'][c]) for c in cases])]
    write(OUT/'evaluation.json',dict(rows=rows,protocol_sha256=sha(target),
        real_DS23_accuracy_gain=False,completed=sum(r['status']=='complete' for r in rows)))


if __name__=='__main__': main()
