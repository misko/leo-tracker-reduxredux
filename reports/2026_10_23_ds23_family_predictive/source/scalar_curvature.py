"""Actual scalar fitting-objective curvature at saved RF endpoints, no GPS."""
from pathlib import Path
import numpy as np
import family_predictive as f
import mechanism as m

OUT=Path(__file__).resolve().parents[1]


def differences(objective,x,h):
    x=np.asarray(x,float);v=float(objective(x));grad=np.zeros(2);hes=np.zeros((2,2))
    for i in range(2):
        dx=np.eye(2)[i]*h;plus=float(objective(x+dx));minus=float(objective(x-dx))
        grad[i]=(plus-minus)/(2*h);hes[i,i]=(plus+minus-2*v)/h**2
    a=np.array([h,h]);b=np.array([h,-h])
    hes[0,1]=hes[1,0]=(objective(x+a)+objective(x-a)-objective(x+b)-objective(x-b))/(4*h*h)
    vals,vecs=np.linalg.eigh(hes)
    return dict(score=v,gradient=grad,hessian=hes,eigenvalues=vals,weak_direction=vecs[:,0],
                condition_number=float(vals[-1]/vals[0]) if vals[0]>0 else None,
                local_newton_step_km=-np.linalg.solve(hes,grad) if vals[0]>0 else None,step_km=h)


def main():
    jobs=m.read(OUT/'protocol.json')['jobs'];inputs={}
    for job in jobs:
        path=OUT/'raw'/job['name']/'result.json';inputs[str(path)]=m.sha(path)
    protocol=dict(source_sha256=m.sha(Path(__file__)),input_hashes=inputs,
                  scope='posthoc RF-only sensitivity of ALL16jobs plusgraph/fullordinary/priorfinalcontrols; noendpointselection',
                  objective='p.residual(x) squared including visibility penalties, exactly the scalar minimized byfit',
                  finite_difference_km=[.02,.05],fixed_phase_reference=True,
                  uncertainty='local Hessian diagnostic; not calibrated posterior or global basin evidence',no_GPS=True)
    path=OUT/'curvature_protocol.json'
    if path.exists():assert m.read(path)==protocol
    else:m.write(path,protocol)
    rows=[]
    for case in f.CASES:
        parent,kind,fragments,record=m.load(case);full=m.append(parent,fragments)
        native=m.read(m.FROZEN/'raw'/case/'native'/(case+'.json'))['methods']['persistent5s']['arms']
        contexts=[('graph',parent,record['ordinary_graph']['arms']),('ordinary_native',full,native),('prior_final',full,record['final']['arms'])]
        for job in jobs:
            if job['case']!=case:continue
            result=m.read(OUT/'raw'/job['name']/'result.json')
            train,_=f.training_data(full,kind,job['family'],job['mode'])
            contexts.append((job['name'],train,result['arms']))
        for name,d,pair in contexts:
            for arm,saved in pair.items():
                p=m.exp.paths.build(d,kind,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
                def objective(z):
                    r=p.residual(z);return float(r@r)
                values=[differences(objective,x,h) for h in (.02,.05)]
                row=dict(case=case,name=name,arm=arm,endpoint_east_north_km=x,curvatures=values)
                if name in ('graph','ordinary_native','prior_final'):
                    row['gauss_newton']=f.local_sensitivity(p,x)
                rows.append(row)
    m.write(OUT/'scalar_curvature.json',dict(protocol=protocol,rows=rows))
    print('Evaluated',len(rows),'saved endpoint contexts; two step sizes each.')


if __name__=='__main__':main()
