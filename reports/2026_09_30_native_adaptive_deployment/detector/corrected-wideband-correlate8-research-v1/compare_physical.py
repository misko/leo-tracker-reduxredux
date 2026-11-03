"""Compare serial ABBA detector runs, preserving numeric output lexemes."""
import hashlib
import json
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent


def main():
    runs = []
    reference = None
    for name in ("control-1", "candidate-1", "candidate-2", "control-2"):
        path = HERE / f"physical-{name}.jsonl"
        raw = path.read_text()
        parsed = [json.loads(line) for line in raw.splitlines() if line]
        lexical = [json.loads(line, parse_float=str, parse_int=str)
                   for line in raw.splitlines() if line]
        result = next(row["result"] for row in parsed if "result" in row)
        lex_result = next(row["result"] for row in lexical if "result" in row)
        rows = [{k: v for k, v in row.items() if k != "timings_ms"}
                for row in lex_result["rows"]]
        if reference is None:
            reference = rows
        timing = json.loads((HERE / f"physical-{name}.time.json").read_text())
        runs.append({
            "name": name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "exact_non_timing_row_fields_and_numeric_lexemes": rows == reference,
            "call_wall_seconds": result["call_wall_ms"] / 1000,
            "whole_process": timing,
        })
    means = {v: mean(r["call_wall_seconds"] for r in runs if r["name"].startswith(v))
             for v in ("control", "candidate")}
    exact = all(r["exact_non_timing_row_fields_and_numeric_lexemes"] and
                r["whole_process"]["exit_code"] == 0 for r in runs)
    gain = 100 * (1 - means["candidate"] / means["control"])
    result = {
        "schema": "leo-correlate8-physical-abba/v1",
        "status": "pass" if exact else "fail",
        "scope": "one saved DS9 dwell, dual RX, serial CPU-only physical ARM ABBA",
        "runs": runs, "mean_call_wall_seconds": means,
        "mean_reduction_percent": gain,
        "minimum_gain_percent_for_further_qualification": 3,
        "performance_threshold_met": gain >= 3,
        "real_time_qualified": False, "production_changed": False,
    }
    (HERE / "physical-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
