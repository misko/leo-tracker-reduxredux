"""Evaluation-only loss decomposition; GPS never selects an inference variant."""

import argparse
from pathlib import Path
import numpy as np
from ds23_precision_diagnostics import compare_screens
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_refined_eccentricity import eccentric_problem
from probe_ds23_refined_family_catalogue import OUT,context
from prototype_dsx01_continuous_position import CENTER
from report_algo01_ds23_sample import REFERENCE
from run_algo01_ds23_sample import ROOT,read,write,sha


def decompose(p,x,powers):
    c=p.calculate(x);active=p.keep;data=powers[p.noise_groups]*c['noise_precision'][p.noise_groups]*(c['conditional_residual_hz']/p.point_noise)**2
    coeff=c['latent_coefficient']**2*c['coefficient_prior_precision']
    nb,ns=p.hardware.shape[1],p.smooth.shape[1];phase=nb+ns;orbit=phase+len(p.labels);stop=len(coeff)-len(p.members)
    terms=dict(data=float(data[active].sum()),RX_affine=float(coeff[:nb].sum()),RX_smooth=float(coeff[nb:phase].sum()),
        phase=float(coeff[phase:orbit].sum()),orbit=float(coeff[orbit:stop].sum()),fragment=float(coeff[stop:].sum()),
        log_volume=float(c['logvolume']),noise_gamma=float(c['noise_gamma_cost']),phase_gamma=float(c['prior_gamma_cost']),
        normalization=float(c['normalization_constant']))
    if abs(sum(terms.values())-c['negative_twice_elbo'])>1e-5:raise ValueError('loss decomposition does not reproduce full normalized objective')
    families=[]
    for local,j in enumerate(p.labels):
        use=active&(p.flat_labels==local);support=p.supported_local.index(local) if local in p.supported_local else None
        orbital=0.
        if support is not None:
            orbital=float(coeff[orbit+3*support:orbit+3*support+3].sum()+coeff[orbit+3*len(p.supported)+2*support:orbit+3*len(p.supported)+2*support+2].sum())
        constant=[k for k,r in enumerate(p.rows) if r['candidate_index']==j]
        families.append(dict(norad=int(p.scan.norads[j]),points=int(use.sum()),data=float(data[use].sum()),
            phase_prior=float(coeff[phase+local]),orbit_prior=orbital,fragment_prior=float(coeff[stop+np.array(constant,int)].sum()),
            posterior_phase_s=float(p.state(x)['phases'][j])))
    tracks=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        use=active[sl]
        if use.any():tracks.append(dict(track=p.scan.tracks[i]['key'],norad=row['candidate_norad'],
            **compare_screens(c['conditional_residual_hz'][sl][use],p.flat_times[sl][use],p.point_noise[sl][use])))
    return dict(endpoint_east_north_km=x,negative_twice_elbo=float(c['negative_twice_elbo']),terms=terms,families=families,tracks=tracks)


def run(case):
    scan,node,keep,powers,noise,radio,model,old,offsets=context(case,True)
    search=read(OUT/(case+'_companion.json'));reference=np.array([(REFERENCE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),(REFERENCE[0]-CENTER[0])*111.])
    records=[];selected=search['chosen'];cost_cache={}
    def fixed(candidate,arm,xy,details=True):
        base=problem(scan,candidate,arm,keep);_,receipt=phase_widths(scan,base.labels)
        means=forecast_phase_mean(receipt,model['shrinkage']);ref=np.zeros(len(means))
        for _ in range(5):
            p=eccentric_problem(scan,candidate,keep,arm,ref,powers,means,model,noise)
            ref=np.clip(p.state(xy)['phases'][p.labels],-15,15)
        return decompose(p,xy,powers) if details else float(p.calculate(xy)['negative_twice_elbo'])
    valid=[r for r in search['trials'] if r.get('paired_valid')]
    for trial in valid:
        candidate=changed_node(scan,node,trial['proposal']['changes']);arms={}
        for arm,saved in trial['arms'].items():
            x=np.array(saved['endpoint_east_north_km'])
            arms[arm]=dict(at_RF_endpoint=fixed(candidate,arm,x),at_evaluation_site=fixed(candidate,arm,reference))
        records.append(dict(norad=trial['proposal']['norad'],arms=arms))
        print(case,'decomposed',trial['proposal']['norad'],flush=True)
    chosen=changed_node(scan,node,selected['proposal']['changes']);x=np.array(selected['arms']['c0']['endpoint_east_north_km'])
    gradients={}
    for name,xy in [('RF_endpoint',x),('evaluation_site',reference)]:
        gradients[name]={}
        for step in (.05,.1):
            columns=[]
            for k in range(2):
                delta=np.zeros(2);delta[k]=step
                columns.append((fixed(chosen,'c0',xy+delta,False)-fixed(chosen,'c0',xy-delta,False))/(2*step))
            gradients[name][str(step)]=columns
    grid=[]
    for east in np.linspace(-10,10,9):
        for north in np.linspace(-10,10,9):
            xy=reference+np.array([east,north])
            if east*east+north*north>100 or np.any(abs(xy)>12.5):continue
            grid.append(dict(offset_east_north_km=[east,north],xy_km=xy,loss=fixed(chosen,'c0',xy,False)))
    write(OUT/(case+'_loss.json'),dict(case=case,identities=records,RF_selected_norad=selected['proposal']['norad'],
        evaluation_site_xy_km=reference,RF_endpoint_xy_km=x,gradients=gradients,grid=grid,
        GPS_used_only_for_diagnostic_site_and_plot_grid=True,no_inference_parameters_selected_using_GPS=True,
        surface_fixed_identities_and_mask_with_five_phase_refresh_rounds=True,
        grid_does_not_rerun_discovery_association_or_position_descent=True,
        radius_km=10,grid_spacing_km=2.5,regional_box_clipping=True,
        source_sha256=sha(Path(__file__)),catalogue_sha256=sha(OUT/(case+'_companion.json'))))
    print(case,'loss map complete',len(grid),'points',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True);run(parser.parse_args().case)
