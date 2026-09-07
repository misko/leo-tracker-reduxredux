from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

from leo.analysis.standard import native_pngs
from leo.analysis.standard.native_analyzers import production_standard_native_evidence_registry


class _Document:
    def __init__(self, **values: Any) -> None:
        self.values = values
        for key, value in values.items():
            setattr(self, key, value)

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return dict(self.values)


def _science(detection: _Document) -> SimpleNamespace:
    return SimpleNamespace(
        detections=(detection,),
        conditioned_hough_replay=(),
        residual_hough_bank=SimpleNamespace(families=(), trajectories=()),
        residual_hough_representatives=(),
        dealiased_trajectory_bank=SimpleNamespace(branches=()),
        final_trajectory_bank=object(),
        cfo_alias_map=_Document(
            alias_spacing_numerator_hz=2_500_000,
            alias_spacing_denominator=11,
        ),
    )


def test_native_png_source_cannot_filter_path_evidence_by_cross_radio_intervals() -> None:
    parameters = inspect.signature(native_pngs.native_standard_png_source).parameters

    assert "valid_utc_intervals" not in parameters
    assert "preserve_per_path_waterfall" not in parameters


def test_path_source_preserves_detections_and_breaks_only_at_own_continuity_boundary(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        native_pngs,
        "build_final_trajectory_table_v3",
        lambda _bank: _Document(trajectories=()),
    )
    source = SimpleNamespace(
        stream_id="stream-0",
        radio_id="radio-0",
        receiver_id=0,
        sample_rate_hz=10,
        tuned_center_frequency_hz=1_190_000_000,
        timing=SimpleNamespace(first_estimate_utc_ns=1_000_000_000),
        continuity_segments=(
            _Document(segment_index=0),
            _Document(segment_index=1),
        ),
    )
    first = _Document(sample_start=2, time_s=0.2, marker="first")
    second = _Document(sample_start=3, time_s=0.3, marker="second")
    stateful = SimpleNamespace(
        source=source,
        segments=(
            SimpleNamespace(global_device_sample_start=0, local_science=_science(first)),
            SimpleNamespace(global_device_sample_start=20, local_science=_science(second)),
        ),
    )
    waterfall = SimpleNamespace(waterfall=_Document(tiles=()))
    report = SimpleNamespace(segments=())
    config = SimpleNamespace(feedback=SimpleNamespace(subwindow_ms=25, probe_ms=20))

    path = native_pngs._path_source(
        waterfall,
        stateful,
        report,
        config=config,
        origin_utc_ns=1_000_000_000,
    )

    detections = path.pilot_scan["detections"]
    assert tuple(item.get("marker") for item in detections) == ("first", None, "second")
    assert tuple(item["time_s"] for item in detections) == (0.2, 2.0, 2.3)
    assert detections[1]["reason"] == "continuity boundary; no scientific sample"
    assert detections[1]["scores"] == ()


def test_paired_presentation_identity_marks_path_local_evidence_semantics() -> None:
    spec = production_standard_native_evidence_registry().get("paired-presentation-native").spec

    assert spec.algorithm_version == "standard-native-paired-presentation-v9"
    assert spec.configuration_schema == "paired-presentation-native.evidence.v8"
