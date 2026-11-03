"""Offline stage-local diagnostics. Truth is explicitly diagnostic, never a deployable seed."""
import concurrent.futures as futures
from dataclasses import asdict, replace
import json
import multiprocessing
from pathlib import Path
import shutil
import sys
import traceback
import numpy as np

HERE = Path(__file__).resolve().parent
SOFT = HERE.parent / '2026_10_07_n64_soft_slope_priors'
sys.path.insert(0, str(SOFT))
import run_soft as run
from slope_penalty import PenalizedObjective, annotate_region, penalty
from summarize import distance_km, reference_point
from leo.analysis.regional_position_score import coordinates
from validate_soft import independent_penalty

engine = run.engine
ORIGINAL_FIT = engine.fit_position
CONFIGS = dict(run.PHASES)
CONFIGS['sigma2_60'] = dict(run.COMMON, width=60., slope_prior=dict(kind='none'))
run.PHASES.update(CONFIGS)
engine.PHASES = run.PHASES
ARMS = ('zero-c', 'fitted-c')
PHASES = ('sigma2_60', 'gaussian60', 'smooth60', 'hard30', 'gaussian30', 'smooth30')


def read(path):
    return json.loads(Path(path).read_text())


def source(label, phase):
    root = run.PREVIOUS if phase == 'sigma2_60' else SOFT
    return root / 'results' / label / phase


def reference():
    d = read(run.OLD / 'evaluation.json')
    return [d['reference_latitude_deg'], d['reference_longitude_deg']]


def error(prior, vector):
    return distance_km(*coordinates(prior, vector[:2]), reference())


def region_path(folder, xy, radius):
    return folder / 'regions' / f'{xy[0]:g}_{xy[1]:g}_{radius:g}.json'


def inside(xy, center, radius):
    return bool(np.linalg.norm(np.asarray(xy) - center) <= radius + 1e-8)


def summarize_candidate(row, prior):
    keys = ('arm', 'origin', 'objective', 'selection_score', 'data_nll', 'timing_penalty',
            'slope_penalty', 'frozen_slope_penalty', 'frequency_rms_hz', 'converged',
            'feasible', 'stationarity', 'stop_reason', 'boundary', 'additional_slopes_hz_s')
    return dict({k: row.get(k) for k in keys}, error_km=error(prior, row['vector']),
                position_km=row['vector'][:2])


def saved_case(label, phase):
    _, _, _, prior, _ = engine.CONTEXT[label]
    truth = reference_point(prior, reference())
    folder = source(label, phase)
    result, search = read(folder / 'result.json'), read(folder / 'search.json')
    points = search['search']['evaluations']
    ordered = sorted(points, key=lambda p: (p['score'], p['east_km'], p['north_km']))
    enriched = []
    for rank, point in enumerate(ordered, 1):
        xy = [point['east_km'], point['north_km']]
        radius = max(25., point['spacing_km'] / np.sqrt(2))
        record = read(folder / 'points' / f'{xy[0]:g}_{xy[1]:g}.json')
        fit = record.get('fit')
        slopes = np.asarray(fit['vector'])[[3, 5]] if fit else None
        enriched.append(dict(point=xy, spacing_km=point['spacing_km'], radius_km=radius, rank=rank,
            score=point['score'], distance_to_reference_km=float(np.linalg.norm(np.asarray(xy) - truth)),
            covers_reference=inside(truth, xy, radius), status=record['status'],
            converged=fit['converged'] if fit else False,
            stationarity=fit['stationarity'] if fit else None,
            stop_reason=fit['stop_reason'] if fit else record.get('error'),
            slopes_hz_s=slopes, slope_penalty=penalty(slopes, CONFIGS[phase]['slope_prior'])[0] if fit else None))
    valid_cover = [p for p in enriched if p['covers_reference'] and p['status'] == 'complete']
    regions = []
    for b in result['basins']:
        xy = [b['east_km'], b['north_km']]; radius = max(25., b['spacing_km'] / np.sqrt(2))
        r = read(region_path(folder, xy, radius))
        arms = {}
        for arm in ARMS:
            feasible = [c for c in r['candidates'] if c['arm'] == arm and c['feasible']]
            accepted = [c for c in feasible if c['converged']]
            pack = lambda row: summarize_candidate(row, prior) if row else None
            arms[arm] = dict(best_accepted=pack(min(accepted, key=lambda c:c['selection_score'], default=None)),
                nearest_accepted=pack(min(accepted, key=lambda c:error(prior,c['vector']), default=None)),
                best_feasible=pack(min(feasible, key=lambda c:c['selection_score'], default=None)))
        point = next(p for p in enriched if p['point'] == xy)
        regions.append(dict(point=xy, radius_km=radius, covers_reference=inside(truth,xy,radius),
            status=r['status'], error=r.get('error'), elapsed_s=r['elapsed_s'], coarse=point, arms=arms))
    selected = {a:summarize_candidate(result['selections'][a]['result'],prior) for a in ARMS}
    return dict(label=label, phase=phase, truth_point_km=truth, selections=selected, regions=regions,
        nearest_grid_point_km=min(p['distance_to_reference_km'] for p in enriched),
        points_within25=sum(p['distance_to_reference_km']<=25 for p in enriched),
        best_reference_covering_point=valid_cover[0] if valid_cover else None, points=enriched)


