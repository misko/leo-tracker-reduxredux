"""Read-only description of the sealed TLE projections, without fitting a model.

No alternate covariance, location, RF residual or model-selection calculation is
performed. Energy here is in the baseline's standardized parameter coordinates.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import rankdata

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'derived_inventory.json'


def correlation(x,y,weights=None):
    x,y=np.asarray(x,float),np.asarray(y,float)
    w=np.ones(len(x)) if weights is None else np.asarray(weights,float)
    w=w/w.sum()
    x,y=x-np.sum(w*x),y-np.sum(w*y)
    denominator=np.sqrt(np.sum(w*x*x)*np.sum(w*y*y))
    return float(np.sum(w*x*y)/denominator) if denominator>1e-15 else None


def spearman(x,y):
    return correlation(rankdata(x),rankdata(y))


def quantiles(values):
    return dict(zip(['min','q25','median','q75','max'],np.quantile(values,[0,.25,.5,.75,1]).tolist()))


def main():
    original=SOURCE.read_bytes()
    source_sha=hashlib.sha256(original).hexdigest()
    rows=json.loads(original)['rows']
    contexts=[];projections=[]
    for r in rows:
        if r['status']!='ready':continue
        time=r['common_epoch_utc_ns'][1]
        nominal_age=(time-r['nominal_epoch_utc_ns'])/3.6e12
        history=sorted(r['historical_projection'],key=lambda v:v['epoch_utc_ns'])
        coefficients=np.asarray([v['coefficients'] for v in history])
        coefficient_energy=np.sum(coefficients**2,axis=1)
        age=np.asarray([(time-v['epoch_utc_ns'])/3.6e12 for v in history])
        eigenvalues,eigenvectors=np.linalg.eigh(np.asarray(r['second_moment']))
        principal_energy=(coefficients@eigenvectors[:,-1])**2
        principal_shares=principal_energy/max(float(principal_energy.sum()),1e-30)
        trace_shares=coefficient_energy/max(float(coefficient_energy.sum()),1e-30)
        direction_energy=np.mean(coefficients**2,axis=0)
        direction_fraction=direction_energy/max(float(direction_energy.sum()),1e-30)
        capped=max(r['unbounded_eigenvalues'])>16+1e-8
        rec=dict(case=r['case'],dataset=r['dataset'],family=r['selected_family'],epochs=len(history),
            capped=capped,nominal_age_h=nominal_age,mean_history_age_h=float(age.mean()),
            oldest_history_age_h=float(age.max()),youngest_history_age_h=float(age.min()),
            mean_extra_age_h=float(age.mean()-nominal_age),
            max_unbounded_covariance_eigenvalue=max(r['unbounded_eigenvalues']),
            history_coefficient_rms=float(np.sqrt(coefficient_energy.mean())),
            within_context_spearman_age_coefficient_norm=spearman(age,np.sqrt(coefficient_energy)),
            oldest_epoch_trace_energy_fraction=float(trace_shares[0]),
            oldest_epoch_principal_energy_fraction=float(principal_shares[0]),
            youngest_epoch_trace_energy_fraction=float(trace_shares[-1]),
            oldest_epoch_has_largest_coefficient_energy=bool(np.argmax(coefficient_energy)==0),
            principal_energy_weighted_history_age_h=float(principal_shares@age),
            unweighted_history_age_h=float(age.mean()),
            mean_motion_coefficient_energy_fraction=float(direction_fraction[0]),
            inclination_coefficient_energy_fraction=float(direction_fraction[1]),
            RAAN_coefficient_energy_fraction=float(direction_fraction[2]),
            baseline_radial_sigma_km=r['mode_metadata']['radial_sigma_km'],
            baseline_cross_sigma_km=r['mode_metadata']['cross_sigma_km'])
        contexts.append(rec)
        log_norm=np.log1p(np.sqrt(coefficient_energy))
        for i,(h,a,energy) in enumerate(zip(history,age,coefficient_energy)):
            projections.append(dict(case=r['case'],dataset=r['dataset'],family=r['selected_family'],
                capped=capped,epoch_utc_ns=h['epoch_utc_ns'],history_age_h=float(a),nominal_age_h=nominal_age,
                additional_forecast_h=float(a-nominal_age),history_to_nominal_age_ratio=float(a/nominal_age),
                coefficient_norm=float(np.sqrt(energy)),coefficient_energy=float(energy),
                principal_energy_fraction=float(principal_shares[i]),trace_energy_fraction=float(trace_shares[i]),
                mean_motion_coefficient=float(coefficients[i,0]),inclination_coefficient=float(coefficients[i,1]),
                RAAN_coefficient=float(coefficients[i,2]),context_weight=1/len(history),
                centered_history_age_h=float(a-age.mean()),centered_log1p_coefficient_norm=float(log_norm[i]-log_norm.mean())))
    repeated={n:sum(r['family']==n for r in contexts) for n in {r['family'] for r in contexts}}
    by_family=[]
    for n in sorted(repeated):
        group=[r for r in contexts if r['family']==n]
        by_family.append(dict(family=n,contexts=len(group),
            nominal_age_h=float(np.mean([r['nominal_age_h'] for r in group])),
            mean_history_age_h=float(np.mean([r['mean_history_age_h'] for r in group])),
            mean_extra_age_h=float(np.mean([r['mean_extra_age_h'] for r in group])),
            history_coefficient_rms=float(np.mean([r['history_coefficient_rms'] for r in group])),
            max_unbounded_covariance_eigenvalue=float(np.mean([r['max_unbounded_covariance_eigenvalue'] for r in group]))))
    def between(rows):
        y=[r['history_coefficient_rms'] for r in rows]
        return dict(count=len(rows),spearman_mean_history_age_to_coefficient_RMS=spearman([r['mean_history_age_h'] for r in rows],y),
            spearman_nominal_age_to_coefficient_RMS=spearman([r['nominal_age_h'] for r in rows],y),
            spearman_extra_age_to_coefficient_RMS=spearman([r['mean_extra_age_h'] for r in rows],y))
    def capped_group(capped):
        group=[r for r in contexts if r['capped']==capped]
        return dict(contexts=len(group),
            nominal_age_h=quantiles([r['nominal_age_h'] for r in group]),
            mean_history_age_h=quantiles([r['mean_history_age_h'] for r in group]),
            mean_extra_age_h=quantiles([r['mean_extra_age_h'] for r in group]),
            oldest_trace_share=quantiles([r['oldest_epoch_trace_energy_fraction'] for r in group]),
            oldest_principal_share=quantiles([r['oldest_epoch_principal_energy_fraction'] for r in group]),
            direction_energy_fraction_mean={key:float(np.mean([r[key] for r in group])) for key in
                ['mean_motion_coefficient_energy_fraction','inclination_coefficient_energy_fraction','RAAN_coefficient_energy_fraction']})
    within=[r['within_context_spearman_age_coefficient_norm'] for r in contexts
            if r['within_context_spearman_age_coefficient_norm'] is not None]
    stats=dict(source=str(SOURCE),source_sha256=source_sha,source_unchanged=True,
        no_RF_or_GPS_or_position_fit=True,alternative_covariance_or_model_selection_performed=False,
        contexts=len(contexts),historical_projections=len(projections),unique_families=len(repeated),
        repeated_family_context_counts={str(n):count for n,count in repeated.items() if count>1},
        pooled_projection_spearman_age_norm=spearman([r['history_age_h'] for r in projections],[r['coefficient_norm'] for r in projections]),
        pooled_projection_spearman_age_ratio_norm=spearman([r['history_to_nominal_age_ratio'] for r in projections],[r['coefficient_norm'] for r in projections]),
        within_context_spearman=quantiles(within),within_context_positive_count=sum(r>0 for r in within),
        within_context_equal_weight_centered_correlation=correlation([r['centered_history_age_h'] for r in projections],
            [r['centered_log1p_coefficient_norm'] for r in projections],[r['context_weight'] for r in projections]),
        oldest_has_largest_coefficient_energy_count=sum(r['oldest_epoch_has_largest_coefficient_energy'] for r in contexts),
        oldest_trace_share=quantiles([r['oldest_epoch_trace_energy_fraction'] for r in contexts]),
        oldest_principal_share=quantiles([r['oldest_epoch_principal_energy_fraction'] for r in contexts]),
        principal_energy_weighted_age_excess_h=quantiles([r['principal_energy_weighted_history_age_h']-r['unweighted_history_age_h'] for r in contexts]),
        between_context=between(contexts),between_family_means=between(by_family),
        capped=capped_group(True),uncapped=capped_group(False),
        inference='descriptive correlations only; short correlated TLE histories, shared baseline scales and near-unique families prevent an independent causal/generalization claim',
        parameter_energy_units='squared standardized coefficient, not physical state energy; three directions are not orthogonal')
    for name,records in [('history_age_projections.csv',projections),('history_age_contexts.csv',contexts),('history_age_family_means.csv',by_family)]:
        with (ROOT/name).open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    (ROOT/'history_age_summary.json').write_text(json.dumps(stats,indent=2,allow_nan=False)+'\n')
    assert len(contexts)==sum(r['status']=='ready' for r in rows)
    assert len(projections)==sum(len(r['historical_projection']) for r in rows if r['status']=='ready')
    assert all(r['history_age_h']>r['nominal_age_h']>0 for r in projections)
    for context in contexts:
        group=[r for r in projections if r['case']==context['case']]
        assert np.isclose(sum(r['trace_energy_fraction'] for r in group),1)
        assert np.isclose(sum(r['principal_energy_fraction'] for r in group),1)
        assert np.isclose(sum(context[key] for key in ['mean_motion_coefficient_energy_fraction',
            'inclination_coefficient_energy_fraction','RAAN_coefficient_energy_fraction']),1)
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==source_sha
    plot(contexts,projections)
    print(json.dumps(stats,indent=2))


def plot(contexts,points):
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(12.6,9),layout='constrained')
    ages=np.array([r['history_age_h'] for r in points]);norms=np.array([r['coefficient_norm'] for r in points])
    nominal=np.array([r['nominal_age_h'] for r in points])
    scatter=axes[0,0].scatter(ages,norms,c=nominal,cmap='viridis',s=19,alpha=.7)
    axes[0,0].set(title='Older TLEs have longer propagation horizons',xlabel='Historical propagation age at scan midpoint (h)',
        ylabel='Three-mode coefficient norm',yscale='log')
    fig.colorbar(scatter,ax=axes[0,0],label='Nominal propagation age (h)')
    axes[0,1].scatter([r['centered_history_age_h'] for r in points],
        [r['centered_log1p_coefficient_norm'] for r in points],s=19,alpha=.6,color='#2878b5')
    axes[0,1].axhline(0,color='black',lw=.7);axes[0,1].axvline(0,color='black',lw=.7)
    axes[0,1].set(title='Within each target context',xlabel='Historical age minus context mean (h)',
        ylabel='log(1 + coefficient norm) minus context mean')
    for capped,label,color,marker in [(False,'41 uncapped','#36a088','o'),(True,'55 capped at 16','#c96464','^')]:
        group=[r for r in contexts if r['capped']==capped]
        axes[1,0].scatter([r['mean_extra_age_h'] for r in group],
            [r['max_unbounded_covariance_eigenvalue'] for r in group],color=color,marker=marker,s=32,label=label,alpha=.8)
    axes[1,0].axhline(16,color='black',ls=':',lw=1)
    axes[1,0].set(title='Capping and extra historical propagation age',xlabel='Mean historical age minus nominal age (h)',
        ylabel='Largest covariance eigenvalue before clipping',yscale='log')
    axes[1,0].legend(frameon=False,fontsize=9)
    keys=['mean_motion_coefficient_energy_fraction','inclination_coefficient_energy_fraction','RAAN_coefficient_energy_fraction']
    groups=[[r for r in contexts if not r['capped']],[r for r in contexts if r['capped']]]
    bottom=np.zeros(2)
    for key,label,color in zip(keys,['Mean motion','Inclination','RAAN'],['#2878b5','#36a088','#f2ba54']):
        values=np.array([np.mean([r[key] for r in group]) for group in groups])
        axes[1,1].bar(['Uncapped','Capped'],values,bottom=bottom,color=color,label=label,width=.6)
        for x,(value,base) in enumerate(zip(values,bottom)):
            if value>.08:axes[1,1].text(x,base+value/2,f'{100*value:.1f}%',ha='center',va='center')
        bottom+=values
    axes[1,1].set(title='Mean standardized parameter-energy fractions',ylabel='Fraction of coefficient second-moment trace',ylim=(0,1))
    axes[1,1].legend(frameon=False,fontsize=9,loc='upper right')
    for ax in axes.flat:ax.grid(alpha=.14);ax.set_axisbelow(True)
    fig.suptitle('Historical forecast age is a confounder of the covariance proxy',fontsize=14)
    fig.supxlabel('96 ready contexts; 365 correlated historical projections; descriptive orbit-only diagnostics. Parameter energy is not physical state energy.',fontsize=9)
    for ext in ['png','pdf']:fig.savefig(ROOT/('history_age_diagnostic.'+ext),dpi=180)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12.6,4.7),layout='constrained')
    for ax,x,label in [(axes[0],nominal,'Nominal propagation age at scan midpoint (h)'),
                       (axes[1],ages/nominal,'Historical / nominal propagation age')]:
        scatter=ax.scatter(x,norms,c=ages,cmap='plasma',s=20,alpha=.7)
        ax.set(xlabel=label,ylabel='Three-mode coefficient norm',yscale='log')
        ax.grid(alpha=.14);ax.set_axisbelow(True)
        fig.colorbar(scatter,ax=ax,label='Historical propagation age (h)')
    axes[1].set_xscale('log')
    axes[0].set_title('Coefficient size versus nominal age')
    axes[1].set_title('Coefficient size versus relative forecast horizon')
    fig.suptitle('Both historical and nominal forecast horizons vary',fontsize=13)
    fig.supxlabel('365 projections from 96 ready contexts; correlated descriptive observations, not an error-calibration experiment.',fontsize=9)
    for ext in ['png','pdf']:fig.savefig(ROOT/('history_age_ratio_diagnostic.'+ext),dpi=180)
    plt.close(fig)


if __name__=='__main__':main()
