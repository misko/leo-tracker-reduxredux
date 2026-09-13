"""Offline diagnostic; train on four sparse pilots, predict four unseen pilots.

Local CFO values are previously independently checked C estimates, including
rejected measurements. Their use here conveys no feedback authority.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from check_heldout_pilot_phase import predict

BASE = Path(__file__).parent
ROOT = BASE / 'missed-candidate-replay-v1'
RATE = 2500000


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit_carrier(times, frequency):
    # Only the training partition supplies frequency information.
    center = np.asarray(times) + 1649.5 / RATE
    return np.polyfit(center[:4], np.asarray(frequency)[:4], 1)


def phase_cycles(time, carrier):
    slope, intercept = carrier
    return intercept * time + .5 * slope * time ** 2


def main():
    times = np.arange(8) * .012
    expected = np.array([-4000., 460000.])
    frequency = expected[1] + expected[0] * (times + 1649.5 / RATE)
    carrier = fit_carrier(times, frequency)
    np.testing.assert_allclose(carrier, expected, rtol=1e-10)
    phase = .6 + 2 * np.pi * (phase_cycles(times, expected) + 12 * times)
    corrected = .2 * np.exp(1j * (phase - 2 * np.pi * phase_cycles(times, carrier)))
    checked = predict(times, corrected)
    assert checked['heldout_phase_rms_rad'] < 1e-8
    assert abs(checked['heldout_coherent_gain'] - 4) < 1e-10
    mutated = frequency.copy()
    mutated[4:] += 10000
    np.testing.assert_array_equal(fit_carrier(times, mutated), carrier)

    manifest = json.loads((ROOT / 'result.json').read_text())
    refs_path = BASE / 'direct-references.ci16'
    assert digest(refs_path) == '78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2'
    refs = np.fromfile(refs_path, dtype='<i2').reshape(4, 3300, 4)
    result = dict(scope='four_training_local_cfo_linear_drift_then_heldout_phase',
                  new_rf_samples=0, acceptance_gates_changed=False,
                  false_alarm_calibrated=False, native_tracking_qualified=False,
                  source_sha256=digest(Path(__file__)),
                  phase_helper_sha256=digest(BASE / 'check_heldout_pilot_phase.py'),
                  input_manifest_sha256=digest(ROOT / 'result.json'),
                  synthetic_checks=4, cases=[])
    for case in manifest['cases']:
        root = ROOT / case['label']
        assert digest(root / 'iq.ci16') == case['input_sha256']
        assert digest(root / 'stdout.jsonl') == case['journal_sha256']
        rows = [json.loads(line) for line in (root / 'stdout.jsonl').read_text().splitlines()]
        past = [row for row in rows if row['kind'] == 3][:8]
        assert len(past) == 8
        first = past[0]['first']
        times = np.array([(row['first'] - first) / RATE for row in past])
        frequency = [row['cfo_hz'] for row in past]
        carrier = fit_carrier(times, frequency)
        raw = np.fromfile(root / 'iq.ci16', dtype='<i2').reshape(-1, 2).astype(float)
        iq = raw[:, 0] + 1j * raw[:, 1]
        correlations = []
        for row, start_time in zip(past, times):
            basis = refs[row['reference_phase']].astype(float)
            ref = basis[:, 0] + 1j * basis[:, 1]
            t = start_time + np.arange(3300) / RATE
            z = iq[row['first']:row['first'] + 3300] * np.exp(-2j * np.pi * phase_cycles(t, carrier))
            correlations.append(np.vdot(ref, z) / np.sqrt(np.vdot(ref, ref).real * np.vdot(z, z).real))
        checked = predict(times, correlations)
        row = dict(label=case['label'], frame_numbers=[r['frame'] for r in past],
                   source_first=[r['first'] for r in past], training_cfo_hz=frequency[:4],
                   trained_drift_hz_per_second=float(carrier[0]),
                   trained_frequency_at_first_start_hz=float(carrier[1]),
                   matched_power=[float(abs(a)**2) for a in correlations],
                   complex_correlations=[[float(a.real), float(a.imag)] for a in correlations],
                   **checked)
        result['cases'].append(row)
        print(case['label'], round(carrier[0], 2), round(checked['heldout_phase_rms_rad'], 4),
              round(checked['heldout_coherent_gain'], 4), flush=True)
    with (BASE / 'heldout-pilot-drift-v1.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
