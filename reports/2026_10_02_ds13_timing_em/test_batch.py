import subprocess
from types import SimpleNamespace

import pytest
from batch import run_cell


def test_timeout_is_retained_as_failure(tmp_path):
    def timeout(command, **kwargs):
        assert kwargs["timeout"] == 90
        assert kwargs["env"]["OPENBLAS_NUM_THREADS"] == "1"
        raise subprocess.TimeoutExpired(command, 90)

    result = run_cell(tmp_path, "scan", "gem", "medium", execute=timeout)
    assert result["exit_code"] == 124
    assert (tmp_path / "runs/scan/gem-medium/failure.json").exists()
    with pytest.raises(FileExistsError):
        run_cell(tmp_path, "scan", "gem", "medium", execute=timeout)


def test_exit_zero_without_seal_is_not_success(tmp_path):
    with pytest.raises(RuntimeError, match="seal"):
        run_cell(tmp_path, "scan", "direct", "loose",
                 execute=lambda *args, **kwargs: SimpleNamespace(returncode=0))
