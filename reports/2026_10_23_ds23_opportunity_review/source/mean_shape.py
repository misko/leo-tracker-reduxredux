"""Exact joint Gaussian temporal-contrast/level decomposition at frozen RF endpoints."""
from pathlib import Path
import sys
import numpy as np
import mechanism as m
sys.path.insert(0,'/srv/bulk/leo/research/algo04-native-mechanisms-20261023/audit')
from diagnostics import decompose

OUT=Path(__file__).resolve().parents[1]


def score(y,k):
    root=np.linalg.cholesky((k+k.T)/2)
    q=float(np.linalg.solve(root,y)@np.linalg.solve(root,y))
    logdet=float(2*np.log(np.diag(root)).sum())
    return dict(quadratic=q,logdet=logdet,normalization=float(len(y)*np.log(2*np.pi)),
                total=q+logdet+len(y)*np.log(2*np.pi))


def split(y,k,slices):
    n=len(y);means=[];contrasts=[]
    for a,b in slices:
        length=b-a
        basis=np.linalg.qr(np.ones((length,1)),mode='complete')[0]
        mean=np.zeros(n);mean[a:b]=basis[:,0];means.append(mean)
        for col in basis[:,1:].T:
            row=np.zeros(n);row[a:b]=col;contrasts.append(row)
    c=np.asarray(contrasts);u=np.asarray(means);t=np.vstack((c,u))
    assert np.allclose(t@t.T,np.eye(n))
    yc,ym=c@y,u@y;kcc=c@k@c.T;kmc=u@k@c.T;kmm=u@k@u.T
    conditional_y=ym-kmc@np.linalg.solve(kcc,yc)
    conditional_k=kmm-kmc@np.linalg.solve(kcc,kmc.T)
    a,b,whole=score(yc,kcc),score(conditional_y,conditional_k),score(y,k)
    assert abs(a['total']+b['total']-whole['total'])<1e-5
    return dict(contrasts=a,levels_given_contrasts=b,whole=whole,
                contrast_dimensions=len(yc),level_dimensions=len(ym),
                replay_difference=a['total']+b['total']-whole['total'])


def main():
    protocol=dict(cases=['DS23-0259','DS23-0353'],arms=list(m.ARMS),
                  endpoints=['graph_parent','ordinary_native'],source_sha256=m.sha(Path(__file__)),
                  decomposition='orthonormal within-path temporal contrasts then conditional per-path means; exact full shared Gaussian covariance',
                  interpretation='conditional factorization diagnostic; not independent causal effects, not an alternative accepted objective',
                  fixed_observations_aliases_priors=True,no_GPS_or_new_position_fit=True)
    m.write(OUT/'protocol.json',protocol);rows=[]
    for case in protocol['cases']:
        parent,kind,fragments,record=m.load(case);full=m.append(parent,fragments)
        ordinary=m.read(m.FROZEN/'raw'/case/'native'/(case+'.json'))['methods']['persistent5s']['arms']
        for arm in m.ARMS:
            for label,pair in [('graph_parent',record['ordinary_graph']['arms']),('ordinary_native',ordinary)]:
                s=pair[arm];p=m.exp.paths.build(full,kind,arm,s['phase_reference']);x=np.asarray(s['endpoint_east_north_km'])
                d=decompose(p,x,full['powers'])
                parts=split(d['raw_residual_hz'],d['covariance_hz2'],d['entry_slices'])
                rows.append(dict(case=case,arm=arm,endpoint=label,parts=parts,
                                 curved_objective=d['curved_objective'],total_objective=d['total_objective'],
                                 full_score_replay_difference=d['replay_difference']))
    m.write(OUT/'mean_shape.json',dict(protocol=protocol,rows=rows))
    for case in protocol['cases']:
        for arm in m.ARMS:
            a,b=[r for r in rows if r['case']==case and r['arm']==arm]
            print(case,arm,{k:b['parts'][k]['total']-a['parts'][k]['total'] for k in ['contrasts','levels_given_contrasts','whole']},flush=True)


if __name__=='__main__':main()
