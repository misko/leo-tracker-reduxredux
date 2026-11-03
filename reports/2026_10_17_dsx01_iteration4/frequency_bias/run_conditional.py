"""Bounded fixed-baseline conditional residual prediction, both directions."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
sys.path.insert(0, str(REPORTS/'2026_10_16_dsx01_models'))
import common
from conditional import FixedResidualLikelihood, fit_bias_only, masked_baseline


def stats(likelihood, biases, mask):
    state = likelihood.stats(biases)
    assigned = state['assigned'] & mask
    return dict(denominator=int(mask.sum()), associated=int(assigned.sum()),
        association_pct=100.*assigned.sum()/mask.sum() if mask.sum() else None,
        assigned_rms_hz=float(np.sqrt(np.mean(state['residual'][assigned]**2))) if assigned.any() else None)


def execute(source):
    path = HERE/'conditional_results'/f'{source}.json'
    if path.exists():
        return dict(source=source, state='existing')
    started = time.monotonic()
    ctx = common.load_context(source)
    seed_path = REPORTS/'2026_10_16_dsx01_iteration2/results'/f'{source}-fitted-c-profile.json'
    seed = json.loads(seed_path.read_text())
    middle = float(np.median(np.unique(ctx.observations.times_s)))
    early = ctx.observations.times_s <= middle
    challenge = common.challenge_mask(ctx)
    records = []
    for arm in ['fitted-c', 'zero-c']:
        vector, nuisance = np.array(seed['vector']), np.array(seed['nuisance'])
        if arm == 'zero-c':
            vector[6] = 0.
        for direction, train in [('early_to_late', early), ('late_to_early', ~early)]:
            held = ~train
            train_model = masked_baseline(ctx.full_model, ctx.observations, train)
            held_model = masked_baseline(ctx.full_model, ctx.observations, held)
            for sigma in [300., 1000.]:
                learner = FixedResidualLikelihood(train_model, vector, nuisance, sigma)
                biases, diagnostics = fit_bias_only(learner, max_evaluations=300, max_seconds=30.)
                # Held values first enter the calculation after selection is complete.
                predictor = FixedResidualLikelihood(held_model, vector, nuisance, sigma)
                zero = np.zeros(len(biases))
                before, after = predictor.stats(zero), predictor.stats(biases)
                both = before['assigned'] & after['assigned']
                record = dict(source_id=source, arm=arm, direction=direction, sigma_hz=sigma,
                    seed_sha256='sha256:'+hashlib.sha256(seed_path.read_bytes()).hexdigest(),
                    train_observations=int(train.sum()), held_observations=int(held.sum()),
                    split_time_s=middle, diagnostics=diagnostics,
                    held_nll_b0=before['nll'], held_nll_learned=after['nll'],
                    held_nll_delta=after['nll']-before['nll'],
                    held_new=int(np.sum(after['assigned'] & ~before['assigned'])),
                    held_lost=int(np.sum(before['assigned'] & ~after['assigned'])),
                    held_retained=int(both.sum()),
                    held_intersection_b0_rms_hz=float(np.sqrt(np.mean(before['residual'][both]**2))) if both.any() else None,
                    held_intersection_learned_rms_hz=float(np.sqrt(np.mean(after['residual'][both]**2))) if both.any() else None,
                    biases_hz={str(int(s)):float(b) for s, b in zip(ctx.bank.numbers, biases)},
                    physical_vector=vector, clock_and_q=nuisance,
                    configured_reference_distance_km=seed['full_scan']['configured_reference_distance_km'],
                    all_held_b0=stats(predictor, zero, np.ones(int(held.sum()), bool)),
                    all_held_learned=stats(predictor, biases, np.ones(int(held.sum()), bool)),
                    challenge_held_b0=stats(predictor, zero, challenge[held]),
                    challenge_held_learned=stats(predictor, biases, challenge[held]),
                    qualification='Conditional residual prediction only: physical vector, frozen calibration and q are full-data-conditioned and unchanged. Bias selection reads train rows only; this is not cold-pipeline validation or position/identity validation.')
                records.append(record)
    common.save_json(path, dict(source_id=source, records=records,
        elapsed_seconds=time.monotonic()-started,
        code_sha256={name:'sha256:'+hashlib.sha256((HERE/name).read_bytes()).hexdigest()
            for name in ['conditional.py', 'run_conditional.py']}))
    return dict(source=source, state='complete', records=len(records),
        deltas=[round(r['held_nll_delta'], 2) for r in records])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', nargs='+', default=['S01', 'S02', 'S03', 'S04', 'S05'])
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    (HERE/'conditional_results').mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(execute, s) for s in args.sources]):
            print(json.dumps(future.result()), flush=True)


if __name__ == '__main__':
    main()
