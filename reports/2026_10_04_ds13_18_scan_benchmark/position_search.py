"""Independent 2 km conditional position profiles with matched RF arms.

The fitted-c association result freezes observation/subset membership for both
arms. The satellite bank is the union of both association arms on those windows.
Only the cross-fitted nonlinear RX spline is frozen; a single RX offset/line,
RF coefficient and satellite timing are refitted at every candidate position.
This is a new same-model cohort comparison, not a blind localization result.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from calibration import serial
from cohort import ROOF, digest
from numeric_data import load, view


def subset_rows(assignments, margins, ranking, fraction):
    if ranking not in ('rms','support','glrt') or not 0<fraction<=1:
        raise ValueError('invalid subset configuration')
    if not assignments:
        raise ValueError('no assigned observations')
    if ranking=='glrt':
        ranked=sorted(assignments,key=lambda a:(-margins[a['row_index']],a['row_index']))
        return sorted(a['row_index'] for a in ranked[:int(np.ceil(len(ranked)*fraction))])
    numbers=sorted({a['catalog_number'] for a in assignments})
    members={n:[a for a in assignments if a['catalog_number']==n] for n in numbers}
    def key(n):
        rows=members[n]
        metric=np.sqrt(np.mean([a['residual_hz']**2 for a in rows])) if ranking=='rms' else -len(rows)
        return metric,n
    retained=set(sorted(numbers,key=key)[:int(np.ceil(len(numbers)*fraction))])
    return sorted(a['row_index'] for a in assignments if a['catalog_number'] in retained)


def calibration_warning(fold,record,permit):
    if record['arms']['fitted-c']['success']:return None
    if not permit:raise ValueError('profile initializer is not converged')
    return dict(fold=fold,nuisance_gradient=record['arms']['fitted-c'].get('nuisance_gradient'),
                warning='Nonconverged saved calibration. Position results are conditional diagnostics, not validated localization.')


def prepare(directory, method, ranking, fraction, selection_name='selection-p10-g600-t1.json',*,permit_calibration_warning=False):
    full=load(directory,top_only=False)
    if Path(selection_name).name!=selection_name:
        raise ValueError('selection must name a file within this scan')
    source=directory/selection_name
    selection=json.loads(source.read_text())
    results={a:selection['arms'][a][method]['final'] for a in ('fitted-c','zero-c')}
    rows=np.asarray(subset_rows(results['fitted-c']['assignments'],full.margin,ranking,fraction),int)
    data=view(full,rows)
    groups=set(data.group)
    numbers=sorted({a['catalog_number'] for result in results.values() for a in result['assignments']
                    if full.group[a['row_index']] in groups})
    ids=np.array([int(np.flatnonzero(full.numbers==n)[0]) for n in numbers])
    data.numbers=np.asarray(numbers)
    data.position=full.position[ids]
    data.velocity=full.velocity[ids]
    selected={a:{r['catalog_number']:r for r in result['selected']} for a,result in results.items()}
    sources={**full.sources,str(source):digest(source.read_bytes())}
    lookup={int(r):int(g) for r,g in zip(full.original_rows,full.group)}
    corrections=np.zeros(len(rows))
    covered=np.zeros(len(rows),int)
    coefficients, common, lines=[],[],[]
    warnings=[]
    for fold in range(5):
        path=directory/'calibration-v2'/f'fold-{fold}.json'
        record=json.loads(path.read_text())
        warning=calibration_warning(fold,record,permit_calibration_warning)
        if warning:warnings.append(warning)
        sources[str(path)]=digest(path.read_bytes())
        test_groups={lookup[r] for r in record['test_original_rows']}
        mask=np.isin(data.group,list(test_groups))
        covered[mask]+=1
        for rx in (0,1):
            use=mask & (data.receiver==rx)
            corrections[use]=np.interp(data.times[use],record['spline_nodes_s'],record['correction_knots_hz'][rx])
        fitted=record['arms']['fitted-c']
        params=np.asarray(fitted['parameters'])
        common.append(float(np.mean(params[6+np.asarray(record['satellite_indices'],int)])))
        lines.append(params[2:6])
        coefficients.append(fitted['coefficient'])
    if not np.all(covered==1):
        raise ValueError('profile rows do not partition into calibration folds')
    data.measured-=corrections
    initial=np.zeros(6+len(numbers))
    initial[:2]=full.initial[:2]
    initial[2:6]=np.median(lines,axis=0)
    for j,n in enumerate(numbers):
        mode=selected['fitted-c'].get(n,selected['zero-c'].get(n))
        initial[6+j]=np.clip(np.median(common)+mode['offset_s'],-20,20)
    data.initial=initial
    metadata=dict(sources=sources,method=method,ranking=ranking,fraction=fraction,
                     fixed_observation_original_rows=data.original_rows.tolist(),numbers=numbers,
                     seed_coefficient=float(np.median(coefficients)),scope=__doc__,
                     known_roof_lat_lon=ROOF,retained_windows=len(rows),
                     ranking_scope='RMS at known roof is an oracle diagnostic; all memberships and rankings are frozen before position search.')
    if warnings:metadata['calibration_warnings']=warnings
    return data,metadata


def point_design(seed=20261004):
    rng=np.random.default_rng(seed)
    points=[(0.,0.)]
    for h in (.05,.1):
        points.extend(((h,0.),(-h,0.),(0.,h),(0.,-h)))
    for lo,hi in ((0.,1.),(1.,2.)):
        for sector in range(8):
            angle=rng.uniform(sector*np.pi/4,(sector+1)*np.pi/4)
            radius=np.sqrt(rng.uniform(lo**2,hi**2))
            points.append((radius*np.sin(angle),radius*np.cos(angle)))
    points.extend((2*np.sin(a),2*np.cos(a)) for a in np.arange(8)*np.pi/4)
    return np.asarray(points)


class Engine:
    def __init__(self,data,meta,arm,folder,legacy_folder=None):
        from rf_calibration_diagnostic import CalibrationObjective
        self.data,self.meta,self.arm,self.folder=data,meta,arm,folder
        self.objective=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,8.)
        self.objective.base.minimum_shift_s=max(self.objective.base.minimum_shift_s,-20.)
        self.objective.base.maximum_shift_s=min(self.objective.base.maximum_shift_s,20.)
        if arm=='zero-c':
            self.objective.bounds[-1]=(0.,0.)
        self.initial=self.objective.initial.copy()
        self.initial[-1]=meta['seed_coefficient'] if arm=='fitted-c' else 0.
        self.cache={}
        folder.mkdir(exist_ok=True,parents=True)
        self.legacy={}
        legacy_sources={}
        if legacy_folder is not None and legacy_folder.exists():
            for path in sorted(legacy_folder.glob('fit-*.json')):
                record=json.loads(path.read_text())
                if record['signature']['inputs']!=meta or record['signature']['arm']!=arm:
                    raise ValueError('legacy profile has different observations or model inputs')
                legacy_sources[str(path)]=digest(path.read_bytes())
                self.legacy[tuple(record['point_km'])]=record
        self.signature=dict(inputs=meta,arm=arm,implementation=digest(Path(__file__).read_bytes()),
                            maximum_eight_second_attempts=8,legacy_sources=legacy_sources)
        self.saved_count=0
        for path in sorted(folder.glob('fit-*.json')):
            record=json.loads(path.read_text())
            if record['signature']!=self.signature:
                # Driver/report changes need not discard expensive fits. Accept
                # older-driver points only after exact input binding and a fresh
                # numerical objective/gradient audit. Preserve their provenance.
                old=record['signature']
                if old['inputs']!=meta or old['arm']!=arm:
                    raise ValueError('profile cache input mismatch')
                from truth_start_diagnostic import projected_gradient
                vector=np.asarray(record['vector'])
                self.objective.base.deadline=float('inf')
                value,gradient=self.objective.evaluate(vector)
                bounds=list(self.objective.bounds)
                bounds[:2]=[(v,v) for v in vector[:2]]
                pg,_=projected_gradient(vector,gradient,bounds,self.objective.scale)
                if abs(value-record['objective'])>1e-7 or abs(max(abs(pg))-record['nuisance_gradient'])>1e-6:
                    raise ValueError('older-driver cache failed numerical revalidation')
            self.cache[tuple(record['point_km'])]=record
            self.saved_count+=1

    def coordinate(self,point):
        from position_profile_grid import geodesic_position
        e,n=np.asarray(point)*1000
        return geodesic_position(*ROOF,np.degrees(np.arctan2(e,n)),np.hypot(e,n))

    def fit(self,point):
        from truth_start_diagnostic import optimize
        point=np.asarray(point,float)
        key=tuple(np.round(point,8))
        if key in self.cache and (self.cache[key]['success'] or len(self.cache[key]['attempts'])>=8):
            return self.cache[key]
        current=self.initial.copy()
        prior=self.cache.get(key,self.legacy.get(key))
        valid=[r for r in self.cache.values() if r['success']]
        if valid:
            nearest=min(valid,key=lambda r:np.linalg.norm(point-np.asarray(r['point_km'])))
            current=np.asarray(nearest['vector']).copy()
        current[:2]=self.coordinate(point)
        bounds=list(self.objective.bounds)
        bounds[:2]=[(v,v) for v in current[:2]]
        attempts=[]
        if prior is not None:
            current=np.asarray(prior['vector']).copy()
            self.objective.base.deadline=float('inf')
            check_value,_=self.objective.evaluate(current)
            if abs(check_value-prior['objective'])>1e-7:
                raise ValueError('legacy objective reconstruction failed; cannot reuse fit')
            attempts=list(prior['attempts'])
            result=dict(vector=current,success=prior['success'],projected_gradient_inf_norm=prior['nuisance_gradient'])
        for _ in range(0 if prior is not None and prior['success'] else max(0,8-len(attempts))):
            result=optimize(self.objective,current,bounds,budget_s=8.)
            current=np.asarray(result['vector'])
            attempts.append({k:result[k] for k in ('objective','success','status','projected_gradient_inf_norm','elapsed_s')})
            if result['success']:
                break
        self.objective.base.deadline=float('inf')
        value,gradient=self.objective.evaluate(current)
        step=.001
        geographic_jacobian=np.column_stack([(self.coordinate(point+np.eye(2)[i]*step)-self.coordinate(point-np.eye(2)[i]*step))/(2*step) for i in range(2)])
        prior=float(self.objective.base.penalty(current[:self.objective.size])[0])
        record=dict(signature=self.signature,point_km=list(key),objective=float(value),data_nll=float(value-prior),
                    prior_nll=prior,success=bool(result['success']),nuisance_gradient=float(result['projected_gradient_inf_norm']),
                    position_gradient_per_km=(geographic_jacobian.T@gradient[:2]).tolist(),
                    vector=current.tolist(),parameters=self.objective.base.state(current[:self.objective.size])['parameters'].tolist(),
                    coefficient=float(current[-1]),attempts=attempts)
        path=self.folder/f'fit-{self.saved_count:05d}.json'
        with path.open('x') as stream:
            json.dump(record,stream,default=serial,allow_nan=False)
        self.cache[key]=record
        self.saved_count+=1
        print('PROFILE',self.arm,np.round(point*1000,1),'score',round(value,4),'ok',record['success'],flush=True)
        return record


def run(directory,method='alternatives',ranking='support',fraction=1.,smoke=False):
    from scipy.optimize import minimize
    data,meta=prepare(directory,method,ranking,fraction)
    name=f'{method}-{ranking}-{int(round(fraction*100))}'
    root=directory/'position-v2'/name
    results={}
    for arm in ('fitted-c','zero-c'):
        engine=Engine(data,meta,arm,root/arm,legacy_folder=directory/'position'/name/arm)
        design=point_design()
        for point in design[:2] if smoke else design:
            result=engine.fit(point)
            if not result['success']:
                print('PROFILE WARNING',arm,point,'nonconverged; retaining failed site and continuing matched grid',flush=True)
        if smoke:
            continue
        ranked=sorted([r for r in engine.cache.values() if r['success']],key=lambda r:r['objective'])
        if not ranked:
            results[arm]=dict(status='no_converged_profile',failed_sites=len(engine.cache))
            continue
        starts=[np.zeros(2)]
        for record in ranked:
            point=np.asarray(record['point_km'])
            if all(np.linalg.norm(point-other)>.4 for other in starts):
                starts.append(point)
            if len(starts)==3:
                break
        def objective(point):
            r=engine.fit(point)
            if not r['success']:
                raise RuntimeError('nonconverged nuisance profile inside position search')
            return r['objective'],np.asarray(r['position_gradient_per_km'])
        trials=[]
        for start in starts:
            try:
                fit=minimize(objective,start,jac=True,method='SLSQP',bounds=[(-2,2)]*2,
                             constraints=[dict(type='ineq',fun=lambda x:4-np.dot(x,x),jac=lambda x:-2*x)],
                             options=dict(maxiter=25,ftol=1e-7))
                trials.append(dict(start_km=start.tolist(),point_km=fit.x.tolist(),objective=float(fit.fun),
                                   success=bool(fit.success),message=str(fit.message)))
            except RuntimeError as error:
                trials.append(dict(start_km=start.tolist(),success=False,message=str(error)))
        feasible=[r for r in engine.cache.values() if r['success'] and np.linalg.norm(r['point_km'])<=2.000001]
        best=min(feasible,key=lambda r:r['objective'])
        roof=engine.fit([0,0])
        fd={str(h):[(engine.fit(np.eye(2)[i]*h)['objective']-engine.fit(-np.eye(2)[i]*h)['objective'])/(2*h) for i in range(2)] for h in (.05,.1)}
        minima=[t for t in trials if t['success']]
        ambiguous=any(np.linalg.norm(np.asarray(t['point_km'])-best['point_km'])>.1 and abs(t['objective']-best['objective'])<1. for t in minima)
        results[arm]=dict(best=best,trials=trials,roof=roof,finite_difference_gradient_per_km=fd,
                          failed_sites=sum(not r['success'] for r in engine.cache.values()),
                          successful_local_searches=len(minima),
                          radius_m=float(1000*np.linalg.norm(best['point_km'])),boundary=bool(np.linalg.norm(best['point_km'])>1.999),
                          ambiguous=ambiguous,samples=len(engine.cache),claim='Best found within 2 km; not a global optimum certificate.')
    if not smoke:
        with (root/'summary.json').open('x') as stream:
            json.dump(dict(meta=meta,arms=results),stream,default=serial,allow_nan=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--method',choices=('greedy','replacement','alternatives'),default='alternatives')
    p.add_argument('--ranking',choices=('rms','support','glrt'),default='support')
    p.add_argument('--fraction',type=float,default=1.)
    p.add_argument('--smoke',action='store_true')
    a=p.parse_args()
    run(a.directory,a.method,a.ranking,a.fraction,a.smoke)
