#!/usr/bin/env python3
"""Bounded DS11 full-catalogue numerator audit under the frozen IID model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PLAN = ROOT / "reports/2026_09_30_ds11_single10/plan.json"
TLE_ROOT = Path("/var/lib/leo/tle")
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
RELEASE_SITE = Path(
    "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/"
    ".venv/lib/python3.14/site-packages"
)
INDICES = (0, 1)
TRACK_IDS = {
    0: (
        "sha256:02a3ad66a02dcaf4dac18161c529961d1d8a47d1ac480072f4871d1800edd380",
        "sha256:0b8ac3038340bc2aeb49ef67551de001f3fbf80468b6735ada578c766ba1cc64",
        "sha256:165eb4cabb633205e434a48555322c428627b58063dd162ec7eca939a9d3913f",
    ),
    1: (
        "sha256:003a79c8c673eac793000b59e4b223b987bd13f958d68bbc0de938b21796b453",
        "sha256:0205c9f673544e89493b22db18ee963a430f413f29abcdc79ad464e8d9e89df8",
        "sha256:03e89b8758ce13dac638ec117a9dec510dad7af5f48af205bcc7ca01672736ab",
    ),
}


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prefixed_digest(path: Path) -> str:
    return "sha256:" + digest(path)


def save_exclusive(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def interpolate_states(position, velocity, timing_grid, tau):
    """Match Stationary.prediction's clamped two-node state interpolation."""
    import numpy as np

    grid = np.asarray(timing_grid, dtype=float)
    hi = min(max(int(np.searchsorted(grid, tau, side="right")), 1), len(grid) - 1)
    lo = hi - 1
    weight = (float(tau) - grid[lo]) / (grid[hi] - grid[lo])
    pos = position[:, 0] * (1.0 - weight) + position[:, 1] * weight
    vel = velocity[:, 0] * (1.0 - weight) + velocity[:, 1] * weight
    return pos, vel, lo, hi, float(weight)


