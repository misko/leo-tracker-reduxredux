import ctypes as ct
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3.scout_readout_trial import CODE, Held, distribution, factor_bytes


@pytest.fixture(scope="module")
def readout(tmp_path_factory):
    work = tmp_path_factory.mktemp("scout-readout")
    source = work / "held.c"
    library = work / "held.so"
    private = CODE.read_text().split("/* Mode 0 runs", 1)[0]
    source.write_text("""
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <time.h>
enum { period=13333, samples=200000 };
typedef struct { double r, i; } PortableFineComplex;
typedef struct { double epoch, hz, score; int confirmation; } TimingFirstResult;
typedef struct { unsigned flags; double offset_samples, fractional_residual_hz,
    fractional_exact, fractional_control; } PortableVerifierResult;
typedef struct { PortableFineComplex true_pilot[period], rolled[period]; } TwoCarrierReceiver;
""" + private + """
void measure_blocks(const PortableFineComplex *pilot, const PortableFineComplex *rolled,
                    const int16_t *samples, double epoch, double hz, BlockReadout *result) {
    TwoCarrierReceiver context;
    memcpy(context.true_pilot, pilot, sizeof(context.true_pilot));
    memcpy(context.rolled, rolled, sizeof(context.rolled));
    *result = block_readout(&context, samples, 0, (TimingFirstResult){epoch, hz, 0., 1});
}
""")
    subprocess.run(["cc", "-shared", "-fPIC", "-std=c11", "-O2", source, "-lm", "-o", library], check=True)
    native = ct.CDLL(str(library)).measure_blocks
    native.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_double, ct.c_double, ct.POINTER(Held)]
    native.restype = None
    return native


@pytest.mark.parametrize("template", [0, 1, None])
def test_held_waveform_checks_signed_cfo_and_rolled_negative(readout, template):
    rng = np.random.default_rng(117)
    pilot, rolled = [np.exp(1j * np.pi/2 * rng.integers(0, 4, 13333)) for _ in range(2)]
    samples = np.zeros((200000, 2, 2), dtype=np.int16)
    epoch, coarse, frequency = 8750, -238000., -237810.
    start, length = 88 + 130*44, 4*7*44
    if template is not None:
        for frame in range(14):
            j = (frame*40000 + 1)//3 + epoch + start
            signal = (pilot, rolled)[template][start:start+length]
            rx = 8000*signal*np.exp(2j*np.pi*(frequency*np.arange(length)/1e7 + frame*.177))
            samples[j:j+length, 0] = np.rint(np.column_stack((rx.real, rx.imag))).astype(np.int16)
    result = Held()
    readout(pilot.ctypes.data, rolled.ctypes.data, samples.ctypes.data, epoch, coarse, ct.byref(result))
    assert result.examined
    assert bool(result.accepted) == (template == 0)
    assert bool(result.rolled_accepted) == (template == 1)
    if template == 0:
        assert result.hz == pytest.approx(frequency, abs=2.)
        assert result.exact > .99 and result.control < .1


def test_trace_identity_can_detect_signed_zero_and_single_nonzero_difference():
    negative = (0, 1, -.0, 100., .27, .02)
    positive = (0, 1, .0, 100., .27, .02)
    assert factor_bytes([negative]) != factor_bytes([positive])
    assert distribution([443.892])["p95"] == 443.892
