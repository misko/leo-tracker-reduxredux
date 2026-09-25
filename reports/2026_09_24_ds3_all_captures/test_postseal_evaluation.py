from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ds3_postseal", HERE / "postseal_evaluation.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["ds3_postseal"] = module
spec.loader.exec_module(module)


def seal(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(sha256)


def test_collect_requires_reference_free_all56_artifacts(tmp_path: Path) -> None:
    artifact = tmp_path / "portable/inference/joint-all56__baseline.json"
    seal(artifact, {"estimated_position": {"latitude_deg": 1, "longitude_deg": 2}})
    with pytest.raises(ValueError, match="missing artifact"):
        module.collect(tmp_path, (0.0, 0.0))
    seal(artifact, {"reference_used_for_inference": True})
    with pytest.raises(ValueError, match="reference-bearing"):
        module.collect(tmp_path, (0.0, 0.0))
