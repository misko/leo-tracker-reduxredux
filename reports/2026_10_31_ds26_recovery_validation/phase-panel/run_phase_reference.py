"""Bounded DS26-0265 frozen-competition numerical-reference experiment."""
import argparse
import copy
import hashlib
import signal
import time
from pathlib import Path

import numpy as np

from debug_fast_graph_unassociated import read, write, memberships
from annotate_predictive_only import context, prediction_models
from annotate_track_predictively import fit_training
from leo.analysis.research.grouped_prediction import replay_split, identity_consensus
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD
from phase_reference_checks import phase_refresh, reference_domain

ROOT = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030/cases/DS26-0265/candidate-v2/recovery')
TID = '36f621d91e81526b1ce4'


def fingerprint(mask):
    return hashlib.sha256(np.asarray(mask, np.uint8).tobytes()).hexdigest()


def check_domains(p, phase, entries):
    checks = dict(curved=reference_domain(p.sky['time_s'], p.flat_times, p.flat_labels, phase))
    if entries:
        from ds23_predictive_linear import linear_geometry
        view, *_ = linear_geometry(p, entries)
        checks['predictive'] = reference_domain(p.sky['time_s'], view.flat_times, view.flat_labels, phase)
    if not all(v['in_domain'] for v in checks.values()):
        raise ValueError('reference update leaves frozen causal orbit bank')
    return checks


def run(out, inventory=None, annotation_source=None, annotation_only=False):
    began = time.monotonic()
    inv_path = inventory or next((ROOT / 'all-large-track-recovery').glob('*/inventory.json'))
    source = annotation_source or ROOT / TID / 'annotation'
    inv, frozen, pr = read(inv_path), read(source / 'result.json'), read(source / 'protocol.json')
    d = context(inv)
    base, _ = d['problems']['c0']
    target = pr['target']; track = d['scan'].tracks[target['track_index']]
    n = len(base.flat_times); full_times = np.r_[base.flat_times, track['times']]
    sources = [inv_path, source / 'result.json', source / 'protocol.json', Path(__file__)]
    write(out / 'protocol.json', dict(inventory=str(inv_path), source=str(source), limits_s=[15, 30],
        saved_grouped_partitions=3, paired_c_arms=True, graph_fits_per_limit=6,
        same_candidates_aliases_priors_masks_starts_and_search_budgets=True,
        physical_phase_prior_and_target_integration_support_unchanged=True,
        GPS_used=False, new_RF=False, new_TLE=False, extrapolation=False,
        reference_rounds=5, position_iterations=48, wall_budget_s=590,
        source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}))
    # fit_training imports this fitter at call time. Capture its full termination
    # records while retaining the exact existing training implementation.
    import investigate_dsx01_localization_failures as fitter
    original_fit = fitter.fit
    attempts = []
    def recording_fit(*a, **k):
        r = original_fit(*a, **k); attempts.append(copy.deepcopy(r)); return r
    fitter.fit = recording_fit
    annotations = {}
    try:
        for limit in (15, 30):
            folder = out / f'reference{limit}' / 'annotation'; folder.mkdir(parents=True)
            folds = []
            for fold in frozen['folds']:
                train, held = replay_split(full_times, fold['split'])
                keep = d['keep'] & train[:n]; tt, th = train[n:], held[n:]
                updated = copy.deepcopy(fold)
                hashes = dict(graph_training=fingerprint(keep), target_training=fingerprint(tt), target_held=fingerprint(th))
                fits = {}
                for arm in ('c0', 'fitted_c'):
                    before = len(attempts)
                    p, x, meta = fit_training(d, d['node'], keep, arm, reference_limit_s=limit)
                    for h, state in zip(meta['history'], attempts[before:], strict=True): h['optimizer'] = state
                    fits[arm] = p, x, meta
                for proposal in updated['proposals']:
                    for arm, (p, x, meta) in fits.items():
                        mu, cov, lp, phases, elev, prior = prediction_models(d, p, x, target['track_index'], proposal['candidate_index'],
                            phase_step=pr['phase_step_s'], uncalibrated_phase_mixture=pr['uncalibrated_phase_mixture'])
                        # All target phase-grid evaluations also stay in the bank.
                        for boundary in (float(phases.min()), float(phases.max())):
                            domain = reference_domain(p.sky['time_s'], track['times'], np.zeros(len(track['times']), int), [boundary])
                            if not domain['in_domain']: raise ValueError('target predictive phase leaves causal bank')
                        score = mixture_prediction(track['values'] + proposal['alias'] * PERIOD, mu, cov, lp, tt, th)
                        weights = score['training_mixture_weights']; mean = float(weights @ phases)
                        value = dict(meta, scores=dict(conditional_target=score, target=score), prior=prior,
                            minimum_target_elevation_deg=float(elev[weights > 1e-6].min()),
                            target_phase_training_mean_s=mean, target_phase_training_sigma_s=float(np.sqrt(weights @ (phases-mean)**2)),
                            target_phase_boundary_mass=float(weights[abs(phases)>=14.9].sum()) if len(phases)>1 else float(abs(phases[0])>=14.9),
                            target_enters_calibration_equations=False, mask_sha256=hashes)
                        if limit == 15:
                            old = next(q for q in fold['proposals'] if q['norad']==proposal['norad'])['arms'][arm]
                            value['frozen_score_difference'] = score['negative_twice_log_density']-old['scores']['conditional_target']['negative_twice_log_density']
                            value['frozen_rms_difference_hz'] = score['rms_hz']-old['scores']['target']['rms_hz']
                            if abs(value['frozen_score_difference'])>1e-5: raise ValueError('15s frozen score replay mismatch')
                        proposal['arms'][arm] = value
                folds.append(updated)
                write(folder / f"seed-{fold['seed']}.json", updated)
                print('annotation', limit, fold['seed'], [(a, fits[a][2]['final_phase_change_s']) for a in fits], flush=True)
            result = dict(frozen, folds=folds, annotation=identity_consensus(folds, score_name='conditional_target'),
                reference_limit_s=limit, seconds=time.monotonic()-began, no_production_change=True)
            annotations[limit] = result
            write(folder / 'result.json', result); write(folder / 'protocol.json', dict(pr, reference_limit_s=limit, frozen_competition=True))
    finally:
        fitter.fit = original_fit
    write(out / 'annotation_summary.json', {str(k):v['annotation'] for k,v in annotations.items()})
    if annotation_only or annotations[30]['annotation']['status'] != 'conditionally_supported_identity':
        write(out / 'terminal.json', dict(completed=True, inclusion_attempted=False,
            reason='annotation-only requested' if annotation_only else 'broader-reference identity gates failed', seconds=time.monotonic()-began)); return
    from continue_shared import run as include_shared
    shared=out/'shared'; shared.mkdir(); include_shared(out,shared)
    write(out/'terminal.json',dict(completed=True,inclusion_attempted=True,inclusion_root=str(shared),seconds=time.monotonic()-began))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inventory',type=Path); parser.add_argument('--source',type=Path)
    parser.add_argument('--annotation-only',action='store_true'); args=parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    def timeout(*unused): raise TimeoutError('590-second workflow budget')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(590)
    try: run(args.output,args.inventory,args.source,args.annotation_only)
    except Exception as exc:
        write(args.output/'failure.json', dict(type=type(exc).__name__, message=str(exc)))
        raise
