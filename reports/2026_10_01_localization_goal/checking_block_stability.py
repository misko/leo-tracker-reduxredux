"""Descriptive leave-one-time-block ranking sensitivity, not confidence intervals."""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    path = HERE/'checking-expansion-v1.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    doc = json.loads(path.read_text())
    rows = []
    for r in doc['rows']:
        if not r['accepted']:
            rows.append(dict(unit=r['unit'], accepted=False))
            continue
        source_path = HERE/'source-split-expansion-v1'/(r['unit']+'.json')
        assert digest(source_path) == r['source_sha256']
        source = json.loads(source_path.read_text())
        times = defaultdict(list)
        for p in source['checking_points']:
            times[p['source_group_id']].append(
                (p['support_center_utc_ns']-source['start_utc_ns'])/1e9)
        by_seed = {m['seed_index']: m for m in r['modes']}
        training = np.asarray(by_seed[r['training_winner_seed']]['per_group_log_ratios'])
        checking = np.asarray(by_seed[r['checking_winner_seed']]['per_group_log_ratios'])
        delta = checking-training
        blocks = defaultdict(float)
        for group, value in zip(r['source_group_order'], delta, strict=True):
            blocks[int(np.floor(np.median(times[group])/10.))] += float(value)
        total = float(delta.sum())
        deleted = [total-v for v in blocks.values()]
        rows.append(dict(unit=r['unit'], accepted=True,
                         ranking_changed=r['training_winner_seed'] != r['checking_winner_seed'],
                         total_margin=total, blocks=len(blocks),
                         minimum_margin_after_block_deletion=min(deleted),
                         maximum_margin_after_block_deletion=max(deleted),
                         positive_margins_after_deletion=sum(v > 0 for v in deleted)))
    output = HERE/'checking-block-stability-v1.json'
    result = dict(rows=rows, scores_sha256=digest(path), source_sha256=digest(__file__),
                  block_seconds=10, qualification='Descriptive ranking sensitivity only. '
                  'Remove one10s UTC-relative block across all receivers/channels at a time '
                  'from already evaluated score differences; no refit or assumption that blocks '
                  'are independent. Not a confidence interval, acceptance gate or tuned selector.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
