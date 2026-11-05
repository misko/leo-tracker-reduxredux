"""Count repeated training masks without doing any additional position fitting."""
import argparse
import hashlib
import json
from pathlib import Path

from probe_algo07v3_annotation_arms import fold_inputs, load_context

from leo.analysis.localization_v3.recovery_partitions import planned_split


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    d, inv, receipt = load_context(request)
    seen, rows = {}, []
    for index, target in enumerate(inv['selected_targets']):
        for fold in range(3):
            view, i, full, n, seed, plan = fold_inputs(d, inv, index, fold)
            train, _, _ = planned_split(full, view['scan'].tracks[i]['times'], seed, plan)
            mask = d['keep'] & train[:n]
            key = mask.tobytes()
            row = dict(target=index, track_id=target['track_id'], seed=seed,
                       inactive_fragment=target['inactive_fragment'],
                       training_points=int(mask.sum()),
                       mask_sha256=hashlib.sha256(key).hexdigest(),
                       previous_same_mask=seen.get(key))
            rows.append(row)
            seen.setdefault(key, dict(target=index, seed=seed))
    result = dict(rows=rows, total=len(rows), unique_masks=len(seen),
                  scientific_receipt=receipt,
                  note='Mask equality is necessary, not sufficient, for training-cache reuse',
                  request_sha256=hashlib.sha256(args.request.read_bytes()).hexdigest())
    (Path(__file__).parent / 'training-masks.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(total=len(rows), unique_masks=len(seen))))


if __name__ == '__main__':
    main()
