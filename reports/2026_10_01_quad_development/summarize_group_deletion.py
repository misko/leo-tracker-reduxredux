"""Account for every planned group-deletion arm and plot accepted motion."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from check_group_influence import UNITS
from check_receiver_curvature import save
from screen_seed_prefix import digest, sealed
from regression_batch import verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def main():
    rows = []; inputs = {}
    for unit in UNITS:
        for arm in ('fixed', 'reassigned'):
            directory = HERE/'group-deletion-v1'/unit/arm
            launch = sealed(directory/'launch.json'); inputs[str(directory/'launch.json')] = digest(directory/'launch.json')
            result = sealed(directory/'result.json') if (directory/'result.json').exists() else None
            if result:
                freeze = sealed(directory/'sources.json')
                verify_sources(freeze['source_sha256']); verify_sources(freeze['inputs'])
                for name in ('sources.json', 'result.json'): inputs[str(directory/name)] = digest(directory/name)
            accepted = bool(process_ok(launch) and result and result['audit']['accepted'])
            rows.append(dict(unit=unit, arm=arm, accepted=accepted, launch=launch, result=result))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.7), constrained_layout=True)
    colors = {'DS9': '#386cb0', 'DS10': '#df8829', 'DS11': '#2b9871'}
    for row in rows:
        if not row['accepted']: continue
        c = row['result']['comparison']; ds = row['unit'].split('-')[0]; marker = 'o' if row['arm'] == 'fixed' else 'x'
        axes[0].scatter(c['predicted_step_m'], c['actual_step_m'], color=colors[ds], marker=marker)
        i = UNITS.index(row['unit'])
        axes[1].scatter(i+(-.1 if row['arm'] == 'fixed' else .1), c['vector_difference_m'], color=colors[ds], marker=marker)
    values = [r['result']['comparison'][k] for r in rows if r['accepted'] for k in ('predicted_step_m', 'actual_step_m')]
    upper = max(values)*1.05 if values else 1
    axes[0].plot([0, upper], [0, upper], '--', color='gray'); axes[0].set_xlim(0, upper); axes[0].set_ylim(0, upper)
    axes[0].set_xlabel('Frozen-weight predicted step (m)'); axes[0].set_ylabel('Nonlinear refit step (m)')
    axes[1].set_xticks(range(9), [u.replace('-B01-', '\n') for u in UNITS], fontsize=8)
    axes[1].set_ylabel('Prediction versus refit vector difference (m)')
    for ax in axes: ax.grid(alpha=.2)
    fig.suptitle('Group deletion: circles = fixed identities; crosses = reassignment\nAccepted motion only; no geographic error scoring')
    figure = HERE/'group-deletion-summary-v1.png'; fig.savefig(figure, dpi=160); plt.close(fig)
    result = dict(rows=rows, planned=len(rows), accepted=sum(r['accepted'] for r in rows),
        total_process_seconds=sum(r['launch']['elapsed_seconds'] for r in rows), inputs=inputs,
        sources={str(Path(__file__).resolve()): digest(__file__)}, figure_sha256=digest(figure))
    save(HERE/'group-deletion-summary-v1.json', result)
    for r in rows: print(r['unit'], r['arm'], r['accepted'], r['result']['audit'] if r['result'] else 'missing', r['result'].get('comparison') if r['result'] else '')
    print('accepted', result['accepted'], 'planned', result['planned'], 'seconds', result['total_process_seconds'])


if __name__ == '__main__': main()
