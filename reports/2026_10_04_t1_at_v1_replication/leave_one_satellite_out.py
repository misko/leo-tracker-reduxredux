"""Independent single-satellite deletion tests for frozen T1-AT N12/N15.

Remove one satellite from the candidate bank and all windows originally owned
by it, across receivers/channels. All other windows/calibration stay unchanged;
the same finite-set likelihood can still softly redistribute retained windows.
Recenter the surviving timing parameters into the smaller zero-sum basis.
Do not compare absolute NLL across deletions (data and bank sizes differ).
Three-start bounded position searches; matched RF-arm budgets, not global minima.
"""
import argparse
import copy
import csv
import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import subset_positions as positions
from convergence_fisher import fit
from resume_position_convergence import best_record

HERE=Path(__file__).resolve().parent
OUT=HERE/'leave-one-out-N12-N15'
ARMS=('fitted-c','zero-c')


def digest(path):return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def delete_satellite(full, number):
    if number is not None and number not in full.numbers:raise ValueError('Unknown satellite')
    keep=np.ones(len(full.times),bool) if number is None else full.owners!=number
    ids=np.flatnonzero(np.ones(len(full.numbers),bool) if number is None else full.numbers!=number)
    if not keep.any() or not len(ids):raise ValueError('No remaining evidence')
    data=copy.copy(full)
    for key in ('times','measured','rf','receiver','channel','group','margin','original_rows','owners','fixed_receiver_hz'):
        if hasattr(data,key):setattr(data,key,getattr(full,key)[keep].copy())
    for key in ('numbers','position','velocity'):setattr(data,key,getattr(full,key)[ids].copy())
    data.initial=np.r_[full.initial[:6],full.initial[6:][ids]]
    return data,keep,ids


def remap_start(obj, record, ids, arm):
    p=np.array(record['parameters']);total=p[6:][ids];common=float(np.mean(total))
    lo,hi=obj.bounds[6]
    common_feasible=np.clip(common,lo,hi)
    return np.r_[p[:6],common_feasible,obj.base.basis.T@(total-common),
                 record['coefficient'] if arm=='fitted-c' else 0.]


def load(scan):
    root=positions.ROOT/scan
    meta=json.loads((root/'input.json').read_text())
    assert digest(root/'input.npz')==meta['input_sha256']
    with np.load(root/'input.npz') as z:full=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    old=json.loads((root/'all-100.json').read_text())
    for arm in ARMS:
        updated=HERE/'convergence-retry/final'/f'{scan}-{arm}.json'
        if updated.exists():
            newer=json.loads(updated.read_text())['best']
            old['arms'][arm]['best']=best_record([old['arms'][arm]['best'],newer])
    return full,meta,old


