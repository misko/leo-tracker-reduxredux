from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
VALIDATOR = PROJECT_ROOT / "deploy" / "scripts" / "validate-current-release"


def test_current_qnap_target_is_rejected_lexically(tmp_path: Path) -> None:
    current = tmp_path / "current"
    current.symlink_to("/mnt/qnap01/must-not-be-opened")
    result = subprocess.run(
        (str(VALIDATOR), str(current)),
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 65
    assert "QNAP cannot contain current release" in result.stderr
