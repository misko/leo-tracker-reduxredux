"""Assemble frozen child bundles into one continuous multiscan numerical input."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

LIGHT_SPEED_KM_S = 299_792.458
FRAME_LATITUDE_DEG = 38.5816
FRAME_LONGITUDE_DEG = -121.4944
NODE_SPACING_S = 0.25
TAU_BOUND_S = 11.0
CHILD_ARRAY_NAMES = (
    "times",
    "measured",
    "rf",
    "receiver",
    "channel",
    "group",
    "margin",
    "nodes",
    "position",
    "velocity",
    "numbers",
    "initial",
)


@dataclass(frozen=True)
class OrbitStates:
    satellite_ids: np.ndarray
    position_km: np.ndarray
    velocity_km_s: np.ndarray
    snapshot: dict


class OrbitStateProvider(Protocol):
    def __call__(
        self,
        snapshot: dict,
        satellite_ids: np.ndarray,
        origin_utc_ns: int,
        nodes_s: np.ndarray,
    ) -> OrbitStates: ...


@dataclass(frozen=True)
class _Child:
    session_id: str
    origin_utc_ns: int
    manifest: dict
    arrays: dict[str, np.ndarray]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observation_nodes(times_s: np.ndarray) -> np.ndarray:
    times = np.asarray(times_s, dtype=float)
    if times.ndim != 1 or not len(times) or np.any(~np.isfinite(times)):
        raise ValueError("observation times must be a nonempty finite vector")
    first = np.floor((float(np.min(times)) - TAU_BOUND_S) / NODE_SPACING_S) * NODE_SPACING_S
    final_query = float(np.max(times)) + TAU_BOUND_S
    last = np.ceil(final_query / NODE_SPACING_S) * NODE_SPACING_S + NODE_SPACING_S
    count = int(round((last - first) / NODE_SPACING_S)) + 1
    return first + np.arange(count, dtype=float) * NODE_SPACING_S


def _load_child(directory: Path, expected_session: str, expected_dataset: str) -> _Child:
    manifest_path = directory / "bundle.json"
    archive_path = directory / "bundle.npz"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "coherent-localization-bundle/v1":
        raise ValueError(f"{expected_session}: unsupported child bundle schema")
    if manifest.get("session_id") != expected_session:
        raise ValueError(f"{expected_session}: child session identity mismatch")
    if manifest.get("dataset") != expected_dataset:
        raise ValueError(f"{expected_session}: child dataset identity mismatch")
    expected_digest = manifest.get("artifacts", {}).get("bundle_npz_sha256")
    if expected_digest and _sha256(archive_path) != expected_digest:
        raise ValueError(f"{expected_session}: child archive digest mismatch")
    with np.load(archive_path, allow_pickle=False) as source:
        missing = sorted(set(CHILD_ARRAY_NAMES) - set(source.files))
        if missing:
            raise ValueError(f"{expected_session}: child archive lacks {', '.join(missing)}")
        arrays = {name: source[name].copy() for name in CHILD_ARRAY_NAMES}
    origin = manifest.get("origin_utc_ns")
    if not isinstance(origin, int):
        raise ValueError(f"{expected_session}: child origin_utc_ns is invalid")
    _validate_child(expected_session, arrays, manifest.get("tracks"))
    return _Child(expected_session, origin, manifest, arrays)


def _validate_child(session_id: str, arrays: dict[str, np.ndarray], tracks) -> None:
    times = arrays["times"]
    if times.ndim != 1 or not len(times) or np.any(~np.isfinite(times)):
        raise ValueError(f"{session_id}: child times are invalid")
    for name in ("measured", "rf", "receiver", "channel", "group", "margin"):
        if arrays[name].shape != times.shape:
            raise ValueError(f"{session_id}: child {name} does not align with times")
    numbers = arrays["numbers"]
    if numbers.ndim != 1 or not len(numbers) or len(np.unique(numbers)) != len(numbers):
        raise ValueError(f"{session_id}: child candidate IDs are invalid")
    if arrays["initial"].shape != (6 + len(numbers),):
        raise ValueError(f"{session_id}: child initial vector has the wrong size")
    nodes = arrays["nodes"]
    state_shape = (len(numbers), len(nodes), 3)
    if (
        nodes.ndim != 1
        or len(nodes) < 2
        or arrays["position"].shape != state_shape
        or arrays["velocity"].shape != state_shape
    ):
        raise ValueError(f"{session_id}: child ephemeris arrays are invalid")
    if not isinstance(tracks, list):
        raise ValueError(f"{session_id}: child tracks are invalid")
    for track in tracks:
        rows = np.asarray(track.get("rows"), dtype=int)
        candidates = np.asarray(track.get("candidate_indices"), dtype=int)
        if rows.ndim != 1 or np.any(rows < 0) or np.any(rows >= len(times)):
            raise ValueError(f"{session_id}: child track rows are invalid")
        if candidates.ndim != 1 or np.any(candidates < 0) or np.any(candidates >= len(numbers)):
            raise ValueError(f"{session_id}: child track candidates are invalid")


def _snapshot_from_first_child(child: _Child) -> dict:
    snapshot = child.manifest.get("provenance", {}).get("tle_snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("earliest child lacks frozen TLE snapshot provenance")
    required = ("provider", "collected_utc_ns", "digest")
    if any(name not in snapshot for name in required):
        raise ValueError("earliest child TLE snapshot provenance is incomplete")
    if int(snapshot["collected_utc_ns"]) >= child.origin_utc_ns:
        raise ValueError("frozen unit TLE snapshot is not causal")
    return {name: snapshot[name] for name in required}


def _coordinates(point: np.ndarray) -> tuple[float, float]:
    east, north = point
    angular = np.hypot(east, north) / 6371.0088
    bearing = np.arctan2(east, north)
    latitude, longitude = np.deg2rad([FRAME_LATITUDE_DEG, FRAME_LONGITUDE_DEG])
    result_latitude = np.arcsin(
        np.sin(latitude) * np.cos(angular) + np.cos(latitude) * np.sin(angular) * np.cos(bearing)
    )
    result_longitude = longitude + np.arctan2(
        np.sin(bearing) * np.sin(angular) * np.cos(latitude),
        np.cos(angular) - np.sin(latitude) * np.sin(result_latitude),
    )
    return tuple(np.rad2deg([result_latitude, result_longitude]))


def _ecef(latitude_deg: float, longitude_deg: float) -> np.ndarray:
    latitude, longitude = np.deg2rad([latitude_deg, longitude_deg])
    eccentricity = (1 / 298.257223563) * (2 - 1 / 298.257223563)
    radius = 6378.137 / np.sqrt(1 - eccentricity * np.sin(latitude) ** 2)
    return np.array(
        [
            radius * np.cos(latitude) * np.cos(longitude),
            radius * np.cos(latitude) * np.sin(longitude),
            radius * (1 - eccentricity) * np.sin(latitude),
        ]
    )


class JointData:
    """Dynamic-candidate multiscan input with one continuous UTC time base."""

    def __init__(
        self,
        *,
        dataset: str,
        unit_id: str,
        child_sessions: tuple[str, ...],
        child_origins_utc_ns: np.ndarray,
        origin_utc_ns: int,
        reference_time_s: float,
        snapshot: dict,
        arrays: dict[str, np.ndarray],
        nodes: np.ndarray,
        numbers: np.ndarray,
        position: np.ndarray,
        velocity: np.ndarray,
        initial: np.ndarray,
        tracks: list[dict],
        capture_index: np.ndarray,
        provenance: dict | None = None,
    ) -> None:
        self.dataset = dataset
        self.unit_id = unit_id
        self.session_id = unit_id
        self.child_sessions = child_sessions
        self.child_origins_utc_ns = np.asarray(child_origins_utc_ns, dtype=np.int64)
        self.origin_utc_ns = int(origin_utc_ns)
        self.reference_time_s = float(reference_time_s)
        self.reference_epoch_utc_ns = self.origin_utc_ns + round(self.reference_time_s * 1e9)
        self.tle_snapshot = dict(snapshot)
        for name, values in arrays.items():
            setattr(self, name, np.asarray(values))
        self.nodes = np.asarray(nodes, dtype=float)
        self.numbers = np.asarray(numbers, dtype=np.int64)
        self.position = np.asarray(position, dtype=float)
        self.velocity = np.asarray(velocity, dtype=float)
        self.initial = np.asarray(initial, dtype=float)
        self.tracks = [
            {
                **track,
                "rows": np.asarray(track["rows"], dtype=np.int64),
                "candidate_indices": np.asarray(track["candidate_indices"], dtype=np.int64),
            }
            for track in tracks
        ]
        self.capture_index = np.asarray(capture_index, dtype=np.int64)
        self.provenance = {} if provenance is None else dict(provenance)
        self.parameter_names = (
            "east_km",
            "north_km",
            "rx0_intercept_hz_at_unit_reference",
            "rx0_slope_hz_s",
            "rx1_intercept_hz_at_unit_reference",
            "rx1_slope_hz_s",
            *(f"tau_s_{int(number)}" for number in self.numbers),
        )
        self._validate()

    def _validate(self) -> None:
        count = len(self.times)
        if count == 0 or np.any(~np.isfinite(self.times)):
            raise ValueError("joint times must be nonempty and finite")
        for name in ("measured", "rf", "receiver", "channel", "group", "margin"):
            if getattr(self, name).shape != (count,):
                raise ValueError(f"joint {name} does not align with times")
        if self.capture_index.shape != (count,):
            raise ValueError("capture_index does not align with times")
        if np.any(self.capture_index < 0) or np.any(self.capture_index >= len(self.child_sessions)):
            raise ValueError("capture_index falls outside child_sessions")
        for group in np.unique(self.group):
            if len(np.unique(self.capture_index[self.group == group])) != 1:
                raise ValueError("a remapped source group crosses child captures")
        candidate_count = len(self.numbers)
        if candidate_count == 0 or len(np.unique(self.numbers)) != candidate_count:
            raise ValueError("joint candidate IDs must be nonempty and unique")
        expected = (candidate_count, len(self.nodes), 3)
        if self.position.shape != expected or self.velocity.shape != expected:
            raise ValueError("full union ephemeris shape is incomplete")
        if np.any(~np.isfinite(self.position)) or np.any(~np.isfinite(self.velocity)):
            raise ValueError("full union ephemeris must be finite")
        if np.any(np.linalg.norm(self.position, axis=-1) <= 6378.137):
            raise ValueError("full union ephemeris contains non-orbital positions")
        spacing = np.diff(self.nodes)
        if (
            self.nodes.ndim != 1
            or len(self.nodes) < 2
            or np.any(~np.isfinite(self.nodes))
            or not np.allclose(spacing, NODE_SPACING_S, rtol=0.0, atol=1e-12)
        ):
            raise ValueError("joint nodes must be a uniform 0.25-second grid")
        if np.min(self.times) - TAU_BOUND_S < self.nodes[0] - 1e-12:
            raise ValueError("joint ephemeris does not cover negative timing shifts")
        if np.max(self.times) + TAU_BOUND_S >= self.nodes[-1]:
            raise ValueError("joint ephemeris does not cover positive timing shifts")
        if self.initial.shape != (6 + candidate_count,) or np.any(~np.isfinite(self.initial)):
            raise ValueError("joint initial vector has the wrong size or nonfinite values")
        for track in self.tracks:
            rows = np.asarray(track["rows"], dtype=int)
            satellites = np.asarray(track["candidate_indices"], dtype=int)
            capture = int(track["capture_index"])
            if rows.ndim != 1 or np.any(rows < 0) or np.any(rows >= count):
                raise ValueError("joint track rows are invalid")
            if np.any(self.capture_index[rows] != capture):
                raise ValueError("joint track rows do not preserve capture lineage")
            if (
                satellites.ndim != 1
                or np.any(satellites < 0)
                or np.any(satellites >= candidate_count)
            ):
                raise ValueError("joint track candidates are invalid")

    def predict(self, parameters, rows=None, satellites=None):
        parameters = np.asarray(parameters, dtype=float)
        if parameters.shape != (6 + len(self.numbers),) or np.any(~np.isfinite(parameters)):
            raise ValueError("parameters must match [east,north,a0,b0,a1,b1,tau per satellite]")
        if (rows is None) != (satellites is None):
            raise ValueError("Supply paired rows and satellites, or neither")
        if rows is None:
            rows = np.arange(len(self.times))[:, None]
            satellites = np.arange(len(self.numbers))[None, :]
        else:
            rows = np.asarray(rows, dtype=int)
            satellites = np.asarray(satellites, dtype=int)
            if rows.shape != satellites.shape:
                raise ValueError("Paired rows and satellite indices must have identical shapes")
            if np.any(rows < 0) or np.any(rows >= len(self.times)):
                raise ValueError("row index falls outside joint observations")
            if np.any(satellites < 0) or np.any(satellites >= len(self.numbers)):
                raise ValueError("satellite index falls outside the union bank")
        query = self.times[rows] + parameters[6:][satellites]
        if np.any(query < self.nodes[0]) or np.any(query >= self.nodes[-1]):
            raise ValueError("Shifted orbit time lies outside the joint ephemeris")
        fraction = (query - self.nodes[0]) / NODE_SPACING_S
        lower = np.floor(fraction).astype(int)
        weight = (fraction - lower)[..., None]
        position = (
            self.position[satellites, lower] * (1 - weight)
            + self.position[satellites, lower + 1] * weight
        )
        velocity = (
            self.velocity[satellites, lower] * (1 - weight)
            + self.velocity[satellites, lower + 1] * weight
        )
        latitude, longitude = _coordinates(parameters[:2])
        receiver_position = _ecef(latitude, longitude)
        delta = position - receiver_position
        direction = delta / np.linalg.norm(delta, axis=-1)[..., None]
        latitude_rad, longitude_rad = np.deg2rad([latitude, longitude])
        up = np.array(
            [
                np.cos(latitude_rad) * np.cos(longitude_rad),
                np.cos(latitude_rad) * np.sin(longitude_rad),
                np.sin(latitude_rad),
            ]
        )
        receive_time = self.times[rows]
        receiver = self.receiver[rows]
        offset = parameters[2 + 2 * receiver] + parameters[3 + 2 * receiver] * (
            receive_time - self.reference_time_s
        )
        prediction = (
            -self.rf[rows] * np.sum(direction * velocity, axis=-1) / LIGHT_SPEED_KM_S + offset
        )
        return prediction, np.sum(direction * up, axis=-1) >= 0


def assemble_unit(
    selection_path: Path,
    dataset: str,
    unit_id: str,
    scans_root: Path,
    orbit_state_provider: OrbitStateProvider,
) -> JointData:
    selection = json.loads(Path(selection_path).read_text())
    try:
        units = selection["datasets"][dataset]["units"]
    except KeyError as error:
        raise ValueError(f"frozen selection lacks dataset {dataset}") from error
    matches = [unit for unit in units if unit.get("unit_id") == unit_id]
    if len(matches) != 1:
        raise ValueError(f"frozen selection does not identify exactly one unit {unit_id}")
    session_ids = tuple(matches[0].get("session_ids", ()))
    if (
        len(session_ids) not in (1, 2, 4)
        or matches[0].get("size") != len(session_ids)
        or len(set(session_ids)) != len(session_ids)
    ):
        raise ValueError("frozen unit must contain one, two, or four distinct child sessions")
    children = tuple(
        _load_child(Path(scans_root) / session_id, session_id, dataset)
        for session_id in session_ids
    )
    origins = np.asarray([child.origin_utc_ns for child in children], dtype=np.int64)
    if np.any(np.diff(origins) <= 0):
        raise ValueError("frozen unit child origins must be strictly chronological")
    origin = int(origins[0])
    offsets = (origins - origin).astype(float) / 1e9

    arrays = {
        name: [] for name in ("times", "measured", "rf", "receiver", "channel", "group", "margin")
    }
    capture_index = []
    tracks = []
    group_offset = 0
    row_offset = 0
    for child_index, (child, time_offset) in enumerate(zip(children, offsets, strict=True)):
        child_count = len(child.arrays["times"])
        arrays["times"].append(child.arrays["times"] + time_offset)
        for name in ("measured", "rf", "receiver", "channel", "margin"):
            arrays[name].append(child.arrays[name])
        child_groups, inverse = np.unique(child.arrays["group"], return_inverse=True)
        arrays["group"].append(inverse.astype(np.int64) + group_offset)
        group_offset += len(child_groups)
        capture_index.append(np.full(child_count, child_index, dtype=np.int64))
        for track in child.manifest["tracks"]:
            tracks.append(
                {
                    **track,
                    "track_id": f"{child.session_id}:{track['track_id']}",
                    "source_track_id": track["track_id"],
                    "session_id": child.session_id,
                    "capture_index": child_index,
                    "rows": np.asarray(track["rows"], dtype=int) + row_offset,
                    "candidate_numbers": np.asarray(
                        [
                            child.arrays["numbers"][index]
                            for index in np.asarray(track["candidate_indices"], dtype=int)
                        ],
                        dtype=np.int64,
                    ),
                }
            )
        row_offset += child_count
    combined = {name: np.concatenate(parts) for name, parts in arrays.items()}
    capture_index_array = np.concatenate(capture_index)
    numbers = np.unique(np.concatenate([child.arrays["numbers"] for child in children]))
    number_to_union = {int(number): index for index, number in enumerate(numbers)}
    for track in tracks:
        track["candidate_indices"] = np.asarray(
            [number_to_union[int(number)] for number in track.pop("candidate_numbers")],
            dtype=np.int64,
        )

    nodes = observation_nodes(combined["times"])
    snapshot = _snapshot_from_first_child(children[0])
    states = orbit_state_provider(snapshot, numbers.copy(), origin, nodes.copy())
    if not isinstance(states, OrbitStates):
        raise TypeError("orbit_state_provider must return OrbitStates")
    if not np.array_equal(np.asarray(states.satellite_ids, dtype=np.int64), numbers):
        raise ValueError("orbit provider did not return every union satellite in requested order")
    if states.snapshot != snapshot:
        raise ValueError("orbit provider did not preserve the pinned unit TLE snapshot")

    reference_time = 0.5 * (float(np.min(combined["times"])) + float(np.max(combined["times"])))
    initial = np.zeros(6 + len(numbers), dtype=float)
    first_initial = children[0].arrays["initial"]
    initial[:2] = first_initial[:2]
    for receiver in (0, 1):
        intercept_index = 2 + 2 * receiver
        slope_index = intercept_index + 1
        initial[intercept_index] = first_initial[intercept_index] + first_initial[slope_index] * (
            reference_time - 150.0
        )
        initial[slope_index] = first_initial[slope_index]
    initialized_tau = set()
    for child in children:
        for child_index, number in enumerate(child.arrays["numbers"]):
            union_index = number_to_union[int(number)]
            if union_index not in initialized_tau:
                initial[6 + union_index] = child.arrays["initial"][6 + child_index]
                initialized_tau.add(union_index)

    selection_path = Path(selection_path)
    scans_root = Path(scans_root)
    provenance = {
        "scope": (
            "frozen multiscan numerical input; no evaluation reference read and no fit performed"
        ),
        "timing_authority": "each child bundle origin_utc_ns",
        "selection": {
            "path": str(selection_path),
            "sha256": _sha256(selection_path),
        },
        "children": [
            {
                "session_id": child.session_id,
                "origin_utc_ns": child.origin_utc_ns,
                "bundle_json_sha256": _sha256(scans_root / child.session_id / "bundle.json"),
                "bundle_npz_sha256": _sha256(scans_root / child.session_id / "bundle.npz"),
            }
            for child in children
        ],
        "tle_snapshot": dict(snapshot),
        "reference_truth_read": False,
    }

    return JointData(
        dataset=dataset,
        unit_id=unit_id,
        child_sessions=session_ids,
        child_origins_utc_ns=origins,
        origin_utc_ns=origin,
        reference_time_s=reference_time,
        snapshot=snapshot,
        arrays=combined,
        nodes=nodes,
        numbers=numbers,
        position=states.position_km,
        velocity=states.velocity_km_s,
        initial=initial,
        tracks=tracks,
        capture_index=capture_index_array,
        provenance=provenance,
    )


def _jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def save_joint_data(data: JointData, directory: Path) -> dict:
    """Persist one validated joint unit atomically without replacing prior evidence."""
    if not isinstance(data, JointData):
        raise TypeError("data must be JointData")
    data._validate()
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError(f"refusing to replace existing joint bundle: {directory}")
    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{directory.name}.", dir=directory.parent))
    try:
        arrays = {
            name: getattr(data, name)
            for name in (
                "times",
                "measured",
                "rf",
                "receiver",
                "channel",
                "group",
                "margin",
                "capture_index",
                "nodes",
                "position",
                "velocity",
                "numbers",
                "initial",
                "child_origins_utc_ns",
            )
        }
        archive_path = temporary / "bundle.npz"
        np.savez(archive_path, **arrays)
        manifest = {
            "schema": "multiscan-coherent-localization-bundle/v1",
            "dataset": data.dataset,
            "unit_id": data.unit_id,
            "child_sessions": list(data.child_sessions),
            "origin_utc_ns": data.origin_utc_ns,
            "reference_time_s": data.reference_time_s,
            "reference_epoch_utc_ns": data.reference_epoch_utc_ns,
            "parameter_order": "[east,north,a0,b0,a1,b1,tau per union satellite]",
            "candidate_count": len(data.numbers),
            "tle_snapshot": dict(data.tle_snapshot),
            "tracks": _jsonable(data.tracks),
            "provenance": _jsonable(data.provenance),
            "artifacts": {"bundle_npz_sha256": _sha256(archive_path)},
        }
        (temporary / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
        temporary.rename(directory)
        return manifest
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def load_joint_data(directory: Path) -> JointData:
    """Load one persisted joint unit after binding its arrays to the manifest digest."""
    directory = Path(directory)
    manifest = json.loads((directory / "bundle.json").read_text())
    if manifest.get("schema") != "multiscan-coherent-localization-bundle/v1":
        raise ValueError("unsupported joint bundle schema")
    archive_path = directory / "bundle.npz"
    expected_digest = manifest.get("artifacts", {}).get("bundle_npz_sha256")
    if not isinstance(expected_digest, str) or _sha256(archive_path) != expected_digest:
        raise ValueError("joint bundle.npz digest mismatch")
    required = {
        "times",
        "measured",
        "rf",
        "receiver",
        "channel",
        "group",
        "margin",
        "capture_index",
        "nodes",
        "position",
        "velocity",
        "numbers",
        "initial",
        "child_origins_utc_ns",
    }
    with np.load(archive_path, allow_pickle=False) as source:
        missing = sorted(required - set(source.files))
        if missing:
            raise ValueError(f"joint bundle.npz lacks arrays: {', '.join(missing)}")
        arrays = {name: source[name].copy() for name in required}
    reference_time = manifest.get("reference_time_s")
    if reference_time is None:
        reference_time = manifest.get("reference_epoch", {}).get("time_from_unit_origin_s")
    snapshot = manifest.get("tle_snapshot")
    if snapshot is None:
        snapshot = manifest.get("ephemeris", {}).get("snapshot")
    if reference_time is None or not isinstance(snapshot, dict):
        raise ValueError("joint bundle lacks reference epoch or TLE snapshot provenance")
    candidate_count = manifest.get("candidate_count")
    if candidate_count is None:
        candidate_count = manifest.get("candidate_union", {}).get("count")
    if candidate_count != len(arrays["numbers"]):
        raise ValueError("joint manifest candidate count does not match arrays")
    provenance = manifest.get("provenance")
    if provenance is None:
        provenance = {
            "legacy_manifest_artifacts": manifest.get("artifacts", {}),
            "timing_authority": manifest.get("timing_authority"),
            "tle_snapshot": snapshot,
            "reference_truth_read": manifest.get("verification", {}).get("reference_truth_read"),
        }
    data = JointData(
        dataset=manifest["dataset"],
        unit_id=manifest["unit_id"],
        child_sessions=tuple(manifest["child_sessions"]),
        child_origins_utc_ns=arrays.pop("child_origins_utc_ns"),
        origin_utc_ns=int(manifest["origin_utc_ns"]),
        reference_time_s=float(reference_time),
        snapshot=snapshot,
        arrays={
            name: arrays[name]
            for name in ("times", "measured", "rf", "receiver", "channel", "group", "margin")
        },
        nodes=arrays["nodes"],
        numbers=arrays["numbers"],
        position=arrays["position"],
        velocity=arrays["velocity"],
        initial=arrays["initial"],
        tracks=manifest["tracks"],
        capture_index=arrays["capture_index"],
        provenance=provenance,
    )
    expected_epoch = manifest.get("reference_epoch_utc_ns")
    if expected_epoch is not None and data.reference_epoch_utc_ns != int(expected_epoch):
        raise ValueError("joint reference epoch does not match persisted time origin")
    return data


class ArchiveOrbitStateProvider:
    """Lazy read-only adapter from one pinned archive snapshot to a full state bank."""

    def __init__(self, tle_root: Path) -> None:
        self.tle_root = Path(tle_root)

    def __call__(
        self,
        snapshot: dict,
        satellite_ids: np.ndarray,
        origin_utc_ns: int,
        nodes_s: np.ndarray,
    ) -> OrbitStates:
        from leo.analysis.adaptive_tle_prediction import propagate_candidate_states

        from leo.operations.tle_archive import TleArchiveReader
        from leo.sky.propagation import parse_element_sets

        reader = TleArchiveReader(self.tle_root)
        matches = [
            item
            for item in reader.list_snapshots(snapshot["provider"])
            if item.collected_utc_ns == int(snapshot["collected_utc_ns"])
            and item.digest == snapshot["digest"]
        ]
        if len(matches) != 1 or matches[0].collected_utc_ns >= origin_utc_ns:
            raise ValueError("pinned unit TLE snapshot is absent or noncausal")
        catalogue = parse_element_sets(reader.read(matches[0]))
        catalogue_numbers = np.asarray(catalogue.satellite_numbers, dtype=np.int64)
        lookup = {int(number): index for index, number in enumerate(catalogue_numbers)}
        missing = [int(number) for number in satellite_ids if int(number) not in lookup]
        if missing:
            raise ValueError(f"pinned TLE snapshot lacks required satellite IDs: {missing}")
        indices = np.asarray([lookup[int(number)] for number in satellite_ids], dtype=int)
        position, velocity, valid = propagate_candidate_states(
            catalogue,
            indices,
            origin_utc_ns,
            np.asarray(nodes_s, dtype=float),
            np.asarray([0.0]),
        )
        if not np.array_equal(valid, indices):
            failed = [int(catalogue_numbers[index]) for index in indices if index not in set(valid)]
            raise ValueError(f"required satellites lack full unit orbit coverage: {failed}")
        return OrbitStates(
            np.asarray(satellite_ids, dtype=np.int64).copy(),
            position[:, 0],
            velocity[:, 0],
            dict(snapshot),
        )


__all__ = [
    "ArchiveOrbitStateProvider",
    "JointData",
    "OrbitStateProvider",
    "OrbitStates",
    "assemble_unit",
    "load_joint_data",
    "observation_nodes",
    "save_joint_data",
]
