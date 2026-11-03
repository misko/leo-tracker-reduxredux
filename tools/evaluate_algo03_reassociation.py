"""Post-fit position/error figures; no inference module imports this reporter."""

import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_algo03_complete_reassociation import context,build
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.retained_track_likelihood import PERIOD

COHORT=ROOT/'reports/2026_10_20_algo03_reassociation_cohort'
HYBRID=ROOT/'reports/2026_10_20_algo03_hybrid_reassociation'
FEASIBLE=ROOT/'reports/2026_10_20_algo03_feasible_hybrids'


def scan268():
    original=read(HYBRID/'execution.json');constrained=read(FEASIBLE/'execution.json')
    chosen=constrained['best_qualified_trial'];selected=read(FEASIBLE/f"trial_{chosen['index']:02d}.json")
    scan,node,keep,base,old=context('DS23-0268');baseline=old['policy_arms'];rows=[]
    for directory,prefix in [(HYBRID,'trial'),(FEASIBLE,'trial')]:
        for path in directory.glob(prefix+'_[0-9][0-9].json'):
            d=read(path);pair=d.get('arms',{});valid=d.get('paired_valid',False)
            if not pair:continue
            for arm,a in pair.items():
                rows.append(dict(stage='constrained' if directory==FEASIBLE else 'unconstrained',
                    index=d.get('index',d.get('hypothesis_index')),arm=arm,valid=valid,
                    error_km=position_error(a['endpoint_latlon']),
                    loss_gain=baseline[arm]['negative_twice_elbo']-a['negative_twice_elbo']))
    write(FEASIBLE/'position_evaluation.json',dict(rows=rows,chosen_index=chosen['index'],
        chosen_error_km={a:position_error(selected['arms'][a]['endpoint_latlon']) for a in ('c0','fitted_c')},
        original_error_km={a:position_error(baseline[a]['endpoint_latlon']) for a in ('c0','fitted_c')},
        evaluation_GPS_only=True,not_yet_generalized=True))
    fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for r in rows:
            if r['arm']!=arm:continue
            color='tab:orange' if r['stage']=='constrained' else 'tab:blue'
            ax.scatter(r['loss_gain'],r['error_km'],color=color,marker='o' if r['valid'] else 'x',s=45,alpha=.75)
        ax.scatter(0,position_error(baseline[arm]['endpoint_latlon']),color='black',marker='*',s=150,label='ALGO02')
        a=selected['arms'][arm];gain=baseline[arm]['negative_twice_elbo']-a['negative_twice_elbo']
        ax.scatter(gain,position_error(a['endpoint_latlon']),facecolor='none',edgecolor='green',s=180,lw=2,label='RF-selected constrained trial')
        ax.axvline(original['search_penalty'],color='grey',ls='--',label='c0 search penalty (applied to c0 only)')
        ax.set(title=arm,xlabel='Original minus new normalized RF loss',ylabel='Post-fit position error (km)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('DS23-0268 · all 1,832 original position observations retained\nBlue: unconstrained hybrid; orange: constrained refinement; ×: fails paired gates')
    fig.savefig(FEASIBLE/'loss_and_position.png',dpi=170);plt.close(fig)
    model=old['hyperparameters_from_pre_RF_TLE_only'];powers=np.asarray(old['weights']);newnode=selected['node']
    def problem(n,saved):
        labels=sorted({r['candidate_index'] for r in n['seed']['rows']});_,receipts=phase_widths(scan,labels)
        means=forecast_phase_mean(receipts,model['shrinkage'])
        return build(scan,n,keep,'c0',np.asarray(saved['phase_reference']),powers,means,model)
    before=problem(node,baseline['c0']);after=problem(newnode,selected['arms']['c0'])
    c0=before.calculate(baseline['c0']['endpoint_east_north_km']);c1=after.calculate(selected['arms']['c0']['endpoint_east_north_km'])
    raw={o['observation_id']:o for o in read(ROOT/'reports/2026_10_19_algo02_ds23_full/DS23-0268/observations.json')}
    focus=[k for k,r in enumerate(base.rows) if r['candidate_norad']==53923 and keep[base.slices[k]].any()]
    fig,axes=plt.subplots(len(focus),2,figsize=(14,2.5*len(focus)),layout='constrained')
    mapping=[]
    for axrow,k in zip(axes,focus,strict=True):
        i=base.members[k];sl=base.slices[k];t=scan.tracks[i];active=keep[sl];ids=np.asarray(t['observation_ids'])[active]
        times=t['times'][active];native=np.array([raw[o]['measured_cfo_hz'] for o in ids])
        graph_shift=t['values'][active]-native
        f0=(before.values[sl]-c0['conditional_residual_hz'][sl])[active]-before.alias[k]*PERIOD-graph_shift
        f1=(after.values[sl]-c1['conditional_residual_hz'][sl])[active]-after.alias[k]*PERIOD-graph_shift
        newlabel=newnode['seed']['rows'][k]['candidate_norad'];color='tab:orange' if newlabel!=53923 else 'tab:green'
        ax=axrow[0];ax.scatter(times,native/1000,color='black',s=10,label='Original GLRT')
        ax.plot(times,f0/1000,color='tab:blue',ls='--',lw=1,label='ALGO02 fit')
        ax.plot(times,f1/1000,color=color,lw=1,label='New hypothesis fit')
        ax.set(title=f"RX{t['receiver']} CH{t['channel']} {t['key'].split('-T')[1].split('-RF')[0]} · 53923 → {newlabel}",ylabel='Native CFO (kHz)',xlabel='Device time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
        ax=axrow[1];ax.axhline(0,color='grey',lw=.7)
        ax.scatter(times,c0['conditional_residual_hz'][sl][active],color='tab:blue',s=12,label='ALGO02 residual')
        ax.scatter(times,c1['conditional_residual_hz'][sl][active],color=color,s=12,marker='x',label='New residual')
        ax.set(xlabel='Device time (s)',ylabel='Conditional residual (Hz)');ax.grid(alpha=.2);ax.legend(fontsize=7)
        mapping.append(dict(component=t['key'],receiver=t['receiver'],channel=t['channel'],points=int(active.sum()),
                            original_norad=53923,new_norad=newlabel))
    fig.suptitle('DS23-0268 · one old family splits into two candidate satellites\nBoth hypotheses pass their final gates; smaller position error is evaluation evidence, not identity proof')
    fig.savefig(FEASIBLE/'family_split_GLRT.png',dpi=150);plt.close(fig)
    write(FEASIBLE/'family_split.json',mapping)


def cohort():
    if not (COHORT/'execution.json').exists():raise ValueError('cohort still running')
    protocol=read(COHORT/'protocol.json');rows=[]
    for case in protocol['cases']:
        d=read(COHORT/case/'result.json')
        for arm in ('c0','fitted_c'):
            rows.append(dict(case=case,arm=arm,accepted=d['accepted'],
                baseline_error_km=position_error(d['baseline_arms'][arm]['endpoint_latlon']),
                policy_error_km=position_error(d['policy_arms'][arm]['endpoint_latlon']),
                hypotheses=d['proposal_hypotheses'],full_finalists=d['full_finalists']))
    summary={}
    for arm in ('c0','fitted_c'):
        selected=[r for r in rows if r['case']!='DS23-0268' and r['arm']==arm]
        summary[arm]=dict(baseline_mean_median_km=[float(np.mean([r['baseline_error_km'] for r in selected])),float(np.median([r['baseline_error_km'] for r in selected]))],
            policy_mean_median_km=[float(np.mean([r['policy_error_km'] for r in selected])),float(np.median([r['policy_error_km'] for r in selected]))],
            accepted_cases=sum(r['accepted'] for r in selected))
    write(COHORT/'evaluation.json',dict(rows=rows,summary=summary,original20_separate_from_debug268=True,
        GPS_only_for_evaluation=True,lower_discovery_budget_than_268_deep_dive=True))
    fig,axes=plt.subplots(1,2,figsize=(14,4.7),layout='constrained')
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        selected=[r for r in rows if r['arm']==arm];x=np.arange(len(selected))
        ax.scatter(x,[r['baseline_error_km'] for r in selected],color='black',s=25,label='ALGO02')
        ax.scatter(x,[r['policy_error_km'] for r in selected],color='tab:orange',marker='x',s=40,label='Reassociation policy')
        ax.set_xticks(x,[r['case'].split('-')[1] for r in selected],rotation=90);ax.axhline(.5,color='grey',ls='--')
        ax.set(title=arm,ylabel='Position error (km)',xlabel='DS23 scan; 0268 is separate debug case');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Fixed reassociation/constrained-fit rules · saved original cold-discovery branches only')
    fig.savefig(COHORT/'position_errors.png',dpi=170);plt.close(fig)
    print(summary)


if __name__=='__main__':
    scan268();cohort()
