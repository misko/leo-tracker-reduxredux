from tools.research.extract_independent_phase_arc import seed_values, training_rows


def test_training_rows_never_return_fresh_held():
    binding = {
        "fresh_random_whole_visit_split": [
            *({"visit_index": index, "partition": "train"} for index in range(15)),
            *({"visit_index": index, "partition": "held"} for index in range(15, 27)),
        ],
        "observations": [{"visit_index": index} for index in range(27)],
    }
    assert [row["visit_index"] for row in training_rows(binding)] == list(range(15))


def test_dealiased_seed_uses_normalized_cfo_not_alias_sign():
    observation = {
        "acquired_cfo_hz": -180_000.0,
        "fractional_tracking_cfo_hz": -179_900.0,
        "normalized_cfo_hz": 47_000.0,
        "rf_normalization_scale": 0.999,
        "dealiased_native_cfo_hz": 47_000.0 / 0.999,
        "relative_alias_index": -1,
    }
    seeds = seed_values(observation)
    assert seeds[-1] == 47_000.0 / 0.999
    assert seeds[-1] > 0
