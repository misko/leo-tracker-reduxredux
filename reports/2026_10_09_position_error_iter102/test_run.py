"""Synthetic actual two-state driver controls without recording access."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location("driver102", Path(__file__).with_name("run.py"))
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def test_two_independent_saved_states_and_exact_budget(tmp_path, monkeypatch):
    for key in ("HERE", "ROOT", "PREFIT"):
        monkeypatch.setattr(driver, key, tmp_path)
    (tmp_path / "protocol.json").write_text(
        json.dumps(
            dict(
                maximum_attempts=2,
                maximum_rounds=2,
                maximum_evaluations_per_attempt=100,
                source_sha256={},
                session_id="synthetic",
            )
        )
    )
    (tmp_path / "published-v3.json").write_text(json.dumps({"manifest": {"document": {}}}))
    (tmp_path / "verified-checkpoints.json").write_text("{}")
    first, second = np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 7.0])
    monkeypatch.setattr(
        driver.replay_prefit,
        "reconstruct",
        lambda *args: ("prefit", first, {"original_objective": 4}),
    )
    monkeypatch.setattr(
        driver.postfit, "reconstruct", lambda: ("postfit", second, {"saved_postfit_objective": 8})
    )
    calls = []

    def qualify(objective, seed, saved, **options):
        calls.append((objective, seed.copy(), saved, options))
        return dict(status="unqualified", qualified=False, objective_evaluations=8)

    monkeypatch.setattr(driver, "qualify", qualify)
    driver.main()
    assert len(calls) == 2
    for (_model, seed, saved, options), expected, score, stage in zip(
        calls, (first, second), (4, 8), ("calibration-prefit", "calibration-postfit"), strict=True
    ):
        np.testing.assert_array_equal(seed, expected)
        assert saved == score
        assert options == dict(
            retained=True,
            stage=stage,
            independently_qualified=False,
            maximum_rounds=2,
            maximum_evaluations=100,
        )
    receipt = json.loads((tmp_path / "result.json").read_text())
    assert len(receipt["attempts"]) == 2
    with pytest.raises(AssertionError):
        driver.main()
