"""Plot saved descriptive diagnostics; no model calls or fitting."""
import csv
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]


def main():
    diagnosis = json.loads((HERE/'diagnosis.json').read_text())
    cold = REPORTS/'2026_10_17_dsx01_iteration4/cold_pipeline/S03-early_to_late'
    prediction = dict(np.load(cold/'held-predictions.npz'))
    current = dict(np.load(cold/'evaluation.npz'))
    original = dict(np.load(REPORTS/'2026_10_16_dsx01_models/results/S03-full-fitted-c-original.npz'))
    original_report = json.loads((REPORTS/'2026_10_16_dsx01_models/results/S03-full-fitted-c-original.json').read_text())
    old_numbers = set(map(int, original_report['full_scan']['total_timing_s']))
    new_numbers = set(map(int, prediction['number']))
    candidate_rows = []
    for number in sorted(old_numbers | new_numbers):
        row = dict(number=number, in_original_bank=number in old_numbers,
            in_cold_bank=number in new_numbers)
        for name, mask in [('train', prediction['train_mask']), ('held', prediction['held_mask'])]:
            before = mask & original['associated'] & (original['satellite_number'] == number)
            after = mask & current['associated'] & (current['satellite_number'] == number)
            row.update({f'original_{name}_assigned':int(before.sum()), f'cold_{name}_assigned':int(after.sum())})
        candidate_rows.append(row)
    with (HERE/'candidate-support.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(candidate_rows[0]))
        writer.writeheader()
        writer.writerows(candidate_rows)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    labels = ['train', 'held']
    x = np.arange(2)
    present = [diagnosis['scopes'][k]['original_winner_present'] for k in labels]
    absent = [diagnosis['scopes'][k]['original_winner_absent'] for k in labels]
    axes[0].bar(x-.18, present, .35, label='Original winner in cold bank', color='#257b97')
    axes[0].bar(x-.18, absent, .35, bottom=present, label='Original winner absent', color='#ce8331')
    axes[0].bar(x+.18, [diagnosis['scopes'][k]['cold_assigned'] for k in labels], .35,
        color='#555555', label='Cold model assigned')
    axes[0].set_xticks(x, labels)
    axes[0].set(title='Full-data labels: descriptive oracle', ylabel='Observations')
    axes[0].legend(fontsize=7)
    data = list(csv.DictReader((HERE/'point-decomposition.csv').open()))
    times = np.array([float(r['time_s']) for r in data])
    rx = np.array([int(r['receiver']) for r in data])
    ch = np.array([int(r['channel']) for r in data])
    delta = np.array([float(r['cold_correction_minus_original_hz']) for r in data])
    centers = np.arange(15., 300., 30.)
    for receiver in [0, 1]:
        for high in [False, True]:
            values = []
            for center in centers:
                use = (rx == receiver) & ((ch >= 5) == high) & (abs(times-center) < 15.)
                values.append(np.median(delta[use]) if use.any() else np.nan)
            axes[1].plot(centers, values, marker='o', label=f'RX{receiver} '+('high' if high else 'low'))
    axes[1].set(title='Cold calibration minus original full fit', xlabel='Capture time (s)', ylabel='Hz; oracle difference')
    axes[1].legend(fontsize=7)
    for field, label in [('same_winner_prediction_delta_hz', 'Total prediction'),
        ('same_winner_orbit_delta_hz', 'Orbit/position/timing'),
        ('cold_correction_minus_original_hz', 'Calibration')]:
        values = np.array([float(r[field]) for r in data])
        use = np.array([r['original_assigned'] == 'True' and r['original_winner_present'] == 'True' for r in data])
        medians = [np.median(abs(values[use & (abs(times-center) < 15.)]))
            if np.any(use & (abs(times-center) < 15.)) else np.nan for center in centers]
        axes[2].plot(centers, medians, marker='o', label=label)
    axes[2].set(title='Same original winner, present in cold bank', xlabel='Capture time (s)', ylabel='Median absolute difference (Hz)')
    axes[2].legend(fontsize=7)
    for axis in axes:
        axis.grid(axis='y', alpha=.2)
    for axis in axes[1:]:
        axis.axvline(149.9750442, color='black', linestyle=':', linewidth=1)
    fig.suptitle('S03 early→late: no fitting; full-data labels/calibration are posthoc diagnostic oracles')
    fig.savefig(HERE/'cold-failure-decomposition.png', dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    main()
