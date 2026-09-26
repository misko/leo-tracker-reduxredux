"""Score tone-pivot phase against original held phase using identical CFO banks."""
from pathlib import Path
import argparse,json
import numpy as np
from timing_trial import options,evaluate

HERE=Path(__file__).resolve().parent
OUT=HERE/'spectral-audit'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,choices=[0,1],required=True);parser.add_argument('--first-window',action='store_true');args=parser.parse_args()
    sid=['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3'][args.scan]
    data=json.loads((OUT/(sid+'.json')).read_text());rows=[r for r in data['rows'] if not args.first_window or r['start_ms']==0];result=[]
    for fold in (0,1):
        baseline=json.loads((HERE/'timing-trial'/f'{sid}-f{fold}-q33.json').read_text());obs=baseline['observations'];train=np.array(baseline['phase_training_mask'],bool)
        phases={}
        for field in ('original_held_phase','held_pivot_phase'):
            y=[]
            for o in obs:
                modes=[sorted([r for r in rows if r['visit']==o['visit'] and r['mode']==m],key=lambda r:r['start_ms']) for m in (0,1)]
                assert len(modes[0])==len(modes[1])==(1 if args.first_window else 6)
                diff=np.array([r[field] for r in modes[1]])-np.array([r[field] for r in modes[0]])
                y.append(float(np.angle(np.mean(np.exp(1j*diff)))))
            phases[field]=np.array(y)
        banks=[dict(np.load(HERE/'timing-trial'/f'{sid}-f{fold}-{tid[7:19]}.npz')) for tid in baseline['track_ids']]
        if args.first_window:
            # The bank uses the mean of six window epochs. Shift only its phase
            # geometry, not the CFO timing prior/posterior, to the first epoch.
            # Propagation uses receive_time + tau, so interpolate the existing
            # 0.2-second tau grid at tau-0.0525 s. Boundary extrapolation is linear.
            dt=-.0525
            for bank in banks:
                tau=bank['taus'];old_projection=bank['projection'];new=np.empty_like(old_projection)
                for candidate in range(len(old_projection)):
                    for dwell in range(len(obs)):
                        y=old_projection[candidate,:,dwell];x=tau+dt
                        new[candidate,:,dwell]=np.interp(x,tau,y)
                        low=x<tau[0];new[candidate,low,dwell]=y[0]+(x[low]-tau[0])*(y[1]-y[0])/(tau[1]-tau[0])
                bank['projection']=new
        for sigma in (100,200):
            a,b=[options(bank,sigma,33) for bank in banks]
            for name,y in phases.items():
                scored=evaluate(a,b,y,train,np.array([r['f0'] for r in obs]),np.array([r['f1'] for r in obs]),1)
                scored.update(fold=fold,sigma=sigma,arm=name,phase_rad=y.tolist());result.append(scored)
                print(sid,fold,sigma,name,'gain',scored['cfo_gain'],flush=True)
    suffix='-first-window-scores.json' if args.first_window else '-scores.json'
    (OUT/(sid+suffix)).write_text(json.dumps(dict(session_id=sid,first_window_only=args.first_window,phase_epoch_shift_s=-.0525 if args.first_window else 0,phase_geometry_method='Linear interpolation in existing 0.2-second orbit-time grid; lower boundary linear extrapolation' if args.first_window else 'Original direct propagation',meaning='Exploratory fixed start_ms=0 restriction after conditional mode-support audit; acquisition-conditioned, not independent confirmation' if args.first_window else 'All six windows retained',experiments=result),indent=2)+'\n')

if __name__=='__main__':main()
