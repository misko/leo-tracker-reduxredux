"""Qualify mean-only phase forecasts using fully pre-scan historical references."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_historical_phase_consensus import build_rows,temporal_split,fit_mean,cost,panel_diagnostics
from ds23_causal_phase_location import fit_location
from learn_ds23_causal_phase_forecast import select_distribution
from run_ds23_combined_recovery_full import OUT as COMBINED
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_historical_phase_consensus'
BULK=Path('/srv/bulk/leo/research/ds23-historical-phase-consensus-20261021')
COHORT=ROOT/'reports/2026_10_20_ds23_excluded_catalogue/calibration_protocol.json'
PILOTS=read(COHORT)['pilot_cases']
SPLIT_DESCRIPTION='70percent distinct last-reference publication times; training labels available by boundary; validation issue times strictly after boundary'


def one(case):
    path=BULK/(case+'.json')
    if path.exists():return read(path)
    began=time.monotonic()
    def timeout(*_):raise TimeoutError('120second causal historical consensus qualification cap')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    try:
        root=Path(read(COMBINED/'protocol.json')['input_roots'][case])
        hp=root/'causal_phase_history'/(case+'.json');fp=hp.with_name(case+'_forecast.json')
        history,forecast=read(hp),read(fp)
        if forecast['history_sha256']!=sha(hp):raise ValueError('historical forecast binding changed')
        rows,rejected=build_rows(history);split=temporal_split(rows,history['cutoff_utc_ns'])
        training,future,disjoint=[split[k] for k in ['training','future','disjoint_future']]
        original_training=[r for r in forecast['transitions'] if r['validation_time_ns']<=split['boundary_ns'] and r['norad']%5!=0]
        selection=dict(qualified=False,counts=dict(consensus_rows=len(rows),training=len(training),
            future_issue_and_label=len(future),satellite_disjoint_future=len(disjoint),original_training=len(original_training)),
            boundary_ns=split['boundary_ns'],boundary_selection=split.get('boundary_selection'),rejected=rejected)
        if min(map(len,[training,future,disjoint,original_training]))<30:
            selection['reason']='insufficient strictly chronological historical reference support'
        else:
            prefix=select_distribution(original_training)
            old_location=fit_location(original_training,prefix)
            incumbent=dict(shrinkage=prefix['shrinkage'],kind=old_location['kind'],coefficient=old_location['coefficient'])
            control=fit_mean(training,prefix,'next_innovation_s')
            consensus=fit_mean(training,prefix,'consensus_phase_s')
            validation={}
            for name,part in [('future',future),('disjoint_future',disjoint)]:
                targets={}
                for target in ['consensus_phase_s','panel_a_phase_s','panel_b_phase_s']:
                    candidate=cost(part,prefix,consensus,target)
                    controls=dict(incumbent_prefix=cost(part,prefix,incumbent,target),
                        matched_next_revision=cost(part,prefix,control,target))
                    targets[target]=dict(candidate_cost=candidate,control_costs=controls,
                        gains={k:value-candidate for k,value in controls.items()})
                penalty=float(2*np.log(len(part))+2*np.log(25))
                reference=panel_diagnostics(part,prefix)
                qualified=bool(min(targets['consensus_phase_s']['gains'].values())>penalty
                    and all(min(targets[k]['gains'].values())>0 for k in ['panel_a_phase_s','panel_b_phase_s'])
                    and reference['agreement_qualified'])
                validation[name]=dict(targets=targets,penalty=penalty,reference_agreement=reference,qualified=qualified)
            qualified=all(v['qualified'] for v in validation.values())
            full_model=read(root/case/'algo02_result.json')['hyperparameters_from_pre_RF_TLE_only']
            final={}
            if qualified:
                final=dict(consensus=fit_mean(rows,full_model,'consensus_phase_s',kinds=(consensus['kind'],)),
                    matched_next_revision=fit_mean(rows,full_model,'next_innovation_s',kinds=(control['kind'],)))
            selection.update(qualified=qualified,prefix_distribution=prefix,incumbent_prefix_mean=incumbent,
                matched_next_revision_mean=control,consensus_mean=consensus,validation=validation,final_mean_models=final,
                original_full_distribution=full_model,prior_variance_and_tail_degrees_unchanged=True)
        result=dict(case=case,status='complete',selection=selection,rows=rows,
            history_path=str(hp),history_sha256=sha(hp),forecast_path=str(fp),forecast_sha256=sha(fp),
            cutoff_utc_ns=history['cutoff_utc_ns'],origin_utc_ns=history['origin_utc_ns'],
            labels_available_only_after_last_reference=True,validation_forecast_issues_strictly_after_training_boundary=True,
            all_current_scan_TLE_epochs_and_collections_precede_cutoff=True,
            later_revisions_are_of_old_historical_events_only=True,
            no_RF_GPS_satellite_nominations_or_current_post_scan_TLE_used=True,
            historical_consensus_and_panels_are_not_independent_orbit_truth=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(case,result['status'],result.get('selection',{}).get('qualified'),
        result.get('selection',{}).get('counts'),result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    cases=['DS23-0268','DS23-0405']+PILOTS
    protocol=dict(cases=cases,engineering=cases[:2],preexisting_random_pilots=PILOTS,
        cohort_sha256=sha(COHORT),mean_only=True,current_phase_variance_tail_degrees_and_other_priors_fixed=True,
        references='three successive historical TLEs propagated to first reference publication; median phase target',
        panels='first-and-third mean versus second reference; distinct revisions, correlated errors possible',
        temporal_split=SPLIT_DESCRIPTION,
        satellite_split='NORAD divisible by5 excluded from all prefix distribution and mean fitting',
        controls=['incumbent-style prefix next-revision mean','matched next-revision mean with same training rows and mean class'],
        mean_class='shrinkage grid0,.25,.5,.75,1 plus optional one signed feature; BIC-style complexity penalty',
        qualification='in later-time and satellite-disjoint later-time partitions, consensus target beats both controls by2logN+2log25; both reference panels improve; median panel disagreement<1fixed phase SD',
        minimum_rows_each_partition=30,workers=5,per_case_seconds=120,
        historical_labels_not_orbit_truth=True,no_GPS_RF_new_collection_or_current_post_scan_TLE_used=True,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'ds23_historical_phase_consensus.py',
            'learn_ds23_causal_phase_forecast.py','ds23_causal_phase_location.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen historical consensus mean experiment changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=5) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,c) for c in cases])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,protocol_sha256=sha(path),
        no_position_estimate_changed=True))


if __name__=='__main__':main()
