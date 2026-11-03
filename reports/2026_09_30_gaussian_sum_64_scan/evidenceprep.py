#!/usr/bin/env python3
"""Freeze and prepare the authorized 64-scan evidence panel without fitting."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import argparse
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / "reports/2026_09_30_gaussian_sum_single_scan"
AUTHORITIES = {
    "DS9": ROOT / "reports/2026_09_28_ds9_post_ds8/manifest.json",
    "DS10": ROOT / "reports/2026_09_29_ds10_post_ds9/local/manifest.json",
    "DS11": ROOT / "reports/2026_09_30_ds11_post_ds10/local/manifest.json",
}
COUNTS = {"DS9": 22, "DS10": 21, "DS11": 21}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def old_adapter():
    spec = importlib.util.spec_from_file_location("old_gaussian_evidence", OLD / "evidence.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load evidence adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def freeze_selection() -> dict[str, Any]:
    selected = {}
    for dataset, path in AUTHORITIES.items():
        captures = sorted(read(path)["captures"], key=lambda row: (row["capture_start_utc_ns"], row["session_id"]))
        count = COUNTS[dataset]
        indices = [math.floor(i * (len(captures) - 1) / (count - 1)) for i in range(count)]
        selected[dataset] = [captures[index] | {"selection_index": index, "unit_id": f"{dataset}-F{index + 1:03d}"}
                             for index in indices]
    return {
        "schema": "gaussian-sum-64-scan-selection/v1",
        "method": "per dataset chronological floor(i*(N-1)/(count-1)); zero based; capture start then session ID",
        "counts": COUNTS,
        "authorities": {dataset: {"path": str(path), "sha256": digest(path)} for dataset, path in AUTHORITIES.items()},
        "selected": selected,
    }


def find_exports(session_id: str) -> list[Path]:
    matches = []
    paths = list(ROOT.glob("reports/*/exports/*/observations.json")) + list((HERE / "evidence/sources").glob("*.observations.json"))
    for path in paths:
        prefix = path.read_text(encoding="utf-8")[:600]
        if f'"session_id":"{session_id}"' in prefix or f'"session_id": "{session_id}"' in prefix:
            matches.append(path.resolve())
    return sorted(matches)


def build_inventory(selection: dict[str, Any]) -> dict[str, Any]:
    adapter = old_adapter()
    rows = []
    for dataset, captures in selection["selected"].items():
        for capture in captures:
            accepted, rejected = [], []
            for path in find_exports(capture["session_id"]):
                try:
                    bundle = adapter.load_observation_export(path, capture)
                    accepted.append({"path": str(path), "sha256": bundle["source"]["sha256"],
                                     "tracks": len(bundle["tracks"]),
                                     "observations": sum(len(row["measured_hz"]) for row in bundle["tracks"])})
                except Exception as error:
                    rejected.append({"path": str(path), "error": f"{type(error).__name__}: {error}"})
            rows.append({"dataset": dataset, "unit_id": capture["unit_id"], "session_id": capture["session_id"],
                         "manifest_sha256": capture["manifest_sha256"],
                         "status": "ready" if accepted else "missing_selected_export",
                         "accepted_exports": accepted, "rejected_exports": rejected})
    return {"schema": "gaussian-sum-64-scan-inventory/v1", "selection_sha256": digest(HERE / "selection.json"),
            "rows": rows, "counts": {"ready": sum(row["status"] == "ready" for row in rows),
                                      "missing_selected_export": sum(row["status"] != "ready" for row in rows)}}


def export_observations(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    adapter = old_adapter()
    results = []
    for row in inventory["rows"]:
        if row["status"] != "ready":
            results.append({"unit_id": row["unit_id"], "status": "failed", "error": row["status"]})
            continue
        source = Path(row["accepted_exports"][0]["path"])
        output = HERE / "evidence" / f"{row['unit_id']}.json"
        bundle = adapter.load_observation_export(source, {"session_id": row["session_id"],
                                                          "manifest_sha256": row["manifest_sha256"]})
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(bundle, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        results.append({"unit_id": row["unit_id"], "status": "complete", "path": str(output), "sha256": digest(output)})
    return results


def export_missing_source(unit_id: str, output: Path) -> None:
    selection = read(HERE / "selection.json")
    matches = [row for rows in selection["selected"].values() for row in rows if row["unit_id"] == unit_id]
    if len(matches) != 1:
        raise ValueError("unit absent or duplicated")
    spec = importlib.util.spec_from_file_location("baseline_exporter", ROOT / "tools/ds7_export_baseline.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load public baseline exporter")
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    exporter.export(matches[0], output, Path("/srv/bulk/leo"), Path("/var/lib/leo/tle"))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("freeze")
    source = sub.add_parser("export-source")
    source.add_argument("unit_id")
    source.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "export-source":
        export_missing_source(args.unit_id, args.output)
        return
    selection = freeze_selection()
    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    inventory = build_inventory(selection)
    inventory["observation_exports"] = export_observations(inventory)
    (HERE / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    print(json.dumps({"selected": 64, **inventory["counts"], "inventory_sha256": digest(HERE / "inventory.json")}, separators=(",", ":")))


if __name__ == "__main__":
    main()
