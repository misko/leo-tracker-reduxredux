"""Frozen, paired N01--N64 replay. Reference coordinates are never loaded here."""
import concurrent.futures as futures
from dataclasses import asdict,replace
import fcntl
import functools
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time
import traceback
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
HERE=Path(__file__).resolve().parent
GRID=HERE.parent/'2026_10_07_single_method_grid'
SLOPE=HERE.parent/'2026_10_07_slope_priors'
sys.path.extend([str(GRID),str(SLOPE)])
import numpy as np
from scipy.optimize import nnls
import data
from native_score import NativeObjective,predict_orbits
from bounded_fit import fit_position,PositionFit
import leo.analysis.regional_position_bootstrap as boot
from leo.analysis.regional_position_score import PositionObjective
from leo.analysis.regional_position_calibration import receiver_correction,RegionalCalibration
from leo.analysis.regional_position_association import associate_calibration
import leo.analysis.regional_position_association as association_module
from leo.analysis.regional_position_search import distinct_basins,SpatialSearch
import edge_grid
boot.predict_orbits=predict_orbits
association_module.predict_orbits=predict_orbits

PHASES={
 'before':dict(sigma=.15,width=None,levels=[100.,50.,25.,12.5],edge='legacy-zero'),
 'after':dict(sigma=1.,width=60.,levels=[40.,20.,10.,5.],edge='nearest')}
CONTEXT={}

def encode(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError(type(value).__name__)
def write(path,value):
    path=Path(path);temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,indent=2,default=encode,allow_nan=False)+'\n');temp.replace(path)
def bootstrap(value):
    return boot.PositionBootstrap(tuple(value['satellite_indices']),np.asarray(value['vector']),
                                  tuple(boot.BootstrapMatch(**m) for m in value['matches']))
def context(label,phase):
    d,obs,bank,prior,score=CONTEXT[label]
    return d,obs,bank,prior,replace(score,relative_sigma_s=PHASES[phase]['sigma'])
def point_path(label,phase,xy):return HERE/'results'/label/phase/'points'/f'{xy[0]:g}_{xy[1]:g}.json'
def warm():return os.getpid()

def score_point(task):
    label,phase,xy=task;path=point_path(label,phase,xy)
    if path.exists():return dict(json.loads(path.read_text()),cache_hit=True)
    d,obs,bank,prior,score=context(label,phase)
    start=time.monotonic();out=dict(point=xy,score=1e100,status='failed',cache_hit=False)
    try:
        shared=HERE/'results'/label/'bootstrap'/f'{xy[0]:g}_{xy[1]:g}.json'
        with shared.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if shared.exists():seed=bootstrap(json.loads(shared.read_text()))
            else:
                seed=boot.bootstrap_position(obs,bank,prior,xy,d['bootstrap_tracks'],maximum_seconds=5.)
                write(shared,asdict(seed))
        out.update(bootstrap=asdict(seed),bootstrap_seconds=time.monotonic()-start)
        obj=NativeObjective(obs,bank.select(list(seed.satellite_indices)),prior,score)
        fit=fit_position(obj,seed.vector,fixed_position=True,rf_arm='fitted-c',maximum_seconds=5.,
                         maximum_iterations=200,slope_half_width_hz_s=PHASES[phase]['width'])
        out.update(status='complete',score=fit.objective,fit=asdict(fit))
    except Exception as error:out.update(error=str(error),traceback=traceback.format_exc())
    out['elapsed_s']=time.monotonic()-start;write(path,out)
    return out

