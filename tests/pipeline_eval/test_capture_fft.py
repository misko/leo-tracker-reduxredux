"""Exercise the native opt-in, legacy and screened ports, and probe substitution."""

from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.capture_fft_positions import substitute
from tools.pipeline_eval.variants import capture_fft


def test_native_full_grid_routes_screen_and_preserves_unsupported_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    kernel = capture_fft.FullGrid(capture_fft.build(tmp_path / "fft.so"))

    def old(*_):
        return "original"

    observe = []

    def retained(residuals, rows, count, epoch_sep, cfo_sep, epochs):
        assert (residuals, count, epoch_sep, cfo_sep, epochs) == ((0,), 1, 5, 10_000, 10)
        assert np.array_equal(rows[0], np.ones(10))
        return "source peak selector"

    acquisition = SimpleNamespace(
        OFDM_SYMBOL_DURATION_S=0.0001,
        FRAME_RATE_HZ=1000,
        _folded_anchor_score_grid=old,
        _power_prefix=lambda values: np.r_[0, np.cumsum(np.abs(values) ** 2)],
        _retain_score_map_peaks=retained,
    )
    screen = SimpleNamespace(acquire=old)
    args = (np.ones(40, dtype=complex), np.ones(6, dtype=complex), 10000, (0,), (0, 2), 10)
    with kernel.route(acquisition, screen):
        result, picked = screen.acquire(
            acquisition, args, (0,), 1, 5, 10_000, observer=observe.append
        )
        assert np.array_equal(result[0], np.ones(10))
        assert picked == "source peak selector"
        assert observe == [{"path": "fft_full_grid", "columns": 10}]
        outside = (args[0] * 40000, *args[1:])
        assert acquisition._folded_anchor_score_grid(*outside) == "original"
    assert screen.acquire is acquisition._folded_anchor_score_grid is old
    assert [call["applied"] for call in kernel.calls] == [True, False]


def test_partial_iq_substitutes_only_bound_stereo_visits():
    def row(visit, receiver):
        return dict(visit_index=visit, receiver_id=receiver, candidates=[])

    original = [row(v, r) for v in (5, 7) for r in (0, 1)]
    record = {"source": {"probes": original}}
    new_pair = [dict(r, candidates=[{"epoch": 1}]) for r in original[:2]]
    probes, stats = substitute(record, {5: (original[:2], new_pair)})
    assert probes == new_pair + original[2:]
    assert stats == dict(
        total_visits=2, substituted_visits=[5], untouched_visits=1, changed_factor_visits=1
    )
    with pytest.raises(ValueError, match="frozen native probes"):
        substitute(record, {5: (original[2:], new_pair)})
