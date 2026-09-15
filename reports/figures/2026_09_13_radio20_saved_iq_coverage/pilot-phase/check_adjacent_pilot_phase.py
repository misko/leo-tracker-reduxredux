"""Bounded saved-IQ adjacent-pilot diagnostic, with no acceptance authority."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.signal import zoom_fft

BASE = Path(__file__).parent
ROOT = BASE / 'missed-candidate-replay-v1'
RATE = 2500000
TRAIN = 32


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schedule(first, frame):
    # Same Q16 period and nearest-even quarter-sample rounding as C scheduler.
    advance = frame * 218453333
    whole, fraction = divmod(advance, 65536)
    phase = round(fraction / 16384)
    return first + whole + phase // 4, phase % 4


def forecast(times, frequency):
    return np.polyfit(np.asarray(times[:TRAIN]) + 1649.5 / RATE,
                      np.asarray(frequency[:TRAIN]), 1)


def cycles(time, carrier):
    return carrier[1] * time + .5 * carrier[0] * time ** 2


def phase_review(times, values):
    design = np.column_stack((times, np.ones(len(times))))
    fitted = np.linalg.lstsq(design[:TRAIN], np.unwrap(np.angle(values[:TRAIN])), rcond=None)[0]
    errors = np.angle(values * np.exp(-1j * (design @ fitted)))
    held = values[TRAIN:] * np.exp(-1j * (design[TRAIN:] @ fitted))
    return dict(residual_frequency_hz=float(fitted[0] / (2 * np.pi)),
                phase_errors_rad=errors.tolist(),
                heldout_phase_rms_rad=float(np.sqrt(np.mean(errors[TRAIN:] ** 2))),
                heldout_coherent_gain=float(abs(held.sum()) ** 2 / np.vdot(held, held).real))


def main():
    times = np.arange(64) / 750
    known = np.array([-4000., 460000.])
    frequency = known[1] + known[0] * (times + 1649.5 / RATE)
    model = forecast(times, frequency)
    np.testing.assert_allclose(model, known, rtol=1e-10)
    changed = frequency.copy(); changed[TRAIN:] += 10000
    np.testing.assert_array_equal(forecast(times, changed), model)
    signal = .2 * np.exp(1j * (.6 + 2 * np.pi * (cycles(times, known) + 12 * times)))
    corrected = signal * np.exp(-2j * np.pi * cycles(times, model))
    review = phase_review(times, corrected)
    assert review['heldout_phase_rms_rad'] < 1e-8
    assert abs(review['heldout_coherent_gain'] - 32) < 1e-10
    assert [schedule(0, f) for f in range(4)] == [(0, 0), (3333, 1), (6666, 3), (10000, 0)]
    n = np.arange(3300)
    grid = np.linspace(459000, 461000, 401)
    peak = zoom_fft(np.exp(2j * np.pi * 460125 * n / RATE),
                    [grid[0], grid[-1]], len(grid), fs=RATE, endpoint=True)
    assert grid[np.argmax(abs(peak))] == 460125

    manifest = json.loads((ROOT / 'result.json').read_text())
    refpath = BASE / 'direct-references.ci16'
    assert digest(refpath) == '78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2'
    refs = np.fromfile(refpath, dtype='<i2').reshape(4, 3300, 4).astype(float)
    result = dict(scope='adjacent_64_pilots_first_32_training_next_32_heldout',
                  sample_rate=RATE, new_rf_samples=0, acceptance_gates_changed=False,
                  native_tracking_qualified=False, false_alarm_calibrated=False,
                  timing_policy='fixed_initial_resolved_start_and_Q16_period_no_timing_feedback',
                  source_sha256=digest(Path(__file__)),
                  input_manifest_sha256=digest(ROOT / 'result.json'), synthetic_checks=6, cases=[])
    for case in manifest['cases']:
        if case['label'] not in ('candidate-0', 'positive', 'control'):
            continue
        root = ROOT / case['label']
        assert digest(root / 'iq.ci16') == case['input_sha256']
        assert digest(root / 'stdout.jsonl') == case['journal_sha256']
        journal = [json.loads(line) for line in (root / 'stdout.jsonl').read_text().splitlines()]
        initial = next(r for r in journal if r['kind'] == 3)
        assert initial['frame'] == initial['reference_phase'] == 0
        resolver = next(r for r in journal if r['kind'] == 2)['cfo_hz']
        raw = np.fromfile(root / 'iq.ci16', dtype='<i2').reshape(-1, 2).astype(float)
        iq = raw[:, 0] + 1j * raw[:, 1]
        grid = np.linspace(resolver - 1000, resolver + 1000, 401)
        jobs = [schedule(initial['first'], frame) for frame in range(64)]
        times = np.array([(at - initial['first']) / RATE for at, _ in jobs])
        frequencies = []; powers = []
        for at, phase in jobs:
            ref = refs[phase, :, 0] + 1j * refs[phase, :, 1]
            z = iq[at:at + 3300]
            spectrum = zoom_fft(z * ref.conj(), [grid[0], grid[-1]], len(grid), fs=RATE, endpoint=True)
            best = int(np.argmax(abs(spectrum)))
            frequencies.append(float(grid[best]))
            powers.append(float(abs(spectrum[best]) ** 2 / (np.vdot(ref, ref).real * np.vdot(z, z).real)))
        # Only the first 32 local peaks train the carrier. Held-out peaks are diagnostics.
        model = forecast(times, frequencies)
        values = []
        for (at, phase), time in zip(jobs, times):
            ref = refs[phase, :, 0] + 1j * refs[phase, :, 1]
            z = iq[at:at + 3300] * np.exp(-2j * np.pi * cycles(time + n / RATE, model))
            values.append(np.vdot(ref, z) / np.sqrt(np.vdot(ref, ref).real * np.vdot(z, z).real))
        values = np.array(values)
        checked = phase_review(times, values)
        row = dict(label=case['label'], jobs=jobs, local_peak_cfo_hz=frequencies,
                   local_peak_power=powers, trained_drift_hz_per_second=float(model[0]),
                   trained_cfo_hz=float(model[1]),
                   forecast_matched_power=(abs(values) ** 2).tolist(),
                   complex_correlations=[[float(a.real), float(a.imag)] for a in values], **checked)
        result['cases'].append(row)
        print(case['label'], 'drift', round(model[0], 2), 'phase RMS', round(checked['heldout_phase_rms_rad'], 4),
              'gain', round(checked['heldout_coherent_gain'], 4), 'power median', round(float(np.median(powers)), 5), flush=True)
    with (BASE / 'adjacent-pilot-phase-v1.json').open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')


if __name__ == '__main__':
    main()
