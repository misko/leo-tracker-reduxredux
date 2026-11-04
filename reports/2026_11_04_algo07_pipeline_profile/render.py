"""Render the timing inventory; measurements from separate runs are not summed."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text())


def main():
    chain = read('position-chain.json')
    publication = read('publication-profile.json')
    native = read('native-full-timing.json')
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout='constrained')
    groups = [
        (axes[0], ['Full native GLRT'], [native['wall_seconds']],
         'Fresh replay · 16 workers', '#496b9b'),
        (axes[1], [r['algorithm'] for r in chain['stages']],
         [r['worker_seconds'] for r in chain['stages']],
         'Recorded production workers · 319.6 s total', '#328a7c'),
        (axes[2], ['Evidence reads (two)', 'Predictions / grid', 'Plot eight PNGs',
                   'Write current revision', 'Other / compatibility writes'],
         [sum(r['seconds'] for r in publication['calls'] if r['stage']=='read_and_validate_evidence'),
          next(r['seconds'] for r in publication['calls']
               if r['stage']=='reconstruct_predictions_and_conditional_grid'),
          next(r['seconds'] for r in publication['calls'] if r['stage']=='render_eight_pngs'),
          next(r['seconds'] for r in publication['calls'] if r['stage']=='write_private_publication'),
          publication['uninstrumented_publication_seconds']],
         'Fresh presentation profile · cProfile enabled', '#b67a34'),
    ]
    for ax, labels, values, title, color in groups:
        bars = ax.barh(labels, values, color=color)
        ax.bar_label(bars, labels=[f'{v:.1f} s' for v in values], padding=4)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=10)
        ax.set_xlabel('Wall seconds (panels have different scales)')
        ax.set_xlim(0, max(values)*1.28)
        ax.grid(axis='x', alpha=.15)
    fig.suptitle('ALGO07 timing inventory — November 4, 14:00:48 UTC fast scan\n'
                 'Same recording; distinct executions. These panels are not an end-to-end sum.',
                 fontsize=13)
    fig.savefig(ROOT / 'timing-inventory.png', dpi=140)
    plt.close(fig)

    hotspots = read('native-hotspots.json')
    rows = hotspots['rows'][:7]
    labels = ['Coarse integer correlation', 'Conditioned frame scores', 'GLRT64 scoring',
              'Normalized frame FFT scores', 'Normalized frame score', 'FFT', 'Array reductions']
    fig, ax = plt.subplots(figsize=(10, 4.5), layout='constrained')
    bars = ax.barh(labels, [r['self_seconds'] for r in rows], color='#496b9b')
    ax.bar_label(bars, fmt='%.2f s', padding=3)
    ax.invert_yaxis()
    ax.set(xlabel='Exclusive self time (seconds)',
           title='Installed GLRT detector: 16 randomly selected paired-receiver windows\n'
                 'Two windows per channel; seed 20261104; shared host')
    ax.set_xlim(0, max(r['self_seconds'] for r in rows)*1.18)
    ax.grid(axis='x', alpha=.2)
    fig.savefig(ROOT / 'native-hotspots.png', dpi=140)
    plt.close(fig)


if __name__ == '__main__':
    main()
