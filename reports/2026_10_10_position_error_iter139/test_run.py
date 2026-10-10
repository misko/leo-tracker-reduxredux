import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import run


def fixture():
    calls = []
    terms = SimpleNamespace(
        responsibilities=np.ones((4, 1)), residual_hz=np.array([[250], [375], [250], [375]]), nll=4
    )

    def evaluate(v, c):
        calls.append((v, c))
        return 10, None, None, terms

    model = SimpleNamespace(
        observations=SimpleNamespace(window_ids=list("abcd")),
        bank=SimpleNamespace(numbers=[42]),
        score=SimpleNamespace(sigma_hz=125),
        evaluate_joint=evaluate,
    )
    details = [
        dict(
            first_window_id=a,
            second_window_id=b,
            group=[0, 1, 100, "upper"],
            alternating_block=i,
            score=6,
            shared_label_mass=1,
        )
        for i, (a, b) in enumerate((("a", "b"), ("c", "d")))
    ]
    predecessor = dict(
        support=dict(rows=[dict(window_id=x) for x in "abcd"]),
        pairing={},
        arms={arm: dict(pair_details=details, score_sum=12) for arm in ("fitted-c", "zero-c")},
    )
    archive = dict(
        stages=dict(
            B7={
                arm: dict(vector=[0], clock_coefficients=[0], objective=10)
                for arm in ("fitted-c", "zero-c")
            }
        )
    )
    return model, archive, predecessor, calls


def test_two_calls_exact_pair_parity_and_mean_diagnostic():
    model, archive, predecessor, calls = fixture()
    result = run.analyze(model, archive, predecessor)
    assert len(calls) == 2
    assert result["status"] == "complete"
    assert result["arms"]["fitted-c"]["weighted_product_sum"] == 12
    assert result["arms"]["zero-c"]["crossprediction_centered_product_sum"] == 0


@pytest.mark.parametrize("field", ["score", "shared_label_mass"])
def test_pair_parity_failure_stops_before_second_call(field):
    model, archive, predecessor, calls = fixture()
    predecessor["arms"]["fitted-c"]["pair_details"][0][field] += 0.1
    with pytest.raises(ValueError, match="individual pair"):
        run.analyze(model, archive, predecessor)
    assert len(calls) == 1


def test_real_namespace_import_without_recording_access():
    code = f"""
import sys
from pathlib import Path
sys.path.insert(0,{str(run.HERE)!r})
import run
assert 'adapter' not in sys.modules
folder=run.ROOT/'reports/2026_10_09_position_error_iter116'
sys.path.insert(0,str(folder))
entry=run.implementation.module('actual_entry_for139_test',folder/'entrypoint.py')
import driver,adapter
assert driver.PointEvaluator is adapter.PointEvaluator
assert Path(adapter.__file__).parent == folder
assert run.implementation.HERE==run.HERE
assert run.implementation.perform is run.perform
"""
    env = dict(os.environ, PYTHONPATH=str(run.ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    child = subprocess.run(
        [sys.executable, "-c", code], env=env, cwd=run.ROOT, capture_output=True, text=True
    )
    assert child.returncode == 0, child.stderr
