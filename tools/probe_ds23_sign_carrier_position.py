"""Paired real-data position interventions from RF-qualified sign carriers.

Inference has no evaluation coordinate. Same original tracks, aliases, masks,
causal priors and cold regional initialization as the signed-prior incumbent.
"""

import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_causal_phase_location import qualify,adjust_means
from ds23_synthetic_precision import make_precision_control
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached,parameters,summary
from run_ds23_combined_recovery_full import context,ARMS,valid,prepare
from run_algo01_ds23_sample import ROOT,read,write,sha
from validate_ds23_sign_aware_carrier import OUT as RF

OUT=ROOT/'reports/2026_10_20_ds23_sign_carrier_position'
SIGNED_AUDIT=ROOT/'reports/2026_10_20_ds23_signed_recoveries/evaluation_audit.json'
METHODS=('continuous_same_points','sign_CFO_only','sign_CFO_and_precision')


def context_signed(case):
    scan,node,mask,base,old=context(case);powers,ordinary,hyper=parameters(scan,base,old)
    binding=read(SIGNED_AUDIT)['evidence'][case];path=ROOT/binding['path']
    if sha(path)!=binding['sha256']:raise ValueError('independently audited signed incumbent changed')
    saved=read(path)
    if saved['baseline_arms']!=old['policy_arms']:raise ValueError('signed incumbent uses different original observations')
    from run_ds23_combined_recovery_full import OUT as COMBINED
    root=Path(read(COMBINED/'protocol.json')['input_roots'][case])
    history_path=root/'causal_phase_history'/(case+'.json');forecast_path=history_path.with_name(case+'_forecast.json')
    history,forecast=read(history_path),read(forecast_path)
    if saved['history_sha256']!=sha(history_path) or saved['forecast_sha256']!=sha(forecast_path):raise ValueError('causal signed history changed')
    cutoff=scan.receipt['cutoff_utc_ns']
    if any(max(v['epoch'],v['collected_utc_ns'])>cutoff for versions in history['past_versions'].values() for v in versions):raise ValueError('noncausal TLE')
    selection=qualify(forecast['transitions'],forecast['temporal_split_boundary_ns'],forecast['prefix_distribution'],hyper)
    if selection!=saved['selection']:raise ValueError('signed historical qualification changed')
    _,receipts=phase_widths(scan,base.labels)
    adjusted=adjust_means(ordinary,receipts,hyper,selection)
    np.testing.assert_allclose(adjusted,saved['means_s'],rtol=0,atol=1e-12)
    means=adjusted if saved['accepted'] else ordinary
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    return scan,node,mask,powers,means,hyper,entries,saved,path


def intervene(scan,rows,method):
    changed=copy.copy(scan);changed.tracks=[dict(t,values=np.asarray(t['values']).copy()) for t in scan.tracks]
    lookup={r['observation_id']:r for r in rows};found=set();overrides={};deltas={}
    from leo.analysis.research.retained_track_likelihood import PERIOD
    for t in changed.tracks:
        for k,oid in enumerate(t['observation_ids']):
            if oid not in lookup:continue
            r=lookup[oid];error=(t['values'][k]-r['archived_CFO_hz']+PERIOD/2)%PERIOD-PERIOD/2
            if abs(error)>1e-6:raise ValueError('RF point differs from canonical original GLRT value')
            new=r['base_fit']['CFO_hz'] if method=='continuous_same_points' else r['proposed_CFO_hz']
            delta=float(new-r['archived_CFO_hz']);t['values'][k]+=delta;found.add(oid);deltas[oid]=delta
            if method=='sign_CFO_and_precision':
                value=r['proposed_noise_sigma_hz']
                if value is None or value<5:raise ValueError('RF precision must satisfy the declared5Hz floor')
                meta=scan.fixed_window_noise
                original=meta['per_observation_noise_sigma_hz'][oid] if meta['extra_parameter_BIC_gain']>0 else scan.radio_sigma_hz
                overrides[oid]=min(float(value),float(original))
    if found!=set(lookup):raise ValueError('RF qualified point missing from original graph')
    return changed,overrides,deltas


