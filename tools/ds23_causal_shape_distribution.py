"""Pre-RF qualification of five-dimensional orbital-parameter uncertainty."""

import argparse
from math import lgamma
from pathlib import Path
import numpy as np
from sgp4.api import Satrec
from ds23_causal_shape_forecast import OUT as FORECAST,states
from probe_ds23_history_calibrated_phase import HISTORY
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.sky.frames import julian_day_from_utc_ns

OUT=ROOT/'reports/2026_10_19_ds23_causal_shape_distribution'


def mean_elements(satellite,utc_ns):
    jd,fr=julian_day_from_utc_ns(np.array([utc_ns]));code,_,_=satellite.sgp4(float(jd[0]),float(fr[0]))
    if code:raise ValueError('mean-element propagation failed')
    return np.array([satellite.nm*1440/(2*np.pi),satellite.im,satellite.Om,
                     satellite.em*np.cos(satellite.om),satellite.em*np.sin(satellite.om)])


def nll(z,covariance,nu):
    z=np.asarray(z,float);cov=np.asarray(covariance,float);d=z.shape[1]
    root=np.linalg.cholesky(cov);q=np.sum(np.linalg.solve(root,z.T)**2,axis=0);logdet=2*np.log(np.diag(root)).sum()
    if nu is None:return q+logdet+d*np.log(2*np.pi)
    return logdet+d*np.log((nu-2)*np.pi)+2*lgamma(nu/2)-2*lgamma((nu+d)/2)+(nu+d)*np.log1p(q/(nu-2))


def fit_covariance(z,diagonal=False,nu=3.):
    z=np.asarray(z,float);cov=np.eye(z.shape[1])
    for _ in range(128):
        root=np.linalg.cholesky(cov);q=np.sum(np.linalg.solve(root,z.T)**2,axis=0)
        w=(nu+z.shape[1])/(nu-2+q)
        proposed=(z.T*w)@z/len(z)
        if diagonal:proposed=np.diag(np.diag(proposed))
        eigen,axes=np.linalg.eigh((proposed+proposed.T)/2)
        proposed=(axes*np.clip(eigen,.01,100))@axes.T
        if np.max(abs(proposed-cov))<1e-7:cov=proposed;break
        cov=proposed
    return cov


def select(rows):
    times=sorted({r['validation_time_ns'] for r in rows})
    if len(times)<3:return dict(qualified=False,model='Gaussian_I',covariance=np.eye(5),nu=None)
    cutoff=times[max(0,int(.7*len(times))-1)]
    train=np.array([r['z'] for r in rows if r['validation_time_ns']<=cutoff]);test=np.array([r['z'] for r in rows if r['validation_time_ns']>cutoff])
    if len(train)<30 or len(test)<30:return dict(qualified=False,model='Gaussian_I',covariance=np.eye(5),nu=None)
    candidates=[]
    for name,cov,nu,k in [('Gaussian_I',np.eye(5),None,0),('Student_I',np.eye(5),3.,0),
                         ('Student_diagonal',fit_covariance(train,True),3.,5),('Student_full',fit_covariance(train),3.,15)]:
        candidates.append(dict(model=name,covariance=cov,nu=nu,training_BIC=float(nll(train,cov,nu).sum()+k*np.log(len(train))),
                               validation_nll=float(nll(test,cov,nu).sum())))
    chosen=min(candidates,key=lambda r:r['training_BIC']);baseline=candidates[0]['validation_nll']
    improvement=(baseline-chosen['validation_nll'])/max(1.,abs(baseline));qualified=chosen['model']!='Gaussian_I' and improvement>=.01
    return dict(qualified=qualified,model=chosen['model'] if qualified else 'Gaussian_I',
        covariance=chosen['covariance'] if qualified else np.eye(5),nu=chosen['nu'] if qualified else None,
        trained_model=chosen['model'],candidates=candidates,validation_relative_gain=improvement,
        train_count=len(train),validation_count=len(test),publication_split_ns=cutoff,
        covariance_eigenvalue_bounds=[.01,100],mean_is_zero=True,
        qualification_is_for_later_causal_TLE_innovations_not_true_orbit_error=True)


def run(case):
    OUT.mkdir(parents=True,exist_ok=True);forecast=read(FORECAST/(case+'.json'));history=read(HISTORY/(case+'.json'))
    assert forecast['history_sha256']==sha(HISTORY/(case+'.json'))
    lookup={n:{r['epoch']:r for r in v} for n,v in history['past_versions'].items()};satellites={};rows=[]
    def sat(n,epoch):
        key=n,epoch
        if key not in satellites:satellites[key]=Satrec.twoline2rv(*lookup[str(n)][epoch]['lines'])
        return satellites[key]
    for row in forecast['transitions']:
        n=row['norad'];a,b,c=[sat(n,e) for e in row['version_epochs']];target=row['validation_time_ns']
        if row['age_gap_ratio']<=0:continue
        p,v=states(b,target,np.array([0.,150.,300.]));radial=p/np.linalg.norm(p,axis=1)[:,None]
        inertial=v.copy();inertial[:,0]-=EARTH_ROTATION_RAD_S*p[:,1];inertial[:,1]+=EARTH_ROTATION_RAD_S*p[:,0]
        normal=np.cross(p,inertial);normal/=np.linalg.norm(normal,axis=1)[:,None]
        dp=np.array(row['predictor_shape'])[:9].reshape(3,3)/row['age_gap_ratio']
        sr=max(.05,float(np.median(abs(np.sum(dp*radial,axis=1)))));sn=max(.025,float(np.median(abs(np.sum(dp*normal,axis=1)))))
        radius=float(np.mean(np.linalg.norm(p,axis=1)));reference=row['version_epochs'][1]
        ea,eb,ec=[mean_elements(s,reference) for s in (a,b,c)]
        motion=b.no_kozai*1440/(2*np.pi);angular=sn/radius
        sigma=np.r_[1.5*motion/radius*sr,angular,angular/max(abs(np.sin(b.inclo)),.1),np.clip(abs(ea[3:]-eb[3:]),1e-5,5e-4)]
        delta=ec-eb;delta[2]=(delta[2]+np.pi)%(2*np.pi)-np.pi
        rows.append(dict(norad=n,validation_time_ns=target,z=delta/sigma,sigma=sigma,
            version_epochs=row['version_epochs']))
    selection=select(rows)
    write(OUT/(case+'.json'),dict(case=case,selection=selection,transitions=rows,
        columns=['mean_motion','inclination','RAAN','e_cos_perigee','e_sin_perigee'],
        source_sha256=sha(Path(__file__)),forecast_sha256=sha(FORECAST/(case+'.json')),
        history_sha256=sha(HISTORY/(case+'.json')),no_GPS_RF_or_post_scan_TLE_used=True,
        orbit_phase_prior_not_retrained=True,parameter_difference_covariance_is_conservative_proxy_not_orbit_truth=True))
    print(case,selection['model'],'qualified',selection['qualified'],'gain',selection.get('validation_relative_gain'),
          'eigenvalues',np.linalg.eigvalsh(selection['covariance']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True);run(parser.parse_args().case)
