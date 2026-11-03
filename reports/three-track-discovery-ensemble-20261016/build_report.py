"""Package the completed, bounded diagnostics and draw their measured results."""
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

HERE = Path(__file__).resolve().parent
RESULTS = HERE / 'results'
RESULTS.mkdir(exist_ok=True)
SOURCE = Path('/tmp/three-track-discovery-ensemble')
folds = ['early_to_late', 'late_to_early']
labels = ['CH2 · 50–75 s', 'CH4 · 40–100 s', 'CH2 · 170–190 s']
ensemble = {}
for fold in folds:
    for suffix in ['.json', '.training-progress.jsonl']:
        name = fold + '_batched_v2' + suffix
        shutil.copy2(SOURCE / name, RESULTS / name)
    ensemble[fold] = json.loads((RESULTS / (fold + '_batched_v2.json')).read_text())
shutil.copy2(SOURCE / 'polynomial-control.json', RESULTS / 'polynomial-control.json')
for path in Path('/tmp/three-track-acquisition-clutter').glob('*_pass1.json'):
    shutil.copy2(path, RESULTS / ('acquisition_' + path.name))
shutil.copy2('/tmp/three-track-neighbor-calibration-shortlist.json',
             RESULTS / 'neighbor-calibration-shortlist.json')

fig = Figure(figsize=(12, 4.5), layout='constrained')
FigureCanvasAgg(fig)
axes = fig.subplots(1, 2)
summary = []
for ax, fold in zip(axes, folds):
    d = ensemble[fold]
    worst = np.array([max(t['training_rms_hz'] for t in f['arms']['fitted-c']['tracks'])
                      for f in d['families']])
    ax.plot(np.arange(1, len(worst) + 1), np.sort(worst), 'o-', color='#167f9b')
    ax.axhline(200, ls='--', color='#a83e35', label='200 Hz descriptive reference')
    ax.axhline(375, ls=':', color='gray', label='375 Hz descriptive reference')
    ax.set(yscale='log', xlabel='Calibration families sorted by worst training RMS',
           ylabel='Worst of the three training RMS values (Hz)',
           title='Forward fold' if fold == folds[0] else 'Reverse fold')
    ax.grid(alpha=.2)
    ax.legend(fontsize=8)
    summary.append(dict(fold=fold, families=len(worst),
        all_three_training_below_200_hz=int(np.sum(worst <= 200)),
        all_three_training_below_375_hz=int(np.sum(worst <= 375)),
        minimum_worst_training_rms_hz=float(worst.min()),
        elapsed_seconds=d['elapsed_seconds'],
        prediction_oracle_maximum_error_hz=d['batched_prediction_maximum_error_hz']))
fig.suptitle('None of the 24 frozen discovery calibrations fits all three training groups within 200 Hz\n'
             'Full 1,035-candidate search; fitted c; this plot contains training scores only')
fig.savefig(HERE / '01_frozen_family_training.png', dpi=180)

fig = Figure(figsize=(12, 4.7), layout='constrained')
FigureCanvasAgg(fig)
axes = fig.subplots(1, 2)
for ax, fold in zip(axes, folds):
    x = np.arange(3)
    for offset, arm, color in [(-.18, 'fitted-c', '#167f9b'),
                               (.18, 'coefficient-zero-control', '#dc7824')]:
        winner = ensemble[fold]['winners'][arm]
        heights = [t['test_rms_hz'] for t in winner['tracks']]
        bars = ax.bar(x + offset, heights, .36, color=color,
                      label='Fitted c' if arm == 'fitted-c' else 'Delete c; no refit')
        for bar, value in zip(bars, heights):
            ax.text(bar.get_x() + bar.get_width()/2, value*1.06, str(round(value)),
                    ha='center', fontsize=8)
    ax.axhline(375, ls=':', color='gray')
    ax.set(xticks=x, xticklabels=labels, yscale='log', ylim=(60, 8000),
           ylabel='Withheld carrier RMS (Hz)',
           title='Forward fold' if fold == folds[0] else 'Reverse fold')
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=.2)
fig.suptitle('Training-selected frozen calibration families do not recover both temporal folds\n'
             'The zero-coefficient diagnostic deletes c from frozen calibrations; it is not a refitted ablation')
fig.savefig(HERE / '02_frozen_family_test.png', dpi=180)

fig = Figure(figsize=(12, 4.7), layout='constrained')
FigureCanvasAgg(fig)
axes = fig.subplots(1, 2)
for ax, fold in zip(axes, folds):
    for offset, arm, color in [(-.18, 'fitted-c', '#167f9b'), (.18, 'zero-c', '#dc7824')]:
        d = json.loads((RESULTS / f'acquisition_{fold}_{arm}_pass1.json').read_text())
        accepted = d['audit']['accepted']
        heights = [t['test_rms_hz'] for t in d['tracks']]
        bars = ax.bar(np.arange(3) + offset, heights, .36, color=color,
                      alpha=1 if accepted else .5, hatch=None if accepted else '//',
                      label=('Fitted c' if arm == 'fitted-c' else 'Refitted c = 0') +
                            (' · accepted' if accepted else ' · numerical gate failed'))
        for bar, value in zip(bars, heights):
            ax.text(bar.get_x() + bar.get_width()/2, value*1.06, str(round(value)),
                    ha='center', fontsize=8)
    ax.axhline(375, ls=':', color='gray')
    ax.set(xticks=np.arange(3), xticklabels=labels, yscale='log', ylim=(70, 10000),
           ylabel='Withheld carrier RMS (Hz)',
           title='Forward fold' if fold == folds[0] else 'Reverse fold')
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=.2)
fig.suptitle('One acquisition-margin clutter slope does not resolve the reverse fold\n'
             'Matched observations, candidate proposals, priors and optimization budgets')
fig.savefig(HERE / '03_acquisition_clutter_test.png', dpi=180)
(HERE / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
files = [dict(path=str(p.relative_to(HERE)), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
         for p in sorted(HERE.rglob('*')) if p.is_file() and p.name != 'manifest.json'
         and '__pycache__' not in p.parts]
(HERE / 'manifest.json').write_text(json.dumps(dict(scope='Bounded diagnostic results; '
    'no independent satellite identity labels or geographic truth. No production changes.',
    files=files), indent=2) + '\n')
print(json.dumps(dict(files=len(files), summary=summary)))
