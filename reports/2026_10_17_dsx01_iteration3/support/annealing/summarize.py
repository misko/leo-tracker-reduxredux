"""Postseal all-five RAW-policy metrics; never mix later numerical repairs."""

import csv
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('annealing_summary_ports', HERE/'polish.py')
ports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports)
pilot = ports.pilot


def main():
    for label in ('S01', 'S02', 'S03', 'S04', 'S05'):
        name = 'seal' if label in pilot.LABELS else 'remaining_seal'
        seal = json.loads((HERE/f'{name}_{label}.json').read_text())
        if any(pilot.digest(row['path']) != row['sha256'] for row in seal['outcomes']):
            raise ValueError('all20 raw units must seal before summary')
    with (pilot.common.DATASET/'membership.csv').open() as stream:
        memberships = list(csv.DictReader(stream))
    rows, finished_rows = [], []
    for label in ('S01', 'S02', 'S03', 'S04', 'S05'):
        context = pilot.common.load_context(label)
        region_ids = {r['region_id'] for r in memberships if r['source_id'] == label}
        masks = {region: np.isin(context.observations.window_ids,
            [r['observation_id'] for r in memberships if r['region_id'] == region])
            for region in sorted(region_ids)}
        for arm in ('fitted-c', 'zero-c'):
            ctx = replace(context, fixed_c=arm == 'zero-c')
            # Every series, including c0, uses the same original published
            # fitted-c state for new/lost/intersection metrics.
            reference = context.vector, context.nuisance
            for method in ('continuation', 'annealing'):
                prefix = 'fit' if label in pilot.LABELS else 'remaining_fit'
                path = HERE/f'{prefix}_{label}_{arm}_{method}.json'
                saved = json.loads(path.read_text())
                raw = saved if label in pilot.LABELS else saved['raw']
                v, n = np.array(raw['vector']), np.array(raw['nuisance'])
                pilot.common.save_json(HERE/f'uniform_fit_{label}_{arm}_{method}.json', dict(
                    vector=v, nuisance=n, diagnostics=raw['diagnostics'],
                    source_path=str(path), source_sha256=pilot.digest(path),
                    policy='normalized copy of raw inference endpoint, numerical finishes excluded'))
                audit = pilot.common.endpoint_status(ctx, v, n)
                if abs(audit['training_objective']-raw['diagnostics']['objective']) > 1e-7:
                    raise ValueError('raw source objective mismatch')
                _, _, best, assigned, residual = pilot.common.point_state(ctx.full_model, v, n)
                np.savez_compressed(HERE/f'uniform_eval_{label}_{arm}_{method}.npz',
                    associated=assigned, residual_hz=residual,
                    satellite_number=ctx.bank.numbers[best], times_s=ctx.observations.times_s)
                rows.append(dict(source_id=label, arm=arm, method=method,
                    source_path=str(path), source_sha256=pilot.digest(path),
                    inference=raw['diagnostics'], audit=audit,
                    full=pilot.common.measure(ctx, v, n, original=reference),
                    challenge=pilot.common.measure(ctx, v, n, original=reference,
                        mask=pilot.common.challenge_mask(ctx)),
                    windows={name: dict(observations=int(mask.sum()),
                        associated=int(assigned[mask].sum())) for name, mask in masks.items()}))
                if label not in pilot.LABELS and saved['supplement']:
                    fv, fn = np.array(saved['vector']), np.array(saved['nuisance'])
                    _, _, fb, fa, fr = pilot.common.point_state(ctx.full_model, fv, fn)
                    np.savez_compressed(HERE/f'finishing_eval_{label}_{arm}_{method}.npz',
                        associated=fa, residual_hz=fr, satellite_number=ctx.bank.numbers[fb],
                        times_s=ctx.observations.times_s)
                    finished_rows.append(dict(source_id=label, arm=arm, method=method,
                        source_sha256=pilot.digest(path), audit=saved['audit'],
                        support_unchanged=bool(np.array_equal(fa, assigned)),
                        all_best_candidate_labels_unchanged=bool(np.array_equal(fb, best)),
                        full=pilot.common.measure(ctx, fv, fn, original=reference),
                        challenge=pilot.common.measure(ctx, fv, fn, original=reference,
                            mask=pilot.common.challenge_mask(ctx))))
        print(label, 'uniform RAW-policy evaluation complete', flush=True)
    aggregate = []
    for arm in ('fitted-c', 'zero-c'):
        for method in ('continuation', 'annealing'):
            selected = [r for r in rows if r['arm'] == arm and r['method'] == method]
            aggregate.append(dict(arm=arm, method=method,
                observations=sum(r['full']['observations'] for r in selected),
                associated=sum(r['full']['associated'] for r in selected),
                challenge_observations=sum(r['challenge']['observations'] for r in selected),
                challenge_associated=sum(r['challenge']['associated'] for r in selected),
                strict=sum(r['audit']['accepted'] for r in selected),
                inference_objectives=sum(r['inference']['evaluations'] for r in selected)))
    pilot.common.save_json(HERE/'uniform_evaluation.json', dict(rows=rows, aggregate=aggregate,
        source_sha256={str(Path(__file__)): pilot.digest(__file__)},
        policy='same raw width schedule and125 control for all5; no numerical finishing mixed',
        comparison_reference='same original published fitted-c state for both RF arms',
        postseal_objectives_per_result=6, source_replay_objectives_per_case=2,
        promotion=False))
    pilot.common.save_json(HERE/'finishing_evaluation.json', dict(rows=finished_rows,
        scope='remaining-three immediate finishing only; primary uniform raw series separate',
        postseal_objectives_per_result=5, promotion=False))


if __name__ == '__main__':
    main()