def audit(obj,v,gradient,arm,center,radius,width):
    v=np.asarray(v);n=len(v);scale=np.r_[1.,1.,200.,2.,200.,2.,200.,np.ones(n-7)]
    free=np.arange(n) if arm=='fitted-c' else np.delete(np.arange(n),6)
    lo,hi=np.full(n,-np.inf),np.full(n,np.inf)
    lo[:2],hi[:2]=-obj.prior.radius_km,obj.prior.radius_km
    if width is not None:lo[[3,5]],hi[[3,5]]=-width,width
    lo[6:8],hi[6:8]=[-5000.,-10.],[5000.,10.]
    slacks=list((v-lo)[free])+list((hi-v)[free]);normals=[];active=[]
    for i in free:
        for slack,sign in [(v[i]-lo[i],1),(hi[i]-v[i],-1)]:
            if slack/scale[i]<=1e-7:
                normal=np.zeros(n);normal[i]=sign/scale[i];normals.append(normal)
                if i in (3,5):active.append(int(i))
    boundary=False
    for origin,r in [(np.zeros(2),obj.prior.radius_km),(np.asarray(center),radius)]:
        delta=v[:2]-origin;slack=r*r-delta@delta;slacks.append(slack)
        boundary|=bool(np.linalg.norm(delta)>=r-1e-4)
        if slack<=1e-6:
            normal=np.zeros(n);normal[:2]=-2*delta;normals.append(normal)
    matrix=np.zeros((len(obj.bank.numbers),n));matrix[:,7]=1.;matrix[:,8:]=obj.basis
    shifts=matrix@v
    lower=max(-20.,obj.bank.nodes_s[0]-obj.observations.times_s.min())
    upper=min(20.,obj.bank.nodes_s[-1]-obj.observations.times_s.max())
    slacks.extend(shifts-lower);slacks.extend(upper-shifts)
    normals.extend(matrix[shifts-lower<=1e-6]);normals.extend(-matrix[upper-shifts<=1e-6])
    residual=(gradient*scale)[free]
    if normals:
        a=(np.asarray(normals)*scale)[:,free].T
        beta,_=nnls(a,residual,maxiter=100*a.shape[1]);residual-=a@beta
    stationarity=float(abs(residual).max());feasible=bool(min(slacks)>=-1e-6 and (arm!='zero-c' or v[6]==0))
    return dict(feasible=feasible,converged=feasible and stationarity<=.001,
                stationarity=stationarity,boundary=boundary,slope_active_bounds=active)

