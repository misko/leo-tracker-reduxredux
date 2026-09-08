import json

import numpy as np
import pytest

from leo.analysis.starlink.templates import edge_frequencies_hz, qin_edge_pilot_symbols
from tools.presence_structured_challenge import (
    NEGATIVE_KINDS,
    PROTOCOL,
    cases,
    generate,
    structured_waveform,
    summarize,
    symbol_states,
    validate_protocol,
    variant_flags,
)


@pytest.fixture
def protocol():
    return json.loads(PROTOCOL.read_text())


def spec(kind="repeating_qpsk", **changes):
    return (
        dict(
            rate_hz=2500000,
            edge="lower",
            seed=995001,
            kind=kind,
            snr_db=0.0,
            start_ms=0.0,
            duration_ms=120.0,
        )
        | changes
    )


@pytest.mark.parametrize("kind", NEGATIVE_KINDS)
def test_random_states_are_not_cyclic_rolls_of_known_pilots(kind):
    values = symbol_states(kind, 995002, 4)
    assert values.shape == (4, 300, 8)
    for edge in ("lower", "upper"):
        known = qin_edge_pilot_symbols(edge)
        assert all(not np.allclose(values[0], np.roll(known, roll, axis=0)) for roll in range(300))
    if kind.startswith("repeating"):
        np.testing.assert_array_equal(values[0], values[1])
    else:
        assert not np.array_equal(values[0], values[1])
    np.testing.assert_array_equal(values, symbol_states(kind, 995002, 4))
    assert not np.array_equal(values, symbol_states(kind, 995003, 4))


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_continuous_symbol_model_matches_direct_interior_sample_equations(rate, edge):
    epoch = 271.375
    waveform = structured_waveform(rate, edge, epoch, "independent_qam16", 995004)
    # Compare a small independently indexed set, including the previous frame
    # at dwell start and late frames. No interpolation of detector templates.
    states = symbol_states("independent_qam16", 995004, 91)
    frequencies = edge_frequencies_hz(edge)
    for frame in (-1, 0, 1, 34, 88):
        for symbol in (3, 63, 127, 299):
            index = round(epoch + rate * (frame / 750 + (symbol + 0.5) * 4.4e-6))
            if not 0 <= index < len(waveform):
                continue
            time = (index - epoch) / rate
            frame_time = time - frame / 750
            local = frame_time - symbol * 4.4e-6 - 2 / 15 * 1e-6
            expected = np.sum(
                states[frame + 1, symbol - 2] * np.exp(2j * np.pi * frequencies * local)
            ) / np.sqrt(8)
            assert waveform[index] == pytest.approx(expected, abs=2e-9, rel=2e-9)
    assert not waveform.flags.writeable


@pytest.mark.parametrize("kind", NEGATIVE_KINDS + ("pilot", "pilot_plus_tone", "boundary_pilot"))
def test_generation_is_bounded_repeatable_and_labels_are_explicit(protocol, kind):
    description = spec(kind)
    if kind == "pilot_plus_tone":
        description.update(start_ms=40.0, duration_ms=20.0, tone_offset_hz=220000.0)
    if kind == "boundary_pilot":
        description.update(start_ms=38.0, duration_ms=4.0)
    iq, truth = generate(description, protocol)
    np.testing.assert_array_equal(iq, generate(description, protocol)[0])
    assert iq.dtype == np.int16 and iq.shape == (300000, 2)
    assert truth["starlink_model_present"] == (kind not in NEGATIVE_KINDS)
    assert abs(truth["cfo_hz"]) <= 360000
    assert 0 < truth["epoch_samples"] % 1 < 1
    assert 0 <= truth["clipped_components"] <= iq.size


def test_frozen_inventory_has_no_timing_equivalent_negative(protocol):
    inventory = list(cases(protocol))
    assert len(inventory) == len({json.dumps(r, sort_keys=True) for r in inventory}) == 480
    assert sum(r["kind"] in NEGATIVE_KINDS for r in inventory) == 256
    assert sum(r["kind"] in ("pilot", "pilot_plus_tone") for r in inventory) == 144
    assert sum(r["kind"] == "boundary_pilot" for r in inventory) == 80
    assert protocol["negative_kinds"] == list(NEGATIVE_KINDS)
    assert protocol["policy"] == {"minimum_exact_score": 0.175, "minimum_margin": 0.025}
    assert protocol["maximum_confirmations"] == 1 and not protocol["seeded"]
    assert not protocol["absence_policy_enabled"] and not protocol["live_rf_authorized"]
    assert not set(protocol["negative_seeds"]) & set(protocol["positive_seeds"])


def test_summary_keeps_false_flags_and_unassociated_positives_as_failures(protocol):
    negative = dict(
        truth=spec() | {"starlink_model_present": False},
        variants={v: dict(flagged=True, associated=False) for v in protocol["variants"]},
    )
    positive = dict(
        truth=spec("pilot") | {"starlink_model_present": True},
        variants={v: dict(flagged=True, associated=False) for v in protocol["variants"]},
    )
    for result in summarize([negative, positive], protocol).values():
        assert result["nonpilot_flags"] == 1
        assert result["primary_associated"] == 0
        assert not result["bounded_challenge_pass"]
    assert all(not r["bounded_challenge_pass"] for r in summarize([], protocol).values())


