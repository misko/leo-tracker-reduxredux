"""Five-block-fold RX/time/RF calibration using the existing DS13 likelihood.

Conditional on the known roof and bootstrap candidate set. Held-out residuals
test transfer of nuisance fits, not independent satellite identity discovery.
"""
import argparse
import copy
import inspect
import json
import sys
import time
from pathlib import Path

import numpy as np

from cohort import ROOT, digest
from numeric_data import enable_research_model, load, view
from refinement import circular


def blocked_folds(times, groups):
    times, groups = np.asarray(times), np.asarray(groups)
    if times.shape != groups.shape or times.ndim != 1 or not np.all(np.isfinite(times)):
        raise ValueError('invalid fold inputs')
    result = np.empty(len(times), int)
    for group in np.unique(groups):
        rows = np.flatnonzero(groups == group)
        result[rows] = int(np.floor(np.median(times[rows])/10)) % 5
    return result


def serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value))


def fixed_fit(data, initial, satellites, arm, *, coefficient=0., center=None, starts=None):
    enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    from truth_start_diagnostic import optimize
    objective = CalibrationObjective(data, initial, satellites, False, 8.)
    if center is not None:
        objective.center = float(center)
        objective.features = ((data.rf-objective.center)/1e9)[:, None]
        objective.likelihood.features = objective.features
    objective.base.minimum_shift_s = max(objective.base.minimum_shift_s, -20.)
    objective.base.maximum_shift_s = min(objective.base.maximum_shift_s, 20.)
    bounds = list(objective.bounds)
    bounds[:2] = [(v,v) for v in initial[:2]]
    if arm == 'zero-c':
        bounds[-1] = (0.,0.)
    current = objective.initial.copy()
    current[-1] = coefficient if arm == 'fitted-c' else 0.
    attempts = []
    for _ in range(3):
        fitted = optimize(objective, current, bounds, budget_s=8.)
        current = np.asarray(fitted['vector'])
        attempts.append({k:fitted[k] for k in ('objective','success','status','projected_gradient_inf_norm','elapsed_s')})
        if fitted['success']:
            break
    if not fitted['success']:
        from constrained_fit import optimize as constrained_optimize
        constrained=constrained_optimize(objective,current,bounds,budget_s=20.)
        attempts.append({k:constrained[k] for k in ('objective','success','status','projected_gradient_inf_norm','elapsed_s')})
        if constrained['objective']<=fitted['objective']:
            fitted=constrained
            current=np.asarray(fitted['vector'])
    objective.base.deadline = float('inf')
    objective.evaluate(current)
    state = objective.base.state(current[:objective.size])
    result = dict(parameters=np.asarray(state['parameters']), coefficient=float(current[-1]), vector=current,
                  success=bool(fitted['success']), attempts=attempts, objective=float(fitted['objective']),
                  nuisance_gradient=float(fitted['projected_gradient_inf_norm']),
                  probability=objective.likelihood.last_result['row_association_probability'].copy())
    return result


def multistart_fit(data, starts, satellites, arm, *, center):
    """Rank all five common-shift starts using the actual likelihood, fit two.

    Track-shape initialization's robust score is not the finite-set objective.
    Selecting only its winner can put every seed outside the narrow likelihood.
    Both RF arms get the identical starts and optimization budget.
    """
    from rf_calibration_diagnostic import CalibrationObjective
    ranked = []
    for i, start in enumerate(starts):
        objective = CalibrationObjective(data, start, satellites, False, 8.)
        value, _ = objective.evaluate(objective.initial)
        ranked.append((float(value), i))
    fitted = []
    for _, i in sorted(ranked)[:2]:
        result = fixed_fit(data, starts[i], satellites, arm, center=center)
        result['start_index'] = i
        fitted.append(result)
    best = min(fitted, key=lambda r:r['objective'])
    best['initial_objectives'] = ranked
    best['start_results'] = [{k:r[k] for k in ('start_index','objective','success','attempts')} for r in fitted]
    return best


def prediction(data, parameters, satellites, coefficient, center):
    from prediction_plan import SharedPredictionPlan
    pred, visible, _ = SharedPredictionPlan(data, satellites).predict(np.asarray(parameters))
    pred = pred.reshape(len(data.times), len(satellites)) + coefficient*(data.rf[:,None]-center)/1e9
    return pred, visible.reshape(pred.shape)