def refine_region(task):
    label,phase,xy,radius=task;folder=HERE/'results'/label/phase
    path=folder/'regions'/f'{xy[0]:g}_{xy[1]:g}_{radius:g}.json'
    if path.exists():
        cached=json.loads(path.read_text())
        if cached['status']!='running':return cached
    d,obs,bank,prior,score=context(label,phase);width=PHASES[phase]['width']
    fit=functools.partial(fit_position,maximum_seconds=20.,maximum_iterations=600,slope_half_width_hz_s=width)
    started=time.monotonic();out=dict(point=xy,local_radius_km=radius,runs=[],candidates=[],status='running')
    try:
        point=json.loads(point_path(label,phase,xy).read_text());seed=bootstrap(point['bootstrap'])
        subset=bank.select(list(seed.satellite_indices));obj=NativeObjective(obs,subset,prior,score)
        pre=PositionFit(**{**point['fit'],'vector':np.asarray(point['fit']['vector'])})
        if not pre.converged:pre=fit(obj,pre.vector,fixed_position=True)
        if not pre.converged:raise ValueError('V16 calibration prefit did not converge')
        correction=receiver_correction(obs,obj.evaluate(pre.vector)[2])
        corrected=NativeObjective(obs,subset,prior,score,receiver_baseline_hz=correction.values_hz)
        post=fit(corrected,pre.vector,fixed_position=True)
        if not post.converged:raise ValueError('V16 calibration postfit did not converge')
        baseline=correction.values_hz+corrected.design[:,:4]@post.vector[2:6]
        calibrated=RegionalCalibration(seed.satellite_indices,pre,post,correction,baseline)
        associated=associate_calibration(obs,bank,prior,calibrated,maximum_seconds=60.)
        final_bank=bank.select(list(associated.selected_indices))
        objective=NativeObjective(obs,final_bank,prior,score,receiver_baseline_hz=baseline)
        oracle=PositionObjective(obs,final_bank,prior,score,receiver_baseline_hz=baseline)
        knots=correction.knots_hz
        penalty=float(.5*(np.sum(knots**2)/50**2+np.sum(np.diff(knots,n=2,axis=1)**2)/25**2))
        out.update(calibration=asdict(calibrated),association=asdict(associated),
                   satellite_numbers=final_bank.numbers,calibration_penalty=penalty)
        def record(v,arm,origin,**extra):
            v=np.asarray(v);value,gradient,terms=oracle.evaluate(v)
            fast,fg,_=objective.evaluate(v)
            np.testing.assert_allclose(value,fast,atol=1e-6,rtol=0)
            np.testing.assert_allclose(gradient,fg,atol=1e-6,rtol=1e-7)
            mass=float(terms.responsibilities.sum())
            row=dict(arm=arm,origin=origin,vector=v.tolist(),objective=value,selection_score=value+penalty,
                data_nll=float(terms.nll),timing_penalty=value-terms.nll,
                frequency_rms_hz=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)) if mass>1e-12 else None,
                signal_windows=mass,additional_slopes_hz_s=v[[3,5]].tolist(),
                calibration_slopes_hz_s=post.vector[[3,5]].tolist(),
                combined_affine_slopes_hz_s=(v[[3,5]]+post.vector[[3,5]]).tolist(),
                original_oracle_objective_delta=value-fast,
                **audit(oracle,v,gradient,arm,xy,radius,width),**extra)
            out['candidates'].append(row);return row
        def fit_one(v,arm,name,parent=None):
            v=np.asarray(v).copy()
            if width is not None:v[[3,5]]=np.clip(v[[3,5]],-width,width)
            if arm=='zero-c':v[6]=0.
            for center,r in [(np.zeros(2),prior.radius_km),(np.asarray(xy),radius)]:
                delta=v[:2]-center;dist=np.linalg.norm(delta)
                if dist>r:
                    assert dist-r<1e-6
                    v[:2]=center+delta*((r-1e-8)/dist)
            record(v,arm,'initial:'+name,parent_origin=parent)
            result=fit(objective,v,rf_arm=arm,local_center=np.asarray(xy),local_radius_km=radius)
            row=record(result.vector,arm,'fit:'+name,elapsed_s=result.elapsed_s,stop_reason=result.stop_reason,
                       parent_origin=parent,evaluations=result.evaluations)
            np.testing.assert_allclose(row['objective'],result.objective,atol=1e-6,rtol=0)
            out['runs'].append(row);write(path,out)
        for arm in ('zero-c','fitted-c'):
            for name in ('association','zero-timing'):
                v=associated.initial_vector.copy()
                if name=='zero-timing':v[7:]=0.
                fit_one(v,arm,name)
            parent=min((r for r in out['candidates'] if r['arm']==arm and r['feasible']),key=lambda r:r['selection_score'])
            fit_one(parent['vector'],arm,'own-continuation',parent['origin'])
        out['status']='complete'
    except Exception as error:out.update(status='failed',error=str(error),traceback=traceback.format_exc())
    out['elapsed_s']=time.monotonic()-started;write(path,out)
    print('REGION',label,phase,xy,out['status'],out.get('error',''),flush=True)
    return out

def run_case(label,phase,pool):
    folder=HERE/'results'/label/phase;path=folder/'result.json'
    if path.exists():return json.loads(path.read_text())
    begun=time.monotonic();cfg=PHASES[phase];search_path=folder/'search.json'
    if search_path.exists():searched=json.loads(search_path.read_text())
    else:
        rows=[]
        def batch(points):
            tasks=[pool.submit(score_point,(label,phase,xy)) for xy in points]
            values=[f.result() for f in tasks]
            rows.extend({key:r.get(key) for key in ('point','score','status','error','elapsed_s','cache_hit')}|
                        dict(converged=r.get('fit',{}).get('converged'),stop_reason=r.get('fit',{}).get('stop_reason')) for r in values)
            write(folder/'progress.json',dict(points=len(rows),elapsed_s=time.monotonic()-begun,rows=rows))
            return [r['score'] for r in values]
        search,meta=edge_grid.search(batch,levels=cfg['levels'],budget=400,edge_policy=cfg['edge'])
        supported=SpatialSearch(tuple(p for p in search.evaluations if p.score<1e100),search.deferred_cells,search.stop_reason)
        basins=distinct_basins(supported,count=3,minimum_separation_km=12.5)
        searched=dict(search=asdict(search),basins=[asdict(b) for b in basins],edge=meta,rows=rows,elapsed_s=time.monotonic()-begun)
        write(search_path,searched)
    jobs=[pool.submit(refine_region,(label,phase,(b['east_km'],b['north_km']),max(25.,b['spacing_km']/np.sqrt(2)))) for b in searched['basins']]
    regions=[f.result() for f in jobs]
    candidates=[dict(r,point=g['point'],local_radius_km=g['local_radius_km']) for g in regions for r in g['candidates']]
    selections={}
    for arm in ('zero-c','fitted-c'):
        feasible=[r for r in candidates if r['arm']==arm and r['feasible']]
        converged=[r for r in feasible if r['converged']]
        key=lambda r:(r['selection_score'],r['point'],r['origin'])
        selections[arm]=dict(result=min(converged,key=key,default=None),best_feasible=min(feasible,key=key,default=None),
                              feasible_count=len(feasible),converged_count=len(converged))
    result=dict(label=label,phase=phase,config=cfg,selections=selections,basins=searched['basins'],
                region_status=[dict(point=r['point'],status=r['status'],error=r.get('error')) for r in regions],
                elapsed_s=time.monotonic()-begun)
    write(path,result);print('CASE',label,phase,'complete',[r['status'] for r in result['region_status']],flush=True)
    return result

