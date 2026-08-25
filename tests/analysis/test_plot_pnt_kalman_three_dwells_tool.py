from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


def _tool():
    path = Path(__file__).parents[2] / "tools" / "plot_pnt_kalman_three_dwells.py"
    spec = importlib.util.spec_from_file_location("plot_pnt_kalman_three_dwells", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_fixture(root: Path, *, tracker: str, session_id: str = "cap-test") -> None:
    label = "D1"
    stem = "d1-test-radio1-rx1-lower"
    sample_rate_hz = 2_500_000
    frame_start = np.asarray([25_000, 28_333, 31_667, 275_000, 278_333, 281_667])
    window = np.asarray([0, 0, 0, 1, 1, 1])
    bin_index = np.asarray([0, 0, 0, 1, 1, 1])
    centers = np.asarray([0.02, 0.02, 0.02, 0.12, 0.12, 0.12])
    seed_start = np.asarray([25_000, 25_000, 25_000, 275_000, 275_000, 275_000])
    margins = np.asarray([0.4, 0.4, 0.4, 0.5, 0.5, 0.5])
    npz_path = root / f"{stem}-filter-benchmark.npz"
    np.savez(
        npz_path,
        window_index=window,
        window_center_time_s=centers,
        window_raw_disjoint=np.ones(6, dtype=bool),
        bin_index=bin_index,
        seed_sample_start=seed_start,
        seed_glrt_margin=margins,
        frame_index=np.asarray([0, 1, 2, 0, 1, 2]),
        frame_start_sample=frame_start,
        absolute_time_s=frame_start / sample_rate_hz,
        measurement_supported=np.asarray([True, True, False, True, True, True]),
        absolute_cfo_measurement_hz=np.asarray([100.0, 101.0, 102.0, 110.0, 111.0, 112.0]),
        tracked_absolute_cfo_hz=np.asarray([99.0, 100.0, 101.0, 109.0, 110.0, 111.0])
        + (0.5 if tracker == "v3" else 0.0),
        reacquired=np.asarray([False, False, False, True, False, False]),
    )
    summary = {
        "schema": f"test/{tracker}",
        "label": label,
        "session_id": session_id,
        "run_id": "capture-test",
        "scope_sha256": "sha256:scope",
        "stream_id": "stream-1",
        "radio_id": "radio-test",
        "receiver_id": 1,
        "channel": 2,
        "edge": "lower",
        "rf_hz": 10_959_687_500,
        "sample_rate_hz": sample_rate_hz,
        "sample_count": 500_000,
        "recording_manifest_sha256": "recording",
        "analysis_manifest_sha256": "analysis",
        "pilot_scan_sha256": "scan",
        "npz_relative_path": npz_path.name,
        "pnt_source_sha256": tracker,
    }
    if tracker == "v3":
        summary["seed_relative_path"] = f"{stem}-seeds.json"
        seed = {
            "schema": "org.leo.research.sealed-standard-100ms-glrt64-seeds/v1",
            **{
                key: summary[key]
                for key in (
                    "label",
                    "session_id",
                    "run_id",
                    "scope_sha256",
                    "stream_id",
                    "radio_id",
                    "receiver_id",
                    "channel",
                    "edge",
                    "rf_hz",
                    "sample_rate_hz",
                    "sample_count",
                    "recording_manifest_sha256",
                    "analysis_manifest_sha256",
                    "pilot_scan_sha256",
                )
            },
            "selection": "synthetic sealed GLRT selection",
            "bins": [
                {
                    "bin_index": index,
                    "status": "selected",
                    "seed": {
                        "sample_start": start,
                        "source_time_s": start / sample_rate_hz,
                        "center_time_s": center,
                        "tracking_cfo_hz": 100.0 + 10.0 * index,
                        "glrt_margin": margin,
                    },
                }
                for index, start, center, margin in (
                    (0, 25_000, 0.02, 0.4),
                    (1, 275_000, 0.12, 0.5),
                )
            ],
        }
        (root / f"{stem}-seeds.json").write_text(
            json.dumps(seed, indent=2) + "\n", encoding="utf-8"
        )
    (root / f"{stem}-filter-benchmark-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


def test_segmented_trace_breaks_at_masks_windows_reacquisition_and_frame_gaps() -> None:
    tool = _tool()
    time_s = np.arange(8, dtype=float)
    values = 100.0 + time_s
    plotted_time, _, segments = tool.segmented_trace(
        time_s,
        values,
        np.asarray([0, 0, 0, 0, 1, 1, 1, 1]),
        np.asarray([False, False, True, False, False, False, False, False]),
        included=np.asarray([True, True, True, False, True, True, True, True]),
        frame_index=np.asarray([0, 1, 2, 3, 0, 1, 3, 4]),
    )

    assert segments == 4
    assert np.count_nonzero(np.isnan(plotted_time)) == 3
    finite_runs = [
        run for run in np.split(plotted_time, np.flatnonzero(np.isnan(plotted_time))) if len(run)
    ]
    assert not any(run[0] == 1.0 and run[-1] == 2.0 for run in finite_runs)


def test_render_writes_composite_individual_and_provenance(tmp_path: Path) -> None:
    tool = _tool()
    v2_root = tmp_path / "v2"
    v3_root = tmp_path / "v3"
    output_root = tmp_path / "figures"
    v2_root.mkdir()
    v3_root.mkdir()
    _write_fixture(v2_root, tracker="v2")
    _write_fixture(v3_root, tracker="v3")

    receipt_path = tool.render(
        v2_root,
        v3_root,
        output_root,
        [tool.DwellSpec("D1", 0.01, 0.15)],
        dpi=60,
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema"] == "org.leo.research.pnt-kalman-three-dwell-plots/v1"
    assert receipt["configuration"]["continuity_policy"].startswith("line breaks")
    assert receipt["dwells"][0]["zoom_interval_s"] == [0.01, 0.15]
    assert receipt["dwells"][0]["glrt_20ms_seed_count"] == 2
    assert receipt["dwells"][0]["supported_frame_cfo_count"] == 5
    assert receipt["dwells"][0]["supported_frame_cfo_segment_count"] == 2
    assert Path(receipt["composite_figure"]["path"]).is_file()
    assert receipt["composite_figure"]["repository_relative_path"] is None
    assert Path(receipt["dwells"][0]["individual_figure"]["path"]).is_file()
    assert receipt["tool"]["repository_relative_path"] == ("tools/plot_pnt_kalman_three_dwells.py")
    assert len(receipt["composite_figure"]["sha256"]) == 64


def test_render_rejects_mismatched_recording_identity(tmp_path: Path) -> None:
    tool = _tool()
    v2_root = tmp_path / "v2"
    v3_root = tmp_path / "v3"
    v2_root.mkdir()
    v3_root.mkdir()
    _write_fixture(v2_root, tracker="v2")
    _write_fixture(v3_root, tracker="v3", session_id="cap-wrong")

    with np.testing.assert_raises_regex(ValueError, "identity mismatch for session_id"):
        tool.render(
            v2_root,
            v3_root,
            tmp_path / "figures",
            [tool.DwellSpec("D1", 0.01, 0.15)],
            dpi=60,
        )