def numerator_comparison(scores, visible, retained):
    """Compare retained and full numerator mass without changing the divisor."""
    import numpy as np
    from scipy.special import logsumexp

    scores = np.asarray(scores, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    retained = np.asarray(retained, dtype=bool)
    keep = visible & retained
    omitted = visible & ~retained
    if not visible.any() or not keep.any():
        raise ValueError("full and retained visible sets must be nonempty")
    full = float(logsumexp(scores[visible]))
    kept = float(logsumexp(scores[keep]))
    omitted_log_fraction = (
        float(logsumexp(scores[omitted]) - full) if omitted.any() else None
    )
    best = int(np.argmax(np.where(visible, scores, -np.inf)))
    return {
        "full_log_numerator": full,
        "retained_log_numerator": kept,
        "retained_mass": float(np.exp(kept - full)),
        "omitted_log_fraction": omitted_log_fraction,
        "best_index": best,
        "best_retained": bool(retained[best]),
    }


def require_exact_replay(replay_hz: float, visibility_equal: bool) -> None:
    if not math.isfinite(replay_hz) or replay_hz >= 1e-6 or not visibility_equal:
        raise ValueError("retained prediction/visibility replay failed")


def validate_manifest() -> dict:
    manifest = read(HERE / "manifest.json")
    if manifest.get("schema") != "ds11-catalogue-iid-audit-manifest/v1":
        raise ValueError("unexpected manifest schema")
    for raw_path, expected in manifest["sources"].items():
        path = Path(raw_path)
        if digest(path) != expected:
            raise ValueError(f"source digest mismatch: {path}")
    if manifest["indices"] != list(INDICES):
        raise ValueError("index selection changed")
    return manifest


def validate_input(index: int, manifest: dict):
    import numpy as np

    sys.path.insert(0, str(ROOT / "tools"))
    import ds7_fast_baseline_adapter as fast

    plan = read(PLAN)
    entry = plan["inputs"][index]
    if entry["session_id"] != manifest["scans"][str(index)]["session_id"]:
        raise ValueError("session binding mismatch")
    for artifact in entry["artifacts"]:
        if prefixed_digest(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError("input artifact digest mismatch")
    docs = fast.load_documents({"config": plan["config"], "inputs": [entry]})
    if len(docs) != 1:
        raise ValueError("one document required")
    doc = docs[0]
    selected = tuple(sorted(t["track_id"] for t in doc["tracks"])[:3])
    if selected != TRACK_IDS[index]:
        raise ValueError("frozen lexicographic track selection changed")
    result_path = Path(manifest["scans"][str(index)]["iid_result_path"])
    receipt_path = Path(manifest["scans"][str(index)]["iid_receipt_path"])
    result, receipt = read(result_path), read(receipt_path)
    if (
        result.get("index") != index
        or result.get("method") != "iid"
        or result.get("session") != entry["session_id"]
        or not result.get("selected", {}).get("qualified")
        or receipt.get("index") != index
        or receipt.get("method") != "iid"
        or receipt.get("exit_code") != 0
    ):
        raise ValueError("IID endpoint binding or qualification failed")
    endpoint = np.asarray(result["selected"]["x"], dtype=float)
    if endpoint.shape != (3,) or not np.isfinite(endpoint).all():
        raise ValueError("invalid IID endpoint")
    return plan, entry, doc, endpoint, fast


def reconstruct_catalogue(meta: dict):
    import numpy as np
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records, parse_element_sets

    archive = TleArchiveReader(TLE_ROOT)
    refs = archive.list_snapshots()
    by_digest = {ref.digest: ref for ref in refs}
    used = []

    def payload(key):
        if key not in by_digest:
            raise ValueError(f"bound snapshot unavailable: {key}")
        raw = archive.read(by_digest[key])
        if "sha256:" + hashlib.sha256(raw.encode()).hexdigest() != key:
            raise ValueError("snapshot payload digest mismatch")
        used.append(key)
        return exclude_labelled_starlink_debris(raw)[0]

    base_records = list(parse_element_set_records(payload(meta["baseline_snapshot_sha256"])))
    choices = {}
    for source in meta["provider_sources"]:
        raw = payload(source["snapshot_sha256"])
        records = parse_element_set_records(raw)
        epochs = parse_element_sets(raw).element_epoch_utc_ns()
        for record, epoch in zip(records, epochs, strict=True):
            key = (int(epoch), source["collected_utc_ns"], source["snapshot_sha256"])
            old = choices.get(record.satellite_number)
            if old is None or key > old[0]:
                choices[record.satellite_number] = (key, record)
    catalogue = parse_element_sets(
        "".join(choices[row.satellite_number][1].text for row in base_records)
    )
    if list(catalogue.satellite_numbers) != [row.satellite_number for row in base_records]:
        raise ValueError("catalogue physical identity/order changed")
    if len(catalogue.satellite_numbers) != meta["catalogue_size"]:
        raise ValueError("catalogue size changed")
    return catalogue, sorted(set(used))


def evaluate_case(track, engine, catalogue, retained_ids, x, fast):
    import numpy as np
    from leo.analysis.adaptive_tle_prediction import (
        LIGHT_KM_S,
        REFERENCE_RF_HZ,
        propagate_candidate_states,
    )

    tau = float(x[2])
    grid = np.asarray(engine.taus, dtype=float)
    hi = min(max(int(np.searchsorted(grid, tau, side="right")), 1), len(grid) - 1)
    lo = hi - 1
    nodes = np.asarray([grid[lo], grid[hi]], dtype=float)
    positions, velocities, ids = propagate_candidate_states(
        catalogue,
        np.arange(len(catalogue.satellite_numbers)),
        engine.document["start_utc_ns"],
        np.asarray(track["times_s"], dtype=float),
        nodes,
    )
    pos, vel, _, _, weight = interpolate_states(positions, velocities, nodes, tau)
    rec, up = fast.baseline.site(*engine.coordinates(x))
    direction = pos - rec
    direction /= np.linalg.norm(direction, axis=-1)[..., None]
    prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(direction * vel, axis=-1)
    visible = np.any((direction @ up)[:, track["mask"]] >= 0, axis=1)

    lookup = {int(value): slot for slot, value in enumerate(ids)}
    if any(int(value) not in lookup for value in retained_ids):
        raise ValueError("retained candidate missing from propagated catalogue")
    slots = np.asarray([lookup[int(value)] for value in retained_ids], dtype=int)
    cached, cached_visible = engine.prediction(track, x)
    replay = float(np.max(np.abs(cached - prediction[slots])))
    visibility_equal = bool(np.array_equal(cached_visible, visible[slots]))
    require_exact_replay(replay, visibility_equal)

    visible_slots = np.flatnonzero(visible)
    if not len(visible_slots):
        raise RuntimeError("no full-catalogue training-visible candidate")
    residual = track["y"][None, :] - prediction[visible_slots]
    score, _, audits, _ = fast.profile(residual, track["mask"])
    converged = all(row["converged"] for row in audits)
    if not converged:
        raise RuntimeError("full-catalogue offset stationarity failed")
    retained_mask = np.isin(ids, retained_ids)
    comparison = numerator_comparison(
        score, np.ones(len(visible_slots), dtype=bool), retained_mask[visible_slots]
    )
    best_slot = int(visible_slots[comparison.pop("best_index")])
    best_catalogue_index = int(ids[best_slot])
    return {
        **comparison,
        "best_catalogue_index": best_catalogue_index,
        "best_norad": int(catalogue.satellite_numbers[best_catalogue_index]),
        "catalogue_size": int(len(catalogue.satellite_numbers)),
        "propagated_valid": int(len(ids)),
        "visible": int(visible.sum()),
        "retained": int(len(retained_ids)),
        "retained_visible": int((retained_mask & visible).sum()),
        "timing_nodes_s": [float(nodes[0]), float(nodes[1])],
        "timing_interpolation_weight": weight,
        "prediction_replay_hz": replay,
        "visibility_replay_equal": visibility_equal,
        "profile_max_abs_gradient": float(max(abs(row["gradient"]) for row in audits)),
        "profile_root_count_min": int(min(row["roots"] for row in audits)),
        "profile_root_count_max": int(max(row["roots"] for row in audits)),
    }


def run(index: int) -> None:
    import numpy as np

    if index not in INDICES:
        raise ValueError("pilot index not allowed")
    started = time.monotonic()
    manifest = validate_manifest()
    plan, entry, doc, endpoint, fast = validate_input(index, manifest)
    candidate_meta_path = Path(
        next(a["path"] for a in entry["artifacts"] if a["path"].endswith("manifest.json"))
    )
    bank_path = Path(
        next(a["path"] for a in entry["artifacts"] if a["path"].endswith(".npz"))
    )
    meta = read(candidate_meta_path)
    catalogue, snapshots = reconstruct_catalogue(meta)
    engine = fast.Stationary(doc, plan["config"])
    track_by_id = {track["track_id"]: track for track in doc["tracks"]}
    bank_index = {row["track_id"]: row["index"] for row in meta["tracks"]}
    rows = []
    with np.load(bank_path, allow_pickle=False) as banks:
        for track_id in TRACK_IDS[index]:
            track = track_by_id[track_id]
            retained = np.asarray(banks[f"candidate_ids_{bank_index[track_id]}"], dtype=int)
            for label, x in (("center", np.zeros(3)), ("iid_endpoint", endpoint)):
                case_started = time.monotonic()
                result = evaluate_case(track, engine, catalogue, retained, x, fast)
                row = {
                    "schema": "ds11-catalogue-iid-audit-case/v1",
                    "index": index,
                    "session_id": entry["session_id"],
                    "track_id": track_id,
                    "setting": label,
                    "x": [float(v) for v in x],
                    "training_observations": int(np.asarray(track["mask"]).sum()),
                    "held_observations_not_scored": int((~np.asarray(track["mask"])).sum()),
                    **result,
                    "elapsed_seconds": time.monotonic() - case_started,
                    "manifest_sha256": digest(HERE / "manifest.json"),
                    "reference_used": False,
                    "held_values_scored": False,
                }
                ordinal = TRACK_IDS[index].index(track_id)
                path = HERE / "runs" / f"{index:02d}" / "cases" / f"{ordinal}-{label}.json"
                save_exclusive(path, row)
                rows.append(row)
                print(index, ordinal, label, result["retained_mass"], flush=True)
    save_exclusive(
        HERE / "runs" / f"{index:02d}" / "result.json",
        {
            "schema": "ds11-catalogue-iid-audit-result/v1",
            "index": index,
            "session_id": entry["session_id"],
            "cases": len(rows),
            "track_ids": list(TRACK_IDS[index]),
            "provider_snapshot_sha256": snapshots,
            "minimum_retained_mass": min(row["retained_mass"] for row in rows),
            "omitted_leading_candidates": sum(not row["best_retained"] for row in rows),
            "elapsed_seconds": time.monotonic() - started,
            "manifest_sha256": digest(HERE / "manifest.json"),
            "reference_used": False,
            "held_values_scored": False,
        },
    )


def batch() -> None:
    for index in INDICES:
        started = time.monotonic()
        command = [
            "sudo",
            "-n",
            "env",
            "OPENBLAS_NUM_THREADS=1",
            "OMP_NUM_THREADS=1",
            "MKL_NUM_THREADS=1",
            "nice",
            "-n",
            "19",
            PYTHON,
            str(HERE / "audit.py"),
            "run",
            str(index),
        ]
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=90)
            receipt = {
                "index": index,
                "exit_code": process.returncode,
                "timed_out": False,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "wall_seconds": time.monotonic() - started,
                "manifest_sha256": digest(HERE / "manifest.json"),
            }
        except subprocess.TimeoutExpired as error:
            receipt = {
                "index": index,
                "exit_code": None,
                "timed_out": True,
                "stdout": (error.stdout or b"").decode() if isinstance(error.stdout, bytes) else error.stdout,
                "stderr": (error.stderr or b"").decode() if isinstance(error.stderr, bytes) else error.stderr,
                "wall_seconds": time.monotonic() - started,
                "manifest_sha256": digest(HERE / "manifest.json"),
            }
        save_exclusive(HERE / "runs" / f"{index:02d}" / "receipt.json", receipt)
        print(json.dumps(receipt), flush=True)


def prepare() -> None:
    plan = read(PLAN)
    scans = {}
    sources = {}

    def bind(path: Path) -> None:
        sources[str(path.resolve())] = digest(path)

    for path in (
        HERE / "audit.py",
        HERE / "PROTOCOL.md",
        HERE / "test_audit.py",
        PLAN,
        ROOT / "tools/ds7_baseline_adapter.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        RELEASE_SITE / "leo/operations/tle_archive.py",
        RELEASE_SITE / "leo/analysis/adaptive_tle_prediction.py",
        RELEASE_SITE / "leo/sky/propagation.py",
    ):
        bind(path)
    masses = []
    for index, entry in enumerate(plan["inputs"]):
        shortlist_path = Path(
            next(a["path"] for a in entry["artifacts"] if a["path"].endswith("manifest.json"))
        ).with_name("shortlists.json")
        masses.append((read(shortlist_path)["minimum_anchor_top8_mass"], index))
    if min(masses) != (0.9233187825367867, 1):
        raise ValueError("training-only worst exporter proxy changed")
    for index in INDICES:
        entry = plan["inputs"][index]
        for artifact in entry["artifacts"]:
            path = Path(artifact["path"])
            if prefixed_digest(path) != artifact["sha256"]:
                raise ValueError("input artifact digest mismatch during prepare")
            bind(path)
        shortlist_path = Path(
            next(a["path"] for a in entry["artifacts"] if a["path"].endswith("manifest.json"))
        ).with_name("shortlists.json")
        bind(shortlist_path)
        result_path = ROOT / f"reports/2026_09_30_ds11_single10/runs/{index:02d}_iid.json"
        receipt_path = ROOT / f"reports/2026_09_30_ds11_single10/runs/{index:02d}_iid.receipt.json"
        bind(result_path)
        bind(receipt_path)
        scans[str(index)] = {
            "session_id": entry["session_id"],
            "track_ids": list(TRACK_IDS[index]),
            "iid_result_path": str(result_path.resolve()),
            "iid_receipt_path": str(receipt_path.resolve()),
            "minimum_anchor_top8_mass": read(shortlist_path)["minimum_anchor_top8_mass"],
        }
    save_exclusive(
        HERE / "manifest.json",
        {
            "schema": "ds11-catalogue-iid-audit-manifest/v1",
            "indices": list(INDICES),
            "settings_per_track": ["center", "iid_endpoint"],
            "scans": scans,
            "sources": dict(sorted(sources.items())),
            "reference_used": False,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "batch"))
    parser.add_argument("index", nargs="?", type=int)
    args = parser.parse_args()
    if args.command == "prepare":
        if args.index is not None:
            raise ValueError("prepare takes no index")
        prepare()
    elif args.command == "run":
        if args.index is None:
            raise ValueError("run requires index")
        run(args.index)
    else:
        if args.index is not None:
            raise ValueError("batch takes no index")
        batch()


if __name__ == "__main__":
    main()
