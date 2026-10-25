"""Bounded causal-only test of one scale-preserving phase/shape correlation.

All orbit coordinates are projected in the current engine's physical state
basis. No RF observations, satellite associations or geographic truth enter
the forecast learner. Later historical TLEs are prediction proxies, not truth.
"""
from concurrent.futures import ProcessPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from sgp4.api import Satrec

from ds23_causal_phase_location import fit_location, predict
from ds23_joint_orbit_prior import correlation_fit, nll
from fit_s01_69333_tle_parameter import perturb
from learn_ds23_causal_phase_forecast import select_distribution, transition as legacy_transition
from prototype_dsx01_mean_motion import reference_motion_satellite
from leo.sky.frames import greenwich_mean_sidereal_time_rad, julian_day_from_utc_ns, teme_to_ecef
from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S

OUT = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
CASES = json.loads(Path('/srv/bulk/leo/research/ds24-channel-halves-20261024/summary.json').read_text())['baseline']['fitted_c']['common_cases']
SEED = 2026102501
SAMPLE_SATELLITES = 1024
FOLDS = 4
BLOCK_NS = int(6*3600e9)
TIMES = np.array([0., 150., 300.])
SHRINKAGE = .5


def encode(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=encode)+'\n')


def digest(version):
    return hashlib.sha256('\n'.join(version['lines']).encode()).hexdigest()


def phase_sigma(old_phase, age, gap):
    return float(np.clip(np.hypot(1., old_phase*age/gap), 1., 15.))


def ecef(satellite, origin, times=TIMES):
    utc = np.asarray(origin+np.rint(np.asarray(times)*1e9), np.int64)
    jd, fr = julian_day_from_utc_ns(utc)
    error, p, v = satellite.sgp4_array(jd, fr)
    if np.any(error):
        raise ValueError('SGP4 propagation failed')
    p, v = teme_to_ecef(p[None], v[None], greenwich_mean_sidereal_time_rad(jd, fr))
    return p[0], v[0]


def shifted(satellite, origin, phase, times=TIMES):
    p, v = ecef(satellite, origin, np.asarray(times)+phase)
    angle = EARTH_ROTATION_RAD_S*phase
    cosine, sine = np.cos(angle), np.sin(angle)
    for value in (p, v):
        xx, yy = value[:, 0].copy(), value[:, 1].copy()
        value[:, 0] = cosine*xx-sine*yy
        value[:, 1] = sine*xx+cosine*yy
    return p, v


def stack(p, v):
    return np.r_[np.asarray(p).ravel(), 150*np.asarray(v).ravel()]


def physical_basis(previous, nominal, origin):
    """Mirror build_modes/previous_bank at 0/150/300 s, in physical units.

    First column is one second of orbital phase. Remaining columns are one
    current-engine prior SD each, with reference-aligned mean motion and
    inclination/RAAN parameter perturbations. Position/velocity state rows use
    the predeclared 150 s velocity scaling and no site geometry.
    """
    sa, sb = (Satrec.twoline2rv(*v['lines']) for v in (previous, nominal))
    pn, vn = ecef(sb, origin)
    po, _ = ecef(sa, origin)
    vi = vn.copy()
    vi[:, 0] -= EARTH_ROTATION_RAD_S*pn[:, 1]
    vi[:, 1] += EARTH_ROTATION_RAD_S*pn[:, 0]
    old_phase = float(np.median(np.sum((po-pn)*vi, axis=1)/np.sum(vi*vi, axis=1)))
    po, _ = shifted(sa, origin, -old_phase)
    radial = pn/np.linalg.norm(pn, axis=1)[:, None]
    normal = np.cross(pn, vi)
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    sr = max(.05, float(np.median(abs(np.sum((po-pn)*radial, axis=1)))))
    sn = max(.025, float(np.median(abs(np.sum((po-pn)*normal, axis=1)))))
    radius = float(np.mean(np.linalg.norm(pn, axis=1)))
    motion = sb.no_kozai*1440/(2*np.pi)
    sigma_motion = 1.5*motion/radius*sr
    angular = np.rad2deg(sn/radius)
    scales = [sigma_motion, angular, angular/max(abs(np.sin(sb.inclo)), .1)]
    pp, vp = shifted(sb, origin, .01)
    pm, vm = shifted(sb, origin, -.01)
    columns = [stack((pp-pm)/.02, (vp-vm)/.02)]
    elapsed = ((origin/1e9+150)/86400+2440587.5-sb.jdsatepoch-sb.jdsatepochF)
    for index, parameter in enumerate(('mean_motion_rev_day', 'inclination_deg', 'raan_deg')):
        satellites = [reference_motion_satellite(sb, step, elapsed) if index==0 else perturb(sb, parameter, step)
            for step in (.001, -.001)]
        plus_p, plus_v = ecef(satellites[0], origin)
        minus_p, minus_v = ecef(satellites[1], origin)
        columns.append(stack((plus_p-minus_p)/.002*scales[index], (plus_v-minus_v)/.002*scales[index]))
    gap = (nominal['epoch']-previous['epoch'])/1e9
    age = (origin-nominal['epoch'])/1e9
    return dict(design=np.column_stack(columns), nominal_position=pn, nominal_velocity=vn,
        old_phase_s=old_phase, phase_sigma_s=phase_sigma(old_phase, age, gap),
        unit_forecast_s=float(-np.clip((age+150)/gap, 0, 2)*old_phase), age_s=age+150,
        physical_parameter_sigma=scales, radial_sigma_km=sr, cross_sigma_km=sn)


