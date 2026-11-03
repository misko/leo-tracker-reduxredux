"""Export two metadata-selected DS13 singles and a common track-derived seed."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from rough_smoke import load_module, serializable

ROOT = Path(__file__).resolve().parent
POPULATION = ROOT.parent / "2026_10_02_ds13_from_911c4e5d/local/manifest.json"
LEGACY = ROOT.parent / "2026_10_02_localization_benchmark"
MULTI = ROOT.parent / "2026_10_02_multiscan_localization"


def select_scans(manifest):
    if manifest.get("dataset_id") != "DS13":
        raise ValueError("expected DS13 population")
    captures = manifest["captures"]
    if len(captures) < 2 or len({row["session_id"] for row in captures}) != len(captures):
        raise ValueError("DS13 must contain distinct admitted captures")
    ordered = sorted(captures, key=lambda row: (row["capture_start_utc_ns"], row["session_id"]))
    return [ordered[0], ordered[-1]]


def export_scan(session):
    from alias_family import group_alias_families
    from edge_alias_diagnostic import _metadata
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    helper = load_module("ds13_export_helpers", LEGACY / "export_ds11.py")
    selected = select_scans(json.loads(POPULATION.read_text()))
    matches = [row for row in selected if row["session_id"] == session]
    if len(matches) != 1:
        raise ValueError("scan is outside frozen first/last selection")
    capture = matches[0]
    evidence_path = POPULATION.parent / "analysis" / f"{session}.json"
    paths = [POPULATION, evidence_path, Path(__file__), ROOT / "protocol.json",
             LEGACY / "export_ds11.py", MULTI / "edge_alias_diagnostic.py",
             MULTI / "alias_family.py", MULTI / "candidate_prevalence_diagnostic.py"]
    snapshot = snapshot_files(paths)
    product = json.loads(evidence_path.read_text())["tracking"]["product"]
    if product["input_manifest_sha256"] != capture["manifest_sha256"]:
        raise ValueError("frozen tracking does not bind admitted capture")
    source, projected, rows, join, sample_rate = _metadata(
        Path("/srv/bulk/leo"), session, capture["manifest_sha256"],
        product["analysis_manifest_sha256"],
    )
    if len(projected) != product["projected_candidate_count"]:
        raise ValueError("projected candidate inventory changed")
    if any(row is None for row in rows):
        raise ValueError("incomplete raw GLRT metadata join")
    config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(projected, config=config)
    reconstructed = [{"tracklet_id": track.tracklet_id, "observation_count": len(track.points)}
                     for track in trajectory.tracklets]
    tracks, mapping = helper.track_rows(projected, trajectory, reconstructed)
    mapping["scope"] = "New frozen-config reconstruction; not a replay of production track membership"
    mapping["configuration_digest"] = str(config.digest)
    origin = source.timing.first_sample_estimate_utc_ns
    arrays, raw_receipt = helper.raw_arrays(projected, origin)
    nodes = np.arange(-60.0, max(361.0, np.max(arrays["times"]) + 61.0), 0.25)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    tle = helper._snapshot(archive, product, origin)
    payload, _ = exclude_labelled_starlink_debris(archive.read(tle))
    catalogue = parse_element_sets(payload)
    numbers, position, velocity, candidates = helper.candidate_states(
        catalogue, product["track_reviews"], origin, nodes,
    )
    arrays.update(nodes=nodes, position=position, velocity=velocity,
                  numbers=numbers, initial=np.zeros(6 + len(numbers)))
    for row, point in zip(rows, projected, strict=True):
        row["candidate_id"] = point.candidate_id
    grouping = group_alias_families(rows, frame_period_samples=sample_rate / 750.0)
    indices = {point.candidate_id: index for index, point in enumerate(projected)}
    representatives = [indices[row["candidate_id"]] for row in grouping["representative_rows"]]
    assert_snapshot_unchanged(snapshot)
    manifest = {
        "schema": "coherent-localization-bundle/v1", "dataset": "DS13",
        "session_id": session, "origin_utc_ns": origin,
        "tracks": tracks, "track_mapping": mapping, "raw_observations": raw_receipt,
        "candidate_bank": candidates, "family_representatives": representatives,
        "alias_grouping": grouping, "metadata_join": join,
        "provenance": {"scope": "Known-site-reviewed candidate pool; not blind validation",
                       "input_manifest_sha256": source.input_manifest_sha256,
                       "analysis_manifest_sha256": source.analysis_manifest_sha256,
                       "source_hashes": snapshot},
        "artifacts": {},
    }
    evaluation = {"reference_site": product["observer_site"], "session_id": session,
                  "scope": "Evaluation-only reference; do not read during fitting"}
    helper._write_bundle(ROOT / "scans" / session, arrays, manifest, evaluation)
    return {"session": session, "rows": len(projected), "families": len(representatives),
            "tracks": len(tracks)}


def load_scan(session):
    from finite_set_alias_family import FamilyGeometryData

    bundle = load_module("ds13_bundle", LEGACY / "bundle.py")
    directory = ROOT / "scans" / session
    manifest = json.loads((directory / "bundle.json").read_text())
    source = bundle.Data(directory)
    source.reference_time_s = 150.0
    return source, FamilyGeometryData(source, manifest["family_representatives"])


class ShiftedData:
    def __init__(self, source, shift):
        self.source, self.shift = source, shift

    def __getattr__(self, name):
        return getattr(self.source, name)

    def predict(self, parameters, **kwargs):
        parameters = np.asarray(parameters).copy()
        parameters[6:] += self.shift
        return self.source.predict(parameters, **kwargs)


def longest_tracks(data, per_receiver=12):
    chosen = []
    for receiver in (0, 1):
        tracks = [track for track in data.tracks if track["receiver"] == receiver
                  and len(track["rows"]) >= 15]
        tracks.sort(key=lambda track: (-np.ptp(data.times[track["rows"]]), track["track_id"]))
        chosen.extend(tracks[:per_receiver])
    if not chosen:
        raise ValueError("no sufficiently supported tracks")
    return chosen


def initialize_scan(session):
    from grouped_likelihood import DEFAULT_ALIAS_HZ
    from staged_fit import fit_receiver_lines
    from track_seed import fit_rough, loss

    output = ROOT / "scans" / session / "seed.json"
    if output.exists():
        raise FileExistsError(output)
    paths = [ROOT / "scans" / session / name for name in ("bundle.json", "bundle.npz")]
    paths += [Path(__file__), ROOT / "protocol.json", LEGACY / "bundle.py",
              ROOT.parent / "2026_10_02_coherent_localization/common.py"]
    paths += [MULTI / name for name in (
        "track_seed.py", "staged_fit.py", "grouped_likelihood.py", "finite_set_fit.py",
        "finite_set_alias_family.py", "rough_smoke.py", "prediction_jacobian.py",
        "prediction_plan.py",
    )]
    snapshot = snapshot_files(paths)
    source, _ = load_scan(session)
    data = copy.copy(source)
    data.tracks = longest_tracks(source)
    rough = fit_rough(data, budget_s=45)
    accepted = [row for row in rough["assignments"] if row["accepted"]
                and row["source_groups"] >= 15 and row["span_s"] >= 15]
    if not accepted:
        raise ValueError("no matched long tracks")
    accepted.sort(key=lambda row: (-row["span_s"], -row["source_groups"], row["track_index"]))
    satellites = list(dict.fromkeys(row["satellite_index"] for row in accepted))[:16]
    rough["assignments"] = [row for row in accepted if row["satellite_index"] in satellites]
    attempts = []
    for shift in (-10.0, -5.0, 0.0, 5.0, 10.0):
        parameters = fit_receiver_lines(ShiftedData(data, shift), rough)
        parameters[6:] = shift
        costs = []
        for track in rough["assignments"]:
            rows = np.asarray(track["rows"])
            indices = np.full(len(rows), track["satellite_index"])
            predicted, visible = data.predict(parameters, rows=rows, satellites=indices)
            residual = (data.measured[rows] - predicted + DEFAULT_ALIAS_HZ / 2) % (
                DEFAULT_ALIAS_HZ
            ) - DEFAULT_ALIAS_HZ / 2
            if np.any(visible):
                costs.append(float(np.mean(loss(residual[visible]))))
        attempts.append({"global_shift_s": shift, "parameters": parameters,
                         "score": float(np.mean(costs))})
    selected = min(attempts, key=lambda attempt: attempt["score"])
    result = {"session": session, "rough": rough, "satellites": satellites,
              "catalog_numbers": data.numbers[satellites], "initial": selected["parameters"],
              "global_shift_grid": attempts, "source_hashes": snapshot,
              "reference_read": False,
              "scope": "Top 12 tracks per RX by duration; provisional matches, max16 satellites. "
                       "Robust RX-line fits at five common timing shifts; same seed for all arms."}
    assert_snapshot_unchanged(snapshot)
    with output.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"session": session, "satellites": len(satellites),
            "rough_success": rough["success"], "global_shift_s": selected["global_shift_s"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "initialize"))
    parser.add_argument("session")
    args = parser.parse_args()
    print(json.dumps(export_scan(args.session) if args.action == "export"
                     else initialize_scan(args.session)), flush=True)
