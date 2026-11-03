"""Independent SGP4 element initialization, range-rate and Gaussian projection."""

from concurrent.futures import ProcessPoolExecutor
import itertools
import numpy as np
from sgp4.api import Satrec,WGS72

from analyze_dsx01_fixed_site import ecef_states
from audit_ds23_family_cavity import density
from prototype_dsx01_continuous_position import latlon
from probe_ds23_uncertainty_mean import OUT,CASES,selected_context,problem
from run_algo01_ds23_sample import read,write,sha
from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.sky.frames import geodetic_to_ecef_km
from leo.sky.propagation import ElementSetCatalogue


def frequency(p,j,times,draws,x):
    """Initialize all element changes in one call, then direct rotated range-rate."""
    sat=Satrec.twoline2rv(*p.scan.elements[str(int(p.scan.norads[j]))]['lines']);m=p.mode_metadata.get(j);satellites=[]
    elapsed=(p.scan.receipt['origin_utc_ns']/1e9+150)/86400+2440587.5-sat.jdsatepoch-sat.jdsatepochF
    for draw in draws:
        delta=draw[1]*m['mean_motion_sigma_rev_day'] if len(draw)>1 else 0.
        changed=Satrec();changed.sgp4init(WGS72,sat.operationmode,sat.satnum,(sat.jdsatepoch-2433281.5)+sat.jdsatepochF,
            sat.bstar,sat.ndot,sat.nddot,sat.ecco,sat.argpo,
            sat.inclo+(np.deg2rad(draw[2]*m['inclination_sigma_deg']) if len(draw)>1 else 0.),
            sat.mo-2*np.pi*delta*elapsed,sat.no_kozai+delta*2*np.pi/1440,
            sat.nodeo+(np.deg2rad(draw[3]*m['raan_sigma_deg']) if len(draw)>1 else 0.))
        changed.jdsatepoch,changed.jdsatepochF=sat.jdsatepoch,sat.jdsatepochF;satellites.append(changed)
    n=int(p.scan.norads[j]);cat=ElementSetCatalogue((str(n),)*len(draws),(n,)*len(draws),tuple(satellites))
    position,velocity,good=ecef_states(cat,p.scan.receipt['origin_utc_ns'],p.sky['time_s']);assert good.all()
    result=[];observer=geodetic_to_ecef_km(*latlon(x),0.)
    for k,draw in enumerate(draws):
        requested=times+draw[0];states=[]
        if requested.min()<p.sky['time_s'][0] or requested.max()>p.sky['time_s'][-1]:raise ValueError('independent range-rate audit would extrapolate')
        angle=EARTH_ROTATION_RAD_S*draw[0];co,si=np.cos(angle),np.sin(angle)
        for array in [position[k],velocity[k]]:
            value=np.stack([np.interp(requested,p.sky['time_s'],array[:,axis]) for axis in range(3)],axis=1)
            a,b=value[:,0].copy(),value[:,1].copy();value[:,0]=co*a-si*b;value[:,1]=si*a+co*b;states.append(value)
        line=states[0]-observer;rate=np.einsum('ij,ij->i',line,states[1])/np.linalg.norm(line,axis=1)
        result.append(-11.5e9*rate/299792.458)
    return np.asarray(result)


def one(case):
    saved=read(OUT/(case+'.json'));assert saved['status']=='complete';d,arms=selected_context(case);checks=[]
    for arm,r in saved['arms'].items():
        p,x=problem(d,arm,arms[arm]);density(d,p,x,d['means'],d['entries'])
        c=p.curved_calculate(x) if d['entries'] else p.calculate(x);u=c['features'][p.keep];groups=p.noise_groups[p.keep]
        weight=d['powers'][groups]*c['noise_precision'][groups]/p.point_noise[p.keep]**2;v=c['coefficient_prior_precision'];coef=c['coefficient']
        augmented=np.vstack((u*np.sqrt(weight)[:,None],np.diag(np.sqrt(v))));_,root=np.linalg.qr(augmented,mode='reduced')
        inverse=np.linalg.solve(root,np.eye(len(root)));covariance=inverse@inverse.T;begin=p.hardware.shape[1]+p.smooth.shape[1]
        bias=np.zeros(len(p.flat_times));maximum=0.
        for family in r['families']:
            j=family['candidate_index'];local=p.labels.index(j);slots=family['slots'];mean=coef[slots].copy();mean[0]*=p.phase_sigma[local]
            cov=covariance[np.ix_(slots,slots)].copy();cov[0,:]*=p.phase_sigma[local];cov[:,0]*=p.phase_sigma[local]
            np.testing.assert_allclose(mean,family['mean'],rtol=0,atol=1e-10);np.testing.assert_allclose(cov,family['covariance'],rtol=1e-7,atol=1e-8)
            if not family['valid']:continue
            # Three standard-normal knots and weights, independently constructed.
            indices=np.array(list(itertools.product(range(3),repeat=len(mean))));knots=np.array([-np.sqrt(3),0,np.sqrt(3)])
            mass=np.array([1/6,2/3,1/6]);nodes=mean+knots[indices]@np.linalg.cholesky(cov).T;w=np.prod(mass[indices],axis=1)
            use=np.flatnonzero((p.flat_labels==local)&p.keep);central=frequency(p,j,p.flat_times[use],mean[None,:],x)[0]
            actual=p.q[use]*(w@frequency(p,j,p.flat_times[use],nodes,x)-central);expected=np.asarray(family['uncertainty_mean_shift_hz']['hermite3'])
            delta=float(np.max(abs(actual-expected)));assert delta<2e-5;maximum=max(maximum,delta);bias[use]=actual
        derivative=[]
        for axis in range(2):
            offset=np.eye(2)[axis]*.01;plus=p.calculate(x+offset);minus=p.calculate(x-offset)
            derivative.append((p.q*(plus['intercept']-minus['intercept'])+(plus['features']-minus['features'])@coef)/.02)
        derivative=np.column_stack(derivative)[p.keep];full=np.block([[derivative*np.sqrt(weight)[:,None],u*np.sqrt(weight)[:,None]],
            [np.zeros((len(v),2)),np.diag(np.sqrt(v))]])
        fitted=np.linalg.lstsq(full,np.r_[-bias[p.keep]*np.sqrt(weight),np.zeros(len(v))],rcond=None)[0][:2]
        delta=float(np.max(abs(fitted-r['effects']['hermite3']['predicted_position_shift_km']))) if r['all_active_families_valid'] else None
        if delta is not None:assert delta<2e-6
        checks.append(dict(arm=arm,maximum_exact_uncertainty_mean_difference_hz=maximum,
            independent_augmented_SVD_shift_difference_km=delta,Gaussian_covariance_rebuilt_with_QR=True))
    return dict(case=case,all_passed=True,checks=checks,source_sha256=sha(OUT/(case+'.json')),reference_position_used=False)


def main():
    assert read(OUT/'execution.json')['all_complete']
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,CASES))
    write(OUT/'independent_numerical_audit.json',dict(rows=rows,all_passed=True,
        exact_elements_initialized_jointly_and_direct_rotated_range_rate=True,augmented_QR_covariance_and_SVD_position_projection=True,
        no_position_adopted_no_GPS_or_accuracy_gain_claim=True,source_execution_sha256=sha(OUT/'execution.json')))


if __name__=='__main__':main()
