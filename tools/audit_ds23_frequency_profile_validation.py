"""Audit held-symbol RF prediction and render two reproducible examples."""

from pathlib import Path
import json
import numpy as np
from ds23_joint_component_refinement import JointComponentWorkspace
from run_algo01_ds23_sample import ROOT,read,write,sha

DEVELOPMENT=ROOT/'reports/2026_10_21_ds23_frequency_profile_validation'
CONFIRMATION=ROOT/'reports/2026_10_21_ds23_frequency_profile_confirmation'
PROFILE=ROOT/'reports/2026_10_21_ds23_frequency_profile'


def check(root):
    evaluation=read(root/'evaluation.json');protocol=read(root/'protocol.json')
    for name,digest in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=digest:raise ValueError('RF-profile scientific source changed')
    if not evaluation['all_terminal'] or evaluation['complete']!=len(protocol['jobs']):raise ValueError('RF-profile work is incomplete')
    for row in evaluation['rows']:
        for fold in row['folds']:
            value=2*fold['baseline_prediction']['heldout_samples']*np.log(fold['baseline_prediction']['heldout_squared_error']/fold['piecewise_heldout_squared_error'])
            if abs(value-fold['heldout_profile_gain'])>1e-8:raise ValueError('saved RF prediction gain is inconsistent')
    return protocol,evaluation


def replay_one(root,protocol,evaluation):
    eligible=sorted([r for r in evaluation['rows'] if r['RF_profile_qualified']],key=lambda r:(r['case'],r['probe']))
    if not eligible:raise ValueError('no RF-qualified example to replay')
    row=eligible[0];item=next(j for j in protocol['jobs'] if (j['job']['case'],j['job']['probe'])==(row['case'],row['probe']));job=item['job']
    with np.load(Path(item['source'])/'panels'/(job['case']+'.npz'),allow_pickle=False) as z:
        metadata=json.loads(str(z['metadata_json']));point=next(p for p in metadata['points'] if p['probe']==job['probe'])
        v=z[point['window_key']][:,point['receiver_offset']]
    y=v[:,0].astype(float)+1j*v[:,1].astype(float)
    p=JointComponentWorkspace(y,metadata['sample_rate_hz'],job['edge'],[job['first']['epoch'],job['second']['epoch']],
        [item['fit']['first_fit'],item['fit']['second_fit']]);all_segments=p.segments;thirds=np.array_split(np.arange(len(all_segments)),3);errors=[]
    for fold in row['folds']:
        p.segments=all_segments;base=p.statistics(fold['baseline']['parameters'],fold['parity'],derivatives=False,prediction=True)
        if abs(base['heldout_squared_error']/fold['baseline_prediction']['heldout_squared_error']-1)>1e-12:raise ValueError('constant held-symbol RF error does not replay')
        total=0.
        for k,indices in enumerate(thirds):
            p.segments=[all_segments[i] for i in indices]
            predicted=p.statistics(fold['parts'][k]['fit']['parameters'],fold['parity'],derivatives=False,prediction=True)
            total+=predicted['heldout_squared_error']
        if abs(total/fold['piecewise_heldout_squared_error']-1)>1e-12:raise ValueError('piecewise held-symbol RF error does not replay')
        errors.append(dict(parity=fold['parity'],baseline_SSE=base['heldout_squared_error'],piecewise_SSE=total))
    return dict(case=row['case'],probe=row['probe'],root=str(root.relative_to(ROOT)),raw_held_symbol_errors_replayed=errors)


def main():
    dp,de=check(DEVELOPMENT);cp,ce=check(CONFIRMATION)
    ids=[{(r['case'],r['probe']) for r in e['rows']} for e in [de,ce]]
    if ids[0]&ids[1]:raise ValueError('RF development and confirmation probes overlap')
    receipts=[replay_one(root,p,e) for root,p,e in [(DEVELOPMENT,dp,de),(CONFIRMATION,cp,ce)]]
    summary={name:{k:e[k] for k in ['complete','both_folds_predict_better','RF_qualified','median_heldout_profile_gain']}
        for name,e in [('development',de),('point_disjoint_confirmation',ce)]}
    write(CONFIRMATION/'independent_replay_audit.json',dict(summary=summary,receipts=receipts,
        probe_identity_disjointness_verified=True,all_stored_gain_formulas_replayed=True,
        one_real_raw_probe_per_cohort_recomputed=True,all_other_raw_predictions_not_recomputed=True,
        same23_scans_and_location_not_new_scan_or_location_validation=True,
        no_absolute_CFO_or_position_correction_established=True,
        temporal_model_improvement_does_not_identify_receiver_LO_vs_sample_clock_vs_template_impairment=True))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    original=read(PROFILE/'evaluation.json');lookup={(r['case'],r['probe']):r for r in original['rows']}
    qualified=[r for r in de['rows'] if r['RF_profile_qualified']]
    selected=sorted(qualified,key=lambda r:-abs(lookup[r['case'],r['probe']]['contrast']['common_contrast_hz']))[:2]
    fig,axes=plt.subplots(1,3,figsize=(15,4.8),constrained_layout=True)
    for ax,row in zip(axes[:2],selected,strict=True):
        saved=lookup[row['case'],row['probe']]
        for component in [0,1]:
            t=np.array([p['effective_time_s'][component] for p in saved['parts']])*1000
            values=np.array([p['CFO_hz'][component] for p in saved['parts']])-saved['whole_probe_fixed_frequency'][component]
            uncertainty=np.sqrt([p['covariance_hz2'][component][component] for p in saved['parts']])
            ax.errorbar(t,values,yerr=uncertainty,fmt='o-',capsize=2,label=f'Component{component+1}')
        ax.set(xlabel='Effective time within 20 ms probe (ms)',ylabel='CFO relative to whole-probe fit (Hz)',title=row['group']+f" · probe {row['probe']}")
        ax.legend(fontsize=8);ax.grid(alpha=.2)
    for x,(name,e) in enumerate([('Development',de),('New probes',ce)]):
        axes[2].bar(x-.18,e['both_folds_predict_better']/e['complete']*100,width=.34,color='tab:blue',label='Both folds predict better' if x==0 else None)
        axes[2].bar(x+.18,e['RF_qualified']/e['complete']*100,width=.34,color='tab:orange',label='Also stable/in bounds' if x==0 else None)
    axes[2].set(xticks=[0,1],xticklabels=['46 probes','23 new probes'],ylabel='Percentage of probes',ylim=(0,100),title='Conditional RF prediction')
    axes[2].legend(fontsize=8);axes[2].grid(axis='y',alpha=.2)
    fig.suptitle('Within-probe carrier variation survives held-symbol RF tests in a subset\nPoint-disjoint confirmation; same scans/site; conditional local error bars; no absolute frequency or position correction adopted')
    fig.savefig(CONFIRMATION/'validated_frequency_profiles.png',dpi=160);plt.close(fig)
    print(summary,flush=True)


if __name__=='__main__':main()
