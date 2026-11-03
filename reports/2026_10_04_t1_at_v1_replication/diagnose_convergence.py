"""Finite-difference and visibility checks at saved continuation solutions."""
import json
from types import SimpleNamespace
import numpy as np
import subset_positions as positions
from resume_position_convergence import OUT


def objective_for(scan,arm):
    positions.enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    root=positions.ROOT/scan
    meta=json.loads((root/'input.json').read_text())
    with np.load(root/'input.npz') as z:d=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    obj=CalibrationObjective(d,d.initial,np.arange(len(d.numbers)),False,120.)
    obj.center=meta['rf_center_hz'];obj.features=((d.rf-obj.center)/1e9)[:,None]
    obj.likelihood.features=obj.features
    obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-20.)
    obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,20.)
    obj.base.deadline=float('inf')
    if arm=='zero-c':obj.bounds[-1]=(0.,0.)
    return obj,d


def run():
    from position_direct import coordinate,coordinate_jacobian
    out=[]
    for path in sorted(OUT.glob('N*-*.json')):
        if '.partial.' in path.name:continue
        r=json.loads(path.read_text())
        if r['converged']:continue
        obj,d=objective_for(r['scan'],r['arm'])
        v=np.array(r['best']['vector']);p=np.array(r['best']['point_km']);scale=obj.scale.copy();scale[:2]=1.
        z=v/scale;z[:2]=p
        def evaluate(z):
            v=z*scale;v[:2]=coordinate(z[:2])
            f,g=obj.evaluate(v);g0=g.copy();g*=scale;g[:2]=coordinate_jacobian(z[:2]).T@g0[:2]
            _,visible=obj.base.predict(v[:obj.size])
            return f,g,visible
        f,g,visible=evaluate(z)
        free=[i for i,(lo,hi) in enumerate(obj.bounds) if lo is None or lo!=hi]
        indices=sorted(free,key=lambda i:-abs(g[i]))[:4]
        if r['scan']!='N08':indices=[6]
        tests=[]
        for i in indices:
            for step in [1e-4,1e-6,1e-8]:
                direction=np.eye(len(z))[i]*step
                fm,gm,vm=evaluate(z-direction);fp,gp,vp=evaluate(z+direction)
                tests.append(dict(index=i,scale=float(scale[i]),step=step,analytic=float(g[i]),
                                  minus_slope=float((f-fm)/step),plus_slope=float((fp-f)/step),
                                  minus_gradient=float(gm[i]),plus_gradient=float(gp[i]),
                                  visibility_flips_minus=int(sum((vm!=visible).ravel())),
                                  visibility_flips_plus=int(sum((vp!=visible).ravel()))))
        out.append(dict(scan=r['scan'],arm=r['arm'],distance_m=r['distance_m'],position_change_m=r['position_change_m'],
                        kkt=r['best']['kkt_residual'],score_change=r['delta_score'],tests=tests))
    (OUT/'finite-difference-audit.json').write_text(json.dumps(out,indent=2))
    for r in out:
        print(r['scan'],r['arm'],'movement',r['position_change_m'],'KKT',r['kkt'])
        if r['scan']=='N08':print(json.dumps(r['tests'],indent=2))


if __name__=='__main__':
    positions.enable_research_model()
    run()
