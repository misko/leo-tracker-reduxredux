"""Plot audited errors and runtime with all planned scans visible."""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluation', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    data = json.loads(args.evaluation.read_text())
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, layout='constrained')
    colors = {'DS9': '#276FBF', 'DS10': '#D97706', 'DS11': '#168570'}
    for dataset, color in colors.items():
        pairs = [(i+1, r) for i, r in enumerate(data['rows'])
                 if r['unit'].startswith(dataset+'-')]
        accepted = [(i, r) for i, r in pairs if r['accepted']]
        axes[0].scatter([i for i, r in accepted], [r['error_m'] for i, r in accepted],
                        color=color, label=dataset, s=28)
        finished = [(i, r) for i, r in pairs if 'runtime_s' in r]
        axes[1].scatter([i for i, r in finished], [r['runtime_s'] for i, r in finished],
                        color=color, s=28)
    for ax in axes:
        for i, r in enumerate(data['rows'], start=1):
            if r['status'] == 'not_finished':
                ax.axvspan(i-.45, i+.45, color='#eeeeee', zorder=0)
            elif not r['accepted']:
                ax.axvline(i, color='crimson', linestyle=':', alpha=.7)
        ax.grid(alpha=.2)
        ax.set_xlim(.5, data['planned_count']+.5)
    axes[0].set_yscale('log')
    axes[0].axhline(1000, color='black', linestyle='--', label='1,000 m median target')
    axes[0].axhline(3000, color='black', linestyle=':', label='3,000 m p90 target')
    axes[0].set_ylabel('Horizontal error (m, logarithmic scale)')
    axes[0].legend(ncol=3, fontsize=9, loc='upper center', bbox_to_anchor=(.5, 1.18))
    axes[1].axhline(60, color='black', linestyle='--', label='60 s median target')
    axes[1].axhline(90, color='crimson', linestyle=':', label='90 s hard limit')
    axes[1].set_ylim(0, max(100, max((r.get('runtime_s', 0) for r in data['rows']), default=0)*1.1))
    axes[1].set_ylabel('Supervised runtime (s)')
    axes[1].set_xlabel('Frozen scan order — grey columns unfinished; red dotted columns rejected')
    axes[1].legend(fontsize=9)
    subtitle = ('Complete regression panel; accuracy uses the existing site reference'
                if data['finished_count'] == data['planned_count'] else
                'Errors shown only for accepted scans; incomplete panel is not a final result')
    fig.suptitle(f"Frozen regression: {data['finished_count']}/64 finished, "
                 f"{data['accepted_count']}/64 accepted\n"
                 +subtitle)
    fig.savefig(args.output, dpi=160)


if __name__ == '__main__':
    main()
