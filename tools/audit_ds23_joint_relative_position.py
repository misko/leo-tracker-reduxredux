"""Replay joint fits with grid orbit geometry and direct probability densities."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path
import numpy as np

from audit_ds23_unanchored_relative_position import grid,physical_columns
from ds23_joint_relative_audit import expected_log_density
from ds23_predictive_linear import linear_geometry
from probe_ds23_joint_relative_position import OUT,context,make,relative_gates
from probe_ds23_frequency_events import summary
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha
from run_ds23_combined_recovery_full import valid
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid


def absolute_grid(p,x,phase,bank=None):
    f,e=phase_frequency_grid(p.sky if bank is None else bank,p.flat_times,*latlon(x),phase_seconds=phase)
    ix=np.arange(len(p.flat_times));return f[p.flat_labels,ix],e[p.flat_labels,ix]


def absolute_features(p,x):
    f,e=absolute_grid(p,x,p.reference);plus,_=absolute_grid(p,x,p.reference+.01);minus,_=absolute_grid(p,x,p.reference-.01)
    derivative=(plus-minus)/.02;intercept=f-derivative*p.reference[p.flat_labels]
    phase=np.zeros((len(f),len(p.labels)));phase[np.arange(len(f)),p.flat_labels]=p.q*derivative*p.phase_sigma[p.flat_labels]
    orbital=np.zeros((len(f),3*len(p.supported)))
    for k,local in enumerate(p.supported_local):
        for mode in range(3):
            predictions=[]
            for sign in [-1,1]:
                bank=dict(time_s=p.sky['time_s'],position_km=p.sky['position_km'].copy(),velocity_km_s=p.sky['velocity_km_s'].copy())
                for field in ['position_km','velocity_km_s']:bank[field][local]+=sign*.001*p.mode_bank[field][3*local+mode]
                predictions.append(absolute_grid(p,x,p.reference,bank)[0])
            orbital[:,3*k+mode]=p.q*(predictions[1]-predictions[0])/.002
    hardware=p.hardware.copy();hardware[:,[4,6]]*=10
    return p.q*intercept,np.column_stack((hardware,p.smooth*200,phase,orbital,p.constants)),e


def relative_features(rf,x):
    f,e=phase_frequency_grid(rf.sky,rf.times,*latlon(x),phase_seconds=rf.reference)
    plus,_=phase_frequency_grid(rf.sky,rf.times,*latlon(x),phase_seconds=rf.reference+.01)
    minus,_=phase_frequency_grid(rf.sky,rf.times,*latlon(x),phase_seconds=rf.reference-.01)
    derivative=(plus-minus)/.02;intercept=f-derivative*rf.reference[:,None];ix=np.arange(len(rf.values))
    features=np.zeros((len(ix),len(rf.labels)+3*len(rf.supported)+len(rf.groups)))
    features[ix,rf.first]-=rf.q*derivative[rf.first,ix]*rf.phase_sigma[rf.first]
    features[ix,rf.second]+=rf.q*derivative[rf.second,ix]*rf.phase_sigma[rf.second]
    begin=len(rf.labels);stop=begin+3*len(rf.supported)
    features[:,begin:stop]=physical_columns(rf,x,rf.reference)
    features[ix,stop+rf.noise_groups]=rf.bias_sigma
    return rf.q*(intercept[rf.second,ix]-intercept[rf.first,ix]),features


def one(saved,output_dir=None,context_factory=context):
    d=context_factory(saved['case']);pairs={};checks=[]
    for arm,record in saved['arms'].items():
        p=make(d,arm,np.asarray(record['joint_phase_reference']),saved['include_relative'],saved['bias_sigma_hz'])
        x=np.asarray(record['endpoint_east_north_km']);c=p.calculate(x);w=len(c['coefficient'])
        assert abs(c['negative_twice_elbo']-record['negative_twice_elbo'])<1e-6
        np.testing.assert_allclose(c['coefficient'],record['coefficient'],rtol=0,atol=1e-8)
        intercept,features,e=absolute_features(p,x);features=np.pad(features,((0,0),(0,w-features.shape[1])))
        feature_delta=float(np.max(abs(features-c['features'])))
        assert feature_delta<2e-4
        raw=p.values-intercept;u=[features[p.keep]];y=[raw[p.keep]];sigma=[p.point_noise[p.keep]]
        present=np.unique(p.noise_groups[p.keep]);groups=[p.noise_groups[p.keep]];power=[d['powers'][present]]
        noise=[c['noise_precision'][present]];rf=p.relative_problem
        if saved['include_relative']:
            ri,ru=relative_features(rf,x);mapped=np.zeros((len(rf.values),w));mapped[:,p.relative_mapping]=ru
            u.append(mapped);y.append(rf.values-ri);sigma.append(rf.noise);groups.append(len(p.members)+rf.noise_groups)
            power.append(np.ones(len(rf.groups)));noise.append(c['relative_noise_precision'])
        mean=np.zeros(w);phase_begin=p.hardware.shape[1]+p.smooth.shape[1]
        mean[phase_begin:phase_begin+len(p.labels)]=d['old_means']/p.phase_sigma
        for j,index in p.joint_column_plan['new_phases'].items():mean[index]=d['rf_means'][d['rf_labels'].index(j)]/d['rf_widths'][d['rf_labels'].index(j)]
        scales=np.ones(w);scales[p.joint_old_width-len(p.members):p.joint_old_width]=.3
        phase_slots=list(range(phase_begin,phase_begin+len(p.labels)))+list(p.joint_column_plan['new_phases'].values())
        direct=expected_log_density(np.concatenate(y),np.vstack(u),np.concatenate(sigma),np.concatenate(groups),
            np.concatenate(power),mean,scales,c['coefficient'],np.concatenate(noise),c['coefficient_prior_precision'],phase_slots,d['model']['nu'])
        expected_curved=c.get('curved_negative_twice_elbo',c['negative_twice_elbo'])
        density_delta=abs(direct['negative_twice_elbo']-expected_curved)
        if density_delta>2e-3:raise ValueError(f'independent expected log density mismatch:{density_delta}')
        assert direct['maximum_coefficient_normal_equation_error']<1e-5
        predictive_delta=0.
        if d['original_entries']:
            view,values,noise_sigma,g,slices=linear_geometry(p,d['original_entries'])
            vi,vu,_=absolute_features(view,x);vu=np.pad(vu,((0,0),(0,w-vu.shape[1])))
            residual=values-vi-vu@c['coefficient'];cov=vu@direct['covariance_physical']@vu.T
            cov+=np.diag(2*noise_sigma**2)+300.**2*(g[:,None]==g[None,:])
            predictive=float(residual@np.linalg.solve(cov,residual)+np.linalg.slogdet(cov)[1]+len(values)*np.log(2*np.pi))
            predictive_delta=abs(predictive-(c['negative_twice_elbo']-expected_curved))
            assert predictive_delta<2e-3
        maximum=0.
        if saved['include_relative']:
            coefficient=c['coefficient'][p.relative_mapping];phase=coefficient[:len(rf.labels)]*rf.phase_sigma
            if np.max(abs(phase))<=15:
                f,e=grid(rf,x,phase);begin=len(rf.labels);stop=begin+3*len(rf.supported)
                residual=rf.values-f-physical_columns(rf,x,phase)@coefficient[begin:stop]-rf.bias_sigma*coefficient[stop+rf.noise_groups]
                maximum=float(np.max(abs(residual-p.exact_relative(x)[0])));assert maximum<2e-4
        replay=summary(p,x,d['original_entries']);replay.update(final_phase_change_s=record['final_phase_change_s'],
            relative_gates=relative_gates(p,x,saved['bias_sigma_hz']))
        assert replay['gates']==record['gates'] and replay['linear_gates']==record['linear_gates']
        assert [g['compatible'] for g in replay['relative_gates']]==[g['compatible'] for g in record['relative_gates']]
        pairs[arm]=replay
        checks.append(dict(arm=arm,maximum_independent_feature_difference_hz=feature_delta,
            expected_log_density_difference=density_delta,predictive_dense_covariance_loss_difference=predictive_delta,
            exact_relative_residual_difference_hz=maximum,coefficient_normal_equation_error=direct['maximum_coefficient_normal_equation_error']))
    accepted=bool(valid(pairs) and all(r['final_phase_change_s']<=.01 and all(g['compatible'] for g in r['relative_gates']) for r in pairs.values()))
    assert accepted==saved['accepted']
    return dict(case=saved['case'],variant=saved['variant'],checks=checks,accepted=accepted,
        reference_position_used=False,source_sha256=sha((OUT if output_dir is None else Path(output_dir))/(saved['case']+'_'+saved['variant']+'.json')))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,default=OUT)
    args=parser.parse_args();out=args.directory
    execution=read(out/'execution.json');assert execution['all_terminal']
    complete=[r for r in execution['rows'] if r['status']=='complete']
    with ProcessPoolExecutor(max_workers=6) as pool:audits=list(pool.map(partial(one,output_dir=out),complete))
    write(out/'independent_numerical_audit.json',dict(audits=audits,all_passed=True,
        direct_expected_log_density_and_entropy=True,independent_grid_and_perturbed_orbit_features=True,
        dense_predictive_covariance_checked=True,all_original_gates_replayed=True,reference_position_used=False))
    print('Independent joint likelihood and geometry audits pass',flush=True)


if __name__=='__main__':main()
