"""Component checks for first-only selection and shared later confirmation metrics."""

import json

import evaluator
import numpy as np
import pytest


def noise(rng, shape):
    return rng.normal(size=shape) + 1j * rng.normal(size=shape)


def case():
    rng = np.random.default_rng(606)
    times = np.arange(64) * 4.4e-6
    frequency_a, frequency_b = 19 / (512 * 4.4e-6), -7 / (512 * 4.4e-6)
    a = np.exp(2j * np.pi * frequency_a * times)[None] + 0.6 * noise(rng, (3, 64))
    b = np.exp(2j * np.pi * frequency_b * times)[None] * np.repeat(
        np.exp(1j * rng.uniform(-np.pi, np.pi, (3, 8))), 8, axis=1
    )
    first = [(a, noise(rng, (3, 64))), (b, noise(rng, (3, 64)))]
    later = [
        (noise(rng, (4, 64)), noise(rng, (4, 64))),
        (np.broadcast_to(np.exp(2j * np.pi * frequency_b * times), (2, 64)), noise(rng, (2, 64))),
    ]
    bank = [
        dict(candidate_id="a", candidate_rank=4, epoch_sample=137, seed_cfo_hz=10000.0),
        dict(candidate_id="b", candidate_rank=1, epoch_sample=741, seed_cfo_hz=20000.0),
    ]
    kwargs = dict(
        exact_template_energy=np.linspace(0.3, 2.1, 64),
        control_template_energy=np.linspace(0.7, 1.3, 64),
    )
    return bank, first, later, kwargs


def test_first_only_winners_and_total_cfo_are_correct():
    bank, first, later, kwargs = case()
    result = evaluator.evaluate_bank(bank, first, later, **kwargs)
    assert result["status"] == "complete"
    assert result["candidate_count"] == 2
    assert len(result["methods"]) == 17
    assert result["baseline_winner"]["candidate_id"] == "a"
    assert result["methods"]["segment8"]["winner"]["candidate_id"] == "b"
    replacement = [(np.ones_like(a) * 100, np.zeros_like(b)) for a, b in later]
    changed = evaluator.evaluate_bank(bank, first, replacement, **kwargs)
    for method, item in result["methods"].items():
        assert item["winner"] == changed["methods"][method]["winner"]
        winner = item["winner"]
        assert winner["total_cfo_hz"] == winner["seed_cfo_hz"] + winner["residual_cfo_hz"]
    assert (
        result["methods"]["gaussian_coherent"]["same_candidate_max_abs_cfo_change_from_current_hz"]
        == 0
    )


def test_shared_confirmation_metrics_and_fixed_frequency_without_reselection():
    bank, first, later, kwargs = case()
    result = evaluator.evaluate_bank(bank, first, later, **kwargs)
    by_id = {item["candidate_id"]: index for index, item in enumerate(bank)}
    baseline = result["baseline_winner"]
    reference = evaluator._scorer.score_at_frequency(
        *later[by_id[baseline["candidate_id"]]], baseline["residual_cfo_hz"], **kwargs
    )
    for method, item in result["methods"].items():
        winner = item["winner"]
        fixed = evaluator._scorer.score_at_frequency(
            *later[by_id[winner["candidate_id"]]], winner["residual_cfo_hz"], **kwargs
        )
        assert item["own_fixed_confirmation"]["score"] == pytest.approx(fixed[method]["score"])
        for label, name in [
            ("gaussian", "gaussian_coherent"),
            ("phase_kernel32", "phase_kernel32"),
        ]:
            common = item["common_confirmation"][label]
            assert common["winner"]["exact_score"] == pytest.approx(fixed[name]["exact_score"])
            assert common["winner"]["control_score"] == pytest.approx(fixed[name]["control_score"])
            expected_margin = fixed[name]["exact_score"] - fixed[name]["control_score"]
            baseline_margin = reference[name]["exact_score"] - reference[name]["control_score"]
            assert common["winner"]["margin"] == pytest.approx(expected_margin)
            assert common["baseline"]["margin"] == pytest.approx(baseline_margin)
            assert common["margin_difference"] == pytest.approx(expected_margin - baseline_margin)
    for common in result["methods"]["current_coherent_margin"]["common_confirmation"].values():
        assert common["margin_difference"] == 0


