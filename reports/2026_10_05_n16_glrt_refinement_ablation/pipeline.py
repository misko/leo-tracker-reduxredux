"""Controlled raw / saved orbit-free / additional orbit-free GLRT experiment.

Full-data, known-roof upstream calibration; independent 4 km localization.
Same candidate inventory, archived orbit bank, seeds, priors and fit budgets.
No heldout folds, no new IQ acquisition, no oracle input to GLRT refinement.
"""
import argparse
import copy
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'2026_10_04_t1_at_v1_replication'
CONES = HERE.parent/'2026_10_05_cone_prior_localization'
sys.path[:0] = [str(BASE), str(CONES), str(HERE.parent/'2026_10_05_receiver_cones')]
import full_data_calibration as calibration
from numeric_data import load as original_load, view
from refinement import circular, winners
from full_calibration_seed_audit import seed_vector
from seed_restart_pipeline import fixed_objective, unpack_fit
from convergence_fisher import fit
from cone_objective import Objective
from timing_bound_comparison import feasible_start
from audit_post_scan_tle import diagnostics
from polish_position_score_sweep import slsqp_fit
from subset_positions import serial

SCANS = tuple(f'N{i:02}' for i in range(1,17))
ARMS = ('fitted-c','zero-c')
STAGES = ('raw','pass1','pass2')
ARCHIVE = BASE/'full-scan-seed-restart'
FIELDS = ('times','measured','rf','receiver','channel','group','margin','original_rows',
          'owners','numbers','position','velocity','nodes','initial','fixed_receiver_hz')
BUDGET = dict(calibration_starts=2,calibration_s=12.,calibration_polish_s=18.,
              roof_s=8.,position_starts=3,position_s=12.,polish_s=15.,slsqp_s=15.)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,default=serial,allow_nan=False,indent=2))


def top_indices(records):
    best = {}
    for i,row in enumerate(records):
        key=tuple(row['probe_key']);priority=(row['margin'],-row['row_index'])
        if key not in best or priority>best[key][0]:best[key]=(priority,i)
    return np.array(sorted(v[1] for v in best.values()),int)


def load_stage(scan,stage):
    folder=calibration.INPUTS/scan/'seed-timing-v6'
    d=original_load(folder,top_only=False)
    original=json.loads((folder/'observations.json').read_text())
    if stage=='raw':
        d.measured=np.array([r['original_hz'] for r in original['records']])
        d.margin=np.array([r['original_margin'] for r in original['records']])
    elif stage=='pass2':
        path=HERE/'refinement'/scan/'refined.json';updated=json.loads(path.read_text())
        assert updated['summary']['status']=='complete'
        assert updated['summary']['parent_sha256']==digest(folder/'refinement/refined.json')
        byrow={r['row_index']:r for r in updated['records']}
        assert len(byrow)==len(d.times)
        for row in original['records']:
            assert byrow[row['row_index']]['candidate_id']==row['candidate_id']
            assert byrow[row['row_index']]['probe_key']==row['probe_key']
        d.measured=np.array([byrow[int(i)]['output_hz'] for i in d.original_rows])
        d.margin=np.array([byrow[int(i)]['refinement'].get('margin',byrow[int(i)]['original_margin']) for i in d.original_rows])
        d.sources[str(path)]='sha256:'+digest(path)
    elif stage!='pass1':raise ValueError(stage)
    records=[dict(probe_key=r['probe_key'],row_index=r['row_index'],margin=m) for r,m in zip(original['records'],d.margin)]
    indices=top_indices(records)
    d=view(d,indices);d.top_rows=d.original_rows.copy();d.top_mask=np.ones(len(indices),bool)
    assert len(np.unique(d.group))==len(d.times)
    d.sources[str(Path(__file__))]='sha256:'+digest(__file__)
    d.measurement_stage=stage
    return d


