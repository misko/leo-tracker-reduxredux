from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "report_full_capture_hough_end_to_end.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("full_capture_hough_end_to_end_tool", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dense_final_lineage_reconstructs_degree_one_tracks() -> None:
    tool = _load_tool()
    source = json.loads((ROOT / tool.SOURCE_JSON).read_text(encoding="utf-8"))
    lifecycle = json.loads((ROOT / tool.DOWNSTREAM_JSON).read_text(encoding="utf-8"))

    tracks, observations, detections, passing = tool._reconstruct_tracks(source, lifecycle)

    assert tuple(item.label for item in tracks) == ("H1", "H2", "H4", "H3", "H7", "H10")
    assert all(item.canonical.polynomial_degree == 1 for item in tracks)
    assert all(item.canonical.point_count == len(item.observation_ids) for item in tracks)
    assert all(item.start_s < item.end_s for item in tracks)
    assert len(observations) == len(passing) == 2_127
    assert len(detections) == 5_999


def test_every_dense_final_member_closes_to_the_source_evidence() -> None:
    tool = _load_tool()
    source = json.loads((ROOT / tool.SOURCE_JSON).read_text(encoding="utf-8"))
    lifecycle = json.loads((ROOT / tool.DOWNSTREAM_JSON).read_text(encoding="utf-8"))

    tracks, observations, _, _ = tool._reconstruct_tracks(source, lifecycle)
    source_ids = {item.observation_id for item in observations}

    assert len(source_ids) == len(observations)
    for track in tracks:
        assert set(track.observation_ids) <= source_ids
        assert len(track.observation_ids) == len(set(track.observation_ids))
