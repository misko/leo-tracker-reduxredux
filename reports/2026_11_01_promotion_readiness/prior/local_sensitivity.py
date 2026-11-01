"""Fixed RF-position sensitivity, no parameter or cell selection."""
import copy
import sys
import time
import numpy as np
import ablate as a


def main():
    out=a.OUT/'local_sensitivity.json'
    if out.exists():raise FileExistsError(out)
    spec=dict(created_utc_ns=time.time_ns(),cells=list(a.CELLS),step_km=.05,
        centers='Saved ALGO06 RF endpoint per arm; fixed saved phase reference',
        predictive_subcells=['width','radial','cross'],
        scope='Descriptive local frequency-score sensitivity only; not a refit, predictive validation, or localization selection',
        code_sha256=a.e.sha(__file__),parent_spec_sha256=a.e.sha(a.OUT/'spec.json'))
    a.e.write(a.OUT/'local_sensitivity_spec.json',spec)
    d,hd,z,_,_=a.contexts();rows=[]
    offsets=np.array([[0,0],[.05,0],[-.05,0],[0,.05],[0,-.05]])
    for name,parts in a.CELLS.items():
        dd=a.mixed(d,hd,z,parts)
        for arm,(p,x) in dd['problems'].items():
            scores=np.array([a.e.objective(p,dd,x+v) for v in offsets])
            rows.append(dict(cell=name,arm=arm,scores=scores,
                gradient_per_km=[(scores[1]-scores[2])/.1,(scores[3]-scores[4])/.1]))
    sub=[]
    if len(d['families'])!=1 or len(hd['families'])!=1:raise ValueError('one mixture expected')
    old,new=d['families'][0],hd['families'][0]
    np.testing.assert_array_equal(old.phases,new.phases)
    np.testing.assert_array_equal(old.bank['position_km'],new.bank['position_km'])
    for cell in ('original','width','radial','cross','complete'):
        f=copy.copy(old);f.modes={k:np.array(v,copy=True) for k,v in old.modes.items()}
        if cell in ('width','complete'):
            f.logprior=new.logprior.copy();f.distribution=new.distribution
        for k in ('position_km','velocity_km_s'):
            if cell in ('radial','complete'):f.modes[k][0::3]=new.modes[k][0::3]
            if cell in ('cross','complete'):
                f.modes[k][1::3]=new.modes[k][1::3];f.modes[k][2::3]=new.modes[k][2::3]
        for arm,(p,x) in d['problems'].items():
            scores=np.array([f.evaluate(p,x+v,d['powers'],d['entries']) for v in offsets])
            sub.append(dict(cell=cell,arm=arm,scores=scores,
                gradient_per_km=[(scores[1]-scores[2])/.1,(scores[3]-scores[4])/.1]))
    a.e.write(out,dict(rows=rows,predictive_subcells=sub,spec=spec))
    print('Local score sensitivity complete',flush=True)


if __name__=='__main__':main()
