from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.cli.arm_glrt import run


def test_rejects_nonfinite_timeout_before_any_file_access() -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        run(SimpleNamespace(timeout_s=float("nan")))


def test_module_cli_starts_without_optional_radio_driver_imports() -> None:
    root = Path(__file__).parents[2]
    environment = {**os.environ, "PYTHONPATH": str(root / "src")}
    completed = subprocess.run(
        [sys.executable, "-m", "leo.cli.arm_glrt", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--native-binary" in completed.stdout


def test_lazy_public_cli_exports_preserve_model_and_backend_access() -> None:
    root = Path(__file__).parents[2]
    completed = subprocess.run(
        [sys.executable, "-c", "\n".join((
            "import sys",
            "from leo.cli import CliBackendError, CommandResultV1, ExitCode",
            "assert issubclass(CliBackendError, Exception)",
            "assert CommandResultV1.__name__ == 'CommandResultV1'",
            "assert ExitCode.__name__ == 'ExitCode'",
            "assert 'leo.radio.pluto_host_adaptive' not in sys.modules",
        ))],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
    )
    assert completed.returncode == 0, completed.stderr
