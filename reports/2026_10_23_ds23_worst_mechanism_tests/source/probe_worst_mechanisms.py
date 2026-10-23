"""Conditional simulations on frozen outlier sampling; no real-data adoption."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
import argparse
import hashlib
import signal
import time
import traceback
import numpy as np

from probe_ds23_worst_association_bottleneck import setup
from probe_ds23_synthetic_closure import generate
from probe_ds23_synthetic_noise import perturb_tracks, gate_counts
from probe_ds23_synthetic_known_nuisance import fit_known
from ds23_synthetic_known_nuisance import known_problem, attach_known_predictive, COMPONENTS
from ds23_synthetic_phase_law import bounded_phase_draw
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import refit, cached
import probe_ds23_synthetic_nuisance_components as component
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = Path(__file__).resolve().parents[1]
CASES = ('DS23-0081', 'DS23-0326')
SITES = ((-5., 5.), (5., -5.))
ARMS = ('c0', 'fitted_c')
VARIANTS = dict(noise_only=None, all_nuisance=(), known_phase=('phase',),
                known_receiver=('radio', 'smooth'), all_known=COMPONENTS)


def sample_key(site_index, draw):
    if site_index not in range(len(SITES)) or draw not in range(3):
        raise ValueError('outside predeclared simulation grid')
    return 100 * site_index + draw


def observations_digest(scan):
    h = hashlib.sha256()
    for track in scan.tracks:
        h.update(np.asarray(track['values'], dtype='<f8').tobytes())
    return h.hexdigest()


@lru_cache(maxsize=2)
def context(case):
    return setup(case)


def synthetic(d, site_index, draw, variant):
    site, key = SITES[site_index], sample_key(site_index, draw)
    before = observations_digest(d['scan'])
    if variant == 'noise_only':
        scan, node, entries, reconstruction = generate(d['scan'], d['node'], d['base'],
            d['means'], d['entries'], site)
        truth = dict(maximum_forward_alias_reconstruction_error_hz=reconstruction)
    else:
        component.SITE = site
        component.bounded_phase_draw = bounded_phase_draw
        scan, node, entries, truth = component.synthesize(d['scan'], d['node'], d['keep'],
            d['base'], d['powers'], d['means'], d['model'], d['entries'], 'all', key)
    noise = perturb_tracks(scan, set(d['base'].members) | {e['track_index'] for e in entries},
        194729 + 1009 * key + int(scan.case.split('-')[1]))
    if observations_digest(d['scan']) != before:
        raise AssertionError('simulation mutated original observations')
    if truth['maximum_forward_alias_reconstruction_error_hz'] > 1e-7:
        raise AssertionError('alias reconstruction failed')
    return scan, node, entries, truth, noise


def parity(d, scan, node, entries, truth):
    comparisons = []
    for arm in ARMS:
        reference = d['means']
        p = known_problem(scan, node, d['keep'], arm, reference, d['powers'], d['means'], d['model'], truth, ())
        attach_known_predictive(p, entries, d['powers'], truth, ())
        q = make_event_problem(scan, node, d['keep'], arm, reference, d['powers'], d['means'], d['model'], [])
        attach_event_predictive(q, entries, d['powers'])
        for x in ((0., 0.), (4., -3.)):
            a, b = p.calculate(np.array(x)), q.calculate(np.array(x))
            np.testing.assert_array_equal(a['coefficient'], b['coefficient'])
            np.testing.assert_array_equal(a['residual'], b['residual'])
            np.testing.assert_allclose(a['negative_twice_elbo'], b['negative_twice_elbo'], rtol=0, atol=1e-8)
            comparisons.append(dict(arm=arm, position=x, loss_difference=float(a['negative_twice_elbo']-b['negative_twice_elbo'])))
    return comparisons


def run(case, site_index, draw, variant):
    path = OUT/'synthetic'/f'{case}_site{site_index}_draw{draw}_{variant}.json'
    if path.exists():
        return read(path)
    started = time.monotonic()
    record = dict(case=case, site_index=site_index, draw=draw, variant=variant,
        site_east_north_km=SITES[site_index], cold_start_east_north_km=[0., 0.],
        real_GPS_used=False, full_hierarchical_prior_predictive=False,
        oracle_labels_and_aliases=True, known_components=VARIANTS[variant],
        generating_c=0., matched_observations_masks_candidates_priors_budgets_in_c_arms=True)
    def timeout(*_):
        raise TimeoutError('120 second paired simulation cap')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(120)
    try:
        d = context(case)
        scan, node, entries, truth, noise = synthetic(d, site_index, draw, variant)
        if variant == 'all_nuisance' and site_index == draw == 0:
            record['no_knowledge_model_parity'] = parity(d, scan, node, entries, truth)
        pair = {}
        for arm in ARMS:
            if variant in ('noise_only', 'all_nuisance'):
                r = refit(scan, node, d['keep'], arm, d['powers'], d['means'], d['model'], [], entries)
            else:
                r = fit_known(scan, node, d['keep'], arm, d['powers'], d['means'], d['model'], entries, truth, VARIANTS[variant])
            r['synthetic_position_error_km'] = float(np.linalg.norm(np.asarray(r['endpoint_east_north_km']) - SITES[site_index]))
            r['original_gate_counts'] = gate_counts(r)
            r['at_search_boundary'] = bool(np.any(np.isclose(np.abs(r['endpoint_east_north_km']), 12.5)))
            if r['linear_calibration_max_difference'] != 0:
                raise AssertionError('linear tracks changed calibration')
            pair[arm] = r
        record.update(status='complete', arms=pair, paired_qualified=valid(pair), noise=noise,
            generation_truth=truth, synthetic_observations_sha256=observations_digest(scan),
            original_observations_unchanged=True, curved_points=int(d['keep'].sum()),
            predictive_points=sum(e['points'] for e in entries))
    except Exception as exc:
        record.update(status='failed', error=repr(exc), traceback=traceback.format_exc())
    finally:
        signal.alarm(0)
    record['seconds'] = time.monotonic()-started
    write(path, record)
    print(case, site_index, draw, variant, record['status'],
          {a: round(r['synthetic_position_error_km'], 4) for a,r in record.get('arms', {}).items()}, flush=True)
    return record


def protocol():
    sources = [Path(__file__)] + [ROOT/'tools'/s for s in (
        'probe_ds23_worst_association_bottleneck.py', 'probe_ds23_synthetic_closure.py',
        'probe_ds23_synthetic_nuisance_components.py', 'ds23_synthetic_phase_law.py',
        'ds23_synthetic_known_nuisance.py', 'probe_ds23_synthetic_known_nuisance.py')]
    p = dict(cases=CASES, sites=SITES, draws=3, variants=VARIANTS, workers=6,
        paired_job_cap_seconds=120, current_published_sampling_masks_labels_weights=True,
        original_noise_scales_Gaussian_draws=True, corrected_unit_variance_Student_phase=True,
        frozen_cold_start=[0.,0.], phase_rounds=5, position_iterations_per_round=48,
        generating_c=0., source_sha256={str(s):sha(s) for s in sources},
        no_GPS_selection_or_real_data_adoption=True, conditional_simulation_not_association_benchmark=True)
    import json
    p = json.loads(json.dumps(p))
    path = OUT/'synthetic/protocol.json'
    if path.exists() and read(path) != p:
        raise ValueError('frozen protocol changed')
    if not path.exists():
        write(path,p)
    return p


def evaluate():
    rows = [read(p) for p in sorted((OUT/'synthetic').glob('DS23-*.json'))]
    summaries = []
    for case in CASES:
        for variant in VARIANTS:
            complete = [r for r in rows if r['case']==case and r['variant']==variant and r['status']=='complete']
            for arm in ARMS:
                rs = [r['arms'][arm] for r in complete]
                err = [r['synthetic_position_error_km'] for r in rs]
                summaries.append(dict(case=case,variant=variant,arm=arm,n=len(err),
                    mean_error_km=float(np.mean(err)) if err else None,
                    median_error_km=float(np.median(err)) if err else None,
                    max_error_km=max(err) if err else None,
                    boundary_count=sum(r['at_search_boundary'] for r in rs),
                    all_original_gates_pass=sum(r['original_gate_counts']['all_original_gates_pass'] for r in rs)))
    matched = []
    for case in CASES:
        for site in range(2):
            for draw in range(3):
                subset=[r for r in rows if r['case']==case and r['site_index']==site and r['draw']==draw
                        and r['variant']!='noise_only' and r['status']=='complete']
                if subset:
                    assert len({r['synthetic_observations_sha256'] for r in subset})==1
                    matched.append(dict(case=case,site=site,draw=draw,variants=len(subset)))
    write(OUT/'synthetic/evaluation.json',dict(summary=summaries,completed=sum(r['status']=='complete' for r in rows),
        expected=60, failures=[r for r in rows if r['status']!='complete'], matched_common_draw_audits=matched))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args();protocol()
    jobs=[(c,s,d,v) for c in CASES for s in range(2) for d in range(3) for v in VARIANTS]
    if args.preflight:jobs=[(c,0,0,'all_nuisance') for c in CASES]
    with ProcessPoolExecutor(max_workers=min(6,len(jobs))) as pool:
        for f in as_completed([pool.submit(run,*j) for j in jobs]):f.result()
    evaluate()


if __name__=='__main__':main()
