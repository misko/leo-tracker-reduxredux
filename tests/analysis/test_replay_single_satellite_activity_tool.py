from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

VALLADO_00005 = (
    "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753\n"
    "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667\n"
)


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/replay_single_satellite_activity.py"
    spec = importlib.util.spec_from_file_location("replay_single_satellite_activity_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _curve(times_s: tuple[float, ...], delay_s: float) -> np.ndarray:
    shifted = np.asarray(times_s, dtype=np.float64) + delay_s
    return 1_000.0 * shifted * shifted - 3_000.0 * shifted


def _mock_geometry(
    *,
    times_s: tuple[float, ...],
    delay_s: float,
    **_kwargs: object,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    count = len(times_s)
    return (
        _curve(times_s, delay_s),
        np.full(count, 65.0, dtype=np.float64),
        np.full(count, 550.0, dtype=np.float64),
    )


def _fixture(
    tmp_path: Path,
    tool: ModuleType,
    *,
    active_cells: tuple[int, ...] = (2, 3, 4, 5, 6),
    missing_probe: tuple[int, int] | None = None,
) -> tuple[dict[str, object], Path, Path, str]:
    sample_rate_hz = 1_000_000
    first_utc_ns = 962_131_819_733_568_000
    component_id = "sha256:component"
    branch_id = "sha256:branch"
    scheduled = []
    observations = []
    for cell_index in range(10):
        for offset_index, offset_s in enumerate((0.025, 0.075)):
            ordinal = 2 * cell_index + offset_index
            time_s = cell_index * 0.1 + offset_s
            sample_start = round(time_s * sample_rate_hz)
            probe_id = f"probe-{cell_index:02d}-{offset_index}"
            has_observation = cell_index in active_cells and missing_probe != (
                cell_index,
                offset_index,
            )
            scheduled.append(
                {
                    "probe_id": probe_id,
                    "schedule_ordinal": ordinal,
                    "coarse_window_index": 0,
                    "subwindow_index": cell_index,
                    "probe_offset_ms": 25 if offset_index == 0 else 75,
                    "probe_sample_start": sample_start,
                    "probe_sample_count": 20_000,
                    "probe_start_time_s": time_s,
                    "probe_start_utc": {
                        "earliest_utc_ns": first_utc_ns + round(time_s * 1e9),
                        "estimate_utc_ns": first_utc_ns + round(time_s * 1e9),
                        "latest_utc_ns": first_utc_ns + round(time_s * 1e9),
                    },
                    "scan_detection_present": True,
                    "scan_status": "complete" if has_observation else "no_result",
                    "usable_for_activity": True,
                    "source_candidate_count": int(has_observation),
                    "retained_candidate_count": int(has_observation),
                    "truncated_candidate_count": 0,
                }
            )
            if has_observation:
                source_id = f"source-{cell_index:02d}-{offset_index}"
                observations.append(
                    {
                        "branch_id": branch_id,
                        "component_id": component_id,
                        "probe_id": probe_id,
                        "probe_sample_start": sample_start,
                        "measurement_time_s": time_s,
                        "source_observation_id": source_id,
                        "component_cfo_hz": float(_curve((time_s,), 0.1)[0] + 100_000.0),
                    }
                )
    dataset: dict[str, object] = {
        "schema": tool.INPUT_SCHEMA,
        "candidate_only": True,
        "satellite_specificity_claimed": False,
        "capture": {
            "session_id": "cap-test",
            "stream_id": "stream-0",
            "radio_id": "radio-test",
            "radio_serial": "serial-test",
            "receiver_id": 0,
            "recording_manifest_digest": "sha256:manifest",
            "sample_rate_hz": sample_rate_hz,
            "declared_sample_count": sample_rate_hz,
            "observed_sample_count": sample_rate_hz,
            "coverage_fraction": 1.0,
        },
        "frequency_binding": {"sky_frequency_hz": 11_000_000_000},
        "timing_binding": {"first_estimate_utc_ns": first_utc_ns},
        "scheduled_probes": scheduled,
        "alias_components": [
            {
                "component_id": component_id,
                "status": "resolved",
                "branch_ids": [branch_id],
            }
        ],
        "branches": [
            {
                "branch_id": branch_id,
                "component_id": component_id,
                "source_probe_count": len(observations),
                "observations": observations,
            }
        ],
        "source_products": {},
    }
    dataset_path = tmp_path / "input.json"
    _write(dataset_path, dataset)
    tle_path = tmp_path / "snapshot.tle"
    tle_path.write_text(VALLADO_00005, encoding="utf-8")
    tle_digest = "sha256:" + hashlib.sha256(tle_path.read_bytes()).hexdigest()
    return dataset, dataset_path, tle_path, tle_digest


def _replay(
    tool: ModuleType,
    dataset: dict[str, object],
    dataset_path: Path,
    tle_path: Path,
    tle_digest: str,
    *,
    config: object | None = None,
) -> dict[str, object]:
    return tool.replay_branch(
        dataset=dataset,
        dataset_path=dataset_path,
        tle_path=tle_path,
        expected_tle_digest=tle_digest,
        catalog_number=5,
        branch_id="sha256:branch",
        observer=tool.ObserverSiteV1(
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            label="test-observer",
        ),
        config=config
        or tool.ReplayConfig(
            delay_min_s=-0.2,
            delay_max_s=0.2,
            delay_step_s=0.1,
            delay_prior_sigma_s=1.0,
            cfo_sigma_hz=5.0,
            detection_probability=0.9,
            clutter_cost=8.0,
            satellite_cost=2.0,
            episode_cost=1.0,
        ),
    )


def test_replay_recovers_one_exact_half_second_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    monkeypatch.setattr(tool, "_doppler_curve", _mock_geometry)
    dataset, dataset_path, tle_path, tle_digest = _fixture(tmp_path, tool)

    result = _replay(tool, dataset, dataset_path, tle_path, tle_digest)

    assert result["schema"] == tool.OUTPUT_SCHEMA
    assert result["specificity_claimed"] is False
    assert result["conditional_on_dealiased_branch"] is True
    assert result["costs_calibrated"] is False
    assert result["profile"]["posterior_best_delay_s"] == pytest.approx(0.1)
    assert result["profile"]["posterior_best_cfo_offset_hz"] == pytest.approx(100_000.0)
    assert result["profile"]["holdout_observation_count"] == 4
    assert result["activity"]["selected"] is True
    assert result["activity"]["episodes"] == [
        {
            "start_cell": 2,
            "end_cell_exclusive": 7,
            "duration_s": 0.5,
            "left_censored": False,
            "right_censored": False,
        }
    ]
    assert len(result["activity"]["assignments"]) == 10
    assert result["activity"]["missed_probe_ids"] == []


def test_no_result_probe_is_preserved_as_an_active_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    monkeypatch.setattr(tool, "_doppler_curve", _mock_geometry)
    dataset, dataset_path, tle_path, tle_digest = _fixture(tmp_path, tool, missing_probe=(4, 1))

    result = _replay(tool, dataset, dataset_path, tle_path, tle_digest)

    assert result["activity"]["selected"] is True
    assert result["activity"]["missed_probe_ids"] == ["probe-04-1"]
    assert result["branch"]["usable_scheduled_probe_count"] == 20


def test_replay_rejects_unresolved_or_cross_component_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    monkeypatch.setattr(tool, "_doppler_curve", _mock_geometry)
    dataset, dataset_path, tle_path, tle_digest = _fixture(tmp_path, tool)
    unresolved = deepcopy(dataset)
    unresolved["alias_components"][0]["status"] = "insufficient"
    with pytest.raises(ValueError, match="resolved CFO component"):
        _replay(tool, unresolved, dataset_path, tle_path, tle_digest)

    cross_component = deepcopy(dataset)
    cross_component["branches"][0]["observations"][0]["component_id"] = "other"
    with pytest.raises(ValueError, match="independently gauged"):
        _replay(tool, cross_component, dataset_path, tle_path, tle_digest)


def test_replay_is_deterministic_under_input_permutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    monkeypatch.setattr(tool, "_doppler_curve", _mock_geometry)
    dataset, dataset_path, tle_path, tle_digest = _fixture(tmp_path, tool)
    first = _replay(tool, dataset, dataset_path, tle_path, tle_digest)
    permuted = deepcopy(dataset)
    permuted["scheduled_probes"].reverse()
    permuted["branches"][0]["observations"].reverse()

    second = _replay(tool, permuted, dataset_path, tle_path, tle_digest)

    assert second == first


def test_replay_rejects_tle_digest_mismatch_and_qnap_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    monkeypatch.setattr(tool, "_doppler_curve", _mock_geometry)
    dataset, dataset_path, tle_path, _tle_digest = _fixture(tmp_path, tool)
    with pytest.raises(ValueError, match="TLE digest mismatch"):
        _replay(tool, dataset, dataset_path, tle_path, "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="refuses output"):
        tool._refuse_qnap_output(Path("/mnt/qnap01/research/replay.json"))
