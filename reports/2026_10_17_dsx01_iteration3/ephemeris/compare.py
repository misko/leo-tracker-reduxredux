"""Causal Space-Track element sensitivity with the same selected satellite IDs.

Research-only orchestration. Target coordinates and hand-selected tracks never
enter candidate construction, initializers or fit selection. Both providers
start at the same saved original state; band calibration is deliberately fixed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace, asdict
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
OLD = REPORTS / '2026_10_16_dsx01_models'
PREVIOUS = REPORTS / '2026_10_16_dsx01_iteration2'
sys.path[:0] = [str(OLD), str(PREVIOUS)]
from common import load_context, measure, challenge_mask, endpoint_status, point_state, save_json
from bank_expansion import fixed_shift
from profile_search import fit


def with_bank(context, bank):
    """Replace ephemerides only; keep candidate order and calibration exactly."""
    from leo.analysis.sequential_group_calibration import fixed_shift_objective
    from leo.analysis.shared_scan_model import SharedScanObjective
    from leo.application.channel_group_refinement import objective

    if not np.array_equal(context.bank.numbers, bank.numbers):
        raise ValueError('Identical ordered satellite IDs required for the provider comparison')
    if not np.array_equal(context.bank.nodes_s, bank.nodes_s):
        raise ValueError('Identical ephemeris query nodes required')
    shift = fixed_shift(context.model)
    joint = objective(SimpleNamespace(observations=context.observations), bank,
                      context.prior, context.nodes)
    raw = fixed_shift_objective(joint.base, shift)
    raw.score = context.model.score
    model = SharedScanObjective(raw, shift, mask=context.train_mask)
    full = SharedScanObjective(raw, shift)
    for name in ('design', 'clock_design', 'baseline'):
        np.testing.assert_array_equal(getattr(raw, name), getattr(context.model.original, name))
    return replace(context, model=model, full_model=full, bank=bank,
                   vector=context.vector.copy(), nuisance=context.nuisance.copy())


def epoch_summary(catalogue, numbers, origin):
    lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
    missing = sorted(set(map(int, numbers)) - set(lookup))
    if missing:
        raise ValueError(f'Matched candidate IDs absent from selected snapshot: {missing}')
    epochs = np.asarray(catalogue.element_epoch_utc_ns(), dtype=np.int64)
    age = np.array([(origin - int(epochs[lookup[int(n)]])) / 3.6e12 for n in numbers])
    return dict(signed_age_h=age.tolist(), median_absolute_age_h=float(np.median(abs(age))),
                absolute_age_h_quantiles=np.quantile(abs(age), [0, .1, .5, .9, 1]).tolist(),
                negative_signed_age_count=int(np.sum(age < 0)))


def prepare(context):
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    origin = context.source['first_sample_estimate_utc_ns']
    original = next(s for s in archive.list_snapshots()
                    if s.digest == context.source['tle_sha256']
                    and s.collected_utc_ns == context.source['tle_collected_utc_ns'])
    alternative = archive.select_latest_before(origin, 'space-track')
    receipts = {}
    selected = list(map(int, context.bank.numbers))
    for label, snapshot in [('original_snapshot', original), ('causal_space_track', alternative)]:
        if snapshot.collected_utc_ns >= origin:
            raise ValueError('Snapshot was unavailable before recording start')
        catalogue = parse_element_sets(archive.read(snapshot))
        receipts[label] = dict(provider=snapshot.provider, digest=snapshot.digest,
            collected_utc_ns=snapshot.collected_utc_ns,
            collection_age_min=(origin-snapshot.collected_utc_ns)/6e10,
            selected_elements=epoch_summary(catalogue, selected, origin))
        if label == 'causal_space_track':
            lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
            bank, receipt = build_regional_bank(catalogue, [lookup[n] for n in selected],
                origin, context.observations, context.prior, maximum_seconds=60)
            order = {int(n): i for i, n in enumerate(bank.numbers)}
            if set(order) != set(selected):
                raise ValueError('Alternative bank changed original regional eligibility')
            bank = bank.select([order[n] for n in selected])
            receipts[label]['bank_build'] = asdict(receipt)
    return with_bank(context, bank), receipts


def run_source(source_id, arms):
    original = load_context(source_id)
    context, authority = prepare(original)
    output = HERE / 'results'
    output.mkdir(parents=True, exist_ok=True)
    save_json(output / f'{source_id}-authority.json', authority)
    results = []
    for arm in arms:
        path = output / f'{source_id}-{arm}-profile.json'
        if path.exists():
            results.append(dict(source=source_id, arm=arm, existing=True))
            continue
        ctx = replace(context, vector=context.vector.copy(), nuisance=context.nuisance.copy(),
                      fixed_c=arm == 'zero-c', deadline=time.monotonic()+120)
        if ctx.fixed_c:
            ctx.vector[6] = 0.
        seed = measure(ctx, ctx.vector, ctx.nuisance)
        result = fit(ctx, max_evaluations=1000, max_seconds=120)
        v, n = result['vector'], result['nuisance']
        record = dict(source_id=source_id, arm=arm, method='causal-space-track-profile',
            vector=v, nuisance=n, diagnostics=result['diagnostics'], audit=endpoint_status(ctx,v,n),
            full_scan=measure(ctx,v,n), challenge=measure(ctx,v,n,mask=challenge_mask(ctx)),
            outside=measure(ctx,v,n,mask=~challenge_mask(ctx)), source=ctx.source,
            provider_authority=authority, seed_metrics=seed,
            budget=dict(full_objectives=1000, wall_seconds=120),
            qualification='Controlled provider sensitivity, selected IDs and original seed/calibration fixed; warm development result, not end-to-end validation.')
        _, _, best, associated, residual = point_state(ctx.full_model,v,n)
        np.savez_compressed(path.with_suffix('.npz'), associated=associated,
                            residual_hz=residual,satellite_number=ctx.bank.numbers[best],
                            times_s=ctx.observations.times_s,train_mask=ctx.train_mask)
        save_json(path,record)
        brief = dict(source=source_id, arm=arm, full=record['full_scan']['associated'],
                     windows=record['challenge']['associated'], audit=record['audit'],
                     reference_km=record['full_scan'].get('configured_reference_distance_km'))
        results.append(brief)
        print(json.dumps(brief),flush=True)
    return results


def main():
    p=argparse.ArgumentParser()
    # S02--S04 already use this identical causal Space-Track snapshot. Their
    # immutable prior profile receipts are identity controls, not new trials.
    p.add_argument('--sources',nargs='+',default=['S01','S05'])
    p.add_argument('--arms',nargs='+',default=['fitted-c','zero-c'])
    p.add_argument('--workers',type=int,default=5)
    args=p.parse_args()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(run_source,s,args.arms) for s in args.sources]):
            f.result()


if __name__=='__main__':
    main()
