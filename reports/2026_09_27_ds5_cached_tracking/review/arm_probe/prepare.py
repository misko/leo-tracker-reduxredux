#!/usr/bin/env python3
"""Materialize selected saved IQ and templates into a transport directory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plan_path = HERE / "plan.json"
    plan = json.loads(plan_path.read_text())
    if not plan.get("holdout_excluded"):
        raise ValueError("refusing a plan without explicit holdout exclusion")
    args.output.mkdir(parents=True, exist_ok=False)
    files = []
    templates = {}
    for case in plan["cases"]:
        if case["split"] not in ("dev", "control"):
            raise ValueError("only development and control cases are permitted")
        source = ROOT / case["dataset_dir"] / case["raw_npy"]["path"]
        expected = case["raw_npy"]["sha256"].removeprefix("sha256:")
        if digest(source) != expected:
            raise ValueError(f"source hash mismatch: {case['case_id']}")
        iq = np.load(source, allow_pickle=False)
        expected_shape = (case["rate_hz"] * 120 // 1000, 2, 2)
        if iq.dtype != np.dtype("<i2") or iq.shape != expected_shape or not iq.flags.c_contiguous:
            raise ValueError(f"unexpected IQ contract: {case['case_id']}")
        raw_name = f"case-{len(files):02d}.ci16"
        raw_path = args.output / raw_name
        raw_path.write_bytes(iq.tobytes(order="C"))
        if digest(source) != expected:
            raise ValueError(f"source changed while preparing: {case['case_id']}")
        key = f"{case['rate_hz']}-{case['edge']}"
        if key not in templates:
            paths = {}
            for roll, label in ((0, "exact"), (17, "control")):
                values = np.asarray(qin_edge_pilot_frame(case["rate_hz"], case["edge"], symbol_roll=roll), dtype="<c16")
                name = f"template-{key}-{label}.c128"
                (args.output / name).write_bytes(values.tobytes(order="C"))
                paths[label] = name
                paths[f"{label}_sha256"] = digest(args.output / name)
                paths["count"] = len(values)
            templates[key] = paths
        files.append({**case, "raw_file": raw_name, "raw_file_sha256": digest(raw_path), "template_key": key})
    manifest = {
        "schema": "org.leo.research.arm-stateless-probe-bundle/v1",
        "plan_sha256": digest(plan_path), "cases": files, "templates": templates,
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(digest(args.output / "manifest.json"))


if __name__ == "__main__":
    main()