def calibrate(scan,stage,d):
    path=HERE/stage/scan/'calibration.json'
    if path.exists():
        r=json.loads(path.read_text());calibration.validate_scope(r,d);return r
    oldpath=ARCHIVE/scan/'calibration.json';old=json.loads(oldpath.read_text())
    ids=np.array(old['satellite_indices']);center=old['rf_center_hz']
    bootstrap_path=calibration.INPUTS/scan/'seed-timing-v6/bootstrap.json'
    boot=json.loads(bootstrap_path.read_text())
    pool=[(r['parameters'],0.) for r in boot['common_timing_trials']]
    # Identical pre-existing numerical seed pool for every measurement/RF arm.
    pool += [(old[part][a]['parameters'],old[part][a]['coefficient']) for part in ('pre','arms') for a in ARMS]

    def solve(data,seeds,arm):
        obj=fixed_objective(data,ids,center,arm);ranked=[]
        for p,c in seeds:
            v=seed_vector(obj,p,ids,0. if arm=='zero-c' else c)
            value,_=obj.evaluate(v);ranked.append((value,v))
        records=[]
        for _,v in sorted(ranked,key=lambda item:item[0])[:BUDGET['calibration_starts']]:
            records.append(fit(obj,v,[0.,0.],BUDGET['calibration_s'],True,radius_km=4.))
        best=min(records,key=lambda r:r['objective'])
        records.append(fit(obj,np.array(best['vector']),[0.,0.],BUDGET['calibration_polish_s'],True,radius_km=4.))
        best=min(records,key=lambda r:r['objective']);result=unpack_fit(obj,best)
        result['records']=records
        return result

    pre={a:solve(d,pool,a) for a in ARMS}
    if not all(p['success'] for p in pre.values()):
        save(path.with_name('unconverged-prefit.json'),{a:{k:v for k,v in p.items() if k!='probability'} for a,p in pre.items()})
        # Do not turn a compute limit into a scientific exclusion. Preserve flags.
    sys.path.insert(0,str(HERE.parent/'2026_10_03_ds13_coverage_goal'))
    import receiver_spline
    pred,visible=calibration.prediction(d,pre['fitted-c']['parameters'],ids,pre['fitted-c']['coefficient'],center)
    residual=circular(d.measured[:,None]-pred)
    support,owner=calibration.supported_rows(pre['fitted-c']['probability'],visible,residual)
    spline=receiver_spline.fit(d.times[support],d.receiver[support],residual[np.flatnonzero(support),owner[support]])
    adjusted=copy.copy(d);adjusted.measured=d.measured-receiver_spline.predict(spline,d.times,d.receiver)
    postpool=[(pre[a]['parameters'],pre[a]['coefficient']) for a in ARMS]+pool
    arms={a:solve(adjusted,postpool,a) for a in ARMS}
    r=dict(scan=scan,stage=stage,observations=d.sources,fit_original_rows=d.original_rows.tolist(),
        evaluation_original_rows=d.original_rows.tolist(),heldout_original_rows=[],satellite_indices=ids,
        seed_numbers=d.numbers[ids],rf_center_hz=center,spline_nodes_s=receiver_spline.NODES,
        correction_knots_hz=spline@receiver_spline.NULL.T,spline_training_original_rows=d.original_rows[support],
        spline_training_rows=int(sum(support)),
        pre={a:{k:v for k,v in p.items() if k!='probability'} for a,p in pre.items()},
        arms={a:{k:v for k,v in p.items() if k!='probability'} for a,p in arms.items()},
        converged=all(p['success'] for p in [*pre.values(),*arms.values()]),
        sources={str(p):digest(p) for p in (oldpath,bootstrap_path)},budget=BUDGET,
        caveat='Unconverged upstream fits are retained but flagged; all full-data, no heldout folds.')
    save(path,r);print('CALIBRATED',scan,stage,r['converged'],flush=True);return r


class StageCalibration(calibration.FullCalibration):
    def __init__(self,scan,stage):
        self.data=load_stage(scan,stage);self.d=self.data
        self.path=HERE/stage/scan/'calibration.json';self.record=calibrate(scan,stage,self.data)
        calibration.validate_scope(self.record,self.data)
        self.sources={**self.data.sources,str(self.path):'sha256:'+digest(self.path)}
        self.baseline={a:[] for a in ARMS};self.correction=np.zeros(len(self.data.times))
        for rx in (0,1):
            m=self.data.receiver==rx
            self.correction[m]=np.interp(self.data.times[m],self.record['spline_nodes_s'],self.record['correction_knots_hz'][rx])


