"""Per-satellite chain-rule attribution at the capture-bound operator roof.

Scans are independent. Fixed top-window observations and selected satellite sets
from the earlier profile model. Refit nuisance parameters at the capture roof;
include both fitted-c and c=0 with identical priors and observation sets.
"""
import csv
import json
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
BULK=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
sys.path.insert(0,str(BULK))
from profile_top_2km import Engine,save
from replay import digest

OUT=HERE/'gradient-by-satellite'


def contribution_terms(weights,derivatives):
    """NLL derivative/Hz times Hz/km, expressed as score change per100m."""
    w=np.asarray(weights);j=np.asarray(derivatives)
    if j.shape!=w.shape+(2,) or not np.all(np.isfinite(w)) or not np.all(np.isfinite(j)):
        raise ValueError('Finite row/satellite weights and paired EN derivatives required')
    return w[:,:,None]*j*.1


def prediction(engine,vector):
    p,visible,_=engine.obj.base.predict(np.asarray(vector)[:engine.obj.size],with_jacobian=True)
    return p+(engine.obj.features@np.asarray(vector)[engine.obj.size:])[:,None],visible


def case(task):
    scan,arm=task
    evidence=json.loads((HERE/'orientation-evidence.json').read_text())
    previous=json.loads((BULK/f'position-top-2km/independent-{scan}-{arm}.json').read_text())
    engine=Engine(scan,arm)
    engine.lat,engine.lon=evidence['operator_roof_lat_lon']
    engine.cache={};engine.calls=[]
    engine.folder=OUT/f'{scan}-{arm}';engine.folder.mkdir(parents=True,exist_ok=True)
    for path in sorted(engine.folder.glob('fit-*.json')):
        r=json.loads(path.read_text());engine.calls.append(r)
        key=tuple(np.round([r['east_m'],r['north_m']],5))
        old=engine.cache.get(key)
        if old is None or (r['success'] and not old['success']) or (r['success']==old['success'] and r['objective']<old['objective']):
            engine.cache[key]=r

    def fit(point,label,start):
        for attempt in range(4):
            r=engine.fit(point,label,force_start=start)
            if engine.calls[-1]['success']:return r
            start=engine.calls[-1]['vector']
        raise RuntimeError(f'Unconverged {scan} {arm} {label}')

    restarts=[]
    for label,seed in [('prior-local-minimum',previous['best']['vector']),('prior-reference',previous['roof']['vector'])]:
        existing=[r for r in engine.calls if r['label']==label]
        if existing and existing[-1]['success']:
            last=existing[-1]
        else:
            fit([0,0],label,existing[-1]['vector'] if existing else seed)
            last=engine.calls[-1]
        restarts.append({k:last[k] for k in ('objective','success','nuisance_gradient','label')})
    roof=engine.cache[(0.,0.)]
    x=np.array(roof['vector'])
    engine.obj.base.deadline=float('inf')
    value,gradient=engine.obj.evaluate(x)
    weights=-engine.obj.likelihood.last_result['prediction_gradient'].copy()
    support=engine.obj.likelihood.last_result['row_association_probability'].copy()
    _,_,jac=engine.obj.base.predict(x[:engine.obj.size],with_jacobian=True)
    # Convert the existing regional position coordinates to local capture-roof EN.
    h=.001
    transform=np.column_stack([(engine.coordinate(np.eye(2)[i]*h)-engine.coordinate(-np.eye(2)[i]*h))/(2*h) for i in range(2)])
    unique_shared=jac.base.shared.reshape(-1,len(engine.data.numbers),6)
    shared=unique_shared[engine.obj.base.plan.inverse,:,:2]
    direct_jac=shared@transform
    direct_terms=contribution_terms(weights,direct_jac)
    direct_total=engine.position_gradient([0,0],gradient[:2])*.1
    np.testing.assert_allclose(direct_terms.sum(axis=(0,1)),direct_total,atol=1e-7,rtol=1e-8)
    assert np.all(engine.obj.base.penalty(x[:engine.obj.size])[1][:2]==0)
    steps=[]
    for step_m in (10.,5.):
        derivatives=[];prior=[];finite=[];visibility_changes=[]
        for axis in range(2):
            shift=np.eye(2)[axis]*step_m/1000
            high=fit(shift,f'plus-{step_m:g}m-axis{axis}',x)
            low=fit(-shift,f'minus-{step_m:g}m-axis{axis}',x)
            ph,vh=prediction(engine,high['vector']);pl,vl=prediction(engine,low['vector'])
            derivatives.append((ph-pl)/(2*step_m/1000))
            prior.append((high['prior_nll']-low['prior_nll'])/(2*step_m)*100)
            finite.append((high['objective']-low['objective'])/(2*step_m)*100)
            visibility_changes.append(int(np.sum(vh!=vl)))
        terms=contribution_terms(weights,np.stack(derivatives,axis=-1))
        satellite=terms.sum(axis=0)
        total=satellite.sum(axis=0)+np.array(prior)
        np.testing.assert_allclose(total,direct_total,atol=.005,rtol=.01)
        np.testing.assert_allclose(finite,direct_total,atol=.005,rtol=.01)
        assert not any(visibility_changes),'Visibility discontinuity requires separate attribution'
        receiver=np.stack([terms[engine.data.receiver==rx].sum(axis=0) for rx in (0,1)])
        steps.append(dict(step_m=step_m,satellite_gradients_per_100m=satellite,
            receiver_satellite_gradients_per_100m=receiver,prior_gradient_per_100m=prior,
            total_gradient_per_100m=total,profile_score_finite_difference_per_100m=finite,
            visibility_changes=visibility_changes))
    chosen=steps[-1];g=np.array(chosen['satellite_gradients_per_100m'])
    ascent=direct_total/np.linalg.norm(direct_total)
    rows=[]
    for i,n in enumerate(engine.data.numbers):
        rows.append(dict(scan=scan,arm=arm,satellite=int(n),
            east_gradient_per_100m=g[i,0],north_gradient_per_100m=g[i,1],
            gradient_magnitude_per_100m=float(np.linalg.norm(g[i])),
            pressure_along_total_downhill=float(g[i]@ascent),
            direct_east_per_100m=float(direct_terms[:,i,0].sum()),
            direct_north_per_100m=float(direct_terms[:,i,1].sum()),
            soft_association_support=float(support[:,i].sum()),
            rx0_east_per_100m=chosen['receiver_satellite_gradients_per_100m'][0,i,0],
            rx0_north_per_100m=chosen['receiver_satellite_gradients_per_100m'][0,i,1],
            rx1_east_per_100m=chosen['receiver_satellite_gradients_per_100m'][1,i,0],
            rx1_north_per_100m=chosen['receiver_satellite_gradients_per_100m'][1,i,1]))
    result=dict(scan=scan,arm=arm,capture_roof_lat_lon=evidence['operator_roof_lat_lon'],
        observation_count=len(engine.data.times),candidate_count=len(engine.data.numbers),
        roof_fit=roof,roof_restarts=restarts,steps=steps,rows=rows,
        direct_total_gradient_per_100m=direct_total,
        maximum_satellite_step_difference=float(np.max(abs(np.array(steps[0]['satellite_gradients_per_100m'])-g))),
        sources={str(p):digest(p) for p in [HERE/'orientation-evidence.json',Path(__file__),
                  BULK/'profile_top_2km.py',BULK/f'position-top-2km/{scan}-profile-input.npz',
                  BULK/f'position-top-2km/{scan}-profile-input.json']})
    save(OUT/f'{scan}-{arm}.json',result)
    print('ATTRIBUTION',scan,arm,'gradient/100m',direct_total,'top',sorted(rows,key=lambda r:-r['pressure_along_total_downhill'])[:3],flush=True)
    return result


