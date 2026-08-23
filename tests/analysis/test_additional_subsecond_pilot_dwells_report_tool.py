from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_additional_subsecond_pilot_dwells.py"
    tools_path = str(path.parent)
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    spec = importlib.util.spec_from_file_location(
        "additional_subsecond_pilot_dwells_report_tool", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_inputs_require_exactly_five_unique_sessions_and_runs(tmp_path: Path) -> None:
    tool = _tool()
    path = tmp_path / "inputs.json"
    path.write_text(
        json.dumps(
            {
                "schema": "org.leo.research.additional-subsecond-pilot-inputs/v1",
                "pipeline_release_id": "a" * 40,
                "dwells": [
                    {"session_id": f"session-{index}", "run_id": f"run-{index}"}
                    for index in range(5)
                ],
            }
        )
    )

    release, rows = tool._validated_inputs(path)

    assert release == "a" * 40
    assert len(rows) == 5

    document = json.loads(path.read_text())
    document["dwells"][-1] = document["dwells"][0]
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="duplicate"):
        tool._validated_inputs(path)


def test_run_manifest_must_have_successful_terminal_jobs_and_match_release(
    tmp_path: Path,
) -> None:
    tool = _tool()
    session = "session-a"
    run = "run-a"
    root = tmp_path / "analysis" / session / run
    root.mkdir(parents=True)
    manifest = {
        "session_id": session,
        "run_id": run,
        "pipeline_lane": "standard",
        "pipeline_release_id": "b" * 40,
        "jobs": [{"outcome": "complete"}, {"outcome": "partial_coverage"}],
    }
    (root / "manifest.json").write_text(json.dumps(manifest))

    selected, loaded, digest = tool._validated_run_root(
        tmp_path, session_id=session, run_id=run, release="b" * 40
    )

    assert selected == root
    assert loaded == manifest
    assert digest.startswith("sha256:")

    manifest["jobs"][0]["outcome"] = "failed"
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="non-successful job outcome"):
        tool._validated_run_root(tmp_path, session_id=session, run_id=run, release="b" * 40)


def test_stream_tuning_tag_selects_edge() -> None:
    tool = _tool()
    tags = ("LIVE", "tuning:stream-0:ch4:lower", "tuning:stream-1:ch1:upper")

    assert tool._edge_for_stream(tags, "stream-0") is tool.StarlinkEdge.LOWER
    assert tool._edge_for_stream(tags, "stream-1") is tool.StarlinkEdge.UPPER

    with pytest.raises(ValueError, match="one tuning tag"):
        tool._edge_for_stream(("LIVE",), "stream-0")
