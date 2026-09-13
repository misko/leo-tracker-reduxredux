"""Localize adjacent pilots to diagnose fixed-schedule failures, not detect RF."""
import json
from pathlib import Path
import numpy as np
from scipy.signal import zoom_fft
from check_adjacent_pilot_phase import BASE, ROOT, RATE, TRAIN, digest, forecast, cycles, phase_review


def main():
    prior = json.loads((BASE / 'adjacent-pilot-phase-v1.json').read_text())
    manifest = json.loads((ROOT / 'result.json').read_text())
    refs = np.fromfile(BASE / 'direct-references.ci16', dtype='<i2').reshape(4, 3300, 4).astype(float)
    result = dict(scope='adjacent_pilot_localization_and_training_only_timing_forecast',
                  new_rf_samples=0, acceptance_gates_changed=False, native_tracking_qualified=False,
                  false_alarm_calibrated=False, source_sha256=digest(Path(__file__)),
                  helper_sha256=digest(BASE / 'check_adjacent_pilot_phase.py'),
                  prior_sha256=digest(BASE / 'adjacent-pilot-phase-v1.json'), cases=[])
    for old in prior['cases']:
        case = next(c for c in manifest['cases'] if c['label'] == old['label'])
        path = ROOT / case['label'] / 'iq.ci16'
        assert digest(path) == case['input_sha256']
        raw = np.fromfile(path, dtype='<i2').reshape(-1, 2).astype(float)
        iq = raw[:, 0] + 1j * raw[:, 1]
        journal = [json.loads(line) for line in (ROOT / case['label'] / 'stdout.jsonl').read_text().splitlines()]
        resolver = next(r for r in journal if r['kind'] == 2)['cfo_hz']
        grid = np.linspace(resolver - 1000, resolver + 1000, 401)
        localized = []
        for at, phase in old['jobs']:
            best = None
            for quarter in range(-8, 9):
                start, refphase = divmod(at * 4 + phase + quarter, 4)
                ref = refs[refphase, :, 0] + 1j * refs[refphase, :, 1]
                z = iq[start:start + 3300]
                spectrum = zoom_fft(z * ref.conj(), [grid[0], grid[-1]], len(grid), fs=RATE, endpoint=True)
                k = int(np.argmax(abs(spectrum)))
                power = float(abs(spectrum[k]) ** 2 / (np.vdot(ref, ref).real * np.vdot(z, z).real))
                candidate = dict(start=start, reference_phase=refphase, offset_quarters=quarter,
                                 cfo_hz=float(grid[k]), power=power)
                if best is None or power > best['power']:
                    best = candidate
            localized.append(best)
        # Freeze both models at frame 31. Held-out localization is never fitted.
        frames = np.arange(64)
        position = np.array([r['start'] + r['reference_phase'] / 4 for r in localized])
        nominal = old['jobs'][0][0] + frames * RATE / 750
        timing = np.polyfit(frames[:TRAIN], (position - nominal)[:TRAIN], 1)
        predicted = nominal + np.polyval(timing, frames)
        jobs = [divmod(int(round(p * 4)), 4) for p in predicted]
        origin = old['jobs'][0][0]
        local_times = np.array([(r['start'] - origin) / RATE for r in localized])
        carrier = forecast(local_times, [r['cfo_hz'] for r in localized])
        times = np.array([(at - origin) / RATE for at, _ in jobs])
        values = []
        for (at, phase), time in zip(jobs, times):
            ref = refs[phase, :, 0] + 1j * refs[phase, :, 1]
            z = iq[at:at + 3300] * np.exp(-2j * np.pi * cycles(time + np.arange(3300) / RATE, carrier))
            values.append(np.vdot(ref, z) / np.sqrt(np.vdot(ref, ref).real * np.vdot(z, z).real))
        checked = phase_review(times, np.array(values))
        row = dict(label=case['label'], localized=localized, predicted_jobs=jobs,
                   trained_timing_samples_per_frame=float(timing[0]), trained_timing_offset=float(timing[1]),
                   trained_drift_hz_per_second=float(carrier[0]), trained_cfo_hz=float(carrier[1]),
                   forecast_matched_power=[float(abs(v)**2) for v in values],
                   heldout_position_error_samples=(position[TRAIN:] - predicted[TRAIN:]).tolist(),
                   complex_correlations=[[float(v.real), float(v.imag)] for v in values], **checked)
        result['cases'].append(row)
        print(case['label'], 'localized median', np.median([r['power'] for r in localized]),
              'held forecast median', np.median(row['forecast_matched_power'][TRAIN:]),
              'phase RMS', checked['heldout_phase_rms_rad'], 'gain', checked['heldout_coherent_gain'], flush=True)
    with (BASE / 'adjacent-pilot-timing-v1.json').open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')


if __name__ == '__main__':
    main()
