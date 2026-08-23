from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    path = tools_root / "report_pilot_pnt_kalman_five_dwells.py"
    spec = importlib.util.spec_from_file_location("pilot_pnt_kalman_five_dwells_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(tools_root))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(tools_root))
    return module


def _candidate(*, time_s: float, accuracy: float, margin: float, rank: int = 0) -> dict:
    return {
        "time_s": time_s,
        "sample_start": round(time_s * 2_500_000),
        "candidates": [
            {
                "rank": rank,
                "local_epoch_sample": 3,
                "qam_accuracy": accuracy,
                "scores": [
                    {
                        "method": "glrt64",
                        "margin": margin,
                        "tracking_cfo_hz": 100_000.0,
                    }
                ],
            }
        ],
    }


def test_inventory_has_five_unique_new_release_runs() -> None:
    tool = _tool()

    assert len(tool.DWELLS) == 5
    assert len({item.session_id for item in tool.DWELLS}) == 5
    assert len({item.run_id for item in tool.DWELLS}) == 5
    assert all(len(item.paths) == 4 for item in tool.DWELLS)
    assert tool.PIPELINE_RELEASE_ID == "9f45c2aefc60b355ad1da173211c9c1255a13395"


def test_candidate_selection_is_phase_blind_margin_gated_and_separated() -> None:
    tool = _tool()
    scan = {
        "detections": [
            _candidate(time_s=1.00, accuracy=0.90, margin=0.20),
            _candidate(time_s=1.05, accuracy=0.99, margin=0.20),
            _candidate(time_s=1.25, accuracy=0.80, margin=0.20),
            _candidate(time_s=2.00, accuracy=0.98, margin=0.01),
            _candidate(time_s=59.90, accuracy=1.00, margin=0.20),
        ]
    }

    pool = tool._candidate_pool(scan)
    selected = tool._separated_candidates(pool)

    assert [item[1]["time_s"] for item in pool] == [1.05, 1.0, 1.25]
    assert [item[1]["time_s"] for item in selected] == [1.05, 1.25]
    source = inspect.getsource(tool._path_selection)
    assert "phase" not in source
    assert "kalman" not in source.lower()


def test_run_manifest_must_bind_release_recording_and_sealed_products(tmp_path: Path) -> None:
    tool = _tool()
    dwell = tool.DWELLS[0]
    manifest_path = tmp_path / "analysis" / dwell.session_id / dwell.run_id / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    document = {
        "run_id": dwell.run_id,
        "session_id": dwell.session_id,
        "pipeline_release_id": tool.PIPELINE_RELEASE_ID,
        "input_manifest_digest": dwell.recording_manifest_digest,
        "pipeline_lane": "standard",
        "products": [{"kind": "test"}],
    }
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    dwell = replace(dwell, run_manifest_digest=tool._file_digest(manifest_path))

    assert tool._validate_run_manifest(tmp_path, dwell) == document
    document["pipeline_release_id"] = "0" * 40
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance mismatch"):
        tool._validate_run_manifest(tmp_path, dwell)


def test_run_manifest_digest_is_frozen(tmp_path: Path) -> None:
    tool = _tool()
    dwell = tool.DWELLS[0]
    manifest_path = tmp_path / "analysis" / dwell.session_id / dwell.run_id / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    document = {
        "run_id": dwell.run_id,
        "session_id": dwell.session_id,
        "pipeline_release_id": tool.PIPELINE_RELEASE_ID,
        "input_manifest_digest": dwell.recording_manifest_digest,
        "pipeline_lane": "standard",
        "products": [{"kind": "test"}],
    }
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="run manifest digest mismatch"):
        tool._validate_run_manifest(tmp_path, dwell)
