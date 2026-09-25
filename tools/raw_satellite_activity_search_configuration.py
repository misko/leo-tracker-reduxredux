"""Pure search-configuration construction for raw catalogue activity studies.

This module deliberately has no storage discovery or replay dependencies. It
is shared by catalogue replay and structural-penalty plan preparation so a
predeclared digest covers exactly the configuration later persisted by replay.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]

INPUT_SCHEMA = "org.leo.research.duration-constrained-satellite-assignment-input/v1"
OUTPUT_SCHEMA = "org.leo.research.raw-catalogue-satellite-activity-replay/v1"
ALGORITHM = "starlink-full-window-coarse-to-fine-v1"
NULL_CERTIFICATE_ALGORITHM = "optimistic-zero-residual-semi-markov-lower-bound-v1"
GROUPED_REPLAY_ALGORITHM = "bounded-exhaustive-grouped-nuisance-semimarkov-v1"
MEMBER_EVALUATION_SCOPE_ALGORITHM = "raw-catalogue-member-evaluation-scope-v1"
CONTROLLED_STUDY_FAMILY_ALGORITHM = "controlled-search-configuration-family-v1"
PRODUCER_IMPLEMENTATION_MANIFEST_ALGORITHM = "raw-catalogue-producer-file-manifest-v1"

_PRODUCER_IMPLEMENTATION_PATHS = (
    "tools/screen_raw_satellite_activity_catalog.py",
    "tools/raw_satellite_activity_search_configuration.py",
    "tools/replay_raw_grouped_satellite_activity.py",
    "tools/replay_joint_fixed_satellite_activity.py",
    "src/leo/analysis/research/satellite_activity.py",
    "src/leo/analysis/research/multi_satellite_activity.py",
    "src/leo/analysis/research/grouped_satellite_activity.py",
    "src/leo/analysis/research/satellite_activity_scores.py",
    "src/leo/sky/doppler.py",
    "src/leo/sky/frames.py",
    "src/leo/sky/propagation.py",
    "src/leo/sky/sampling.py",
    "src/leo/sky/screening.py",
    "src/leo/contracts/base.py",
    "src/leo/contracts/digests.py",
    "src/leo/contracts/sky.py",
    "pyproject.toml",
    "uv.lock",
)

_PILOT_SCAN_CONFIGURATION_FIELDS = (
    "schema_version",
    "algorithm_version",
    "maximum_scored_candidates_per_probe",
    "methods",
    "probe_samples",
    "coarse_window_samples",
    "subwindow_samples",
    "frequency_coordinate",
    "frequency_reference",
)


def _positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class CatalogueScreenConfig:
    """Staged catalogue search controls outside the final raw replay config."""

    name_prefix: str = "STARLINK"
    geometry_spacing_s: float = 0.5
    coarse_delay_step_s: float = 0.5
    coarse_modes_per_delay: int = 1
    refinement_catalog_count: int = 32
    refinement_guard_cost: float = 0.0
    maximum_refinement_catalog_count: int = 64
    final_catalog_count: int = 3

    def __post_init__(self) -> None:
        if not self.name_prefix.strip():
            raise ValueError("catalogue name prefix must not be empty")
        for value, label in (
            (self.geometry_spacing_s, "geometry spacing"),
            (self.coarse_delay_step_s, "coarse delay step"),
        ):
            _positive(value, label)
        if not math.isfinite(self.refinement_guard_cost) or self.refinement_guard_cost < 0.0:
            raise ValueError("refinement guard cost must be finite and nonnegative")
        for value, label in (
            (self.coarse_modes_per_delay, "coarse modes per delay"),
            (self.refinement_catalog_count, "refinement catalogue count"),
            (self.maximum_refinement_catalog_count, "maximum refinement catalogue count"),
            (self.final_catalog_count, "final catalogue count"),
        ):
            _positive_integer(value, label)
        if self.refinement_catalog_count > self.maximum_refinement_catalog_count:
            raise ValueError("refinement catalogue count exceeds its hard maximum")
        if self.final_catalog_count not in {2, 3}:
            raise ValueError("the existing grouped oracle requires two or three final catalogues")
        if self.final_catalog_count > self.refinement_catalog_count:
            raise ValueError("final catalogue count exceeds refinement catalogue count")


def _json_copy(value: Any, label: str) -> Any:
    """Copy a JSON value while rejecting NaN and non-JSON state."""

    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must contain only finite JSON values") from error


def producer_implementation_manifest() -> dict[str, Any]:
    """Digest the fixed producer implementation surface used by plan and replay."""

    repository_root = Path(__file__).resolve().parents[1]
    files = []
    for relative_path in _PRODUCER_IMPLEMENTATION_PATHS:
        path = repository_root / relative_path
        if not path.is_file():
            raise ValueError(f"producer implementation file is missing: {relative_path}")
        files.append(
            {
                "path": relative_path,
                "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "algorithm": PRODUCER_IMPLEMENTATION_MANIFEST_ALGORITHM,
        "files": files,
        "runtime_versions": {
            "python": ".".join(str(item) for item in sys.version_info[:3]),
            "numpy": importlib.metadata.version("numpy"),
            "sgp4": importlib.metadata.version("sgp4"),
        },
    }


def pilot_scan_search_configuration(document: dict[str, Any]) -> dict[str, Any]:
    """Retain exactly the scan fields that change candidate opportunities."""

    if any(label not in document for label in _PILOT_SCAN_CONFIGURATION_FIELDS):
        raise ValueError("pilot scan omits search-configuration fields")
    methods = document["methods"]
    if not isinstance(methods, list) or any(not isinstance(item, str) for item in methods):
        raise ValueError("pilot scan methods are not a string list")
    return {
        label: _json_copy(document[label], f"pilot scan {label}")
        for label in _PILOT_SCAN_CONFIGURATION_FIELDS
    }


def build_member_evaluation_scope(
    *,
    duration_dataset_digest: str,
    pilot_scan_digest: str,
    session_id: str,
    recording_manifest_digest: str,
    stream_id: str,
    receiver_id: int,
    tuning_tag: str,
    sky_frequency_hz: float,
    scheduled_probe_ids: tuple[str, ...],
    window_start_s: float,
    window_end_s: float,
) -> dict[str, Any]:
    """Bind one member's immutable input identity and exact evaluation window."""

    return {
        "algorithm": MEMBER_EVALUATION_SCOPE_ALGORITHM,
        "duration_dataset_digest": duration_dataset_digest,
        "pilot_scan_digest": pilot_scan_digest,
        "capture": {
            "session_id": session_id,
            "recording_manifest_digest": recording_manifest_digest,
            "stream_id": stream_id,
            "receiver_id": receiver_id,
        },
        "frequency_binding": {
            "tuning_tag": tuning_tag,
            "sky_frequency_hz": sky_frequency_hz,
        },
        "window": {
            "start_s": window_start_s,
            "end_s": window_end_s,
            "scheduled_probe_ids": list(scheduled_probe_ids),
        },
    }


