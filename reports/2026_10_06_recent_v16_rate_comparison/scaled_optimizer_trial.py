"""Matched 60-second SLSQP scaling pilot, preserving the physical objective."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import factorial as study

OUT=study.OUT/'optimizer-scaling-v1'
REPORT=study.REPORT/'optimizer-scaling-v1'


class Scaled:
    def __init__(self,obj,divisor):
        if not np.isfinite(divisor) or divisor<=0:raise ValueError('Positive finite divisor required')
        self.obj=obj;self.divisor=float(divisor)
    def __getattr__(self,name):return getattr(self.obj,name)
    def evaluate(self,vector):
        value,gradient=self.obj.evaluate(vector)
        return value/self.divisor,gradient/self.divisor


def run(arm,mode):
    from position_score_sweep import Objective,SPECS,finish
    from polish_position_score_sweep import slsqp_fit
    source=study.OUT/f'positions/R100-02/original/T1AT/off/{arm}.json'
    old=json.loads(source.read_text())
    with np.load(source.parent/'input.npz',allow_pickle=False) as z:
        data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    assert old['input_sha256']==study.stage.sha(source.parent/'input.npz')
    divisor=len(data.times) if mode=='per-window' else 1.
    signature=dict(source_sha256=study.stage.sha(source),input_sha256=old['input_sha256'],
        implementation_sha256=study.stage.sha(__file__),budget_s=60.,divisor=divisor)
    path=OUT/f'{arm}-{mode}.json'
    if path.exists():
        saved=json.loads(path.read_text());assert saved['signature']==signature;return saved
    obj=Objective(data,old['input_metadata']['rf_center_hz'],arm,SPECS['C0'])
    before=finish(obj,data,old['best'])
    assert abs(before['objective']-old['objective'])<1e-7
    new=slsqp_fit(Scaled(obj,divisor),old['best'],60.,radius_km=4.)
    new['objective']*=divisor
    # Judge convergence using the original, unscaled physical loss, never the
    # scaled optimizer's KKT number or its success flag.
    after=finish(obj,data,new)
    assert abs(after['objective']-new['objective'])<1e-7
    new.update(objective=after['objective'],kkt_residual=after['kkt'],success=after['converged'])
    assert after['objective']<=before['objective']+1e-7
    result=dict(arm=arm,mode=mode,signature=signature,source=str(source),before=before,
        best=new,after=after)
    study.stage.save(path,result)
    print(json.dumps(dict(arm=arm,mode=mode,error_m=after['distance_m'],
        objective_change=after['objective']-before['objective'],kkt=after['kkt'],converged=after['converged'])),flush=True)
    return result


def report():
    from build_report import table
    rows=[json.loads(p.read_text()) for p in sorted(OUT.glob('*.json'))]
    REPORT.mkdir(parents=True,exist_ok=True)
    body=['# Equal budget optimizer scaling pilot',
        'This pilot tests R100-02 original measurements, T1-AT scoring, cones off. '
        'Ordinary SLSQP and per-window loss-scaled SLSQP each receive 60 seconds from '
        'the same saved baseline solution in each RF arm. The objective and gradient '
        'are divided by the number of associated windows only inside the latter solver. '
        'This leaves the exact minimizer unchanged but changes numerical scaling and '
        'effective stopping behavior. All final convergence checks use the original unscaled loss.',
        'Both arms retain their original observations, satellites, priors, timing limits, '
        'and 4 km boundary. Results are saved separately from the main experiment. '
        'This is a targeted difficult-case pilot, not evidence of a cohort-wide improvement.',
        f'{len(rows)} of 4 planned trials saved.',
        table(['RF','Optimizer','Before error m','After error m','Loss change','Unscaled KKT','Converged','Boundary'],
            [[r['arm'],r['mode'],f"{r['before']['distance_m']:.1f}",f"{r['after']['distance_m']:.1f}",
              f"{r['after']['objective']-r['before']['objective']:+.6f}",f"{r['after']['kkt']:.6g}",
              r['after']['converged'],r['after']['boundary']] for r in rows]),
        'Run `scaled_optimizer_trial.py` using the scientific Python environment. '
        'Every receipt records input, baseline, and implementation hashes. Lower loss '
        'is not automatically lower position error, and unconverged points are not minima.']
    (REPORT/'report.md').write_text('\n\n'.join(body)+'\n')


if __name__=='__main__':
    study.freeze()
    for arm in study.stage.ARMS:
        for mode in ('ordinary','per-window'):
            run(arm,mode);report()
