from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest
from PIL import Image

from leo.contracts.recording import RecordingStreamV2
from tests.station.manifest_examples import manifest_example_v2

ROOT = Path(__file__).parents[2]
INPUTS_PATH = ROOT / "config" / "analysis" / "recent-frame-cfo-rate-v1.json"


def _tool() -> ModuleType:
    path = ROOT / "tools" / "prototype_recent_frame_cfo_rate.py"
    spec = importlib.util.spec_from_file_location("prototype_recent_frame_cfo_rate_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _inputs() -> dict[str, Any]:
    document = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _lossless_stream(*, first_sample_utc_ns: int) -> RecordingStreamV2:
    base = manifest_example_v2(radio_count=1, applied_receiver_ids=(1,)).streams[0]
    document = base.model_dump(mode="json")
    sample_count = 573
    document.update(
        {
            "requested_sample_count": sample_count,
            "captured_sample_count": sample_count,
        }
    )
    document["radio"]["radio_id"] = "radio_pluto_5d4d"
    chunk = document["chunks"][0]
    chunk.update(
        {
            "sample_count": sample_count,
            "uncompressed_bytes": sample_count * 4,
        }
    )
    last_sample_utc_ns = first_sample_utc_ns + round((sample_count - 1) * 1e9 / 2_500_000)
    timing = document["timing"]
    timing["first_sample"].update(
        {
            "estimate_utc_ns": first_sample_utc_ns,
            "earliest_utc_ns": first_sample_utc_ns,
            "latest_utc_ns": first_sample_utc_ns,
        }
    )
    timing["last_sample"].update(
        {
            "estimate_utc_ns": last_sample_utc_ns,
            "earliest_utc_ns": last_sample_utc_ns,
            "latest_utc_ns": last_sample_utc_ns,
        }
    )
    document["continuity"].update(
        {
            "refill_count": sample_count,
            "first_source_sequence": 0,
            "last_source_sequence": sample_count - 1,
            "first_device_sample_counter": 10_000,
            "last_device_sample_counter": 10_000 + sample_count - 1,
            "observed_sample_count": sample_count,
            "device_span_sample_count": sample_count,
        }
    )
    return RecordingStreamV2.model_validate(document)


class _AgeBoundaryStore:
    def __init__(self, stream: RecordingStreamV2, manifest_sha256: str) -> None:
        self._bundle = SimpleNamespace(
            manifest_sha256=manifest_sha256,
            manifest=SimpleNamespace(
                streams=(stream,),
                tags=(f"tuning:{stream.stream_id}:ch3:lower",),
            ),
        )
        self.reader_called = False

    def inspect(self, session_id: str) -> SimpleNamespace:
        assert session_id
        return self._bundle

    def reader(self, bundle: object, stream_id: str, *, verify: bool) -> SimpleNamespace:
        assert bundle is self._bundle
        assert stream_id == self._bundle.manifest.streams[0].stream_id
        assert verify is True
        self.reader_called = True
        return SimpleNamespace(sample_rate_hz=1, receiver_ids=(1,))


def test_inputs_are_closed_and_allow_exactly_twelve_hours() -> None:
    tool = _tool()
    document = _inputs()

    document["maximum_age_s"] = 43_200.0
    assert len(tool._validate_inputs(document)) == 3

    open_document = copy.deepcopy(document)
    open_document["unreviewed_selection"] = True
    with pytest.raises(ValueError, match="unsupported or non-closed"):
        tool._validate_inputs(open_document)

    open_dwell = copy.deepcopy(document)
    open_dwell["dwells"][0]["unreviewed_continuity"] = "assumed"
    with pytest.raises(ValueError, match="dwell fields are not closed"):
        tool._validate_inputs(open_dwell)

    too_old = copy.deepcopy(document)
    too_old["maximum_age_s"] = math.nextafter(43_200.0, math.inf)
    with pytest.raises(ValueError, match="older than 12 hours"):
        tool._validate_inputs(too_old)


def test_dwell_age_accepts_cutoff_and_rejects_one_nanosecond_older(tmp_path: Path) -> None:
    tool = _tool()
    document = _inputs()
    item = document["dwells"][0]
    reference_ns = int(document["selection_reference_utc_ns"])
    cutoff_ns = reference_ns - 43_200 * 1_000_000_000

    at_cutoff = _AgeBoundaryStore(
        _lossless_stream(first_sample_utc_ns=cutoff_ns),
        item["recording_manifest_sha256"],
    )
    with pytest.raises(ValueError, match="pinned 2.5 MS/s receiver"):
        tool.analyze_dwell(
            at_cutoff,
            tmp_path,
            item,
            document,
            maximum_frames=20,
        )
    assert at_cutoff.reader_called is True

    outside = _AgeBoundaryStore(
        _lossless_stream(first_sample_utc_ns=cutoff_ns - 1),
        item["recording_manifest_sha256"],
    )
    with pytest.raises(ValueError, match="outside the frozen <=12-hour selection window"):
        tool.analyze_dwell(
            outside,
            tmp_path,
            item,
            document,
            maximum_frames=20,
        )
    assert outside.reader_called is False


def test_continuity_gate_accepts_verified_contiguous_v2_refills() -> None:
    tool = _tool()
    stream = _lossless_stream(first_sample_utc_ns=1_000_000_000)

    assert stream.continuity.refill_count == 573
    assert stream.continuity.segment_count == 1
    assert stream.continuity.gap_count == 0
    assert tool._continuity_is_lossless(stream) is True


@pytest.mark.parametrize(
    "updates",
    (
        {"gap_count": 1},
        {"missing_sample_count": 1, "device_span_sample_count": 574},
        {"observed_sample_count": 572},
        {"segment_count": 2},
    ),
    ids=("declared-gap", "missing-sample", "observed-loss", "split-segment"),
)
def test_continuity_gate_rejects_gaps_or_loss(updates: dict[str, int]) -> None:
    tool = _tool()
    stream = _lossless_stream(first_sample_utc_ns=1_000_000_000)
    continuity = stream.continuity.model_copy(update=updates)
    degraded = stream.model_copy(update={"continuity": continuity})

    assert tool._continuity_is_lossless(degraded) is False


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 5_000_000, 10_000_000))
def test_frame_starts_follow_fractional_sample_lattice_without_drift(
    sample_rate_hz: int,
) -> None:
    tool = _tool()
    epoch_sample = 17
    frame_content = round(302 * sample_rate_hz * tool.OFDM_SYMBOL_DURATION_S)

    starts = tool._frame_starts(
        epoch_sample,
        sample_rate_hz,
        0.0,
        0.020,
        frame_content,
    )

    period_samples = sample_rate_hz / tool.FRAME_RATE_HZ
    expected = tuple(
        epoch_sample + round(frame_index * period_samples) for frame_index in range(len(starts))
    )
    assert starts == expected
    assert set(b - a for a, b in zip(starts, starts[1:], strict=False)) == {
        math.floor(period_samples),
        math.ceil(period_samples),
    }
    assert starts[-1] + frame_content <= round(0.020 * sample_rate_hz)
    assert abs((starts[-1] - starts[0]) - (len(starts) - 1) * period_samples) <= 0.5


