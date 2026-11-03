"""Paired component stress tests under original causal nuisance scales.

No real evaluation position or future elements are used. Labels are oracle
labels by construction. This is a conditional component simulation, not a
full hierarchical prior-predictive test or a real localization improvement.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_frequency_events import make_event_problem
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from leo.analysis.research.retained_track_likelihood import PERIOD
from probe_ds23_frequency_events import parameters,refit
from probe_ds23_synthetic_closure import generate,alias_encode,TEMPLATES
from probe_ds23_synthetic_noise import perturb_tracks,gate_counts,SITE
from run_ds23_combined_recovery_full import context,ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_synthetic_nuisance_components'
GROUPS=('radio','smooth','orbit','fragment','phase','all')


def select_coefficients(z,widths,group):
    """Preserve common draws, with physical 300-Hz fragment constants."""
    if group not in GROUPS:raise ValueError('unknown nuisance component')
    nb,ns,nphase,norbit,nfragment=widths
    if len(z)!=sum(widths) or min(widths)<0:raise ValueError('matching nuisance coordinates required')
    output=np.zeros(len(z));starts=np.r_[0,np.cumsum(widths)]
    for name,index,scale in [('radio',0,1.),('smooth',1,1.),('orbit',3,1.),('fragment',4,.3)]:
        if group in (name,'all'):
            sl=slice(starts[index],starts[index+1]);output[sl]=scale*np.asarray(z)[sl]
    return output


def bounded_phase_draw(means,sigmas,nu,uniforms):
    """Condition the existing phase law on the declared +/-15-second domain."""
    from scipy.stats import norm,t
    means,sigmas,u=[np.asarray(x,float) for x in (means,sigmas,uniforms)]
    if means.shape!=sigmas.shape or means.shape!=u.shape or not all(np.isfinite(x).all() for x in (means,sigmas,u)):
        raise ValueError('matching finite phase coordinates required')
    if np.any(sigmas<=0) or np.any((u<=0)|(u>=1)):raise ValueError('positive scales and interior quantiles required')
    law=norm if nu is None else t(float(nu))
    lower=law.cdf((-15-means)/sigmas);upper=law.cdf((15-means)/sigmas)
    if np.any(upper<=lower):raise ValueError('phase prior has no representable mass in search domain')
    return means+sigmas*law.ppf(lower+u*(upper-lower))


def synthesize(scan,node,mask,base,powers,means,hyper,entries,group,draw):
    seed=811979+1009*draw+int(scan.case.split('-')[1]);rng=np.random.default_rng(seed)
    nominal=make_event_problem(scan,node,mask,'c0',means,powers,means,hyper,[])
    widths=(nominal.hardware.shape[1],nominal.smooth.shape[1],len(nominal.labels),3*len(nominal.supported),len(nominal.members))
    z=rng.normal(size=sum(widths));u=rng.uniform(size=len(means));linear_z=rng.normal(size=len(entries))
    phases=bounded_phase_draw(means,nominal.phase_sigma,hyper['nu'],u) if group in ('phase','all') else means.copy()
    synthetic,copied,predictive,reconstruction=generate(scan,node,base,phases,entries,SITE)
    p=make_event_problem(scan,node,mask,'c0',phases,powers,means,hyper,[])
    geometry=geometry_features(p,SITE,0.)
    coefficient=select_coefficients(z,widths,group)
    delta=geometry['features']@coefficient
    for k,(i,sl) in enumerate(zip(p.members,p.slices,strict=True)):
        raw=synthetic.tracks[i]['values']+copied['aliases'][k]*PERIOD+delta[sl]
        values,alias=alias_encode(raw);synthetic.tracks[i]['values']=values;copied['aliases'][k]=alias
        reconstruction=max(reconstruction,float(max(abs(values+alias*PERIOD-raw))))
    if entries:
        view,_,_,_,slices=linear_geometry(p,entries)
        linear_delta=geometry_features(view,SITE,0.)['features']@coefficient
        for k,(entry,sl) in enumerate(zip(predictive,slices,strict=True)):
            raw=synthetic.tracks[entry['track_index']]['values']+entry['alias']*PERIOD+linear_delta[sl]
            if group in ('fragment','all'):raw=raw+300*linear_z[k]
            values,alias=alias_encode(raw);synthetic.tracks[entry['track_index']]['values']=values;entry['alias']=alias
            reconstruction=max(reconstruction,float(max(abs(values+alias*PERIOD-raw))))
    info=dict(latent_seed=seed,coordinate_widths=widths,standard_normal_draw=z,selected_coefficients=coefficient,
        phase_prior_means_s=means,phase_prior_sigma_s=nominal.phase_sigma,true_phases_s=phases,
        phase_prior_nu=hyper['nu'],phase_conditioned_on_bounds_s=[-15,15],
        curved_additive_nuisance_RMS_hz=float(np.sqrt(np.mean(delta[mask]**2))),
        maximum_forward_alias_reconstruction_error_hz=reconstruction)
    return synthetic,copied,predictive,info


def run(case,draw,group):
    path=OUT/(case+'_draw'+str(draw)+'_'+group+'.json')
    if path.exists():return read(path)
    begin=time.monotonic()
    def timeout(*_):raise TimeoutError('120 second component-control budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    result=dict(case=case,draw=draw,group=group,synthetic_site_east_north_km=SITE,
        cold_start_east_north_km=[0,0],evaluation_GPS_used=False,oracle_labels_and_aliases=True,
        full_hierarchical_prior_predictive=False)
    try:
        scan,node,mask,base,old=context(case);powers,means,hyper=parameters(scan,base,old)
        entries=old['linear_entries'] if old['linear_paired_valid'] else []
        original=[t['values'].copy() for t in scan.tracks]
        synthetic,copied,predictive,info=synthesize(scan,node,mask,base,powers,means,hyper,entries,group,draw)
        noise_seed=194729+draw*1009+int(case.split('-')[1])
        noise=perturb_tracks(synthetic,set(base.members)|{e['track_index'] for e in predictive},noise_seed)
        if any(not np.array_equal(v,t['values']) for v,t in zip(original,scan.tracks,strict=True)):
            raise ValueError('simulation changed original observations')
        pair={a:refit(synthetic,copied,mask,a,powers,means,hyper,[],predictive) for a in ARMS}
        for a,r in pair.items():
            r['synthetic_position_error_km']=float(np.linalg.norm(np.asarray(r['endpoint_east_north_km'])-SITE))
            r['original_gate_counts']=gate_counts(r)
        result.update(status='complete',arms=pair,noise_seed=noise_seed,noise=noise,generation_truth=info,
            paired_original_qualification=valid(pair),original_observations_unchanged=True,
            same_observations_masks_weights_priors_labels_aliases_in_both_c_arms=True)
    except Exception as exc:result.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-begin;write(path,result)
    print(case,draw,group,result['status'],{a:r['synthetic_position_error_km'] for a,r in result.get('arms',{}).items()},flush=True)
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(templates=list(TEMPLATES),groups=list(GROUPS),draws_per_template=2,
        synthetic_site=list(SITE),workers=8,per_instance_seconds=120,
        common_noise_seed='194729+1009*draw+template_number',common_latent_seed='811979+1009*draw+template_number',
        original_causal_prior_scales=True,radio_c_truth=0,fragment_sigma_hz=300,
        phase_draws_from_existing_Gaussian_or_Student_law_conditioned_to_minus15_plus15=True,
        Gaussian_observation_noise_only_not_full_hierarchical_predictive=True,
        correct_labels_known_by_construction_not_full_association_validation=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_synthetic_closure.py',ROOT/'tools/probe_ds23_synthetic_noise.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('component protocol changed')
    if not target.exists():write(target,protocol)
    rows=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(run,c,d,g) for c in TEMPLATES for d in range(2) for g in GROUPS]
        for f in as_completed(futures):
            rows.append(f.result());write(OUT/'progress.json',dict(completed=len(rows),total=len(futures)))
    summary={}
    for g in GROUPS:
        summary[g]={}
        for a in ARMS:
            selected=[r for r in rows if r['group']==g and r['status']=='complete'];arms=[r['arms'][a] for r in selected]
            errors=[r['synthetic_position_error_km'] for r in arms]
            summary[g][a]=dict(n=len(errors),mean_km=float(np.mean(errors)) if errors else None,
                median_km=float(np.median(errors)) if errors else None,maximum_km=max(errors) if errors else None,
                original_gate_pass=sum(r['original_gate_counts']['all_original_gates_pass'] for r in arms),
                paired_qualified=sum(r['paired_original_qualification'] for r in selected))
    write(OUT/'evaluation.json',dict(instances=len(rows),summary=summary,
        failures=[dict(case=r['case'],draw=r['draw'],group=r['group'],error=r.get('error')) for r in rows if r['status']!='complete'],
        full_real_DS23_accuracy_gain=False,conditional_component_simulation_only=True,protocol_sha256=sha(target)))


if __name__=='__main__':main()
