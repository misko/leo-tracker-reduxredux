import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('phase_likelihood',ROOT/'2026_09_27_ds6_phase_likelihood/run.py');phase=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase)
spec=importlib.util.spec_from_file_location('correlation',ROOT/'2026_09_27_ds6_likelihood_association/prepare.py');corr=importlib.util.module_from_spec(spec);spec.loader.exec_module(corr)


def main():
    src=ROOT/'2026_09_27_ds6_phase_expansion';selection=json.loads((src/'protocol.json').read_text());f=np.linspace(-375,375,751);delta=np.linspace(-np.pi,np.pi,720,endpoint=False);slopes=np.linspace(-.2,.2,41);weights=np.ones(41);weights[[0,-1]]=.5;weights/=weights.sum();scans=[]
    for record in selection['selected']:
        sid=record['session_id'];planpath=src/(sid+'-plan.json');plan=json.loads(planpath.read_text());cachepath=src/(sid+'-frames.json');cache=json.loads(cachepath.read_text());replaypath=src/(sid+'-replay.json');replay=json.loads(replaypath.read_text());assert replay['complete'];groups=[]
        for group in plan['selected_groups']:
            visits=[v for v in plan['selected'] if v['group']==group['group'] and v['partition']=='train'];assert len(visits)==2;obs=[]
            for v in visits:
                windows=[w for w in cache if w['group']==v['group'] and w['visit']==v['visit']];assert windows;ref=float(np.mean([w['start_ms']/1000+.0035 for w in windows]));ll=np.zeros((len(slopes),len(delta)))
                for w in windows:
                    post=phase.posterior(phase.base.extract(w['frame'],'fit'),16.,f,delta);shift=2*np.pi*slopes*(w['start_ms']/1000+.0035-ref);density=np.array(post['probability'])*len(delta)
                    ll+=np.log(np.maximum(np.interp(delta[None,:]+shift[:,None],delta,density,period=2*np.pi),1e-300))
                lp=logsumexp(ll+np.log(weights)[:,None],axis=0);prob=np.exp(lp-logsumexp(lp));relative=(v['valid_start_counter']-plan['timing']['session_start_device_sample_counter'])/plan['rate_hz']+ref
                obs.append(dict(visit=v['visit'],time_s=relative,qualified_windows=len(windows),probability=prob.tolist()))
            ids=[m['rx0_track_id'] for m in visits[0]['modes']];groups.append(dict(group=group['group'],track_ids=ids,observations=obs,correlation=corr.correlation(*[o['probability'] for o in obs]).tolist()))
        scans.append(dict(session_id=sid,rate_msps=record['sample_rate_msps'],plan_path=str(planpath.relative_to(ROOT)),plan_sha256=hashlib.sha256(planpath.read_bytes()).hexdigest(),frames_sha256=hashlib.sha256(cachepath.read_bytes()).hexdigest(),replay_sha256=hashlib.sha256(replaypath.read_bytes()).hexdigest(),groups=groups,unavailable_reason=None if groups else 'No pair meets frozen training/held requirements'))
    (HERE/'inputs.json').write_text(json.dumps(dict(selection_sha256=hashlib.sha256((src/'protocol.json').read_bytes()).hexdigest(),kappa=16.,within_dwell_slope_hz=[-.2,.2],scans=scans),indent=2)+'\n')


if __name__=='__main__':main()
