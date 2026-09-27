"""Prepare training-visit phase likelihoods without reading held phase values."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent


def correlation(a,b):
    # mean_theta L1(theta)*L2(theta+shift), with densities relative to uniform.
    a=np.array(a)*len(a);b=np.array(b)*len(b)
    return np.maximum(np.fft.ifft(np.conj(np.fft.fft(a))*np.fft.fft(b)).real/len(a),0.)


def main():
    ppath=ROOT/'2026_09_27_ds6_phase_likelihood/results.json';pp=json.loads(ppath.read_text());srcpath=ROOT/'2026_09_27_ds6_differential_cfo/results.json';src=json.loads(srcpath.read_text());delta=np.array(pp['phase_grid_rad']);slopes=np.linspace(-.2,.2,41);weight=np.ones(41);weight[[0,-1]]=.5;weight/=weight.sum();rows=[]
    for s in src['scans']:
        phase=next(p for p in pp['scans'] if p['session_id']==s['session_id']);groups=[]
        for g in s['groups']:
            observations=[]
            for o in g['phase_observations']:
                if not o['train']:continue
                windows=[w for w in phase['windows'] if w['group']==g['group'] and w['visit']==o['visit']];assert len(windows)==o['windows'];ref=float(np.mean([w['start_ms']/1000+.0035 for w in windows]));ll=np.zeros((len(slopes),len(delta)))
                for w in windows:
                    density=np.array(w['arms']['16.0']['probability'])*len(delta)
                    shift=2*np.pi*slopes*(w['start_ms']/1000+.0035-ref)
                    ll+=np.log(np.maximum(np.interp(delta[None,:]+shift[:,None],delta,density,period=2*np.pi),1e-300))
                lp=logsumexp(ll+np.log(weight)[:,None],axis=0);prob=np.exp(lp-logsumexp(lp));observations.append(dict(visit=o['visit'],time_s=o['time_s'],windows=len(windows),probability=prob.tolist()))
            assert len(observations)==2
            groups.append(dict(group=g['group'],track_ids=g['track_ids'],observations=observations,offset_correlation=correlation(*[o['probability'] for o in observations]).tolist()))
        rows.append(dict(session_id=s['session_id'],groups=groups))
    output=dict(phase_source_sha256=hashlib.sha256(ppath.read_bytes()).hexdigest(),cfo_source_sha256=hashlib.sha256(srcpath.read_bytes()).hexdigest(),
                kappa=16.,within_dwell_slope_hz=[-.2,.2],phase_nodes=len(delta),scans=rows)
    (HERE/'inputs.json').write_text(json.dumps(output,indent=2)+'\n')


if __name__=='__main__':main()
