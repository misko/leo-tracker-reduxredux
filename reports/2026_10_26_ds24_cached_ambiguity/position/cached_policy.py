"""Exact cached implementation of the previous frozen ambiguity position law."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import lru_cache
import importlib.util
from pathlib import Path
import signal
import time
import traceback
import numpy as np
from scipy.special import logsumexp
import geometry_cache as gc

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
PRIOR=Path('/srv/bulk/leo/research/ds24-ambiguity-policy-r01/position')
spec=importlib.util.spec_from_file_location('original_ambiguity_policy',PRIOR/'policy.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
r,sr=base.r,base.sr
OriginalTarget=base.Target
CACHE=gc.StateCache(HERE/'cache')
KEYS={}
REGIONAL=[(0.,0.),(-10.,-10.),(-10.,10.),(10.,-10.),(10.,10.)]
TOL=dict(frequency_hz=2e-8,shape_columns_hz=2e-8,elevation_deg=2e-11,objective=1e-6,gradient_per_km=1e-5)


def write(name,value):r.write_new(HERE/name,value)


def cached_physical(candidate,comp,nodes,logs,key):
    values=[];minimum=np.inf
    for start in range(0,len(nodes),512):
        geo=CACHE.geometry(key,comp['x'],start,min(start+512,len(nodes)))
        minimum=min(minimum,float(geo['elevation_deg'].min()))
        raw=comp['raw'][None]-comp['q'][None]*geo['frequency_hz']
        shape=comp['q'][None,:,None]*geo['shape_columns_hz']
        costs=sr.sm.positive_costs(raw,comp['covariance'],shape,comp['shifts'])
        density=logsumexp(-costs/2,axis=1)-np.log(9)
        values.append(np.where(geo['elevation_deg'].min(axis=1)>=0,density,-np.inf))
    logz=float(logsumexp(np.concatenate(values)+logs))
    return dict(objective=-2*logz,logZ=logz,node_min_elevation_deg=minimum,order=len(nodes),
        original_prior_normalization=True,visible_mass_renormalized=False)


class CachedTarget(OriginalTarget):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.keys={(j,n):KEYS[(j,n)] for j in self.models for n in (16,32,64)}

    @lru_cache(maxsize=128)
    def score(self,position,method,order=16):
        comp=self.component(position);chosen=list(self.models) if method=='mixture' else [58175]
        rows=[cached_physical(self.models[j],comp,*self.rules[(j,order)],self.keys[(j,order)]) for j in chosen]
        null=base.k.null_score(comp,np.arange(len(comp['raw']))) if method=='mixture' else None
        objective=base.combine([row['logZ'] for row in rows],-.5*null['objective'] if null else 0.,method)
        return dict(objective=objective,candidates=[dict(norad=j,**row) for j,row in zip(chosen,rows,strict=True)],
            unknown_objective=null['objective'] if null else None,phase_rule_order=order,
            physical_class_prior=.5 if method=='mixture' else 1.,target_calibrates_parent=False)


def install():
    base.HERE=HERE;base.ROOT=ROOT;base.Target=CachedTarget


def source_bindings():
    inputs=dict(r.read(PRIOR/'protocol.json')['source_input_hashes'])
    for path in list(HERE.glob('*.py'))+list(HERE.glob('*.md'))+[ROOT/'COORDINATOR_PLAN.md',PRIOR/'RF_seal.json']:
        inputs[str(path)]=gc.sha(path)
    return inputs


def prep_freeze():
    meta=r.read(base.OLD/'prepared/DS24-0011/metadata.json')
    points=[dict(name=name,position=meta['probes'][name]) for name in ('minus','center','plus')]
    points += [dict(name='regional'+str(i),position=x) for i,x in enumerate(REGIONAL)]
    write('preparation_protocol.json',dict(source_input_hashes=source_bindings(),tolerances=TOL,points=points,
        gradient_h_km=.01,geometry_all_nodes=True,score_order=16,old_probe_reference_orders=[32,64],
        preparation_cap_seconds=240,total_cap_seconds=600,cache_state_only=True,scientific_retries=0))
    print('PREPARATION_FROZEN',gc.sha(HERE/'preparation_protocol.json'),flush=True)


def load_keys():
    global KEYS
    KEYS={(int(row['norad']),int(row['order'])):row['key'] for row in r.read(HERE/'cache_manifest.json')['rows']}


def prepare():
    began=time.monotonic();result={};rows=[]
    try:
        sr.alarm(240.)
        protocol=r.read(HERE/'preparation_protocol.json')
        for path,digest in protocol['source_input_hashes'].items():
            if gc.sha(path)!=digest:raise ValueError('prefrozen source/input changed:'+path)
        d,entry,saved,meta,models=base.load()
        cache_rows=[]
        for j,candidate in models.items():
            for n in (16,32,64):
                nodes,logs=base.rule(candidate,n);key,body=CACHE.build(candidate,nodes)
                KEYS[(j,n)]=key;cache_rows.append(dict(norad=j,order=n,**body))
        write('cache_manifest.json',dict(rows=cache_rows,total_bytes=sum(row['bytes'] for row in cache_rows)))
        print('CACHE_READY',sum(row['bytes'] for row in cache_rows),flush=True)
        for arm in base.ARMS:
            reference=r.read(base.OLD/base.CASE/'center'/(arm+'_parent.json'))['phase_reference']
            parent=r.build(d,arm,reference);old=OriginalTarget(d,base.parent_view(parent),entry,models)
            fast=CachedTarget(d,base.parent_view(parent),entry,models)
            for item in protocol['points']:
                x=np.asarray(item['position']);at=[]
                for offset in (np.zeros(2),np.array([.01,0]),np.array([-.01,0]),np.array([0,.01]),np.array([0,-.01])):
                    pos=x+offset;coordinate=tuple(pos)
                    t=time.monotonic();a=old.score(coordinate,'mixture',16);old_seconds=time.monotonic()-t
                    t=time.monotonic();b=fast.score(coordinate,'mixture',16);cached_seconds=time.monotonic()-t
                    error=abs(a['objective']-b['objective'])
                    if error>TOL['objective']:raise ValueError('objective equivalence failure')
                    at.append(dict(position=pos,old=a['objective'],cached=b['objective'],error=error,old_seconds=old_seconds,cached_seconds=cached_seconds))
                oldgrad=np.array([(at[1]['old']-at[2]['old'])/.02,(at[3]['old']-at[4]['old'])/.02])
                fastgrad=np.array([(at[1]['cached']-at[2]['cached'])/.02,(at[3]['cached']-at[4]['cached'])/.02])
                graderror=float(np.max(abs(oldgrad-fastgrad)))
                if graderror>TOL['gradient_per_km']:raise ValueError('gradient equivalence failure')
                geometry=[]
                # Every node, every candidate at the center of each frozen control.
                for j,candidate in (models.items() if arm=='c0' else []):
                    nodes=old.rules[(j,16)][0];errors={name:0. for name in ('frequency_hz','shape_columns_hz','elevation_deg')}
                    for start in range(0,len(nodes),512):
                        first=base.k.m.q.phase_geometry(candidate,x,nodes[start:start+512])
                        second=CACHE.geometry(KEYS[(j,16)],x,start,min(start+512,len(nodes)))
                        for name in errors:errors[name]=max(errors[name],float(np.max(abs(first[name]-second[name]))))
                    if any(errors[name]>TOL[name] for name in errors):raise ValueError('geometry equivalence failure')
                    geometry.append(dict(norad=j,errors=errors))
                reference_orders={}
                if item['name'] in ('minus','center','plus'):
                    for n in (32,64):
                        first=old.score(tuple(x),'mixture',n);second=fast.score(tuple(x),'mixture',n)
                        error=abs(first['objective']-second['objective'])
                        if error>TOL['objective']:raise ValueError('reference-order equivalence failure')
                        reference_orders[str(n)]=dict(old=first['objective'],cached=second['objective'],error=error)
                row=dict(arm=arm,name=item['name'],points=at,old_gradient=oldgrad,cached_gradient=fastgrad,gradient_error=graderror,
                    geometry=geometry,reference_orders=reference_orders)
                rows.append(row);write(Path('equivalence')/(arm+'_'+item['name']+'.json'),row)
                print('EQUIVALENT',arm,item['name'],flush=True)
        # Real cross-round ownership check: a fresh parent/reference produces a
        # fresh component cache while satellite keys remain exactly unchanged.
        checks=[]
        for arm in base.ARMS:
            original=r.build(d,arm,np.zeros(len(d['means'])))
            refreshed=r.build(d,arm,np.asarray(r.read(base.OLD/base.CASE/'center'/(arm+'_parent.json'))['phase_reference']))
            a=CachedTarget(d,base.parent_view(original),entry,models)
            b=CachedTarget(d,base.parent_view(refreshed),entry,models)
            ca=a.component(tuple(meta['common_x']));cb=b.component(tuple(meta['common_x']))
            direct=OriginalTarget(d,base.parent_view(refreshed),entry,models).component(tuple(meta['common_x']))
            error=max(float(np.max(abs(cb[name]-direct[name]))) for name in ('raw','covariance','parent_noise','parent_coefficients'))
            changed=float(np.max(abs(ca['covariance']-cb['covariance'])))
            if error>1e-8 or changed<=0 or a.keys!=b.keys:raise ValueError('cross-round cache invalidation failed')
            checks.append(dict(arm=arm,old_new_covariance_difference=changed,direct_fresh_parent_error=error,geometry_keys_unchanged=True))
        result=dict(all_passed=True,rows=len(rows),cross_round=checks)
    except Exception as exc:
        result=dict(all_passed=False,rows=len(rows),error=repr(exc),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result['seconds']=time.monotonic()-began;write('preparation_result.json',result)
    print('PREPARATION_TERMINAL',result['all_passed'],result['seconds'],flush=True)


def freeze():
    preparation=r.read(HERE/'preparation_result.json')
    if not preparation['all_passed']:raise ValueError('equivalence failure: no fit launch')
    inputs=source_bindings()
    for path in list(HERE.glob('*.json'))+list((HERE/'equivalence').glob('*.json')):
        inputs[str(path)]=gc.sha(path)
    # Hash cache bytes once before dispatch; workers only map immutable inputs.
    for row in r.read(HERE/'cache_manifest.json')['rows']:
        inputs[str(HERE/'cache'/(row['key']+'.npy'))]=row['states_sha256']
        path=HERE/'cache'/(row['key']+'.json');inputs[str(path)]=gc.sha(path)
    tests=r.read(HERE/'test_receipt.json');spent=preparation['seconds']+tests['seconds']
    write('protocol.json',dict(source_input_hashes=inputs,preparation_seconds=spent,arm_worker_seconds=(600-spent)/2,
        total_worker_seconds=600,workers=2,BLAS_threads=1,fit_seconds=60,methods=base.METHODS,
        scientific_law='exact prior position policy.py unchanged; cached receiver-independent paired satellite states only',
        equivalence_tolerances=TOL,control_endpoint_tolerance_km=.001,control_objective_abs_tolerance=1e-3,
        parent_refresh='original5x48,coldzero starts,referencesclippedbetweenrounds; currentparent/Gamma perx',
        gates_and_policy='unchanged original source support/residual/fullacceptedID rules; always exactoriginal operationalreference',
        GPS_used=False,candidate_pruning=False,node_reduction=False,scientific_retries=0))
    print('FROZEN',gc.sha(HERE/'protocol.json'),flush=True)


def verify():
    protocol=r.read(HERE/'protocol.json')
    for path,digest in protocol['source_input_hashes'].items():
        if gc.sha(path)!=digest:raise ValueError('frozen source/input changed:'+path)
    audit=r.read(ROOT/'audit/preflight.json')
    if audit.get('all_passed') is not True or audit.get('protocol_sha256')!=gc.sha(HERE/'protocol.json'):
        raise ValueError('exact independent preflight required')
    return protocol


def job(arm,seconds):
    install();load_keys()
    result=base.arm_job(arm,seconds)
    for method in ('no_addition','hard'):
        path=HERE/arm/method/'raw_endpoint.json'
        if path.exists():
            actual=r.read(path);prior=r.read(PRIOR/arm/method/'raw_endpoint.json')
            difference=float(np.linalg.norm(np.asarray(actual['endpoint_east_north_km'])-prior['endpoint_east_north_km']))
            delta=float(actual['parent_negative_twice_elbo']-prior['parent_negative_twice_elbo'])
            write(Path(arm)/(method+'_prior_control.json'),dict(passed=bool(difference<=.001 and abs(delta)<=1e-3),
                endpoint_difference_km=difference,parent_ELBO_difference=delta))
    return result


def run():
    started=time.monotonic();protocol=verify();load_keys();setup=time.monotonic()-started
    seconds=protocol['arm_worker_seconds']-setup/2;results=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(job,arm,seconds):arm for arm in base.ARMS}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(arm=futures[future],status='worker_failed',error=repr(exc),seconds=seconds))
    slots=[]
    for arm in base.ARMS:
        for method in base.METHODS:
            path=HERE/arm/(method+'_result.json')
            slots.append(r.read(path) if path.exists() else dict(arm=arm,method=method,status='not_completed',operational_policy='original_reference'))
    write('execution.json',dict(arms=results,all6_slots=slots,all_selected_terminal=True,
        cumulative_scientific_seconds=protocol['preparation_seconds']+setup+sum(row['seconds'] for row in results),
        setup_seconds=setup,cap_seconds=600,GPS_used=False,operational_policy='original_reference'))
    files={str(path):gc.sha(path) for path in HERE.rglob('*') if path.is_file() and '.pytest_cache' not in str(path) and '__pycache__' not in str(path)}
    write('RF_seal.json',dict(files=files,protocol_sha256=gc.sha(HERE/'protocol.json'),all_selected_terminal=True,GPS_used=False))
    print('TERMINAL',r.read(HERE/'execution.json')['cumulative_scientific_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prep-freeze','prepare','freeze','run']);args=parser.parse_args()
    {'prep-freeze':prep_freeze,'prepare':prepare,'freeze':freeze,'run':run}[args.action]()
