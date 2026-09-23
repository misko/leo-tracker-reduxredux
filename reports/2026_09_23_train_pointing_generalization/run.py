#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[2]
HERE = Path(__file__).parent
CONE = ROOT / "reports/2026_09_23_train_pointing_cone/run.py"
SEED = 20260923
FRACTIONS = (0.5, 0.8, 0.95)


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fold_map(candidate_ids):
    unique = np.asarray(sorted(set(candidate_ids)))
    rng = np.random.default_rng(SEED)
    shuffled = unique[rng.permutation(len(unique))]
    return {value: index % 5 for index, value in enumerate(shuffled)}


def angle_matrix(cone, midpoint, receiver_ids, mapping):
    orientations = cone.orientation_grid(15)
    mounts = cone.axes_batched(orientations)[:, list(mapping)]
    selected = mounts[:, receiver_ids, :]
    cosine = np.einsum("ntc,tc->nt", selected, midpoint, optimize=True)
    angles = np.degrees(np.arccos(np.clip(cosine, -1, 1))).astype(np.float32)
    return orientations, angles


def evaluate(cone, orientations, angles, weights, train, held):
    best = [None] * len(FRACTIONS)
    for start in range(0, len(orientations), 1024):
        values = cone.weighted_quantiles_batched(
            angles[start : start + 1024, train], weights[train], FRACTIONS
        )
        for column in range(len(FRACTIONS)):
            local = int(np.argmin(values[:, column]))
            candidate = (float(values[local, column]), start + local)
            if best[column] is None or candidate[0] < best[column][0]:
                best[column] = candidate
    output = {}
    for column, fraction in enumerate(FRACTIONS):
        held_angles = angles[best[column][1], held]
        output[str(fraction)] = {
            "fit_deg": best[column][0],
            "held_deg": cone.weighted_quantile(held_angles, weights[held], fraction),
            "orientation": [int(x) for x in orientations[best[column][1]]],
        }
    return output


def shuffled_labels(labels, strata, permutation):
    rng = np.random.default_rng(SEED + 1000 + permutation)
    result = labels.copy()
    unchanged_strata = 0
    for key in sorted(set(strata)):
        indices = np.flatnonzero(strata == key)
        if len(indices) < 2 or len(set(labels[indices])) < 2:
            unchanged_strata += 1
            continue
        result[indices] = labels[indices][rng.permutation(len(indices))]
    return result, unchanged_strata, int(np.sum(result != labels))


def main(control_count=20):
    started = time.monotonic()
    cone = load(CONE, "pointing_cone_source")
    captured = []

    def capture(midpoint, endpoints, receiver_ids, weights, mapping, fractions, **kwargs):
        if tuple(mapping) == (0, 1):
            captured.append((midpoint.copy(), receiver_ids.copy(), weights.copy()))
        dummy = {
            str(f): {
                "midpoint_cone_deg": 0.0,
                "endpoint_cone_deg": 0.0,
                "tilt_deg": 0,
                "tilt_azimuth_deg": 0,
                "yaw_deg": 0,
            }
            for f in fractions
        }
        return {str(bound): dummy for bound in (0, 15, 30)}

    cone.profile = capture
    cone.HERE = HERE
    cone.main()
    temporary_prepared = HERE / "results.json"
    prepared_path = HERE / "prepared_inputs.json"
    temporary_prepared.replace(prepared_path)
    (HERE / "results.sha256").unlink()
    prepared = json.loads(prepared_path.read_text())
    metadata = json.loads(Path("/tmp/leo-train-rx-metadata.json").read_text())["sessions"]
    lanes = {
        (
            session["session_id"],
            track["track_id"],
        ): f"{track['channel']}/{track['edge']}/{track['actual_rf_hz']}/{track['sample_rate_hz']}"
        for session in metadata
        for track in session["tracks"]
    }
    all_candidates = [x["candidate_id"] for row in prepared["results"] for x in row["identities"]]
    folds = fold_map(all_candidates)
    rows, failures = [], []
    for index, base in enumerate(prepared["results"]):
        midpoint, actual_labels, weights = captured[index]
        identities = base["identities"]
        fold_ids = np.asarray([folds[x["candidate_id"]] for x in identities])
        strata = np.asarray(
            [f"{x['session_id']}|{lanes[(x['session_id'], x['track_id'])]}" for x in identities]
        )
        label_sets = [("actual", -1, actual_labels, 0, 0)]
        for permutation in range(control_count):
            labels, unchanged, moved = shuffled_labels(actual_labels, strata, permutation)
            label_sets.append(("shuffle", permutation, labels, unchanged, moved))
        for kind, permutation, labels, unchanged, moved in label_sets:
            for mapping in ((0, 1), (1, 0)):
                orientations, angles = angle_matrix(cone, midpoint, labels, mapping)
                for fold in range(5):
                    held, train = fold_ids == fold, fold_ids != fold
                    if not np.any(held) or not np.any(train):
                        failures.append({"location": index, "fold": fold, "reason": "empty fold"})
                        continue
                    quantiles = evaluate(cone, orientations, angles, weights, train, held)
                    rows.append(
                        {
                            "group": base["group"],
                            "role": base["location"]["role"],
                            "mapping": list(mapping),
                            "kind": kind,
                            "permutation": permutation,
                            "fold": fold,
                            "held_candidate_count": len(
                                set(identities[i]["candidate_id"] for i in np.flatnonzero(held))
                            ),
                            "held_track_count": int(np.sum(held)),
                            "held_duration_s": float(np.sum(weights[held])),
                            "unchanged_strata": unchanged,
                            "moved_labels": moved,
                            "quantiles": quantiles,
                        }
                    )
    output = {
        "schema": "train-pointing-generalization/v1",
        "seed": SEED,
        "control_count": control_count,
        "truth_used": False,
        "held_external_used": False,
        "elapsed_s": time.monotonic() - started,
        "rows": rows,
        "failures": failures,
        "bindings": {
            "protocol": digest(HERE / "PROTOCOL.md"),
            "source": digest(Path(__file__)),
            "locations": digest(HERE / "locations.json"),
            "cone_source": digest(CONE),
            "prepared_inputs": digest(prepared_path),
        },
    }
    path = HERE / "results.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    (HERE / "results.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")


if __name__ == "__main__":
    main()