def render(results,arm):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    cases=[r for r in results if r['arm']==arm]
    fig,axes=plt.subplots(1,2,figsize=(15,13))
    for ax,r in zip(axes,cases):
        rows=sorted(r['rows'],key=lambda x:-x['gradient_magnitude_per_100m'])
        data=np.array([[x['east_gradient_per_100m'],x['north_gradient_per_100m']] for x in rows])
        prior=np.array(r['steps'][-1]['prior_gradient_per_100m']);total=np.array(r['direct_total_gradient_per_100m'])
        data=np.vstack((total,prior,data));labels=['TOTAL','Timing prior']+[str(x['satellite']) for x in rows]
        y=np.arange(len(labels))
        ax.barh(y-.17,data[:,0],height=.31,color='#0072b2',label='East component')
        ax.barh(y+.17,data[:,1],height=.31,color='#d55e00',label='North component')
        ax.set_yticks(y,labels,fontsize=9);ax.invert_yaxis();ax.axvline(0,color='black',lw=.8)
        ax.axhline(1.5,color='.6',lw=.7);ax.grid(axis='x',alpha=.15)
        ax.set_xlabel('Score gradient per 100 m (lower score is better)')
        ax.set_title(f"Scan {r['scan']} · {r['candidate_count']} satellites\nTotal: E {total[0]:+.3f}, N {total[1]:+.3f}")
    fig.suptitle(f'DS13 · position-gradient contribution by satellite · {arm}',fontsize=17,y=.985)
    fig.legend(handles=[Line2D([],[],color='#0072b2',lw=7,label='East component'),Line2D([],[],color='#d55e00',lw=7,label='North component')],loc='upper center',bbox_to_anchor=(.5,.954),ncol=2)
    fig.text(.5,.027,'Evaluated at capture-bound operator roof; A and B independent; nuisance parameters refitted at each probe.\nPositive east/north gradient favors moving west/south; negative favors east/north. Satellite rows + timing prior = TOTAL.\nChain-rule attribution along the profiled nuisance path; not leave-one-satellite-out influence or identity confidence.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.087,1,.927));fig.savefig(OUT/f'gradient-by-satellite-{arm}.png',dpi=160);plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('fork')) as pool:
        results=list(pool.map(case,[(s,a) for s in 'AB' for a in ('fitted-c','zero-c')]))
    with (OUT/'contributions.csv').open('w',newline='') as stream:
        rows=[row for r in results for row in r['rows']]
        w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    save(OUT/'receipt.json',dict(results=results,scope=__doc__,
        score='Per-scan finite-set negative log likelihood plus zero-centered Gaussian timing priors; no greedy count objective.',
        attribution='dNLL/dprediction times total prediction derivative along reoptimized nuisance path. Timing prior derivative separate. Direct envelope gradient also retained.',
        limitations=['Saved receiver baseline remains fixed; extra linear RX terms, RF coefficient and timing refitted.',
            'All top-response windows including greedy-unassigned retained. Soft likelihood ownership is not frozen hard membership.',
            'Conditional in-sample local derivative; not proof of wrong satellite identity or deletion benefit.']))
    for arm in ('fitted-c','zero-c'):render(results,arm)


if __name__=='__main__':main()
