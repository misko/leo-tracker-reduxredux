from dataclasses import replace

import numpy as np
import pytest

import leo.scanner.adaptive_hop_analysis as detector
from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisSource, analyze_adaptive_hop_visit
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tools.qualify_adaptive_hop_analysis import ReplayReader, compare_candidates


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_saved_parity_harness_keeps_only_rx1_and_explicit_modelled_receipt(monkeypatch, rate, edge):
    iq = np.zeros((rate * 120 // 1000, 2), dtype="<i2")
    iq[:] = [12, -5]
    reader = ReplayReader({"rate_hz": rate, "edge": edge, "channel": 3}, iq)
    source = AdaptiveHopAnalysisSource(reader)
    assert source.visits[reader.index].event.target.edge == edge
    assert source.visits[reader.index].event.target.channel == 3
    assert np.all(source.read_visit(reader.index)[:, 0] == 0)
    assert np.all(source.read_visit(reader.index)[:, 1] == 12 - 5j)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    product = analyze_adaptive_hop_visit(source, reader.index)
    reference = _fake_fractional_dwell(
        source.read_visit(reader.index), product.configuration, edge=edge
    )
    counts = compare_candidates(product, reference)
    assert counts == {
        "candidates": 44,
        "fractional_complete": 44,
        "unavailable": 0,
        "integer_vs_fractional_winner_changes": 22,
    }
    changed = replace(reference.probes[0].candidates[0], fractional_margin=0.123)
    probe = replace(reference.probes[0], candidates=(changed, reference.probes[0].candidates[1]))
    with pytest.raises(AssertionError, match="parity"):
        compare_candidates(product, replace(reference, probes=(probe, *reference.probes[1:])))
