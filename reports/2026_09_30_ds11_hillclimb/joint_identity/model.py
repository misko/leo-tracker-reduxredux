"""Training-frozen joint physical-identity mixture for DS11 single scans."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.special import logsumexp


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402


VARIANTS = ("joint_identity",)
CONFIDENCE_THRESHOLD = 0.90


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_assignments(documents, config, original_x, candidate_norad, *, model_factory=None):
    """Freeze strong physical identities from the original IID training endpoint."""
    factory = model_factory or fast.baseline.Stationary
    engines = [factory(document, config) for document in documents]
    assignments = []
    for document_index, (document, engine) in enumerate(zip(documents, engines, strict=True)):
        local = np.asarray(original_x, dtype=float)[[0, 1, document_index + 2]]
        mapping = candidate_norad[document_index]
        if set(mapping) != {track["track_id"] for track in document["tracks"]}:
            raise ValueError("physical identity mapping track coverage mismatch")
        for track_index, track in enumerate(document["tracks"]):
            norads = tuple(int(value) for value in mapping[track["track_id"]])
            if len(norads) != len(set(norads)):
                raise ValueError("duplicate physical NORAD within candidate bank")
            prediction, visible = engine.prediction(track, local)
            score, _, audits, _ = fast.profile(track["y"][None, :] - prediction, track["mask"])
            if not all(audit["converged"] for audit in audits):
                raise RuntimeError("offset stationarity check failed while freezing association")
            if len(norads) != len(score):
                raise ValueError("physical identity mapping differs from candidate bank")
            score = np.where(visible, score, -np.inf)
            normal = logsumexp(score)
            if not np.isfinite(normal):
                raise ValueError("no visible training candidate while freezing association")
            probability = np.exp(score - normal)
            slot = int(np.argmax(probability))
            confidence = float(probability[slot])
            assignments.append({
                "document_index": document_index,
                "track_index": track_index,
                "track_id": track["track_id"],
                "receiver_id": int(track["receiver_id"]),
                "rf_hz": float(track["rf_hz"]),
                "norad": norads[slot] if confidence >= CONFIDENCE_THRESHOLD else None,
                "confidence": confidence,
                "unambiguous": confidence >= CONFIDENCE_THRESHOLD,
            })
    return assignments


def freeze_groups(assignments, candidate_norad):
    """Group a strong identity only when it spans exact receiver/RF strata."""
    by_identity = defaultdict(list)
    for row in assignments:
        if row["unambiguous"]:
            by_identity[(row["document_index"], row["norad"])].append(row)

    groups = []
    grouped = set()
    for (document_index, norad), rows in sorted(by_identity.items()):
        strata = {(row["receiver_id"], row["rf_hz"]) for row in rows}
        if len(strata) < 2:
            continue
        mapping = candidate_norad[document_index]
        supports = [set(map(int, mapping[row["track_id"]])) for row in rows]
        common = set.intersection(*supports)
        if not common:
            raise ValueError("joint identity group has empty physical candidate intersection")
        if norad not in common:
            raise ValueError("frozen selected identity absent from group candidate intersection")
        members = tuple((row["document_index"], row["track_index"]) for row in rows)
        if grouped.intersection(members):
            raise ValueError("track occurs in more than one joint identity group")
        grouped.update(members)
        groups.append({
            "document_index": document_index,
            "norad": int(norad),
            "members": members,
            "candidate_norad": tuple(sorted(common)),
            "strata": tuple(sorted(strata)),
        })
    all_tracks = {(row["document_index"], row["track_index"]) for row in assignments}
    singletons = tuple(sorted(all_tracks - grouped))
    if len(grouped) + len(singletons) != len(assignments):
        raise ValueError("joint association observation accounting mismatch")
    return groups, singletons


class JointIdentity:
    """One latent physical candidate per frozen group; independent track CFOs."""

    def __init__(self, documents, config, candidate_norad, groups, singletons,
                 *, model_factory=None):
        factory = model_factory or fast.baseline.Stationary
        self.documents = documents
        self.models = [factory(document, config) for document in documents]
        self.candidate_norad = candidate_norad
        self.groups = groups
        self.singletons = singletons
        self._track_count = sum(len(document["tracks"]) for document in documents)
        covered = set(singletons)
        for group in groups:
            covered.update(group["members"])
        expected = {
            (document_index, track_index)
            for document_index, document in enumerate(documents)
            for track_index in range(len(document["tracks"]))
        }
        if covered != expected or len(singletons) + sum(len(g["members"]) for g in groups) != len(expected):
            raise ValueError("joint association must account for every track exactly once")
        self._slots = {}
        for document_index, document in enumerate(documents):
            mapping = candidate_norad[document_index]
            for track_index, track in enumerate(document["tracks"]):
                ids = tuple(int(value) for value in mapping[track["track_id"]])
                if len(ids) != len(set(ids)):
                    raise ValueError("duplicate physical NORAD within candidate bank")
                self._slots[(document_index, track_index)] = {
                    norad: slot for slot, norad in enumerate(ids)
                }
        for group in groups:
            catalogue_sizes = {
                documents[d]["tracks"][t]["catalogue_size"] for d, t in group["members"]
            }
            if len(catalogue_sizes) != 1:
                raise ValueError("joint group catalogue sizes differ")
            for member in group["members"]:
                if not set(group["candidate_norad"]).issubset(self._slots[member]):
                    raise ValueError("joint group support is absent from a member candidate bank")

    def _track_terms(self, x, gradient):
        terms = {}
        x = np.asarray(x, dtype=float)
        for document_index, (document, engine) in enumerate(
            zip(self.documents, self.models, strict=True)
        ):
            local = x[[0, 1, document_index + 2]]
            for track_index, track in enumerate(document["tracks"]):
                prediction, visible = engine.prediction(track, local)
                residual = track["y"][None, :] - prediction
                score, _, audits, offsets = fast.profile(residual, track["mask"])
                if not all(audit["converged"] for audit in audits):
                    raise RuntimeError("offset stationarity check failed")
                score = np.where(visible, score, -np.inf)
                if not np.isfinite(score).any():
                    raise ValueError("no visible training candidate")
                candidate_gradient = None
                if gradient:
                    centered = residual[:, track["mask"]] - offsets[:, None]
                    slope = 5 * centered / (40000 + centered**2)
                    candidate_gradient = np.zeros((len(score), 3))
                    for axis in range(3):
                        step = 1e-4 if axis < 2 else 1e-5
                        plus, minus = local.copy(), local.copy()
                        plus[axis] += step
                        minus[axis] -= step
                        if axis == 2:
                            plus[axis] = min(5.0, plus[axis])
                            minus[axis] = max(-5.0, minus[axis])
                        delta = (
                            engine.prediction(track, plus)[0]
                            - engine.prediction(track, minus)[0]
                        ) / (plus[axis] - minus[axis])
                        candidate_gradient[:, axis] = np.sum(
                            slope * delta[:, track["mask"]], axis=1
                        )
                terms[(document_index, track_index)] = {
                    "score": score,
                    "gradient": candidate_gradient,
                    "offset": offsets,
                    "catalogue_size": int(track["catalogue_size"]),
                }
        return terms

    @staticmethod
    def _add_local(derivative, document_index, local):
        derivative[:2] += local[:2]
        derivative[document_index + 2] += local[2]

    def evaluate(self, x, gradient=True):
        x = np.asarray(x, dtype=float)
        terms = self._track_terms(x, gradient)
        total = 0.0
        derivative = np.zeros_like(x)
        for member in self.singletons:
            document_index, _ = member
            term = terms[member]
            normal = logsumexp(term["score"])
            total += float(normal - math.log(term["catalogue_size"]))
            if gradient:
                responsibility = np.exp(term["score"] - normal)
                self._add_local(
                    derivative, document_index, responsibility @ term["gradient"]
                )
        for group in self.groups:
            combined_score = []
            combined_gradient = []
            for norad in group["candidate_norad"]:
                score = 0.0
                local_gradient = np.zeros(3)
                for member in group["members"]:
                    slot = self._slots[member][norad]
                    score += terms[member]["score"][slot]
                    if gradient:
                        local_gradient += terms[member]["gradient"][slot]
                combined_score.append(score)
                if gradient:
                    combined_gradient.append(local_gradient)
            combined_score = np.asarray(combined_score)
            normal = logsumexp(combined_score)
            if not np.isfinite(normal):
                raise ValueError("no jointly visible training candidate")
            catalogue_size = terms[group["members"][0]]["catalogue_size"]
            total += float(normal - math.log(catalogue_size))
            if gradient:
                responsibility = np.exp(combined_score - normal)
                local = responsibility @ np.asarray(combined_gradient)
                self._add_local(derivative, group["document_index"], local)
        return {"score": total, "gradient": derivative}

    def responsibility_diagnostics(self, x):
        """Return training-only IID and joint physical-candidate masses."""
        terms = self._track_terms(np.asarray(x, dtype=float), False)
        rows = []
        for group in self.groups:
            joint_score = np.asarray([
                sum(terms[member]["score"][self._slots[member][norad]]
                    for member in group["members"])
                for norad in group["candidate_norad"]
            ])
            joint_normal = logsumexp(joint_score)
            if not np.isfinite(joint_normal):
                raise ValueError("no jointly visible training candidate")
            joint = {
                norad: float(value) for norad, value in zip(
                    group["candidate_norad"], np.exp(joint_score - joint_normal), strict=True
                )
            }
            for member in group["members"]:
                score = terms[member]["score"]
                normal = logsumexp(score)
                ids = self.candidate_norad[member[0]][
                    self.documents[member[0]]["tracks"][member[1]]["track_id"]
                ]
                iid = {int(norad): float(value) for norad, value in zip(
                    ids, np.exp(score - normal), strict=True
                )}
                support = set(iid) | set(joint)
                tv = 0.5 * sum(abs(iid.get(norad, 0.0) - joint.get(norad, 0.0))
                               for norad in support)
                rows.append({
                    "group_norad": group["norad"],
                    "member": member,
                    "iid_selected_probability": iid.get(group["norad"], 0.0),
                    "joint_selected_probability": joint.get(group["norad"], 0.0),
                    "total_variation": tv,
                    "joint_max_probability": max(joint.values()),
                })
        return rows


def _qualified_incumbent(index, session_id):
    result_path = BASE / "runs" / f"{index:02d}_iid.json"
    receipt_path = BASE / "runs" / f"{index:02d}_iid.receipt.json"
    if not receipt_path.exists() or not result_path.exists():
        raise ValueError("original IID result or receipt missing")
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get("exit_code") != 0 or receipt.get("index") != index
            or receipt.get("method") != "iid"):
        raise ValueError("original IID receipt is not a successful matching attempt")
    record = json.loads(result_path.read_text())
    if (record.get("index") != index or record.get("method") != "iid"
            or record.get("session") != session_id):
        raise ValueError("original IID result identity mismatch")
    bounds = ((-12.0, 12.0), (-12.0, 12.0), (-5.0, 5.0))
    valid = []
    for start in record.get("starts", []):
        x = start.get("x", [])
        finite = (len(x) == 3 and all(math.isfinite(float(value)) for value in x)
                  and math.isfinite(float(start.get("score", math.nan)))
                  and math.isfinite(float(start.get("gradient", math.nan)))
                  and math.isfinite(float(start.get("audit", math.nan))))
        boundary = finite and any(
            min(float(value) - lo, hi - float(value)) < 0.001
            for value, (lo, hi) in zip(x, bounds, strict=True)
        )
        qualified = bool(finite and start.get("success") and not boundary
                         and float(start["gradient"]) <= 0.01
                         and float(start["audit"]) <= 0.02)
        if bool(start.get("qualified")) != qualified:
            raise ValueError("original IID start qualification is inconsistent")
        if qualified:
            valid.append(start)
    selected = record.get("selected")
    if not valid or selected is None:
        raise ValueError("original same-scan IID fit is unqualified")
    winner = max(valid, key=lambda row: float(row["score"]))
    if selected.get("x") != winner.get("x") or selected.get("score") != winner.get("score"):
        raise ValueError("original IID selected endpoint is not highest qualified start")
    return selected, result_path, receipt_path


def _resources(index, documents):
    if index is None:
        raise ValueError("joint identity grouping requires the immutable single-scan index")
    plan_path = BASE / "plan.json"
    sidecar_path = HERE.parent / "source_balance" / "catalogue_identities.json"
    plan = json.loads(plan_path.read_text())
    sidecar = json.loads(sidecar_path.read_text())
    if sidecar.get("schema") != "ds11-source-balance-identities/v1":
        raise ValueError("physical identity sidecar schema mismatch")
    if sidecar.get("plan_sha256") != _digest(plan_path):
        raise ValueError("physical identity sidecar plan binding mismatch")
    entry = plan["inputs"][index]
    scan = sidecar["scans"][str(index)]
    if len(documents) != 1 or not (
        documents[0]["session_id"] == entry["session_id"] == scan["session_id"]
    ):
        raise ValueError("joint identity session or index binding mismatch")
    paths = [Path(artifact["path"]) for artifact in entry["artifacts"]]
    observation = next(path for path in paths if path.name == "observations.json")
    manifest = next(path for path in paths if path.name == "manifest.json")
    bank = next(path for path in paths if path.suffix == ".npz")
    for path, key in ((observation, "observation_sha256"),
                      (manifest, "manifest_sha256"), (bank, "bank_sha256")):
        if _digest(path) != scan[key]:
            raise ValueError(f"physical identity sidecar {key} binding mismatch")
    selected, result_path, receipt_path = _qualified_incumbent(index, entry["session_id"])
    candidates = [{
        track_id: row["candidate_norad"] for track_id, row in scan["tracks"].items()
    }]
    return candidates, selected["x"], {
        "plan": plan_path,
        "sidecar": sidecar_path,
        "incumbent": result_path,
        "receipt": receipt_path,
    }


def build_model(documents, config, variant, index=None):
    if variant not in VARIANTS:
        raise ValueError(f"unknown joint identity variant: {variant}")
    candidate_norad, original_x, resources = _resources(index, documents)
    assignments = freeze_assignments(documents, config, original_x, candidate_norad)
    groups, singletons = freeze_groups(assignments, candidate_norad)
    model = JointIdentity(documents, config, candidate_norad, groups, singletons)
    model.metadata = {
        "objective": "training-frozen empirical-Bayes joint physical-identity likelihood",
        "normalized_posterior": False,
        "variant": variant,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "freeze": "original same-scan IID training endpoint only",
        "group_key": "same strong physical NORAD spanning exact receiver/RF strata",
        "candidate_support": "intersection of retained physical NORAD candidate banks",
        "cfo": "independently profiled for every track/candidate pair",
        "tracks": len(assignments),
        "unambiguous_tracks": sum(row["unambiguous"] for row in assignments),
        "ambiguous_singletons": sum(not row["unambiguous"] for row in assignments),
        "joint_groups": len(groups),
        "joint_group_tracks": sum(len(group["members"]) for group in groups),
        "independent_tracks": len(singletons),
        "resource_sha256": {name: _digest(path) for name, path in resources.items()},
    }
    return model
