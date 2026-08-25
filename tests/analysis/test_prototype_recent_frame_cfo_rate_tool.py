from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

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
