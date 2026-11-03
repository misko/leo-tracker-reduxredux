"""Post-experiment nominal temporal-support audit; no IQ reads or position fits."""
import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from leo.application.scanner_trajectory import fractional_glrt64_support_geometry

import run


def nominal_pilot_center(epoch, indices, fs=5_000_000):
    """Mean FFT sample time, reproducing eight-frame demodulator rounding.

    This is geometric support, not a claim about amplitude-weighted frequency
    estimator sensitivity or the interpolation filter's full impulse support.
    """
    centers = []
    ratio = 240_000_000 // fs
    for frame in range(8):
        frame_epoch = epoch + frame * fs / 750
        start = max(0, int(frame_epoch) - round(fs * 10e-6))
        fft_starts = np.rint((frame_epoch-start)*ratio +
                             (np.asarray(indices)+2)*1056 + 16)
        centers.extend(start/fs + (fft_starts+511.5)/240_000_000)
    return float(np.mean(centers))


def summary(values):
    a = np.asarray(values)
    return dict(min=float(a.min()), median=float(np.median(a)), max=float(a.max()),
                median_centered_rms=float(np.sqrt(np.mean((a-np.median(a))**2))))


def main():
    plan = run.read(run.HERE / "plan.json")
    docs, fast, _, _ = run.context(plan)
    wave_path = run.WAVE / "manifest.json"
    wave = run.read(wave_path)
    diagnosis_path = run.HILL / "source_loo/diagnose.py"
    diagnosis = run.module("support_audit_diagnosis", diagnosis_path)
    _, _, _, verified, sidecar, mappings = diagnosis.validate_inputs(0)
    assert [t['track_id'] for t in verified[0]['tracks']] == [t['track_id'] for t in docs[0]['tracks']]
    outcome_path = run.HERE / "outcome.json"
    outcome = run.read(outcome_path)
    assert outcome['plan_sha256'] == run.digest(run.HERE / 'plan.json')
    x = np.asarray(outcome['control']['x'])
    geometry = fast.Stationary(docs[0], plan['config'])
    tracks = {t['track_id']: t for t in docs[0]['tracks']}
    rows = []
    for row in wave['rows']:
        candidate = SimpleNamespace(**row['candidate'])
        support = fractional_glrt64_support_geometry(candidate, sample_rate_hz=5_000_000,
                                                     probe_sample_count=100_000)
        epoch = candidate.integer_epoch_sample + candidate.fractional_epoch_offset_samples
        track = tracks[row['track_id']]
        i = row['observation_index']
        assert track['mask'][i] and track['times_s'][i] == row['time_s']
        j = mappings[0][row['track_id']].index(65512)
        original = geometry.prediction(track, x)[0][j, i]
        arms = {}
        for arm, indices in zip(run.ARMS, (np.arange(64), np.arange(20, 220))):
            delta = nominal_pilot_center(epoch, indices) - support.center_in_probe_samples/5_000_000
            shifted = x.copy()
            shifted[2] += delta
            difference = geometry.prediction(track, shifted)[0][j, i] - original
            arms[arm] = dict(pilot_minus_glrt_center_s=delta,
                             conditional_geometric_frequency_difference_hz=float(difference))
        rows.append(dict(track_id=row['track_id'], observation_index=i, arms=arms))
    summaries = {}
    for track_id in sorted({r['track_id'] for r in rows}):
        summaries[track_id] = {arm: {
            key: summary([r['arms'][arm][key] for r in rows if r['track_id'] == track_id])
            for key in rows[0]['arms'][arm]} for arm in run.ARMS}
    files = [Path(__file__), wave_path, outcome_path, run.HERE/'plan.json', run.HERE/'run.py',
             diagnosis_path, sidecar, Path(inspect.getfile(fractional_glrt64_support_geometry)),
             run.ROOT/'reports/2026_09_27_ds7_header/analyze.py',
             run.ROOT/'reports/2026_09_29_training_waveform/estimator.py']
    result = dict(schema='ds11-nominal-waveform-support-audit/v1',
                  position_refit_performed=False, iq_read=False, reference_used=False,
                  conditional_norad=65512, effective_estimator_weighting_measured=False,
                  summaries=summaries, rows=rows,
                  sources={str(p): run.digest(p) for p in files})
    run.write(run.HERE/'support_audit.json', result)
    print(__import__('json').dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
