"""Full-scan nuisance calibration pilot; no withheld folds or synthetic fold files.

Reuse frozen top-one refined observations, bootstrap candidates, orbit bank,
likelihood and priors. All-window prefit, supported-window receiver correction,
then all-window nuisance refit. Known roof is fixed. In-sample evidence only.
"""
import argparse
import copy
import json
import sys
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from run import HERE,BENCHMARK,LEGACY
from numeric_data import load,enable_research_model
from calibration import multistart_fit,fixed_fit,prediction,serial
from refinement import circular
from timing_bound_comparison import digest
from convergence_fisher import fit

INPUTS=Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
OUT=HERE/'full-data-calibration-pilot'
ARMS=('fitted-c','zero-c')


def supported_rows(probability,visible,residual):
    winner=np.argmax(probability,axis=1);rows=np.arange(len(winner))
    mask=(probability[rows,winner]>=.8)&visible[rows,winner]&(abs(residual[rows,winner])<=600.)
    return mask,winner


def validate_scope(record,data):
    rows=data.original_rows.tolist()
    if record['fit_original_rows']!=rows or record['evaluation_original_rows']!=rows:
        raise ValueError('Full-scan calibration must fit and evaluate every top window')
    if record['heldout_original_rows'] or len(np.unique(data.group))!=len(rows):
        raise ValueError('Unexpected holdout or duplicate-window observation')
    if record['observations']!=data.sources:
        raise ValueError('Calibration input digest mismatch')


def polish(data,result,satellites,arm,center):
    from rf_calibration_diagnostic import CalibrationObjective
    obj=CalibrationObjective(data,np.asarray(result['parameters']),satellites,False,30.)
    obj.center=center;obj.features=((data.rf-center)/1e9)[:,None];obj.likelihood.features=obj.features
    obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-20.)
    obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,20.)
    if arm=='zero-c':obj.bounds[-1]=(0.,0.)
    refined=fit(obj,np.asarray(result['vector']),[0.,0.],25.,True,radius_km=4.)
    chosen=np.asarray(refined['vector']) if refined['objective']<=result['objective']+1e-7 else np.asarray(result['vector'])
    obj.base.deadline=float('inf');value,_=obj.evaluate(chosen)
    used_refined=np.array_equal(chosen,np.asarray(refined['vector']))
    output=dict(result,parameters=obj.base.state(chosen[:obj.size])['parameters'],vector=chosen,
        coefficient=float(chosen[-1]),objective=value,
        probability=obj.likelihood.last_result['row_association_probability'].copy(),
        polish=refined,success=bool(refined['success'] if used_refined else result['success']))
    return output


