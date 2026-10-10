from types import SimpleNamespace

import numpy as np
import pytest
from compare import compare


def fixture():
    saved = dict(
        vector=np.arange(9, dtype=float),
        clock_coefficients=np.arange(5, dtype=float),
        objective=10.0,
    )
    model = SimpleNamespace(
        slope_slice=slice(0, 3),
        observations=SimpleNamespace(times_s=np.arange(3), measured_hz=np.arange(3)),
        fixed_rf_drift=False,
        evaluate_joint=lambda *a: (10.0,),
    )

    def starts(vector, clock, **kwargs):
        return {
            ("original", arm): {
                "vector": np.asarray(vector).copy(),
                "clock_coefficients": np.asarray(clock).copy(),
            }
            for arm in ("fitted-c", "zero-c")
        }

    def locked_starts(*args, **kwargs):
        result = starts(*args, **kwargs)
        result["original", "zero-c"]["vector"][6] = 0
        result["original", "zero-c"]["clock_coefficients"][-2:] = 0
        return result

    return (
        model,
        {"stages": {"B7": {a: saved for a in ("fitted-c", "zero-c")}}},
        dict(rows=[{}, {}, {}]),
        dict(
            physics="timestamp",
            pair_rows=lambda r: dict(
                observations=3, pairs=[[0, 1]], unpaired=[{"index": 2, "reason": "missing-support"}]
            ),
            shared_starts=locked_starts,
            clone_model=lambda *a: "control",
            phase_convert=lambda c: c,
            paired_convert=lambda c, p, rho, **kw: "rho25",
            phase_predict=None,
            timestamp_predict=None,
            emission=None,
        ),
    )


def test_four_matched_calls_preserve_failure_and_missing_support():
    model, archive, support, kwargs = fixture()
    calls = []

    def attempt(objective, vector, clock, arm):
        calls.append((objective, vector.copy(), clock.copy(), arm))
        if len(calls) == 2:
            raise ValueError("preserved failure")
        vector[:] = 99
        return dict(converged=True)

    result = compare(model, archive, support, run_attempt=attempt, **kwargs)
    assert [(c[0], c[3]) for c in calls] == [
        (v, a) for v in ("control", "rho25") for a in ("fitted-c", "zero-c")
    ]
    for arm in ("fitted-c", "zero-c"):
        subset = [c for c in calls if c[3] == arm]
        np.testing.assert_array_equal(subset[0][1], subset[1][1])
        np.testing.assert_array_equal(subset[0][2], subset[1][2])
    assert calls[1][1][6] == 0 and np.all(calls[1][2][-2:] == 0)
    assert result["status"] == "attempt-failed"
    assert "preserved failure" in result["attempts"]["control"]["zero-c"]["error"]
    assert result["pairing"]["unpaired"][0]["reason"] == "missing-support"


def test_parity_failure_prevents_all_fits():
    model, archive, support, kwargs = fixture()
    model.evaluate_joint = lambda *a: (11.0,)
    progress = {}
    with pytest.raises(ValueError, match="parity"):
        compare(
            model,
            archive,
            support,
            run_attempt=lambda *a: pytest.fail("No fit"),
            progress=progress,
            **kwargs,
        )
    assert progress["support"] is support
    assert progress["pairing"]["unpaired"][0]["reason"] == "missing-support"


def test_support_membership_failure_prevents_all_fits():
    model, archive, support, kwargs = fixture()
    kwargs["pair_rows"] = lambda r: dict(observations=2)
    with pytest.raises(ValueError, match="membership"):
        compare(model, archive, support, run_attempt=lambda *a: pytest.fail("No fit"), **kwargs)


def test_actual_dependency_import_order_isolated():
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    code = """
import runpy,sys,importlib.util
from pathlib import Path
root=Path.cwd()
runpy.run_path(str(root/'reports/2026_10_09_position_error_iter106/engine.py'))
before={k:sys.modules.get(k) for k in ('adapter','audit_core','pair_score')}
spec=importlib.util.spec_from_file_location('support138smoke',root/'reports/2026_10_10_position_error_iter138/run.py')
value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
assert all(sys.modules.get(k) is v for k,v in before.items())
runpy.run_path(str(root/'reports/2026_10_10_position_error_iter130/objective.py'))
"""
    subprocess.run([sys.executable, "-c", code], cwd=root, check=True)


def test_terminal_without_claim_is_never_overwritten(tmp_path, monkeypatch):
    import json
    import sys

    import run

    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run.py", "--label", "member"])
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(key, "1")
    plan = dict(
        physics="timestamp",
        rho=0.25,
        maximum_fit_calls=48,
        maximum_seconds_per_fit=90,
        maximum_iterations_per_fit=600,
        qualification_threshold=0.001,
        variants=["control", "rho25"],
        arms=["fitted-c", "zero-c"],
        maximum_workers=1,
        threads_per_worker=1,
        members=[{"label": label} for label in ["member"] + [str(i) for i in range(11)]],
        sources={},
        inputs={},
    )
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    (tmp_path / "results").mkdir()
    terminal = tmp_path / "results/member.json"
    terminal.write_text("original receipt")
    with pytest.raises(FileExistsError, match="no overwrite"):
        run.main()
    assert terminal.read_text() == "original receipt"
    assert not terminal.with_suffix(".claim.json").exists()


def test_batch_foreign_claim_rejected(tmp_path):
    import json

    from batch import validate

    path = tmp_path / "member.json"
    path.write_text(json.dumps(dict(label="member", protocol_sha256="expected", status="complete")))
    path.with_suffix(".claim.json").write_text(
        json.dumps(dict(label="other", protocol_sha256="expected"))
    )
    with pytest.raises(ValueError, match="Foreign claim"):
        validate(path, "member", "expected")
