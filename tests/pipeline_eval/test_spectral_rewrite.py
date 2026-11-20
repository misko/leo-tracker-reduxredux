from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.winner_bound_spectrum import component
from tools.pipeline_eval.variants import spectral_rewrite as rewrite


class Producer:
    def __init__(self):
        self.fallbacks = 0

    def _validate_glrt_pair(self, exact, control):
        if exact.values.shape != control.values.shape or not np.array_equal(
            exact.times_s, control.times_s
        ):
            raise ValueError("paired GLRT correlations must have identical geometry")

    def _glrt_pair(self, exact, control, *, size):
        self.fallbacks += 1
        self._validate_glrt_pair(exact, control)
        if size == rewrite.SIZE and exact.values.size:
            grid = np.fft.fftfreq(size, exact.symbol_step_s)
            return component(exact.values, grid), component(control.values, grid)
        return (0.0, 0.0), (0.0, 0.0)


def pair(frames, rng, *, zero=False):
    step = 4.4e-6
    times = np.arange(frames)[:, None] / 750 + np.arange(64) * step
    both = []
    for _ in range(2):
        values = (
            np.zeros((frames, 64), complex)
            if zero
            else (rng.normal(size=(frames, 64)) + 1j * rng.normal(size=(frames, 64)))
        )
        both.append(SimpleNamespace(values=values, times_s=times, symbol_step_s=step))
    return both


@pytest.mark.parametrize("batched", (False, True))
def test_both_exact_and_control_spectra_equal_after_varying_reused_shapes(batched):
    rng = np.random.default_rng(721110)
    producer = Producer()
    candidate = rewrite.PairSpectrum(producer, component, batched=batched)
    for frames in (15, 1, 14, 15, 2):
        for zero in (True, False):
            fields = pair(frames, rng, zero=zero)
            expected = producer._glrt_pair(*fields, size=512)
            observed = candidate.scores(*fields)
            assert [v.hex() for row in observed for v in row] == [
                v.hex() for row in expected for v in row
            ]
    assert producer.fallbacks == 10
    assert candidate.workspace is not None if batched else candidate.workspace is None


def test_irregular_geometry_uses_producer_and_mismatched_references_fail_closed():
    producer = Producer()
    candidate = rewrite.PairSpectrum(producer, component)
    exact, control = pair(2, np.random.default_rng(17))
    exact.times_s[0, 3] += 1e-9
    candidate.scores(exact, control)
    assert producer.fallbacks == 1
    control.times_s = control.times_s.copy()
    control.times_s[0, 3] += 1e-9
    with pytest.raises(ValueError, match="identical geometry"):
        candidate.scores(exact, control)


def test_batched_workspace_dispatches_one_transform_per_spectral_step(monkeypatch):
    recorder = []
    fft = np.fft.fft
    ifft = np.fft.ifft

    def forward(values, **args):
        recorder.append(("fft", values.shape, args.get("n")))
        return fft(values, **args)

    def inverse(values, **args):
        recorder.append(("ifft", values.shape, args.get("n")))
        return ifft(values, **args)

    monkeypatch.setattr(np.fft, "fft", forward)
    monkeypatch.setattr(np.fft, "ifft", inverse)
    candidate = rewrite.PairSpectrum(Producer(), component)
    candidate.scores(*pair(14, np.random.default_rng(23)))
    assert recorder == [
        ("fft", (2, 14, 64), 128),
        ("ifft", (2, 128), None),
        ("fft", (2, 512), None),
    ]
