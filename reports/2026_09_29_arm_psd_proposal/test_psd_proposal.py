import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


MODULE_PATH = Path(__file__).with_name("psd_proposal.py")
SPEC = importlib.util.spec_from_file_location("psd_proposal", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
PSD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PSD)

ORACLE_ROOT = Path("/var/tmp/leo-arm-full-search-oracle-allrates")


def _representative_templates() -> dict[int, Path]:
    oracle_path = ORACLE_ROOT / "oracle.json"
    if not oracle_path.exists():
        pytest.skip("all-rates oracle is not available")
    oracle = json.loads(oracle_path.read_text())
    result = {}
    for case in oracle["cases"]:
        rate = int(case["context"]["rate_hz"])
        result.setdefault(rate, ORACLE_ROOT / case["templates"]["exact"]["file"])
    return result


@pytest.mark.parametrize("cfo_hz", [-240_000.0, 240_000.0])
def test_ranks_positive_and_negative_shifts_at_all_native_rates(cfo_hz: float) -> None:
    for rate_hz, template_path in _representative_templates().items():
        template = PSD.load_complex128(template_path)
        time_s = np.arange(template.size) / rate_hz
        shifted = template * np.exp(2j * np.pi * cfo_hz * time_s)
        bank = PSD.make_bank(template, rate_hz)
        result = PSD.propose(shifted, bank)
        assert result["best_cfo_hz"] == cfo_hz, (rate_hz, result)
        assert result["ranking_bin_ids"][0] == result["best_bin_id"]
        assert result["confidence"] > 0.0


@pytest.mark.parametrize("kind", ["zero", "noise"])
def test_uninformative_inputs_produce_finite_results(kind: str) -> None:
    template = np.exp(2j * np.pi * (0.07 * np.arange(4096) + 1e-5 * np.arange(4096) ** 2))
    if kind == "zero":
        iq = np.zeros(50_000, dtype=np.complex128)
    else:
        rng = np.random.default_rng(20260929)
        iq = rng.normal(size=50_000) + 1j * rng.normal(size=50_000)
    result = PSD.rank_cfo_bins(iq, template, 2_500_000)
    assert len(result["ranking_hz"]) == 11
    assert set(result["ranking_hz"]) == set(PSD.ORIGINAL11_CFO_HZ)
    assert np.isfinite(result["confidence"])
    assert np.all(np.isfinite(list(result["scores"].values())))
    if kind == "zero":
        assert result["confidence"] == 0.0
        assert set(result["scores"].values()) == {0.0}


def test_mean_removal_makes_constant_iq_uninformative() -> None:
    estimate = PSD.averaged_psd(np.full(50_000, 3.0 + 4.0j))
    assert np.allclose(estimate, np.full(estimate.size, 1.0 / estimate.size))


def test_rejects_invalid_rate() -> None:
    with pytest.raises(ValueError, match="sample_rate_hz"):
        PSD.rank_cfo_bins(np.ones(2048), np.ones(2048), 0.0)
