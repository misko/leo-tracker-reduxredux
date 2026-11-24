"""Price the remaining original-input work on six cases with measured solver pairs."""

import gzip
import json
from pathlib import Path

from reports.ALGO08.v3.release_intake_rate import rate_gates, required_rate
from reports.ALGO08.v3.release_stage_budget import checked


MEASUREMENTS = Path(__file__).resolve().parent / "measurements"
INTAKE_PIN = "97889f708715be74e1036e2c9e5f30a38800658bfe9ecff2be4aacbdb2b13aed"
SOLVER_GZIP_PIN = "56526836f300cc9085c4a6b82ebb69c1beb13758444c4e54683d63d12b68a612"


def compare(intake, solver):
    original = {row["case"]: row for row in intake["rows"]}
    keys = solver["case_order"]
    if len(keys) != len(set(keys)) or set(keys) != set(solver["enrolled"]) or not solver["saved_only"]:
        raise ValueError("Require each enrolled saved pair exactly once")
    cases = []
    for key in keys:
        pair = solver["enrolled"][key]
        case = "DS30-" + key
        raw = original[case]
        if raw["byte_low"] != raw["byte_high"] or raw["post_s"] is None:
            raise ValueError(f"Require exact original extent and stage clock for {case}")
        result = pair["result"]
        named = result["archive_stock_clock"]["elapsed_s"]
        routed = result["clock"]["elapsed_s"] + pair["source_stage"]["preflight"]["elapsed_ns"] / 1e9
        cases.append(dict(case=case, size=raw["byte_high"], elapsed_s=raw["elapsed_s"],
                          named_post_s=raw["post_s"], named_saved_s=named, saved_wall_s=routed,
                          scaled_post_s=raw["post_s"] * routed / named))
    scenarios = {}
    for field in ("saved_wall_s", "scaled_post_s"):
        rows = [dict(row, post_s=row[field]) for row in cases]
        scenarios[field] = dict(
            gate=required_rate(rows, "size", 1, 0),
            at_283_MB_s=rate_gates(rows, "size", 283.1, 1, 0),
            per_case_MB_s={r["case"]: r["size"] / 1e6 / (r["elapsed_s"]/2-r["post_s"])
                           if r["post_s"] < r["elapsed_s"]/2 else None for r in rows},
        )
    return dict(cases=cases, scenarios=scenarios)


def load():
    intake = json.loads(checked(MEASUREMENTS / "release-intake-rate.json", INTAKE_PIN))
    solver = json.loads(gzip.decompress(checked(MEASUREMENTS / "history-risk-six-case.json.gz", SOLVER_GZIP_PIN)))
    return compare(intake, solver)


if __name__ == "__main__":
    print(json.dumps(load(), indent=2, allow_nan=False))
