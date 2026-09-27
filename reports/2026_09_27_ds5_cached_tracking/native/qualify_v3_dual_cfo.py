#!/usr/bin/env python3
"""Dev-only same-visit oracle check of the V3 dual-CFO contract; noncausal."""

from __future__ import annotations

import json
import statistics
import sys
from contextlib import ExitStack
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATASET = ROOT / "reports/2026_09_26_ds5_server_eval/dataset"
sys.path.insert(0, str(HERE))

from known_state import sha256  # noqa: E402
from known_state_v3 import NativeKnownStateV3, build_library_v3  # noqa: E402


def run(output: Path):
    oracle_path = HERE / "real_oracle_microbenchmark.json"
    oracle = json.loads(oracle_path.read_text())
    cases_path = DATASET / "cases.json"
    cases = {
        case["case_id"]: case
        for case in json.loads(cases_path.read_text())["cases"]
    }
    library = build_library_v3()
    rows = []
    with ExitStack() as stack:
        workspaces = {}
        arrays = {}
        for reference in oracle["rows"]:
            case = cases[reference["case_id"]]
            if case["split"] != "dev":
                raise ValueError("dual-CFO qualification is dev-only")
            key = case["rate_hz"], case["edge"]
            if key not in workspaces:
                workspaces[key] = stack.enter_context(
                    NativeKnownStateV3(*key, library)
                )
            if case["case_id"] not in arrays:
                path = (DATASET / case["raw_npy"]["path"]).resolve()
                expected = case["raw_npy"]["sha256"].removeprefix("sha256:")
                if sha256(path) != expected:
                    raise ValueError("IQ provenance mismatch")
                arrays[case["case_id"]] = np.load(path, allow_pickle=False)
            rate = case["rate_hz"]
            window_samples = rate // 50
            begin = reference["window_index"] * window_samples
            selected = arrays[case["case_id"]][
                begin : begin + window_samples, reference["rx"], :
            ]
            seed = reference["blind_candidate"]
            epoch = seed["epoch"] + seed["fractional_offset_samples"]
            # These states are deliberately distinct. Acquisition CFO is the
            # GLRT scoring center; tracking CFO is the expected physical state.
            scored_cfo = seed["acquired_cfo_hz"]
            expected_physical_cfo = seed["tracking_cfo_hz"]
            variants = {}
            for frame_limit in (16, 4, 2):
                native = workspaces[key]
                for _ in range(10):
                    native.measure(
                        selected,
                        epoch,
                        scored_cfo,
                        expected_physical_cfo_hz=expected_physical_cfo,
                        frame_limit=frame_limit,
                    )
                measured = [
                    native.measure(
                        selected,
                        epoch,
                        scored_cfo,
                        expected_physical_cfo_hz=expected_physical_cfo,
                        frame_limit=frame_limit,
                    )
                    for _ in range(100)
                ]
                variants[str(frame_limit)] = {
                    "result": measured[0],
                    "median_cpu_ms": statistics.median(
                        value["total_cpu_ms"] for value in measured
                    ),
                    "median_wall_ms": statistics.median(
                        value["total_wall_ms"] for value in measured
                    ),
                }
            rows.append(
                {
                    "case_id": case["case_id"],
                    "rx": reference["rx"],
                    "rate_hz": rate,
                    "seed_source": "same_visit_blind_result_oracle_noncausal",
                    "blind_candidate": seed,
                    "variants": variants,
                }
            )
    summary = {}
    for frame_limit in (16, 4, 2):
        key = str(frame_limit)
        summary[key] = {
            "oracle_seeded_reference_positives": len(rows),
            "strict_margin_passes": sum(
                row["variants"][key]["result"]["margin"] > 0.025
                for row in rows
            ),
            "trusted_physical_cfo_innovations": sum(
                row["variants"][key]["result"]["cfo_innovation_within_8khz"]
                for row in rows
            ),
            "retained_reference_positives": sum(
                row["variants"][key]["result"]["margin"] > 0.025
                and row["variants"][key]["result"]["cfo_innovation_within_8khz"]
                for row in rows
            ),
            "median_cpu_ms": statistics.median(
                row["variants"][key]["median_cpu_ms"] for row in rows
            ),
        }
    receipt = {
        "schema": "org.leo.research.known-state-v3-dual-cfo-oracle/v1",
        "status": "same_visit_oracle_seed_microbenchmark_not_causal_tracking",
        "dataset_cases_sha256": sha256(cases_path),
        "oracle_receipt_sha256": sha256(oracle_path),
        "library_sha256": sha256(library),
        "source_sha256": sha256(Path(__file__)),
        "rows": rows,
        "summary": summary,
        "limitations": [
            "same-visit blind outputs are oracle seeds, not prospective tracker state",
            "partial-frame exact/control scores have distinct unqualified semantics",
            "real observations are unlabeled",
        ],
    }
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run(HERE / "v3_dual_cfo_oracle.json")
