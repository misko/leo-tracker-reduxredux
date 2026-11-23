"""Plot the measured saved time and assumed acquisition time from the sealed budget."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


def render(receipt, destination):
    rows = receipt['cases']
    fig, ax = plt.subplots(figsize=(9, 3.9), layout='constrained')
    y = list(range(len(rows)))
    downstream = [row[row['hindsight']]['saved_elapsed_s'] for row in rows]
    acquisition = [row['compressed_MB'] / 292.39 for row in rows]
    targets = [row['baseline_s'] / 2 for row in rows]
    ax.barh(y, downstream, color='#254969', height=0.48)
    ax.barh(y, acquisition, left=downstream, color='#e5f3ed', edgecolor='#467663', hatch='///', height=0.48)
    for pos, (saved, acquire, target) in enumerate(zip(downstream, acquisition, targets)):
        ax.vlines(target, pos - .36, pos + .36, color='#943b25', linewidth=2.6)
        ax.text(saved / 2, pos, f'{saved:.1f} s', va='center', ha='center', color='white')
        ax.text(max(saved + acquire, target) + .6, pos, f'{saved + acquire:.1f} s', va='center', color='#1f373f')
    ax.set(yticks=y, yticklabels=[f"{r['case']}  ·  {'v3' if r['hindsight'] == 'stock' else 'cumulative'}" for r in rows],
           xlim=(0, max(max(targets), max(a + b for a, b in zip(downstream, acquisition))) + 7),
           xlabel='Seconds per recording')
    ax.invert_yaxis()
    ax.tick_params(length=0)
    ax.set_axisbelow(True)
    ax.xaxis.grid(visible=True, color='#d8dfe1', linewidth=.8)
    for side in ax.spines.values():
        side.set_visible(False)
    fig.suptitle('Projected runtime with the more accurate solver on each recording', x=.015, ha='left', weight='bold')
    ax.legend(handles=[Patch(color='#254969', label='Measured saved publication'),
                       Patch(facecolor='#e5f3ed', edgecolor='#467663', hatch='///', label='Acquisition at 292 MB/s (modeled)'),
                       Line2D([], [], marker='|', ms=13, mew=2.6, ls='', color='#943b25', label='Half of raw v3 time')],
              loc='upper center', bbox_to_anchor=(.50, -.24), ncol=3, frameon=False, fontsize=9)
    fig.savefig(destination, dpi=145, bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('png', type=Path)
    args = parser.parse_args()
    render(json.loads(args.receipt.read_text()), args.png)