@pytest.mark.parametrize(
    "change",
    [
        {"rate_hz": 10},
        {"edge": "bad"},
        {"kind": "wrong_pilot"},
        {"seed": True},
        {"start_ms": -1},
        {"duration_ms": 121},
        {"snr_db": float("nan")},
        {"tone_offset_hz": float("inf")},
        {"tone_offset_hz": 230000},
    ],
)
def test_invalid_or_unbounded_inputs_fail(protocol, change):
    with pytest.raises(ValueError):
        generate(spec() | change, protocol)


@pytest.mark.parametrize(
    "name,amplitude,diversity",
    [
        ("normalized", 0, 0),
        ("amplitude", 1, 0),
        ("normalized-diverse", 0, 1),
        ("amplitude-diverse", 1, 1),
    ],
)
def test_variant_flags_require_explicit_diversity_opt_in(name, amplitude, diversity):
    assert variant_flags(name) == (
        f"-DLEO_PRESENCE_RANK_AMPLITUDE_WEIGHTED={amplitude}",
        f"-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY={diversity}",
    )


def test_unknown_variant_fails():
    with pytest.raises(ValueError, match="unknown"):
        variant_flags("not-a-variant")


def test_support_requires_explicit_variant_and_new_inventory_is_independent():
    assert variant_flags("amplitude-diverse-supported") == (
        *variant_flags("amplitude-diverse"),
        "-DLEO_PRESENCE_ENERGY_SUPPORT=1",
    )
    fresh = json.loads(
        PROTOCOL.with_name("arm-presence-energy-support-challenge-v1.json").read_text()
    )
    validate_protocol(fresh)
    inventory = list(cases(fresh))
    seeds = [s["seed"] for s in inventory]
    assert len(seeds) == len(set(seeds)) == fresh["case_count"] == 576
    assert seeds == list(range(2026098000, 2026098576))
    assert sum(s["kind"] in NEGATIVE_KINDS for s in inventory) == 256
    assert sum(s["kind"] == "boundary_pilot" for s in inventory) == 80
    assert sum(s["kind"] == "pilot" and s["snr_db"] == -6 for s in inventory) == 48
    assert fresh["optimized_arithmetic"]


def test_symbol_support_is_explicit_and_uses_fresh_disjoint_seeds():
    assert variant_flags("amplitude-diverse-symbol-supported") == (
        *variant_flags("amplitude-diverse-supported"),
        "-DLEO_PRESENCE_ENERGY_SYMBOL_SUPPORT=1",
    )
    new = json.loads(
        PROTOCOL.with_name("arm-presence-symbol-support-challenge-v1.json").read_text()
    )
    old = json.loads(
        PROTOCOL.with_name("arm-presence-energy-support-challenge-v1.json").read_text()
    )
    validate_protocol(new)
    inventory = list(cases(new))
    seeds = {r["seed"] for r in inventory}
    assert len(seeds) == len(inventory) == 576
    assert not seeds.intersection(r["seed"] for r in cases(old))
    for key in old:
        if key not in ("scope", "interpretation", "variants", "independent_case_seed_base"):
            assert new[key] == old[key], key


@pytest.mark.parametrize(
    "change",
    [
        {"independent_case_seed_base": True},
        {"independent_case_seed_base": -1},
        {"independent_case_seed_base": 2**32 - 1},
        {"independent_case_seed_base": 1, "case_count": 4097},
        {"optimized_arithmetic": "true"},
    ],
)
def test_invalid_new_challenge_options_fail(protocol, change):
    with pytest.raises(ValueError, match="unreviewed"):
        validate_protocol(protocol | change)


@pytest.mark.parametrize(
    "change",
    [
        {"variants": []},
        {"variants": ["amplitude", "amplitude"]},
        {"variants": ["amplitude", "unknown"]},
        {"variants": [None]},
        {"variants": "amplitude"},
        {"maximum_confirmations": 2},
        {"receiver": 0},
        {"seeded": True},
        {"dwell_ms": 100},
        {"absence_policy_enabled": True},
        {"live_rf_authorized": True},
        {"policy": {"minimum_exact_score": 0.17, "minimum_margin": 0.025}},
    ],
)
def test_unreviewed_protocol_fails_before_execution(protocol, change):
    with pytest.raises(ValueError, match="unreviewed"):
        validate_protocol(protocol | change)


def test_holdout_preserves_model_policy_and_uses_disjoint_seeds(protocol):
    holdout = json.loads(PROTOCOL.with_name("arm-presence-structured-holdout-v1.json").read_text())
    validate_protocol(protocol)
    validate_protocol(holdout)
    assert holdout["variants"] == ["amplitude", "amplitude-diverse"]
    assert len(list(cases(holdout))) == holdout["case_count"] == 480
    seed_keys = ("negative_seeds", "positive_seeds", "boundary_seeds")
    original_seeds = {s for k in seed_keys for s in protocol[k]}
    fresh_seeds = [s for k in seed_keys for s in holdout[k]]
    assert len(set(fresh_seeds)) == len(fresh_seeds)
    assert not original_seeds.intersection(fresh_seeds)
    for key in protocol:
        if key not in (*seed_keys, "scope", "interpretation", "variants"):
            assert holdout[key] == protocol[key], key
