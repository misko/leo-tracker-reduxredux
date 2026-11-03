import importlib.util
import json
from pathlib import Path
import sys

SPEC = importlib.util.spec_from_file_location("bounded_launch", Path(__file__).with_name("launch.py"))
assert SPEC and SPEC.loader
launch_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch_module)


def fake_runner(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "fake_runner.py"
    path.write_text(body)
    return path


def test_success_records_exact_command_and_fixed_environment(tmp_path):
    runner = fake_runner(tmp_path, "import os; print(os.environ['OPENBLAS_NUM_THREADS'])")
    result = launch_module.launch("DS9-F001", "prior_only", "regional", tmp_path / "out",
                                  runner=runner, python_executable=Path(sys.executable), timeout_s=2)
    assert result["status"] == "complete" and result["returncode"] == 0
    assert result["stdout"].strip() == "1"
    assert result["command"][2:4] == ["DS9-F001", "prior_only"]
    assert result["environment"]["PYTHONPATH"].endswith("/src")


def test_failure_before_native_receipt_is_preserved(tmp_path):
    runner = fake_runner(tmp_path, "import sys; print('failed', file=sys.stderr); raise SystemExit(7)")
    result = launch_module.launch("DS9-F001", "greedy", "stress", tmp_path / "out",
                                  runner=runner, python_executable=Path(sys.executable), timeout_s=2)
    assert result["status"] == "error" and result["returncode"] == 7
    assert "failed" in result["stderr"]
    assert not result["native_prediction_exists"]
    assert json.loads((tmp_path / "out/DS9-F001-stress-greedy.launch.json").read_text())["status"] == "error"


def test_timeout_preserves_progress_without_creating_native_final(tmp_path):
    runner = fake_runner(tmp_path, "import pathlib,time,sys\nout=pathlib.Path(sys.argv[-1]); out.mkdir(parents=True,exist_ok=True)\n(out/'DS9-F001-regional-gaussian_sum.progress.json').write_text('{}')\ntime.sleep(2)")
    result = launch_module.launch("DS9-F001", "gaussian_sum", "regional", tmp_path / "out",
                                  runner=runner, python_executable=Path(sys.executable), timeout_s=.05)
    assert result["status"] == "timeout"
    assert result["native_progress_exists"]
    assert not result["native_prediction_exists"] and not result["native_seal_exists"]
    assert (tmp_path / "out/DS9-F001-regional-gaussian_sum.progress.json").exists()
