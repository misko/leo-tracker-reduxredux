"""Standalone scientific figures for the prior definitions and replay results."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import run_soft as run
from slope_penalty import penalty

plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})


def save(fig, name):
    for suffix in ('png', 'svg'):
        fig.savefig(run.HERE / f'{name}.{suffix}', dpi=170)
    plt.close(fig)


def plot_priors():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    for ax, cap in zip(axes, (60, 30)):
        x = np.linspace(-cap, cap, 801)
        for kind, color in [('hard', '#1876a3'), ('gaussian', '#d86c29'), ('smooth', '#238b57')]:
            spec = dict(kind='none') if kind == 'hard' else run.PHASES[f'{kind}{cap}']['slope_prior']
            y = [penalty([b, 0.], spec)[0] for b in x]
            ax.plot(x, y, color=color, lw=2, label=kind.capitalize())
        for sign in (-1, 1):
            ax.axvline(sign * cap, color='#444', ls=':', lw=1)
        ax.axvspan(-cap * 1.15, -cap, color='#ddd', alpha=.6)
        ax.axvspan(cap, cap * 1.15, color='#ddd', alpha=.6)
        ax.set(title=f'Hard outer limit ±{cap} Hz/s', xlim=(-cap * 1.15, cap * 1.15), ylim=(-.15, 5.),
               xlabel='One receiver’s fitted slope (Hz/s)', ylabel='Added penalty (NLL units)')
        ax.text(0, 4.6, 'Shaded areas are forbidden for all three', ha='center', fontsize=8)
        ax.grid(alpha=.15); ax.legend(loc='upper center', bbox_to_anchor=(.5, .88), ncol=3, fontsize=8)
    fig.suptitle('Gaussian and smooth priors: equal cost at the limit, different behavior inside')
    save(fig, 'prior_shapes')


def plot_search_case(result, label='N25'):
    """Show retained search regions without using reference data for selection."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Circle, Patch
    from analyze_soft import MAIN, NAMES, read, root, reference_point
    from leo.contracts.regional_position import RegionalPrior
    metadata = read(run.OLD / 'inputs' / label / 'inputs.json')
    evaluation = read(run.OLD / 'evaluation.json')
    reference = [evaluation['reference_latitude_deg'], evaluation['reference_longitude_deg']]
    truth = reference_point(RegionalPrior(**metadata['prior']), reference)
    lookup = {(r['label'], r['phase'], r['arm']): r for r in result['rows']}
    fig, axes = plt.subplots(2, 3, figsize=(13, 9.5), layout='constrained')
    for ax, phase in zip(axes.flat, MAIN):
        folder = root(phase) / 'results' / label / phase
        search, case = read(folder / 'search.json'), read(folder / 'result.json')
        points = search['search']['evaluations']
        xy = np.array([[p['east_km'], p['north_km']] for p in points])
        best = sorted((p for p in points if p['score'] < 1e100), key=lambda p: p['score'])[:25]
        ax.scatter(*xy.T, s=5, color='#bbbbbb', alpha=.55, linewidths=0)
        ax.scatter([p['east_km'] for p in best], [p['north_km'] for p in best],
                   s=12, color='#d86c29', linewidths=0)
        ax.add_patch(Circle((0, 0), 250, fill=False, edgecolor='#aaaaaa', lw=.7))
        status = {tuple(r['point']): r['status'] for r in case['region_status']}
        for basin in case['basins']:
            radius = max(25., basin['spacing_km'] / np.sqrt(2))
            center = (basin['east_km'], basin['north_km'])
            style = (dict(facecolor='#eeeeee', edgecolor='#b35a5a', hatch='///', alpha=.5)
                     if status[center] != 'complete'
                     else dict(facecolor='#1876a3', edgecolor='#1876a3', alpha=.2))
            ax.add_patch(Circle(center, radius, **style))
        ax.scatter(*truth, marker='*', s=130, color='#bd1622', zorder=5)
        selected = case['selections']['fitted-c']['result']
        row = lookup[label, phase, 'fitted-c']
        if selected:
            ax.scatter(*selected['vector'][:2], marker='x', s=55, color='#171717', zorder=6)
        detail = f"{row['error_km']:.2f} km" if row['accepted'] else 'no accepted result'
        ax.set(title=f'{NAMES[phase]}: {detail}', aspect='equal', xlim=(-265, 265), ylim=(-265, 265),
               xlabel='East of starting prior (km)', ylabel='North of starting prior (km)')
        ax.grid(alpha=.12)
    handles = [Line2D([], [], marker='.', color='#bbbbbb', ls='', label='400 evaluated grid points'),
               Line2D([], [], marker='.', color='#d86c29', ls='', label='25 lowest coarse scores'),
               Line2D([], [], marker='o', color='#1876a3', alpha=.4, ls='', label='Retained refinement regions'),
               Patch(facecolor='#eeeeee', edgecolor='#b35a5a', hatch='///', label='Region calibration failed'),
               Line2D([], [], marker='*', color='#bd1622', ls='', label='Reference location'),
               Line2D([], [], marker='x', color='#171717', ls='', label='Selected fitted-c position')]
    fig.legend(handles=handles, loc='outside lower center', ncol=3, fontsize=9)
    explanation = {'N25': 'the ±30 soft priors discard the correct region',
                   'N49': 'Hard 30 and Gaussian 60 discard the correct region',
                   'N64': 'Smooth 60 and Gaussian 30 discard the correct region'}.get(label, 'retained search regions')
    fig.suptitle(f'{label}: {explanation}\n'
                 'Titles show final fitted-c error; reference coordinates are used only for evaluation')
    save(fig, f'{label.lower()}_search_regions')