def pipeline_probe(task):
    label, phase, xy, radius, mode = task
    engine.HERE = HERE / mode
    engine.context(label, phase)
    target = engine.point_path(label, phase, xy)
    assert target.is_relative_to(HERE)
    target.parent.mkdir(parents=True, exist_ok=True)
    (target.parent.parent / 'regions').mkdir(exist_ok=True)
    shutil.copyfile(source(label, phase) / 'points' / target.name, target)
    calls = []
    def measured(obj, start, **kwargs):
        def once(vector, name):
            r = ORIGINAL_FIT(obj, vector, **kwargs)
            calls.append(dict(name=name, fixed_position=kwargs.get('fixed_position', False),
                              arm=kwargs.get('rf_arm', 'fitted-c'), **asdict(r)))
            return r
        fit = once(start, 'original-call')
        if mode == 'calibration_retry' and kwargs.get('fixed_position') and not fit.converged:
            continuation = once(fit.vector, 'calibration-continuation')
            pool = [fit, continuation]
            if not continuation.converged:
                zero = fit.vector.copy(); zero[7:] = 0.
                pool.append(once(zero, 'calibration-zero-timing'))
            accepted = [r for r in pool if r.converged]
            fit = min(accepted or pool, key=lambda r:r.objective)
        return fit
    engine.fit_position = measured
    try:
        region = annotate_region(run.BASE_REFINE((label,phase,tuple(xy),radius)), CONFIGS[phase]['slope_prior'])
    finally:
        engine.fit_position = ORIGINAL_FIT
    engine.write(region_path(target.parent.parent, xy, radius), region)
    _, _, _, prior, _ = engine.CONTEXT[label]
    winners = {}
    for arm in ARMS:
        pool = [r for r in region['candidates'] if r['arm']==arm and r['feasible'] and r['converged']]
        best = min(pool,key=lambda r:r['selection_score'],default=None)
        winners[arm] = summarize_candidate(best,prior) if best else None
    return dict(kind='pipeline',label=label,phase=phase,mode=mode,point=xy,radius_km=radius,
                status=region['status'],error=region.get('error'),calls=calls,winners=winners)


def final_probe(task):
    label, phase, xy, radius = task
    _, obs, bank, prior, base_score = engine.context(label, phase)
    cfg = CONFIGS[phase]; spec = cfg['slope_prior']
    score = replace(base_score, relative_sigma_s=cfg['sigma'])
    region = read(region_path(source(label,phase),xy,radius))
    selected_bank = bank.select(region['association']['selected_indices'])
    baseline = np.asarray(region['calibration']['receiver_baseline_hz'])
    obj = PenalizedObjective(run.BASE_NATIVE(obs,selected_bank,prior,score,receiver_baseline_hz=baseline),spec)
    oracle = run.BASE_ORACLE(obs,selected_bank,prior,score,receiver_baseline_hz=baseline)
    truth = reference_point(prior, reference())
    frozen = penalty(np.asarray(region['calibration']['postfit']['vector'])[[3,5]],spec)[0]
    constant = region['calibration_penalty'] + frozen
    outputs = []
    def fit_one(start, arm, name, fixed=False, local=True):
        v = np.asarray(start).copy()
        if local:
            delta=v[:2]-xy; length=np.linalg.norm(delta)
            if radius < length <= radius+1e-4:
                v[:2]=xy+delta*((radius-1e-7)/length)
        result = ORIGINAL_FIT(obj,v,rf_arm=arm,fixed_position=fixed,
            maximum_seconds=20.,maximum_iterations=600,slope_half_width_hz_s=cfg['width'],
            local_center=np.asarray(xy) if local else None,local_radius_km=radius if local else None)
        raw,grad,terms = oracle.evaluate(result.vector)
        cost, extra = independent_penalty(result.vector,spec)
        native,native_grad,_ = obj.evaluate(result.vector)
        np.testing.assert_allclose([native,result.objective],[raw+cost,raw+cost],atol=1e-6,rtol=0)
        np.testing.assert_allclose(native_grad,grad+extra,atol=1e-6,rtol=1e-7)
        if arm=='zero-c': assert result.vector[6]==0.
        audit_grad=grad+extra
        if fixed: audit_grad=audit_grad.copy(); audit_grad[:2]=0.
        checked=engine.audit(oracle,result.vector,audit_grad,arm,xy if local else [0.,0.],
                              radius if local else prior.radius_km,cfg['width'])
        assert checked['converged']==result.converged
        mass=float(terms.responsibilities.sum())
        row=dict(name=name,arm=arm,**asdict(result),error_km=error(prior,result.vector),
            selection_score=raw+cost+constant,data_nll=float(terms.nll),timing_penalty=raw-float(terms.nll),
            slope_penalty=cost,frozen_slope_penalty=frozen,
            signal_fraction=mass/len(obs.times_s),
            inside_original_region=inside(result.vector[:2],xy,radius),
            local_disk_preserved=local,reference_fixed=fixed,original_oracle_audit=checked)
        outputs.append(row)
        return row
    fitted_pool=[c for c in region['candidates'] if c['arm']=='fitted-c' and c['feasible']]
    best_fitted=min(fitted_pool,key=lambda c:c['selection_score'])['vector']
    association=np.asarray(region['association']['initial_vector'])
    zero=association.copy();zero[7:]=0.
    starts={'association':association,'zero-timing':zero,'fitted-feasible':np.asarray(best_fitted)}
    for arm in ARMS:
        feasible=[c for c in region['candidates'] if c['arm']==arm and c['feasible']]
        best=min(feasible,key=lambda c:c['selection_score'])
        fit_one(best['vector'],arm,'best-feasible-continuation')
        profiles=[]
        for name,start in starts.items():
            v=start.copy();v[:2]=truth
            profiles.append(fit_one(v,arm,'reference-fixed:'+name,fixed=True,local=False))
        accepted=[r for r in profiles if r['converged']]
        if accepted:
            start=min(accepted,key=lambda r:r['selection_score'])['vector']
            fit_one(start,arm,'release-from-reference',local=inside(truth,xy,radius))
    return dict(kind='final',label=label,phase=phase,point=xy,radius_km=radius,
                reference_in_region=inside(truth,xy,radius),outputs=outputs)