def _plot_fixture(tool: ModuleType) -> tuple[tuple[dict[str, object], ...], ...]:
    methods = tuple(method.value for method in tool.FrameCfoRateMethod)
    summaries = []
    for duration_ms in (20.0, 75.0):
        for label_index, label in enumerate(("D1", "D2")):
            for method_index, method in enumerate(methods):
                summaries.append(
                    {
                        "label": label,
                        "duration_ms": duration_ms,
                        "method": method,
                        "pooled_odd_cfo_rms_hz": (
                            80.0 + 5.0 * label_index + 3.0 * method_index + duration_ms / 20.0
                        ),
                        "median_conditional_rate_sigma_hz_s": (
                            1_000.0 + 20.0 * method_index + duration_ms
                        ),
                    }
                )
    for method_index, method in enumerate(methods):
        summaries.append(
            {
                "label": "D1",
                "duration_ms": 125.0,
                "method": method,
                "pooled_odd_cfo_rms_hz": 70.0 + method_index,
                "median_conditional_rate_sigma_hz_s": 900.0 + method_index,
            }
        )

    rows = []
    for label_index, label in enumerate(("D1", "D2")):
        for method in (
            tool.FrameCfoRateMethod.GLRT_RATE.value,
            tool.FrameCfoRateMethod.SUMMED_PROFILE.value,
        ):
            for window_index, reference_time_s in enumerate((10.0, 10.075, 10.150)):
                rows.append(
                    {
                        "label": label,
                        "duration_ms": 75.0,
                        "method": method,
                        "reference_time_s": reference_time_s,
                        "rate_hz_s": (
                            -30_000.0
                            + 500.0 * label_index
                            + 20.0 * window_index
                            + (100.0 if method == tool.FrameCfoRateMethod.SUMMED_PROFILE else 0.0)
                        ),
                    }
                )
    return tuple(summaries), tuple(rows)


