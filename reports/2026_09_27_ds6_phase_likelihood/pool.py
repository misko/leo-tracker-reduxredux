"""Whole-window prediction from marginal DD likelihoods, preserving phase."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from run import posterior,base
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent


def shifted_log_density(probability,phase_grid,shifts):
    # Periodic linear interpolation of the positive likelihood, not its log.
    prediction=phase_grid[None,:]+shifts[:,None]
    values=np.interp(prediction,phase_grid,np.array(probability)*len(phase_grid),period=2*np.pi)
    return np.log(np.maximum(values,1e-300))


def main():
    source=HERE/'results.json';results=json.loads(source.read_text());assert results['complete'];delta=np.array(results['phase_grid_rad']);f=np.linspace(-375,375,751);slopes=np.linspace(-.2,.2,41);weights=np.ones(len(slopes));weights[[0,-1]]=.5;weights/=weights.sum()
    protocol=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),seed=2026092719,kappa=16.,slope_prior_hz=[-.2,.2],slope_nodes=41,
        split='Permute six original window starts using seed+visit; first three train, last three held; intersect with original qualification',
        training='Fitting phasors from training windows only',held='Evaluation phasors from held windows only; independent receiver common phase/rate marginalized per window',
        reference='Each held window has independent uniform DD; score gain measures transfer across windows, not geographic accuracy')
    pp=HERE/'pool-protocol.json';pp.write_text(json.dumps(protocol,indent=2)+'\n');rows=[]
    for scan in results['scans']:
        sid=scan['session_id'];cache=json.loads((ROOT/'2026_09_27_ds6_phase_curvature'/(sid+'-frames.json')).read_text());lookup={(r['visit'],r['group'],r['start_ms']):r['frame'] for r in cache}
        for group,visit in sorted({(w['group'],w['visit']) for w in scan['windows']}):
            windows=[w for w in scan['windows'] if w['group']==group and w['visit']==visit];order=np.random.default_rng(protocol['seed']+visit).permutation(6)*21;train=[w for w in windows if w['start_ms'] in order[:3]];held=[w for w in windows if w['start_ms'] in order[3:]]
            row=dict(session_id=sid,group=group,visit=visit,train_starts_ms=[w['start_ms'] for w in train],held_starts_ms=[w['start_ms'] for w in held])
            if len(train)<2 or not held:
                row['unavailable_reason']='Fewer than two qualified training windows or no held window';rows.append(row);continue
            reference=float(np.mean([w['start_ms']/1000+.0035 for w in train]));lt=np.zeros((len(slopes),len(delta)));lh=np.zeros_like(lt)
            for w in train:
                lt+=shifted_log_density(w['arms']['16.0']['probability'],delta,2*np.pi*slopes*(w['start_ms']/1000+.0035-reference))
            for w in held:
                frame=lookup[visit,group,w['start_ms']];p=posterior(base.extract(frame,'evaluation'),16.,f,delta)
                lh+=shifted_log_density(p['probability'],delta,2*np.pi*slopes*(w['start_ms']/1000+.0035-reference))
            prior=np.log(weights)[:,None]-np.log(len(delta));z=logsumexp(lt+prior);prob=np.exp(logsumexp(lt+prior,axis=0)-z);mean=float(np.angle(prob@np.exp(1j*delta)));distance=abs(base.wrap(delta-mean));ii=np.argsort(distance);radius=float(np.degrees(distance[ii[np.searchsorted(np.cumsum(prob[ii]),.95)]]))
            row.update(reference_s=reference,mean_dd_rad=mean,credible95_radius_deg=radius,held_log_score_gain=float(logsumexp(lt+lh+prior)-z),phase_probability=prob.tolist());rows.append(row)
    (HERE/'pool-results.json').write_text(json.dumps(dict(complete=True,protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),rows=rows),indent=2)+'\n')
    print(json.dumps([{k:v for k,v in r.items() if k!='phase_probability'} for r in rows],indent=2))


if __name__=='__main__':main()
