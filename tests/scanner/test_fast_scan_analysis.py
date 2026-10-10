from dataclasses import replace

import numpy as np
import pytest

from leo.contracts.fast_scan import FastScanPolicyV1, FastScanWindowResultV1
from leo.processing.fast_scan import predictor_factory
from leo.scanner.fast_scan_analysis import analyze_window
from leo.storage.fast_scan import FastScanStore, FastSegmentSource
from tests.fast_scan_support import Predictor, detector, recording


def test_pair_gate_shadow_and_invalid_support(tmp_path):
    _, _, doc = FastScanStore(tmp_path / "bulk").ingest(recording(tmp_path / "raw"))
    windows = list(FastSegmentSource(doc["segments"][0]).windows())
    policy = FastScanPolicyV1()
    quiet = analyze_window(windows[0], (0, 1), Predictor(), policy, detector)
    rescued = analyze_window(windows[1], (0, 1), Predictor(), policy, detector)
    assert quiet.status == "skipped_fast_score" and not quiet.receivers
    assert rescued.status == "processed" and len(rescued.receivers) == 2
    assert rescued.sample_start_utc_ns is None and not rescued.qualified_tracking
    assert (
        analyze_window(
            windows[0], (0, 1), Predictor(), FastScanPolicyV1(mode="shadow"), detector
        ).status
        == "processed"
    )
    invalid = replace(
        windows[1], acquisition={**windows[1].acquisition, "validity_includes_guard": False}
    )
    assert (
        analyze_window(invalid, (0, 1), Predictor(), policy, detector).status == "invalid_capture"
    )
    with pytest.raises(ValueError, match="require every"):
        FastScanWindowResultV1.model_validate({**quiet.model_dump(), "status": "processed"})


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_owned_predictor_matches_independent_reference(edge):
    from leo.analysis.starlink.pilot_predictor import pilot_period
    from tools.fast8_cfo_free_checks import prepare_bank, template_features

    # The independent vectorized research oracle does not use the new C fold.
    predictor = predictor_factory(edge, 2)
    rng = np.random.default_rng(20261010)
    samples = rng.integers(-32768, 32767, (50000, 2, 2), dtype=np.int16)
    observed = predictor.score_ci16(samples)
    bank = prepare_bank(pilot_period(edge), pilot_period(edge, 17), (1,))
    for rx in range(2):
        z = samples[:, rx, 0].astype(float) + 1j * samples[:, rx, 1]
        expected = template_features(z, bank)
        assert observed[rx]["margin"] == pytest.approx(expected["margin"], abs=2e-14)