def test_plot_is_valid_and_byte_deterministic_for_synthetic_rows(tmp_path: Path) -> None:
    tool = _tool()
    summaries, rows = _plot_fixture(tool)
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    tool._plot(first, summaries, rows)
    tool._plot(second, tuple(reversed(summaries)), tuple(reversed(rows)))

    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(first) as image:
        assert image.format == "PNG"
        assert image.size[0] > image.size[1] > 1_000
        image.verify()


def test_plot_uses_longest_common_duration_when_smoke_has_no_common_125_ms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    summaries, rows = _plot_fixture(tool)
    titles: list[str] = []

    def capture_titles(figure: Any, _path: Path, **_kwargs: object) -> None:
        titles.extend(axis.get_title() for axis in figure.axes)

    monkeypatch.setattr(tool.Figure, "savefig", capture_titles)
    tool._plot(tmp_path / "smoke.png", summaries, rows)

    assert "B  75 ms error relative to GLRT trend" in titles
    assert "D  Non-overlapping 75 ms rate estimates" in titles
    assert all("125 ms" not in title for title in titles if title.startswith(("B", "D")))


def _track_rows(
    tool: ModuleType,
    *,
    labels: tuple[str, ...] = ("D1", "D2"),
) -> tuple[dict[str, object], ...]:
    methods = (
        tool.FrameCfoRateMethod.GLRT_RATE.value,
        tool.FrameCfoRateMethod.FRAME_MAXIMA.value,
        tool.FrameCfoRateMethod.SUMMED_PROFILE.value,
    )
    rows = []
    for label_index, label in enumerate(labels):
        analysis_start_s = 10.0 + label_index
        for duration_ms in (75.0, 125.0):
            for block_index in range(4):
                nominal_start_s = analysis_start_s + block_index * duration_ms / 1_000.0
                nominal_stop_s = nominal_start_s + duration_ms / 1_000.0
                for method_index, method in enumerate(methods):
                    # The earliest 125 ms window is intentionally incomplete.  A selector
                    # must compare only windows for which every displayed method exists.
                    if duration_ms == 125.0 and block_index == 0 and method_index == 2:
                        continue
                    rows.append(
                        {
                            "label": label,
                            "window_id": f"{label}-{duration_ms:g}ms-{block_index:04d}",
                            "duration_ms": duration_ms,
                            "block_index": block_index,
                            "method": method,
                            "nominal_start_s": nominal_start_s,
                            "nominal_stop_s": nominal_stop_s,
                            "reference_time_s": 0.5 * (nominal_start_s + nominal_stop_s),
                            "cfo_hz": 1_000.0 + 30.0 * method_index,
                            "rate_hz_s": -2_000.0 + 100.0 * method_index,
                            "training_objective": 50.0 + method_index,
                            "odd_exact_objective": 40.0 + method_index,
                            "odd_cfo_rms_hz": 20.0 + method_index,
                        }
                    )
    return tuple(rows)


def _track_dwells(*, labels: tuple[str, ...] = ("D1", "D2")) -> tuple[SimpleNamespace, ...]:
    output = []
    for label_index, label in enumerate(labels):
        analysis_start_s = 10.0 + label_index
        output.append(
            SimpleNamespace(
                label=label,
                analysis_start_s=analysis_start_s,
                analysis_stop_s=analysis_start_s + 0.5,
                frame_inventory=(),
                profiles=(),
            )
        )
    return tuple(output)


def test_representative_track_selection_is_response_blind_and_order_invariant() -> None:
    tool = _tool()
    dwells = _track_dwells()
    rows = _track_rows(tool)

    selected = tool._select_representative_windows(dwells, rows)

    assert [entry["label"] for entry in selected] == ["D1", "D2"]
    assert [entry["duration_ms"] for entry in selected] == [125.0, 125.0]
    # The nominal start of block 2 is exactly at each 500 ms dwell midpoint.
    assert [entry["block_index"] for entry in selected] == [2, 2]
    assert [entry["nominal_start_s"] for entry in selected] == [10.25, 11.25]
    assert [entry["nominal_stop_s"] for entry in selected] == [10.375, 11.375]

    mutated_rows = []
    for index, row in enumerate(reversed(rows)):
        changed = dict(row)
        changed.update(
            {
                "cfo_hz": (-1.0 if index % 2 else 1.0) * 1e12,
                "rate_hz_s": index * 1e9,
                "training_objective": -index * 1e8,
                "odd_exact_objective": index * 1e7,
                "odd_cfo_rms_hz": 1e6 - index,
            }
        )
        mutated_rows.append(changed)
    mutated_dwells = tuple(
        SimpleNamespace(
            label=dwell.label,
            analysis_start_s=dwell.analysis_start_s,
            analysis_stop_s=dwell.analysis_stop_s,
            profiles=(),
            frame_inventory=(
                {
                    "reference_time_s": dwell.analysis_start_s + 0.25,
                    "even_absolute_cfo_hz": 1e15,
                    "odd_absolute_cfo_hz": -1e15,
                },
            ),
        )
        for dwell in reversed(dwells)
    )

    mutated = tool._select_representative_windows(
        mutated_dwells,
        tuple(mutated_rows),
    )
    identity_fields = (
        "label",
        "window_id",
        "duration_ms",
        "block_index",
        "nominal_start_s",
        "nominal_stop_s",
    )
    assert [tuple(entry[field] for field in identity_fields) for entry in mutated] == [
        tuple(entry[field] for field in identity_fields) for entry in selected
    ]


