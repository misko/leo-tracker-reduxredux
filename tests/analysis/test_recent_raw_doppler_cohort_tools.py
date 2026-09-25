from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _tool(name: str) -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    path = tools_root / f"{name}.py"
    sys.path.insert(0, str(tools_root))
    try:
        spec = importlib.util.spec_from_file_location(f"{name}_test_module", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(tools_root))
    return module


def _analysis_run(
    root: Path,
    *,
    session_id: str,
    run_id: str,
    maximum_job_id: int,
    outcome: str = "complete",
) -> None:
    run_root = root / session_id / run_id
    product_root = run_root / "scientific" / "path-standard" / "sha256:path"
    product_root.mkdir(parents=True)
    (product_root / "standard.pilot-scan.v3.json").write_text("{}", encoding="utf-8")
    (product_root / "standard.dealiased-trajectory-bank.v4.json").write_text("{}", encoding="utf-8")
    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "run_id": run_id,
                "pipeline_lane": "standard",
                "pipeline_release_id": f"release-{run_id}",
                "jobs": [{"job_id": maximum_job_id, "outcome": outcome}],
            }
        ),
        encoding="utf-8",
    )


def test_recent_selector_uses_latest_successful_terminal_job_not_mtime(tmp_path: Path) -> None:
    tool = _tool("select_recent_raw_doppler_dwells")
    session = "cap-20260823T150300-92ac23cd745f"
    _analysis_run(
        tmp_path,
        session_id=session,
        run_id="older-success",
        maximum_job_id=100,
    )
    _analysis_run(
        tmp_path,
        session_id=session,
        run_id="newer-success",
        maximum_job_id=200,
    )
    _analysis_run(
        tmp_path,
        session_id=session,
        run_id="failed-newest",
        maximum_job_id=300,
        outcome="failed",
    )

    selected = tool.successful_runs(tmp_path)

    assert len(selected) == 1
    assert selected[0].run_id == "newer-success"
    assert selected[0].maximum_job_id == 200
    assert selected[0].path_product_count == 1
    assert selected[0].analysis_manifest_digest.startswith("sha256:")


def _cohort_inputs(path: Path) -> list[dict[str, object]]:
    rows = [
        {
            "label": f"R{index:02d}",
            "session_id": f"cap-20260823T{index:06d}-{index:012x}",
            "run_id": f"run-{index}",
            "analysis_manifest_digest": f"sha256:analysis-{index}",
            "recording_manifest_digest": f"sha256:recording-{index}",
        }
        for index in range(1, 51)
    ]
    path.write_text(
        json.dumps(
            {
                "schema": "org.leo.research.recent-raw-doppler-inputs/v1",
                "selected_dwell_count": 50,
                "dwells": rows,
            }
        ),
        encoding="utf-8",
    )
    return rows


def test_recent_runner_checkpoints_one_dwell_and_reuses_digest_closed_result(
    tmp_path: Path,
) -> None:
    tool = _tool("analyze_recent_raw_doppler_cohort")
    inputs = tmp_path / "inputs.json"
    rows = _cohort_inputs(inputs)
    output_root = tmp_path / "results"
    calls: list[tuple[str, str, bool]] = []

    def analyze_raw_dwell(**kwargs: object) -> dict[str, object]:
        calls.append(
            (
                str(kwargs["session_id"]),
                str(kwargs["run_id"]),
                bool(kwargs["include_frames"]),
            )
        )
        return {
            "schema": "org.leo.research.raw-dwell-doppler/v1",
            "session_id": kwargs["session_id"],
            "run_id": kwargs["run_id"],
            "analysis_manifest_digest": rows[0]["analysis_manifest_digest"],
            "recording_manifest_digest": rows[0]["recording_manifest_digest"],
            "status": "complete",
        }

    tool.analyze_raw_dwell = analyze_raw_dwell
    arguments = {
        "bulk_root": tmp_path,
        "inputs_path": inputs,
        "output_root": output_root,
        "maximum_track_attempts": 4,
        "only_label": "R01",
        "maximum_dwells": None,
        "resume": True,
    }

    tool.run_cohort(**arguments)
    tool.run_cohort(**arguments)

    assert calls == [(rows[0]["session_id"], rows[0]["run_id"], False)]
    index = json.loads((output_root / "index.json").read_text(encoding="utf-8"))
    assert index["dwell_count"] == 50
    assert index["completed_result_count"] == 1
    assert index["results"][0]["status"] == "complete"
    assert index["results"][1]["status"] == "pending"
