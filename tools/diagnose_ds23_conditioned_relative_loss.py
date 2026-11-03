"""Retrospective DBG01 fixed-position falsification; never an inference input."""

from concurrent.futures import ProcessPoolExecutor
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_conditioned_relative_position import OUT as POSITION,context_selected
from probe_ds23_conditioned_relative_nomination import OUT
from probe_ds23_joint_relative_position import OUT as JOINT,context,make,relative_gates
from prototype_dsx01_continuous_position import CENTER
from run_algo01_ds23_sample import read,write

REFERENCE=(37.849061591561885,-122.48574968092912)
REFERENCE_XY=np.array([(REFERENCE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),(REFERENCE[0]-CENTER[0])*111])
CASES=['DS23-0240','DS23-0331','DS23-0293']


def one(case):
    selected=read(POSITION/(case+'_conditioned_best.json'));baseline=read(JOINT/'confirmation20'/(case+'_quarantined_GLRT.json'))
    rows=[]
    for model in ['original_relative','conditioned_best']:
        d=context(case) if model=='original_relative' else context_selected(case,'conditioned_best')
        for arm in ['c0','fitted_c']:
            points=dict(GLRT_endpoint=np.asarray(baseline['arms'][arm]['endpoint_east_north_km']),
                selected_endpoint=np.asarray(selected['arms'][arm]['endpoint_east_north_km']),evaluation_reference=REFERENCE_XY)
            for name,x in points.items():
                reference=np.zeros(len(d['all_labels']));history=[]
                for _ in range(10):
                    p=make(d,arm,reference,True,float(np.sqrt(2)*300));phase=np.clip(p.state(x)['phases'][d['all_labels']],-15,15)
                    change=float(np.max(abs(phase-reference)));history.append(change);reference=phase
                full=p.calculate(x);c=p.curved_calculate(x) if d['original_entries'] else full
                prior=c['latent_coefficient']**2*c['coefficient_prior_precision'];begin=p.hardware.shape[1]+p.smooth.shape[1]
                old=p.joint_old_width;rf=p.relative_problem
                blocks=dict(radio=list(range(p.hardware.shape[1])),smooth=list(range(p.hardware.shape[1],begin)),
                    phase=list(range(begin,begin+len(p.labels)))+list(p.joint_column_plan['new_phases'].values()),
                    orbit=list(range(begin+len(p.labels),old-len(p.members))),fragment=list(range(old-len(p.members),old)),
                    relative_constant=p.relative_mapping[-len(rf.groups):].tolist())
                blocks['orbit']+= [index+k for index in p.joint_column_plan['new_modes'].values() for k in range(3)]
                assert sorted(v for vs in blocks.values() for v in vs)==list(range(len(prior)))
                terms={'prior_'+key:float(prior[values].sum()) for key,values in blocks.items()}
                terms.update(weighted_data=c['quadratic']-float(prior.sum()),logvolume=c['logvolume'],
                    noise_Gamma=c['noise_gamma_cost'],prior_Gamma=c['prior_gamma_cost'],normalization=c['normalization_constant'],
                    predictive=full['negative_twice_elbo']-c['negative_twice_elbo'])
                assert abs(sum(terms.values())-full['negative_twice_elbo'])<1e-6
                residual,elevation,phases=p.exact_relative(x)
                rows.append(dict(case=case,model=model,arm=arm,point=name,position_east_north_km=x,
                    loss=full['negative_twice_elbo'],terms=terms,phase_refresh_changes_s=history,
                    GLRT_RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
                    relative_RMS_hz=float(np.sqrt(np.mean(residual**2))) if residual is not None else None,
                    relative_gates=relative_gates(p,x,float(np.sqrt(2)*300)),
                    RF_curves=[dict(group=g['group'],times=rf.times[sl],residual_hz=residual[sl] if residual is not None else None)
                        for g,sl in zip(rf.groups,rf.slices,strict=True)],
                    explicit_evaluation_position_diagnostic_not_algorithm_selection=True))
    return rows


def main():
    with ProcessPoolExecutor(max_workers=3) as pool:rows=[r for batch in pool.map(one,CASES) for r in batch]
    write(OUT/'fixed_position_loss_diagnostic.json',dict(rows=rows,reference_position_used_only_in_explicit_diagnostic=True,
        no_GPS_selected_model_hyperparameter_or_repair=True,
        raw_losses_from_different_RF_masks_not_ranked=True,
        retrospective_cases_illustrate_worsening_improvement_and_rejected_RF_curve=True))
    keys=['weighted_data','prior_radio','prior_smooth','prior_phase','prior_orbit','prior_fragment','prior_relative_constant','logvolume','noise_Gamma','prior_Gamma','predictive']
    fig,axes=plt.subplots(1,3,figsize=(15,6),layout='constrained',sharey=True)
    for ax,case in zip(axes,CASES,strict=True):
        for model,offset,color in [('original_relative',-.18,'#777777'),('conditioned_best',.18,'#168b91')]:
            records=[r for r in rows if (r['case'],r['model'],r['arm'])==(case,model,'fitted_c')]
            a=next(r for r in records if r['point']=='selected_endpoint');b=next(r for r in records if r['point']=='evaluation_reference')
            delta=[b['terms'][key]-a['terms'][key] for key in keys]
            ax.barh(np.arange(len(keys))+offset,delta,height=.33,color=color,label=model)
        ax.axvline(0,c='black',lw=.7);ax.grid(axis='x',alpha=.2);ax.set(title=case,xlabel='Reference minus selected-endpoint loss contribution')
    axes[0].set_yticks(range(len(keys)),keys);axes[0].invert_yaxis();axes[-1].legend(fontsize=7)
    fig.suptitle('DBG01 fixed-position falsification · positive favors displaced endpoint\nNuisances refreshed at each fixed location; within-model differences only; GPS used solely for diagnosis')
    fig.savefig(OUT/'fixed_position_loss_diagnostic.png',dpi=160);plt.close(fig)
    print('Fixed-position diagnostics complete',len(rows),flush=True)


if __name__=='__main__':main()
