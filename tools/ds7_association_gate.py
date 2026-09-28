#!/usr/bin/env python3
"""Reference-free structural gate for DS7 association/search inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

SCHEMA = "ds7-association-gate/v1"
REFERENCE_RF_HZ = 11_200_000_000.0
EXPECTED_SEED = 2026092711
EXPECTED_TAUS = np.arange(-5.0, 5.001, 0.25)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _partition(session_id: str, visit: int) -> bool:
    value = hashlib.sha256(f"{EXPECTED_SEED}:visit:{session_id}:{visit}".encode()).hexdigest()
    return int(value[:8], 16) % 10 < 6


def training_selection_digest(document: dict) -> str:
    """Digest only fields allowed to influence shortlist selection."""
    rows = []
    for track in document["tracks"]:
        selected = [
            [time, measured, visit]
            for time, measured, visit, keep in zip(
                track["times_s"],
                track["measured_hz"],
                track["visits"],
                track["training_mask"],
                strict=True,
            )
            if keep
        ]
        # measured_hz is already scaled to the canonical carrier upstream.
        # Physical channel RF is provenance and cannot affect shortlist selection.
        rows.append({"track_id": track["track_id"], "training": selected})
    return _canonical_digest(rows)


def audit(plan_path: Path, tracks_path: Path, bank_dir: Path) -> dict:
    failures: list[str] = []
    plan = json.loads(plan_path.read_text())
    tracks = json.loads(tracks_path.read_text())
    session = tracks.get("session_id")
    captures = {row["session_id"]: row for row in plan.get("captures", [])}
    if session not in captures:
        failures.append("track session is absent from frozen plan")
    elif captures[session]["manifest_sha256"] != tracks.get("manifest_sha256"):
        failures.append("track manifest does not match frozen plan")
    if tracks.get("schema") != "ds7-baseline-track-export/v1":
        failures.append("wrong track schema")
    if tracks.get("partition_seed") != EXPECTED_SEED:
        failures.append("unexpected partition seed")

    eligible = []
    visit_labels: dict[int, bool] = {}
    rf_values = set()
    for index, row in enumerate(tracks.get("tracks", [])):
        fields = (
            row.get("times_s", []),
            row.get("measured_hz", []),
            row.get("training_mask", []),
            row.get("visits", []),
        )
        lengths = {len(value) for value in fields}
        if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
            failures.append(f"track {index} arrays have unequal or zero lengths")
            continue
        if not all(type(value) is bool for value in row["training_mask"]):
            failures.append(f"track {index} mask is not boolean")
        if not all(math.isfinite(float(value)) for value in row["times_s"] + row["measured_hz"]):
            failures.append(f"track {index} has non-finite observations")
        if any(b <= a for a, b in zip(row["times_s"], row["times_s"][1:], strict=False)):
            failures.append(f"track {index} times are not strictly increasing")
        for visit, label in zip(row["visits"], row["training_mask"], strict=True):
            expected = _partition(session, visit)
            if label != expected:
                failures.append(f"track {index} visit {visit} violates frozen partition")
            if visit in visit_labels and visit_labels[visit] != label:
                failures.append(f"visit {visit} has inconsistent masks")
            visit_labels[visit] = label
        train = sum(row["training_mask"])
        held = len(row["training_mask"]) - train
        if train >= 2 and held >= 1:
            eligible.append(row)
        rf_values.add(float(row["rf_hz"]))

    manifest_path, shortlist_path, banks_path = (
        bank_dir / "manifest.json",
        bank_dir / "shortlists.json",
        bank_dir / "banks.npz",
    )
    for path in (manifest_path, shortlist_path, banks_path):
        if not path.is_file():
            failures.append(f"missing bank artifact: {path.name}")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    shortlists = json.loads(shortlist_path.read_text()) if shortlist_path.is_file() else {}
    if manifest:
        if manifest.get("schema") != "ds7-baseline-bank-export/v1":
            failures.append("wrong bank manifest schema")
        if manifest.get("session_id") != session or manifest.get("manifest_sha256") != tracks.get(
            "manifest_sha256"
        ):
            failures.append("bank binding mismatch")
        if manifest.get("tracks_sha256") != _sha256(tracks_path):
            failures.append("bank does not hash-bind exact tracks")
    if shortlists:
        if shortlists.get("schema") != "ds7-baseline-shortlists/v1":
            failures.append("wrong shortlist schema")
        if (
            not isinstance(shortlists.get("catalogue_size"), int)
            or shortlists.get("catalogue_size", 0) <= 0
        ):
            failures.append("invalid full-catalogue normalization size")
        mass = shortlists.get("minimum_anchor_top8_mass")
        if not isinstance(mass, (int, float)) or not math.isfinite(mass) or not 0 <= mass <= 1:
            failures.append("invalid top8 retained-mass diagnostic")
        for key in ("baseline_snapshot_sha256", "provider_sources", "catalogue_size"):
            if manifest.get(key) != shortlists.get(key):
                failures.append(f"manifest and shortlist differ on {key}")
    expected_ids = [row["track_id"] for row in eligible]
    metadata = manifest.get("tracks", [])
    if [row.get("track_id") for row in metadata] != expected_ids:
        failures.append("bank track order/membership differs from eligible tracks")
    shortlist_map = shortlists.get("shortlists", {})
    if set(shortlist_map) != set(expected_ids):
        failures.append("shortlist membership differs from eligible tracks")
    if shortlists and (
        shortlists.get("session_id") != session
        or shortlists.get("manifest_sha256") != tracks.get("manifest_sha256")
    ):
        failures.append("shortlist binding mismatch")

    candidate_counts = []
    if banks_path.is_file():
        with np.load(banks_path, allow_pickle=False) as bank:
            if "timing_grid_s" not in bank or not np.array_equal(
                bank["timing_grid_s"], EXPECTED_TAUS
            ):
                failures.append("timing grid is not exact 41-point -5..5 quarter-second grid")
            expected_keys = {"timing_grid_s"}
            for index, row in enumerate(eligible):
                names = [f"candidate_ids_{index}", f"position_km_{index}", f"velocity_km_s_{index}"]
                expected_keys.update(names)
                if any(name not in bank for name in names):
                    failures.append(f"track {index} bank arrays missing")
                    continue
                ids, pos, vel = (bank[name] for name in names)
                candidate_counts.append(int(len(ids)))
                if len(ids) > 5 * len(EXPECTED_TAUS) * 8:
                    failures.append(f"track {index} exceeds declared shortlist-union cap")
                if (
                    ids.ndim != 1
                    or len(ids) == 0
                    or not np.array_equal(ids, np.unique(ids))
                    or np.any(ids <= 0)
                ):
                    failures.append(
                        f"track {index} candidate IDs are not sorted unique positive values"
                    )
                if ids.tolist() != shortlist_map.get(row["track_id"]):
                    failures.append(f"track {index} shortlist and bank IDs differ")
                shape = (len(ids), len(EXPECTED_TAUS), len(row["times_s"]), 3)
                if pos.shape != shape or vel.shape != shape:
                    failures.append(f"track {index} state-bank shape mismatch")
                if not np.isfinite(pos).all() or not np.isfinite(vel).all():
                    failures.append(f"track {index} state bank is non-finite")
                if index < len(metadata) and (
                    metadata[index].get("candidate_count") != len(ids)
                    or metadata[index].get("observation_count") != len(row["times_s"])
                ):
                    failures.append(f"track {index} metadata counts differ")
            if set(bank.files) != expected_keys:
                failures.append("bank contains undeclared arrays")

    checks = {
        "training_selection_digest": training_selection_digest(tracks),
        "eligible_track_count": len(eligible),
        "excluded_track_count": len(tracks.get("tracks", [])) - len(eligible),
        "candidate_count_min": min(candidate_counts) if candidate_counts else None,
        "candidate_count_max": max(candidate_counts) if candidate_counts else None,
        "catalogue_size": shortlists.get("catalogue_size"),
        "minimum_anchor_top8_mass": shortlists.get("minimum_anchor_top8_mass"),
        "rf_hz_values": sorted(rf_values),
        "doppler_normalization": {
            "policy": "measurement and prediction use the same canonical carrier",
            "canonical_rf_hz": REFERENCE_RF_HZ,
            "measurement_source": "normalized_dealiased_cfo_hz",
            "track_rf_hz_role": "physical channel provenance only",
            "per_track_prediction_rf_permitted": False,
            "source_audit_revision": "75b76f66974c78588c6599822e8007aaa767466b",
        },
        "selection_policy": (
            "five geographic anchors; training-only top8 at each of 41 tau values; per-track union"
        ),
        "normalization_policy": (
            "per-track logsumexp(candidate scores) minus log(full causal catalogue size)"
        ),
    }
    return {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "plan_sha256": _sha256(plan_path),
        "tracks_sha256": _sha256(tracks_path),
        "bank_artifact_sha256": {
            p.name: _sha256(p) for p in (manifest_path, shortlist_path, banks_path) if p.is_file()
        },
        "session_id": session,
        "checks": checks,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--tracks", type=Path, required=True)
    parser.add_argument("--bank-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.plan, args.tracks, args.bank_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    raise SystemExit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
