"""Independent cavity densities, nonlinear predictions and common mixture checks."""

from pathlib import Path
import numpy as np

import probe_ds23_family_cavity_nominations as old
from probe_ds23_position_cavity import position_covariance,prove_exclusion,coarse
from ds23_position_cavity import normal_grid,reweight_nodes
from audit_ds23_family_cavity import density
from ds23_family_cavity import predictive_density_reference,directional_orbit_frequency_reference
from ds23_conditioned_relative_nomination import gaussian_prediction
from ds23_frequency_events import make_event_problem
from ds23_height_problem import geometry_features
from build_dsx01_orbit_modes import build_modes
from run_algo01_ds23_sample import read,sha
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency


def direct_mixture(scores,log_weights):
    scores=np.asarray(scores);minimum=float(scores.min())
    return float(minimum-2*np.log(np.exp(log_weights)@np.exp((minimum-scores)/2)))


def exact_residual(d,data,row):
    p=data['p'];j=row['candidate_index'];phase=row['phase_s']
    if abs(phase)>15:return 0.
    bank=dict(time_s=d['scan'].sky['time_s'],**{k:d['scan'].sky[k][[j]] for k in ['position_km','velocity_km_s']})
    f,e=paired_phase_frequency(bank,data['times'],np.zeros(len(data['times']),int),np.array([phase]),*latlon(d['x']))
    coefficient=np.asarray(row['coefficient']);nb=data['radio_width'];predicted=data['radio']@coefficient[:nb]+data['q']*f
    if row['physical_modes']:
        if j in p.supported:
            local=p.labels.index(j);modes=dict(time_s=p.mode_bank['time_s'],**{k:p.mode_bank[k][3*local:3*local+3] for k in ['position_km','velocity_km_s']})
        else:modes=build_modes(d['scan'],[j],[j],'physical')[0]
        physical,convergence=directional_orbit_frequency_reference(bank,modes,coefficient[nb+1:nb+4],data['times'],phase,*latlon(d['x']))
        assert convergence<2e-5
        predicted+=data['q']*physical
    predicted+=coefficient[-len(data['members']):][data['groups']]
    residual=data['values']+np.asarray(row['aliases'])[data['groups']]/4.4e-6-predicted
    error=float(np.max(abs(residual-np.asarray(row['residual_hz']))));assert error<2e-4
    assert abs(float(e.min())-row['minimum_elevation_deg'])<1e-8
    return error


def svd_position_reference(p,x,powers):
    c=p.calculate(x);u=c['features'];columns=[]
    for axis in range(2):
        step=np.eye(2)[axis]*.01;expected=[]
        for z in [x+step,x-step]:
            g=geometry_features(p,z,0.);expected.append(p.q*g['intercept']+g['features']@c['coefficient'])
        columns.append((expected[0]-expected[1])/.02)
    design=np.column_stack((*columns,u))[p.keep]
    weight=powers[p.noise_groups[p.keep]]*c['noise_precision'][p.noise_groups[p.keep]]/p.point_noise[p.keep]**2
    system=np.vstack((design*np.sqrt(weight[:,None]),np.diag(np.sqrt(np.r_[0.,0.,c['coefficient_prior_precision']]))))
    _,values,vectors=np.linalg.svd(system,full_matrices=False)
    return ((vectors.T/values**2)@vectors)[:2,:2]


