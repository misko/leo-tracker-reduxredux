"""Summarize completed direct-integration and shared-rate experiments."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
OUT = HERE / 'quality-quadrature'


def main():
    mixture = json.loads((HERE / 'quality-mixture/summary.json').read_text())
    summary = []
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, old, label in zip(axes, mixture['scans'], ['08:20', '10:50']):
        sid = old['session_id']
        runs = {n: json.loads((OUT / f'{sid}-n{n}.json').read_text()) for n in (32, 64)}
        comparisons = []
        for m, name in enumerate(['generic', 'timing_informed']):
            a, b = [runs[n]['models'][m] for n in (32, 64)]
            delta = b['held_log_predictive'] - a['held_log_predictive']
            maxblock = max(abs(x['log_predictive'] - y['log_predictive']) for x, y in zip(a['rows'], b['rows']))
            maxprob = max(float(np.max(np.abs(np.array(x['identity_probabilities']) - y['identity_probabilities']))) for x, y in zip(a['rows'], b['rows']))
            comparisons.append(dict(model=name, n32_score=a['held_log_predictive'], n64_score=b['held_log_predictive'], score_change_nats=delta, max_block_change_nats=maxblock, max_identity_probability_change=maxprob, consistency_passed=abs(delta) <= .05 and maxblock <= .05))
            scores = [old['runs'][-1]['scores'][name], a['held_log_predictive'], b['held_log_predictive']]
            ax.plot(range(3), np.array(scores) - old['stationary_score'], 'o-', label=name.replace('_', ' '))
        summary.append(dict(session_id=sid, stationary_score=old['stationary_score'], comparisons=comparisons))
        ax.set(title=f'{label} real DS5 track', ylabel='Held CFO gain over stationary (nats)', xticks=range(3), xticklabels=['8 mixtures', '32 nodes', '64 nodes'])
        ax.axhline(0, color='gray', lw=.8); ax.legend(); ax.grid(alpha=.2)
    fig.suptitle('Numerical sensitivity: these are predictive scores, not identity accuracy')
    fig.tight_layout(); fig.savefig(OUT / 'integration-comparison.png', dpi=160); plt.close(fig)
    (OUT / 'summary.json').write_text(json.dumps(dict(tolerance_nats=.05, all_consistent=all(c['consistency_passed'] for s in summary for c in s['comparisons']), scans=summary), indent=2) + '\n')

    shared = json.loads((HERE / 'shared-rate/scores.json').read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for arm, dx in [('independent', -.16), ('shared', .16)]:
        values = [r['train_eval_rms_deg'] for r in shared['repeatability'] if r['arm'] == arm]
        axes[0].bar(np.arange(2) + dx, values, width=.32, label=arm)
    axes[0].set(xticks=[0, 1], xticklabels=['09:50 (17 windows)', '12:00 (25 windows)'], ylabel='Train/evaluation double-difference RMS (degrees)', title='Real phase repeatability'); axes[0].legend()
    rows = shared['comparisons']
    for key, label in [('independent_phase_gain_nats', 'independent'), ('shared_phase_gain_nats', 'shared')]:
        axes[1].scatter(range(8), [r[key] for r in rows], label=label, marker='o' if label == 'independent' else 'x')
    axes[1].axhline(0, color='gray', lw=.8)
    axes[1].set(xticks=range(8), xticklabels=[f"{['09:50','12:00'][i//4]}\nf{r['fold']} σ{r['sigma_hz']}" for i, r in enumerate(rows)], ylabel='Held CFO gain from phase (nats)', title='Same candidates; only phase-rate fitting changes')
    axes[1].tick_params(axis='x', labelsize=7); axes[1].legend()
    fig.tight_layout(); fig.savefig(HERE / 'shared-rate/comparison.png', dpi=160); plt.close(fig)

    oracle = json.loads((OUT / 'physical-phase-audit.json').read_text())
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for start in (0, 63):
        rows = [r for r in oracle['cases'] if r['start_ms'] == start]
        axes[0].scatter([np.degrees(r['expected_wrapped_phase_rad']) for r in rows], [np.degrees(r['measured_wrapped_phase_rad']) for r in rows], label=f'{start} ms start')
        axes[1].plot([r['baseline_m'] for r in rows], [np.degrees(r['error_rad']) for r in rows], 'o-', label=f'{start} ms start')
    axes[0].plot([-180, 180], [-180, 180], '--', color='gray'); axes[0].set(xlabel='Injected double difference (degrees)', ylabel='Recovered double difference (degrees)')
    axes[1].axhline(0, color='gray', lw=.8); axes[1].set(xlabel='Synthetic baseline (m)', ylabel='Wrapped error (degrees)')
    for ax in axes: ax.legend(); ax.grid(alpha=.2)
    fig.suptitle('Synthetic physical RF oracle: no noise, multipath or hardware response')
    fig.tight_layout(); fig.savefig(OUT / 'physical-phase-oracle.png', dpi=160); plt.close(fig)


if __name__ == '__main__':
    main()
