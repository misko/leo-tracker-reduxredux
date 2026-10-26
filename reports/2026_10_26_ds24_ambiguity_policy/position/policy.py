"""DS24-0011: matched original five-refresh parent fits with optional target factors."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
import signal
import sys
import time
import traceback
import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp, roots_legendre

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OLD = Path('/srv/bulk/leo/research/ds24-ambiguity-position-r01/ambiguity')
sys.path.insert(0, str(OLD))
import pilot02 as old
sr, k, r = old.sr, old.k, old.r
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from investigate_dsx01_localization_failures import fit
from run_ds23_combined_recovery_full import growth_supported
from audit_ds23_algo01_coverage import retained_metrics
from probe_ds23_frequency_events import summary

CASE = 'DS24-0011'
ARMS = ('c0', 'fitted_c')
METHODS = ('no_addition', 'hard', 'mixture')
ORDER = 16
FIT_SECONDS = 60.
TOTAL_SECONDS = 600.


def write(name, value):
    r.write_new(HERE / name, value)


def load():
    d, entry, saved, meta = old.context(CASE)
    if len(entry['observation_ids']) != 20 or len(saved['candidate_norads']) != 8:
        raise ValueError('original whole-owner/pool changed')
    models = {norad: k.candidate(d, norad) for norad in saved['candidate_norads']}
    return d, entry, saved, meta, models


def source_gate(d, parent, x, entry):
    """Gate original frozen-parent predictions; no target normal-equation update."""
    row_index = next(i for i, row in enumerate(parent.rows) if row['component'] == entry['component'])
    offered = parent.keep.copy()
    offered[parent.slices[row_index]] = True
    # Bound methods deliberately read the ORIGINAL parent and its cached arrays.
    fields = dict(vars(parent))
    fields.update(keep=offered, state=parent.state, calculate=parent.calculate,
                  conditional_frequency=parent.conditional_frequency)
    gates = retained_metrics(SimpleNamespace(**fields), np.asarray(x))
    target = next(row for row in gates['tracks'] if row['component'] == entry['component'])
    support = growth_supported(parent, dict(candidate_index=entry['candidate_index'], rows=[row_index]))
    return dict(original_target_gate=target, original_growth_supported=bool(support),
        original_target_active_points=int(parent.keep[parent.slices[row_index]].sum()),
        offered_native_IDs=entry['observation_ids'], accepted_target=False,
        meanings='original frozen-parent profile/conditional gates and owner cascade; marginal target moments never create calibration support')


def rule(candidate, order):
    times = np.asarray(candidate['target_track']['times'])
    grid = np.asarray(candidate['target_sky']['time_s'])
    if not np.array_equal(grid, candidate['target_mode_bank']['time_s']):
        raise ValueError('nominal/mode interpolation grids differ')
    cuts = np.unique(np.r_[-15., 15., (grid[:, None] - times[None, :]).reshape(-1)])
    cuts = cuts[(cuts >= -15) & (cuts <= 15)]
    z, weight = roots_legendre(order)
    half = np.diff(cuts) / 2
    nodes = ((cuts[:-1] + cuts[1:])[:, None] / 2 + half[:, None] * z).reshape(-1)
    prior = sr.law(candidate)
    logs = (np.log(half[:, None]) + np.log(weight)[None]).reshape(-1)
    logs += prior['distribution'].logpdf(nodes) - np.log(prior['mass'])
    return nodes, logs


def physical(candidate, comp, nodes, logs):
    values = []
    minimum = np.inf
    for start in range(0, len(nodes), 512):
        phases = nodes[start:start + 512]
        geometry = k.m.q.phase_geometry(candidate, comp['x'], phases)
        minimum = min(minimum, float(geometry['elevation_deg'].min()))
        raw = comp['raw'][None] - comp['q'][None] * geometry['frequency_hz']
        shape = comp['q'][None, :, None] * geometry['shape_columns_hz']
        costs = sr.sm.positive_costs(raw, comp['covariance'], shape, comp['shifts'])
        density = logsumexp(-costs / 2, axis=1) - np.log(9)
        density = np.where(geometry['elevation_deg'].min(axis=1) >= 0, density, -np.inf)
        values.append(density)
    logz = float(logsumexp(np.concatenate(values) + logs))
    return dict(objective=-2 * logz, logZ=logz, node_min_elevation_deg=minimum,
                order=len(nodes), original_prior_normalization=True, visible_mass_renormalized=False)


def combine(physical_logz, unknown_logz, method):
    if method == 'hard':
        return -2 * physical_logz[0]
    if method != 'mixture' or len(physical_logz) != 8:
        raise ValueError('declared whole-owner factor required')
    return float(-2 * logsumexp(np.r_[np.asarray(physical_logz) + np.log(.5 / 8), unknown_logz + np.log(.5)]))


class Target:
    """One exact parent conditional shared by all eight identities and unknown."""
    def __init__(self, d, parent, entry, models):
        self.d, self.parent, self.entry, self.models = d, parent, entry, models
        view, values, sigma, groups, _ = linear_geometry(parent, [entry])
        hardware = view.hardware.copy(); hardware[:, [4, 6]] *= 10
        width = parent.hardware.shape[1] + parent.smooth.shape[1]
        self.ht = np.zeros((len(values), parent.calculate(np.zeros(2))['features'].shape[1]))
        self.ht[:, :width] = np.column_stack((hardware, view.smooth * 200))
        self.values, self.sigma, self.groups, self.q = values, sigma, groups, view.q
        self.existing = linear_geometry(parent, d['entries']) if d['entries'] else None
        self.rules = {(j, n): rule(candidate, n) for j, candidate in models.items() for n in (16, 32, 64)}

    @lru_cache(maxsize=128)
    def component(self, position):
        x = np.asarray(position)
        c = self.parent.calculate(x)
        p = self.parent
        g = p.noise_groups[p.keep]
        weights = self.d['powers'][g] * c['noise_precision'][g] / p.point_noise[p.keep]**2
        train = c['features'][p.keep]
        gram = np.diag(c['coefficient_prior_precision']) + train.T @ (train * weights[:, None])
        root = np.linalg.cholesky(gram)
        ut = solve_triangular(root, self.ht.T, lower=True).T
        if self.existing:
            view, values, sigma, groups, _ = self.existing
            geometry = geometry_features(view, x, 0.)
            he = geometry['features']
            raw = values - view.q * geometry['intercept'] - he @ c['coefficient']
            ue = solve_triangular(root, he.T, lower=True).T
            fe = np.column_stack((ue, np.eye(int(groups.max()) + 1)[groups] * 300.))
            ft = np.column_stack((ut, np.zeros((len(ut), fe.shape[1] - len(gram)))))
            white = fe / (sigma * np.sqrt(2))[:, None]
            re = np.linalg.cholesky(np.eye(fe.shape[1]) + white.T @ white)
            mean = solve_triangular(re.T, solve_triangular(re, white.T @ (raw / (sigma * np.sqrt(2))), lower=True), lower=False)
            update = ft @ mean
            uncertainty = solve_triangular(re, ft.T, lower=True).T
        else:
            update = np.zeros(len(ut)); uncertainty = ut
        covariance = np.diag(2 * self.sigma**2) + uncertainty @ uncertainty.T + 300.**2
        comp = dict(x=x, raw=self.values - self.ht @ c['coefficient'] - update,
            covariance=(covariance + covariance.T) / 2, q=self.q, groups=self.groups,
            d=self.d, parent_coefficients=c['coefficient'].copy(), parent_noise=c['noise_precision'].copy())
        comp['aliases'], comp['shifts'] = k.alias_vectors(self.groups, np.arange(-4, 5))
        return comp

    @lru_cache(maxsize=128)
    def score(self, position, method, order=ORDER):
        comp = self.component(position)
        chosen = list(self.models) if method == 'mixture' else [58175]
        rows = [physical(self.models[j], comp, *self.rules[(j, order)]) for j in chosen]
        null = k.null_score(comp, np.arange(len(comp['raw']))) if method == 'mixture' else None
        objective = combine([row['logZ'] for row in rows], -.5 * null['objective'] if null else 0., method)
        return dict(objective=objective, candidates=[dict(norad=j, **row) for j, row in zip(chosen, rows, strict=True)],
            unknown_objective=null['objective'] if null else None, phase_rule_order=order,
            physical_class_prior=.5 if method == 'mixture' else 1., target_calibrates_parent=False)


def attach(parent, target, method):
    if method == 'no_addition':
        return parent
    calculate = parent.calculate
    def augmented(x):
        c = dict(calculate(np.asarray(x)))
        prediction = target.score(tuple(np.asarray(x)), method)
        score = prediction['objective']
        if not np.isfinite(score) or score < 0:
            raise ValueError('normalized target density has invalid positive scalar cost')
        c['parent_negative_twice_elbo'] = c['negative_twice_elbo']
        c['negative_twice_elbo'] += score
        c['residual'] = np.r_[c['residual'], np.sqrt(score)]
        c['target_prediction'] = prediction
        return c
    # The target holds ORIGINAL parent methods through a separate shallow view;
    # no recursive augmented calculate and no target coefficient/Gamma update.
    parent.calculate = augmented
    return parent


def parent_view(parent):
    fields = dict(vars(parent))
    fields.update(calculate=parent.calculate, state=parent.state, residual=parent.residual,
                  conditional_frequency=parent.conditional_frequency)
    return SimpleNamespace(**fields)


def context_smoke():
    began = time.monotonic(); sr.alarm(45.)
    d, entry, saved, meta, models = load(); checks = []
    for arm in ARMS:
        reference = np.asarray(r.read(OLD / CASE / 'center' / (arm + '_parent.json'))['phase_reference'])
        parent = r.build(d, arm, reference)
        target = Target(d, parent_view(parent), entry, models)
        comp = target.component(tuple(meta['common_x']))
        archived = old.arrays(OLD / CASE / 'center' / (arm + '_background.npz'))
        # The actual narrow port must reproduce the archived parent conditional,
        # then exercise the unknown density only with redacted target response.
        errors = {name:float(np.max(np.abs(comp[name] - archived[name]))) for name in ('raw', 'covariance', 'q')}
        if max(errors.values()) > 1e-6:
            raise ValueError('actual conditional port does not replay: ' + repr(errors))
        null = k.null_score(dict(comp, raw=np.zeros_like(comp['raw'])), np.arange(20))
        gate = source_gate(d, parent, meta['common_x'], entry)
        if gate['original_growth_supported'] or gate['original_target_active_points']:
            raise ValueError('unexpected source eligibility; policy must be reconsidered before freeze')
        before = dict(parent.calculate(meta['common_x']))
        residual_before = np.asarray(parent.residual(meta['common_x'])).copy()
        attach(parent, SimpleNamespace(score=lambda position,method:dict(objective=7.)), 'hard')
        after = parent.calculate(meta['common_x'])
        scalar_delta = float(parent.residual(meta['common_x']) @ parent.residual(meta['common_x']) - residual_before @ residual_before)
        if abs(after['negative_twice_elbo']-before['negative_twice_elbo']-7.)>1e-8 or abs(scalar_delta-7.)>1e-8:
            raise ValueError('real parent scalar objective/normalization increment failed')
        if d['entries'] and 'linear_predictive_objective' not in before:
            raise ValueError('full original curved+existing predictive parent factor required')
        checks.append(dict(arm=arm, exact20_native_IDs=entry['observation_ids'], errors=errors,
            redacted_unknown_objective=null['objective'], source_gate=gate,
            parent_phase_reference=reference, all8_absent_active=True, cavity_removed_IDs=[],
            full_parent_includes_existing_predictive=True, original_predictive_points=sum(row['points'] for row in d['entries']),
            scalar_residual_increment=scalar_delta, full_ELBO_increment=after['negative_twice_elbo']-before['negative_twice_elbo']))
    signal.setitimer(signal.ITIMER_REAL, 0)
    write('load_smoke04.json', dict(all_passed=True, checks=checks, seconds=time.monotonic()-began,
        source_sha256=r.sha(__file__), actual_target_density_evaluations=0))
    print('SMOKE', r.read(HERE/'load_smoke04.json')['seconds'], flush=True)


def freeze():
    inputs = dict(r.read(OLD/'protocol02.json')['source_input_hashes'])
    own_inputs=list(HERE.glob('*.py'))+list(HERE.glob('*.md'))+list(HERE.glob('load_smoke*.json'))+list(HERE.glob('test_receipt*.json'))
    own_inputs += [HERE/'prefreeze_failure_accounting.json', ROOT/'COORDINATOR_PLAN.md', OLD/'RF_seal.json', OLD/CASE/'execution.json',
        Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')/CASE/'parent.json']
    for path in own_inputs:
        inputs[str(path)] = r.sha(path)
    for arm in ARMS:
        for probe in ('minus', 'center', 'plus'):
            for suffix in ('_parent.json', '_background.npz', '_summary.json'):
                path = OLD/CASE/probe/(arm+suffix); inputs[str(path)] = r.sha(path)
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and path.endswith('.py') and (path.startswith(str(r.REPO)) or path.startswith('/srv/bulk/leo/research/')):
            inputs[path] = r.sha(path)
    charges=list(HERE.glob('load_smoke*.json'))+list(HERE.glob('test_receipt*.json'))+[HERE/'prefreeze_failure_accounting.json']
    spent = sum(r.read(path)['seconds'] for path in charges)
    write('protocol.json', dict(source_input_hashes=inputs, case=CASE, arms=ARMS, methods=METHODS,
        total_worker_seconds=600, preparation_seconds=spent, arm_worker_seconds=(600-spent)/2,
        per_method_fit_seconds=60, workers=2, BLAS_threads=1,
        parent_fit='original5roundsx48boundedGN,zero2Dstartandphasereference,clipreferencesonlybetweenrounds; no target coefficient/Gamma update',
        target_rule='fixedGL16everyoriginalnominal+modeinterpolationpiece,full[-15,15]originalStudentnormalization,LOSzero; all8+unknown',
        initial_controls='all3oldprobes/botharms:GL16vsoldpoint<=1e-3,and32/64reference<=1e-3; delta-secantinsideoldboundedinterval',
        endpoint_checks='GL16/32/64targetatrawendpointand±.01kmaxes,score<=1e-3,FDgradient<=1e-3objective/km; qualificationfailure preserved no rescue',
        target_law='samewhole20IDs,original8causalidentities,fullphase-dependent3modes,9uniformaliases,one300Hzconstant,sharedparentradio+oldpredictiveconditional',
        primary_mixture='physicalmass.5uniformover8;properfixedgraphfrequencydegree4unknownmass.5; no tuning',
        operational_policy='always exact original reference: source lacks accepted curved family/two RX-channel owners; rawfits remain unqualified',
        qualification='originalparentpairedresidual/phase/Gamma+completeoriginalacceptedIDpreservation; originalsourceprofile/conditional/support and owner checks unchanged; evidence never identity/support',
        no_addition_reproduction='endpointnorm<=.001km; originalFULLparentELBOabsolute<=1e-3ANDrelative<=1e-8; savedsame-referenceobjectiveexactreplay<=1e-8; failure means unqualified comparison, no rescue',
        GPS_before_RF_seal=False, position_fits=6, scientific_retries=0, candidate_changes=0, source_point_changes=0))
    print('FROZEN', r.sha(HERE/'protocol.json'), flush=True)


def verify():
    protocol = r.read(HERE/'protocol.json')
    for path, digest in protocol['source_input_hashes'].items():
        if r.sha(path) != digest:
            raise ValueError('frozen input/source changed: ' + path)
    receipt = r.read(ROOT/'audit/preflight.json')
    if receipt.get('all_passed') is not True or receipt.get('protocol_sha256') != r.sha(HERE/'protocol.json'):
        raise ValueError('exact independent preflight required')
    return protocol


def initial_replay(d, entry, models, arm):
    rows = []
    for probe in ('minus', 'center', 'plus'):
        meta = r.read(OLD/'prepared'/CASE/'metadata.json'); x = np.asarray(meta['probes'][probe])
        reference = r.read(OLD/CASE/probe/(arm+'_parent.json'))['phase_reference']
        parent = r.build(d, arm, reference); target = Target(d, parent_view(parent), entry, models)
        original = r.read(OLD/CASE/probe/(arm+'_summary.json'))
        for method in ('hard', 'mixture'):
            scores = {str(order):target.score(tuple(x), method, order) for order in (16, 32, 64)}
            oldscore = original['hard']['objective'] if method == 'hard' else original['mixture']['0.5']['objective']
            error = max(abs(scores[n]['objective'] - oldscore) for n in scores)
            if error > 1e-3:
                raise ValueError('original probe/numerical reproduction failed')
            rows.append(dict(probe=probe, method=method, order_objectives={n:score['objective'] for n,score in scores.items()},
                old_objective=oldscore, maximum_error=error))
    by = {(row['probe'],row['method']):row['order_objectives']['16'] for row in rows}
    secant = ((by['plus','mixture']-by['plus','hard'])-(by['minus','mixture']-by['minus','hard']))/.2
    oldcase = r.read(OLD/CASE/'execution.json')
    interval = next(row['delta_finite_difference_interval'] for row in oldcase['contrasts'] if row['arm']==arm and row['weight']==.5)
    if not interval[0] <= secant <= interval[1]:
        raise ValueError('new deterministic secant outside archived conservative interval')
    write(Path(arm)/'initial_replay.json',dict(passed=True,rows=rows,delta_secant=secant,old_interval=interval))


def endpoint_numerics(target, method, x):
    if method == 'no_addition':
        return dict(passed=True, target_factor_absent=True)
    positions = [x, x+np.array([.01,0]), x-np.array([.01,0]), x+np.array([0,.01]), x-np.array([0,.01])]
    rows = [{str(n):target.score(tuple(position),method,n)['objective'] for n in (16,32,64)} for position in positions]
    gradients = {str(n):np.array([(rows[1][str(n)]-rows[2][str(n)])/.02,(rows[3][str(n)]-rows[4][str(n)])/.02]) for n in (16,32,64)}
    score_error = max(abs(row['16']-row['64']) for row in rows)
    reference_error = max(abs(row['32']-row['64']) for row in rows)
    gradient_error = max(np.max(abs(gradients['16']-gradients['64'])),np.max(abs(gradients['32']-gradients['64'])))
    return dict(passed=bool(score_error<=1e-3 and reference_error<=1e-3 and gradient_error<=1e-3),
        positions=positions,rows=rows,gradients=gradients,maximum_score_error=score_error,
        reference_error=reference_error,maximum_gradient_error=gradient_error,
        qualification='point quadrature stability, not global evidence certification')


def control_reproduction(endpoint, objective, saved, same_reference_delta):
    distance=float(np.linalg.norm(np.asarray(endpoint)-saved['endpoint_east_north_km']))
    delta=float(objective-saved['negative_twice_elbo'])
    relative=abs(delta)/max(1.,abs(saved['negative_twice_elbo']))
    return dict(passed=bool(distance<=.001 and abs(delta)<=1e-3 and relative<=1e-8 and abs(same_reference_delta)<=1e-8),
        endpoint_difference_km=distance, full_parent_ELBO_difference=delta, relative_ELBO_difference=relative,
        saved_same_reference_objective_difference=same_reference_delta, endpoint_tolerance_km=.001,
        objective_absolute_tolerance=1e-3,objective_relative_tolerance=1e-8,same_reference_tolerance=1e-8)


def fit_method(d, entry, models, arm, method, deadline):
    began=time.monotonic(); sr.alarm(min(FIT_SECONDS,deadline-began))
    reference=np.zeros(len(d['means'])); x=np.zeros(2); history=[]
    for epoch in range(5):
        parent=r.build(d,arm,reference)
        untouched=parent_view(parent)
        target=Target(d,untouched,entry,models) if method!='no_addition' else None
        problem=attach(parent,target,method)
        result=fit(problem,x,iterations=48);x=np.asarray(result['parameters'])
        phase=problem.state(x)['phases'][problem.labels]
        change=float(np.max(abs(np.clip(phase,-15,15)-reference)))
        history.append(dict(epoch=epoch,fit=result,reference=reference,unclipped_posterior_phase=phase,phase_change_s=change))
        write(Path(arm)/method/f'epoch{epoch}.json',history[-1])
        reference=np.clip(phase,-15,15)
    raw=dict(arm=arm,method=method,status='fit_complete',endpoint_east_north_km=x,history=history,
        final_phase_change_s=change,parent_phase_reference=problem.reference,
        parent_negative_twice_elbo=untouched.calculate(x)['negative_twice_elbo'],
        target_prediction=target.score(tuple(x),method) if target else None,
        scientific_fit_seconds=time.monotonic()-began,operational_policy='original_reference',target_association_qualified=False)
    write(Path(arm)/method/'raw_endpoint.json',raw)
    sr.alarm(deadline-time.monotonic())
    numerics=endpoint_numerics(target,method,x)
    write(Path(arm)/method/'numerical_qualification.json',numerics)
    parent_summary=summary(untouched,x,d['entries'])
    parent_summary['final_phase_change_s']=change
    parent_valid=bool(r.valid({a:parent_summary for a in ARMS}))
    c=untouched.calculate(x)
    member=r.membership(d,arm,dict(endpoint_east_north_km=x,phase_reference=problem.reference,
        negative_twice_elbo=c['negative_twice_elbo']))
    original=r.read(Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')/CASE/'parent.json')['coverage'][arm]
    lost=sorted(set(original['accepted_observation_ids'])-set(member['accepted_observation_ids']))
    gates=dict(parent_original_valid=parent_valid,maximum_unclipped_phase_s=float(np.max(abs(parent_summary['state']['phases']))),
        final_phase_change_s=change,final_log_precision_change=float(c['final_log_precision_change']),
        Gamma_converged=bool(c['final_log_precision_change']<=1e-5),parent_summary=parent_summary,
        membership=member,original_accepted_IDs_lost=lost,source=source_gate(d,untouched,x,entry),
        source_association_qualified=False,operational_policy='original_reference')
    if method=='no_addition':
        saved=d['arms'][arm]
        reference_parent=r.build(d,arm,saved['phase_reference'])
        replay_delta=float(reference_parent.calculate(saved['endpoint_east_north_km'])['negative_twice_elbo']-saved['negative_twice_elbo'])
        gates['original_reference_reproduction']=control_reproduction(x,c['negative_twice_elbo'],saved,replay_delta)
    write(Path(arm)/method/'gates.json',gates)
    return dict(arm=arm,method=method,status='complete',numerically_stable=numerics['passed'],
        endpoint_east_north_km=x,parent_valid=parent_valid,Gamma_converged=gates['Gamma_converged'],
        full_original_IDs_preserved=not lost,source_growth_supported=gates['source']['original_growth_supported'],
        original_reference_reproduction=gates.get('original_reference_reproduction'),
        operational_policy='original_reference',seconds=time.monotonic()-began)


def arm_job(arm, seconds):
    began=time.monotonic();deadline=began+seconds;rows=[]
    try:
        sr.alarm(deadline-time.monotonic());d,entry,saved,meta,models=load()
        initial_replay(d,entry,models,arm)
        print(arm,'initial RF replay passed',flush=True)
        for method in METHODS:
            try:
                result=fit_method(d,entry,models,arm,method,deadline)
            except Exception as exc:
                result=dict(arm=arm,method=method,status='failed_or_budget_limited',error=repr(exc),traceback=traceback.format_exc(),
                    raw_endpoint_available=(HERE/arm/method/'raw_endpoint.json').exists(),operational_policy='original_reference')
            rows.append(result);write(Path(arm)/(method+'_result.json'),result)
            print(arm,method,result['status'],flush=True)
            sr.alarm(deadline-time.monotonic())
        result=dict(arm=arm,status='terminal',rows=rows,seconds=time.monotonic()-began)
    except Exception as exc:
        result=dict(arm=arm,status='failed_or_budget_limited',rows=rows,error=repr(exc),traceback=traceback.format_exc(),seconds=time.monotonic()-began)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
    write(Path(arm)/'execution.json',result)
    return result


def run():
    protocol=verify();results=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(arm_job,arm,protocol['arm_worker_seconds']):arm for arm in ARMS}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(arm=futures[future],status='worker_failed',error=repr(exc),seconds=protocol['arm_worker_seconds']))
    slots=[]
    for arm in ARMS:
        for method in METHODS:
            path=HERE/arm/(method+'_result.json')
            slots.append(r.read(path) if path.exists() else dict(arm=arm,method=method,status='not_completed',operational_policy='original_reference'))
    write('execution.json',dict(arms=results,all6_slots=slots,all_selected_terminal=True,
        cumulative_scientific_seconds=protocol['preparation_seconds']+sum(row['seconds'] for row in results),
        cap_seconds=600,DS24_0012='unresolved in previous pilot, not rerun',GPS_used=False,operational_policy='original_reference'))
    files={str(path):r.sha(path) for path in HERE.rglob('*') if path.is_file() and '.pytest_cache' not in str(path) and '__pycache__' not in str(path)}
    write('RF_seal.json',dict(files=files,protocol_sha256=r.sha(HERE/'protocol.json'),all_selected_terminal=True,GPS_used=False))
    print('TERMINAL',r.read(HERE/'execution.json')['cumulative_scientific_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['smoke','freeze','run']);args=parser.parse_args()
    {'smoke':context_smoke,'freeze':freeze,'run':run}[args.action]()
