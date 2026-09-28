"""Independent wrapped-CZT check using host single-precision FFTW and saved IQ.

Numerical qualification only: this is not an ARM timing or hit-recovery run.
"""
import ctypes as ct
import ctypes.util
import hashlib
import json
from pathlib import Path

import numpy as np


class FFT:
    def __init__(self, length):
        self.lib = ct.CDLL(ctypes.util.find_library("fftw3f"))
        self.lib.fftwf_plan_dft_1d.argtypes = [ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_uint]
        self.lib.fftwf_plan_dft_1d.restype = ct.c_void_p
        self.lib.fftwf_execute.argtypes = [ct.c_void_p]
        self.lib.fftwf_destroy_plan.argtypes = [ct.c_void_p]
        self.a = np.zeros(length, np.complex64)
        self.b = np.zeros(length, np.complex64)
        self.plans = {sign: self.lib.fftwf_plan_dft_1d(length, self.a.ctypes.data, self.b.ctypes.data, sign, 64) for sign in (-1, 1)}
        assert all(self.plans.values())

    def run(self, values, sign):
        self.a[:] = values
        self.lib.fftwf_execute(self.plans[sign])
        return self.b.copy()

    def close(self):
        for plan in self.plans.values():
            self.lib.fftwf_destroy_plan(plan)


def main():
    folder = Path('/var/tmp/leo-arm-full-search-oracle-allrates')
    manifest = json.loads((folder / 'oracle.json').read_text())
    rows = []
    for case in manifest['cases']:
        rate = case['context']['rate_hz']
        ref = case['templates']['exact']
        assert hashlib.sha256((folder / ref['file']).read_bytes()).hexdigest() == ref['sha256']
        template = np.fromfile(folder / ref['file'], dtype='<c16')
        n, nf = len(template), 41
        length = 1 << (n + nf - 2).bit_length()
        fft = FFT(length)
        theta = 2 * np.pi * 100 / rate
        k = np.arange(n)
        chirp = np.exp(-.5j * theta * k * k).astype(np.complex64)
        d = np.arange(-(n - 1), nf)
        kernel = np.zeros(length, np.complex64)
        kernel[d % length] = np.exp(.5j * theta * d * d).astype(np.complex64)
        kernel_fft = fft.run(kernel, -1)
        direct_basis = np.exp(-1j * theta * np.arange(nf)[:, None] * k)
        for rx in case['receivers']:
            ref = rx['raw_probe']
            assert hashlib.sha256((folder / ref['file']).read_bytes()).hexdigest() == ref['sha256']
            samples = np.fromfile(folder / ref['file'], dtype='<c16')
            for candidate in rx['retained_candidates'][:2]:
                epoch = candidate['refined_epoch_sample']
                f0 = candidate['residual_cfo_hz'] - 2000 + .12345
                base = np.conj(template) * np.exp(-2j * np.pi * f0 * k / rate)
                exact, screen = np.zeros(nf), np.zeros(nf)
                frames = 0
                for frame in range(16):
                    start = epoch + int(np.floor(frame * rate / 750 + .5))
                    if start + n > len(samples):
                        break
                    x = samples[start:start + n]
                    denom = np.sqrt(np.vdot(template, template).real * np.vdot(x, x).real)
                    weighted = x * base
                    a = np.zeros(length, np.complex64)
                    a[:n] = weighted.astype(np.complex64) * chirp
                    got = fft.run(fft.run(a, -1) * kernel_fft, 1)[:nf] / np.float32(length)
                    if denom:
                        exact += np.abs(direct_basis @ weighted) / denom
                        screen += np.abs(got.astype(np.complex128)) / denom
                    frames += 1
                exact /= frames
                screen /= frames
                guard = 128 * np.finfo(np.float32).eps
                winner = int(np.argmax(exact))
                rows.append(dict(rate_hz=rate, ordinal=case['context']['ordinal'], receiver_id=rx['receiver_id'], rank=candidate['rank'], frames=frames, bins=nf, max_score_error=float(np.max(np.abs(exact-screen))), exact_winner=winner, winner_retained=bool(screen[winner] >= np.max(screen)-2*guard)))
        fft.close()
    result = dict(kind='host numerical check; not ARM or end-to-end recovery', embedding='wrapped kernel, output index j', oracle_sha256=hashlib.sha256((folder/'oracle.json').read_bytes()).hexdigest(), cases=rows, max_score_error=max(r['max_score_error'] for r in rows), all_winners_retained=all(r['winner_retained'] for r in rows))
    Path(__file__).with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'}, indent=2))
    assert result['all_winners_retained']


if __name__ == '__main__':
    main()
