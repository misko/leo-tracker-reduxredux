"""Replay recovered signed-prior fits and report a matched 410-scan comparison."""

from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from algo02_scan import bind_run_directory,load_scan,pair_passes
from ds23_causal_phase_location import qualify,adjust_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from extend_ds23_signed_prior_recoveries import OUT,SIGNED,prepare
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import summary,cached
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha
from run_algo02_ds23 import DEFAULT_RUN,verify_freeze


def verify(case,protocol):
    binding=protocol['recovered_original_bindings'][case];root=ROOT/binding['root']
    record=read(OUT/(case+'.json'));original=read(root/case/'algo02_result.json')
    bind_run_directory(root);scan=load_scan(root,case)
    node=read(root/case/'result.json')['final_node'];mask=np.asarray(original['mask'],bool)
    np.testing.assert_array_equal(record['original_mask'],mask)
    if record['baseline_arms']!=original['policy_arms']:
        raise ValueError('signed policy changed the matched original baseline')
    model=original['hyperparameters_from_pre_RF_TLE_only'];powers=np.asarray(original['weights'])
    base=problem(scan,node,'c0',mask);_,receipts=phase_widths(scan,base.labels)
    history=read(root/'causal_phase_history'/(case+'.json'))
    forecast=read(root/'causal_phase_history'/(case+'_forecast.json'))
    cutoff=scan.receipt['cutoff_utc_ns']
    if history['cutoff_utc_ns']!=cutoff or any(max(v['epoch'],v['collected_utc_ns'])>cutoff
        for versions in history['past_versions'].values() for v in versions) or any(
        r['validation_time_ns']>cutoff for r in forecast['transitions']):
        raise ValueError('recovered prior uses a noncausal history target')
    if sha(root/'causal_phase_history'/(case+'.json'))!=record['history_sha256'] or sha(root/'causal_phase_history'/(case+'_forecast.json'))!=record['forecast_sha256']:
        raise ValueError('signed history changed')
    selection=qualify(forecast['transitions'],forecast['temporal_split_boundary_ns'],forecast['prefix_distribution'],model)
    if selection!=record['selection']:raise ValueError('historical prior qualification changed')
    ordinary=forecast_phase_mean(receipts,model['shrinkage'])
    np.testing.assert_allclose(record['original_means_s'],ordinary,rtol=0,atol=1e-12)
    np.testing.assert_allclose(record['means_s'],adjust_means(ordinary,receipts,model,selection),rtol=0,atol=1e-12)
    means=adjust_means(ordinary,receipts,model,selection) if record['accepted'] else ordinary
    entries=original['linear_entries'] if original['linear_paired_valid'] else []
    replayed={};rows=[]
    for arm,saved in record['policy_arms'].items():
        p=make_event_problem(scan,node,mask,arm,np.asarray(saved['phase_reference']),powers,means,model,[])
        attach_event_predictive(p,entries,powers);cached(p)
        x=np.asarray(saved['endpoint_east_north_km']);fresh=summary(p,x,entries)
        delta=fresh['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta)>1e-3 or fresh['linear_calibration_max_difference']>1e-10:
            raise ValueError('signed endpoint or calibration did not replay')
        fresh['final_phase_change_s']=saved.get('final_phase_change_s',0.)
        replayed[arm]=fresh
        rows.append(dict(case=case,arm=arm,prior_qualified=selection['qualified'],accepted=record['accepted'],
            RF_replay_difference=delta,baseline_error_km=position_error(original['policy_arms'][arm]['endpoint_latlon']),
            signed_error_km=position_error(saved['endpoint_latlon'])))
    if not pair_passes(replayed,include_linear=bool(entries)):
        raise ValueError('recovered signed policy fails original gates')
    return rows


def statistics(values):
    a=np.asarray(values)
    return dict(count=len(a),mean_km=float(a.mean()),median_km=float(np.median(a)),
        p90_km=float(np.quantile(a,.9)),maximum_km=float(a.max()),below_half_km=int(sum(a<=.5)))


def main():
    protocol=prepare();verify_freeze(DEFAULT_RUN)
    audit_path=SIGNED/'evaluation_audit.json'
    if sha(audit_path)!=protocol['original_signed_evidence_audit_sha256']:
        raise ValueError('original signed evidence audit changed')
    evidence=dict(read(audit_path)['evidence'])
    checks=[r for case in protocol['cases'] for r in verify(case,protocol)]
    for case in protocol['cases']:
        if case in evidence:raise ValueError('recovery replaced an original evaluated scan')
        path=OUT/(case+'.json');evidence[case]=dict(path=str(path.relative_to(ROOT)),sha256=sha(path))
    rows=[]
    for case,binding in sorted(evidence.items()):
        path=ROOT/binding['path']
        if sha(path)!=binding['sha256']:raise ValueError('scientific policy changed')
        record=read(path)
        for arm in ('c0','fitted_c'):
            rows.append(dict(case=case,arm=arm,recovered=case in protocol['cases'],
                baseline_error_km=position_error(record['baseline_arms'][arm]['endpoint_latlon']),
                signed_error_km=position_error(record['policy_arms'][arm]['endpoint_latlon'])))
    results={}
    for arm in ('c0','fitted_c'):
        selected=[r for r in rows if r['arm']==arm]
        results[arm]={name:statistics([r[field] for r in selected])
            for name,field in (('original_ALGO02','baseline_error_km'),('signed_prior','signed_error_km'))}
    missing=sorted({r['dataset_label'] for r in read(DEFAULT_RUN/'sample.json')['selected']}-set(evidence))
    write(OUT/'evaluation_audit.json',dict(evidence=evidence,all_original_and_recovered_evidence_bound=True,
        recovered_RF_gate_replays=checks,source_sha256=sha(Path(__file__))))
    write(OUT/'evaluation.json',dict(population=413,available=len(evidence),unavailable=missing,
        statistics=results,recovered_checks=checks,all_rows=rows,
        GPS_used_only_for_reporting=True,algorithm_and_prior_rule_unchanged=True,
        no_generalized_new_algorithm_gain_claimed=True,full_half_km_goal_achieved=False))
    figure,axes=plt.subplots(1,2,figsize=(12,5))
    for method,field,color in (('Original ALGO02','baseline_error_km','#8b9299'),
                               ('Signed prior','signed_error_km','#3c8a79')):
        values=sorted(r[field] for r in rows if r['arm']=='fitted_c')
        axes[0].plot(values,np.arange(1,len(values)+1)/len(values),label=method,color=color)
    axes[0].set(xlabel='Position error (km)',ylabel='Fraction of 410 available scans',xlim=(0,5),ylim=(0,1))
    axes[0].axvline(.5,color='black',ls='--',lw=.8);axes[0].legend()
    for arm,color,marker in (('c0','#5685b4','o'),('fitted_c','#b56b90','s')):
        for row in checks:
            if row['arm']!=arm:continue
            axes[1].scatter(row['baseline_error_km'],row['signed_error_km'],color=color,marker=marker,
                label=arm if row['case']==protocol['cases'][0] else None)
            axes[1].annotate(row['case'].replace('DS23-',''),(row['baseline_error_km'],row['signed_error_km']),
                xytext=(4,4),textcoords='offset points',fontsize=7)
    axes[1].plot([0,4],[0,4],color='gray',ls='--')
    axes[1].set(xlabel='Original ALGO02 error (km)',ylabel='Signed-prior error (km)',xlim=(0,4),ylim=(0,4))
    axes[1].legend()
    for ax in axes:ax.grid(alpha=.15)
    figure.suptitle('DS23 · unchanged signed-prior policy extended to six recovered scans\n'
        '410 available / 413 original members · matched c arms · remaining failures explicit')
    figure.tight_layout(rect=(0,0,1,.89));figure.savefig(OUT/'position_comparison_410.png',dpi=175);plt.close(figure)
    print(results,'remaining',missing,flush=True)


if __name__=='__main__':
    main()
