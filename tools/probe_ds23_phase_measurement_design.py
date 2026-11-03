"""Bounded diagnostic: how many independent timing measurements are needed?

Hypothetical measurements are simulated from frozen synthetic phase truths.
They are never applied to real DS23 observations or called an accuracy gain.
The satellite selection is fixed using real RF geometry before truth is read.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_phase_measurement_design import local_design,choose_labels,make_phase_measured_problem,attach_phase_measured_predictive
from ds23_frequency_events import make_event_problem
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached,summary,parameters
from probe_ds23_synthetic_known_nuisance import setup,SOURCE
from probe_ds23_synthetic_noise import gate_counts
from run_ds23_combined_recovery_full import context,ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_phase_measurement_design'
BULK=Path('/srv/bulk/leo/research/ds23-phase-measurement-design-20261021')
VARIANTS={f'information_{k}_sd{s}':dict(method='information',budget=k,sigma_s=s)
          for k,s in [(1,.1),(3,.1),(6,.1),(3,.3),(3,1.)]}
VARIANTS.update(point_count_3_sd01=dict(method='point_count',budget=3,sigma_s=.1),
                random_3_sd01=dict(method='random',budget=3,sigma_s=.1),
                information_all_sd01=dict(method='information',budget=10000,sigma_s=.1))


def prepare():
    old=read(ROOT/'reports/2026_10_20_ds23_synthetic_known_nuisance/protocol.json')
    protocol=dict(cases=old['cases'],pilot_cases=old['cases'][:3],site_by_case=old['site_by_case'],variants=VARIANTS,
        source_simulation_protocol_sha256=sha(SOURCE/'protocol.json'),
        measurements='true simulated phase plus independent Gaussian noise; not measured on real IQ',
        design='greedy local curved-only position covariance reduction at original real RF c0 endpoint',
        design_has_no_synthetic_phase_truth_position_or_simulation_outcome=True,
        conditional_on_Gamma_precisions_and_existing_identities=True,
        original_Student_phase_and_radio_priors_observations_masks_aliases_and_noise_preserved=True,
        same_independent_measurement_standard_normal_draw_per_label_across_variants=True,
        predictive_linear_never_calibrates=True,matched_c0_fitted_c=True,regional_width_km=25,cold_start=[0,0],
        phase_rounds=5,position_steps=48,workers=8,per_case_seconds=300,
        real_DS23_accuracy_gain=False,no_real_GPS_or_postscan_TLE_or_new_RF_collection=True,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'ds23_phase_measurement_design.py','ds23_gaussian_information.py']})
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);p=OUT/'protocol.json'
    if p.exists() and read(p)!=protocol:raise ValueError('phase measurement diagnostic protocol changed')
    if not p.exists():write(p,protocol)
    return protocol


def plan(case):
    pth=BULK/(case+'_design.json')
    if pth.exists():return read(pth)
    scan,node,mask,base,old=context(case);powers,means,hyper=parameters(scan,base,old)
    saved=old['policy_arms']['c0']
    p=make_event_problem(scan,node,mask,'c0',np.asarray(saved['phase_reference']),powers,means,hyper,[])
    p.design_powers=powers
    design=local_design(p,np.asarray(saved['endpoint_east_north_km']))
    variants={name:choose_labels(design,v['sigma_s'],v['budget'],v['method'],831017+int(case.split('-')[1])) for name,v in VARIANTS.items()}
    result=dict(case=case,design=design,variants=variants,labels=p.labels,
        norads=[int(scan.norads[j]) for j in p.labels],real_RF_endpoint=saved['endpoint_east_north_km'],
        no_truth_or_simulation_outcome_used=True)
    write(pth,result);return result


def refit(scan,node,mask,arm,powers,means,hyper,entries,measurements):
    x=np.zeros(2);reference=np.zeros(len(means));history=[]
    for _ in range(5):
        p=make_phase_measured_problem(scan,node,mask,arm,reference,powers,means,hyper,measurements)
        attach_phase_measured_predictive(p,entries,powers);cached(p)
        fitted=fit(p,x,iterations=48);x=np.array(fitted['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))))
        reference=phase
    r=summary(p,x,entries);r.update(history=history,final_phase_change_s=history[-1]['phase_change_s'])
    r['independent_phase_residual_s']=p.calculate(x)['phase_measurement_residual_s']
    return r


def one(case):
    protocol=read(OUT/'protocol.json');began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300second phase measurement design cap')))
    signal.alarm(300);results=[]
    try:
        selected=plan(case)  # Must be persisted before generating/reading truth.
        scan,node,mask,powers,means,hyper,entries,truth,baseline=setup(case,protocol['site_by_case'][case])
        replay={}
        for arm,r in baseline['arms'].items():
            p=make_phase_measured_problem(scan,node,mask,arm,np.array(r['phase_reference']),powers,means,hyper,[])
            attach_phase_measured_predictive(p,entries,powers)
            delta=p.calculate(np.array(r['endpoint_east_north_km']))['negative_twice_elbo']-r['negative_twice_elbo']
            assert abs(delta)<1e-6;replay[arm]=delta
        rng=np.random.default_rng(194819+int(case.split('-')[1]));noise=rng.normal(size=len(means))
        for name,v in VARIANTS.items():
            pth=BULK/(case+'_'+name+'.json')
            if pth.exists():results.append(read(pth));continue
            ids=selected['variants'][name]['label_indices']
            measurements=[dict(candidate_index=selected['labels'][k],norad=selected['norads'][k],
                phase_s=truth['true_phases_s'][k]+v['sigma_s']*noise[k],sigma_s=v['sigma_s']) for k in ids]
            arms={a:refit(scan,node,mask,a,powers,means,hyper,entries,measurements) for a in ARMS}
            for r in arms.values():
                r['synthetic_position_error_km']=float(np.linalg.norm(np.array(r['endpoint_east_north_km'])-protocol['site_by_case'][case]))
                r['original_gate_counts']=gate_counts(r)
                assert r['linear_calibration_max_difference']==0
            result=dict(case=case,variant=name,status='complete',arms=arms,paired_qualified=valid(arms),
                measurements=measurements,design_sha256=sha(BULK/(case+'_design.json')),
                baseline_identity_control=replay,synthetic_baseline_sha256=sha(SOURCE/(case+'_draw0_all.json')),
                synthetic_not_real_position_gain=True)
            write(pth,result);results.append(result)
            print(case,name,result['paired_qualified'],{a:r['synthetic_position_error_km'] for a,r in arms.items()},flush=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();write(BULK/(case+'_execution_failure.json'),dict(case=case,status='failed',error=repr(exc)))
    finally:signal.alarm(0)
    return dict(case=case,completed=len(results),total=len(VARIANTS),seconds=time.monotonic()-began)


def evaluate(cases):
    summary={};failures=[]
    for name in ['baseline',*VARIANTS]:
        rows=[]
        for case in cases:
            path=SOURCE/(case+'_draw0_all.json') if name=='baseline' else BULK/(case+'_'+name+'.json')
            if path.exists():rows.append(read(path))
            else:failures.append(dict(case=case,variant=name))
        summary[name]={}
        for arm in ARMS:
            errors=[r['arms'][arm]['synthetic_position_error_km'] for r in rows]
            summary[name][arm]=dict(n=len(errors),mean_km=float(np.mean(errors)) if errors else None,
                median_km=float(np.median(errors)) if errors else None,
                paired_qualified=sum(valid(r['arms']) for r in rows),
                original_gates_pass=sum(gate_counts(r['arms'][arm])['all_original_gates_pass'] for r in rows))
    return dict(cases=cases,summary=summary,missing_instances=failures,real_DS23_accuracy_gain=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['pilot','full'],default='pilot')
    args=parser.parse_args();protocol=prepare();cases=protocol['pilot_cases'] if args.stage=='pilot' else protocol['cases']
    with ProcessPoolExecutor(max_workers=min(8,len(cases))) as pool:
        execution=[f.result() for f in as_completed([pool.submit(one,c) for c in cases])]
    write(OUT/(args.stage+'_evaluation.json'),dict(evaluate(cases),execution=execution,all_terminal=True))


if __name__=='__main__':main()