def test_fixed_confirmation_calls_use_only_first_winner_cfos_and_cache(monkeypatch):
    bank, first, later, kwargs = case()
    calls = []
    original = evaluator._scorer.score_at_frequency

    def capture(exact, control, cfo_hz, **options):
        calls.append((exact, control, cfo_hz))
        return original(exact, control, cfo_hz, **options)

    monkeypatch.setattr(evaluator._scorer, "score_at_frequency", capture)
    result = evaluator.evaluate_bank(bank, first, later, **kwargs)
    expected = {
        (item["winner"]["candidate_id"], item["winner"]["residual_cfo_hz"])
        for item in result["methods"].values()
    }
    assert len(calls) == result["cost"]["unique_fixed_hypotheses"] == len(expected)
    actual = set()
    for exact, control, frequency in calls:
        index = next(i for i, pair in enumerate(later) if exact is pair[0])
        assert control is later[index][1]
        actual.add((bank[index]["candidate_id"], frequency))
    assert actual == expected


def test_persisted_integer_comparison_uses_unfiltered_original_bank_order():
    bank, first, later, kwargs = case()
    initial = evaluator.evaluate_bank(bank, first, later, **kwargs)
    by_id = {
        item["candidate_id"]: item
        for item in initial["methods"]["current_coherent_margin"]["ranking"]
    }
    for item in bank:
        score = by_id[item["candidate_id"]]
        item.update(
            {persisted: score[field] for field, persisted in evaluator._PERSISTED_FIELDS.items()}
        )
    result = evaluator.evaluate_bank(bank, first, later, **kwargs)
    assert all(count == 2 for count in result["baseline_comparison"]["compared_counts"].values())
    assert all(
        error == 0 for error in result["baseline_comparison"]["max_absolute_errors"].values()
    )
    bank[1]["persisted_integer_compatible"] = False
    bank[1]["persisted_integer_margin"] += 2
    result = evaluator.evaluate_bank(bank, first, later, **kwargs)
    assert result["baseline_comparison"]["entries"][1]["status"] == "incompatible"
    assert all(count == 1 for count in result["baseline_comparison"]["compared_counts"].values())


def test_ids_ranks_and_frame_counts_preserved_and_json_serializable():
    bank, first, later, kwargs = case()
    bank = [
        dict(rank=i, epoch_sample=item["epoch_sample"], seed_cfo_hz=item["seed_cfo_hz"])
        for i, item in enumerate(bank)
    ]
    for pair in first + later:
        for values in pair:
            values.setflags(write=False)
    result = evaluator.evaluate_bank(bank, first, later, **kwargs)
    assert result["source_frame_counts"] == [
        dict(candidate_id=0, first=3, later=4),
        dict(candidate_id=1, first=3, later=2),
    ]
    for item in result["methods"].values():
        counts = result["source_frame_counts"][item["winner"]["candidate_id"]]
        assert item["first_frame_count"] == counts["first"]
        assert item["later_frame_count"] == counts["later"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "change",
    [
        "empty",
        "missing_pair",
        "duplicate_id",
        "duplicate_rank",
        "fractional_epoch",
        "nonfinite_seed",
        "bad_shape",
        "zero_frames",
        "nonfinite_values",
        "nonfinite_persisted",
    ],
)
def test_invalid_evidence_fails_explicitly(change):
    bank, first, later, kwargs = case()
    if change == "empty":
        bank, first, later = [], [], []
    elif change == "missing_pair":
        later.pop()
    elif change == "duplicate_id":
        bank[1]["candidate_id"] = bank[0]["candidate_id"]
    elif change == "duplicate_rank":
        bank[1]["candidate_rank"] = bank[0]["candidate_rank"]
    elif change == "fractional_epoch":
        bank[0]["epoch_sample"] = 137.5
    elif change == "nonfinite_seed":
        bank[0]["seed_cfo_hz"] = np.inf
    elif change == "bad_shape":
        first[0] = (np.ones((2, 63)), np.ones((2, 63)))
    elif change == "zero_frames":
        later[0] = (np.empty((0, 64)), np.empty((0, 64)))
    elif change == "nonfinite_values":
        later[0][0][0, 0] = np.nan
    elif change == "nonfinite_persisted":
        bank[0]["persisted_integer_margin"] = np.nan
    with pytest.raises(ValueError):
        evaluator.evaluate_bank(bank, first, later, **kwargs)


def test_wrong_fft_or_missing_real_energies_rejected():
    bank, first, later, kwargs = case()
    with pytest.raises(ValueError, match="512"):
        evaluator.evaluate_bank(bank, first, later, fft_size=256, **kwargs)
    kwargs["exact_template_energy"] = np.zeros(64)
    with pytest.raises(ValueError):
        evaluator.evaluate_bank(bank, first, later, **kwargs)
