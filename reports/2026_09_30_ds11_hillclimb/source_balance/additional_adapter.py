"""Explicit-path adapter for frozen source-balance additional replication."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
FROZEN_MODEL = HERE / "model.py"
FROZEN_MODEL_SHA256 = "23d806106b7d144d93ee34440e4dbf3d276bfcf71a0a64e882168175b42f7cca"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if digest(FROZEN_MODEL) != FROZEN_MODEL_SHA256:
    raise RuntimeError("frozen source-balance model changed after screen")
_spec = importlib.util.spec_from_file_location("ds11_screen_frozen_source_balance", FROZEN_MODEL)
frozen = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = frozen
_spec.loader.exec_module(frozen)


def _require_same_session(document_session, entry_session, scan_session):
    if not (document_session == entry_session == scan_session):
        raise ValueError("additional session or index binding mismatch")


def _load_validated_incumbent(index, session, runs_dir):
    """Accept only a receipt-backed, internally qualified same-scan IID result."""
    receipt_path = runs_dir / f"{index:02d}_iid.receipt.json"
    incumbent_path = runs_dir / f"{index:02d}_iid.json"
    if not receipt_path.exists():
        raise ValueError("additional IID result has no terminal receipt")
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("exit_code") != 0 or receipt.get("index") != index:
        raise ValueError("additional IID receipt is not a successful matching attempt")
    if not incumbent_path.exists():
        raise ValueError("receipt-backed additional IID result is missing")
    record = json.loads(incumbent_path.read_text())
    if (record.get("index") != index or record.get("session") != session or
            record.get("method") != "iid"):
        raise ValueError("additional IID result identity mismatch")
    sources = record.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("additional IID result lacks source bindings")
    for name, expected in sources.items():
        if digest(Path(name)) != expected:
            raise ValueError("additional IID declared source hash mismatch")

    bounds = ((-12.0, 12.0), (-12.0, 12.0), (-5.0, 5.0))
    valid = []
    for start in record.get("starts", []):
        x = start.get("x", [])
        finite = (len(x) == 3 and all(math.isfinite(float(value)) for value in x) and
                  math.isfinite(float(start.get("score", math.nan))) and
                  math.isfinite(float(start.get("gradient", math.nan))) and
                  math.isfinite(float(start.get("audit", math.nan))))
        boundary = finite and any(
            min(float(value) - lo, hi - float(value)) < 0.001
            for value, (lo, hi) in zip(x, bounds, strict=True)
        )
        qualified = bool(
            finite and start.get("success") and not boundary and
            float(start["gradient"]) <= 0.01 and float(start["audit"]) <= 0.02
        )
        if bool(start.get("qualified")) != qualified:
            raise ValueError("additional IID start qualification is inconsistent")
        if qualified:
            valid.append(start)
    selected = record.get("selected")
    if not valid or selected is None:
        raise ValueError("additional same-scan IID fit is unqualified")
    winner = max(valid, key=lambda row: float(row["score"]))
    if selected.get("x") != winner.get("x") or selected.get("score") != winner.get("score"):
        raise ValueError("additional IID selected endpoint is not highest qualified start")
    return selected, incumbent_path, receipt_path


def build_additional_model(
    documents,
    config,
    *,
    index: int,
    plan_path: Path,
    runs_dir: Path,
    identity_sidecar_path: Path,
    variant: str = "source_receiver_equal",
):
    """Build the screen-frozen winner without consulting original-32 paths."""
    if variant != "source_receiver_equal":
        raise ValueError("additional adapter is frozen to the screen winner")
    plan_path = Path(plan_path).resolve()
    runs_dir = Path(runs_dir).resolve()
    identity_sidecar_path = Path(identity_sidecar_path).resolve()
    plan = json.loads(plan_path.read_text())
    entry = plan["inputs"][index]
    sidecar = json.loads(identity_sidecar_path.read_text())
    if sidecar["schema"] != "ds11-source-balance-additional-identities/v1":
        raise ValueError("additional identity sidecar schema mismatch")
    if sidecar["plan_sha256"] != digest(plan_path):
        raise ValueError("additional identity sidecar plan binding mismatch")
    scan = sidecar["scans"][str(index)]
    if len(documents) != 1:
        raise ValueError("additional session or index binding mismatch")
    _require_same_session(
        documents[0]["session_id"], entry["session_id"], scan["session_id"]
    )
    paths = [Path(row["path"]) for row in entry["artifacts"]]
    observation = next(path for path in paths if path.name == "observations.json")
    manifest = next(path for path in paths if path.name == "manifest.json")
    bank = next(path for path in paths if path.suffix == ".npz")
    for path, key in ((observation, "observation_sha256"),
                      (manifest, "manifest_sha256"), (bank, "bank_sha256")):
        if digest(path) != scan[key]:
            raise ValueError(f"additional identity {key} binding mismatch")
    incumbent, incumbent_path, receipt_path = _load_validated_incumbent(
        index, entry["session_id"], runs_dir
    )
    candidate_norad = [{
        track_id: row["candidate_norad"] for track_id, row in scan["tracks"].items()
    }]
    assignments = frozen.freeze_assignments(
        documents, config, incumbent["x"], candidate_norad
    )
    weights = frozen.derive_weights(assignments, variant)
    model = frozen.SourceBalancedIID(documents, config, weights, assignments)
    model.metadata = {
        "variant": variant,
        "freeze": "additional original same-scan IID training endpoint only",
        "screen_frozen_model_sha256": FROZEN_MODEL_SHA256,
        "adapter_sha256": digest(Path(__file__)),
        "plan_sha256": digest(plan_path),
        "identity_sidecar_sha256": digest(identity_sidecar_path),
        "incumbent_iid_sha256": digest(incumbent_path),
        "incumbent_iid_receipt_sha256": digest(receipt_path),
        "tracks": len(assignments),
        "unambiguous_tracks": sum(row["unambiguous"] for row in assignments),
        "ambiguous_singletons": sum(not row["unambiguous"] for row in assignments),
        "normalized_posterior": False,
    }
    return model
