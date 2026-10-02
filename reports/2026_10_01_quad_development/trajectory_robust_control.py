"""Fixed-noise Student-t4 single-curve control on frozen mixture folds."""
import math
from pathlib import Path
import numpy as np
from run_window import prepare_window
from trajectory_mixture import design,predict
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from check_receiver_curvature import save
HERE=Path(__file__).resolve().parent


def density(residual,sigma):
    z=np.asarray(residual)/sigma
    return math.lgamma(2.5)-math.lgamma(2)-.5*math.log(4*math.pi)-math.log(sigma)-2.5*np.log1p(z*z/4)


def robust_fit(t,y,sigma):
    center=float(np.mean(t));scale=max(float(np.ptp(t)),1.);offset=float(np.mean(y));X=design(t,center,scale);v=y-offset
    beta=np.linalg.lstsq(X,v,rcond=None)[0];last=float(density(v-X@beta,sigma).sum());converged=False
    for i in range(100):
        z=(v-X@beta)/sigma;w=np.sqrt(5/(4+z*z));beta=np.linalg.lstsq(X*w[:,None],v*w,rcond=None)[0]
        value=float(density(v-X@beta,sigma).sum())
        if value<last-1e-7:raise AssertionError('nonmonotone robust control')
        if abs(value-last)<1e-7*len(t):converged=True;break
        last=value
    return dict(beta=beta.tolist(),center=center,scale=scale,offset=offset,converged=converged,iterations=i+1)


def main():
    source=HERE/'trajectory-mixture-v1.json';data=sealed(source);verify_sources(data['sources']);verify_sources(data['inputs'])
    original=sealed(HERE/'radio-segmentation-v1.json');lookup={r['track_id']:r for s in original['scans'] for r in s['tracks']};rows=[]
    for scan in data['scans']:
        for track in scan['tracks']:
            raw=lookup[track['track_id']];t=np.array(raw['times_s']);y=np.array(raw['frequencies_hz'])
            for fold in track['folds']:
                sigma=fold['sigma_hz'];train=np.arange(len(t))%2==fold['training_parity'];held=~train
                model=robust_fit(t[train],y[train],sigma)
                if model['converged']:
                    ll=float(density(y[held]-model['offset']-design(t[held],model['center'],model['scale'])@np.array(model['beta']),sigma).sum())
                    policy=fold['baseline_log_score']+fold['selected_gain'];gain=policy-ll
                else:ll=gain=None
                rows.append(dict(unit=scan['unit'],track_index=track['track_index'],sigma_hz=sigma,training_parity=fold['training_parity'],
                    held_points=fold['held_points'],mixture_selected=fold['mixture_selected'],model=model,robust_log_score=ll,policy_minus_robust=gain))
    save(HERE/'trajectory-robust-control-v1.json',dict(rows=rows,inputs={str(source):digest(source),str(HERE/'radio-segmentation-v1.json'):digest(HERE/'radio-segmentation-v1.json')},
        sources={str(HERE/n):digest(HERE/n) for n in ('trajectory_robust_control.py','TRAJECTORY_ROBUST_CONTROL_PLAN.md','test_trajectory_robust_control.py')},
        qualification='Fixed Gaussian mixture selection versus fitted Student-t4 single-curve surrogate; no mixture refit or geographic inference.'))
    for unit in sorted({r['unit'] for r in rows}):
        for sigma in (100,300):
            group=[r for r in rows if r['unit']==unit and r['sigma_hz']==sigma];valid=[r for r in group if r['model']['converged']];selected=[r for r in valid if r['mixture_selected']]
            print(unit,sigma,'converged',len(valid),'/',len(group),'policygain',sum(r['policy_minus_robust'] for r in valid)/sum(r['held_points'] for r in valid),'selectedgain',sum(r['policy_minus_robust'] for r in selected)/sum(r['held_points'] for r in selected) if selected else None)


if __name__=='__main__':main()
