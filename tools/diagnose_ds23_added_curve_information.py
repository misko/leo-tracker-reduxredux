"""Conditional local information in accepted added curves, without GPS input."""

from pathlib import Path
import numpy as np
from ds23_new_curved_family import make_new_family_problem
from ds23_position_information import marginal_position_information, ellipse_scales
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from probe_ds23_new_family_anchor_only import prepare as anchor_prepare, BULK as ANCHOR
from probe_ds23_independent_secondary import prepare as independent_prepare, BULK as INDEPENDENT
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import geodetic_to_ecef_km

OUT=ROOT/'reports/2026_10_21_ds23_added_curve_information'


def relative_increment(before,after):
    eigen,axes=np.linalg.eigh(before);root=(axes*(1/np.sqrt(eigen)))@axes.T
    value=root@(after-before)@root
    return np.linalg.eigvalsh((value+value.T)/2)


def one(case,root,prepare,arm):
    saved=read(root/(case+'.json'));d=prepare(case);d['extra']=saved['extra_entries']
    record=saved['arms'][arm];x=np.array(record['endpoint_east_north_km'])
    p=make_new_family_problem(d,arm,np.array(record['phase_reference']),True);c=p.calculate(x);coef=c['coefficient']
    ev,ey,_,eg,es=linear_geometry(p,d['extra']);nextra=len(d['extra'])
    anchors=np.concatenate([d['anchors'][e['component']] for e in d['extra']]);kappa=np.zeros(len(ey));sigma=np.zeros(len(ey))
    for entry,sl in zip(d['extra'],es,strict=True):
        cov=d['covariance'][entry['component']];kappa[sl]=cov['kappa'];sigma[sl]=cov['marginal_sigma_hz']*np.sqrt(1-cov['kappa']**2)
    if d['original_entries']:
        lv,ly,lsigma,lg,lsl=linear_geometry(p,d['original_entries'])
        nlin=len(d['original_entries'])
    else:
        lv=None;nlin=0
    def design(position):
        old=geometry_features(p,position,0.);ou=np.column_stack((old['features'],np.zeros((len(p.values),nextra))))
        extra=geometry_features(ev,position,0.);eu=np.column_stack((extra['features'],np.eye(nextra)[eg]*300))
        old_mean=p.q*old['intercept']+ou@coef;new_mean=ev.q*extra['intercept']+eu@coef
        combined=eu-kappa[:,None]*ou[anchors];conditional=new_mean-kappa*old_mean[anchors]
        if lv is not None:
            linear=geometry_features(lv,position,0.);lu=np.column_stack((linear['features'],np.zeros((len(ly),nextra))))
            linear_mean=lv.q*linear['intercept']+lu@coef
        else:
            lu=np.empty((0,len(coef)));linear_mean=np.array([])
        return dict(old=ou[p.keep],extra=combined,linear=lu,
                    old_mean=old_mean[p.keep],new_mean=conditional,raw_new_mean=new_mean,linear_mean=linear_mean)
    current=design(x);columns={name:[] for name in ['old_mean','new_mean','raw_new_mean','linear_mean']}
    for k in [0,1]:
        delta=np.zeros(2);delta[k]=.01;plus,minus=design(x+delta),design(x-delta)
        for name in columns:columns[name].append((plus[name]-minus[name])/.02)
    derivative={name:np.column_stack(values) for name,values in columns.items()}
    old_w=d['powers'][p.noise_groups[p.keep]]*c['noise_precision'][p.noise_groups[p.keep]]/p.point_noise[p.keep]**2
    new_w=np.asarray(p.joint_conditional_powers)[eg]*c['joint_secondary_noise_precision'][eg]/sigma**2
    old_u=np.column_stack((current['old'],np.zeros((len(current['old']),nlin))))
    new_u=np.column_stack((current['extra'],np.zeros((len(current['extra']),nlin))))
    if nlin:
        linear_u=np.column_stack((current['linear'],np.eye(nlin)[lg]*300));linear_w=1/(2*lsigma**2)
    else:
        linear_u=np.empty((0,len(coef)));linear_w=np.array([])
    before_u=np.vstack((old_u,linear_u));before_j=np.vstack((derivative['old_mean'],derivative['linear_mean']));before_w=np.r_[old_w,linear_w]
    after_u=np.vstack((before_u,new_u));after_j=np.vstack((before_j,derivative['new_mean']));after_w=np.r_[before_w,new_w]
    prior=np.r_[c['coefficient_prior_precision'],np.ones(nlin)]
    phase_begin=p.hardware.shape[1]+p.smooth.shape[1];phase_indices=np.arange(phase_begin,phase_begin+len(p.labels))
    results={}
    for name,kept in [('phase_uncertain',np.arange(len(prior))),('phase_fixed_at_RF_fit',np.setdiff1d(np.arange(len(prior)),phase_indices))]:
        before=marginal_position_information(before_j,before_u[:,kept],before_w,prior[kept])
        after=marginal_position_information(after_j,after_u[:,kept],after_w,prior[kept])
        increment=after-before
        if np.linalg.eigvalsh(increment).min() < -1e-7:raise ValueError('added evidence lost Gaussian information')
        raw=derivative['new_mean'].T@(derivative['new_mean']*new_w[:,None])
        results[name]=dict(before_information=before,after_information=after,increment_information=increment,
            before_scales=ellipse_scales(before),after_scales=ellipse_scales(after),
            relative_information_increment_eigenvalues=relative_increment(before,after),
            fraction_of_added_fixed_nuisance_information_retained=float(np.trace(increment)/np.trace(raw)))
    angles=[]
    state=p.state(x)
    for e,sl in zip(d['extra'],es,strict=True):
        primary_local=int(p.flat_labels[anchors[sl][0]]);other_local=p.labels.index(e['candidate_index']);time=float(np.mean(ev.flat_times[sl]))
        position,_=paired_phase_states(p.sky,np.array([time,time]),np.array([primary_local,other_local]),state['phases'][p.labels])
        vector=position-geodetic_to_ecef_km(*latlon(x),0.);vector/=np.linalg.norm(vector,axis=1)[:,None]
        angles.append(float(np.rad2deg(np.arccos(np.clip(vector[0]@vector[1],-1,1)))))
    return dict(case=case,arm=arm,results=results,sky_separations_deg=angles,
        conditional_to_unconditioned_added_gradient_norm_ratio=float(np.linalg.norm(derivative['new_mean'])/np.linalg.norm(derivative['raw_new_mean'])),
        fitted_position_used_no_GPS=True,result_sha256=sha(root/(case+'.json')),
        original_curved_points=int(p.keep.sum()),original_predictive_points=len(linear_w),added_curved_points=len(ey))


