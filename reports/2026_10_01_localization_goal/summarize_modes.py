"""Describe sealed regression search behavior without changing mode selection."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluation', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    evaluation = json.loads(args.evaluation.read_text())
    rows = []
    root = Path(__file__).resolve().parent
    for audited in evaluation['rows']:
        if not audited['accepted']:
            continue
        paths = list((root/'regression-v1').glob('batch-*/'+audited['unit']+'.json'))
        assert len(paths) == 1
        payload = paths[0].read_bytes()
        assert 'sha256:'+hashlib.sha256(payload).hexdigest() == audited['receipt_sha256']
        receipt = json.loads(payload)
        best = receipt['best']
        competitors = []
        for fit in receipt['fits']:
            if fit['seed_index'] == best['seed_index'] or not fit['objectives']:
                continue
            competitors.append(dict(
                seed_index=fit['seed_index'], converged=fit['converged'],
                separation_m=float(np.linalg.norm(
                    np.asarray(fit['mean'][:2])-np.asarray(best['mean'][:2]))*1000),
                objective_gap=fit['objectives'][-1]-best['objectives'][-1],
            ))
        rows.append(dict(
            unit=audited['unit'], winner_seed=best['seed_index'],
            winner_iterations=best['iterations'],
            cpu_s=receipt['cpu_seconds'], runtime_s=audited['runtime_s'],
            acquisition_s=receipt['proposal']['wall_seconds'],
            error_m=audited['error_m'], competitors=competitors,
        ))
    result = dict(
        qualification=('Post-evaluation diagnostic of accepted scans only. Distances between '
                       'modes use local chart coordinates. Objective gaps are not calibrated '
                       'posterior probabilities. No reference-based model selection.'),
        evaluation_sha256='sha256:'+hashlib.sha256(args.evaluation.read_bytes()).hexdigest(),
        planned_count=evaluation['planned_count'], finished_count=evaluation['finished_count'],
        accepted_count=len(rows),
        nonfirst_seed_winners=sum(r['winner_seed'] != 0 for r in rows),
        scans_with_unconverged_competitor=sum(
            any(not c['converged'] for c in r['competitors']) for r in rows),
        scans_with_converged_competitor_over_1km=sum(
            any(c['converged'] and c['separation_m'] > 1000 for c in r['competitors'])
            for r in rows),
        median_cpu_s=float(np.median([r['cpu_s'] for r in rows])) if rows else None,
        median_acquisition_s=float(np.median([r['acquisition_s'] for r in rows])) if rows else None,
        rows=rows,
    )
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    main()