def nomination(case,nominations_dir):
    directory=Path(nominations_dir);saved=read(directory/(case+'_nominations.json'));d=old.setup(case);checks=[];family_checks=[]
    assert saved['status']=='complete';variant=saved['variant'];base=d['base']
    for element in d['scan'].elements.values():
        v=element['provenance'];assert max(v['element_epoch_utc_ns'],v['collected_utc_ns'])<=d['scan'].receipt['cutoff_utc_ns']
    for family,cavity in zip(saved['families'],saved['cavities'],strict=True):
        target=family['original_index'];assert target==cavity['original_index'];keep=d['keep'].copy()
        for row,sl in zip(base.rows,base.slices,strict=True):
            if row['candidate_index']==target:keep[sl]=False
        np.testing.assert_array_equal(keep,cavity['calibration_mask'])
        fit=cavity['fit'];reference=np.zeros(len(d['means']));x=np.zeros(2)
        for step in fit['history']:
            np.testing.assert_array_equal(step['fit']['history'][0]['parameters'],x)
            p=make_event_problem(d['scan'],d['node'],keep,'c0',reference,d['powers'],d['means'],d['model'],[])
            x=np.asarray(step['fit']['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            assert abs(float(np.max(abs(phase-reference)))-step['phase_change_s'])<1e-10
            final_reference=reference;reference=phase
        np.testing.assert_allclose(final_reference,fit['phase_reference'],rtol=0,atol=1e-12)
        assert abs(p.calculate(x)['negative_twice_elbo']-fit['negative_twice_elbo'])<1e-6
        if fit['final_phase_change_s']>.01:
            assert family['skipped_reason']==cavity['skipped_reason']=='other_family_position_phase_not_converged'
            assert family['best'] is None and family['predictive_gain'] is None and family['candidates']==[]
            prove_exclusion(p,x)
            family_checks.append(dict(original_norad=family['original_norad'],cold_other_family_position_fit_replayed=True,
                nomination_skipped_nonconverged_other_family_position=True,phase_change_s=fit['final_phase_change_s']))
            continue
        center_d=dict(d,x=x,reference=np.asarray(fit['phase_reference']));center=old.family_data(center_d,target);center['target']=target
        covariance=position_covariance(center['p'],x,d['powers']);np.testing.assert_allclose(covariance,cavity['position_covariance_km2'],rtol=1e-8,atol=1e-10)
        independent=svd_position_reference(center['p'],x,d['powers']);relative=float(np.linalg.norm(independent-covariance)/np.linalg.norm(covariance));assert relative<1e-5
        grid=normal_grid(x,covariance,center['p'].lower,center['p'].upper)
        np.testing.assert_allclose(grid['positions'],cavity['positions'],rtol=0,atol=1e-8)
        prove_exclusion(center['p'],x)
        nodes=[];losses=[];coarse_rows=[];center_index=None
        for z in grid['positions']:
            nd=dict(center_d,x=z);data=center if np.max(abs(z-x))<1e-10 else old.family_data(nd,target);data['target']=target
            if data is center:center_index=len(nodes)
            assert data['held_ids']==family['held_observation_ids']
            # A fresh, uncached objective is tested at every mixture node.
            prove_exclusion(data['p'],z)
            node_density=density(nd,data['p'],z,d['means'],[])
            nodes.append((nd,data,node_density));losses.append(data['p'].calculate(z)['negative_twice_elbo']);coarse_rows.append(coarse(nd,data,z))
        logw=reweight_nodes(grid['positions'],x,covariance,grid['log_weights'],losses)
        np.testing.assert_allclose(logw,cavity['log_weights'],rtol=0,atol=1e-8)
        score_grid=np.array([c['score'] for c in coarse_rows]);valid=np.any(np.isfinite(score_grid),axis=0)
        scores=np.full(score_grid.shape[1],np.inf)
        for j in np.flatnonzero(valid):scores[j]=direct_mixture(score_grid[:,j],logw)
        screen=coarse_rows[center_index]['score'] if variant=='point_cavity' else scores
        expected=[target]+[int(j) for j in np.argsort(screen) if np.isfinite(screen[j]) and j!=target][:7]
        assert [r['candidate_index'] for r in family['candidates']]==expected
        for candidate in family['candidates']:
            components=[(center_index,candidate)] if variant=='point_cavity' else list(enumerate(candidate['components']))
            independent_scores=[]
            for k,row in components:
                nd,data,node_density=nodes[k];capture=[]
                def record(raw,design,cov,sigma):
                    capture[:]=[(raw.copy(),design.copy(),cov.copy(),sigma.copy())]
                    return gaussian_prediction(raw,design,cov,sigma)
                old.gaussian_prediction=record
                try:replay=old.candidate_prediction(nd,data,row['candidate_index'],row['aliases'])
                finally:old.gaussian_prediction=gaussian_prediction
                assert abs(replay['score']-row['score'])<1e-5 and replay['qualified']==row['qualified']
                direct,method=predictive_density_reference(*capture[0]);delta=abs(direct-row['score']);assert delta<2e-3
                residual=exact_residual(nd,data,row);independent_scores.append(direct)
                checks.append(dict(original_norad=family['original_norad'],candidate_norad=row['norad'],node=k,
                    predictive_density_difference=delta,predictive_density_method=method,exact_independent_residual_difference_hz=residual,**node_density))
            mixed=independent_scores[0] if variant=='point_cavity' else direct_mixture(independent_scores,logw)
            assert abs(mixed-candidate['score'])<2e-3
            if variant=='quadrature_cavity':
                assert candidate['qualified']==all(r['qualified'] for r in candidate['components'])
                assert all(r['aliases']==candidate['aliases'] for r in candidate['components'])
        eligible=sorted([r for r in family['candidates'] if r['qualified'] and r['candidate_index']!=target],key=lambda r:r['score'])
        assert family['best']==(eligible[0] if eligible else None)
        if eligible:assert abs(family['predictive_gain']-(family['original']['score']-eligible[0]['score']))<1e-8
        family_checks.append(dict(original_norad=family['original_norad'],cold_other_family_position_fit_replayed=True,
            SVD_position_covariance_relative_difference=relative,held_value_perturbation_checks_per_node=3,nodes=len(nodes)))
    return dict(case=case,variant=variant,checks=checks,family_checks=family_checks,all_original_held_points_excluded_from_position_and_calibration=True,
        current_full_catalogue_epoch_and_collection_causal=True,conditional_on_fixed_other_labels_aliases_powers=True,
        local_position_quadrature_is_proposal_not_global_confidence=True,reference_position_used=False,
        source_sha256=sha(directory/(case+'_nominations.json')))