def run(directory, *, only_fold=None):
    started = time.monotonic()
    data = load(directory)
    source = directory/'bootstrap.json'
    bootstrap = json.loads(source.read_text())
    # Bootstrap also binds its implementation; compare shared upstream inputs.
    for path, expected in data.sources.items():
        if bootstrap['sources'].get(path) != expected:
            raise ValueError('bootstrap observations or ephemeris changed')
    sys.path.append(str(ROOT/'reports/2026_10_03_ds13_coverage_goal'))
    import receiver_spline
    from rf_calibration_diagnostic import CalibrationObjective
    from truth_start_diagnostic import optimize
    implementation = [Path(__file__), Path(inspect.getfile(receiver_spline)),
                      Path(__file__).with_name('constrained_fit.py'),
                      Path(inspect.getfile(CalibrationObjective)), Path(inspect.getfile(optimize))]
    signature = dict(bootstrap_sha256=digest(source.read_bytes()), observations=data.sources,
                     implementation={str(p):digest(p.read_bytes()) for p in implementation})
    satellites = np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in bootstrap['selected_seed_numbers']])
    folds = blocked_folds(data.times, data.group)
    folder = directory/'calibration-v2'
    folder.mkdir(exist_ok=True)
    outputs = []
    for fold in range(5) if only_fold is None else [only_fold]:
        target = folder/f'fold-{fold}.json'
        if target.exists():
            saved = json.loads(target.read_text())
            if saved['signature'] != signature:
                raise ValueError('calibration resume signature mismatch')
            outputs.append(saved)
            continue
        train, test = view(data, folds!=fold), view(data, folds==fold)
        if not len(train.times) or not len(test.times):
            raise ValueError('empty temporal fold')
        center = float(np.mean(np.unique(data.rf)))
        pre = {}
        initial = np.asarray(bootstrap['initial_parameters'])
        starts = [np.asarray(r['parameters']) for r in bootstrap['common_timing_trials']]
        for arm in ('fitted-c','zero-c'):
            pre[arm] = multistart_fit(train, starts, satellites, arm, center=center)
            print('CALIBRATE',directory.name,fold,arm,'pre',pre[arm]['success'],pre[arm]['nuisance_gradient'],flush=True)
        # Fit the shared receiver-only curvature on training rows, excluding the
        # test block. Same frozen nonlinear correction for both RF ablation arms.
        pred, visible = prediction(train, pre['fitted-c']['parameters'], satellites, pre['fitted-c']['coefficient'], center)
        residual = circular(train.measured[:,None]-pred)
        probability = pre['fitted-c']['probability']
        best = np.argmax(probability, axis=1)
        rr = np.arange(len(train.times))
        supported = (probability[rr,best]>=.8) & visible[rr,best] & (abs(residual[rr,best])<=600.)
        spline = receiver_spline.fit(train.times[supported],train.receiver[supported],residual[rr[supported],best[supported]])
        correction_train = receiver_spline.predict(spline,train.times,train.receiver)
        correction_test = receiver_spline.predict(spline,test.times,test.receiver)
        adjusted = copy.copy(train)
        adjusted.measured = train.measured-correction_train
        arms = {}
        for arm in ('fitted-c','zero-c'):
            result = fixed_fit(adjusted,pre[arm]['parameters'],satellites,arm,coefficient=pre[arm]['coefficient'],center=center)
            pred, visible = prediction(test,result['parameters'],satellites,result['coefficient'],center)
            residual = circular(test.measured[:,None]-pred-correction_test[:,None])
            nearest = np.min(np.where(visible,abs(residual),np.inf),axis=1)
            inside = nearest<=600
            arms[arm] = {k:v for k,v in result.items() if k!='probability'}
            arms[arm].update(heldout_inside600=int(sum(inside)),heldout_windows=len(test.times),
                             heldout_nearest_rms_inside600_hz=float(np.sqrt(np.mean(nearest[inside]**2))) if np.any(inside) else None)
            print('CALIBRATE',directory.name,fold,arm,'post',result['success'],result['nuisance_gradient'],flush=True)
        record = dict(signature=signature,fold=fold,seed_numbers=data.numbers[satellites],satellite_indices=satellites,
                      train_original_rows=train.original_rows,test_original_rows=test.original_rows,
                      rf_center_hz=center, spline_nodes_s=receiver_spline.NODES,
                      correction_knots_hz=spline@receiver_spline.NULL.T,spline_training_rows=int(sum(supported)),
                      spline_training_original_rows=train.original_rows[supported],arms=arms,
                      pre_fit_attempts={a:pre[a]['attempts'] for a in pre},
                      initialization_search={a:{k:pre[a][k] for k in ('start_index','initial_objectives','start_results')} for a in pre},
                      converged=all(pre[a]['success'] and arms[a]['success'] for a in arms),
                      scope=__doc__,bootstrap_scope='Whole-scan track shapes supplied common initialization and candidate set. Held-out nuisance transfer is conditional on those; not a fully held-out identity test.',
                      spline_priors=dict(amplitude_sigma_hz=50,second_difference_sigma_hz=25,knot_spacing_s=30,noise_sigma_hz=200,robust_iterations=3),
                      c_ablation='Identical training/test rows, seed bank, timing priors, fit budgets, nonlinear receiver correction; c is fitted or fixed to zero.')
        with target.open('x') as stream:
            json.dump(record,stream,default=serial,indent=2,allow_nan=False)
        outputs.append(record)
    print(json.dumps(dict(scan=directory.name,folds=len(outputs),converged=sum(r['converged'] for r in outputs),elapsed_s=time.monotonic()-started)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--fold',type=int,choices=range(5))
    args=parser.parse_args()
    run(args.directory,only_fold=args.fold)