def calibrate(scan):
    enable_research_model()
    sys.path.insert(0,str(HERE.parent/'2026_10_03_ds13_coverage_goal'))
    import receiver_spline
    directory=INPUTS/scan/'seed-timing-v6';data=load(directory)
    target=OUT/scan/'calibration.json';target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        record=json.loads(target.read_text());validate_scope(record,data);return record
    bootstrap=json.loads((directory/'bootstrap.json').read_text())
    for p,h in data.sources.items():assert bootstrap['sources'][p]==h
    satellites=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in bootstrap['selected_seed_numbers']])
    starts=[np.asarray(r['parameters']) for r in bootstrap['common_timing_trials']]
    center=float(np.mean(np.unique(data.rf)));pre={}
    for arm in ARMS:
        pre[arm]=multistart_fit(data,starts,satellites,arm,center=center)
        pre[arm]=polish(data,pre[arm],satellites,arm,center)
        print('FULL CAL PRE',scan,arm,pre[arm]['success'],flush=True)
    if not all(pre[a]['success'] for a in ARMS):
        target.with_name('calibration-pre-partial.json').write_text(json.dumps(pre,default=serial,indent=2))
        raise RuntimeError('Calibration prefit not converged; partial receipt retained')
    pred,visible=prediction(data,pre['fitted-c']['parameters'],satellites,pre['fitted-c']['coefficient'],center)
    residual=circular(data.measured[:,None]-pred)
    support,winner=supported_rows(pre['fitted-c']['probability'],visible,residual)
    rows=np.arange(len(data.times))
    spline=receiver_spline.fit(data.times[support],data.receiver[support],residual[rows[support],winner[support]])
    correction=receiver_spline.predict(spline,data.times,data.receiver)
    adjusted=copy.copy(data);adjusted.measured=data.measured-correction
    arms={}
    for arm in ARMS:
        r=fixed_fit(adjusted,pre[arm]['parameters'],satellites,arm,coefficient=pre[arm]['coefficient'],center=center)
        r=polish(adjusted,r,satellites,arm,center)
        pred,visible=prediction(data,r['parameters'],satellites,r['coefficient'],center)
        nearest=np.min(np.where(visible,abs(circular(data.measured[:,None]-pred-correction[:,None])),np.inf),axis=1)
        inside=nearest<=600.
        arms[arm]={k:v for k,v in r.items() if k!='probability'}
        arms[arm].update(in_sample_inside600=int(sum(inside)),in_sample_windows=len(data.times),
            in_sample_nearest_rms_inside600_hz=float(np.sqrt(np.mean(nearest[inside]**2))))
        print('FULL CAL POST',scan,arm,r['success'],'inside600',sum(inside),flush=True)
    record=dict(scope=__doc__,scan=scan,observations=data.sources,
        bootstrap_source=str(directory/'bootstrap.json'),bootstrap_sha256=digest(directory/'bootstrap.json'),
        implementation_sha256=digest(Path(__file__)),fit_original_rows=data.original_rows,
        evaluation_original_rows=data.original_rows,heldout_original_rows=[],seed_numbers=data.numbers[satellites],
        satellite_indices=satellites,rf_center_hz=center,spline_nodes_s=receiver_spline.NODES,
        correction_knots_hz=spline@receiver_spline.NULL.T,spline_training_original_rows=data.original_rows[support],
        spline_training_rows=int(sum(support)),arms=arms,
        pre={a:{k:v for k,v in pre[a].items() if k!='probability'} for a in ARMS},
        converged=all(arms[a]['success'] for a in ARMS),
        spline_priors=dict(amplitude_sigma_hz=50,second_difference_sigma_hz=25,knot_spacing_s=30,noise_sigma_hz=200,robust_iterations=3),
        c_ablation='Matched full windows, bootstrap bank, priors, budgets; common fitted-c-derived nonlinear RX correction.')
    target.write_text(json.dumps(record,default=serial,indent=2,allow_nan=False))
    if not record['converged']:raise RuntimeError('Full calibration did not converge; not qualified for discovery')
    return record


class FullCalibration:
    def __init__(self,scan):
        self.data=load(INPUTS/scan/'seed-timing-v6');self.d=self.data
        self.path=OUT/scan/'calibration.json';self.record=json.loads(self.path.read_text())
        validate_scope(self.record,self.data)
        if not self.record['converged']:raise ValueError('Unconverged full calibration')
        self.sources={**self.data.sources,str(self.path):digest(self.path),str(Path(__file__)):digest(Path(__file__))}
        self.baseline={a:[] for a in ARMS}
        self.correction=np.zeros(len(self.data.times))
        for rx in (0,1):
            m=self.data.receiver==rx
            self.correction[m]=np.interp(self.data.times[m],self.record['spline_nodes_s'],self.record['correction_knots_hz'][rx])

    def receiver_baseline(self,arm):
        p=np.asarray(self.record['arms'][arm]['parameters']);d=self.data
        return self.correction+p[2+2*d.receiver]+p[3+2*d.receiver]*(d.times-150.)

    def predict(self,arm,ids,timing):
        from prediction_jacobian import paired_prediction_jacobian
        ids=np.asarray(ids,dtype=int);d=self.data;n=len(d.times)
        p=np.asarray(self.record['arms'][arm]['parameters']).copy();p[6+ids]=timing
        prediction,visible,jac=paired_prediction_jacobian(d,p,np.repeat(np.arange(n),len(ids)),np.tile(ids,n))
        correction=self.correction+self.record['arms'][arm]['coefficient']*(d.rf-self.record['rf_center_hz'])/1e9
        return prediction.reshape(n,-1)+correction[:,None],visible.reshape(n,-1),jac.tau.reshape(n,-1)

    def residual(self,arm,index,timing):
        p,v,r=self.predict(arm,[index],timing)
        return circular(self.data.measured-p[:,0]),v[:,0],r[:,0]


