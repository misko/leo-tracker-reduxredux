"""Deterministic explicitly placed Standard probe scheduling."""

from __future__ import annotations

from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import ProbeScheduleV2, ProbeWindowV2


def build_probe_schedule(
    *,
    sample_rate_hz: int,
    sample_count: int,
    subwindow_ms: int = 50,
    probe_ms: int = 20,
    probe_offsets_ms: tuple[int, ...] = (0, 25),
    maximum_coarse_windows: int = 120,
) -> ProbeScheduleV2:
    """Create the exact bounded schedule without reading IQ.

    Only complete one-second coarse windows and complete leading probes are
    scheduled. ``source_probe_count`` describes the unbounded geometry while
    the returned list accounts for the configured coarse-window cap.
    """

    integers = (sample_rate_hz, subwindow_ms, probe_ms, maximum_coarse_windows)
    if any(isinstance(value, bool) or value <= 0 for value in integers):
        raise ValueError("schedule geometry must be positive")
    if sample_count < 0:
        raise ValueError("sample_count cannot be negative")
    if 1_000 % subwindow_ms:
        raise ValueError("subwindow_ms must divide one second")
    if probe_ms > subwindow_ms:
        raise ValueError("probe_ms cannot exceed subwindow_ms")
    if (
        not probe_offsets_ms
        or probe_offsets_ms != tuple(sorted(set(probe_offsets_ms)))
        or any(
            isinstance(offset, bool) or not isinstance(offset, int) for offset in probe_offsets_ms
        )
        or any(offset < 0 or offset + probe_ms > subwindow_ms for offset in probe_offsets_ms)
    ):
        raise ValueError("probe offsets must be unique, ordered, and contained in each subwindow")
    if sample_rate_hz * subwindow_ms % 1_000 or sample_rate_hz * probe_ms % 1_000:
        raise ValueError("schedule durations must map to integral samples")
    if any(sample_rate_hz * offset % 1_000 for offset in probe_offsets_ms):
        raise ValueError("probe offsets must map to integral samples")

    complete_seconds = sample_count // sample_rate_hz
    probes_per_second = 1_000 // subwindow_ms
    source_probe_count = complete_seconds * probes_per_second * len(probe_offsets_ms)
    returned_seconds = min(complete_seconds, maximum_coarse_windows)
    subwindow_samples = sample_rate_hz * subwindow_ms // 1_000
    probe_samples = sample_rate_hz * probe_ms // 1_000
    probes = []
    for coarse_index in range(returned_seconds):
        coarse_start = coarse_index * sample_rate_hz
        for subwindow_index in range(probes_per_second):
            subwindow_start = coarse_start + subwindow_index * subwindow_samples
            for probe_offset_ms in probe_offsets_ms:
                sample_start = subwindow_start + sample_rate_hz * probe_offset_ms // 1_000
                identity = {
                    "algorithm_version": "standard-probe-schedule-v2",
                    "sample_rate_hz": sample_rate_hz,
                    "coarse_window_index": coarse_index,
                    "subwindow_index": subwindow_index,
                    "probe_offset_ms": probe_offset_ms,
                    "sample_start": sample_start,
                    "sample_count": probe_samples,
                }
                probes.append(
                    ProbeWindowV2(
                        probe_id=canonical_digest(identity),
                        coarse_window_index=coarse_index,
                        subwindow_index=subwindow_index,
                        probe_offset_ms=probe_offset_ms,
                        sample_start=sample_start,
                        sample_count=probe_samples,
                        time_s=sample_start / sample_rate_hz,
                    )
                )
    values = {
        "schema_version": 2,
        "algorithm_version": "standard-probe-schedule-v2",
        "sample_rate_hz": sample_rate_hz,
        "declared_sample_count": sample_count,
        "coarse_window_ms": 1000,
        "subwindow_ms": subwindow_ms,
        "probe_ms": probe_ms,
        "probe_offsets_ms": probe_offsets_ms,
        "maximum_coarse_windows": maximum_coarse_windows,
        "source_probe_count": source_probe_count,
        "returned_probe_count": len(probes),
        "truncated_probe_count": source_probe_count - len(probes),
        "probes": [item.model_dump(mode="json") for item in probes],
    }
    return ProbeScheduleV2.model_validate({**values, "schedule_digest": canonical_digest(values)})
