"""Isolate the phase extractor change using unchanged CFO proposal banks."""
import json
import numpy as np
from joint_phase_score import shift_geometry
from timing_trial import evaluate,options
from shared_baseline_trial import load,SESSIONS
from shared_rate_trial import HERE,OUT

def main():
    data=json.loads((OUT/'results.json').read_text());results=[];summaries=[]
    for scan in data['scans']:
        sid=scan['session_id'];old_scores=json.loads((HERE/'joint-phase'/f'{sid}-scores.json').read_text())['experiments']
        for kind in ('independent','shared'):
            errors=[]
            for r in scan['rows']:
                m=r[kind]['modes'];delta=(m[1]['evaluation']['phase_rad']-m[0]['evaluation']['phase_rad'])-(m[1]['train']['phase_rad']-m[0]['train']['phase_rad']);errors.append(np.angle(np.exp(1j*delta)))
            summaries.append(dict(session_id=sid,arm=kind,qualified_windows=len(errors),train_eval_rms_deg=float(np.degrees(np.sqrt(np.mean(np.array(errors)**2))))))
        for fold in (0,1):
            target,obs,banks=load(sid,fold);y=[]
            for o in target['observations']:
                rows=[r for r in scan['rows'] if r['visit']==o['visit']]
                phases=[r['shared']['modes'][1]['evaluation']['phase_rad']-r['shared']['modes'][0]['evaluation']['phase_rad'] for r in rows]
                y.append(float(np.angle(np.mean(np.exp(1j*np.array(phases)))))) if phases else y.append(0.)
            for sigma in (100,200):
                a,b=[options(bank,sigma,33) for bank in banks]
                score=evaluate(a,b,np.array(y),np.array(obs['training_mask'],bool),np.array([o['f0'] for o in target['observations']]),np.array([o['f1'] for o in target['observations']]),np.array(obs['kappa']))
                baseline=next(r for r in old_scores if r['fold']==fold and r['sigma']==sigma and r['arm']=='joint_qualified')
                assert np.isclose(score['exact_cfo_held'],baseline['exact_cfo_held'])
                results.append(dict(session_id=sid,fold=fold,sigma_hz=sigma,independent_phase_gain_nats=baseline['cfo_gain'],shared_phase_gain_nats=score['cfo_gain'],difference_nats=score['cfo_gain']-baseline['cfo_gain'],shared_phase_vs_constant=score['phase_gain_vs_constant']))
                print(results[-1],flush=True)
        (OUT/'scores.json').write_text(json.dumps(dict(protocol='Same qualified window set, geometry epochs, retained CFO candidates and 100/200Hz scenarios as joint-phase report. Only extraction rate model changes. Original .2s timing bank; not the later causal quality model. No claim of independent satellite truth.',repeatability=summaries,comparisons=results),indent=2)+'\n')

if __name__=='__main__':main()