def main():
    labels=[f'N{i:02d}' for i in range(1,65)]
    files=[Path(__file__),HERE/'native_score.py',HERE/'fast_score.py',HERE/'orbits.cpp',HERE/'orbits.so',
           HERE/'data.py',HERE/'cohort.json',HERE/'association_replay_migration.json',GRID/'grid.py',GRID/'edge_grid.py',SLOPE/'bounded_fit.py']
    import leo
    package=Path(leo.__file__).parent
    files.extend(package/p for p in ('analysis/regional_position_score.py','analysis/regional_position_bootstrap.py',
        'analysis/regional_position_calibration.py','analysis/regional_position_association.py',
        'analysis/regional_position_search.py','analysis/t1_at.py','analysis/t1_at_discovery.py','contracts/regional_position.py'))
    protocol=dict(labels=labels,method='V16',phases=PHASES,points_per_phase=400,basins=3,basin_separation_km=12.5,
        coarse_seconds=5.,coarse_iterations=200,bootstrap_seconds=5.,final_seconds=20.,final_iterations=600,
        calibration='V16 pre/post fitted-c; gauged piecewise receiver correction',
        slope_scope='Hard bound on each fitted affine slope, not on frozen baseline plus final slope or piecewise total drift.',
        final_arms=['zero-c','fitted-c'],starts=['association','zero-timing','own-continuation'],
        ablation_scope='final-stage c only, shared discovery/calibration/association within each phase',
        baseline='Fresh controlled before, not previously published roof-seeded results.',
        reference_usage='Never read by this process; evaluate only after score selection.',workers=20,parallel_cases=12,
        sources={str(p):data.digest(p) for p in files})
    path=HERE/'protocol.json'
    if path.exists():assert json.loads(path.read_text())==protocol,'protocol changed; do not mix caches'
    else:write(path,protocol)
    start=time.monotonic()
    for label in labels:
        CONTEXT[label]=data.load(label)
        (HERE/'results'/label/'bootstrap').mkdir(parents=True,exist_ok=True)
        for phase in PHASES:
            for sub in ('points','regions'):(HERE/'results'/label/phase/sub).mkdir(parents=True,exist_ok=True)
    print('INPUTS LOADED',len(CONTEXT),'seconds',time.monotonic()-start,flush=True)
    with futures.ProcessPoolExecutor(max_workers=20,mp_context=multiprocessing.get_context('fork')) as pool:
        [f.result() for f in [pool.submit(warm) for _ in range(20)]]
        with futures.ThreadPoolExecutor(max_workers=12) as threads:
            pending={threads.submit(run_case,label,phase,pool):(label,phase) for label in labels for phase in PHASES}
            results=[]
            for future in futures.as_completed(pending):
                try:results.append(future.result())
                except Exception as error:
                    label,phase=pending[future]
                    results.append(dict(label=label,phase=phase,status='failed',error=str(error),traceback=traceback.format_exc()))
                write(HERE/'run_progress.json',dict(completed=len(results),requested=128,elapsed_s=time.monotonic()-start,
                                                  cases=[dict(label=r['label'],phase=r['phase'],status=r.get('status','complete')) for r in results]))
    write(HERE/'results.json',dict(results=results,elapsed_s=time.monotonic()-start))
    print('COMPLETE',len(results),'seconds',time.monotonic()-start,flush=True)
if __name__=='__main__':main()
