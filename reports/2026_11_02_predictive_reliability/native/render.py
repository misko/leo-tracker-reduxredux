"""Visualize held native CFO without fitting or model selection."""
import importlib.util
from pathlib import Path
import textwrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def segments(times, maximum_gap=5.):
    return np.split(np.arange(len(times)), np.flatnonzero(np.diff(times) > maximum_gap) + 1)


def render(case, split, target, endpoints, output):
    output = Path(output)
    output.mkdir(exist_ok=True)
    channels = sorted({(int(rx), int(ch)) for _, arrays, _ in endpoints
                       for rx, ch, family in zip(arrays['receiver'], arrays['channel'], arrays['family'], strict=True)
                       if family == target})
    if not channels:
        fig, ax = plt.subplots(figsize=(11, 3))
        ax.axis('off')
        ax.text(.5, .5, f'{case} {split}\nNo completed supported saved target endpoint\nNO REFIT; missing endpoints were not rerun',
                ha='center', va='center', transform=ax.transAxes)
    else:
        fig, axes = plt.subplots(len(channels), 3, figsize=(16, 3.0 * len(channels)), squeeze=False)
        colors = {1.: '#2563a5', 4.: '#d05e20'}
        for row_index, (receiver, channel) in enumerate(channels):
            observed_drawn = False
            for scale, arrays, metadata in endpoints:
                use = (arrays['family'] == target) & (arrays['receiver'] == receiver) & (arrays['channel'] == channel)
                if not use.any():
                    continue
                t = arrays['time_s'][use]
                if not observed_drawn:
                    axes[row_index, 0].scatter(t, arrays['observed_native_hz'][use], s=10, c='black', label='held native CFO', zorder=5)
                    axes[row_index, 1].scatter(t, arrays['observed_lifted_hz'][use], s=10, c='black', label='held lifted CFO', zorder=5)
                    observed_drawn = True
                color = colors[float(scale)]
                label = f'SD{scale:g}'
                first = True
                for fragment in np.unique(arrays['fragment'][use]):
                    indices = np.flatnonzero(use & (arrays['fragment'] == fragment))
                    indices = indices[np.argsort(arrays['time_s'][indices])]
                    for segment in segments(arrays['time_s'][indices]):
                        selected = indices[segment]
                        at = arrays['time_s'][selected]
                        axes[row_index, 0].plot(at, arrays['prediction_native_branch_hz'][selected], '.-', ms=3, lw=1.2,
                            color=color, label=label + ' full prediction' if first else None)
                        axes[row_index, 1].plot(at, arrays['orbital_conditional_hz'][selected], ':', lw=1.4,
                            color=color, label=label + ' trained orbit only' if first else None)
                        axes[row_index, 1].plot(at, arrays['prediction_lifted_hz'][selected], '.-', ms=3, lw=1.2,
                            color=color, label=label + ' full prediction' if first else None)
                        std = np.sqrt(arrays['predictive_variance_hz2'][selected])
                        axes[row_index, 1].fill_between(at, arrays['prediction_lifted_hz'][selected] - std,
                            arrays['prediction_lifted_hz'][selected] + std, color=color, alpha=.1)
                        axes[row_index, 2].plot(at, arrays['residual_hz'][selected], '.-', ms=4, lw=.9,
                            color=color, label=label + ' held residual' if first else None)
                        first = False
                if scale == endpoints[0][0]:
                    for graph in metadata['fragment_graph']:
                        if graph['receiver'] != receiver or graph['channel'] != channel:
                            continue
                        full_times = np.sort(np.asarray(graph['times_s']))
                        boundaries = [float(full_times[0]), float(full_times[-1])]
                        for piece in graph['pieces']:
                            boundaries += [float(piece[key]) for key in ('start_s', 'end_s') if key in piece]
                        for ax in axes[row_index]:
                            for boundary in set(boundaries):
                                ax.axvline(boundary, lw=.6, color='.55', alpha=.45)
                            for left, right in zip(full_times[:-1], full_times[1:], strict=True):
                                if right - left > 5:
                                    ax.axvspan(left, right, color='.5', alpha=.08)
            for column, ax in enumerate(axes[row_index]):
                ax.set_xlabel('Seconds from scan origin')
                ax.set_ylabel(f'RX{receiver} CH{channel}\nCFO (Hz)' if column < 2 else f'RX{receiver} CH{channel}\nObserved − prediction (Hz)')
                ax.grid(alpha=.18)
                if row_index == 0:
                    ax.set_title(('Native graph CFO branch', 'Alias-lifted orbit and full prediction; ±1 model SD', 'Held residual')[column])
                    ax.legend(fontsize=8, loc='best')
            axes[row_index, 2].axhline(0, color='black', lw=.6)
        flags = []
        for scale, _, metadata in endpoints:
            qualified = metadata['saved_numerical_fit_qualified']
            flags.append(f'SD{scale:g}: ' + ('qualified' if qualified else 'UNQUALIFIED: ' + ', '.join(metadata['saved_unqualified_reasons'])))
        subtitle = '\n'.join(textwrap.fill(flag, 155) for flag in flags)
        fig.suptitle(f'{case} · family {target} · {split} · fitted c · NO REFIT\n{subtitle}',
                     fontsize=11, color='#a12020' if any(not meta['saved_numerical_fit_qualified'] for _, _, meta in endpoints) else 'black')
        fig.text(.01, .01, 'Held points only. Fixed graph/aliases/identity; train-only calibration. Lines stop at fragments and gaps >5 s. '
                 'Gray boundaries/gaps come from the graph. Bands are local moment-Gaussian model SDs, not calibrated intervals.', fontsize=8)
        fig.tight_layout(rect=(0, .035, 1, .88 if len(channels) == 1 else .91))
    fig.savefig(output / f'{case}_{split}.png', dpi=150)
    plt.close(fig)
