import numpy as np

from reports.ALGO08.v3.late_pilot_rescue import Contrast, build, choices, nomination, replacements


def test_frozen_late_contrast_distinguishes_appearance_and_disappearance(tmp_path, monkeypatch):
    library = tmp_path / "contrast.so"
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    build(library)
    detector = Contrast(library)
    rng = np.random.default_rng(715)
    samples = rng.integers(-1000, 1000, size=(200_000, 2, 2), dtype=np.int16)
    late = rng.integers(-4000, 4000, size=(40_000, 2), dtype=np.int16)
    early = rng.integers(-4000, 4000, size=(40_000, 2), dtype=np.int16)
    samples[80_000:, 0] = np.tile(late, (3, 1))
    samples[:80_000, 1] = np.tile(early, (2, 1))
    assert detector.run(samples, 0, 40_000)[0] > 0.75
    assert detector.run(samples, 1, 40_000)[0] < -0.75
    assert abs(detector.run(samples, 0, 38_976)[0]) < 0.25
    phase = 2 * np.pi * np.arange(200_000) * 997 / 40_000
    samples[:, 0] = (12_000 * np.stack((np.cos(phase), np.sin(phase)), axis=-1)).astype(np.int16)
    assert abs(detector.run(samples, 0, 40_000)[0]) < 1e-6


def rows():
    return [dict(visit_index=i // 2, receiver_id=i % 2, anchor=False, short_positive=i % 2 == 0,
                 scores=dict(on_period=i, off_period=-i)) for i in range(24)]


def test_budget_uses_short_misses_and_keeps_periodic_and_hash_sample_blind():
    cohort = rows()
    state = choices(cohort)
    misses = state["misses"]
    assert misses["on_period"]["nominations"] == [(11, 1), (10, 1), (9, 1)]
    assert misses["off_period"]["nominations"] == [(0, 1), (1, 1), (2, 1)]
    assert state["positive_counterfactual"]["on_period"]["nominations"] == [(11, 0), (10, 0), (9, 0)]
    for baseline in ("periodic", "hash"):
        metadata = [dict(visit_index=row["visit_index"], receiver_id=row["receiver_id"]) for row in cohort[1::2]]
        actual = nomination(metadata, baseline)
        assert actual == misses[baseline]["nominations"]
        assert len(set(actual)) == 3
    assert nomination(cohort[:3], "periodic") == []


def test_counterfactual_distinguishes_supported_losses_from_additions():
    def factor(cfo):
        return dict(fractional_tracking_cfo_hz=cfo, integer_epoch_sample=3,
                    fractional_epoch_offset_samples=0., fractional_margin=.2)

    stock, different = factor(11_021), factor(11_922)
    evidence = [(None, None, stock, stock, different, None, ("c0",)),
                (None, None, stock, different, stock, None, ("fitted_c",)),
                (None, None, stock, stock, None, None, ())]
    assert replacements(evidence) == dict(tested=3, dropped=1, displaced=2, strong_lost=3,
                                          installed_match_lost=2, installed_match_gained=1,
                                          c0_owner_match_lost=1, fitted_c_owner_match_lost=0)
