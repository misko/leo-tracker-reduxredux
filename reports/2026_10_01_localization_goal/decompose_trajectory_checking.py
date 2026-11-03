"""Separate candidate checking-score changes by exact prediction coverage."""
import json
from pathlib import Path

import numpy as np
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    paths = [HERE/'checking-expansion-v1.json', HERE/'trajectory-hypothesis-checking-v1.json']
    for path in paths:
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    old = {r['unit']: r for r in json.loads(paths[0].read_text())['rows']}
    rows = []
    for row in json.loads(paths[1].read_text())['rows']:
        unit = row['unit']
        assert row['source_group_order'] == old[unit]['source_group_order']
        modes = [next(m for m in entry['modes']
                      if m['seed_index'] == entry['training_winner_seed'])
                 for entry in [old[unit], row]]
        a, b = [np.array(m['per_group_log_ratios']) for m in modes]
        # Empty predictions give exactly zero in this sealed scoring implementation.
        # Count equality rules out zero-valued scores at covered groups in these data.
        assert np.count_nonzero(a) == modes[0]['groups_with_prediction']
        assert np.count_nonzero(b) == modes[1]['groups_with_prediction']
        masks = dict(common=(a != 0)&(b != 0), gained=(a == 0)&(b != 0),
                     lost=(a != 0)&(b == 0), neither=(a == 0)&(b == 0))
        sections = {label: dict(groups=int(mask.sum()), log_ratio_gain=float((b-a)[mask].sum()))
                    for label, mask in masks.items()}
        assert abs(sum(v['log_ratio_gain'] for v in sections.values())-(b-a).sum()) < 1e-8
        rows.append(dict(unit=unit, sections=sections, total_gain=float((b-a).sum())))
    result = dict(rows=rows, inputs={str(p): digest(p) for p in paths},
        auditor_sha256=digest(__file__),
        qualification='Exact score decomposition at training-selected modes. Common groups '
        'are identical observations but condition on both models predicting there; this is '
        'not unbiased overall predictive accuracy, geographic truth, or independent validation.')
    output = HERE/'trajectory-hypothesis-checking-decomposition-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