def plot_results(result):
    from analyze_soft import MAIN, ARMS, NAMES, COLORS
    rows = result['rows']
    plot_priors()
    for label in ('N25', 'N49', 'N64'):
        plot_search_case(result, label)
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), layout='constrained')
    positive = [r['error_km'] for r in rows if r['accepted'] and r['error_km'] > 0]
    lower = min(.05, 10. ** np.floor(np.log10(min(positive))))
    for row_index, arm in enumerate(ARMS):
        for column, phases in enumerate((('sigma2_60', 'gaussian60', 'smooth60'), ('hard30', 'gaussian30', 'smooth30'))):
            ax = axes[row_index, column]
            curves = ('before', *phases) if column == 0 else ('sigma2_60', *phases)
            for phase in curves:
                errors = sorted(r['error_km'] for r in rows if r['phase'] == phase and r['arm'] == arm and r['accepted'])
                color = COLORS.get(phase, '#999999')
                ax.step([lower, *errors, 500], [0, *np.arange(1, len(errors) + 1) / 64 * 100, len(errors) / 64 * 100],
                        where='post', color=color, lw=1.8, ls='--' if phase not in phases else '-', label=NAMES[phase])
            ax.axvline(5, color='#555', ls=':', lw=.8)
            ax.set(title=f'{arm}: ±{60 if column == 0 else 30} Hz/s family', xscale='log', xlim=(lower, 500),
                   ylim=(0, 102), xlabel='Horizontal position error (km)', ylabel='Scans at or below error (% of all 64)')
            ax.grid(alpha=.2); ax.legend(loc='upper left', fontsize=8)
    fig.suptitle('N01–N64: all six main variants use timing σ=2 s')
    save(fig, 'position_comparison')
    fig, axes = plt.subplots(2, 3, figsize=(14, 9), layout='constrained')
    for row_index, arm in enumerate(ARMS):
        for column, (metric, title) in enumerate((('median', 'Median'), ('p90', '90th percentile'), ('maximum', 'Worst accepted'))):
            ax = axes[row_index, column]
            values = [result['summary'][arm][p]['position_error_km'].get(metric, np.nan) for p in MAIN]
            ax.barh(np.arange(len(MAIN)), values, color=[COLORS[p] for p in MAIN])
            ax.set_yticks(range(len(MAIN)), [NAMES[p] for p in MAIN]); ax.invert_yaxis()
            ax.set(title=f'{arm}: {title}', xlabel='Position error (km)')
            maximum = max(v for v in values if np.isfinite(v))
            ax.set_xlim(0, maximum * 1.22)
            for i, v in enumerate(values):
                if np.isfinite(v):
                    ax.text(v + maximum * .02, i, f'{v:.2f}', va='center', fontsize=9)
            ax.grid(axis='x', alpha=.2)
    fig.suptitle('Accuracy summary: median, tail and worst-case errors')
    save(fig, 'accuracy_summary')
    lookup = {(r['label'], r['phase'], r['arm']): r for r in rows}
    phases = MAIN[1:]
    fig, axes = plt.subplots(2, 1, figsize=(17, 6), layout='constrained')
    for ax, arm in zip(axes, ARMS):
        values = np.full((len(phases), 64), np.nan)
        for i, phase in enumerate(phases):
            for j, label in enumerate(run.LABELS):
                b, r = lookup[label, 'sigma2_60', arm], lookup[label, phase, arm]
                if b['accepted'] and r['accepted']:
                    values[i, j] = np.log2(max(r['error_km'], 1e-9) / max(b['error_km'], 1e-9))
        cmap = plt.get_cmap('RdBu_r').copy(); cmap.set_bad('#aaaaaa')
        im = ax.imshow(values, cmap=cmap, vmin=-3, vmax=3, aspect='auto', interpolation='nearest')
        ax.set_yticks(range(len(phases)), [NAMES[p] for p in phases])
        ax.set_xticks(range(64), run.LABELS, rotation=90, fontsize=7)
        ax.set(title=f'{arm}: error ratio versus Hard 60 (σ=2 s)')
        ax.set_xticks(np.arange(-.5, 64, 1), minor=True)
        ax.grid(which='minor', axis='x', color='white', linewidth=.25)
        ax.tick_params(which='minor', bottom=False)
    colorbar = fig.colorbar(im, ax=axes, shrink=.85, pad=.01, ticks=[-3, -2, -1, 0, 1, 2, 3])
    colorbar.ax.set_yticklabels(['≤⅛×', '¼×', '½×', 'Same', '2×', '4×', '≥8×'])
    colorbar.set_label('Blue = lower error; red = higher error; gray = missing result')
    fig.suptitle('Every scan counts: improvements and regressions against the existing hard-60 control')
    save(fig, 'per_scan_changes')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    for ax, arm in zip(axes, ARMS):
        for phase in MAIN:
            stats = result['summary'][arm][phase]
            x, y = stats['median_frequency_rms_hz'], stats['position_error_km'].get('median')
            if x is not None and y is not None:
                ax.scatter([x], [y], s=65, c=COLORS[phase], label=NAMES[phase])
        ax.set(title=arm, xlabel='Median posterior-weighted frequency RMS (Hz)', ylabel='Median position error (km)')
        ax.grid(alpha=.2); ax.legend(fontsize=8)
    fig.suptitle('Frequency fit and position accuracy are separate outcomes')
    save(fig, 'frequency_vs_position')


if __name__ == '__main__':
    plot_priors()