def refit(scan,node,mask,arm,powers,means,hyper,entries,overrides):
    x=np.zeros(2);reference=np.zeros(len(means));history=[]
    for _ in range(5):
        p=make_precision_control(scan,node,mask,arm,reference,powers,means,hyper,entries,overrides);cached(p)
        result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(np.max(abs(phase-reference)))))
        reference=phase
    record=summary(p,x,entries);record.update(history=history,final_phase_change_s=history[-1]['phase_change_s'])
    return record


def run(case):
    path=OUT/(case+'.json')
    if path.exists():return read(path)
    began=time.monotonic()
    def timeout(*_):raise TimeoutError('180 second real-data sign carrier position budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(180)
    try:
        scan,node,mask,powers,means,hyper,entries,signed,signed_path=context_signed(case)
        rf=read(RF/'evaluation.json');selected=[r for r in rf['rows'] if r['case']==case and r['accepted']]
        incumbent=signed['policy_arms'];null={}
        for arm,old in incumbent.items():
            p=make_precision_control(scan,node,mask,arm,np.asarray(old['phase_reference']),powers,means,hyper,entries,{});cached(p)
            delta=p.calculate(np.asarray(old['endpoint_east_north_km']))['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(delta)>1e-6:raise ValueError('normalized original signed likelihood failed replay')
            null[arm]=float(delta)
        results={}
        for method in METHODS:
            changed,overrides,deltas=intervene(scan,selected,method)
            pair={arm:refit(changed,node,mask,arm,powers,means,hyper,entries,overrides) for arm in ARMS}
            accepted=valid(pair)
            results[method]=dict(arms=pair,paired_valid=accepted,policy_arms=pair if accepted else incumbent,
                changed_observation_ids_and_CFO_delta_hz=deltas,precision_overrides_hz=overrides)
            print(case,method,'paired valid',accepted,'RMS',{a:r['RMS_hz'] for a,r in pair.items()},flush=True)
        record=dict(case=case,status='complete',results=results,incumbent_arms=incumbent,
            RF_qualified_points=len(selected),accepted_point_strata={r['observation_id']:r['stratum'] for r in selected},
            original_mask=mask,means_s=means,hyper=hyper,powers=powers,entries=entries,
            original_signed_objective_replay_differences=null,signed_incumbent_path=str(signed_path.relative_to(ROOT)),
            signed_incumbent_sha256=sha(signed_path),RF_validation_sha256=sha(RF/'evaluation.json'),
            original_observations_never_removed=True,no_satellite_or_alias_changes=True,
            no_GPS_or_future_TLE_used=True,linear_points_never_calibrate=True)
    except Exception as exc:record=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-began;write(path,record);return record


def main():
    prepare();OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(cases=['DS23-0202','DS23-0274'],methods=list(METHODS),
        RF_evaluation_sha256=sha(RF/'evaluation.json'),signed_audit_sha256=sha(SIGNED_AUDIT),
        one_hz_reference_changes_only_position_independent_residual_constant=True,
        no_original_point_removed_no_gate_relaxation=True,matched_c_arms=True,
        phase_rounds=5,position_iterations=48,cold_start_km=[0,0],regional_box_km=25,
        noise_rule='accepted RF points only: min(original,max(5Hz,fold difference,2*RF curvature sigma)); proxy not independently calibrated',
        no_GPS_or_future_TLE_used=True,workers=2,per_case_seconds=180,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_synthetic_precision.py',ROOT/'tools/probe_ds23_refined_precision.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('real position experiment changed')
    if not target.exists():write(target,protocol)
    with ProcessPoolExecutor(max_workers=2) as pool:
        rows=[f.result() for f in as_completed([pool.submit(run,c) for c in protocol['cases']])]
    write(OUT/'execution.json',dict(results=rows,all_terminal=True,errors=[r for r in rows if r['status']!='complete']))


if __name__=='__main__':main()
