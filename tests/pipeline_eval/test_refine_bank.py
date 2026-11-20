import numpy as np
import pytest

from leo.analysis.starlink import fast_scan_scores
from tools.pipeline_eval.variants import refine_bank

pytestmark = pytest.mark.hardware  # Requires NumPy's X86_V3 FMA complex multiply contract.


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    path = tmp_path_factory.mktemp("refine-bank") / "refine-bank.so"
    refine_bank.compile_bank(path)
    return path


@pytest.fixture(scope="module")
def iq():
    rng = np.random.default_rng(92017)
    x = rng.integers(-32768, 32768, (2, refine_bank.SAMPLES))
    return x[0] + 1j * x[1]


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_integer_scores_reuse_only_matching_probe_and_cfo(library, iq, edge):
    rate = refine_bank.RATE
    bank = refine_bank.RefinementBank(library, fast_scan_scores)
    assert bank.compatible
    candidate = dict(epoch_samples=(0, 13332, 2343), acquired_cfo_hz=(0.0, 332241.23, -57799.72),
                     edge=edge)
    assert bank.integer(iq, rate, **candidate) == bank.original_integer(iq, rate, **candidate)
    offsets = tuple(e for anchor in candidate["epoch_samples"] for e in
                    fast_scan_scores.circular_epoch_grid(anchor, rate))
    frequencies = tuple(np.repeat(candidate["acquired_cfo_hz"], 5))
    batch = dict(epoch_samples=offsets, acquired_cfo_hz=frequencies, edge=edge)
    assert bank.integer(iq, rate, **batch) == bank.original_integer(iq, rate, **batch)
    assert bank.receipts[-1]["reused"] == 3
    assert bank.receipts[-1]["evaluated"] == 12
    assert bank.receipts[-1]["rotation_rows"] == 3

    # Receiver/cache changes expire the saved center even with the same epoch/CFO.
    zeros = np.zeros_like(iq)
    result = bank.integer(zeros, rate, **batch)
    assert all(item.exact_score == item.control_score == 0 for item in result)
    assert bank.receipts[-1]["reused"] == 0
    assert bank.receipts[-1]["evaluated"] == 15


@pytest.mark.parametrize("epoch,offset", [(0, -1.837435548), (13332, 0.203642), (9891, 0.500001)])
def test_continuous_glrt_matches_across_binary_fraction_changes(library, iq, epoch, offset):
    bank = refine_bank.RefinementBank(library, fast_scan_scores)
    kwargs = dict(epoch_sample=epoch, acquired_cfo_hz=632723.2082, edge="upper",
                  fractional_epoch_offset_samples=offset)
    assert bank.fractional(iq, refine_bank.RATE, **kwargs) == bank.original_fractional(
        iq, refine_bank.RATE, **kwargs,
    )
    assert bank.receipts[-1]["weight_rows"] < bank.receipts[-1]["interpolated_samples"]


def test_unsupported_runtime_and_near_integer_use_original(library, iq):
    bank = refine_bank.RefinementBank(library, fast_scan_scores)
    params = dict(epoch_sample=1234, acquired_cfo_hz=100000.0,
                  fractional_epoch_offset_samples=1.0 + 1e-14)
    assert bank.fractional(iq, refine_bank.RATE, **params) == bank.original_fractional(
        iq, refine_bank.RATE, **params,
    )
    assert not bank.receipts
    bank.compatible = False
    params["fractional_epoch_offset_samples"] = 0.83
    assert bank.fractional(iq, refine_bank.RATE, **params) == bank.original_fractional(
        iq, refine_bank.RATE, **params,
    )
    assert not bank.receipts
