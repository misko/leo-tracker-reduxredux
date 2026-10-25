"""Exact-SGP4 expected-frequency bias from conditional phase/orbit uncertainty.

This diagnoses a nonlinear physical alternative at an existing RF endpoint.
It is not an evidence correction, a fitted position, or a new measurement.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time

import numpy as np
from sgp4.api import Satrec

from analyze_dsx01_fixed_site import ecef_states
from ds23_uncertainty_mean import gaussian_nodes,projected_mean_shift
from ds23_frequency_events import make_event_problem,attach_event_predictive
from fit_s01_69333_tle_parameter import perturb
from prototype_dsx01_mean_motion import reference_motion_satellite
from prototype_dsx01_continuous_position import latlon
from probe_ds23_family_cavity_nominations import setup
from ds23_family_cavity import legacy_phase_reference
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.sky.propagation import ElementSetCatalogue

OUT=ROOT/'reports/2026_10_22_ds23_uncertainty_mean'
SOURCE=ROOT/'reports/2026_10_22_ds23_family_cavity/phase_refreshed/full_DS23/position'
CASES=['DS23-0268','DS23-0405','DS23-0080','DS23-0240']


def selected_context(case):
    d=setup(case);saved=read(SOURCE/(case+'.json'))
    authority=read(ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/evidence/publication_receipt.json')
    assert sha(SOURCE/(case+'.json'))==next(r['position_sha256'] for r in authority['case_result_sha256'] if r['case']==case)
    eligible=[r for r in saved['trials'] if r['paired_valid']]
    best=min(eligible,key=lambda r:r['arms']['c0']['corrected_selection_loss']) if eligible else None
    if best is not None and best['arms']['c0']['corrected_selection_loss']<saved['baseline_corrected_loss']['c0']:
        d.update(node=best['node'],entries=best['entries'],means=np.asarray(best['means']));arms=best['arms']
    else:arms=saved['baseline_arms']
    return d,arms


def problem(d,arm,saved):
    reference=np.asarray(saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
    def build(ref):
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,ref,d['powers'],d['means'],d['model'],[])
        attach_event_predictive(p,d['entries'],d['powers']);return p
    p=build(reference)
    if abs(p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo'])>1e-5:
        reference=legacy_phase_reference(saved['history'],np.zeros(len(d['means'])),lambda r,z:build(r).state(z)['phases'][p.labels])
        p=build(reference)
    assert abs(p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo'])<1e-5
    return p,x


def frequencies(p,j,times,draws,x):
    """One phase and three existing physical element coordinates per draw."""
    draws=np.asarray(draws,float)
    if draws.ndim!=2 or draws.shape[1] not in [1,4] or np.max(abs(draws[:,0]))>15:
        raise ValueError('phase/orbit nodes must satisfy the existing phase support')
    sat=Satrec.twoline2rv(*p.scan.elements[str(int(p.scan.norads[j]))]['lines']);satellites=[]
    elapsed=(p.scan.receipt['origin_utc_ns']/1e9+150)/86400+2440587.5-sat.jdsatepoch-sat.jdsatepochF
    for draw in draws:
        changed=sat
        if len(draw)>1:
            m=p.mode_metadata[j]
            changed=reference_motion_satellite(sat,draw[1]*m['mean_motion_sigma_rev_day'],elapsed)
            changed=perturb(changed,'inclination_deg',draw[2]*m['inclination_sigma_deg'])
            changed=perturb(changed,'raan_deg',draw[3]*m['raan_sigma_deg'])
        if changed.no_kozai<=0 or not 0<=changed.ecco<1 or not 0<=changed.inclo<=np.pi:
            raise ValueError('nonphysical element at Gaussian quadrature node')
        satellites.append(changed)
    n=int(p.scan.norads[j]);catalogue=ElementSetCatalogue((str(n),)*len(draws),(n,)*len(draws),tuple(satellites))
    position,velocity,good=ecef_states(catalogue,p.scan.receipt['origin_utc_ns'],p.sky['time_s'])
    if not good.all():raise ValueError('Gaussian orbital quadrature node failed exact SGP4')
    bank=dict(time_s=p.sky['time_s'],position_km=position,velocity_km_s=velocity)
    return phase_frequency_grid(bank,times,*latlon(x),phase_seconds=draws[:,0])[0]


def one(case):
    path=OUT/(case+'.json')
    if path.exists():return read(path)
    started=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s uncertainty mean diagnostic cap')));signal.alarm(180)
    try:
        d,arms=selected_context(case);results={}
        for element in d['scan'].elements.values():
            v=element['provenance'];assert max(v['element_epoch_utc_ns'],v['collected_utc_ns'])<=d['scan'].receipt['cutoff_utc_ns']
        for arm,saved in arms.items():
            p,x=problem(d,arm,saved);c=p.curved_calculate(x) if d['entries'] else p.calculate(x)
            coef=c['coefficient'];u=c['features'][p.keep];g=p.noise_groups[p.keep];weight=d['powers'][g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
            covariance=np.linalg.inv(np.diag(c['coefficient_prior_precision'])+u.T@(weight[:,None]*u))
            begin=p.hardware.shape[1]+p.smooth.shape[1];families=[];bias={rule:np.zeros(len(p.flat_times)) for rule in ['spherical','hermite3','phase_only']}
            exact_delta=np.zeros(len(p.flat_times));all_valid=True
            for local,j in enumerate(p.labels):
                use=np.flatnonzero((p.flat_labels==local)&p.keep)
                if not len(use):continue
                slots=[begin+local]
                if j in p.supported:slots.extend(range(begin+len(p.labels)+3*p.supported.index(j),begin+len(p.labels)+3*p.supported.index(j)+3))
                mu=coef[slots].copy();cov=covariance[np.ix_(slots,slots)].copy();mu[0]*=p.phase_sigma[local];cov[0,:]*=p.phase_sigma[local];cov[:,0]*=p.phase_sigma[local]
                r=dict(candidate_index=j,norad=int(p.scan.norads[j]),points=len(use),slots=slots,mean=mu,covariance=cov,phase_SD_s=float(np.sqrt(cov[0,0])))
                try:
                    central=frequencies(p,j,p.flat_times[use],mu[None,:],x)[0]
                    a=begin;stop=begin+len(p.labels)+3*len(p.supported)
                    linear=p.q[use]*c['intercept'][use]+c['features'][use,a:stop]@coef[a:stop]
                    exact_delta[use]=p.q[use]*central-linear
                    nodes,weights=gaussian_nodes(mu[:1],cov[:1,:1]);phase_draws=np.tile(mu,(len(nodes),1));phase_draws[:,0]=nodes[:,0]
                    bias['phase_only'][use]=p.q[use]*(weights@frequencies(p,j,p.flat_times[use],phase_draws,x)-central)
                    for rule in ['spherical','hermite3']:
                        nodes,weights=gaussian_nodes(mu,cov,rule);value=weights@frequencies(p,j,p.flat_times[use],nodes,x)-central
                        bias[rule][use]=p.q[use]*value
                    r.update(valid=True,mean_exact_minus_linear_hz=exact_delta[use],
                        uncertainty_mean_shift_hz={rule:b[use] for rule,b in bias.items()},
                        uncertainty_mean_RMS_hz={rule:float(np.sqrt(np.mean(b[use]**2))) for rule,b in bias.items()})
                except ValueError as exc:r.update(valid=False,error=str(exc));all_valid=False
                families.append(r)
            effect={};derivative=[]
            for k in [0,1]:
                offset=np.eye(2)[k]*.01;plus=p.calculate(x+offset);minus=p.calculate(x-offset)
                derivative.append((p.q*(plus['intercept']-minus['intercept'])+(plus['features']-minus['features'])@coef)/.02)
            derivative=np.column_stack(derivative)[p.keep]
            if all_valid:
                for rule,value in bias.items():effect[rule]=projected_mean_shift(derivative,u,weight,c['coefficient_prior_precision'],value[p.keep])
                effect['exact_mean_only']=projected_mean_shift(derivative,u,weight,c['coefficient_prior_precision'],exact_delta[p.keep])
            results[arm]=dict(families=families,all_active_families_valid=all_valid,effects=effect,endpoint=x,
                uncertainty_shift_RMS_hz={rule:float(np.sqrt(np.mean(value[p.keep]**2))) for rule,value in bias.items()},
                exact_mean_remainder_RMS_hz=float(np.sqrt(np.mean(exact_delta[p.keep]**2))),
                spherical_vs_hermite3_RMS_difference_hz=float(np.sqrt(np.mean((bias['spherical'][p.keep]-bias['hermite3'][p.keep])**2))),
                coefficient_posterior_conditioned_on_original_Gamma=True,all_original_points_and_labels_fixed=True,
                cross_family_covariance_not_needed_for_additive_mean_but_full_nuisance_covariance_used_for_projection=True)
        result=dict(case=case,status='complete',arms=results,reference_position_used=False,position_adoption=False,
            not_a_full_nonlinear_evidence_integral=True,source_position_sha256=sha(SOURCE/(case+'.json')))
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workers',type=int,default=4);args=parser.parse_args();OUT.mkdir(exist_ok=True)
    protocol=dict(cases=CASES,workers=args.workers,scope='engineering diagnostic, not accuracy improvement',
        conditional_Gaussian_phase_plus_three_physical_orbit_marginals=True,exact_SGP4_nodes=True,
        rules=['spherical','hermite3'],phase_only_control=True,exact_fitted_mean_control=True,
        original_orbit_parameter_scales_and_phase_correlation_preserved=True,no_truncation_or_renormalization_of_invalid_nodes=True,
        local_position_shift='augmented QR nuisance projection, fixed Gamma/labels and existing tangent Jacobian; diagnostic only',
        no_GPS_future_TLE_new_RF_or_position_adoption=True,per_case_seconds=180,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_uncertainty_mean.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('uncertainty diagnostic protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:rows=[f.result() for f in as_completed([pool.submit(one,c) for c in CASES])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_complete=all(r['status']=='complete' for r in rows),no_GPS_or_geographic_accuracy_claim=True))


if __name__=='__main__':main()
