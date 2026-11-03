#!/usr/bin/env python3
"""Audit the 48 frozen evidence bundles without running scientific fits."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def runner_independent_tracks(evidence: dict[str, Any]):
    spec = importlib.util.spec_from_file_location("gaussian_sum_runner_for_audit", HERE / "run.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.independent_tracks(evidence)


def build_audit() -> dict[str, Any]:
    selection = read(HERE / "selection.json")
    inventory = read(HERE / "inventory.json")
    selected = {
        row["unit_id"]: (dataset, row)
        for dataset, rows in selection["selected"].items()
        for row in rows
    }
    units = []
    for inventory_row in inventory["rows"]:
        unit = inventory_row["unit_id"]
        dataset, capture = selected[unit]
        path = HERE / "evidence" / f"{unit}.json"
        evidence = read(path)
        exports = [item for item in inventory_row["exports"] if "sha256" in item]
        if not exports:
            raise ValueError(f"no accepted source export for {unit}")
        bound = next((item for item in exports if item["sha256"] == evidence["source"]["sha256"]), None)
        source = Path(evidence["source"]["path"])
        source_hash_ok = source.is_file() and digest(source) == evidence["source"]["sha256"]
        retained, excluded = runner_independent_tracks(evidence)
        rf = [float(track["rf_hz"]) for track in evidence["tracks"]]
        collisions = evidence.get("observation_id_collisions", {})
        covariance_missing = sum(
            track.get("uncertainty", {}).get("covariance_hz2") is None
            for track in evidence["tracks"]
        )
        aliases_missing = sum(not track.get("aliases") for track in evidence["tracks"])
        discontinuities_missing = sum(not track.get("discontinuities") for track in evidence["tracks"])
        units.append({
            "dataset": dataset,
            "unit_id": unit,
            "session_id": evidence["session_id"],
            "fit_status": "smoke_ready_not_started" if unit == "DS9-F001" else "pending_not_started",
            "gate": "first_DS9_smoke" if unit == "DS9-F001" else "await_first_DS9_smoke_gate",
            "bindings": {
                "evidence_path": str(path),
                "evidence_sha256": digest(path),
                "source_path": str(source),
                "source_sha256": evidence["source"]["sha256"],
                "source_hash_verified": source_hash_ok,
                "inventory_binding_verified": bound is not None,
                "manifest_binding_verified": evidence["manifest_sha256"] == capture["manifest_sha256"],
            },
            "preassociation_tracks": len(evidence["tracks"]),
            "observations": sum(len(track["measured_hz"]) for track in evidence["tracks"]),
            "runner_independent_tracks": {
                "retained": len(retained),
                "excluded": len(excluded),
                "excluded_track_ids": [row["track_id"] for row in excluded],
                "excluded_reasons": sorted({row["reason"] for row in excluded}),
            },
            "source_overlap": {
                "colliding_observation_atoms": len(collisions),
                "tracks_touching_collisions": len({track for owners in collisions.values() for track in owners}),
            },
            "rf_hz": {"minimum": min(rf), "maximum": max(rf), "distinct": sorted(set(rf))},
            "metadata_gaps": {
                "tracks_without_covariance": covariance_missing,
                "tracks_without_alias_alternatives": aliases_missing,
                "tracks_without_discontinuity_annotations": discontinuities_missing,
                "original_physical_observation_ids_absent_from_source_export": True,
                "completed_track_retrospective_only": True,
            },
        })
    if len(units) != 48 or len({row["unit_id"] for row in units}) != 48:
        raise ValueError("audit must account for 48 unique units")
    datasets = {}
    for dataset in ("DS9", "DS10", "DS11"):
        rows = [row for row in units if row["dataset"] == dataset]
        datasets[dataset] = {
            "units": len(rows),
            "source_hash_bindings_verified": sum(row["bindings"]["source_hash_verified"] for row in rows),
            "inventory_bindings_verified": sum(row["bindings"]["inventory_binding_verified"] for row in rows),
            "manifest_bindings_verified": sum(row["bindings"]["manifest_binding_verified"] for row in rows),
            "preassociation_tracks": sum(row["preassociation_tracks"] for row in rows),
            "observations": sum(row["observations"] for row in rows),
            "runner_retained_tracks": sum(row["runner_independent_tracks"]["retained"] for row in rows),
            "runner_excluded_tracks": sum(row["runner_independent_tracks"]["excluded"] for row in rows),
            "colliding_observation_atoms": sum(row["source_overlap"]["colliding_observation_atoms"] for row in rows),
            "rf_hz_minimum": min(row["rf_hz"]["minimum"] for row in rows),
            "rf_hz_maximum": max(row["rf_hz"]["maximum"] for row in rows),
            "fit_status_counts": {
                status: sum(row["fit_status"] == status for row in rows)
                for status in sorted({row["fit_status"] for row in rows})
            },
        }
    return {
        "schema": "gaussian-sum-data-audit/v1",
        "selection_sha256": digest(HERE / "selection.json"),
        "inventory_sha256": digest(HERE / "inventory.json"),
        "scope": "frozen pre-association evidence only; no fits and no new orbit exports",
        "fit_accounting": {"smoke_ready_not_started": 1, "pending_not_started": 47},
        "datasets": datasets,
        "units": units,
    }


def main() -> None:
    output = HERE / "data-audit.json"
    output.write_text(json.dumps(build_audit(), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(output), "sha256": digest(output)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