def associate(scan):
    cal=FullCalibration(scan);d=cal.data
    sys.path.insert(0,str(LEGACY))
    import greedy_pool_two_scans as historical
    sys.path.insert(0,str(historical.OLD))
    from greedy_restart_scan import compile_mode
    from penalty_replace_search import Search
    out=OUT/scan/'associations';out.mkdir(exist_ok=True)
    historical.FrozenCalibration=lambda:cal;historical.OUT=out;historical.SCAN=scan;historical.SESSIONS[scan]=d.session_id
    if not (out/'candidate-pool.json').exists():
        historical.discover()
        pool=json.loads((out/'candidate-pool.json').read_text())
        pool.update(scope='Full-scan calibration; top-one GLRT; absolute timing +/-20s; in-sample discovery.',
                    calibration_source=str(cal.path),calibration_sha256=digest(cal.path))
        (out/'candidate-pool.json').write_text(json.dumps(pool))
    pool=json.loads((out/'candidate-pool.json').read_text())
    assert pool['original_rows']==d.original_rows.tolist()
    assert pool['calibration_sha256']==digest(cal.path)
    assert [(m['catalog_number'],m['offset_s']) for m in pool['arms'][ARMS[0]]]==[(m['catalog_number'],m['offset_s']) for m in pool['arms'][ARMS[1]]]
    for arm in ARMS:
        target=out/f'{arm}.json'
        if target.exists():continue
        result=Search([compile_mode(m,d.receiver,d.channel) for m in pool['arms'][arm]],d.group,d.times).run(3)
        for selected in result['final']['selected']:
            mode=pool['arms'][arm][selected['mode_index']]
            assigned=[a for a in result['final']['assignments'] if a['catalog_number']==selected['catalog_number']]
            ix=np.asarray([a['row_index'] for a in assigned],int)
            errors,visible,_=cal.residual(arm,mode['satellite_index'],mode['offset_s'])
            assert np.all(visible[ix]) and np.all(abs(errors[ix])<=600.)
            np.testing.assert_allclose(errors[ix],[a['residual_hz'] for a in assigned],atol=1e-6,rtol=0)
        for stage in ('initial','final'):
            r=result[stage]
            assert len({int(d.group[a['row_index']]) for a in r['assignments']})==r['assigned']
            for a in r['assignments']:a['row_index']=int(d.original_rows[a['row_index']])
            r.update(denominator=len(d.times),coverage=r['assigned']/len(d.times),unassigned=len(d.times)-r['assigned'])
        result.update(scan=scan,arm=arm,source_sha256=digest(out/'candidate-pool.json'),scope=pool['scope'],
            rms_hz=float(np.sqrt(np.mean([a['residual_hz']**2 for a in result['final']['assignments']]))))
        target.write_text(json.dumps(result,default=serial,indent=2))
        print('ASSOCIATED',scan,arm,result['final']['assigned'],len(d.times),result['final']['satellites'],flush=True)
    return scan


def run(scan):
    calibrate(scan);return associate(scan)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scans',nargs='+',default=['N12','N15']);parser.add_argument('--calibrate-only',action='store_true')
    args=parser.parse_args();OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(calibrate if args.calibrate_only else run,s) for s in args.scans]):
            result=future.result();print('COMPLETE',result if isinstance(result,str) else result['scan'],flush=True)
