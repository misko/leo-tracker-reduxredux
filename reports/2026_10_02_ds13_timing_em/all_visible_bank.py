"""Export a truth-free all-visible Starlink ephemeris bank for the DS13 scans."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
LEGACY = ROOT.parent / "2026_10_02_localization_benchmark"
MULTI = ROOT.parent / "2026_10_02_multiscan_localization"
POPULATION = ROOT.parent / "2026_10_02_ds13_from_911c4e5d" / "local" / "manifest.json"
OUTPUT_ROOT = ROOT / "all-visible-bank"
TLE_ROOT = Path("/var/lib/leo/tle")
SESSIONS = (
    "scan-fw-911c4e5db9243281",
    "scan-fw-ffa1cc19d8d7c09f",
)
TIMING_WINDOW_S = 10.0
PATCH_HALF_WIDTH_KM = 5.0
NODE_SPACING_S = 0.25
MAX_NUMERICAL_SECONDS = 180.0
SCREEN_BATCH_SIZE = 128
STATE_BATCH_SIZE = 64
ARRAY_NAMES = (
    "nodes",
    "numbers",
    "position",
    "velocity",
    "initial",
    "old_numbers",
    "old_to_expanded",
    "maximum_elevation_sine",
    "screen_visible",
    "retained_original",
)
OBSERVATION_NAMES = ("times", "measured", "rf", "receiver", "channel", "group", "margin")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _array_digest(values) -> str:
    values = np.ascontiguousarray(values)
    header = values.dtype.str.encode() + np.asarray(values.shape, dtype="<i8").tobytes()
    return _sha256_bytes(header + values.tobytes())


def _snapshot_files(paths) -> dict[str, str]:
    snapshot = {}
    for value in paths:
        path = Path(value).resolve()
        key = str(path)
        if key in snapshot:
            raise ValueError(f"duplicate source path {key}")
        snapshot[key] = _sha256_file(path)
    return snapshot


def _assert_snapshot_unchanged(snapshot: dict[str, str]) -> None:
    changed = [path for path, expected in snapshot.items() if _sha256_file(Path(path)) != expected]
    if changed:
        raise RuntimeError(f"all-visible source changed before seal: {', '.join(changed)}")


def _validate_nodes(nodes) -> np.ndarray:
    nodes = np.asarray(nodes, dtype=float)
    if (
        nodes.ndim != 1
        or len(nodes) < 2
        or np.any(~np.isfinite(nodes))
        or not np.allclose(np.diff(nodes), NODE_SPACING_S, rtol=0.0, atol=1e-12)
    ):
        raise ValueError("ephemeris nodes must be a finite quarter-second grid")
    return nodes


def _visibility_nodes(times, nodes, timing_window_s=TIMING_WINDOW_S) -> np.ndarray:
    times = np.asarray(times, dtype=float)
    nodes = _validate_nodes(nodes)
    if times.ndim != 1 or not len(times) or np.any(~np.isfinite(times)):
        raise ValueError("observation times must be a nonempty finite vector")
    if not np.isfinite(timing_window_s) or timing_window_s < 0:
        raise ValueError("timing window must be finite and nonnegative")
    lower = float(np.min(times) - timing_window_s)
    upper = float(np.max(times) + timing_window_s)
    selected = nodes[(nodes >= lower - 1e-12) & (nodes <= upper + 1e-12)]
    incomplete = (
        not len(selected)
        or selected[0] - lower > NODE_SPACING_S
        or upper - selected[-1] > NODE_SPACING_S
    )
    if incomplete:
        raise ValueError("source ephemeris does not cover the requested visibility window")
    return selected


def _patch_observers(center_km, half_width_km=PATCH_HALF_WIDTH_KM):
    from joint_inputs import _coordinates, _ecef

    center = np.asarray(center_km, dtype=float)
    if center.shape != (2,) or np.any(~np.isfinite(center)):
        raise ValueError("patch center must be a finite east/north pair")
    if not np.isfinite(half_width_km) or half_width_km <= 0:
        raise ValueError("patch half-width must be positive and finite")
    offsets = np.asarray(
        [(east, north) for east in (-half_width_km, 0.0, half_width_km)
         for north in (-half_width_km, 0.0, half_width_km)],
        dtype=float,
    )
    observers = []
    coordinates = []
    for point in center + offsets:
        latitude, longitude = _coordinates(point)
        latitude_rad, longitude_rad = np.deg2rad([latitude, longitude])
        up = np.asarray(
            [
                np.cos(latitude_rad) * np.cos(longitude_rad),
                np.cos(latitude_rad) * np.sin(longitude_rad),
                np.sin(latitude_rad),
            ]
        )
        observers.append((_ecef(latitude, longitude), up))
        coordinates.append((latitude, longitude))
    return offsets, np.asarray(coordinates), observers


def _screen_visible(
    catalogue,
    candidate_indices,
    origin_utc_ns,
    nodes,
    observers,
    propagate,
    deadline,
):
    maximum = {}
    valid_indices = set()
    for begin in range(0, len(candidate_indices), SCREEN_BATCH_SIZE):
        if time.monotonic() >= deadline:
            raise TimeoutError("all-visible screening exceeded its numerical deadline")
        batch = candidate_indices[begin : begin + SCREEN_BATCH_SIZE]
        position, _velocity, valid = propagate(
            catalogue,
            batch,
            origin_utc_ns,
            nodes,
            np.asarray([0.0]),
        )
        position = np.asarray(position, dtype=float)[:, 0]
        for local, catalogue_index in enumerate(np.asarray(valid, dtype=int)):
            valid_indices.add(int(catalogue_index))
            highest = -np.inf
            for receiver, up in observers:
                delta = position[local] - receiver
                sine = np.sum(delta * up, axis=-1) / np.linalg.norm(delta, axis=-1)
                highest = max(highest, float(np.max(sine)))
            maximum[int(catalogue_index)] = highest
    visible = {index for index, height in maximum.items() if height >= 0.0}
    return visible, valid_indices, maximum


def _propagate_states(
    catalogue,
    candidate_indices,
    origin_utc_ns,
    nodes,
    propagate,
    deadline,
):
    states = {}
    for begin in range(0, len(candidate_indices), STATE_BATCH_SIZE):
        if time.monotonic() >= deadline:
            raise TimeoutError("all-visible state export exceeded its numerical deadline")
        batch = candidate_indices[begin : begin + STATE_BATCH_SIZE]
        position, velocity, valid = propagate(
            catalogue,
            batch,
            origin_utc_ns,
            nodes,
            np.asarray([0.0]),
        )
        position = np.asarray(position, dtype=float)[:, 0]
        velocity = np.asarray(velocity, dtype=float)[:, 0]
        for local, catalogue_index in enumerate(np.asarray(valid, dtype=int)):
            states[int(catalogue_index)] = (position[local].copy(), velocity[local].copy())
    return states


def _expanded_order(old_numbers, catalogue_numbers, visible_indices, fully_propagated):
    old_numbers = np.asarray(old_numbers, dtype=np.int64)
    catalogue_numbers = np.asarray(catalogue_numbers, dtype=np.int64)
    if len(np.unique(catalogue_numbers)) != len(catalogue_numbers):
        raise ValueError("catalogue numbers must be unique")
    by_number = {int(number): index for index, number in enumerate(catalogue_numbers)}
    missing = [int(number) for number in old_numbers if int(number) not in by_number]
    if missing:
        raise ValueError(f"original candidates are absent from archived catalogue: {missing}")
    old_indices = [by_number[int(number)] for number in old_numbers]
    failed_old = [
        int(catalogue_numbers[index])
        for index in old_indices
        if index not in fully_propagated
    ]
    if failed_old:
        raise ValueError(f"original candidates lack complete ephemeris: {failed_old}")
    additions = sorted(
        (
            index
            for index in visible_indices
            if index in fully_propagated and index not in old_indices
        ),
        key=lambda index: int(catalogue_numbers[index]),
    )
    return np.asarray([*old_indices, *additions], dtype=int)


def _expand_parameters(parameters, old_to_expanded, candidate_count):
    parameters = np.asarray(parameters, dtype=float)
    old_to_expanded = np.asarray(old_to_expanded, dtype=int)
    if parameters.shape != (6 + len(old_to_expanded),):
        raise ValueError("source parameters do not match the original candidate bank")
    if (
        len(np.unique(old_to_expanded)) != len(old_to_expanded)
        or np.any(old_to_expanded < 0)
        or np.any(old_to_expanded >= candidate_count)
    ):
        raise ValueError("old-to-expanded map is invalid")
    expanded = np.zeros(6 + candidate_count, dtype=float)
    expanded[:6] = parameters[:6]
    expanded[6 + old_to_expanded] = parameters[6:]
    return expanded


class ExpandedScanData:
    """Expanded ephemeris with the unchanged alias-family observation geometry."""

    def __init__(self, source, arrays, receipt):
        for name in OBSERVATION_NAMES:
            setattr(self, name, np.asarray(getattr(source, name)).copy())
        for name in ARRAY_NAMES:
            setattr(self, name, np.asarray(arrays[name]).copy())
        self.session_id = receipt["session_id"]
        self.reference_time_s = float(getattr(source, "reference_time_s", 150.0))
        self.original_rows = np.asarray(getattr(source, "original_rows", []), dtype=int).copy()
        self.geometry_receipt = getattr(source, "geometry_receipt", None)
        self.bank_receipt = receipt
        self._validate()

    def _validate(self):
        count = len(self.times)
        misaligned = any(
            np.asarray(getattr(self, name)).shape != (count,) for name in OBSERVATION_NAMES
        )
        if not count or misaligned:
            raise ValueError("observation arrays must be aligned nonempty vectors")
        self.nodes = _validate_nodes(self.nodes)
        candidate_count = len(self.numbers)
        expected = (candidate_count, len(self.nodes), 3)
        if (
            candidate_count <= 64
            or self.position.shape != expected
            or self.velocity.shape != expected
        ):
            raise ValueError("expanded candidate states have inconsistent dimensions")
        if self.initial.shape != (6 + candidate_count,) or np.any(~np.isfinite(self.initial)):
            raise ValueError("expanded initial parameters are invalid")
        if len(np.unique(self.numbers)) != candidate_count:
            raise ValueError("expanded catalogue numbers must be unique")
        if not np.array_equal(self.numbers[self.old_to_expanded], self.old_numbers):
            raise ValueError("old-to-expanded candidate map does not preserve the original bank")
        if np.any(~np.isfinite(self.position)) or np.any(~np.isfinite(self.velocity)):
            raise ValueError("expanded ephemeris must be finite")

    def expand_parameters(self, parameters):
        return _expand_parameters(parameters, self.old_to_expanded, len(self.numbers))

    def remap_satellites(self, old_satellite_indices):
        indices = np.asarray(old_satellite_indices, dtype=int)
        if np.any(indices < 0) or np.any(indices >= len(self.old_to_expanded)):
            raise ValueError("original satellite index falls outside the old bank")
        return self.old_to_expanded[indices]

    def predict(self, parameters, rows=None, satellites=None):
        from joint_inputs import LIGHT_SPEED_KM_S, _coordinates, _ecef

        if (rows is None) != (satellites is None):
            raise ValueError("supply paired rows and satellites, or neither")
        if rows is None:
            rows = np.arange(len(self.times))[:, None]
            satellites = np.arange(len(self.numbers))[None, :]
        else:
            rows = np.asarray(rows, dtype=int)
            satellites = np.asarray(satellites, dtype=int)
            if rows.shape != satellites.shape:
                raise ValueError("paired rows and satellites must have identical shapes")
        parameters = np.asarray(parameters, dtype=float)
        if parameters.shape != (6 + len(self.numbers),):
            raise ValueError("parameters do not match the expanded candidate bank")
        query = self.times[rows] + parameters[6:][satellites]
        if np.any(query < self.nodes[0]) or np.any(query >= self.nodes[-1]):
            raise ValueError("shifted orbit time lies outside exported ephemeris")
        fraction = (query - self.nodes[0]) / NODE_SPACING_S
        lower = np.floor(fraction).astype(int)
        weight = (fraction - lower)[..., None]
        position = self.position[satellites, lower] * (1 - weight)
        position += self.position[satellites, lower + 1] * weight
        velocity = self.velocity[satellites, lower] * (1 - weight)
        velocity += self.velocity[satellites, lower + 1] * weight
        latitude, longitude = _coordinates(parameters[:2])
        delta = position - _ecef(latitude, longitude)
        direction = delta / np.linalg.norm(delta, axis=-1)[..., None]
        latitude_rad, longitude_rad = np.deg2rad([latitude, longitude])
        up = np.asarray(
            [
                np.cos(latitude_rad) * np.cos(longitude_rad),
                np.cos(latitude_rad) * np.sin(longitude_rad),
                np.sin(latitude_rad),
            ]
        )
        receive_time = self.times[rows]
        receiver = self.receiver[rows]
        offset = parameters[2 + 2 * receiver]
        offset += parameters[3 + 2 * receiver] * (receive_time - self.reference_time_s)
        prediction = -self.rf[rows] * np.sum(direction * velocity, axis=-1) / LIGHT_SPEED_KM_S
        return prediction + offset, np.sum(direction * up, axis=-1) >= 0


def _load_from_directory(directory: Path, source):
    receipt_path = directory / "receipt.json"
    archive_path = directory / "expanded.npz"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("schema") != "ds13-all-visible-bank/v1":
        raise ValueError("unsupported all-visible bank schema")
    if receipt.get("artifacts", {}).get("expanded_npz_sha256") != _sha256_file(archive_path):
        raise ValueError("expanded ephemeris digest does not match receipt")
    for path, expected in receipt.get("source_hashes", {}).items():
        if _sha256_file(Path(path)) != expected:
            raise ValueError(f"all-visible source hash changed: {path}")
    current_hashes = {name: _array_digest(getattr(source, name)) for name in OBSERVATION_NAMES}
    if current_hashes != receipt.get("observation_array_hashes"):
        raise ValueError("source observation arrays differ from the sealed expansion")
    with np.load(archive_path, allow_pickle=False) as archive:
        missing = sorted(set(ARRAY_NAMES) - set(archive.files))
        if missing:
            raise ValueError(f"expanded archive lacks arrays: {', '.join(missing)}")
        arrays = {name: archive[name].copy() for name in ARRAY_NAMES}
    expected_hashes = receipt.get("expanded_array_hashes", {})
    if {name: _array_digest(arrays[name]) for name in ARRAY_NAMES} != expected_hashes:
        raise ValueError("expanded array hashes differ from the receipt")
    return ExpandedScanData(source, arrays, receipt)


def load_expanded_scan(session):
    if session not in SESSIONS:
        raise ValueError("session is outside the frozen DS13 pair")
    from prepare_scans import load_scan

    _raw, source = load_scan(session)
    return _load_from_directory(OUTPUT_ROOT / session, source)


def _source_paths(session, runtime_objects):
    evidence = POPULATION.parent / "analysis" / f"{session}.json"
    bundle = ROOT / "scans" / session
    medium = ROOT / "runs-continuation" / session / "medium" / "fit.json"
    paths = [
        Path(__file__),
        ROOT / "prepare_scans.py",
        ROOT / "position-profile-protocol.json",
        ROOT / "position-profile-resource-amendment.json",
        POPULATION,
        evidence,
        bundle / "bundle.json",
        bundle / "bundle.npz",
        medium,
        LEGACY / "export_ds11.py",
        LEGACY / "bundle.py",
        MULTI / "finite_set_alias_family.py",
        MULTI / "finite_set_fit.py",
        MULTI / "joint_inputs.py",
        MULTI / "prediction_jacobian.py",
    ]
    paths.extend(Path(inspect.getfile(value)) for value in runtime_objects)
    return paths


def export_all_visible_bank(session, *, max_numerical_seconds=MAX_NUMERICAL_SECONDS):
    if session not in SESSIONS:
        raise ValueError("session is outside the frozen DS13 pair")
    if not 0 < max_numerical_seconds <= MAX_NUMERICAL_SECONDS:
        raise ValueError("numerical deadline must lie in (0, 180] seconds")
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from prepare_scans import load_scan
    from rough_smoke import load_module

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    helper = load_module("ds13_all_visible_export_helpers", LEGACY / "export_ds11.py")
    runtime_objects = (
        propagate_candidate_states,
        exclude_labelled_starlink_debris,
        TleArchiveReader,
        parse_element_sets,
    )
    source_hashes = _snapshot_files(_source_paths(session, runtime_objects))
    evidence_path = POPULATION.parent / "analysis" / f"{session}.json"
    product = json.loads(evidence_path.read_text())["tracking"]["product"]
    manifest = json.loads((ROOT / "scans" / session / "bundle.json").read_text())
    parent = json.loads(
        (ROOT / "runs-continuation" / session / "medium" / "fit.json").read_text()
    )
    if (
        manifest.get("session_id") != session
        or parent.get("session") != session
        or parent.get("reference_read_before_seal") is not False
        or parent.get("schema") != "ds13-soft-continuation-fit/v1"
    ):
        raise ValueError("source scan or truth-free patch-center fit is invalid")
    raw, source = load_scan(session)
    origin_utc_ns = int(manifest["origin_utc_ns"])
    nodes = _validate_nodes(source.nodes)
    selection_nodes = _visibility_nodes(source.times, nodes)
    center = np.asarray(parent["fit"]["parameters"][:2], dtype=float)
    offsets, patch_coordinates, observers = _patch_observers(center)
    archive = TleArchiveReader(TLE_ROOT)
    tle = helper._snapshot(archive, product, origin_utc_ns)
    raw_payload = archive.read(tle)
    payload, debris = exclude_labelled_starlink_debris(raw_payload)
    catalogue = parse_element_sets(payload)
    catalogue_numbers = np.asarray(catalogue.satellite_numbers, dtype=np.int64)
    starlink_indices = np.asarray(
        [
            index
            for index, name in enumerate(catalogue.names)
            if name.upper().strip().startswith("STARLINK")
        ],
        dtype=int,
    )
    started = time.monotonic()
    deadline = started + float(max_numerical_seconds)
    visible, screen_valid, maximum = _screen_visible(
        catalogue,
        starlink_indices,
        origin_utc_ns,
        selection_nodes,
        observers,
        propagate_candidate_states,
        deadline,
    )
    by_number = {int(number): index for index, number in enumerate(catalogue_numbers)}
    old_indices = [by_number[int(number)] for number in np.asarray(raw.numbers, dtype=int)]
    requested = list(dict.fromkeys([*old_indices, *sorted(visible)]))
    states = _propagate_states(
        catalogue,
        requested,
        origin_utc_ns,
        nodes,
        propagate_candidate_states,
        deadline,
    )
    order = _expanded_order(raw.numbers, catalogue_numbers, visible, set(states))
    numbers = catalogue_numbers[order]
    old_lookup = {int(number): index for index, number in enumerate(numbers)}
    old_to_expanded = np.asarray([old_lookup[int(number)] for number in raw.numbers], dtype=int)
    initial = _expand_parameters(parent["fit"]["parameters"], old_to_expanded, len(numbers))
    retained = np.asarray([index in old_indices for index in order], dtype=bool)
    screen_visible = np.asarray([index in visible for index in order], dtype=bool)
    maximum_elevation = np.asarray([maximum.get(int(index), np.nan) for index in order])
    arrays = {
        "nodes": nodes,
        "numbers": numbers,
        "position": np.asarray([states[int(index)][0] for index in order]),
        "velocity": np.asarray([states[int(index)][1] for index in order]),
        "initial": initial,
        "old_numbers": np.asarray(raw.numbers, dtype=np.int64),
        "old_to_expanded": old_to_expanded,
        "maximum_elevation_sine": maximum_elevation,
        "screen_visible": screen_visible,
        "retained_original": retained,
    }
    ExpandedScanData(source, arrays, {"session_id": session})
    elapsed = time.monotonic() - started
    if elapsed > max_numerical_seconds:
        raise TimeoutError("all-visible export exceeded its numerical deadline")
    full_failures = sorted(
        int(catalogue_numbers[index]) for index in visible if index not in states
    )
    propagation_failures = sorted(
        int(catalogue_numbers[index]) for index in starlink_indices if index not in screen_valid
    )
    debris_rows = [
        {"catalog_number": int(row.catalog_number), "name": row.name} for row in debris
    ]
    receipt = {
        "schema": "ds13-all-visible-bank/v1",
        "session_id": session,
        "status": "complete",
        "source_hashes": source_hashes,
        "reference_read": False,
        "observation_policy": (
            "Existing alias-family rows, values, groups, RF, and times unchanged."
        ),
        "observation_array_hashes": {
            name: _array_digest(getattr(source, name)) for name in OBSERVATION_NAMES
        },
        "tle": {
            "provider": product["original_tle_snapshot"]["provider"],
            "collected_utc_ns": int(tle.collected_utc_ns),
            "digest": tle.digest,
            "raw_payload_sha256": _sha256_bytes(raw_payload.encode()),
            "debris_filtered_payload_sha256": _sha256_bytes(payload.encode()),
        },
        "eligibility": {
            "policy": (
                "STARLINK-named archived TLE records excluding names ending ' DEB'; candidate "
                "must propagate at the visibility screen, and exported candidates must propagate "
                "over the complete original ephemeris grid. No RF response or reference is used."
            ),
            "catalogue_record_count_after_debris_filter": len(catalogue_numbers),
            "starlink_record_count": len(starlink_indices),
            "labelled_starlink_debris_excluded": debris_rows,
            "visibility_screen_propagation_failure_count": len(propagation_failures),
            "visibility_screen_propagation_failure_numbers": propagation_failures,
            "visible_full_grid_failure_count": len(full_failures),
            "visible_full_grid_failure_numbers": full_failures,
        },
        "visibility": {
            "horizon_degrees": 0.0,
            "timing_window_s": [-TIMING_WINDOW_S, TIMING_WINDOW_S],
            "screen_node_spacing_s": NODE_SPACING_S,
            "screen_node_count": len(selection_nodes),
            "screen_time_range_s": [float(selection_nodes[0]), float(selection_nodes[-1])],
            "patch_center_source": "sealed medium fit; objective-selected without reference",
            "patch_center_east_north_km": center.tolist(),
            "patch_half_width_km": PATCH_HALF_WIDTH_KM,
            "patch_offsets_east_north_km": offsets.tolist(),
            "patch_coordinates_lat_lon_deg": patch_coordinates.tolist(),
            "visible_count_before_full_grid_check": len(visible),
        },
        "inventory": {
            "original_candidate_count": len(raw.numbers),
            "expanded_candidate_count": len(numbers),
            "added_visible_candidate_count": int(np.sum(~retained)),
            "original_candidates_outside_screen_retained": int(np.sum(retained & ~screen_visible)),
            "original_number_map": [
                {
                    "old_index": old_index,
                    "catalog_number": int(number),
                    "expanded_index": int(old_to_expanded[old_index]),
                }
                for old_index, number in enumerate(raw.numbers)
            ],
            "ordering": (
                "Original 64 in original order, then visible additions by catalogue number."
            ),
        },
        "ephemeris": {
            "origin_utc_ns": origin_utc_ns,
            "node_count": len(nodes),
            "node_spacing_s": NODE_SPACING_S,
            "node_range_s": [float(nodes[0]), float(nodes[-1])],
            "propagation": (
                "Same archived TLE and propagate_candidate_states path as original export."
            ),
        },
        "initialization": {
            "source": "sealed medium fit",
            "old_candidate_parameters_remapped": True,
            "added_candidate_timing_s": 0.0,
        },
        "resources": {
            "worker_allocation": 1,
            "numeric_threads": 1,
            "maximum_numerical_seconds": max_numerical_seconds,
            "actual_numerical_seconds": elapsed,
            "resource_amendment": "position-profile-resource-amendment.json",
        },
        "expanded_array_hashes": {name: _array_digest(arrays[name]) for name in ARRAY_NAMES},
        "artifacts": {},
    }
    _assert_snapshot_unchanged(source_hashes)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT_ROOT / session
    if destination.exists():
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(prefix=f".{session}-", dir=OUTPUT_ROOT) as temporary:
        staging = Path(temporary)
        archive_path = staging / "expanded.npz"
        np.savez_compressed(archive_path, **arrays)
        receipt["artifacts"]["expanded_npz_sha256"] = _sha256_file(archive_path)
        (staging / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        os.rename(staging, destination)
    return {
        "session_id": session,
        "candidate_count": len(numbers),
        "added_candidate_count": int(np.sum(~retained)),
        "elapsed_s": elapsed,
        "output": str(destination),
        "receipt_sha256": _sha256_file(destination / "receipt.json"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", choices=SESSIONS)
    parser.add_argument("--max-numerical-seconds", type=float, default=MAX_NUMERICAL_SECONDS)
    arguments = parser.parse_args()
    print(
        json.dumps(
            export_all_visible_bank(
                arguments.session,
                max_numerical_seconds=arguments.max_numerical_seconds,
            )
        ),
        flush=True,
    )
