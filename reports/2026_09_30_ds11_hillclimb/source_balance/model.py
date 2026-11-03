"""Training-frozen repeated-source composite likelihood for DS11 single scans."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.special import logsumexp


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402


VARIANTS = ("group_sqrt", "group_equal", "source_receiver_equal")
CONFIDENCE_THRESHOLD = 0.90


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_assignments(documents, config, original_x, candidate_norad, *, model_factory=None):
    """Select grouping identities from training data at the original IID endpoint."""
    factory = model_factory or fast.baseline.Stationary
    engines = [factory(document, config) for document in documents]
    assignments = []
    for document_index, (document, engine) in enumerate(zip(documents, engines, strict=True)):
        local = np.asarray(original_x)[[0, 1, document_index + 2]]
        for track_index, track in enumerate(document["tracks"]):
            prediction, visible = engine.prediction(track, local)
            score, _, audits, _ = fast.profile(
                track["y"][None, :] - prediction, track["mask"]
            )
            if not all(audit["converged"] for audit in audits):
                raise RuntimeError("offset stationarity check failed while freezing groups")
            score = np.where(visible, score, -np.inf)
            normal = logsumexp(score)
            if not np.isfinite(normal):
                raise ValueError("no visible candidate while freezing source group")
            probabilities = np.exp(score - normal)
            slot = int(np.argmax(probabilities))
            confidence = float(probabilities[slot])
            norads = candidate_norad[document_index][track["track_id"]]
            if len(norads) != len(score):
                raise ValueError("physical identity mapping differs from candidate bank")
            if confidence >= CONFIDENCE_THRESHOLD:
                norad = int(norads[slot])
                source = ("source", document_index, norad, float(track["rf_hz"]))
                group = source + (int(track["receiver_id"]),)
                unambiguous = True
            else:
                norad = None
                source = ("ambiguous", document_index, track_index)
                group = source
                unambiguous = False
            assignments.append({
                "document_index": document_index,
                "track_index": track_index,
                "track_id": track["track_id"],
                "receiver_id": int(track["receiver_id"]),
                "rf_hz": float(track["rf_hz"]),
                "norad": norad,
                "confidence": confidence,
                "unambiguous": unambiguous,
                "source": source,
                "group": group,
            })
    return assignments


def derive_weights(assignments, variant):
    """Return per-track composite weights for one of the three frozen arms."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown source-balance variant: {variant}")
    group_counts = Counter(row["group"] for row in assignments)
    if variant == "group_sqrt":
        return np.asarray([group_counts[row["group"]] ** -0.5 for row in assignments])
    if variant == "group_equal":
        return np.asarray([group_counts[row["group"]] ** -1.0 for row in assignments])

    receivers = defaultdict(set)
    for row in assignments:
        receivers[row["source"]].add(row["receiver_id"])
    return np.asarray([
        1.0 / (len(receivers[row["source"]]) * group_counts[row["group"]])
        for row in assignments
    ])


class SourceBalancedIID:
    """Original IID Student-t track mixtures with frozen composite weights."""

    def __init__(self, documents, config, weights, assignments, *, model_factory=None):
        factory = model_factory or fast.baseline.Stationary
        self.documents = documents
        self.models = [factory(document, config) for document in documents]
        self.weights = np.asarray(weights, dtype=float)
        self.assignments = assignments
        if len(self.weights) != sum(len(document["tracks"]) for document in documents):
            raise ValueError("one source-balance weight per track is required")

    def evaluate(self, x, gradient=True):
        x = np.asarray(x, dtype=float)
        total = 0.0
        derivative = np.zeros_like(x)
        weight_index = 0
        for document_index, (document, engine) in enumerate(
            zip(self.documents, self.models, strict=True)
        ):
            local = x[[0, 1, document_index + 2]]
            for track in document["tracks"]:
                track_weight = self.weights[weight_index]
                weight_index += 1
                prediction, visible = engine.prediction(track, local)
                residual = track["y"][None, :] - prediction
                score, _, audits, offsets = fast.profile(residual, track["mask"])
                if not all(audit["converged"] for audit in audits):
                    raise RuntimeError("offset stationarity check failed")
                score = np.where(visible, score, -np.inf)
                normal = logsumexp(score)
                if not np.isfinite(normal):
                    raise ValueError("no visible training candidate")
                total += float(track_weight * (normal - math.log(track["catalogue_size"])))
                if not gradient:
                    continue
                centered = residual[:, track["mask"]] - offsets[:, None]
                slope = 5 * centered / (40000 + centered**2)
                responsibility = np.exp(score - normal)
                local_gradient = np.zeros(3)
                for axis in range(3):
                    step = 1e-4 if axis < 2 else 1e-5
                    plus, minus = local.copy(), local.copy()
                    plus[axis] += step
                    minus[axis] -= step
                    if axis == 2:
                        plus[axis], minus[axis] = min(5.0, plus[axis]), max(-5.0, minus[axis])
                    delta = (
                        engine.prediction(track, plus)[0] - engine.prediction(track, minus)[0]
                    ) / (plus[axis] - minus[axis])
                    local_gradient[axis] = responsibility @ np.sum(
                        slope * delta[:, track["mask"]], axis=1
                    )
                derivative[:2] += track_weight * local_gradient[:2]
                derivative[document_index + 2] += track_weight * local_gradient[2]
        return {"score": total, "gradient": derivative}


