"""Training-only raw-carrier extrapolation; no satellite or position inference."""
import argparse,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-recovery-replay-20261016'))
from replay import replay
from leo.analysis.regional_position_score import ALIAS_HZ,circular

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input',type=Path,required=True);parser.add_argument('--tle-root',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.fold='early_to_late'
if args.output.exists():raise FileExistsError('Use a new diagnostic filename')
ctx=replay(args,return_context=True);results=[]
for target in ctx.derivation['targets']:
    for fold in ['early_to_late','late_to_early']:
        train=np.array(target['training_rows' if fold=='early_to_late' else 'test_rows'])
        test=np.array(target['test_rows' if fold=='early_to_late' else 'training_rows'])
        t=ctx.observations.times_s[train];center=float(t.mean());scale=float(np.ptp(t))
        y=np.unwrap(ctx.observations.measured_hz[train]*2*np.pi/ALIAS_HZ)*ALIAS_HZ/(2*np.pi)
        for degree in [1,2,3]:
            coefficients=np.polyfit((t-center)/scale,y,degree)
            fitted=np.polyval(coefficients,(t-center)/scale)
            predicted=np.polyval(coefficients,(ctx.observations.times_s[test]-center)/scale)
            error=circular(ctx.observations.measured_hz[test]-predicted)
            results.append(dict(track=target['track'],fold=fold,degree=degree,
                training_count=len(train),test_count=len(test),training_rms_hz=float(np.sqrt(np.mean((y-fitted)**2))),
                test_rms_hz=float(np.sqrt(np.mean(error**2))),test_residuals_hz=error.tolist()))
payload=dict(scope='Raw-carrier diagnostic only, with polynomial degree fixed in advance to 1, 2 or 3 and no selection by test error. Phase unwrapping and coefficients use training values only; held residuals use the original alias wrapping. No orbit calibration, satellite assignment or position estimate is learned. The TLE archive is used solely by the shared context verifier.',results=results)
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.open('x') as stream:json.dump(payload,stream,indent=2);stream.write('\n')
print(json.dumps([{k:v for k,v in r.items() if k!='test_residuals_hz'} for r in results],indent=2))
