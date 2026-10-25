"""Summarize published metrics; no inference or algorithm selection."""
from pathlib import Path
import hashlib
import json
import subprocess
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
COMMIT = 'dad19ba5ef74744d8234ccb4d461bac8444663aa'
SOURCES = {
    'channels': 'reports/2026_10_24_ds24_channel_halves/summary.json',
    'receiver': 'reports/2026_10_24_ds24_receiver_orbit_controls/report/summary.json',
    'movement': 'reports/2026_10_25_ds24_movement_policy/evaluation/summary.json',
}

def main():
    data, bindings = {}, {}
    (ROOT / 'sources').mkdir(exist_ok=True)
    for name, path in SOURCES.items():
        raw = subprocess.check_output(['git', 'show', f'{COMMIT}:{path}'], cwd=PUBLISHER)
        data[name] = json.loads(raw)
        (ROOT / 'sources' / f'{name}.json').write_bytes(raw)
        bindings[name] = dict(commit=COMMIT, path=path,
                              sha256=hashlib.sha256(raw).hexdigest())
    labels = ['CH1–8 baseline', 'CH1–4 only', 'CH5–8 only',
              'Receiver-specific noise', 'Shared RX1 candidate', 'Held-family movement policy']
    values = []
    for arm in ['c0', 'fitted_c']:
        channel = data['channels']['baseline'][arm]['groups']
        row = [channel[g]['common']['mean_km'] for g in ['all_channels', 'ch1_4', 'ch5_8']]
        for model in ['receiver_specific_noise', 'receiver_fast_rx1_rf50']:
            candidates = [x for x in data['receiver']['summary']
                          if x['model'] == model and x['arm'] == arm and x['variant'] == 'policy']
            assert len(candidates) == 1 and candidates[0]['n'] == 24
            row.append(candidates[0]['mean_km'])
        movement = [x for x in data['movement']['movement_summary']
                    if x['subset'] == 'all24_development' and x['arm'] == arm
                    and x['policy'] == 'movement_gate']
        assert len(movement) == 1 and movement[0]['positions'] == 24
        row.append(movement[0]['mean_km'])
        values.append(row)
    fig, ax = plt.subplots(figsize=(11, 5.7), layout='constrained')
    y = np.arange(len(labels))
    for shift, vals, color, label in [(-.17, values[0], '#2377a6', 'c = 0'),
                                     (.17, values[1], '#d16826', 'Fitted c')]:
        ax.barh(y + shift, vals, height=.31, color=color, label=label)
        for yy, val in zip(y + shift, vals):
            ax.text(val + .025, yy, f'{val:.3f}', va='center', fontsize=10)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 2.3)
    ax.set_xlabel('Mean position error (km), all 24 usable DS24 fast scans')
    ax.set_title('All channels help; tested receiver corrections offer modest gains', loc='left', pad=16)
    ax.legend(loc='lower right')
    ax.grid(axis='x', alpha=.2)
    ax.set_axisbelow(True)
    fig.text(.01, -.04, 'Previously published results, including policy fallbacks. Candidates are separate experiments, not cumulative improvements.\n'
             'Same-site development cohort; no new algorithm promotion. Historical channel association counts are not used here.', fontsize=10)
    for suffix in ['png', 'pdf']:
        fig.savefig(ROOT / f'accuracy_overview.{suffix}', dpi=180, bbox_inches='tight')
    (ROOT / 'overview_metrics.json').write_text(json.dumps(dict(
        labels=labels, c0_mean_km=values[0], fitted_c_mean_km=values[1],
        source_bindings=bindings, no_new_fits=True, cohort_size=24), indent=2) + '\n')

if __name__ == '__main__':
    main()
