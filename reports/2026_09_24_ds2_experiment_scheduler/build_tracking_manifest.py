#!/usr/bin/env python3
"""Bind frozen DS2 inventory session IDs to safe, sealed tracking receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
ENDPOINT = "http://127.0.0.1:8090/api/v1/scanner/tracking"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def fetch(endpoint: str, session_id: str) -> dict[str, Any]:
    with urlopen(f"{endpoint.rstrip('/')}/{session_id}", timeout=20) as response:  # noqa: S310
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("tracking endpoint did not return an object")
    return value


def partition(session_id: str) -> str:
    """Stable whole-session split; it does not inspect tracking quality or position."""
    bucket = int(hashlib.sha256(session_id.encode()).hexdigest()[:8], 16) % 10
    return "train" if bucket < 7 else "validation" if bucket < 9 else "test"


def safe_receipt(response: dict[str, Any]) -> dict[str, Any]:
    product = response.get("product") if isinstance(response.get("product"), dict) else {}
    return {
        "schema": "ds2-tracking-receipt/v1",
        "session_id": response.get("session_id"),
        "state": response.get("state"),
        "phase": response.get("phase"),
        "product_schema_version": product.get("schema_version"),
        "analysis_manifest_sha256": product.get("analysis_manifest_sha256"),
        "configuration_digest": product.get("configuration_digest"),
        "candidate_policy_digest": product.get("tle_match_config_digest"),
        "trajectory_state": product.get("trajectory_state"),
        "tle_state": product.get("tle_state"),
        "artifacts": [
            {key: artifact.get(key) for key in ("name", "sha256", "byte_count")}
            for artifact in product.get("artifacts", [])
            if isinstance(artifact, dict)
        ],
    }


def build(inventory: dict[str, Any], endpoint: str, output: Path) -> dict[str, Any]:
    if inventory.get("schema") != "ds2-adaptive-inventory/v1":
        raise ValueError("unexpected inventory schema")
    output.mkdir(parents=True, exist_ok=True)
    receipt_root = output / "tracking_receipts"
    receipt_root.mkdir(exist_ok=True)
    grouped: defaultdict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for scan in inventory.get("scans", []):
        if scan.get("inclusion", {}).get("raw_capture_eligible") is not True:
            continue
        session_id = scan["session_id"]
        response = fetch(endpoint, session_id)
        receipt = safe_receipt(response)
        receipt_path = receipt_root / f"{session_id}.json"
        receipt_path.write_text(canonical(receipt))
        complete = response.get("state") == "complete" and receipt["analysis_manifest_sha256"]
        product = {
            "status": "complete" if complete else str(response.get("state", "unavailable")),
            "tracking_product_digest": receipt["analysis_manifest_sha256"],
            "candidate_policy_digest": receipt["candidate_policy_digest"],
            "receipt_path": str(receipt_path.resolve()),
            "cache_path": str((output / "unbound_causal_cache" / session_id).resolve()),
            "tracking_endpoint": f"{endpoint.rstrip('/')}/{session_id}",
        }
        key = (partition(session_id), str(scan["radio_id"]), int(scan["sample_rate_hz"]))
        grouped[key].append(
            {
                "session_id": session_id,
                "captured_at": scan.get("captured_at", ""),
                "product": product,
            }
        )
    groups = []
    for (part, radio, rate), rows in sorted(grouped.items()):
        cohort_id = f"{radio}-{rate}"
        ordered = sorted(rows, key=lambda row: (row["captured_at"], row["session_id"]))
        # Four sessions is a bounded, coherent unit for the staged joint arms;
        # never mix radios or sample rates merely to make a larger union.
        for batch_index in range(0, len(ordered), 4):
            batch = ordered[batch_index : batch_index + 4]
            groups.append(
                {
                    "group_id": f"{part}-{cohort_id}-batch-{batch_index // 4:02d}",
                    "cohort_id": cohort_id,
                    "partition": part,
                    "session_ids": [row["session_id"] for row in batch],
                    "tracking_products": {row["session_id"]: row["product"] for row in batch},
                }
            )
    return {
        "schema": "ds2-position-manifest/v1",
        "manifest_sealed": True,
        "reference_coordinate_in_manifest": False,
        "position_evaluation": "post_seal_external_only",
        "inventory_manifest_sha256": "sha256:"
        + hashlib.sha256(canonical(inventory).encode()).hexdigest(),
        "priors": [
            {
                "id": "blind-prior-not-yet-bound",
                "reference_used_for_selection": False,
                "status": "not_ready",
            }
        ],
        "groups": groups,
        "geometry": {"status": "not_ready"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default=ENDPOINT)
    args = parser.parse_args()
    manifest = build(read_json(args.inventory), args.endpoint, args.output)
    path = args.output / "ds2-tracking-manifest.json"
    path.write_text(canonical(manifest))
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
    print(canonical({"groups": len(manifest["groups"]), "output": str(path)}), end="")


if __name__ == "__main__":
    main()
