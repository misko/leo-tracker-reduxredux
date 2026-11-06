"""Count repeated calibration masks before proposing complete-fit reuse.

This is an optimistic necessary-condition census, not a cache implementation or
a proof that every other input to two fitting problems is equal.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from probe_algo07v3_annotation_arms import fold_inputs, load_context

from leo.analysis.localization_v3.recovery_partitions import planned_split
from leo.operations.localization_v3_job import runtime_versions, source_bindings


def classify(rows):
    groups = {}
    for index, row in enumerate(rows):
        groups.setdefault(row['calibration_mask_sha256'], []).append(index)
    duplicates = [indices for indices in groups.values() if len(indices) > 1]
    return dict(eligible_fold_problems=len(rows), unique_masks=len(groups),
                potentially_reusable_fits_per_arm=len(rows) - len(groups),
                duplicate_groups=duplicates, sufficient_for_reuse=False)


def census(request):
    assert request['runtime'] == runtime_versions()
    d, inv, receipt = load_context(request)
    rows, skipped = [], []
    for index, target in enumerate(inv['selected_targets']):
        for fold in range(3):
            # This census requires three prepared folds. Fail closed if the
            # fixture lacks them or its indices are corrupt; neither is reuse.
            view, i, full, n, seed, plan = fold_inputs(d, inv, index, fold)
            train, held, split = planned_split(full, view['scan'].tracks[i]['times'], seed, plan)
            if train[n:].sum() < 8 or held[n:].sum() < 4:
                skipped.append(dict(target=index, fold=fold, reason='insufficient_target_support'))
                continue
            keep = np.asarray(view['keep'] & train[:n], dtype=np.uint8)
            rows.append(dict(target=index, track_id=target['track_id'], fold=fold, seed=int(seed),
                             inactive_fragment=target['inactive_fragment'],
                             calibration_points=int(keep.sum()), mask_length=len(keep),
                             calibration_mask_sha256=hashlib.sha256(keep.tobytes()).hexdigest(),
                             split=split))
    return dict(run_id=request['identity']['run_id'], scientific_receipt=receipt,
                targets=len(inv['selected_targets']), rows=rows, skipped=skipped, **classify(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), *args.request, Path(__file__),
             Path('tools/probe_algo07v3_annotation_arms.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    bindings.update({r['path']: r['sha256'] for r in source_bindings().values()})
    results = []
    for index, path in enumerate(args.request):
        result = census(json.loads(path.read_bytes()))
        results.append(result)
        (args.output / f'case-{index}.json').write_text(json.dumps(result, indent=2) + '\n')
        summary = {k: v for k, v in result.items() if k not in ('rows', 'skipped')}
        print(json.dumps(summary), flush=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    (args.output / 'result.json').write_text(json.dumps(dict(
        bindings=bindings, cases=results, runtime_modified=False,
        new_fits_executed=0, full_pipeline_speedup=None), indent=2) + '\n')


if __name__ == '__main__':
    main()
