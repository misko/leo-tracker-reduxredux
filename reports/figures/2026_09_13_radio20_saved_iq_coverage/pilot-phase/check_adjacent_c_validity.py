"""Unchanged C moments/gates on offline localized pilots and causal forecasts."""
import ctypes as c
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from tests.starlink_glrt.test_tracking_solver import Moments, moments
from tests.starlink_glrt.test_native_solver import Estimate, dense_fit
from validate_native_admission import rotated

BASE = Path(__file__).parent
FW = Path('/home/mouse9911/gits/plutosdr-fw-radio20-tracking')
RATE = 2500000
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    source = BASE / 'adjacent-pilot-timing-v1.json'
    prior = json.loads(source.read_text())
    manifest_path = BASE / 'missed-candidate-replay-v1/result.json'
    manifest = json.loads(manifest_path.read_text())
    binary = BASE / 'adjacent-c-validity-v1.so'
    assert not binary.exists()
    sources = [FW / 'tools/glrt_tracking_iq.c', FW / 'tools/glrt_native_solver.c']
    subprocess.run(['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                    *map(str, sources), '-lm', '-o', str(binary)], check=True)
    lib = c.CDLL(str(binary))
    ptr = c.POINTER(c.c_int16)
    collect = lib.glrt_tracking_iq_moments_2500000
    collect.argtypes = [ptr, ptr, c.c_size_t, c.c_uint64, c.c_uint32, c.c_uint32, c.POINTER(Moments)]
    solve = lib.glrt_tracking_solve
    solve.argtypes = [c.c_uint32, c.c_uint32, c.POINTER(Moments), c.POINTER(Estimate)]
    refpath = BASE / 'direct-references.ci16'
    assert digest(refpath) == '78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2'
    refs = np.fromfile(refpath, dtype='<i2').reshape(4, 3300, 4)
    bases = []
    for raw in refs.astype(float):
        ref = raw[:, 0] + 1j * raw[:, 1]
        bases.append(np.column_stack((ref, -raw[:, 2] - 1j * raw[:, 3],
                                      1j * np.pi * 1000 / RATE * (2 * np.arange(3300) - 3299) * ref)))
    checks = 0

    def evaluate(iq, frame, at, phase, frequency):
        nonlocal checks
        step = round(frequency / RATE * 2**32) % 2**32
        cut = np.ascontiguousarray(iq[at:at + 3300]); ref = np.ascontiguousarray(refs[phase])
        data = Moments(); out = Estimate()
        assert collect(cut.ctypes.data_as(ptr), ref.ctypes.data_as(ptr), 3300, at, 0, step, c.byref(data)) == 0
        assert solve(RATE, phase, c.byref(data), c.byref(out)) == 0
        z = rotated(cut, 0, step)
        assert list(data.words) == list(moments(z, ref.astype(np.int64)).words)
        correction, coherence, _ = dense_fit(bases[phase], z)
        np.testing.assert_allclose([out.delay * 1e6, out.residual / 1000],
                                   np.clip(correction, -.25, .25), rtol=2e-10, atol=2e-11)
        np.testing.assert_allclose(out.coherence, coherence, rtol=2e-12, atol=2e-14)
        rejection = (32 if np.any(abs(correction) >= .25) else 0) | (64 if coherence < .05 else 0)
        assert out.rejection == rejection
        np.testing.assert_allclose(out.cfo, step * RATE / 2**32 + np.clip(correction[1], -.25, .25) * 1000,
                                   rtol=2e-12, atol=2e-8)
        checks += 1
        return dict(frame=frame, start=at, reference_phase=phase, phase_step=step,
                    coherence=out.coherence, rejection=out.rejection, delay_s=out.delay, cfo_hz=out.cfo,
                    moments=list(data.words))

    result = dict(scope='offline_C_gates_on_localized_adjacent_pilots_then_training_only_forecasts',
                  new_rf_samples=0, acceptance_gates_changed=False, native_tracking_qualified=False,
                  false_alarm_calibrated=False, source_sha256=digest(Path(__file__)),
                  binary_sha256=digest(binary), localization_sha256=digest(source),
                  input_manifest_sha256=digest(manifest_path),
                  c_source_sha256={str(p.relative_to(FW)): digest(p) for p in sources}, cases=[])
    for old in prior['cases']:
        case = next(row for row in manifest['cases'] if row['label'] == old['label'])
        path = BASE / 'missed-candidate-replay-v1' / case['label'] / 'iq.ci16'
        assert digest(path) == case['input_sha256']
        iq = np.fromfile(path, dtype='<i2').reshape(-1, 2)
        local = [evaluate(iq, frame, row['start'], row['reference_phase'], row['cfo_hz'])
                 for frame, row in enumerate(old['localized'])]
        accepted = [row for row in local[:32] if row['rejection'] == 0]
        future = []
        row = dict(label=case['label'], localized=local, accepted_training_frames=[r['frame'] for r in accepted])
        if len(accepted) >= 4:
            # All training is frozen at frame 31; no held-out position/CFO enters these fits.
            frames = np.array([r['frame'] for r in accepted])
            origin = local[0]['start']
            positions = np.array([r['start'] + r['reference_phase']/4 + r['delay_s']*RATE for r in accepted])
            timing = np.polyfit(frames, positions - origin - frames * RATE / 750, 1)
            carrier = np.polyfit(frames, [r['cfo_hz'] for r in accepted], 1)
            for frame in range(32, 64):
                position = origin + frame * RATE / 750 + np.polyval(timing, frame)
                at, phase = divmod(round(position*4), 4)
                future.append(evaluate(iq, frame, at, phase, float(np.polyval(carrier, frame))))
            row.update(timing_fit=timing.tolist(), carrier_fit=carrier.tolist())
        row.update(heldout_forecast=future, localized_accepted=sum(r['rejection']==0 for r in local),
                   forecast_accepted=sum(r['rejection']==0 for r in future))
        result['cases'].append(row)
        print(case['label'], 'localized accepted', row['localized_accepted'], '/64',
              'train', len(accepted), '/32', 'forecast', row['forecast_accepted'], '/', len(future), flush=True)
    result['independently_checked_moment_and_dense_fit_records'] = checks
    with (BASE / 'adjacent-c-validity-v1.json').open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')


if __name__ == '__main__':
    main()
