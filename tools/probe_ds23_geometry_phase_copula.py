"""Test geometry-only dependence without sharing heavy-tail precision."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from ds23_geometry_phase_copula import qualify
from probe_ds23_geometry_phase_covariance import OUT as ORIGINAL, attach_states
from probe_ds23_neighbor_phase_prior import inputs
from run_algo01_ds23_sample import ROOT, read, sha, write

OUT = ORIGINAL/'copula'


def run(case):
    path = OUT/(case+'.json')
    if path.exists():
        raise FileExistsError('preserve sealed copula evidence')
    original = ORIGINAL/(case+'.json')
    prior = read(original)
    hp, fp, history, forecast, _, full, location = inputs(case)
    if sha(hp) != prior['history_sha256'] or sha(fp) != prior['forecast_sha256']:
        raise ValueError('history inputs changed')
    selection = qualify(attach_states(forecast['transitions'], history),
                        forecast['temporal_split_boundary_ns'], prior['selection'], full,
                        location if location['qualified'] else {})
    result = dict(case=case, selection=selection, original_training_result_sha256=sha(original),
                  history_sha256=sha(hp), forecast_sha256=sha(fp),
                  source_sha256=sha(Path(__file__)), helper_sha256=sha(ROOT/'tools/ds23_geometry_phase_copula.py'),
                  no_RF_GPS_or_post_observation_TLE_input=True)
    write(path, result)
    print(case, 'copula qualified', selection['qualified'], 'prefix',
          selection.get('prefix_selection', {}).get('kind'), selection.get('prefix_selection', {}).get('rho'),
          'held', selection.get('validation', {}).get('satellite_disjoint', {}).get('gains'), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    previous = read(ORIGINAL/'protocol.json')
    cases = previous['engineering']+previous['random20']
    OUT.mkdir(exist_ok=True)
    protocol = dict(engineering=previous['engineering'], random20=previous['random20'],
                    original_cohort_seed=previous['original_cohort_seed'],
                    original_protocol_sha256=sha(ORIGINAL/'protocol.json'),
                    geometry_marginal_parameters_and_temporal_satellite_splits_unchanged=True,
                    distribution='Gaussian copula applied to original univariate Student CDFs',
                    controls=['independent Student', 'fitted previous publication covariance', 'fitted global Gaussian copula'],
                    selection='training-fit kernel and rho; training/later/satellite-disjoint gains must each exceed log N + 2 log 2 against every control',
                    pure_dependence_extension_avoids_elliptical_shared_Gamma=True,
                    no_RF_GPS_or_post_observation_TLE_used=True, no_position_fits_until_qualified=True,
                    runtime_requires_exact_matching_nonlinear_copula_prior=True,
                    literature='https://www.statsmodels.org/stable/generated/statsmodels.distributions.copula.api.GaussianCopula.html',
                    workers=args.workers,
                    source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_geometry_phase_copula.py']})
    if (OUT/'protocol.json').exists():
        raise FileExistsError('preserve frozen protocol')
    write(OUT/'protocol.json', protocol)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = [f.result() for f in as_completed([pool.submit(run, case) for case in cases])]
    write(OUT/'qualification.json', dict(all_terminal=True, cases=len(results),
                                       qualified=sum(r['selection']['qualified'] for r in results),
                                       rows=[dict(case=r['case'], selection=r['selection']) for r in results]))


if __name__ == '__main__':
    main()