def project_job(job):
    number, trio, source_cases = job
    a, b, c = trio
    timestamp = c['collected_utc_ns']
    if not (a['collected_utc_ns']<=b['collected_utc_ns']<timestamp and a['epoch']<b['epoch']<c['epoch']<=timestamp):
        return dict(rejected='noncausal_or_unordered')
    if b['epoch']-a['epoch']<1e9:
        return dict(rejected='epoch_gap_under_1s')
    try:
        basis = physical_basis(a, b, timestamp)
        target = Satrec.twoline2rv(*c['lines'])
        pc, vc = ecef(target, timestamp)
        y = stack(pc-basis['nominal_position'], vc-basis['nominal_velocity'])
        coordinate, _, rank, singular = np.linalg.lstsq(basis['design'], y, rcond=1e-10)
        residual = y-basis['design']@coordinate
        legacy = legacy_transition(a, b, c)
        if legacy is None or not np.isfinite(np.r_[coordinate, singular, residual]).all():
            return dict(rejected='nonfinite_or_legacy_invalid')
        return dict(norad=number, validation_time_ns=timestamp, source_cases=source_cases,
            endpoints=[digest(v) for v in trio], version_epochs=[v['epoch'] for v in trio],
            source_available_ns=[v['collected_utc_ns'] for v in trio],
            coordinates_phase_seconds_shape_prior_SD=coordinate,
            unexplained_state_energy_fraction=float((residual@residual)/max(y@y, 1e-30)),
            state_design_rank=int(rank), state_design_condition=float(singular[0]/singular[-1]),
            phase_projection_minus_legacy_s=float(coordinate[0]-legacy['next_innovation_s']),
            engine_features=dict(predicted_sigma_s=basis['phase_sigma_s'],
                unit_forecast_s=basis['unit_forecast_s'], age_s=basis['age_s']),
            physical_parameter_sigma=basis['physical_parameter_sigma'],
            old_phase_s=basis['old_phase_s'], legacy=legacy)
    except (ValueError, np.linalg.LinAlgError) as error:
        return dict(rejected=type(error).__name__+': '+str(error))


