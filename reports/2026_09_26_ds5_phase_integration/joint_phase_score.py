"""Separate source qualification from phase evaluation in the catalogue trial."""
from pathlib import Path
import argparse,json
import numpy as np
from timing_trial import options,evaluate

HERE=Path(__file__).resolve().parent
OUT=HERE/'joint-phase'

def shift_geometry(bank,offsets):
    result=dict(bank);tau=bank['taus'];old=bank['projection'];new=np.empty_like(old)
    for candidate in range(len(old)):
        for dwell,dt in enumerate(offsets):
            y=old[candidate,:,dwell];x=tau+dt;new[candidate,:,dwell]=np.interp(x,tau,y)
            lo=x<tau[0];hi=x>tau[-1]
            new[candidate,lo,dwell]=y[0]+(x[lo]-tau[0])*(y[1]-y[0])/(tau[1]-tau[0])
            new[candidate,hi,dwell]=y[-1]+(x[hi]-tau[-1])*(y[-1]-y[-2])/(tau[-1]-tau[-2])
    result['projection']=new
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,choices=[0,1],required=True);args=parser.parse_args();sid=['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3'][args.scan]
    data=json.loads((OUT/(sid+'.json')).read_text());old=json.loads((HERE/'long-overlap'/(sid+'.json')).read_text())['rows'];output=[];observation_sets=[]
    protocol=dict(session_id=sid,arms=['original_all','joint_all','original_qualified','joint_qualified'],kappa='1 per supported dwell; 0 when none of six windows qualifies; no precision multiplication by window count',qualification='Fixed joint-pilot check on qualification sample blocks; no phase-evaluation samples used in support decisions',geometry='Mean selected window epoch; interpolate 0.2-second timing grid with linear boundary extrapolation for offsets at most 52.5ms',evaluation='Same CFO candidate banks, timing priors and whole-dwell folds as timing trial; all 18 dwell slots retained; retrospective conditional test')
    (OUT/(sid+'-score-protocol.json')).write_text(json.dumps(protocol,indent=2)+'\n')
    for fold in (0,1):
        base=json.loads((HERE/'timing-trial'/f'{sid}-f{fold}-q33.json').read_text());obs=base['observations'];train=np.array(base['phase_training_mask'],bool)
        banks=[dict(np.load(HERE/'timing-trial'/f'{sid}-f{fold}-{tid[7:19]}.npz')) for tid in base['track_ids']]
        for arm in protocol['arms']:
            y=[];k=[];offsets=[];counts=[]
            for o in obs:
                rr=[r for r in data['rows'] if r['visit']==o['visit'] and ('qualified' not in arm or r['both_qualified'])];counts.append(len(rr))
                if not rr:y.append(0.);k.append(0.);offsets.append(0.);continue
                phases=[]
                for r in rr:
                    if arm.startswith('joint'):
                        phases.append(r['modes'][1]['evaluation']['phase_rad']-r['modes'][0]['evaluation']['phase_rad'])
                    else:
                        pair=[next(v for v in old if v['visit']==o['visit'] and v['start_ms']==r['start_ms'] and v['mode']==m) for m in (0,1)]
                        phases.append(pair[1]['coefficients']['held']['phase_rad']-pair[0]['coefficients']['held']['phase_rad'])
                y.append(float(np.angle(np.mean(np.exp(1j*np.array(phases))))));k.append(1.);offsets.append((np.mean([r['start_ms'] for r in rr])-52.5)/1000)
            observation_sets.append(dict(fold=fold,arm=arm,visits=[o['visit'] for o in obs],phase_rad=y,kappa=k,window_counts=counts,phase_epoch_offsets_s=offsets,training_mask=train.tolist()))
            shifted=[shift_geometry(bank,offsets) for bank in banks]
            for sigma in (100,200):
                a,b=[options(bank,sigma,33) for bank in shifted]
                result=evaluate(a,b,np.array(y),train,np.array([o['f0'] for o in obs]),np.array([o['f1'] for o in obs]),np.array(k));result.update(fold=fold,sigma=sigma,arm=arm,supported_training_dwells=int(np.sum(np.array(k)[train])),supported_evaluation_dwells=int(np.sum(np.array(k)[~train])));output.append(result)
                print(sid,fold,sigma,arm,'gain',round(result['cfo_gain'],6),'supported',sum(k),flush=True)
        (OUT/(sid+'-scores.json')).write_text(json.dumps(dict(protocol=protocol,observation_sets=observation_sets,experiments=output),indent=2)+'\n')

if __name__=='__main__':main()
