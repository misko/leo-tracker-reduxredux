"""Bounded, IQ-disjoint absolute/relative position pilot with matched controls.

Frozen relative-curve hypotheses are proposals, not established identities.
Inference and control auditing do not read the evaluation coordinate.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from build_dsx01_orbit_modes import build_modes
from ds23_causal_phase_location import adjust_means
from ds23_disjoint_rf_calibration import exclude_probes
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_joint_relative_position import make_joint_relative,attach_joint_relative_predictive
from ds23_predictive_subsets import realize_predictive_subsets,assert_realized_predictive_membership
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import cached,summary
from probe_ds23_sign_carrier_position import context_signed
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from run_ds23_combined_recovery_full import valid,ARMS
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

INPUT=ROOT/'reports/2026_10_22_ds23_exact_differential_phase/unanchored_relative_inputs'
OUT=ROOT/'reports/2026_10_22_ds23_joint_relative_position'
CASES=['DS23-0202','DS23-0274','DS23-0154']
VARIANTS=[('quarantined_GLRT',False,float(np.sqrt(2)*300)),
          ('joint_bias424',True,float(np.sqrt(2)*300)),('joint_bias1000',True,1000.)]


def context(case):
    scan,node,mask,powers,means,model,entries,signed,binding=context_signed(case)
    source=read(INPUT/(case+'.json'))
    if not source['eligible']:raise ValueError('frozen RF inputs did not qualify support')
    groups=source['groups'];rf_labels=source['nominated_candidate_indices']
    base=make_event_problem(scan,node,mask,'c0',np.zeros(len(means)),powers,means,model,[])
    probes=[dict(time_s=r['time_s'],channel=g['lane'][1],rf_hz=g['lane'][2]) for g in groups for r in g['points']]
    keep,selected,quarantine=exclude_probes(scan,base,mask,entries,probes)
    changed,selected,subsets=realize_predictive_subsets(scan,selected)
    assert_realized_predictive_membership(changed,selected,quarantine['excluded_probe_graph_ids'])
    for sl in base.slices:
        if keep[sl].any() and len(np.unique(base.flat_times[sl][keep[sl]]))<4:
            raise ValueError('quarantine left fewer than four distinct curved times; do not trim to rescue')
    widths,receipts=phase_widths(scan,rf_labels)
    rf_means=forecast_phase_mean(receipts,model['shrinkage'])
    if signed['accepted']:rf_means=adjust_means(rf_means,receipts,model,signed['selection'])
    for j in set(base.labels)&set(rf_labels):
        np.testing.assert_allclose(rf_means[rf_labels.index(j)],means[base.labels.index(j)],rtol=0,atol=1e-12)
    owners={j:set() for j in rf_labels}
    for g in groups:
        for role in ['first','second']:owners[g['nomination'][role+'_index']].add(tuple(g['lane'][:2]))
    supported=[j for j in rf_labels if j in base.supported or (j not in base.labels and len(owners[j])>=2)]
    if not hasattr(scan,'previous_tle_path'):raise ValueError('explicit causal prior path required')
    modes,metadata=build_modes(scan,rf_labels,supported,'physical')
    for j in set(supported)&set(base.supported):
        old=slice(3*base.labels.index(j),3*base.labels.index(j)+3)
        new=slice(3*rf_labels.index(j),3*rf_labels.index(j)+3)
        for field in ['position_km','velocity_km_s']:
            np.testing.assert_allclose(base.mode_bank[field][old],modes[field][new],rtol=0,atol=1e-12)
    cutoff=scan.receipt['cutoff_utc_ns']
    for j in set(base.labels)|set(rf_labels):
        provenance=scan.elements[str(int(scan.norads[j]))]['provenance']
        if max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])>cutoff:
            raise ValueError('noncausal element epoch or collection')
    return dict(scan=changed,node=node,keep=keep,powers=np.asarray(powers),old_means=np.asarray(means),model=model,
        old_labels=list(base.labels),all_labels=sorted(set(base.labels)|set(rf_labels)),
        groups=groups,rf_labels=rf_labels,rf_means=np.asarray(rf_means),rf_widths=widths*model['multiplier'],
        rf_modes=modes,rf_supported=supported,coordinate=latlon,original_entries=selected,
        signed=signed,binding=binding,quarantine_receipt=quarantine,predictive_subset_receipts=subsets,
        rf_mode_metadata=metadata,original_mask=mask,input_sha256=sha(INPUT/(case+'.json')))


def make(d,arm,reference,include_relative,bias_sigma):
    p=make_joint_relative(d,arm,reference,include_relative=include_relative,bias_sigma=bias_sigma)
    attach_joint_relative_predictive(p,d['original_entries'])
    return p


def control_audit(case,output_dir=None):
    d=context(case);rows=[]
    for arm in ARMS:
        saved=d['signed']['policy_arms'][arm]
        for phase_mode in ['zero','incumbent']:
            ref=np.zeros(len(d['all_labels']))
            if phase_mode=='incumbent':
                for k,j in enumerate(d['old_labels']):ref[d['all_labels'].index(j)]=saved['phase_reference'][k]
            oldref=np.array([ref[d['all_labels'].index(j)] for j in d['old_labels']])
            original=make_event_problem(d['scan'],d['node'],d['keep'],arm,oldref,d['powers'],d['old_means'],d['model'],[])
            attach_event_predictive(original,d['original_entries'],d['powers'])
            joint=make(d,arm,ref,False,float(np.sqrt(2)*300));offsets=[]
            for x in [np.zeros(2),np.asarray(saved['endpoint_east_north_km']),np.array([3.,-2.])]:
                a,b=original.calculate(x),joint.calculate(x);w=joint.joint_old_width
                coefficient=float(np.max(abs(a['coefficient']-b['coefficient'][:w])))
                residual=float(np.max(abs(a['conditional_residual_hz']-b['conditional_residual_hz'])))
                prior=float(np.max(abs(a['coefficient_prior_precision']-b['coefficient_prior_precision'][:w])))
                linear=float(np.max(abs(a.get('linear_raw_prediction_residual_hz',np.zeros(1))-b.get('linear_raw_prediction_residual_hz',np.zeros(1)))))
                if max(coefficient,residual,prior,linear)>1e-5:raise ValueError(f'zero-relative control mismatch:{coefficient,residual,prior,linear}')
                offset=b['negative_twice_elbo']-a['negative_twice_elbo'];offsets.append(offset)
                rows.append(dict(arm=arm,phase_mode=phase_mode,position=x,coefficient_delta=coefficient,
                    residual_delta_hz=residual,prior_precision_delta=prior,predictive_delta_hz=linear,unused_prior_loss_offset=offset))
            if np.ptp(offsets)>1e-5:raise ValueError('unused phase priors changed position-dependent loss')
    result=dict(case=case,rows=rows,quarantine=d['quarantine_receipt'],predictive_subsets=d['predictive_subset_receipts'],
        all_GLRT_numerical_rows_disjoint_from_RF=True,causal_element_epoch_and_collection_audited=True,
        shared_phase_priors_and_physical_modes_identical=True,reference_position_used=False,
        original_curved_points=int(d['original_mask'].sum()),remaining_curved_points=int(d['keep'].sum()),
        remaining_predictive_points=sum(e['points'] for e in d['original_entries']),
        rf_groups=len(d['groups']),rf_points=sum(len(g['points']) for g in d['groups']),
        old_labels=d['old_labels'],all_labels=d['all_labels'],rf_supported=d['rf_supported'])
    write((OUT if output_dir is None else Path(output_dir))/(case+'_control_audit.json'),result)
    print(case,'control audit passes',flush=True);return result


def relative_gates(p,x,bias_sigma):
    if not p.relative_include:return []
    raw,elevation,phase=p.exact_relative(x);valid_phase=raw is not None
    c=p.calculate(x);rows=[];rf=p.relative_problem;begin=len(rf.labels)+3*len(rf.supported)
    coef=c['coefficient'][p.relative_mapping]
    for k,(group,sl) in enumerate(zip(rf.groups,rf.slices,strict=True)):
        noise={key:value[0] for key,value in batch_noise_screen(raw[sl][None],rf.times[sl]).items()} if valid_phase else dict(noise_screen_pass=False)
        rms=float(np.sqrt(np.mean(raw[sl]**2))) if valid_phase else None;bias=float(bias_sigma*coef[begin+k])
        passed=bool(valid_phase and rms<=450 and abs(bias)<=3000 and elevation[sl].min()>=0 and noise['noise_screen_pass'])
        rows.append(dict(group=group['group'],compatible=passed,RMS_hz=rms,bias_hz=bias,diagnostics=noise,
            points=sl.stop-sl.start,exact_phase_residual=True))
    return rows


def refit(d,arm,include,bias_sigma):
    reference=np.zeros(len(d['all_labels']));x=np.zeros(2);history=[]
    for _ in range(5):
        p=make(d,arm,reference,include,bias_sigma);cached(p);fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
        phase=np.clip(p.state(x)['phases'][d['all_labels']],-15,15)
        history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
    record=summary(p,x,d['original_entries']);c=p.calculate(x)
    record.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
        joint_phase_reference=p.joint_reference,coefficient=c['coefficient'],noise_precision=c['noise_precision'],
        relative_noise_precision=c['relative_noise_precision'],relative_gates=relative_gates(p,x,bias_sigma),
        normalization_constant=c['normalization_constant'])
    return record


def one(case,variant,include,bias_sigma,output_dir=None):
    output=OUT if output_dir is None else Path(output_dir);path=output/(case+'_'+variant+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s paired joint pilot cap')));signal.alarm(300)
    try:
        d=context(case);pair={arm:refit(d,arm,include,bias_sigma) for arm in ARMS}
        accepted=bool(valid(pair) and all(r['final_phase_change_s']<=.01 and all(g['compatible'] for g in r['relative_gates']) for r in pair.values()))
        result=dict(case=case,variant=variant,status='complete',accepted=accepted,arms=pair,
            policy_arms=pair if accepted else d['signed']['policy_arms'],original_incumbent=d['signed']['policy_arms'],
            quarantine_receipt=d['quarantine_receipt'],predictive_subset_receipts=d['predictive_subset_receipts'],
            mask=d['keep'],powers=d['powers'],entries=d['original_entries'],old_labels=d['old_labels'],all_labels=d['all_labels'],
            rf_labels=d['rf_labels'],rf_supported=d['rf_supported'],bias_sigma_hz=bias_sigma,include_relative=include,
            input_sha256=d['input_sha256'],signed_incumbent_sha256=sha(d['binding']),
            same_IQ_quarantine_and_original_priors_and_search_budgets=True,reference_position_used=False,
            no_GPS_future_TLE_or_new_RF_or_IQ=True,fixed_hypotheses_not_verified_emitters=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,variant=variant,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(case,variant,result['status'],result.get('accepted'),result.get('error'),flush=True);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['audit-controls','fit'],required=True)
    args=parser.parse_args();OUT.mkdir(exist_ok=True)
    protocol=dict(cases=CASES,variants=[list(v) for v in VARIANTS],default='joint_bias424',cold_start_km=[0,0],region_width_km=25,
        phase_rounds=5,steps_per_round=48,workers=6,paired_case_cap_s=300,
        identical_actual_IQ_quarantine_in_every_variant=True,all_original_uncertainty_preserved=True,
        no_new_modes_for_old_unsupported_satellite=True,linear_evidence_predictive_only=True,
        no_truth_future_elements_new_IQ_or_RF=True,original_residual_gates_not_relaxed=True,
        original_incumbent_fallback_for_failed_gates=True,
        raw_objectives_of_RF_on_and_off_not_comparable=True,
        sources={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_joint_relative_position.py']},
        inputs={c:sha(INPUT/(c+'.json')) for c in CASES})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('joint pilot protocol changed')
    if not path.exists():write(path,protocol)
    if args.stage=='audit-controls':
        with ProcessPoolExecutor(max_workers=3) as pool:rows=list(pool.map(control_audit,CASES))
        write(OUT/'control_audit.json',dict(rows=rows,all_passed=True));return
    if not read(OUT/'control_audit.json')['all_passed']:raise ValueError('matched controls unaudited')
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,c,*v) for c in CASES for v in VARIANTS])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,engineering_pilot_not_generalization=True))


if __name__=='__main__':main()
