"""Keep identities and all CFO data fixed; reset only the phase reference."""
from pathlib import Path
import json,time
import numpy as np
from cfo_scale_mixture import mixed_options,refine_bank
from shared_baseline_trial import load,SESSIONS
from timing_trial import evaluate

HERE=Path(__file__).resolve().parent
OUT=HERE/'phase-episodes'

def labels(times,breaks):
    return np.searchsorted(np.sort(np.asarray(breaks)),times,side='right')

def main():
    OUT.mkdir(exist_ok=True);start=time.monotonic()
    audit=json.loads((HERE/'cfo-scale-mixture/pilot-epoch-audit.json').read_text())
    model=json.loads((HERE/'timing-calibration.json').read_text())['model']
    scales=[3.125,6.25,12.5,25,50,100,200,400,800,1600]
    protocol=dict(selection='Use every acquisition-only causal timing break already reported; no phase or held CFO selects breaks.',model='Independent uniform phase intercept per episode; same identity, orbit timing and baseline across episodes. All CFO and phase observations retained.',baseline='Uniform signed -2..2m, 81 points',scales_hz=scales,tau_step_s=.025,quantiles=33,limitations='Retrospective fixed candidate banks and folds; not full-catalogue episode re-association or identity truth.')
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');results=[]
    for sid in SESSIONS:
        breaks=sorted(r['time_s'] for t in audit['tracks'] if t['session_id']==sid for r in t['breaks'])
        for fold in (0,1):
            target,obs,banks=load(sid,fold)
            opts=[mixed_options(refine_bank(b,model,.025),scales,33)[0] for b in banks]
            times=np.array([o['time_s'] for o in target['observations']])+np.array(obs['phase_epoch_offsets_s'])
            groups=labels(times,breaks)
            for arm,g in [('continuous',np.zeros(len(times),int)),('timing_episodes',groups)]:
                score=evaluate(*opts,np.array(obs['phase_rad']),np.array(obs['training_mask'],bool),np.array([o['f0'] for o in target['observations']]),np.array([o['f1'] for o in target['observations']]),np.array(obs['kappa']),phase_groups=g)
                score.update(session_id=sid,fold=fold,arm=arm,break_times_s=breaks,phase_groups=g.tolist(),phase_times_s=times.tolist(),training_mask=obs['training_mask'])
                results.append(score);print(sid,fold,arm,score['cfo_gain'],score['phase_gain_vs_constant'],flush=True)
            (OUT/'results.json').write_text(json.dumps(dict(protocol=protocol,experiments=results,elapsed_s=time.monotonic()-start),indent=2)+'\n')

if __name__=='__main__':main()