def main():
    OUT.mkdir(exist_ok=True)
    jobs=[('DS23-0132',ANCHOR,anchor_prepare),('DS23-0377',ANCHOR,anchor_prepare),('DS23-0014',INDEPENDENT,independent_prepare)]
    rows=[one(case,root,prepare,arm) for case,root,prepare in jobs for arm in ['c0','fitted_c']]
    write(OUT/'evaluation.json',dict(rows=rows,conditional_local_Gaussian_information_only=True,
        Gamma_precisions_held_at_fitted_values=True,no_covariance_orientation_derivative_or_Gamma_feedback_terms=True,
        same_prior_and_precisions_in_before_after_comparisons=True,
        phase_fixed_control_uses_RF_estimates_not_true_phases=True,not_calibrated_position_confidence_or_localization_error=True,
        no_GPS_or_observations_modified=True))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(14,4.5),constrained_layout=True)
    for ax,(case,_,_) in zip(axes,jobs,strict=True):
        row=next(r for r in rows if r['case']==case and r['arm']=='fitted_c')
        for i,name in enumerate(['phase_uncertain','phase_fixed_at_RF_fit']):
            values=np.array(row['results'][name]['relative_information_increment_eigenvalues'])*100
            bars=ax.bar(np.array([0,1])+(i-.5)*.32,values,width=.3,label='Phase uncertain' if i==0 else 'Phase fixed at RF estimate')
            ax.bar_label(bars,fmt='%.2f',fontsize=8)
        ax.set(xticks=[0,1],xticklabels=['Weaker direction','Stronger direction'],ylabel='Additional conditional Gaussian information (%)',title=case)
        ax.grid(axis='y',alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Why additional precise curves need not materially improve position\nLocal mean-design diagnostic at RF fits; Gamma precision fixed; this is not an accuracy or confidence claim')
    fig.savefig(OUT/'added_position_information.png',dpi=160);plt.close(fig)
    for row in rows:
        print(row['case'],row['arm'],'sky angle',row['sky_separations_deg'],'gradient ratio',row['conditional_to_unconditioned_added_gradient_norm_ratio'],
            {k:v['relative_information_increment_eigenvalues'] for k,v in row['results'].items()},flush=True)


if __name__=='__main__':main()
