"""Readability revision from saved tables only; original report/seal remains intact."""
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import report as r

HERE = Path(__file__).resolve().parent
OUT = HERE/'report02'


def main():
    OUT.mkdir(exist_ok=False)
    seal = json.loads((HERE/'report/seal.json').read_text())
    for p, digest in seal['files'].items():
        if r.sha(p) != digest:
            raise ValueError('initial saved report changed: '+p)
    summary = json.loads((HERE/'report/summary.json').read_text())
    closure = summary['closure_selected']
    laws = ['sampled_deployed', 'sampled_right', 'continuous']
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7), layout='constrained')
    for ax, condition in zip(axes, ('single', 'overlap')):
        for row in closure:
            if not row['sequence'].endswith(condition):
                continue
            y = laws.index(row['law'])+(row['receiver']-.5)*.16
            ax.plot([row['acquired_minus_A_circular_hz'], row['final_minus_A_circular_hz']], [y, y], color='.7')
            ax.scatter(row['acquired_minus_A_circular_hz'], y, color='#cf7c23', marker='x', s=48)
            ax.scatter(row['final_minus_A_circular_hz'], y, color='#1966ad', s=24)
        ax.set_yticks(range(3), ['Deployed sampled', 'Right-boundary sampled', 'Continuous exact period'])
        ax.invert_yaxis(); ax.axvline(0, color='.6', linewidth=.8); ax.grid(alpha=.2)
        if condition == 'overlap':
            ax.set_xscale('symlog', linthresh=1.)
            ax.set_xticks([-1e5, -1e3, -10, 0, 10, 1e3, 1e5], ['−100k', '−1k', '−10', '0', '10', '1k', '100k'])
            ax.minorticks_off(); ax.tick_params(axis='x', labelsize=9)
            ax.set_xlabel('Circular CFO error to A (Hz; symlog)')
        else:
            ax.set_xlim(-.35, .45)
            ax.set_xticks([-.3, -.15, 0, .15, .3, .45]); ax.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
            ax.set_xlabel('Circular CFO error to A (Hz; linear scale)')
        ax.set_title('One source' if condition == 'single' else 'Two coincident-epoch sources')
    fig.legend(handles=[Line2D([], [], marker='x', color='#cf7c23', linestyle='', label='Acquired CFO'),
                        Line2D([], [], marker='o', color='#1966ad', linestyle='', label='Selected final CFO')],
               loc='outside upper center', ncol=2)
    fig.savefig(OUT/'closure_stages.png', dpi=170); plt.close(fig)
    # The actual numerical graph pieces are diagnostic; preserve the insufficient
    # support status visibly instead of equating fitted curves with accepted sources.
    sequences = [s['name'] for s in summary['sequences']]
    graphs = {n: json.loads((HERE/'graphs'/f'{n}.json').read_text()) for n in sequences}
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained', sharex=True)
    for row, base in enumerate(('coincident', 'separated')):
        for col, law in enumerate(('sampled_deployed', 'continuous')):
            ax = axes[row, col]; g = graphs[base+'_'+law]['actual']
            ts = np.arange(16)+.01
            ax.plot(ts, 100000+200*ts, color='black', linestyle='--', linewidth=1, label='True A')
            ax.plot(ts, 103000-200*ts, color='.5', linestyle=':', linewidth=1.5, label='True B')
            for rx, color in ((1, '#1966ad'), (2, '#d67829')):
                rows = [x for x in g['rows'] if x['receiver'] == rx]
                ax.scatter([x['time_s'] for x in rows],
                    [100000+float(r.wrap(x['measured_cfo_hz']-100000)) for x in rows],
                    s=28, marker=('o', 'x')[rx-1], color=color, label=f'RX{rx-1} selected')
                for track in [t for t in g['tracks'] if t['receiver'] == rx]:
                    for piece in track['pieces']:
                        t = np.linspace(piece['start_s'], piece['end_s'], 150)
                        v = np.polynomial.legendre.legval((t-piece['reference_time_s'])/piece['time_scale_s'], piece['coefficients_hz'])
                        ax.plot(t, 100000+r.wrap(v-100000), color=color, alpha=.7, linestyle='-.')
            ax.set_title(f'{base.capitalize()} epochs · '+('deployed sampled' if law == 'sampled_deployed' else 'continuous'))
            ax.set_ylabel('CFO near A’s alias branch (Hz)'); ax.grid(alpha=.2)
            if row == 1:
                ax.set_xlabel('Synthetic time (s; 1 s cadence)')
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncol=4)
    fig.supxlabel('Dash-dot: graph polynomial pieces; ALL displayed tracks have insufficient support.', fontsize=10)
    fig.savefig(OUT/'graph_continuity.png', dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 6), layout='constrained', sharey=True)
    palette = {'A': '#368441', 'B': '#8651aa', 'ambiguous': '#a5a5a5', 'unmatched': '#b83f39'}
    for ax, stage in zip(axes, ('final', 'acquired')):
        for i, name in enumerate(sequences):
            for rx in (0, 1):
                row = next(x for x in summary['graph_summary'] if (x['sequence'], x['stage'], x['receiver']) == (name, stage, rx))
                y = 2*i+rx; left = 0
                for label, color in palette.items():
                    ax.barh(y, row[label], left=left, color=color, height=.7); left += row[label]
                ax.text(16.4, y, f"{row['tracks']} track; {row['mixed_descriptive_tracks']} mixed", va='center', fontsize=8)
        ax.set_title('Actual final CFO graph' if stage == 'final' else 'Same selection, acquired CFO graph')
        ax.set_xlabel('Graph-owned points by descriptive CFO proximity')
        ax.set_xlim(0, 27); ax.set_xticks([0, 4, 8, 12, 16]); ax.grid(axis='x', alpha=.2)
    axes[0].set_yticks(range(8), [f"{n.replace('_sampled_deployed', ' · sampled').replace('_continuous', ' · continuous')} RX{rx}"
        for n in sequences for rx in (0, 1)])
    axes[0].invert_yaxis()
    fig.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c, label=k) for k, c in palette.items()],
               loc='outside upper center', ncol=4)
    fig.supxlabel('ALL tracks: insufficient support. “Mixed” means unique-near-A and unique-near-B labels; no source acceptance.', fontsize=9)
    fig.savefig(OUT/'graph_labels.png', dpi=170); plt.close(fig)
    files = [Path(__file__), *[p for p in OUT.iterdir() if p.is_file()]]
    r.write(OUT/'seal.json', dict(original_report_seal_sha256=r.sha(HERE/'report/seal.json'),
        files={str(p): r.sha(p) for p in files}, saved_artifacts_only=True))


if __name__ == '__main__':
    main()
