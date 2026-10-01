"""Geography-free accounting of saved acquisition-ranked fit prefixes.

Solver flags are deliberately not called audited acceptance. No fit is rerun.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sealed(path):
    if digest(path) != path.with_suffix('.sha256').read_text().strip():
        raise ValueError(f'Bad seal: {path}')
    return json.loads(path.read_text())


def summarize_receipt(receipt):
    fits = receipt['fits']
    if [f['seed_index'] for f in fits] != list(range(len(fits))):
        raise ValueError('Fits must form an acquisition-ranked prefix')
    scored = [f for f in fits if f['objectives']]
    best = min(scored, key=lambda f: f['objectives'][-1]) if scored else None
    if best != receipt['best']:
        raise ValueError('Saved winner differs from original minimum rule')
    first = fits[0] if fits and fits[0]['objectives'] else None
    row = dict(unit=receipt['unit'], size=receipt['binding']['size'],
               fit_count=len(fits), winner_index=best['seed_index'] if best else None,
               first_solver_converged=bool(first and first['converged']),
               best_solver_converged=bool(best and best['converged']),
               omitted_recorded_fit_seconds=sum(f['seconds'] for f in fits[1:]),
               baseline_wall_seconds=receipt['wall_seconds'])
    row['objective_gap'] = first['objectives'][-1]-best['objectives'][-1] if first and best else None
    row['position_difference_m'] = float(1000*np.linalg.norm(
        np.asarray(first['mean'][:2])-np.asarray(best['mean'][:2]))) if first and best else None
    return row


def main():
    output = HERE/'seed-prefix-screen-v1.json'
    if output.exists():
        raise FileExistsError(output)
    selection = sealed(HERE/'selection.json')
    inputs = {str(HERE/'selection.json'): digest(HERE/'selection.json')}
    rows = []
    for unit in selection['evaluation_units']:
        path = HERE/'independent-v2'/unit['block_id']/(unit['unit_id']+'.json')
        receipt = sealed(path)
        if receipt['binding'] != unit or receipt['config']['seed_limit'] != 3:
            raise ValueError('Unexpected binding or original start limit')
        inputs[str(path)] = digest(path)
        rows.append(summarize_receipt(receipt))
    summary = {}
    for size in (1, 2, 4):
        local = [r for r in rows if r['size'] == size]
        summary[str(size)] = dict(
            planned=len(local),
            first_solver_converged=sum(r['first_solver_converged'] for r in local),
            best_solver_converged=sum(r['best_solver_converged'] for r in local),
            winner_counts={str(i): sum(r['winner_index'] == i for r in local) for i in (0, 1, 2)},
            median_recorded_fit_seconds_omitted=float(np.median([r['omitted_recorded_fit_seconds'] for r in local])),
            objective_gap_over_1=sum(r['objective_gap'] is not None and r['objective_gap'] > 1 for r in local),
            position_difference_over_100m=sum(r['position_difference_m'] is not None and r['position_difference_m'] > 100 for r in local),
            max_position_difference_m=max(r['position_difference_m'] for r in local if r['position_difference_m'] is not None))
    result = dict(qualification='Saved-fit screening only; solver convergence is not audited acceptance. No geographic reference is read. Omitted work is not cold speedup.',
                  sources={str(Path(__file__).resolve()): digest(__file__)}, inputs=inputs,
                  summary=summary, rows=rows)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    labels = ['Singles', 'Pairs', 'Quads']
    for index, size in enumerate((1, 2, 4)):
        local = [r for r in rows if r['size'] == size]
        axes[0].scatter([index]*len(local), [r['position_difference_m'] for r in local], alpha=.5)
        axes[1].scatter([index]*len(local), [r['omitted_recorded_fit_seconds'] for r in local], alpha=.5)
    for ax in axes:
        ax.set_xticks(range(3), labels)
        ax.grid(alpha=.2)
    axes[0].set_yscale('symlog', linthresh=1)
    axes[0].set_ylabel('First-start vs selected position (m)')
    axes[1].set_ylabel('Recorded later-start fitting work (s)')
    fig.suptitle('Saved-start screening: no reference errors or cold speedup claims')
    fig.savefig(HERE/'seed-prefix-screen-v1.png', dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