def member_evaluation_scope_digest(**kwargs: Any) -> str:
    """Return the canonical digest for :func:`build_member_evaluation_scope`."""

    return canonical_digest(build_member_evaluation_scope(**kwargs))


def controlled_study_configuration_family(
    search_configuration: dict[str, Any],
) -> dict[str, Any]:
    """Project a member search onto settings controlled across the whole study."""

    copied = _json_copy(search_configuration, "search configuration")
    if not isinstance(copied, dict):
        raise ValueError("search configuration must be an object")
    raw_replay = copied.get("raw_replay")
    if not isinstance(raw_replay, dict):
        raise ValueError("search configuration raw replay must be an object")
    for label in ("satellite_cost", "episode_cost"):
        if label not in raw_replay:
            raise ValueError(f"search configuration raw replay omits {label}")
        del raw_replay[label]
    for label in ("sky_frequency_hz", "member_evaluation_scope_digest"):
        if label not in copied:
            raise ValueError(f"search configuration omits source-bound {label}")
        del copied[label]
    return {
        "algorithm": CONTROLLED_STUDY_FAMILY_ALGORITHM,
        "controlled_search_configuration": copied,
    }


def controlled_study_configuration_family_digest(
    search_configuration: dict[str, Any],
) -> str:
    return canonical_digest(controlled_study_configuration_family(search_configuration))


def build_search_configuration(
    *,
    calibration_schema: object,
    calibration_digest: str,
    tle_digest: str,
    sky_frequency_hz: float,
    pilot_scan_configuration: dict[str, Any],
    observer_configuration: dict[str, Any],
    window_start_s: float,
    window_end_s: float,
    scheduled_probe_count: int,
    cell_count: int,
    member_evaluation_scope_digest: str,
    producer_implementation: dict[str, Any],
    raw_replay_configuration: dict[str, Any],
    catalogue_screen_configuration: dict[str, Any],
) -> dict[str, Any]:
    """Build canonical, data-path-independent catalogue search settings."""

    return {
        "algorithm": ALGORITHM,
        "output_schema": OUTPUT_SCHEMA,
        "null_certificate_algorithm": NULL_CERTIFICATE_ALGORITHM,
        "grouped_replay_algorithm": GROUPED_REPLAY_ALGORITHM,
        "input_schema": INPUT_SCHEMA,
        "score_calibration_schema": _json_copy(calibration_schema, "score calibration schema"),
        "score_calibration_digest": calibration_digest,
        "tle_digest": tle_digest,
        "sky_frequency_hz": sky_frequency_hz,
        "member_evaluation_scope_digest": member_evaluation_scope_digest,
        "producer_implementation": _json_copy(
            producer_implementation, "producer implementation manifest"
        ),
        "pilot_scan": _json_copy(pilot_scan_configuration, "pilot scan configuration"),
        "observer": _json_copy(observer_configuration, "observer configuration"),
        "window": {
            "start_s": window_start_s,
            "end_s": window_end_s,
            "duration_s": window_end_s - window_start_s,
            "scheduled_probe_count": scheduled_probe_count,
            "cell_count": cell_count,
        },
        "raw_replay": _json_copy(raw_replay_configuration, "raw replay configuration"),
        "catalogue_screen": _json_copy(
            catalogue_screen_configuration, "catalogue screen configuration"
        ),
        "catalogue_scope": {
            "full_probe_by_delay_visibility_required": True,
            "rise_set_objects_supported": False,
            "data_proposed_cfo_modes": True,
        },
    }
