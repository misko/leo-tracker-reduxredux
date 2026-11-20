import ctypes as ct

import numpy as np
import pytest

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.variants import fine_batch
from tools.pipeline_eval.variants import portable_coarse as coarse


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    if not fine_batch.supports_host():
        pytest.skip("development build targets the measured x86-64-v3 host")
    return coarse.build(tmp_path_factory.mktemp("portable-coarse"))[0]


@pytest.mark.hardware
def test_selector_preserves_signed_ties_peak_edges_and_strict_wrapped_radius(library):
    lib = ct.CDLL(str(library))
    select = lib.portable_coarse_select
    select.argtypes = (
        ct.c_void_p,
        ct.c_void_p,
        ct.c_uint,
        ct.c_uint,
        ct.c_void_p,
        ct.POINTER(coarse.Peak),
    )
    select.restype = ct.c_uint
    cfo = np.array([10_000.0, -10_000.0, 0.0, 20_000.0])
    values = np.zeros((4, 64), dtype=float)
    values[0, [0, 1, 62, 20]] = 0.5
    values[1, [0, 20, 40]] = 0.5
    values[2, [0, 5, 40]] = 0.49
    values[3, [20, 60]] = 0.49
    mask = np.empty_like(values, dtype=np.uint8)
    peaks = (coarse.Peak * coarse.SEEDS)()
    count = select(values.ctypes.data, cfo.ctypes.data, len(cfo), 64, mask.ctypes.data, peaks)
    expected = acquisition._retain_score_map_peaks(tuple(cfo), tuple(values), 8, 5, 10_000, 64)
    assert [(p.score, p.original_epoch, p.residual_hz) for p in peaks[:count]] == list(expected)
    for p in peaks[:count]:
        assert p.refined_epoch == acquisition._refine_epoch(
            values[p.cfo_lane], p.original_epoch, 64
        )


@pytest.mark.hardware
def test_generated_templates_match_installed_reference_and_control(library):
    for edge in ("lower", "upper"):
        with coarse.Coarse(library, edge) as bank:
            for roll in (0, 17):
                expected = acquisition.qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll)
                assert np.max(abs(bank.template(bool(roll)) - expected)) < 5e-15


@pytest.mark.hardware
def test_raw_ci16_null_receiver_mask_and_truncated_frame_support(library):
    rng = np.random.default_rng(71)
    iq = np.zeros((27_401, 2, 2), dtype=np.int16)
    iq[:, 1, :] = rng.integers(-1000, 1000, (len(iq), 2), dtype=np.int16)
    with coarse.Coarse(library, "upper") as bank:
        assert bank.acquire(iq, 1, 12, (0.0, 1000.0), (-800_000.0, 800_000.0), lane_mask=1) == (
            [],
            [],
        )
        assert bank.acquire(iq, 0, 22, (0.0, 1000.0), (-800_000.0, 800_000.0)) == ([], [])
        found, peaks = bank.acquire(iq, 1, 22, (0.0, 1000.0), (-800_000.0, 800_000.0), lane_mask=2)
        assert len(found) == len(peaks) == 8
        for seed in found:
            assert seed["absolute_hz"] == 1_000 + seed["residual_hz"]
            assert seed["bins"] in (161, 321)
        scores, support = bank.grid()
        assert scores.shape == (21, 13_333)
        bounds = [44 * s + (40_000 * f + 1) // 3 for s in range(2, 302, 14) for f in range(15)]
        expected = (np.array(bounds)[:, None] + np.arange(13_333) + 44 <= len(iq)).sum(axis=0)
        np.testing.assert_array_equal(support, expected)
        assert bank.acquire(iq[:26_620], 1, 12, (0.0, 1000.0), (-800_000.0, 800_000.0)) == ([], [])
        assert bank.grid()[0].shape == (0, 13_333)
