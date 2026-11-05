"""Render the completed external geometry probe independently of live canaries."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main(path):
    data = json.loads(path.read_bytes())
    assert data['exact'] and not data['runtime_modified']
    for source, sha in data['bindings'].items():
        assert hashlib.sha256(Path(source).read_bytes()).hexdigest() == sha, source
    out = Path(__file__).resolve().parent
    (out / 'geometry-probe.json').write_bytes(path.read_bytes())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        for i, side in enumerate(('baseline', 'candidate')):
            values = [r['seconds'] for r in data['rows'] if r['arm'] == arm and r['side'] == side]
            bars = ax.bar(np.arange(3) + (i - .5) * .36, values, width=.36,
                          color=('#777777', '#3465a4')[i], label=side)
            ax.bar_label(bars, fmt='%.3f', padding=3)
        ax.set(xticks=np.arange(3),
               xticklabels=['Baseline first', 'Candidate first', 'Baseline first'],
               ylabel='Seconds for 50 geometry evaluations', title=arm, ylim=(0, .35))
        ax.legend()
    fig.suptitle('DS26-0002 · exact fixed-phase geometry experiment\n'
                 '600 evaluations · prepared component only · not enabled in inference')
    fig.savefig(out / 'geometry.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    main(parser.parse_args().input)
