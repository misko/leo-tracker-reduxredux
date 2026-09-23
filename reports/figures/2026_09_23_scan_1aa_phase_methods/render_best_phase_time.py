"""Separate phase/time views of supported dwells from the frozen replay evidence."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
doc = json.loads((ROOT / 'comparison.json').read_text())
pilots = json.loads((ROOT / 'pilot-method-comparison.json').read_text())
rows = [r for r in doc['visits'] if r['state'] == 'replayed'
        and r['production_relative_phase']['supported']]
assert [r['visit'] for r in rows] == [544, 569, 2138]


def degrees(values):
    return np.degrees(np.angle(np.exp(1j * np.asarray(values))))


def line(ax, t, phase, **kwargs):
    # Insert gaps instead of drawing spurious lines across the wrapping boundary.
    y = degrees(phase)
    tx, yy = [], []
    for i in range(len(y)):
        if i and abs(y[i] - y[i - 1]) > 180:
            tx.append(np.nan)
            yy.append(np.nan)
        tx.append(t[i])
        yy.append(y[i])
    ax.plot(tx, yy, **kwargs)


def canvas(title, subtitle):
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True,
                             sharey=True, layout='constrained')
    fig.suptitle(f'{title}\nscan-fw-1aa1d50103d97388 · {subtitle}', fontsize=13)
    for ax, r in zip(axes, rows):
        ax.set_title(f"Visit {r['visit']} · channel {r['inventory']['target']['channel']}"
                     f" · scan +{r['inventory']['relative_time_s']:.2f} s", loc='left', fontsize=11)
        ax.axvspan(0, 60, color='#e5e7eb', alpha=.45)
        ax.axvline(60, color='gray', linestyle=':', linewidth=1)
        ax.set(xlim=(0, 120), ylim=(-185, 185), yticks=[-180, -90, 0, 90, 180],
               ylabel='Residual RX1 − RX0 phase (°)')
        ax.grid(alpha=.2)
    axes[-1].set_xlabel('Time within each separate dwell (ms)')
    return fig, axes


def save(fig, axes, name, note):
    for ax in axes:
        ax.legend(loc='upper left', fontsize=8, framealpha=.9)
    fig.supxlabel(note, fontsize=9)
    fig.savefig(ROOT / name, dpi=180)
    plt.close(fig)


fig, axes = canvas('Broadband phase tracker', 'three supported replay dwells')
for ax, r in zip(axes, rows):
    points = r['all_band_phase']['rows']
    t = np.array([p['center_sample'] for p in points]) / r['sample_rate_hz'] * 1000
    a = [p['training_band_phase_rad'] for p in points]
    line(ax, t, a, color='#0072B2', linewidth=1.4, marker='.', markersize=3,
         label='A-band phase tracker (normalized response)')
    held = r['held_band_phase']['rows']
    ax.scatter(np.array([p['center_sample'] for p in held]) / r['sample_rate_hz'] * 1000,
               degrees([p['training_band_phase_rad'] + p['held_band_residual_phase_rad']
                        for p in held]), color='#D55E00', marker='x', s=20,
               label='Later B-band phase check')
save(fig, axes, 'best-broadband-phase-vs-time.png',
     'Gray: first 60 ms used to estimate carrier/response. Phase wraps at ±180°; no connection across retunes.')

fig, axes = canvas('Smooth broadband phase estimate', 'A-only selection chose spline_1 in each dwell')
for ax, r in zip(axes, rows):
    fits = r['curve_fits']
    points = r['all_band_phase']['rows']
    ax.scatter(np.asarray(fits['time_s']) * 1000,
               degrees([p['training_band_phase_rad'] for p in points]),
               color='#0072B2', alpha=.35, s=12, label='A-band observations')
    line(ax, np.asarray(fits['time_s']) * 1000, fits['curves_rad'][fits['selected']],
         color='black', linewidth=2, label='A-selected smoothing spline')
    held = r['held_band_phase']['rows']
    rms = fits['B_validation'][fits['selected']]['B_rms_deg']
    ax.scatter(np.array([p['center_sample'] for p in held]) / r['sample_rate_hz'] * 1000,
               degrees([p['training_band_phase_rad'] + p['held_band_residual_phase_rad']
                        for p in held]), color='#D55E00', marker='x', s=20,
               label=f'Later B-band check · {rms:.1f}° RMS discrepancy')
save(fig, axes, 'best-spline-phase-vs-time.png',
     'Offline spline uses A-band data throughout 120 ms. B checks frequency transfer; this is not a future-time forecast.')

fig, axes = canvas('Known-pilot phase estimates', 'shared-residual variants; training-only offset alignment')
for ax, r in zip(axes, rows):
    for method, color, marker, label in [
        ('shared_residual', '#009E73', 'o', 'Shared residual'),
        ('refined_shared', '#CC79A7', 'x', 'Refined shared residual'),
    ]:
        p = next(p for p in pilots if p['visit'] == r['visit'] and p['method'] == method)
        t = np.array([v['time_s'] for v in p['rows']]) * 1000
        aligned = [v['native_pilot_rad'] - p['training_offset_rad'] for v in p['rows']]
        ax.scatter(t, degrees(aligned), color=color, marker=marker, s=65,
                   facecolors='none' if marker == 'o' else color,
                   label=f"{label} · later discrepancy {p['held_rms_deg']:.1f}° RMS")
        if method == 'refined_shared':
            ax.scatter(t, degrees([v['scalar_matched_rad'] for v in p['rows']]),
                       marker='_', color='black', s=220, linewidths=2,
                       label='Broadband scalar phase matched to pilot frames')
            ax.text(.015, .06, f"{p['training_count']} training / {p['held_count']} later pilot estimates",
                    transform=ax.transAxes, fontsize=9)
save(fig, axes, 'best-pilot-phase-vs-time.png',
     'Sparse pilot estimates shown without interpolation. Frame-matched phase gauge differs from A/B plots; agreement is not geometric accuracy.')
print('Rendered three separate phase-versus-time PNGs.')
