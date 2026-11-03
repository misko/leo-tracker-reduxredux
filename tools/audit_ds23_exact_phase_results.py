"""Independent grid-orbit/density and original-position endpoint replay."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from refine_ds23_differential_phase_catalogue import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import summary
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.retained_track_likelihood import PERIOD

OUT=ROOT/'reports/2026_10_22_ds23_exact_differential_phase'


def audit_group(saved):
    case,group=saved['case'],saved['group'];root=Path(saved['source']);scan,means,widths,signed=context(case)
    source=read(root/'evaluation.json');protocol=read(root/'protocol.json')
    ids={r['probe'] for r in protocol['jobs'] if r['group']==group}
    rf=sorted([r for r in source['rows'] if r['case']==case and r['probe'] in ids and r['status']=='complete' and r['two_components_qualified']],key=lambda r:r['time_s'])
    t=np.array([r['time_s'] for r in rf]);y=np.array([r['refined_second_value']-r['refined_first_value'] for r in rf])
    noise=saved['noise_sigma_hz'];maximum=0.;score_difference=0.;count=0
    for name,result in saved['results'].items():
        rows=result['all_refined'];indices=np.array([i for r in rows for i in [r['first_index'],r['second_index']]])
        phases=np.array([p for r in rows for p in [r['phase_first_s'],r['phase_second_s']]])
        bank=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][indices],velocity_km_s=scan.sky['velocity_km_s'][indices])
        position=np.zeros(2) if name=='regional_centre' else np.asarray(signed['policy_arms']['c0']['endpoint_east_north_km'])
        f,_=phase_frequency_grid(bank,t,*latlon(position),phase_seconds=phases,rf_hz=saved['lane'][2])
        difference=f[1::2]-f[::2]
        for k,r in enumerate(rows):
            raw=y+r['difference_alias']*PERIOD-difference[k]
            residual=raw-r['relative_bias_hz'];exact=r['exact_fit']
            maximum=max(maximum,float(np.max(abs(residual-exact['residual_hz']))))
            labels=[r['first_index'],r['second_index']];u=(np.asarray(exact['phase_s'])-means[labels])/widths[labels]
            # Independent Sherman-Morrison density for a Gaussian relative constant.
            cost=float(raw@raw/noise**2-1000.**2*raw.sum()**2/(noise**2*(noise**2+len(raw)*1000.**2))
                +np.log1p(len(raw)*1000.**2/noise**2)+u@u)
            score_difference=max(score_difference,abs(cost-exact['profile_cost']))
            if exact['local_Laplace_score'] is not None:
                assert abs(cost+np.linalg.slogdet(exact['observed_half_cost_hessian'])[1]-exact['local_Laplace_score'])<1e-4
            count+=1
    assert maximum<1e-7 and score_difference<1e-4
    return dict(case=case,group=group,exact_phase_proposals_replayed=count,
        maximum_independent_grid_residual_difference_hz=maximum,maximum_profile_cost_difference=score_difference)


def audit_case(case):
    source=OUT/'phase_initialization';scan,node,mask,powers,means,hyper,entries,signed,binding=context_signed(case)
    original=signed['policy_arms'];results={};audits=[];fitted_count=0
    for name in ['zero','prior_mean','negative_prior_mean','RF_median','RF_consensus']:
        r=dict(status='incumbent',arms=original,paired_valid=True,phase_converged=True) if name=='zero' else read(source/(case+'_'+name+'.json'))
        if r['status']=='failed':raise ValueError(f"{case}/{name}: {r['error']}")
        pair={};maximum=0.
        for arm,saved in r['arms'].items():
            p=make_event_problem(scan,node,mask,arm,np.asarray(saved['phase_reference']),powers,means,hyper,[])
            attach_event_predictive(p,entries,powers);x=np.asarray(saved['endpoint_east_north_km'])
            loss=p.calculate(x)['negative_twice_elbo'];maximum=max(maximum,abs(loss-saved['negative_twice_elbo']))
            assert maximum<1e-6
            pair[arm]=summary(p,x,entries)
            # Legacy incumbent receipts do not all expose the same history
            # fields. Check the actual phase fixed point at the replayed state.
            actual_change=float(np.max(abs(np.asarray(p.state(x)['phases'])[p.labels]-np.asarray(saved['phase_reference']))))
            pair[arm]['final_phase_change_s']=actual_change
        gates=bool(valid(pair));assert gates==r['paired_valid']
        if r['status']=='complete':fitted_count+=2
        audits.append(dict(case=case,seed=name,status=r['status'],paired_gates_pass=gates,
            phase_converged=r['phase_converged'],maximum_normalized_loss_difference=maximum))
        results[name]=r
    def choose(names):
        best='zero';gain=0.
        for name in names:
            r=results[name]
            if not r['paired_valid'] or not r['phase_converged']:continue
            improvement=min(original[a]['negative_twice_elbo']-r['arms'][a]['negative_twice_elbo'] for a in original)
            if improvement>gain:best,gain=name,improvement
        return dict(seed=best,minimum_paired_loss_gain=gain,arms=results[best]['arms'])
    policies=dict(budget_matched_TLE=choose(['zero','prior_mean','negative_prior_mean']),
        RF_median=choose(['zero','prior_mean','RF_median']),RF_consensus=choose(['zero','prior_mean','RF_consensus']))
    displacement={name:max(float(np.linalg.norm(np.asarray(v['endpoint_east_north_km'])-original[a]['endpoint_east_north_km'])) for a,v in r['arms'].items()) for name,r in results.items()}
    return dict(case=case,audits=audits,results=results,policies=policies,
        maximum_endpoint_shift_km=displacement,actual_new_fitted_arms=fitted_count,
        signed_sha256=sha(binding),no_GPS_in_numerical_audit=True)


def main():
    refinements=read(OUT/'refined/execution.json');initial=read(OUT/'phase_initialization/execution.json')
    assert refinements['all_terminal'] and initial['all_terminal']
    assert all(r['status']=='complete' for r in refinements['rows'])
    with ProcessPoolExecutor(max_workers=8) as pool:groups=list(pool.map(audit_group,refinements['rows']))
    write(OUT/'independent_group_density_audit.json',dict(groups=groups,all_terminal=True,
        source_refinement_sha256=sha(OUT/'refined/execution.json'),
        exact_phase_proposals_replayed=sum(g['exact_phase_proposals_replayed'] for g in groups)))
    cases=read(OUT/'phase_initialization/protocol.json')['cases']
    with ProcessPoolExecutor(max_workers=6) as pool:scans=list(pool.map(audit_case,cases))
    # Geographic evaluation follows all independent numerical and gate checks.
    from report_algo02_ds23 import position_error
    rows=[]
    for scan in scans:
        for policy,r in scan['policies'].items():
            for arm,a in r['arms'].items():rows.append(dict(case=scan['case'],policy=policy,arm=arm,
                selected_seed=r['seed'],position_error_km=position_error(a['endpoint_latlon']),
                original_error_km=position_error(scan['results']['zero']['arms'][arm]['endpoint_latlon'])))
    statistics={}
    for policy in ['budget_matched_TLE','RF_median','RF_consensus']:
        statistics[policy]={}
        for arm in ['c0','fitted_c']:
            selected=[r for r in rows if r['policy']==policy and r['arm']==arm]
            errors=np.array([r['position_error_km'] for r in selected]);old=np.array([r['original_error_km'] for r in selected])
            statistics[policy][arm]=dict(count=len(errors),mean_km=float(errors.mean()),median_km=float(np.median(errors)),
                incumbent_mean_km=float(old.mean()),incumbent_median_km=float(np.median(old)),maximum_absolute_error_change_m=float(np.max(abs(errors-old))*1000))
    write(OUT/'independent_refinement_and_position_audit.json',dict(groups=groups,scans=scans,rows=rows,statistics=statistics,
        all_terminal=True,exact_phase_proposals_replayed=sum(g['exact_phase_proposals_replayed'] for g in groups),
        actual_new_fitted_endpoint_arms=sum(s['actual_new_fitted_arms'] for s in scans),
        no_new_measurements_priors_or_identities_in_position_fits=True,full_DS23_benchmark_unchanged=True))
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    x=np.arange(len(scans));names=[s['case'].split('-')[1] for s in scans]
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        for seed,color in [('prior_mean','#777777'),('negative_prior_mean','#c18c35'),('RF_median','#168b91'),('RF_consensus','#8765b4')]:
            shift=[np.linalg.norm(np.asarray(s['results'][seed]['arms'][arm]['endpoint_east_north_km'])-s['results']['zero']['arms'][arm]['endpoint_east_north_km'])*1000 for s in scans]
            ax.scatter(x,shift,s=20,color=color,label=seed)
        ax.set_xticks(x,names,rotation=70,fontsize=7);ax.set(title=arm,ylabel='Endpoint displacement from zero-phase start (m)',xlabel='DS23 scan');ax.grid(alpha=.2)
    axes[1].legend(fontsize=8);fig.suptitle('Phase initialization with unchanged observations, identities and priors ·23 scans')
    fig.tight_layout();fig.savefig(OUT/'phase_initialization_displacements.png',dpi=160);plt.close(fig)
    print(dict(refined_proposals=sum(g['exact_phase_proposals_replayed'] for g in groups),
        new_endpoint_arms=sum(s['actual_new_fitted_arms'] for s in scans),statistics=statistics),flush=True)


if __name__=='__main__':main()
