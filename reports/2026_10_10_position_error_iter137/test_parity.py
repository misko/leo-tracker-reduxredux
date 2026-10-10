import copy
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from parity import check_member


class Model:
    size = 8
    initial_clock = np.zeros(4)

    def evaluate_joint(self, vector, clock):
        CALLS.append((vector.copy(), clock.copy()))
        return (float(vector[0]),)


CALLS = []


def test_cli_import_help_without_recording_calls():
    path = Path(__file__).with_name("parity.py")
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    result = subprocess.run(
        [sys.executable, str(path), "--help"], env=env, capture_output=True, text=True, check=True
    )
    assert "--shard" in result.stdout


def fixture(monkeypatch):
    import parity

    monkeypatch.setattr(
        parity,
        "construct",
        lambda case, row, components: (
            Model(),
            np.asarray(row["fit"]["vector"]),
            np.asarray(row["fit"]["clock_coefficients"]),
        ),
    )
    binding = dict(label="DS16-001", session_id="s", expected_input_binding={"all": "five"})
    projection = dict(session_id="s", input_binding={"all": "five"}, operational={})
    for arm, score in (("fitted-c", 3), ("zero-c", 7)):
        projection["operational"][arm] = dict(
            fit=dict(
                vector=[score, 0, 0, 0, 0, 0, 0, 0], clock_coefficients=[0] * 4, objective=score
            )
        )
    return binding, projection


def test_independent_saved_arms_exactly_two_calls(monkeypatch):
    binding, projection = fixture(monkeypatch)
    CALLS.clear()
    result = check_member(binding, lambda b: {}, {}, projection)
    assert result["endpoint_evaluations"] == len(CALLS) == 2
    assert [v[0] for v, _ in CALLS] == [3, 7]


def test_identity_failure_prevents_loader_and_provenance_gate(monkeypatch):
    binding, projection = fixture(monkeypatch)
    bad = copy.deepcopy(projection)
    bad["preparation_source_sha256"] = "truth-bearing"
    with pytest.raises(ValueError, match="Provenance-only"):
        check_member(binding, lambda b: pytest.fail("loader must not run"), {}, bad)
    projection["input_binding"] = {}
    with pytest.raises(ValueError, match="physical signatures"):
        check_member(binding, lambda b: pytest.fail("loader must not run"), {}, projection)


def test_second_arm_failure_preserves_first_and_call_cap(monkeypatch):
    binding, projection = fixture(monkeypatch)
    projection["operational"]["zero-c"]["fit"]["objective"] = 999
    CALLS.clear()
    result = check_member(binding, lambda b: {}, {}, projection)
    assert result["status"] == "failed"
    assert result["arms"]["fitted-c"]["status"] == "complete"
    assert result["arms"]["zero-c"]["status"] == "failed"
    assert len(CALLS) == result["endpoint_evaluations"] == 2