def prepare(scan,stage):
    cal=StageCalibration(scan,stage);d=cal.data
    calibration.OUT=HERE/stage;calibration.FullCalibration=lambda _:cal
    calibration.associate(scan)
    folder=HERE/stage/scan
    result=json.loads((folder/'associations/fitted-c.json').read_text())
    final=result['final'];assigned=sorted(final['assignments'],key=lambda a:a['row_index'])
    lookup={int(n):i for i,n in enumerate(d.original_rows)};rows=np.array([lookup[a['row_index']] for a in assigned])
    selected={a['catalog_number']:a for a in final['selected']};numbers=sorted(selected)
    cols=np.array([np.flatnonzero(d.numbers==n)[0] for n in numbers])
    part=view(d,rows);part.fixed_receiver_hz=cal.receiver_baseline('fitted-c')[rows]
    part.measured-=part.fixed_receiver_hz;part.owners=np.array([a['catalog_number'] for a in assigned])
    part.numbers=d.numbers[cols];part.position=d.position[cols];part.velocity=d.velocity[cols]
    part.initial=np.r_[d.initial[:2],np.zeros(4),[selected[n]['offset_s'] for n in numbers]]
    np.savez_compressed(folder/'position-input.npz',**{k:getattr(part,k) for k in FIELDS})
    meta=dict(scan=scan,stage=stage,windows=len(part.times),denominator=len(d.times),coverage=len(part.times)/len(d.times),
              rf_center_hz=cal.record['rf_center_hz'],calibration_converged=cal.record['converged'],
              replacement_converged=result['converged'],numbers=numbers,input_sha256=digest(folder/'position-input.npz'))
    save(folder/'position-input.json',meta)
    return part,meta,cal


def position(d,meta,cal,scan,stage):
    folder=HERE/stage/scan
    # Same archived locations from both RF arms available to all three stages.
    archive=HERE.parent/'2026_10_05_n16_ambiguity_prototypes/polished'
    seeds=[]
    for arm in ARMS:
        record=json.loads((archive/f'{scan}-{arm}-baseline.json').read_text())
        seeds.append(record['best']['point_km'])
    result={}
    for arm in ARMS:
        path=folder/f'position-{arm}.json'
        if path.exists():result[arm]=json.loads(path.read_text());continue
        obj=Objective(d,meta['rf_center_hz'],arm,0.,None,None,None)
        seed=dict(parameters=d.initial,coefficient=cal.record['arms'][arm]['coefficient'])
        roof=fit(obj,feasible_start(obj,seed,20.,arm),[0.,0.],BUDGET['roof_s'],True,radius_km=4.)
        records=[roof]
        for point in [[0.,0.],*seeds]:
            records.append(fit(obj,np.array(roof['vector']),point,BUDGET['position_s'],False,radius_km=4.))
        best=min(records[1:],key=lambda r:r['objective'])
        records.append(fit(obj,np.array(best['vector']),best['point_km'],BUDGET['polish_s'],False,radius_km=4.))
        best=min(records[1:],key=lambda r:r['objective'])
        if not best['success']:records.append(slsqp_fit(obj,best,BUDGET['slsqp_s'],radius_km=4.))
        best=min(records[1:],key=lambda r:r['objective']);metrics=diagnostics(obj,d,best)
        r=dict(scan=scan,stage=stage,arm=arm,metadata=meta,best=best,roof=roof,records=records,
               budgets=BUDGET,fit_original_rows=d.original_rows,evaluation_original_rows=d.original_rows,
               heldout_original_rows=[],**metrics)
        save(path,r);result[arm]=r
        print('POSITION',scan,stage,arm,round(r['distance_m']),r['converged'],flush=True)
    return result


def run(task):
    scan,stage=task;started=time.monotonic()
    try:
        d,meta,cal=prepare(scan,stage);position(d,meta,cal,scan,stage)
        print('DONE',scan,stage,round(time.monotonic()-started,1),flush=True)
    except Exception as exc:
        save(HERE/stage/scan/'failure.json',dict(type=type(exc).__name__,error=str(exc)))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scans',nargs='+',default=SCANS,choices=SCANS)
    p.add_argument('--stages',nargs='+',choices=STAGES,default=['raw','pass1']);p.add_argument('--workers',type=int,default=6)
    args=p.parse_args()
    save(HERE/'protocol.json',dict(scope=__doc__,stages=STAGES,budget=BUDGET,
        association_score='assigned windows - 10 * satellites',association_tolerance_hz=600.,
        calibration='Full data, same archived bootstrap bank/seeds. Supported rows only for nonlinear RX spline.',
        position='All assigned top-one windows; Q1 smooth horizon; sigma=200Hz; common timing sigma=10s, relative sigma=1/3s; total shifts +/-20s; independent 4km disk.',
        ablation='Matched observations, satellite bank, priors and budgets in fitted-c and c=0 position arms.',
        caveat='Exploratory known-roof calibrated, in-sample evaluation; candidate inventory already detection-selected. Raw does not recover originally discarded probes.',
        implementation_sha256=digest(__file__)))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(run,(s,v)) for s in args.scans for v in args.stages]):f.result()
