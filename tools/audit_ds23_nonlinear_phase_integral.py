"""Independent scalar orbit and Gaussian-density checks for the phase audit."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_frozen_precision import conditional_gaussian
from ds23_nonlinear_phase_integral import phase_frequency_samples
from probe_ds23_nonlinear_phase_integral import OUT,prepare_point,RULES
from probe_ds23_sign_carrier_position import context_signed
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from run_algo01_ds23_sample import read,write,sha


def main():
    document=read(OUT/'evaluation.json');checks=[];rows=[]
    for row in document['rows']:
        if row['status']!='complete':raise ValueError('nonlinear phase diagnostic has a failed case')
        context=context_signed(row['case'])
        for arm,result in row['arms'].items():
            position=np.asarray(result['anchor']);models,metadata,base=prepare_point(context,arm,position)
            for kind in ['curved','joint']:
                model=models[kind];data=metadata[kind];draw=model.draws(**RULES[1]);selected=[0,15,255]
                for index in selected:
                    phase=(draw[index]+base['phase_prior_mean'])*base['phase_sigma']
                    exact=paired_phase_frequency(base['p'].sky,data['times'],data['labels'],phase,*latlon(position))[0]
                    batch=phase_frequency_samples(base['p'].sky,data['times'],data['labels'],phase[None],*latlon(position))[0]
                    orbit_error=float(max(abs(batch-exact)))
                    if orbit_error>1e-7:raise ValueError('batched nonlinear orbit failed scalar replay')
                    correction=data['q']*(exact-data['intercept'])-data['phase_feature']@(draw[index]+base['phase_prior_mean'])
                    predicted=draw[index]@model.phase.T
                    residual=model.raw-predicted;rest=np.ones(len(model.precision),bool);rest[model.phase_indices]=False
                    values=[]
                    for y in [residual,residual-correction]:
                        fit=conditional_gaussian(y,model.rest,1/np.sqrt(model.w),np.ones(len(y)),np.ones(len(y)),model.precision[rest],1.)
                        values.append(fit['objective'])
                    direct=-.5*(values[1]-values[0]);importance=model.log_ratio(draw[index:index+1],correction[None])[0]
                    difference=float(abs(direct-importance))
                    if difference>1e-5:raise ValueError('nonlinear correction differs from independent Gaussian residual solve')
                    checks.append(dict(case=row['case'],arm=arm,kind=kind,draw=index,orbit_error_hz=orbit_error,
                        Gaussian_log_ratio_error=difference))
            diagnostics=result['diagnostics'];reliable=all(d['minimum_effective_sample_fraction']>.2
                and d['maximum_single_weight']<.05 for d in diagnostics[1:])
            centre=next(r for r in result['records'] if r['offset']==[0,0])
            rows.append(dict(case=row['case'],arm=arm,predicted_shift_km=diagnostics[1]['predicted_local_shift_norm_km'],
                seed_shift_disagreement_km=result['independent_seed_shift_difference_km'],importance_reliable=reliable,
                centre_joint_score_correction=centre['estimates'][1]['joint']['negative_twice_log_evidence_correction'],
                centre_mean_nonlinear_remainder_RMS_hz=centre['estimates'][1]['joint']['RMS_of_sample_mean_nonlinear_remainder_hz']))
    cases=[r['case'] for r in document['rows']];x=np.arange(len(cases))
    fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
    for arm,offset,color in [('c0',-.1,'tab:blue'),('fitted_c',.1,'tab:orange')]:
        selected=[next(r for r in rows if r['case']==case and r['arm']==arm) for case in cases]
        axes[0].scatter(x+offset,[r['predicted_shift_km']*1000 for r in selected],color=color,label=arm)
        axes[1].scatter(x+offset,[r['centre_mean_nonlinear_remainder_RMS_hz'] for r in selected],color=color,label=arm)
    axes[0].set(ylabel='Predicted local shift (m)',title='Local correction to current mode; no position adopted')
    axes[1].set(ylabel='Nominal phase remainder RMS (Hz)',title='Posterior mean correction at current mode')
    for ax in axes:
        ax.set_xticks(x,[c.split('-')[1] for c in cases]);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Nonlinear orbital phase under conditioned Gaussian/Gamma precisions\n'
        'Same labels, priors and data; shape modes/reference held fixed; local diagnosis is not full-model accuracy',fontsize=11)
    fig.savefig(OUT/'nonlinear_phase_diagnostics.png',dpi=160);plt.close(fig)
    write(OUT/'independent_replay_audit.json',dict(rows=rows,checks=checks,
        source_sha256=sha(OUT/'evaluation.json'),independent_scalar_orbit_and_Gaussian_ratio_checks=len(checks),
        maximum_orbit_difference_hz=max(c['orbit_error_hz'] for c in checks),
        maximum_Gaussian_log_ratio_error=max(c['Gaussian_log_ratio_error'] for c in checks),
        maximum_predicted_local_shift_km=max(r['predicted_shift_km'] for r in rows),
        maximum_independent_seed_shift_disagreement_km=max(r['seed_shift_disagreement_km'] for r in rows),
        all_importance_checks_pass=all(r['importance_reliable'] for r in rows),
        no_new_position_estimate_or_accuracy_gain=True,
        frozen_Gamma_and_shape_design_diagnostic_does_not_bound_all_nonlinear_hierarchical_models=True))
    print(dict(rows=len(rows),checks=len(checks),maximum_shift_m=max(r['predicted_shift_km'] for r in rows)*1000),flush=True)


if __name__=='__main__':main()
