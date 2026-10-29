from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.starlink.native_short_window import NativeShortWindow
from leo.storage.short_window import ShortWindowWriter
from tests.native_adaptive.detector import test_native_detector as native_detector
from tools.analyze_short_window_recording import analyze_recording

RAW = native_detector.RAW
native_artifact = native_detector.built


def _arrays(fixture: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    exact = np.fromfile(fixture / "lower-exact.c128", dtype="<c16")
    control = np.fromfile(fixture / "lower-control.c128", dtype="<c16")
    samples = np.fromfile(fixture / RAW, dtype="<i2").reshape(-1, 2, 2)[:50_000]
    return exact, control, samples


@pytest.mark.parametrize("fractional", [False, True])
def test_reusable_binding_matches_cli_and_single_receiver(
    native_artifact: tuple[Path, Path], tmp_path: Path, fractional: bool
) -> None:
    output, fixture = native_artifact
    exact, control, samples = _arrays(fixture)
    window = tmp_path / "window.ci16"
    window.write_bytes(samples.tobytes())
    args = [
        str(output / "leo-native-glrt-short-window"),
        "--rate-hz",
        "2500000",
        "--exact-template",
        str(fixture / "lower-exact.c128"),
        "--control-template",
        str(fixture / "lower-control.c128"),
        "--input-ci16",
        str(window),
    ]
    if fractional:
        args.append("--fractional-epoch")
    reference = json.loads(subprocess.run(args, check=True, capture_output=True, text=True).stdout)
    for row in reference["rows"]:
        row.pop("timings_ms")
    library = str(output / "libleo-adaptive-detector.so")
    with NativeShortWindow(library, exact, control, fractional_epoch=fractional) as context:
        actual = context.analyze(samples)
        assert actual["rows"] == reference["rows"]
        assert context.analyze(samples) == actual
        for invalid in (samples[:-1], samples.astype("<f4"), samples[::-1], samples[:, :1]):
            with pytest.raises(ValueError, match="exactly 20 ms"):
                context.analyze(invalid)
        assert context.analyze(samples) == actual
    with pytest.raises(RuntimeError, match="closed"):
        context.analyze(samples)
    context.close()
    for receiver in (0, 1):
        with NativeShortWindow(
            library, exact, control, receiver_count=1, fractional_epoch=fractional
        ) as single:
            one = single.analyze(np.ascontiguousarray(samples[:, receiver : receiver + 1]))
        expected = dict(actual["rows"][receiver], receiver_id=0)
        assert one["rows"] == [expected]
    with pytest.raises(ValueError, match="frame length"):
        NativeShortWindow(library, exact[:-1], control)
    with pytest.raises(ValueError, match="finite"):
        NativeShortWindow(library, exact * np.nan, control)


def _recording(tmp_path: Path, samples: np.ndarray) -> Path:
    writer = ShortWindowWriter(
        tmp_path / "recordings",
        "offline-fixture",
        receiver_ids=(4, 7),
        chunk_windows=2,
        configuration={
            "targets": [
                {
                    "target_id": "low",
                    "rf_mapping_authority": "known",
                    "edge": "lower",
                    "rf_center_hz": 10_710_000_000,
                }
            ]
        },
        radio={"provider": "recorded-fixture"},
    )
    for sequence, count in enumerate((50_000, 50_000, 49_999)):
        writer.append(
            sequence=sequence,
            target_id="low",
            samples=samples[:count],
            acquisition={
                "sample_count": count,
                "complete": count == 50_000,
                "sample_start": 100_000 + 80_000 * sequence,
                "sample_end": 100_000 + 80_000 * sequence + count,
                "generation": 3,
                "counter_authority": "hardware",
                "validity_authority": "provider_attested" if sequence == 0 else "unknown",
                "sample_start_utc_ns": [1_000_000_000 + sequence * 32_000_000] * 2,
                "requested_if_center_hz": 960_000_000,
                "actual_if_center_hz": 960_000_000,
                "quality_flags": [],
            },
            powers=({"decision": "quiet"}, {"decision": "quiet"}),
        )
    return writer.finish(stop_reason="fixture", failure="partial diagnostic window")


def test_recording_analyzer_reuses_context_and_resumes_atomic_results(
    native_artifact: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native, fixture = native_artifact
    _, _, samples = _arrays(fixture)
    recording = _recording(tmp_path, samples)
    output = tmp_path / "analysis.jsonl"
    arguments = {
        "recording": recording,
        "library": native / "libleo-adaptive-detector.so",
        "exact_template": fixture / "lower-exact.c128",
        "control_template": fixture / "lower-control.c128",
        "output": output,
    }
    ordinary = NativeShortWindow.analyze
    calls: list[int] = []

    def interrupted(self: NativeShortWindow, values: np.ndarray) -> dict[str, object]:
        calls.append(id(self))
        if len(calls) == 2:
            raise RuntimeError("injected interruption")
        return ordinary(self, values)

    monkeypatch.setattr(NativeShortWindow, "analyze", interrupted)
    with pytest.raises(RuntimeError, match="injected interruption"):
        analyze_recording(**arguments)
    assert len(set(calls)) == 1
    assert not output.exists()
    checkpoint = output.with_name(output.name + ".partial")
    assert len(checkpoint.read_bytes().splitlines()) == 2
    # A crash may leave one truncated last append. Preserve its complete prefix.
    with checkpoint.open("ab") as stream:
        stream.write(b'{"truncated":')
    monkeypatch.setattr(NativeShortWindow, "analyze", ordinary)
    summary = analyze_recording(**arguments, resume=True)
    assert summary["analyzed_windows"] == 2
    assert summary["diagnostic_windows"] == summary["skipped_windows"] == 1
    assert summary["source_recording_status"] == "incomplete"
    assert summary["qualified_tracking"] is False
    assert not checkpoint.exists()
    documents = [json.loads(line) for line in output.read_bytes().splitlines()]
    first, diagnostic, partial = documents[1:4]
    assert first["powers"] == [{"decision": "quiet"}] * 2
    assert first["status"] == "native_candidate_evidence"
    assert diagnostic["status"] == "diagnostic"
    assert "post_retune_validity_not_attested" in diagnostic["diagnostic_reasons"]
    assert diagnostic["window_support"]["sample_start"] == 180_000
    assert partial["status"] == "skipped_invalid_support"
    assert partial["glrt"] is None
    assert [row["physical_receiver_id"] for row in first["glrt"]["rows"]] == [4, 7]
    snapshot = output.read_bytes()

    def no_reanalysis(*_: object, **__: object) -> None:
        raise AssertionError("idempotent resume must not initialize a detector")

    monkeypatch.setattr(NativeShortWindow, "__init__", no_reanalysis)
    assert analyze_recording(**arguments, resume=True) == summary
    assert output.read_bytes() == snapshot
    with pytest.raises(ValueError, match="binding differs"):
        analyze_recording(**arguments, resume=True, fractional_epoch=True)
    with pytest.raises(FileExistsError):
        analyze_recording(**arguments)
    documents[1]["status"] = "tampered"
    output.write_text("\n".join(json.dumps(document) for document in documents) + "\n")
    with pytest.raises(ValueError, match="digest changed"):
        analyze_recording(**arguments, resume=True)


def test_recording_analyzer_cli_and_actual_counter_bounds(
    native_artifact: tuple[Path, Path], tmp_path: Path
) -> None:
    native, fixture = native_artifact
    _, _, samples = _arrays(fixture)
    recording = _recording(tmp_path, samples)
    output = tmp_path / "cli-analysis.jsonl"
    completed = subprocess.run(
        [
            os.fspath(Path(os.sys.executable)),
            "tools/analyze_short_window_recording.py",
            str(recording),
            "--library",
            str(native / "libleo-adaptive-detector.so"),
            "--exact-template",
            str(fixture / "lower-exact.c128"),
            "--control-template",
            str(fixture / "lower-control.c128"),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["analyzed_windows"] == 2
    documents = [json.loads(line) for line in output.read_bytes().splitlines()]
    assert documents[1]["window_support"]["sample_end_exclusive"] == 150_000
    assert documents[2]["window_support"]["sample_end_exclusive"] == 230_000
    assert documents[1]["glrt"]["window_start_sample"] == 0