def _profile_curve(grid_hz: np.ndarray, peak_hz: float) -> np.ndarray:
    return -((grid_hz - peak_hz) ** 2)


def _payload_dwell(tool: ModuleType, *, reverse: bool = False) -> SimpleNamespace:
    grid_hz = np.asarray((-20.0, 0.0, 20.0))
    profiles = (
        tool.FrameCfoProfile(
            frame_start_sample=100,
            reference_time_s=10.01,
            continuity_segment=0,
            cfo_origin_hz=1_000.0,
            residual_grid_hz=grid_hz,
            even_exact_log_likelihood=_profile_curve(grid_hz, 0.0),
            even_control_log_likelihood=_profile_curve(grid_hz, -8.0),
            odd_exact_log_likelihood=_profile_curve(grid_hz, 3.0),
            odd_control_log_likelihood=_profile_curve(grid_hz, -6.0),
        ),
        tool.FrameCfoProfile(
            frame_start_sample=200,
            reference_time_s=10.07,
            continuity_segment=0,
            cfo_origin_hz=1_010.0,
            residual_grid_hz=grid_hz,
            even_exact_log_likelihood=_profile_curve(grid_hz, 0.0),
            even_control_log_likelihood=_profile_curve(grid_hz, -8.0),
            odd_exact_log_likelihood=_profile_curve(grid_hz, 4.0),
            odd_control_log_likelihood=_profile_curve(grid_hz, -6.0),
        ),
    )
    inventory = (
        {
            "label": "D1",
            "frame_index": -1,
            "reference_time_s": 9.999,
            "continuity_safe": True,
            "training_supported": True,
            "even_absolute_cfo_hz": -9_999.0,
            "odd_absolute_cfo_hz": -9_999.0,
        },
        {
            "label": "D1",
            "frame_index": 0,
            "reference_time_s": 10.01,
            "continuity_safe": True,
            "training_supported": True,
            # Deliberately disagree with the raw-profile peaks.  The visualization
            # must use the exact curves that supplied the fit, not this inventory.
            "even_absolute_cfo_hz": 70_000.0,
            "odd_absolute_cfo_hz": -70_000.0,
        },
        {
            "label": "D1",
            "frame_index": 1,
            "reference_time_s": 10.03,
            "continuity_safe": True,
            "training_supported": False,
            "even_absolute_cfo_hz": 999.0,
            "odd_absolute_cfo_hz": 9_999.0,
        },
        {
            "label": "D1",
            "frame_index": 2,
            "reference_time_s": 10.05,
            "continuity_safe": False,
            "training_supported": False,
            "even_absolute_cfo_hz": None,
            "odd_absolute_cfo_hz": None,
        },
        {
            "label": "D1",
            "frame_index": 3,
            "reference_time_s": 10.07,
            "continuity_safe": True,
            "training_supported": True,
            "even_absolute_cfo_hz": 80_000.0,
            "odd_absolute_cfo_hz": -80_000.0,
        },
        {
            "label": "D1",
            "frame_index": 4,
            # The nominal interval is half-open, so this opportunity is excluded.
            "reference_time_s": 10.125,
            "continuity_safe": True,
            "training_supported": True,
            "even_absolute_cfo_hz": 99_999.0,
            "odd_absolute_cfo_hz": 99_999.0,
        },
    )
    return SimpleNamespace(
        label="D1",
        analysis_start_s=10.0,
        analysis_stop_s=10.125,
        frame_inventory=tuple(reversed(inventory)) if reverse else inventory,
        profiles=tuple(reversed(profiles)) if reverse else profiles,
    )


