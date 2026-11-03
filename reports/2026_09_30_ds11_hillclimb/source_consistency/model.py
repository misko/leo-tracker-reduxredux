"""Training-source-disjoint subset with the unchanged independent-t4 model."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402


VARIANTS = ("training_source_consistent",)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select(track_rows):
    """Exact frozen seeded-greedy maximum-training-coverage selector."""
    by_id = {row["track_id"]: row for row in track_rows}
    if len(by_id) != len(track_rows):
        raise ValueError("duplicate track ID in source selector")
    for row in track_rows:
        if len(row["groups"]) != len(set(row["groups"])):
            raise ValueError("one track reuses a training source group")
    ranked = sorted(by_id, key=lambda key: (-by_id[key]["training_count"], key))
    alternatives = {}
    for seed in (None, *ranked):
        used = set()
        chosen = []
        if seed is not None:
            chosen.append(seed)
            used.update(by_id[seed]["groups"])
        for key in ranked:
            if key == seed:
                continue
            groups = set(by_id[key]["groups"])
            if used.isdisjoint(groups):
                chosen.append(key)
                used.update(groups)
        ids = tuple(sorted(chosen))
        alternatives[ids] = sum(by_id[key]["training_count"] for key in ids)
    best = min(alternatives, key=lambda ids: (-alternatives[ids], ids))
    return {
        "track_ids": best,
        "training_count": alternatives[best],
        "alternative_closures": len(alternatives),
    }


def selection_from_sidecar(document, scan):
    tracks = scan["tracks"]
    if set(tracks) != {track["track_id"] for track in document["tracks"]}:
        raise ValueError("source sidecar track coverage mismatch")
    rows = []
    for track in document["tracks"]:
        points = tracks[track["track_id"]]
        if len(points) != len(track["y"]):
            raise ValueError("source sidecar observation coverage mismatch")
        training = [bool(point["training"]) for point in points]
        if training != track["mask"].tolist():
            raise ValueError("source sidecar partition mismatch")
        groups = [
            point["source_group_id"] for point in points if point["training"]
        ]
        rows.append({
            "track_id": track["track_id"],
            "groups": groups,
            "training_count": int(track["mask"].sum()),
        })
    chosen = select(rows)
    ids = set(chosen["track_ids"])
    used = [group for row in rows if row["track_id"] in ids for group in row["groups"]]
    if len(used) != len(set(used)):
        raise ValueError("selected tracks are not training-source-disjoint")
    return chosen, rows


class SourceConsistentIID:
    """Original IID Student-t4 mixture evaluated on a fixed track subset."""

    def __init__(self, documents, config, *, model_factory=None):
        factory = model_factory or fast.baseline.Stationary
        self.documents = documents
        self.models = [factory(document, config) for document in documents]

    def evaluate(self, x, gradient=True):
        x = np.asarray(x, dtype=float)
        total = 0.0
        derivative = np.zeros_like(x)
        for document_index, engine in enumerate(self.models):
            local = x[[0, 1, document_index + 2]]
            score, local_gradient = engine.evaluate(local, gradient)
            total += float(score)
            if gradient:
                derivative[:2] += local_gradient[:2]
                derivative[document_index + 2] += local_gradient[2]
        return {"score": total, "gradient": derivative}


def _qualified_incumbent(index, session_id):
    result_path = BASE / "runs" / f"{index:02d}_iid.json"
    receipt_path = BASE / "runs" / f"{index:02d}_iid.receipt.json"
    if not result_path.exists() or not receipt_path.exists():
        raise ValueError("original IID result or receipt missing")
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get("exit_code") != 0 or receipt.get("index") != index
            or receipt.get("method") != "iid"):
        raise ValueError("original IID receipt is not a successful matching attempt")
    record = json.loads(result_path.read_text())
    if (record.get("index") != index or record.get("session") != session_id
            or record.get("method") != "iid"):
        raise ValueError("original IID result identity mismatch")
    bounds = ((-12.0, 12.0), (-12.0, 12.0), (-5.0, 5.0))
    valid = []
    for start in record.get("starts", []):
        values = start.get("x", [])
        finite = (len(values) == 3 and all(math.isfinite(float(value)) for value in values)
                  and math.isfinite(float(start.get("score", math.nan)))
                  and math.isfinite(float(start.get("gradient", math.nan)))
                  and math.isfinite(float(start.get("audit", math.nan))))
        boundary = finite and any(
            min(float(value) - low, high - float(value)) < 0.001
            for value, (low, high) in zip(values, bounds, strict=True)
        )
        qualified = bool(finite and start.get("success") and not boundary
                         and float(start["gradient"]) <= 0.01
                         and float(start["audit"]) <= 0.02)
        if bool(start.get("qualified")) != qualified:
            raise ValueError("original IID qualification is inconsistent")
        if qualified:
            valid.append(start)
    selected = record.get("selected")
    if not valid or selected is None:
        raise ValueError("original same-scan IID fit is unqualified")
    winner = max(valid, key=lambda row: float(row["score"]))
    if selected.get("x") != winner.get("x") or selected.get("score") != winner.get("score"):
        raise ValueError("original IID selected endpoint is not highest qualified start")
    return result_path, receipt_path


def _resources(index, documents):
    if index is None:
        raise ValueError("source consistency requires the immutable single-scan index")
    plan_path = BASE / "plan.json"
    sidecar_path = HERE / "source_groups.json"
    plan = json.loads(plan_path.read_text())
    sidecar = json.loads(sidecar_path.read_text())
    if sidecar.get("schema") != "ds11-source-group-sidecar/v1":
        raise ValueError("source sidecar schema mismatch")
    if sidecar.get("plan_sha256") != digest(plan_path):
        raise ValueError("source sidecar plan binding mismatch")
    entry = plan["inputs"][index]
    scan = sidecar["scans"].get(str(index))
    if scan is None:
        raise ValueError("source sidecar does not cover requested index")
    if len(documents) != 1 or not (
        documents[0]["session_id"] == entry["session_id"] == scan["session_id"]
    ):
        raise ValueError("source sidecar session or index binding mismatch")
    observation = next(
        Path(row["path"]) for row in entry["artifacts"] if row["kind"] == "observations"
    )
    if scan["observation_sha256"] != digest(observation):
        raise ValueError("source sidecar observation binding mismatch")
    incumbent_path, receipt_path = _qualified_incumbent(index, entry["session_id"])
    return scan, {
        "plan": plan_path,
        "source_sidecar": sidecar_path,
        "observation": observation,
        "incumbent": incumbent_path,
        "incumbent_receipt": receipt_path,
    }


def build_model(documents, config, variant, index=None):
    if variant not in VARIANTS:
        raise ValueError(f"unknown source-consistency variant: {variant}")
    scan, resources = _resources(index, documents)
    chosen, rows = selection_from_sidecar(documents[0], scan)
    ids = set(chosen["track_ids"])
    selected_document = dict(
        documents[0], tracks=[
            track for track in documents[0]["tracks"] if track["track_id"] in ids
        ]
    )
    model = SourceConsistentIID([selected_document], config)
    original_training = sum(row["training_count"] for row in rows)
    original_observations = sum(len(track["y"]) for track in documents[0]["tracks"])
    selected_observations = sum(len(track["y"]) for track in selected_document["tracks"])
    model.metadata = {
        "objective": "original independent Student-t4 track mixture on frozen subset",
        "normalized_posterior": False,
        "variant": variant,
        "selection": "seeded greedy maximum training coverage",
        "selection_inputs": "training source-group identities and training counts only",
        "candidate_mixture": "unchanged full retained-track candidate mixtures",
        "original_tracks": len(rows),
        "retained_tracks": len(ids),
        "discarded_tracks": len(rows) - len(ids),
        "original_training_observations": original_training,
        "retained_training_observations": chosen["training_count"],
        "retained_training_fraction": chosen["training_count"] / original_training,
        "original_observations": original_observations,
        "retained_observations": selected_observations,
        "alternative_closures": chosen["alternative_closures"],
        "resource_sha256": {name: digest(path) for name, path in resources.items()},
    }
    return model