def inventory():
    unique = {}
    source_receipts = []
    for case in CASES:
        path = SOURCE/'causal_phase_history'/(case+'.json')
        history = json.loads(path.read_text())
        cutoff = history['cutoff_utc_ns']
        assert history['no_following_TLE_or_GPS']
        source_receipts.append(dict(case=case, cutoff_utc_ns=cutoff,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for number, versions in history['past_versions'].items():
            assert all(v['epoch']<=cutoff and v['collected_utc_ns']<=cutoff for v in versions)
            for k in range(2, len(versions)):
                trio = versions[k-2:k+1]
                if trio[-1]['collected_utc_ns']+300_000_000_000>cutoff:
                    continue
                key = (int(number), *(digest(v) for v in trio))
                if key not in unique:
                    unique[key] = [int(number), trio, []]
                unique[key][2].append(case)
                # Preserve the earliest receipted availability for identical
                # version bytes; it is never inferred from the TLE epoch.
                for index in range(3):
                    if trio[index]['collected_utc_ns']<unique[key][1][index]['collected_utc_ns']:
                        unique[key][1][index] = trio[index]
    numbers = sorted({key[0] for key in unique})
    rng = np.random.default_rng(SEED)
    sample = set(map(int, rng.choice(numbers, size=min(SAMPLE_SATELLITES, len(numbers)), replace=False)))
    jobs = [job for key, job in sorted(unique.items()) if key[0] in sample]
    receipt = dict(union_satellites=len(numbers), unique_triples=len(unique),
        sampled_satellites=sorted(sample), sampled_triples=len(jobs), source_receipts=source_receipts)
    return jobs, receipt


def fit_baseline(rows):
    # All baseline hyperparameters and mean-feature selection are trained here,
    # not borrowed from the published model that saw heldout historical labels.
    legacy = [r['legacy'] for r in rows]
    model = select_distribution(legacy)
    location = fit_location(legacy, model)
    return model, location


def standardized(rows, model, location):
    mean = predict([r['engine_features'] for r in rows], model, location['kind'], location['coefficient'])
    phase = (np.array([r['coordinates_phase_seconds_shape_prior_SD'][0] for r in rows])-mean)/(
        np.array([r['engine_features']['predicted_sigma_s'] for r in rows])*model['multiplier'])
    return np.column_stack((phase, np.array([r['coordinates_phase_seconds_shape_prior_SD'][1:] for r in rows])))


def safe_training(rows, test, scheme, fold, block, satellite_folds, time_folds):
    start = block*BLOCK_NS
    forbidden = {(r['norad'], endpoint) for r in test for endpoint in r['endpoints']}
    selected = []
    purged = 0
    for row in rows:
        # Prequential restriction is enforced inside randomized groups.
        if row['validation_time_ns']>=start:
            continue
        row_block = row['validation_time_ns']//BLOCK_NS
        if scheme=='satellite' and satellite_folds[row['norad']]==fold:
            continue
        if scheme=='time_block' and time_folds[row_block]==fold:
            continue
        if any((row['norad'], endpoint) in forbidden for endpoint in row['endpoints']):
            purged += 1
            continue
        selected.append(row)
    return selected, purged


def bootstrap_groups(records, key, seed):
    grouped = {}
    for row in records:
        grouped.setdefault(row[key], []).append(row['gain'])
    means = np.array([np.mean(v) for v in grouped.values()])
    rng = np.random.default_rng(seed)
    sampled = rng.choice(means, size=(2000, len(means)), replace=True).mean(axis=1)
    return dict(groups=len(means), mean_group_gain=float(means.mean()),
        confidence_interval_mean_group_gain=np.quantile(sampled, [.025, .975]),
        bootstrap_is_descriptive_group_resampling_not_independent_orbit_truth=True)


def validate(rows):
    numbers = sorted({r['norad'] for r in rows})
    blocks = sorted({r['validation_time_ns']//BLOCK_NS for r in rows})
    rng = np.random.default_rng(SEED+1)
    satellite_folds = dict(zip(numbers, map(int, rng.integers(FOLDS, size=len(numbers)))))
    time_folds = dict(zip(blocks, map(int, rng.integers(FOLDS, size=len(blocks)))))
    write(OUT/'groups.json', dict(seed=SEED+1, satellite_folds=satellite_folds, publication_block_folds=time_folds,
        block_seconds=BLOCK_NS/1e9, causal_training_restriction='earlier publication blocks only'))
    results = {}
    for scheme in ('satellite', 'time_block'):
        folds, scores = [], []
        for block in blocks:
            block_rows = [r for r in rows if r['validation_time_ns']//BLOCK_NS==block]
            group_ids = sorted({satellite_folds[r['norad']] for r in block_rows}) if scheme=='satellite' else [time_folds[block]]
            for fold in group_ids:
                test = [r for r in block_rows if scheme=='time_block' or satellite_folds[r['norad']]==fold]
                train, purged = safe_training(rows, test, scheme, fold, block, satellite_folds, time_folds)
                if len(train)<300 or len({r['norad'] for r in train})<60 or len(test)<10:
                    folds.append(dict(block=int(block), fold=fold, skipped='predeclared minimum training/test evidence',
                        training_rows=len(train), test_rows=len(test), endpoint_overlap_rows_purged=purged))
                    continue
                model, location = fit_baseline(train)
                train_z, test_z = standardized(train, model, location), standardized(test, model, location)
                correlation = (1-SHRINKAGE)*np.eye(4)+SHRINKAGE*correlation_fit(train_z)
                baseline = nll(test_z, np.eye(4), model['nu'])
                alternative = nll(test_z, correlation, model['nu'])
                for r, old, new in zip(test, baseline, alternative, strict=True):
                    scores.append(dict(norad=r['norad'], block=int(block), fold=fold,
                        baseline_negative_twice_log_density=float(old), alternative_negative_twice_log_density=float(new),
                        gain=float(old-new)))
                folds.append(dict(block=int(block), fold=fold, training_rows=len(train), test_rows=len(test),
                    endpoint_overlap_rows_purged=purged, maximum_training_availability_ns=max(r['validation_time_ns'] for r in train),
                    minimum_test_availability_ns=min(r['validation_time_ns'] for r in test),
                    baseline_phase_model=model, baseline_signed_location=location, correlation=correlation,
                    validation_gain=float((baseline-alternative).sum())))
        gains = np.array([r['gain'] for r in scores])
        satellite_ci = bootstrap_groups(scores, 'norad', SEED+2)
        time_ci = bootstrap_groups(scores, 'block', SEED+3)
        gate = bool(gains.sum()>6*np.log(len(gains)) and
            satellite_ci['confidence_interval_mean_group_gain'][0]>0 and
            time_ci['confidence_interval_mean_group_gain'][0]>0)
        results[scheme] = dict(qualified=gate, validation_rows=len(scores), gain=float(gains.sum()),
            mean_gain=float(gains.mean()), median_gain=float(np.median(gains)),
            penalty=6*np.log(len(gains)), satellite_group_bootstrap=satellite_ci, time_block_bootstrap=time_ci,
            folds=folds, scores=scores)
        print(scheme, 'rows', len(scores), 'gain', gains.sum(), 'qualified', gate, flush=True)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--project-only', action='store_true')
    args = parser.parse_args()
    assert 1<=args.workers<=4
    protocol = dict(seed=SEED, sample_satellites=SAMPLE_SATELLITES, alternatives=1,
        alternative='Four-coordinate phase/shape correlation with fixed 0.5 shrinkage toward identity; all marginal scales unchanged',
        workers=args.workers, group_folds=FOLDS, publication_block_seconds=BLOCK_NS/1e9,
        randomized_satellite_and_time_block_groups=True, chronological_split_is_not_primary_validation=True,
        each_prediction_uses_only_earlier_training_blocks=True, shared_TLE_endpoint_purging=True,
        all_preprocessing_and_baseline_phase_location_fitted_on_training_only=True,
        minimum_training_rows=300, minimum_training_satellites=60, minimum_test_rows=10,
        qualification='Both random grouping schemes: gain>6logN and satellite/time-block 95% descriptive cluster-bootstrap lower gain>0; native-basis compatibility and remainder checks also required',
        representation_gate='median unexplained state energy fraction<0.1 and p90<0.5; no rank deficiency',
        input_window='Frozen per-scan causal histories, deduplicated TLE byte triples; target window ends before source scan cutoff',
        no_RF_IQ_GPS_postscan_TLE_or_DS23_frozen_banks=True, no_position_fits_in_this_script=True,
        TLE_updates_are_correlated_prediction_proxies_not_orbit_truth=True)
    if not (OUT/'protocol.json').exists():
        write(OUT/'protocol.json', protocol)
    began = time.monotonic()
    if (OUT/'projected_rows.json').exists():
        projection = json.loads((OUT/'projected_rows.json').read_text())
    else:
        jobs, receipt = inventory()
        write(OUT/'inventory.json', receipt)
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(project_job, jobs, chunksize=16))
        rejected = {}
        rows = []
        for row in results:
            if 'rejected' in row:
                rejected[row['rejected']] = rejected.get(row['rejected'], 0)+1
            else:
                rows.append(row)
        projection = dict(rows=rows, rejected=rejected, elapsed_seconds=time.monotonic()-began)
        write(OUT/'projected_rows.json', projection)
    if not args.project_only:
        validation = validate(projection['rows'])
        fractions = np.array([r['unexplained_state_energy_fraction'] for r in projection['rows']])
        representation = bool(np.median(fractions)<.1 and np.quantile(fractions,.9)<.5 and
            all(r['state_design_rank']==4 for r in projection['rows']))
        result = dict(validation=validation, representation_gate_passed=representation,
            qualified=representation and all(v['qualified'] for v in validation.values()),
            unexplained_energy_median=float(np.median(fractions)), unexplained_energy_p90=float(np.quantile(fractions,.9)),
            elapsed_seconds=time.monotonic()-began, no_position_fit_or_GPS_used=True)
        write(OUT/'validation.json', result)


if __name__=='__main__':
    main()