def _payload_rows(tool: ModuleType) -> tuple[dict[str, object], ...]:
    common = {
        "label": "D1",
        "window_id": "D1-125ms-0000",
        "duration_ms": 125.0,
        "block_index": 0,
        "nominal_start_s": 10.0,
        "nominal_stop_s": 10.125,
        "reference_time_s": 10.05,
        "frame_count": 2,
    }
    return (
        {
            **common,
            "method": tool.FrameCfoRateMethod.GLRT_RATE.value,
            "cfo_hz": 1_000.0,
            "rate_hz_s": 100.0,
            "odd_cfo_rms_hz": math.sqrt((7.0**2 + 12.0**2) / 2.0),
        },
        {
            **common,
            "method": tool.FrameCfoRateMethod.FRAME_MAXIMA.value,
            "cfo_hz": 1_010.0,
            "rate_hz_s": -20.0,
            "odd_cfo_rms_hz": math.sqrt(((-7.8) ** 2 + 4.4**2) / 2.0),
        },
        {
            **common,
            "method": tool.FrameCfoRateMethod.SUMMED_PROFILE.value,
            "cfo_hz": 1_005.0,
            "rate_hz_s": 40.0,
            "odd_cfo_rms_hz": math.sqrt(((-0.4) ** 2 + 8.2**2) / 2.0),
        },
    )


def test_track_payload_uses_supported_half_open_samples_and_exact_odd_residuals() -> None:
    tool = _tool()
    dwell = _payload_dwell(tool)
    rows = _payload_rows(tool)
    selected = tool._select_representative_windows((dwell,), rows)

    payload = tool._track_payload((dwell,), rows, selected)

    assert len(payload) == 1
    track = payload[0]
    assert track["label"] == "D1"
    assert track["window_id"] == "D1-125ms-0000"
    assert track["opportunity_count"] == 4
    assert track["supported_count"] == 2
    assert track["unsupported_time_ms"] == pytest.approx((30.0, 50.0))
    assert track["time_ms"] == pytest.approx((10.0, 70.0))
    assert track["even_cfo_hz"] == pytest.approx((1_000.0, 1_010.0))
    assert track["odd_cfo_hz"] == pytest.approx((1_003.0, 1_014.0))

    fits = {fit["method"]: fit for fit in track["fits"]}
    assert tuple(fits) == (
        tool.FrameCfoRateMethod.GLRT_RATE.value,
        tool.FrameCfoRateMethod.FRAME_MAXIMA.value,
        tool.FrameCfoRateMethod.SUMMED_PROFILE.value,
    )
    assert fits[tool.FrameCfoRateMethod.GLRT_RATE.value]["predicted_cfo_hz"] == pytest.approx(
        (996.0, 1_002.0)
    )
    assert fits[tool.FrameCfoRateMethod.GLRT_RATE.value]["odd_residual_hz"] == pytest.approx(
        (7.0, 12.0)
    )
    assert fits[tool.FrameCfoRateMethod.FRAME_MAXIMA.value]["predicted_cfo_hz"] == pytest.approx(
        (1_010.8, 1_009.6)
    )
    assert fits[tool.FrameCfoRateMethod.FRAME_MAXIMA.value]["odd_residual_hz"] == pytest.approx(
        (-7.8, 4.4)
    )
    assert fits[tool.FrameCfoRateMethod.SUMMED_PROFILE.value]["predicted_cfo_hz"] == pytest.approx(
        (1_003.4, 1_005.8)
    )
    assert fits[tool.FrameCfoRateMethod.SUMMED_PROFILE.value]["odd_residual_hz"] == pytest.approx(
        (-0.4, 8.2)
    )


def test_track_plot_is_valid_and_byte_deterministic_under_input_reordering(
    tmp_path: Path,
) -> None:
    tool = _tool()
    dwell = _payload_dwell(tool)
    rows = _payload_rows(tool)
    selected = tool._select_representative_windows((dwell,), rows)
    payload = tool._track_payload((dwell,), rows, selected)
    reversed_dwell = _payload_dwell(tool, reverse=True)
    reversed_rows = tuple(reversed(rows))
    reversed_selected = tool._select_representative_windows((reversed_dwell,), reversed_rows)
    reordered_payload = tool._track_payload(
        (reversed_dwell,),
        reversed_rows,
        reversed_selected,
    )
    first = tmp_path / "tracks-first.png"
    second = tmp_path / "tracks-second.png"

    tool._plot_tracks(first, payload)
    tool._plot_tracks(second, reordered_payload)

    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(first) as image:
        assert image.format == "PNG"
        assert image.width > 1_000
        assert image.height > 600
        image.verify()
