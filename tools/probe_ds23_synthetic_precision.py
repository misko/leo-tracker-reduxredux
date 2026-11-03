"""Measure whether better CFO precision can identify phase and position.

Correct identities are known by construction; nonzero physical nuisance draws
and causal phase priors are unchanged. This does not claim real RF precision.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_synthetic_precision import measurement_noise,add_noise,make_precision_control
from ds23_synthetic_phase_law import bounded_phase_draw
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import parameters,cached,summary
from probe_ds23_synthetic_noise import gate_counts
import probe_ds23_synthetic_nuisance_components as component
from probe_ds23_synthetic_known_nuisance import prepare_protocol,SOURCE
from run_ds23_combined_recovery_full import context,ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_synthetic_precision'
FRACTIONS=(1.,.25,.1,.025)


def setup(case,site,fraction):
    scan,node,mask,base,old=context(case);powers,means,hyper=parameters(scan,base,old)
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    component.SITE=tuple(site);component.bounded_phase_draw=bounded_phase_draw
    synthetic,copied,predictive,truth=component.synthesize(scan,node,mask,base,powers,means,hyper,entries,'all',0)
    members=set(base.members)|{e['track_index'] for e in predictive}
    sigma,noise=measurement_noise(synthetic,members,fraction,194729+int(case.split('-')[1]))
    add_noise(synthetic,members,noise)
    original=read(SOURCE/(case+'_draw0_all.json'))
    np.testing.assert_array_equal(truth['true_phases_s'],original['generation_truth']['true_phases_s'])
    np.testing.assert_array_equal(truth['selected_coefficients'],original['generation_truth']['selected_coefficients'])
    return synthetic,copied,mask,powers,means,hyper,predictive,truth,sigma,original


def refit(scan,node,mask,arm,powers,means,hyper,entries,sigma):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=make_precision_control(scan,node,mask,arm,reference,powers,means,hyper,entries,sigma);cached(p)
        fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))))
        reference=phase
    result=summary(p,x,entries)
    result.update(history=history,final_phase_change_s=history[-1]['phase_change_s'])
    return result


def run(case,site,fraction):
    path=OUT/(case+'_fraction'+str(fraction)+'.json')
    if path.exists():return read(path)
    began=time.monotonic()
    def timeout(*_):raise TimeoutError('120 second measurement-precision simulation budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    record=dict(case=case,fraction=fraction,synthetic_site_east_north_km=site,
        real_GPS_used=False,oracle_labels_only_no_known_nuisance_priors=True)
    try:
        scan,node,mask,powers,means,hyper,entries,truth,sigma,baseline=setup(case,site,fraction)
        if fraction==1.:
            pair=baseline['arms']; differences={}
            for arm in ARMS:
                old=pair[arm];p=make_precision_control(scan,node,mask,arm,np.asarray(old['phase_reference']),powers,means,hyper,entries,sigma)
                c=p.calculate(np.asarray(old['endpoint_east_north_km']))
                differences[arm]=float(c['negative_twice_elbo']-old['negative_twice_elbo'])
                if abs(differences[arm])>1e-6:raise ValueError('1Hz reference did not preserve original normalized objective')
            record['baseline_normalized_objective_differences']=differences
        else:
            pair={a:refit(scan,node,mask,a,powers,means,hyper,entries,sigma) for a in ARMS}
            for arm,r in pair.items():
                r['synthetic_position_error_km']=float(np.linalg.norm(np.asarray(r['endpoint_east_north_km'])-site))
                r['original_gate_counts']=gate_counts(r)
        phase_error={a:np.asarray(r['state']['phases'])[sorted({row['candidate_index'] for row in node['seed']['rows']})]-truth['true_phases_s'] for a,r in pair.items()}
        record.update(status='complete',arms=pair,paired_qualified=valid(pair),
            declared_noise_sigma_quantiles_hz=np.quantile(list(sigma.values()),[0,.5,1]),
            phase_error_s=phase_error,matched_true_nuisance_coefficients_and_normal_noise_draws=True,
            persisted_original_noise_contract_unchanged=True)
    except Exception as exc:record.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-began;write(path,record)
    print(case,fraction,record['status'],record.get('error'),{a:(r['synthetic_position_error_km'],gate_counts(r)['all_original_gates_pass']) for a,r in record.get('arms',{}).items()},flush=True)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case');args=parser.parse_args()
    previous=prepare_protocol();cases=previous['cases']
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(cases=cases,site_by_case=previous['site_by_case'],fractions=list(FRACTIONS),
        one_hz_noise_floor=True,nonzero_nuisance_coefficients_and_phase_prior_unchanged=True,
        same_standard_normal_noise_per_physical_ID=True,no_known_phase_or_calibration_means=True,
        same_observations_masks_aliases_powers_and_budgets_in_both_c_arms=True,
        residual_reference='1Hz only a position independent constant; existing research builder, original persisted contract unchanged',
        workers=8,per_case_fraction_seconds=120,phase_rounds=5,position_iterations=48,cold_start_km=[0,0],
        source_simulation_evaluation_sha256=sha(SOURCE/'evaluation.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_synthetic_precision.py',ROOT/'tools/probe_ds23_refined_precision.py']},
        full_hierarchical_prior_predictive=False,synthetic_not_a_real_DS23_accuracy_gain=True)
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('precision simulation protocol changed')
    if not target.exists():write(target,protocol)
    selected=[args.case] if args.case else cases
    if not set(selected).issubset(cases):raise ValueError('case outside predeclared templates')
    with ProcessPoolExecutor(max_workers=min(8,len(selected)*len(FRACTIONS))) as pool:
        jobs=[pool.submit(run,c,protocol['site_by_case'][c],v) for c in selected for v in FRACTIONS]
        for f in as_completed(jobs):f.result()
    evaluation={};pending=[];failures=[]
    for fraction in FRACTIONS:
        rows=[]
        for case in cases:
            path=OUT/(case+'_fraction'+str(fraction)+'.json')
            if not path.exists():pending.append(dict(case=case,fraction=fraction));continue
            r=read(path)
            if r['status']=='complete':rows.append(r)
            else:failures.append(dict(case=case,fraction=fraction,error=r.get('error')))
        evaluation[str(fraction)]={}
        for arm in ARMS:
            errors=[r['arms'][arm]['synthetic_position_error_km'] for r in rows]
            evaluation[str(fraction)][arm]=dict(n=len(errors),mean_km=float(np.mean(errors)) if errors else None,
                median_km=float(np.median(errors)) if errors else None,
                paired_qualified=sum(r['paired_qualified'] for r in rows),
                all_original_gates_pass=sum(gate_counts(r['arms'][arm])['all_original_gates_pass'] for r in rows),
                median_phase_absolute_error_s=float(np.median(np.concatenate([abs(np.asarray(r['phase_error_s'][arm])) for r in rows]))) if rows else None)
    write(OUT/'evaluation.json',dict(summary=evaluation,pending=pending,failures=failures,
        protocol_sha256=sha(target),real_DS23_accuracy_gain=False))
    print('PRECISION_SIMULATION',evaluation,flush=True)


if __name__=='__main__':main()
