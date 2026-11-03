"""Protocol tests for segment comparisons on saved IQ."""
import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recorded_segments as replay


def inventory():
    cases = []
    for split in replay.prior.SPLITS:
        for rate in replay.prior.RATES:
            for visit in range(8):
                cases.append({"case_id": f"{split}-{rate}-{visit}", "origin": "real_ds5",
                    "split": split, "rate_hz": rate, "truth_status": "unknown",
                    "session_id": f"session-{split}-{rate}", "visit_index": visit,
                    "source_start_counter": visit * 120,
                    "source_end_counter_exclusive": (visit + 1) * 120})
    return {"cases": cases}


def test_cohort_independent_different_from_prior_and_session_disjoint():
    data = inventory()
    expected = replay.select(data)
    data["cases"].reverse()
    assert replay.select(data) == expected
    assert len(expected) == 24
    assert {c["visit_index"] for c in expected} == {4, 5}
    bad = copy.deepcopy(data)
    bad["cases"][0]["session_id"] = bad["cases"][-1]["session_id"]
    with pytest.raises(ValueError, match="session leaks"):
        replay.select(bad)


def test_window_geometry_is_disjoint_and_receiver_correct():
    raw = np.zeros((120, 2, 2), dtype="<i2")
    raw[:, 0, 0] = np.arange(120)
    raw[:, 1, 1] = np.arange(120)
    np.testing.assert_array_equal(replay.window(raw, 1000, 0, 0), np.arange(20))
    np.testing.assert_array_equal(replay.window(raw, 1000, 1, 40), 1j * np.arange(40, 60))
    with pytest.raises(ValueError, match="geometry"):
        replay.window(raw, 1000, 0, 110)


def test_energy_vectors_equal_actual_sampled_template_energies():
    _, pm, templates = replay.prior.numerical_helpers()
    rate, edge = 2_500_000, templates.StarlinkEdge.LOWER
    actual = replay.energy_vectors(pm, rate, edge)
    for vector, roll in zip(actual, (0, 17), strict=True):
        template = templates.qin_edge_pilot_frame(rate, edge, symbol_roll=roll)
        direct = []
        for symbol in range(2, 258):
            start, stop = round(symbol * rate * 4.4e-6), round((symbol + 1) * rate * 4.4e-6)
            direct.append(np.sum(np.abs(np.asarray(template[start:stop], complex)) ** 2))
        np.testing.assert_allclose(vector, direct, rtol=1e-12, atol=1e-12)
    assert np.ptp(actual[0]) > 0  # The pilot energies are not silently treated as equal.


def test_evidence_is_shared_and_future_frequency_cannot_reselect():
    first = [(np.ones((3, 256), complex) * (i + 1), np.ones((3, 256), complex))
             for i in range(8)]
    later = [(np.ones((3, 256), complex) * (100 - i), np.ones((3, 256), complex))
             for i in range(8)]
    fixed_calls = []
    energy_calls = []
    def score(exact, control, **kwargs):
        energy_calls.append(kwargs["exact_template_energy"])
        item = dict(score=float(exact[0, 0].real), cfo_hz=123., exact_score=1.,
                    control_score=0., control_cfo_hz=444.)
        return {"a": item, "b": item}
    def fixed(exact, control, cfo_hz, **kwargs):
        fixed_calls.append((exact[0, 0], cfo_hz))
        item = dict(score=2., cfo_hz=cfo_hz, exact_score=2.,
                    control_score=1., control_cfo_hz=cfo_hz)
        return {"a": item, "b": item}
    bank = [{"candidate_id": i, "epoch_sample": i, "seed_cfo_hz": 80_000.} for i in range(8)]
    energy = np.arange(1., 257), np.arange(2., 258)
    output, _ = replay.evaluate(bank, first, later, energy, SimpleNamespace(
        score_bank=score, score_at_frequency=fixed))
    assert fixed_calls == [(93, 123.)] * 3  # Candidate7 wins first; later never changes timing.
    for n in replay.CONFIG["sizes"]:
        for value in output[str(n)].values():
            assert value["winner"]["candidate_id"] == 7
            assert value["confirmation_fixed_timing_frequency"]["total_cfo_hz"] == 80_123
            assert value["first_frame_count"] == value["confirmation_frame_count"] == 3
    assert [len(e) for e in energy_calls] == [64] * 8 + [128] * 8 + [256] * 8
    with pytest.raises(ValueError, match="bank mismatch"):
        replay.evaluate(bank[:7], first, later, energy, SimpleNamespace())


def test_injection_is_reproducible_wrong_pattern_distinct_and_power_correct():
    _, _, templates = replay.prior.numerical_helpers()
    edge = templates.StarlinkEdge.LOWER
    exact = replay.injected_signal(templates, 2_500_000, edge, "exact", .35, 44)
    repeated = replay.injected_signal(templates, 2_500_000, edge, "exact", .35, 44)
    wrong = replay.injected_signal(templates, 2_500_000, edge, "roll29", .35, 44)
    np.testing.assert_array_equal(exact, repeated)
    assert not np.allclose(exact, wrong)
    background = np.full(len(exact), 2 + 3j)
    mixed, scale = replay.add_injection(background, exact, -24)
    ratio = np.mean(np.abs(mixed - background) ** 2) / np.mean(np.abs(background) ** 2)
    assert 10 * np.log10(ratio) == pytest.approx(-24)
    assert scale > 0
    with pytest.raises(ValueError, match="positive"):
        replay.add_injection(background, np.zeros_like(exact), -24)


def test_nested_support_and_scale_normalization():
    _, pm, templates = replay.prior.numerical_helpers()
    rng = np.random.default_rng(45)
    samples = rng.normal(size=20_000) + 1j * rng.normal(size=20_000)
    exact, control = replay.extract(pm, samples, 2_500_000, templates.StarlinkEdge.LOWER, 20, 0.)
    assert exact.shape == control.shape and exact.shape[1] == 256
    assert not exact.flags.writeable and not control.flags.writeable
    import segment_methods
    for n in replay.CONFIG["sizes"]:
        a = segment_methods.score_bank(exact[:, :n], control[:, :n])
        b = segment_methods.score_bank(exact[:, :n] * 7j, control[:, :n] * 7j)
        for name in a:
            assert a[name]["score"] == pytest.approx(b[name]["score"], abs=1e-12)
