"""Freeze an already observed recent completed-GLRT cohort through GET ports."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8090"
OBSERVED_IDS = tuple("scan-fw-" + value for value in (
    "037100c3a1aa6ca8", "426fc8e39a8ae312", "bff98f93bf551aed", "ab4f89ad17f7b673",
    "e02ff59c036b5abe", "b2cec9cc7957e62e", "7869e9c271fe72f8", "ea6d27f9f5712399",
    "f75551f7591fc2a2", "4b63e4e82af22de2", "a1e890eee8e880e1", "48db0c69158afdbd",
    "7503dce5ad59cac2", "87c303fa4942bfa8", "ffe5accf2d020263", "301fa01e56cd55af",
))


def sha(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def glrt_complete(history: dict, status: dict) -> bool:
    if status["session_id"] != history["session_id"]:
        raise ValueError("analysis session binding differs")
    if status["input_manifest_sha256"] != history["input_manifest_sha256"]:
        raise ValueError("analysis recording digest differs")
    return bool(status.get("metrics_manifest_sha256") and
                status.get("checkpoint_visits") == status.get("total_visits") and
                status.get("total_visits", 0) > 0)


def select_recent(history: list[dict], statuses: dict[str, dict], count=16) -> list[dict]:
    if len({r["session_id"] for r in history}) != len(history):
        raise ValueError("duplicate capture identity")
    ordered = sorted(history, key=lambda r: (r["captured_at"], r["session_id"]), reverse=True)
    eligible = [r for r in ordered if glrt_complete(r, statuses[r["session_id"]])]
    if len(eligible) < count:
        raise ValueError("insufficient completed GLRT scans")
    return eligible[:count]


def get(route: str) -> bytes:
    with urlopen(BASE + route, timeout=30) as response:
        return response.read()


def freeze() -> None:
    target = HERE / "selection.json"
    if target.exists():
        raise FileExistsError("cohort is already frozen; do not move it")
    receipts = HERE / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    raw_history = get("/api/v2/scanner/adaptive-sessions?limit=20&cursor=0")
    (receipts / "history.json").write_bytes(raw_history)
    history = json.loads(raw_history)["items"]
    by_id = {r["session_id"]: r for r in history}
    if not set(OBSERVED_IDS) <= set(by_id):
        raise ValueError("observed cohort disappeared from bounded history inventory")
    def status(row):
        sid = row["session_id"]
        route = f"/api/v2/scanner/adaptive-sessions/{sid}/analysis?probe_stride_ms=120"
        raw = get(route)
        (receipts / f"{sid}-analysis.json").write_bytes(raw)
        return sid, json.loads(raw)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        statuses = dict(pool.map(status, history))
    scans = []
    for index, sid in enumerate(OBSERVED_IDS, 1):
        h, s = by_id[sid], statuses[sid]
        if not glrt_complete(h, s):
            raise ValueError("previously observed sealed GLRT scan is no longer available")
        scans.append({"label": f"R{index:02d}", "session_id": sid,
            "capture_utc": h["captured_at"], "sample_rate_hz": h["sample_rate_hz"],
            "edge": h["selected_edge"], "total_visits": s["total_visits"],
            "recording_manifest_sha256": h["input_manifest_sha256"],
            "binding_sha256": s["binding_sha256"],
            "metrics_manifest_sha256": s["metrics_manifest_sha256"],
            "analysis_receipt": f"receipts/{sid}-analysis.json",
            "analysis_receipt_sha256": sha((receipts / f"{sid}-analysis.json").read_bytes())})
    newer = [r for r in history if r["captured_at"] > scans[0]["capture_utc"]]
    value = {
        "schema": "org.leo.research.recent16-glrt-cohort.v1",
        "frozen_utc": dt.datetime.now(dt.UTC).isoformat(),
        "selection": "newest16 completed-GLRT scans at prior metadata observation; fixed identities",
        "completion": "sealed metrics digest present and checkpoint_visits==total_visits>0; no tracking or quality gate",
        "prior_observation_excluded_newer": [{"session_id": "scan-fw-7041e8bada71584f",
            "state": "partial", "checkpoint_visits": 939, "total_visits": 2221,
            "metrics_manifest_sha256": None,
            "note": "observed before full receipts were archived; current receipt retained separately"}],
        "newer_at_receipt_collection": [{"history": r, "status": statuses[r["session_id"]]}
                                         for r in newer],
        "history_receipt_sha256": sha(raw_history), "scans": scans,
        "source_sha256": sha(Path(__file__).read_bytes()),
    }
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"selected": len(scans), "newer_receipt_states":
                      [(r["session_id"], statuses[r["session_id"]]["state"]) for r in newer]}))


if __name__ == "__main__":
    freeze()
