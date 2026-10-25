"""Qualify a new orbital-geometry phase covariance before any RF position fit."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from sgp4.api import Satrec

from ds23_geometry_phase_covariance import orbital_features, qualify
from leo.sky.frames import julian_day_from_utc_ns
from probe_ds23_neighbor_phase_prior import inputs
from run_algo01_ds23_sample import ROOT, read, sha, write

OUT = ROOT/'reports/2026_10_22_ds23_geometry_phase_covariance'
COHORT = ROOT/'reports/2026_10_22_ds23_soft_predictive_identity/protocol.json'


def attach_states(rows, history):
    cutoff = history['cutoff_utc_ns']
    lookup = {}
    for number, versions in history['past_versions'].items():
        if any(max(v['epoch'], v['collected_utc_ns']) > cutoff for v in versions):
            raise ValueError('post-observation history forbidden')
        for a, b, c in zip(versions[:-2], versions[1:-1], versions[2:]):
            if not (a['epoch'] < b['epoch'] < c['epoch'] <= c['collected_utc_ns'] and
                    a['collected_utc_ns'] <= b['collected_utc_ns'] <= c['collected_utc_ns'] and
                    b['epoch']-a['epoch'] >= 1_000_000_000):
                continue
            key = int(number), c['collected_utc_ns']
            if key in lookup:
                raise ValueError('ambiguous satellite update identity')
            lookup[key] = b
    result = []
    for row in rows:
        b = lookup[row['norad'], row['validation_time_ns']]
        if row['validation_time_ns'] > cutoff or b['collected_utc_ns'] > row['validation_time_ns']:
            raise ValueError('noncausal transition geometry')
        age = (row['validation_time_ns']-b['epoch'])/1e9
        if not np.isclose(age, row['age_s'], rtol=0., atol=1e-6):
            raise ValueError('history forecast binding failed')
        jd, fr = julian_day_from_utc_ns(np.array([row['validation_time_ns']], dtype=np.int64))
        err, position, velocity = Satrec.twoline2rv(*b['lines']).sgp4(float(jd[0]), float(fr[0]))
        if err:
            raise ValueError('nominal forecast state propagation failed')
        result.append(dict(row, forecast_publication_ns=b['collected_utc_ns'],
                           **orbital_features(position, velocity)))
    return result


def run(case):
    path = OUT/(case+'.json')
    if path.exists():
        saved = read(path)
        if saved['source_sha256'] != sha(Path(__file__)) or saved['helper_sha256'] != sha(ROOT/'tools/ds23_geometry_phase_covariance.py'):
            raise ValueError('preserve original evidence; source changed')
        return saved
    hp, fp, raw, forecast, _, full, location = inputs(case)
    rows = attach_states(forecast['transitions'], raw)
    selection = qualify(rows, forecast['temporal_split_boundary_ns'], full, location if location['qualified'] else {})
    result = dict(case=case, selection=selection, transitions=len(rows),
                  satellites=len({r['norad'] for r in rows}),
                  validation_events=len({r['validation_time_ns'] for r in rows}),
                  forecast_age_hours_quantiles=np.quantile([r['age_s']/3600 for r in rows], [.1, .5, .9]),
                  history_path=str(hp), forecast_path=str(fp), history_sha256=sha(hp), forecast_sha256=sha(fp),
                  full_incumbent_marginal_model=full, full_incumbent_location=location,
                  no_current_RF_satellite_nomination_loaded=True, no_GPS_or_RF_input=True,
                  features_use_nominal_forecast_TLE_only_at_its_historical_validation_time=True,
                  simultaneous_validation_events_can_contain_different_nominal_publications=True,
                  TLE_innovations_are_imperfect_orbit_error_proxies=True,
                  source_sha256=sha(Path(__file__)), helper_sha256=sha(ROOT/'tools/ds23_geometry_phase_covariance.py'))
    write(path, result)
    print(case, 'qualified', selection['qualified'], 'prefix',
          selection.get('prefix_selection', {}).get('kind'), selection.get('prefix_selection', {}).get('rho'),
          'held gains', selection.get('validation', {}).get('satellite_disjoint', {}).get('gains'), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    cohort = read(COHORT)
    cases = cohort['engineering']+cohort['random20']
    OUT.mkdir(exist_ok=True)
    protocol = dict(engineering=cohort['engineering'], random20=cohort['random20'],
                    original_cohort_seed=cohort['seed'], cohort_sha256=sha(COHORT),
                    hypothesis='Cross-satellite phase errors depend on orbital plane and orbital phase',
                    kernels=['unit orbit normal', 'concatenated unit radial and velocity vectors divided by sqrt(2)'],
                    covariance='(1-rho)I + rho F F.T; unit diagonal; PSD; negative correlations allowed',
                    distribution='Variance-parameterized elliptical multivariate Student; original univariate marginals',
                    rho_grid=[0., .01, .03, .1, .3, .6, .8],
                    controls=['independent Student', 'common Gamma with identity covariance',
                              'previous publication-event independent Student rotation',
                              'common Gamma with fitted exchangeable covariance'],
                    training='earlier validation-update batches, NORAD mod 5 != 0; marginal/location refitted on training only',
                    validation='later whole update batches, and later NORAD mod 5 == 0 batches',
                    qualification='training and both validations must beat every fixed training-fit control by log N + 2 log 2',
                    minimum_event_size=5, minimum_train_events=3, minimum_validation_events=2,
                    no_RF_GPS_or_post_observation_TLE_input=True, no_position_fits_until_qualification=True,
                    unchanged_current_incumbent_marginal_scales_and_means_for_any_later_RF_fit=True,
                    previous_exchangeable_publication_experiment_is_an_explicit_control=True,
                    not_untouched_scans_or_new_location_validation=True,
                    density_reference='https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.multivariate_t.html',
                    workers=args.workers,
                    source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_geometry_phase_covariance.py']})
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('frozen protocol changed')
    if not target.exists():
        write(target, protocol)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = [f.result() for f in as_completed([pool.submit(run, case) for case in cases])]
    write(OUT/'qualification.json', dict(all_terminal=True, cases=len(results),
                                       qualified=sum(r['selection']['qualified'] for r in results),
                                       rows=[dict(case=r['case'], selection=r['selection']) for r in results]))


if __name__ == '__main__':
    main()
