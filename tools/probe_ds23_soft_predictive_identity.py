"""RF-only diagnostics and cold regional soft-identity position prototypes."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import random
import signal
import time
import numpy as np

from ds23_soft_predictive_identity import attach_soft_identities
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from investigate_dsx01_localization_failures import fit
from run_ds23_combined_recovery_full import valid
from run_ds23_reentry_family_cavity_full import selected_with_recorded_reference
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_22_ds23_soft_predictive_identity'
ENGINEERING=['DS23-0268','DS23-0405','DS23-0080','DS23-0240']
ARMS=['c0','fitted_c']


def prepare():
    path=OUT/'protocol.json'
    if path.exists():return read(path)
    previous=read(ROOT/'reports/2026_10_22_ds23_reentry_family_cavity/full_DS23/protocol.json')
    candidates=sorted(set(previous['cases'])-set(previous['pilot_cases_reused_exactly']))
    cohort=sorted(random.Random(2026102218).sample(candidates,20))
    document=dict(engineering=ENGINEERING,random20=cohort,seed=2026102218,
        cohort_frozen_before_any_new_inference_or_geographic_evaluation=True,
        baseline='Previous published conditional-family method; negative coherent-recovery hybrid not adopted',
        hypothesis='Predictive linear identity uncertainty may reduce biased position pull from hard labels',
        labels='all RF-inferred curved-supported labels plus every incumbent predictive label; no fixed satellite whitelist',
        full_catalogue_curved_search_unchanged=True,not_a_full_catalogue_predictive_reassociation=True,
        candidate_aliases='original track aliases held fixed for every candidate',
        identity_prior='uniform among offered identities for each unchanged predictive track',
        variational='q(shared standardized calibration latent) times independent track identity factors; original 300 Hz biases integrated exactly',
        same_curved_posterior_calibration_means_and_Gamma_precisions=True,
        cold_start=[0,0],regional_width_km=25,regional_center=[37.906,-122.545],phase_rounds=5,position_iterations=48,
        EM_maximum_iterations=80,EM_weight_tolerance=1e-7,per_case_seconds=600,
        paired_c0_fitted_c=True,unchanged_physical_priors_points_and_residual_gates=True,
        primary_policy='use the soft-identity model only if both arms pass all original curved/MAP predictive gates and phase/EM convergence; otherwise exact incumbent',
        sensitivity_policy='also require lower normalized c0 bound than incumbent',
        GPS_used_for_inference_or_selection=False,new_RF_or_future_TLE_used=False,
        same_site_previously_studied_not_untouched_or_new_location_validation=True,
        literature='https://www.cs.columbia.edu/~blei/papers/BleiKucukelbirMcAuliffe2017.pdf',
        source_sha256={name:sha(ROOT/'tools'/name) for name in ['ds23_soft_predictive_identity.py','probe_ds23_soft_predictive_identity.py']})
    write(path,document);return document


def setup(case):
    d,arms=selected_with_recorded_reference(case)
    d['incumbent_arms']=arms
    for element in d['scan'].elements.values():
        provenance=element['provenance'];assert max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])<=d['scan'].receipt['cutoff_utc_ns']
    return d


def problem(d,arm,reference,kind):
    p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(reference),d['powers'],d['means'],d['model'],[])
    if kind=='old':attach_event_predictive(p,d['entries'],d['powers'])
    else:attach_soft_identities(p,d['entries'],d['powers'],fixed=kind=='fixed')
    return cached(p)


def diagnostic(case):
    d=setup(case);rows=[]
    for arm,saved in d['incumbent_arms'].items():
        x=np.asarray(saved['endpoint_east_north_km']);reference=saved['phase_reference'];records={}
        for kind in ['old','fixed','soft']:
            p=problem(d,arm,reference,kind);begin=time.monotonic();c=p.calculate(x)
            records[kind]=dict(negative_twice_elbo=c['negative_twice_elbo'],seconds=time.monotonic()-begin,
                coefficient=c['coefficient'],noise_precision=c['noise_precision'])
            if kind!='old' and d['entries']:
                result=c['soft_identity'];weights=result['weights']
                records[kind].update(converged=result['converged'],EM_iterations=result['iterations'],EM_weight_change=result['final_weight_change'],
                    entropies=[float(-np.sum(w[w>0]*np.log(w[w>0]))) for w in weights],
                    weights=weights,candidates=c['identity_candidates'],MAP_entries=c['MAP_linear_entries'],
                    changed_MAP_components=[e['component'] for e,old in zip(c['MAP_linear_entries'],d['entries'],strict=True) if e['candidate_index']!=old['candidate_index']])
        delta=records['fixed']['negative_twice_elbo']-records['old']['negative_twice_elbo']
        assert abs(delta)<2e-5
        assert np.array_equal(records['old']['coefficient'],records['soft']['coefficient'])
        assert np.array_equal(records['old']['noise_precision'],records['soft']['noise_precision'])
        for record in records.values():record.pop('coefficient');record.pop('noise_precision')
        rows.append(dict(arm=arm,records=records,fixed_identity_likelihood_difference=delta,
            curved_calibration_identical=True,predictive_tracks=len(d['entries']),predictive_points=sum(e['points'] for e in d['entries'])))
    return dict(case=case,rows=rows,no_GPS_used=True)


def refit(d,arm):
    x=np.zeros(2);reference=np.zeros(len(d['means']));history=[]
    for _ in range(5):
        p=problem(d,arm,reference,'soft');result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(np.max(abs(next_phase-reference)))));reference=next_phase
    c=p.calculate(x);entries=c.get('MAP_linear_entries',d['entries']);record=summary(p,x,entries)
    record.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],MAP_entries=entries)
    if d['entries']:
        soft=c['soft_identity'];weights=soft['weights']
        record.update(identity_weights=weights,identity_candidates=c['identity_candidates'],EM_iterations=soft['iterations'],
            EM_weight_change=soft['final_weight_change'],EM_converged=soft['converged'],EM_objective_history=soft['history'],
            identity_entropies=[float(-np.sum(w[w>0]*np.log(w[w>0]))) for w in weights])
    else:record['EM_converged']=True
    return record


def run(case,stage):
    path=OUT/stage/(case+'.json')
    if path.exists():return read(path)
    start=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600s soft identity case cap')));signal.alarm(600)
    try:
        if stage=='diagnostic':result=diagnostic(case)
        else:
            d=setup(case);pair={arm:refit(d,arm) for arm in ARMS}
            accepted=bool(valid(pair) and all(r['final_phase_change_s']<=.01 and r['EM_converged'] for r in pair.values()))
            gain=d['incumbent_arms']['c0']['negative_twice_elbo']-pair['c0']['negative_twice_elbo']
            result=dict(case=case,arms=pair,incumbent_arms=d['incumbent_arms'],paired_valid=accepted,
                policy_arms=pair if accepted else d['incumbent_arms'],c0_normalized_RF_gain=gain,
                lower_bound_policy_accepted=accepted and gain>0,
                mask=d['keep'],entries=d['entries'],powers=d['powers'],means=d['means'],hyper=d['model'],node=d['node'])
        result.update(status='complete',seconds=time.monotonic()-start,reference_position_used=False,
            protocol_sha256=sha(OUT/'protocol.json'))
    except Exception as exc:
        import traceback
        result=dict(case=case,status='failed',error=repr(exc),traceback=traceback.format_exc(),seconds=time.monotonic()-start)
    finally:signal.alarm(0)
    write(path,result);print(case,stage,result['status'],round(result['seconds'],2),flush=True);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['diagnostic','positions'],required=True)
    parser.add_argument('--cohort',choices=['engineering','random20'],default='engineering');parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();OUT.mkdir(exist_ok=True);protocol=prepare();(OUT/args.stage).mkdir(exist_ok=True)
    if not 1<=args.workers<=30:raise ValueError('1 to 30 workers required')
    rows=[];cases=protocol[args.cohort]
    with ProcessPoolExecutor(max_workers=min(args.workers,len(cases))) as pool:
        for future in as_completed([pool.submit(run,c,args.stage) for c in cases]):
            rows.append(future.result());write(OUT/(args.cohort+'_'+args.stage+'_progress.json'),dict(completed=len(rows),total=len(cases),rows=rows))
    write(OUT/(args.cohort+'_'+args.stage+'_execution.json'),dict(rows=rows,all_terminal=True,all_passed=all(r['status']=='complete' for r in rows),no_geographic_evaluation_yet=True))


if __name__=='__main__':main()