def run(task):
    scan,number,*options=task
    radius=float(options[0]) if options else 2.
    output=OUT if radius==2. else OUT.with_name(OUT.name+f'-{radius:g}km')
    filename='baseline.json' if number is None else f'drop-{number}.json'
    target=output/scan/filename
    if target.exists():return str(target)
    positions.enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    from position_direct import coordinate
    full,meta,old=load(scan)
    data,keep,ids=delete_satellite(full,number)
    result=dict(scan=scan,removed_satellite=number,scope=__doc__,radius_km=radius,
                original_windows=len(keep),removed_windows=int(sum(~keep)),retained_windows=int(sum(keep)),
                removed_rx0_windows=int(sum((~keep)&(full.receiver==0))),
                removed_rx1_windows=int(sum((~keep)&(full.receiver==1))),
                original_satellites=len(full.numbers),retained_satellites=data.numbers.tolist(),
                retained_rows_sha256='sha256:'+hashlib.sha256(data.original_rows.tobytes()).hexdigest(),
                input_sha256=meta['input_sha256'],rf_center_hz=meta['rf_center_hz'],
                budgets=dict(roof_s=4.,ring_probe_s=.75,ring_probes=6,search_starts=3,search_s=8.,
                             fixed_polish_s=4.,joint_polish_s=6.),
                implementation_sha256={str(p):digest(p) for p in (Path(__file__),HERE/'convergence_fisher.py')},arms={})
    for arm in ARMS:
        obj=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,100.)
        obj.center=meta['rf_center_hz'];obj.features=((data.rf-obj.center)/1e9)[:,None]
        obj.likelihood.features=obj.features
        obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-20.)
        obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,20.)
        if arm=='zero-c':obj.bounds[-1]=(0.,0.)
        obj.base.deadline=float('inf')
        original=old['arms'][arm]
        records=[]
        def fitted(stage,start,point,budget,fixed):
            record=fit(obj,start,point,budget,fixed,radius_km=radius);record['stage']=stage
            assert np.linalg.norm(record['point_km'])<=radius+1e-7
            records.append(record);return record
        roof=fitted('roof',remap_start(obj,original['roof'],ids,arm),[0.,0.],4.,True)
        previous_start=remap_start(obj,original['best'],ids,arm)
        previous_point=original['best']['point_km']
        if radius!=2.:
            prior_path=OUT/scan/filename
            prior=json.loads(prior_path.read_text())
            prior_best=prior['arms'][arm]['best']
            previous_start=prior_best['vector'];previous_point=prior_best['point_km']
            result['two_km_source_sha256']=digest(prior_path)
            assert abs(obj.evaluate(np.array(previous_start))[0]-prior_best['objective'])<1e-7
        if number is None and radius==2.:
            restored=obj.evaluate(previous_start)[0]
            assert abs(restored-original['best']['objective'])<1e-7
            records.append(original['best'])
        # Same six exploratory positions for every deletion and both RF arms.
        probes=[]
        for i in range(6):
            angle=2*np.pi*i/6
            point=.8*radius*np.array([np.cos(angle),np.sin(angle)])
            probes.append(fitted(f'probe-{i}',roof['vector'],point,.75,True))
        remote=min(probes,key=lambda r:r['objective'])
        for name,start,point in [('roof-start',roof['vector'],[0.,0.]),
                                 ('previous-minimum-start',previous_start,previous_point),
                                 ('ring-start',remote['vector'],remote['point_km'])]:
            fitted(name,start,point,8.,False)
        best=best_record(records)
        fixed=fitted('nuisance-polish',best['vector'],best['point_km'],4.,True)
        fitted('final-joint',fixed['vector'],fixed['point_km'],6.,False)
        best=best_record(records)
        roof=min([r for r in records if r['fixed_location'] and np.linalg.norm(r['point_km'])<1e-9],key=lambda r:r['objective'])
        obj.base.deadline=float('inf')
        score=obj.evaluate(np.array(best['vector']))[0]
        assert abs(score-best['objective'])<1e-7
        joint=[r for r in records if r['success'] and not r['fixed_location']]
        ambiguous=any(np.linalg.norm(np.array(r['point_km'])-best['point_km'])>.1 and abs(r['objective']-best['objective'])<1 for r in joint)
        result['arms'][arm]=dict(best=best,roof=roof,records=records,
                                distance_m=1000*float(np.linalg.norm(best['point_km'])),
                                boundary=bool(np.linalg.norm(best['point_km'])>radius-.001),
                                converged=bool(best['success'] and not best['fixed_location']),
                                ambiguous=ambiguous,delta_score_to_roof=best['objective']-roof['objective'],
                                score_reconstruction_error=score-best['objective'])
    target.parent.mkdir(exist_ok=True,parents=True)
    target.write_text(json.dumps(result,indent=2))
    print(scan,number,'removed',result['removed_windows'],
          [(a,round(v['distance_m']),v['converged']) for a,v in result['arms'].items()],flush=True)
    return str(target)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--radius-km',type=float,choices=(2.,4.),default=2.)
    args=p.parse_args()
    if not 1<=args.workers<=6:raise ValueError('Bounded worker count required')
    jobs=[]
    for scan in ('N12','N15'):
        full,_,_=load(scan);jobs.append((scan,None,args.radius_km));jobs.extend((scan,int(n),args.radius_km) for n in full.numbers)
    jobs.sort(key=lambda x:(x[1] is not None,x[0],x[1] or 0))
    started=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i,f in enumerate(as_completed([pool.submit(run,j) for j in jobs]),1):
            f.result();print('COMPLETE',i,'/',len(jobs),'elapsed_s',round(time.monotonic()-started),flush=True)


if __name__=='__main__':main()