def _resources(index, documents):
    if index is None:
        raise ValueError("source-balance grouping requires the immutable single-scan index")
    sidecar_path = HERE / "catalogue_identities.json"
    sidecar = json.loads(sidecar_path.read_text())
    plan_path = BASE / "plan.json"
    if sidecar["schema"] != "ds11-source-balance-identities/v1":
        raise ValueError("identity sidecar schema mismatch")
    if sidecar["plan_sha256"] != _digest(plan_path):
        raise ValueError("identity sidecar plan binding mismatch")
    scan = sidecar["scans"][str(index)]
    if len(documents) != 1 or documents[0]["session_id"] != scan["session_id"]:
        raise ValueError("identity sidecar session binding mismatch")
    plan = json.loads(plan_path.read_text())
    entry = plan["inputs"][index]
    paths = [Path(artifact["path"]) for artifact in entry["artifacts"]]
    observation = next(path for path in paths if path.name == "observations.json")
    manifest = next(path for path in paths if path.name == "manifest.json")
    bank = next(path for path in paths if path.suffix == ".npz")
    for path, key in ((observation, "observation_sha256"),
                      (manifest, "manifest_sha256"), (bank, "bank_sha256")):
        if _digest(path) != scan[key]:
            raise ValueError(f"identity sidecar {key} binding mismatch")
    candidates = [{track_id: row["candidate_norad"] for track_id, row in scan["tracks"].items()}]
    incumbent_path = BASE / "runs" / f"{index:02d}_iid.json"
    incumbent = json.loads(incumbent_path.read_text())["selected"]
    if incumbent is None:
        raise ValueError("original same-scan IID fit is unqualified")
    return candidates, incumbent["x"], sidecar_path, incumbent_path


def build_model(documents, config, variant, index=None):
    candidate_norad, original_x, sidecar_path, incumbent_path = _resources(index, documents)
    assignments = freeze_assignments(documents, config, original_x, candidate_norad)
    weights = derive_weights(assignments, variant)
    model = SourceBalancedIID(documents, config, weights, assignments)
    group_counts = Counter(row["group"] for row in assignments)
    source_counts = Counter(row["source"] for row in assignments)
    model.metadata = {
        "objective": "composite weighted original IID Student-t4 track-mixture likelihood",
        "normalized_posterior": False,
        "variant": variant,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "freeze": "original same-scan IID training endpoint only",
        "group_key": "physical NORAD, exact RF Hz, receiver; ambiguous tracks are singletons",
        "physical_identity_mapping": "bank candidate_ids catalogue row mapped to archived roster NORAD",
        "identity_sidecar_sha256": _digest(sidecar_path),
        "incumbent_iid_sha256": _digest(incumbent_path),
        "tracks": len(assignments),
        "unambiguous_tracks": sum(row["unambiguous"] for row in assignments),
        "ambiguous_singletons": sum(not row["unambiguous"] for row in assignments),
        "repeated_receiver_groups": sum(count > 1 for count in group_counts.values()),
        "repeated_sources": sum(count > 1 for count in source_counts.values()),
        "weight_sum": float(weights.sum()),
        "weight_min": float(weights.min()),
        "weight_max": float(weights.max()),
    }
    return model
