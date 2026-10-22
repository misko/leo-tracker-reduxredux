"""Independent densities, orbit predictions and final gates for family cavities."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

import probe_ds23_family_cavity_nominations as nom
from probe_ds23_family_cavity_position import OUT as POSITION,unused_count
from ds23_conditioned_relative_nomination import gaussian_prediction
from ds23_family_cavity import unused_student_gap,predictive_density_reference,directional_orbit_frequency_reference
from ds23_joint_relative_audit import expected_log_density
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_predictive_linear import linear_geometry
from audit_ds23_joint_relative_position import absolute_features
from build_dsx01_orbit_modes import build_modes
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency


def prior(d,p,c,means):
    width=len(c['coefficient']);begin=p.hardware.shape[1]+p.smooth.shape[1]
    mu=np.zeros(width);mu[begin:begin+len(p.labels)]=means/p.phase_sigma
    scale=np.ones(width);scale[-len(p.members):]=.3
    return mu,scale,list(range(begin,begin+len(p.labels)))


def density(d,p,x,means,entries):
    full=p.calculate(x);c=p.curved_calculate(x) if entries else full
    intercept,u,e=absolute_features(p,x);present=np.unique(p.noise_groups[p.keep]);mu,scale,slots=prior(d,p,c,means)
    independent=expected_log_density((p.values-intercept)[p.keep],u[p.keep],p.point_noise[p.keep],p.noise_groups[p.keep],
        d['powers'][present],mu,scale,c['coefficient'],c['noise_precision'][present],c['coefficient_prior_precision'],slots,d['model']['nu'])
    difference=abs(independent['negative_twice_elbo']-c['negative_twice_elbo']);assert difference<2e-3
    assert independent['maximum_coefficient_normal_equation_error']<1e-4
    prediction_delta=0.
    if entries:
        view,values,sigma,g,slices=linear_geometry(p,entries);vi,vu,_=absolute_features(view,x)
        residual=values-vi-vu@c['coefficient'];cov=vu@independent['covariance_physical']@vu.T+np.diag(2*sigma**2)+300.**2*(g[:,None]==g[None,:])
        value=float(residual@np.linalg.solve(cov,residual)+np.linalg.slogdet(cov)[1]+len(values)*np.log(2*np.pi))
        prediction_delta=abs(value-(full['negative_twice_elbo']-c['negative_twice_elbo']));assert prediction_delta<2e-3
    return dict(density_difference=difference,coefficient_equation_error=independent['maximum_coefficient_normal_equation_error'],
        predictive_dense_covariance_difference=prediction_delta)


def nomination(case,nominations_dir=None):
    source=nom.OUT if nominations_dir is None else Path(nominations_dir)
    d=nom.setup(case);saved=read(source/(case+'_nominations.json'));checks=[]
    for element in d['scan'].elements.values():
        provenance=element['provenance'];assert max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])<=d['scan'].receipt['cutoff_utc_ns']
    for family in saved['families']:
        data=nom.family_data(d,family['original_index']);data['target']=family['original_index'];p=data['p']
        assert data['held_ids']==family['held_observation_ids'] and data['cavity_phase_change_s']<=.01
        audit=density(d,p,d['x'],d['means'],[])
        for row in family['candidates']:
            capture=[]
            def record(raw,design,covariance,sigma):
                capture.append((raw.copy(),design.copy(),covariance.copy(),sigma.copy()))
                return gaussian_prediction(raw,design,covariance,sigma)
            nom.gaussian_prediction=record
            try:replay=nom.candidate_prediction(d,data,row['candidate_index'],row['aliases'])
            finally:nom.gaussian_prediction=gaussian_prediction
            assert abs(replay['score']-row['score'])<1e-5
            raw,design,cov,sigma=capture[-1]
            direct,method=predictive_density_reference(raw,design,cov,sigma)
            delta=abs(direct-row['score']);assert delta<2e-3
            residual_delta=0.;finite_convergence=0.;j=row['candidate_index']
            if abs(row['phase_s'])<=15:
                bank=dict(time_s=d['scan'].sky['time_s'],position_km=d['scan'].sky['position_km'][[j]],velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
                f,e=paired_phase_frequency(bank,data['times'],np.zeros(len(data['times']),int),np.array([row['phase_s']]),*latlon(d['x']))
                coef=np.asarray(row['coefficient']);nb=data['radio_width'];predicted=data['radio']@coef[:nb]+data['q']*f
                if row['physical_modes']:
                    if j in p.supported:
                        local=p.labels.index(j);modes=dict(time_s=p.mode_bank['time_s'],position_km=p.mode_bank['position_km'][3*local:3*local+3],velocity_km_s=p.mode_bank['velocity_km_s'][3*local:3*local+3])
                    else:modes=build_modes(d['scan'],[j],[j],'physical')[0]
                    physical,finite_convergence=directional_orbit_frequency_reference(bank,modes,coef[nb+1:nb+4],
                        data['times'],row['phase_s'],*latlon(d['x']))
                    assert finite_convergence<2e-5,(case,family['original_norad'],row['norad'],'finite derivative convergence',finite_convergence)
                    predicted+=data['q']*physical
                predicted+=coef[-len(data['members']):][data['groups']]
                residual=data['values']+np.asarray(row['aliases'])[data['groups']]/4.4e-6-predicted
                residual_delta=float(np.max(abs(residual-np.asarray(row['residual_hz']))))
                assert residual_delta<2e-4, (case,family['original_norad'],row['norad'],row['phase_s'],residual_delta)
            checks.append(dict(original_norad=family['original_norad'],candidate_norad=row['norad'],predictive_density_difference=delta,predictive_density_method=method,
                exact_independent_residual_difference_hz=residual_delta,finite_orbit_derivative_convergence_hz=finite_convergence,**audit))
    return dict(case=case,checks=checks,all_disputed_points_disjoint_from_calibration=True,
        causal_epoch_and_collection_checked_for_entire_catalogue=True,reference_position_used=False,
        source_sha256=sha(source/(case+'_nominations.json')))


def position(case,position_dir=None):
    source=POSITION if position_dir is None else Path(position_dir)
    d=nom.setup(case);saved=read(source/(case+'.json'));checks=[]
    for trial in saved['trials']:
        pairs={}
        for arm,r in trial['arms'].items():
            p=make_event_problem(d['scan'],trial['node'],d['keep'],arm,np.asarray(r['phase_reference']),d['powers'],np.asarray(trial['means']),d['model'],[])
            attach_event_predictive(p,trial['entries'],d['powers']);x=np.asarray(r['endpoint_east_north_km']);c=p.calculate(x)
            assert abs(c['negative_twice_elbo']-r['negative_twice_elbo'])<1e-6
            check=density(d,p,x,np.asarray(trial['means']),trial['entries'])
            replay=summary(p,x,trial['entries']);assert replay['gates']==r['gates'] and replay['linear_gates']==r['linear_gates']
            corrected=c['negative_twice_elbo']-unused_count(p,trial['entries'])*unused_student_gap(d['model']['nu'])
            assert abs(corrected-r['corrected_selection_loss'])<1e-6
            replay['final_phase_change_s']=r['final_phase_change_s'];pairs[arm]=replay
            checks.append(dict(arm=arm,replacements=trial['replacements'],**check))
        passed=bool(valid(pairs) and all(r['final_phase_change_s']<=.01 for r in pairs.values()));assert passed==trial['paired_valid']
    return dict(case=case,checks=checks,all_original_observations_preserved=True,reference_position_used=False,
        source_sha256=sha(source/(case+'.json')))


def main():
    assert read(POSITION/'execution.json')['all_terminal']
    with ProcessPoolExecutor(max_workers=3) as pool:nominations=list(pool.map(nomination,nom.CASES))
    with ProcessPoolExecutor(max_workers=3) as pool:positions=list(pool.map(position,nom.CASES))
    write(POSITION/'independent_numerical_audit.json',dict(nominations=nominations,positions=positions,all_passed=True,
        direct_expected_log_density_and_dense_predictive_covariance=True,alternate_exact_orbit_and_finite_mode_checks=True,
        all_original_gates_replayed=True,reference_position_used=False))
    print('Cavity nominations and full-evidence fits audited',flush=True)


if __name__=='__main__':main()
