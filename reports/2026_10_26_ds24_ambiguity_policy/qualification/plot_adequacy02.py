"""Saved-array presentation revision: label target-fitted dashed curves."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE / 'report'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    for filename, expected in read(HERE / 'RF_seal.json')['files'].items():
        if sha(Path(filename)) != expected:
            raise ValueError('RF seal mismatch: ' + filename)
    targets = read(HERE / 'metadata.json')['targets']
    colors = {'c0': '#0072B2', 'fitted_c': '#D55E00'}
    figure, axes = plt.subplots(4, 2, figsize=(13, 12), constrained_layout=True)
    inputs = [HERE / 'RF_seal.json', HERE / 'metadata.json', Path(__file__)]
    for i, target in enumerate(targets):
        directory = HERE / target['case']
        original = directory / 'c0_original.npz'
        data = np.load(original)
        inputs.append(original)
        times, values = data['times'], data['values']
        center = float(np.median(values))
        left, right = axes[i]
        left.plot(times, (values - center) / 1000, 'o', ms=3, color='.25', label='Complete graph owner')
        available = False
        for arm in ('c0', 'fitted_c'):
            path = directory / (arm + '_adequacy_checkpoint.json')
            if not path.exists():
                continue
            inputs.append(path)
            diagnostic = read(path)['source_diagnostic']
            available = True
            name = 'c = 0' if arm == 'c0' else 'Fitted c'
            raw = np.asarray(diagnostic['conservative_raw_hz'])
            fullmode = np.asarray(diagnostic['fullmode_raw_hz'])
            left.plot(times, (values - raw - center) / 1000, color=colors[arm], lw=1.5,
                      label=name + f", label {diagnostic['norad']}")
            left.plot(times, (values - fullmode - center) / 1000, '--', color=colors[arm], lw=1)
            right.plot(times, diagnostic['conservative_gate']['profile_residual_hz'], 'o-', ms=2.5,
                       color=colors[arm], lw=1, label=name + ' conservative')
            right.plot(times, diagnostic['fullmode_gate']['profile_residual_hz'], '--', color=colors[arm], lw=1,
                       label=name + ' + target-fitted modes')
        if not available:
            right.set_axis_off()
            right.text(.5, .5, 'MAP / adequacy unavailable\nFrozen slot deadline retained',
                       ha='center', va='center', transform=right.transAxes)
        else:
            right.axhline(0, color='.5', lw=.6)
            right.set_title('Profile residuals: dashed means are target-fitted', fontsize=10)
            right.set_ylabel('Profile residual (Hz)')
            right.set_xlabel('Scan time (s)')
            right.legend(fontsize=7, loc='best')
            right.grid(alpha=.2)
        left.set_title(f"{target['case']}: RX{target['receiver']} CH{target['channel']}, {target['points']} complete points", fontsize=11)
        left.set_ylabel('Graph CFO minus median (kHz)')
        left.set_xlabel('Scan time (s)')
        left.grid(alpha=.2)
        left.legend(fontsize=7, loc='best')
    figure.suptitle('A preferred physical label still has to explain a complete source\nDashed curves use target-fitted physical modes; those means are not independently calibrated', fontsize=13)
    outputs = [REPORT / 'source_adequacy02.png', REPORT / 'source_adequacy02.pdf']
    for path in outputs:
        if path.exists():
            raise FileExistsError(path)
        figure.savefig(path, dpi=170)
    plt.close(figure)
    seal = dict(saved_arrays_only=True, presentation_revision_only=True,
        original_figures_preserved=True, scientific_values_changed=False,
        files={str(path): sha(path) for path in inputs + outputs})
    (REPORT / 'adequacy02_seal.json').write_text(json.dumps(seal, indent=2) + '\n')
