"""Saved conditional nomination outcomes, never an identity acceptance rule."""
import csv
from pathlib import Path
import json

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import experiment as e


def main():
    protocol=e.verify(approval=True);seal=e.read(e.HERE/'RF_seal.json')
    for path,expected in seal['files'].items():
        if e.sha(path)!=expected:raise ValueError('sealed result changed: '+path)
    execution=e.read(e.HERE/'execution.json');rows=[];contexts=[]
    for case_result in execution['rows']:
        case=case_result['case'];context_path=e.HERE/case/'context.json'
        if context_path.exists():contexts.append(e.read(context_path))
        for trial in case_result['rows']:
            folder=e.HERE/case/('trial'+str(trial['trial']))
            truth=e.read(folder/'generation.json') if (folder/'generation.json').exists() else None
            screen=e.read(folder/'screen.json') if (folder/'screen.json').exists() else None
            for arm in e.ARMS:
                path=folder/(arm+'_result.json');result=e.read(path) if path.exists() else None
                true=truth['generating_norad'] if truth else None
                rank=screen['ranked_visible_norads'].index(true)+1 if screen and true in screen['ranked_visible_norads'] else None
                in_pool=true in screen['candidate_norads'] if screen and true is not None else None
                dense=result.get('denser_ranked_norads',[]) if result else []
                exact_rank=dense.index(true)+1 if true in dense else None
                best=result.get('best_physical_norad') if result else None
                gap=result.get('best_physical_minus_null') if result else None
                winner=next((row for row in result.get('candidates',[]) if row['norad']==best),None) if result else None
                dense_gap=winner['reference_objective']-result['null']['objective'] if winner else None
                preference='physical' if gap is not None and gap<0 else 'unresolved' if gap is not None and gap>0 else 'tie' if gap==0 else 'unavailable'
                row=dict(case=case,trial=trial['trial'],kind=trial['kind'],arm=arm,trial_status=trial['status'],
                    arm_status=result['status'] if result else 'unavailable',generating_norad=true,
                    coarse_true_rank=rank,true_in_shortlist=in_pool,exact_true_dense_rank=exact_rank,
                    best_physical_norad=best,physical_best_is_truth=best==true if true is not None and best is not None else None,
                    best_physical_minus_null=gap,reference_best_physical_minus_null=dense_gap,declared_density_preference=preference,
                    ordering_numerically_qualified=result.get('ordering_numerically_qualified',False) if result else False,
                    selected_candidates=len(screen['candidate_norads']) if screen else 0,
                    complete_candidates=sum(c['status']=='complete' for c in result.get('candidates',[])) if result else 0,
                    blocked_candidates=sum(c['status']!='complete' for c in result.get('candidates',[])) if result else 0,
                    unqualified_finite_candidates=sum(c['status']=='complete' and not c['numerically_qualified'] for c in result.get('candidates',[])) if result else 0,
                    original_active_shortlisted_families=result.get('original_active_shortlist_families') if result else None,
                    removed_curved_points=len(result['cavity']['removed_curved_ids']) if result and 'cavity'in result else None,
                    removed_predictive_points=len(result['cavity']['removed_predictive_ids']) if result and 'cavity'in result else None,
                    target_observations_sha256=trial.get('observations_sha256'),
                    null_alias_range_stable=result.get('null',{}).get('alias_stable') if result else None,
                    winner_alias_range_stable=winner.get('alias_stable') if winner else None,
                    seconds=result.get('seconds') if result else None)
                rows.append(row)
    if len(rows)!=24:raise ValueError('all12 trials and both arms must remain in denominator')
    summaries=[]
    for arm in e.ARMS:
        for kind in ('physical','unresolved'):
            chosen=[r for r in rows if r['arm']==arm and r['kind']==kind]
            summaries.append(dict(arm=arm,kind=kind,selected=len(chosen),complete=sum(r['arm_status']=='complete' for r in chosen),
                numerically_qualified=sum(r['ordering_numerically_qualified'] for r in chosen),
                truth_in_shortlist=sum(r['true_in_shortlist'] is True for r in chosen) if kind=='physical' else None,
                shortlist_misses=sum(r['true_in_shortlist'] is False for r in chosen) if kind=='physical' else None,
                unavailable_screen=sum(r['selected_candidates']==0 for r in chosen),
                raw_best_physical_is_truth=sum(r['physical_best_is_truth'] is True for r in chosen) if kind=='physical' else None,
                raw_physical_density_preference=sum(r['declared_density_preference']=='physical' for r in chosen),
                raw_unresolved_density_preference=sum(r['declared_density_preference']=='unresolved' for r in chosen),
                qualified_physical_density_preference=sum(r['ordering_numerically_qualified'] and r['declared_density_preference']=='physical' for r in chosen),
                qualified_unresolved_density_preference=sum(r['ordering_numerically_qualified'] and r['declared_density_preference']=='unresolved' for r in chosen)))
    summary=dict(summaries=summaries,total_trials=12,total_arm_rows=24,
        cumulative_scientific_seconds=execution['cumulative_scientific_seconds'],
        conditional_scope=protocol['conditioning_limit'],layouts_historically_response_selected=True,
        generating_law='c0 parent-conditioned Student physical or Gaussian polynomial target; matched observations in both arms',
        no_identity_threshold_or_false_accept_probability=True,position_fits=0,GPS_used=False,identity_qualified=False)
    e.write(Path('summary.json'),summary);e.write(Path('rows.json'),rows)
    with (e.HERE/'outcomes.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    labels=[(case,trial) for case in e.CASES for trial in range(6)]
    fig,axes=plt.subplots(1,2,figsize=(12,4.7),constrained_layout=True)
    for ax,arm in zip(axes,e.ARMS):
        chosen={(r['case'],r['trial']):r for r in rows if r['arm']==arm}
        for i,key in enumerate(labels):
            row=chosen[key];gap=row['best_physical_minus_null']
            if gap is not None:ax.scatter(i,gap,color='#2563eb' if row['kind']=='physical' else '#d97706',marker='o' if row['ordering_numerically_qualified'] else 'x',s=44)
        ax.axhline(0,color='black',lw=.7);ax.set_xticks(range(12),[f'{case[-4:]} {"P" if trial<4 else "U"}{trial if trial<4 else trial-4}' for case,trial in labels],rotation=50)
        ax.set(title=arm,ylabel='Best physical minus unresolved objective');ax.grid(alpha=.2)
    fig.suptitle('Declared density ranks, not operational identity decisions; × = numerical limitation')
    fig.savefig(e.HERE/'candidate_null_gaps.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
    physical=[r for r in rows if r['kind']=='physical' and r['arm']=='c0']
    x=np.arange(8);ranks=[r['coarse_true_rank'] if r['coarse_true_rank'] is not None else np.nan for r in physical]
    axes[0].bar(x,ranks,color=['#059669' if r['true_in_shortlist'] else '#dc2626' for r in physical]);axes[0].axhline(8.5,color='black',ls='--',lw=.8)
    axes[0].set_xticks(x,[f'{r["case"][-4:]} P{r["trial"]}' for r in physical],rotation=45);axes[0].set(ylabel='True identity ordinary catalogue rank',title='No forced true-label retention');axes[0].grid(axis='y',alpha=.2)
    for offset,arm,color in ((-.12,'c0','#2563eb'),(.12,'fitted_c','#d97706')):
        chosen=[r for r in rows if r['kind']=='physical' and r['arm']==arm]
        axes[1].scatter(x+offset,[r['exact_true_dense_rank'] if r['exact_true_dense_rank'] is not None else np.nan for r in chosen],c=color,label=arm,s=35)
    axes[1].set_xticks(x,[f'{r["case"][-4:]} P{r["trial"]}' for r in physical],rotation=45);axes[1].set(ylabel='True identity exact rank within shortlist',title='Missing/blocked true labels remain absent');axes[1].legend();axes[1].grid(alpha=.2)
    fig.savefig(e.HERE/'nomination_recall.png',dpi=160);plt.close(fig)
    files=[e.HERE/name for name in ('report.py','summary.json','rows.json','outcomes.csv','candidate_null_gaps.png','nomination_recall.png')]
    e.write(Path('report_seal.json'),dict(files={str(path):e.sha(path) for path in files},RF_seal_sha256=e.sha(e.HERE/'RF_seal.json')))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
