"""Plot all conditional held-track scale predictions, including losses."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from check_shared_scale import UNITS
from check_receiver_curvature import save
from screen_seed_prefix import sealed, digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def main():
    rows = []; inputs = {}
    for unit in UNITS:
        directory = HERE/'scale-prediction-v1'/unit
        freeze = sealed(directory/'sources.json'); verify_sources(freeze['source_sha256']); verify_sources(freeze['inputs'])
        assert process_ok(sealed(directory/'launch.json'))
        rows.append(sealed(directory/'result.json'))
        for name in ('sources.json', 'launch.json', 'result.json'): inputs[str(directory/name)] = digest(directory/name)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), constrained_layout=True)
    x = np.arange(3)
    axes[0].bar(x-.17, [r['pooled_gain_per_contrast'] for r in rows], .34, label='Pooled')
    axes[0].bar(x+.17, [r['median_track_gain_per_contrast'] for r in rows], .34, label='Median track')
    axes[0].legend(); axes[0].set_ylabel('Conditional log-score gain / contrast')
    for i, r in enumerate(rows):
        tracks = [t for t in r['tracks'] if t['training_tracks']]
        axes[1].scatter(i+np.linspace(-.15, .15, len(tracks)), [t['gain_per_contrast'] for t in tracks], s=15)
    axes[1].set_ylabel('Each multi-group track: gain / contrast')
    for ax in axes: ax.axhline(0, color='gray', linewidth=.8); ax.set_xticks(x, ['DS9', 'DS10', 'DS11']); ax.grid(axis='y', alpha=.2)
    fig.suptitle('Predict residual scale from other tracks in the same satellite group\nFixed data-fitted states; conditional evidence only')
    figure = HERE/'scale-prediction-summary-v1.png'; fig.savefig(figure, dpi=160); plt.close(fig)
    save(HERE/'scale-prediction-summary-v1.json', dict(rows=rows, conditional_signal_all_three=all(r['conditional_signal'] for r in rows),
        inputs=inputs, sources={str(Path(__file__).resolve()):digest(__file__)}, figure_sha256=digest(figure)))


if __name__ == '__main__': main()
