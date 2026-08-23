from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_glrt_phase_segment_comparison.py"
    spec = importlib.util.spec_from_file_location("glrt_phase_segment_comparison_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trajectory(
    trajectory_id: str,
    branch_id: str,
    *,
    rate: float,
    observations: int,
    alias_index: int,
    margin: float,
) -> SimpleNamespace:
    return SimpleNamespace(
        trajectory_id=trajectory_id,
        branch_id=branch_id,
        polynomial_degree=1,
        absolute_coefficients_hz=(rate, 10_000.0),
        observation_ids=tuple(f"observation-{index}" for index in range(observations)),
        evaluated_probe_count=observations + 10,
        median_block_corrected_margin=margin,
        alias_index=alias_index,
        start_s=1.0,
        end_s=3.0,
    )


def _evidence(scope: str, trajectories, qualifications) -> SimpleNamespace:
    return SimpleNamespace(
        scope=scope,
        final_bank=SimpleNamespace(trajectories=tuple(trajectories)),
        pilot_segments=SimpleNamespace(
            trajectory_summaries=tuple(
                SimpleNamespace(
                    source_trajectory_id=trajectory_id,
                    qualified_segment_count=count,
                )
                for trajectory_id, count in qualifications.items()
            )
        ),
    )


def test_alias_deduplication_keeps_one_rate_and_phase_capable_representative() -> None:
    tool = _tool()
    aliases = (
        _trajectory(
            "trajectory-a", "branch-a", rate=-5_000.0, observations=20, alias_index=0, margin=0.5
        ),
        _trajectory(
            "trajectory-b", "branch-a", rate=-5_000.0, observations=20, alias_index=1, margin=0.5
        ),
    )
    evidence = _evidence("sha256:scope-a", aliases, {"trajectory-a": 0, "trajectory-b": 3})

    tracks = tool.deduplicate_glrt_tracks((evidence,))

    assert len(tracks) == 1
    assert tracks[0].representative_trajectory_id == "trajectory-b"
    assert tracks[0].alias_trajectory_ids == ("trajectory-a", "trajectory-b")
    assert tracks[0].glrt_rate_hz_s == -5_000.0
    assert tracks[0].qualified_75ms_window_count == 3


def test_track_ranking_uses_persistent_support_not_local_rate() -> None:
    tool = _tool()
    evidence = SimpleNamespace(scope="scope")
    low_support = tool.GlrtTrack(
        "scope-b",
        "branch-b",
        "trajectory-b",
        ("trajectory-b",),
        10,
        20,
        2.0,
        1.0,
        3.0,
        -1_000.0,
        0.9,
        8,
        SimpleNamespace(),
        evidence,
    )
    high_support = tool.GlrtTrack(
        "scope-a",
        "branch-a",
        "trajectory-a",
        ("trajectory-a",),
        100,
        110,
        2.0,
        1.0,
        3.0,
        -9_000.0,
        0.1,
        1,
        SimpleNamespace(),
        evidence,
    )

    selected = tool.select_strongest_phase_capable_tracks((low_support, high_support), 2)

    assert [item.representative_trajectory_id for item in selected] == [
        "trajectory-a",
        "trajectory-b",
    ]


def test_path_binding_requires_a_unique_scope_prefix() -> None:
    tool = _tool()
    scopes = ("sha256:abc111", "sha256:abc222")

    parsed = tool.parse_path_bindings(["sha256:abc1=stream-0:1:upper"], scopes)

    assert parsed["sha256:abc111"].label == "stream-0/RX1 upper"
    with pytest.raises(ValueError, match="resolved to 2 scopes"):
        tool.parse_path_bindings(["sha256:abc=stream-0:1:upper"], scopes)


def test_supported_span_uses_only_applied_phase_updates() -> None:
    tool = _tool()
    result = SimpleNamespace(
        frames=(
            SimpleNamespace(time_s=0.000, measurement_supported=False, phase_update_applied=False),
            SimpleNamespace(time_s=0.010, measurement_supported=True, phase_update_applied=True),
            SimpleNamespace(time_s=0.020, measurement_supported=True, phase_update_applied=False),
            SimpleNamespace(time_s=0.045, measurement_supported=True, phase_update_applied=True),
            SimpleNamespace(time_s=0.069, measurement_supported=False, phase_update_applied=True),
        )
    )

    assert tool.supported_span_s(result) == pytest.approx(0.035)


def test_inconsistent_alias_slopes_are_rejected() -> None:
    tool = _tool()
    aliases = (
        _trajectory(
            "trajectory-a", "branch-a", rate=-5_000.0, observations=20, alias_index=0, margin=0.5
        ),
        _trajectory(
            "trajectory-b", "branch-a", rate=-4_999.0, observations=20, alias_index=1, margin=0.5
        ),
    )
    evidence = _evidence("sha256:scope-a", aliases, {})

    with pytest.raises(ValueError, match="inconsistent GLRT rates"):
        tool.deduplicate_glrt_tracks((evidence,))


def test_rate_comparison_figure_renders_segment_uncertainty(tmp_path: Path) -> None:
    tool = _tool()
    track = SimpleNamespace(
        glrt_rate_hz_s=-5_700.0,
        representative_trajectory_id="sha256:trajectory-a",
    )
    analyses = tuple(
        SimpleNamespace(
            phase_segment_qualified=True,
            document={
                "reference_time_s": 48.0 + index,
                "local_doppler_rate_hz_s": -3_800.0 + 20 * index,
                "local_doppler_rate_sigma_hz_s": 120.0,
                "kalman_doppler_rate_hz_s": -3_850.0 + 25 * index,
            },
            binding=SimpleNamespace(label="stream-0/RX0 upper"),
            track=track,
        )
        for index in range(3)
    )
    destination = tmp_path / "rate-comparison.png"

    tool.render_rate_comparison(destination, (analyses,))

    assert destination.is_file()
    assert destination.stat().st_size > 0