def main():
    HERE.mkdir(exist_ok=True)
    source_manifest=read(SOFT/'artifact_manifest.json')
    for name,expected in source_manifest['files'].items():
        assert run.data.digest(SOFT/name)==expected,name
    summary=read(SOFT/'summary.json')
    worst=[max((r for r in summary['rows'] if r['phase']==p and r['arm']==a),key=lambda r:r['error_km'])
           for p in PHASES for a in ARMS]
    pairs=sorted({(r['label'],r['phase']) for r in worst})
    for label in sorted({label for label,phase in pairs}):
        engine.CONTEXT[label]=run.data.load(label)
    cases=[saved_case(label,phase) for label,phase in pairs]
    engine.write(HERE/'saved_audit.json',dict(worst=worst,cases=cases))
    tasks=[]
    for case in cases:
        label,phase=case['label'],case['phase']
        if not any(r['covers_reference'] for r in case['regions']):
            point=case['best_reference_covering_point']
            assert point is not None
            tasks.append(('pipeline',(label,phase,point['point'],point['radius_km'],'grid_rescue')))
        for region in case['regions']:
            xy,radius=region['point'],region['radius_km']
            if region['status']!='complete':
                tasks.append(('pipeline',(label,phase,xy,radius,'calibration_retry')))
            elif (label,phase) in (('N29','sigma2_60'),('N05','gaussian60')) or (label,phase)==('N49','gaussian60') and xy[0]>-100:
                tasks.append(('final',(label,phase,xy,radius)))
    protocol=dict(worst_cases=pairs,tasks=tasks,maximum_seconds_per_fit=20,maximum_iterations=600,
        workers=8,reference_usage='Truth-aided diagnostics only: reference nuisance profiles and selection of an already evaluated covering grid point. Never a deployable seed or N64 performance claim.',
        comparison_scope='Final c arms share frozen observations, bank, calibration and identical reference-profile starts and budgets. Continuations retain own-arm state. Calibration remains fitted-c.',
        source_manifest=run.data.digest(SOFT/'artifact_manifest.json'),source_code=run.data.digest(__file__))
    engine.write(HERE/'protocol.json',protocol)
    print('START',len(cases),'cases',len(tasks),'probe jobs',flush=True)
    outputs=[]
    with futures.ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context('fork')) as pool:
        pending={pool.submit(pipeline_probe if kind=='pipeline' else final_probe,task):(kind,task) for kind,task in tasks}
        for future in futures.as_completed(pending):
            kind,task=pending[future]
            try: output=future.result()
            except Exception as exc: output=dict(kind=kind,task=task,error=str(exc),traceback=traceback.format_exc())
            outputs.append(output)
            print('DONE',kind,task,output.get('error'),flush=True)
            engine.write(HERE/'probes.json',dict(completed=len(outputs),requested=len(tasks),outputs=outputs))
    for name,expected in source_manifest['files'].items():
        assert run.data.digest(SOFT/name)==expected,name
    assert all('traceback' not in r for r in outputs), 'A diagnostic probe raised an exception'
    print('COMPLETE',len(outputs),'probe jobs; original artifacts unchanged',flush=True)


if __name__=='__main__':
    main()
