"""Bind the serial ARM next-up/layout measurements and exact row lexemes."""
import hashlib
import json
from pathlib import Path


here = Path(__file__).resolve().parent
paths = [
    ("next_up", here.parent / "corrected-wideband-nextup-research-v1/physical-candidate-repeat.jsonl"),
    ("epoch_major_bounds", here / "physical-visit-0301.jsonl"),
]
reference_rows = None
runs = []
for variant, path in paths:
    text = path.read_text()
    numeric = [json.loads(line) for line in text.splitlines() if line]
    lexical = [json.loads(line, parse_float=str, parse_int=str)
               for line in text.splitlines() if line]
    call = next(item["result"] for item in numeric if "result" in item)
    lex_call = next(item["result"] for item in lexical if "result" in item)
    rows = [{key: value for key, value in row.items() if key != "timings_ms"}
            for row in lex_call["rows"]]
    if reference_rows is None:
        reference_rows = rows
    runs.append({
        "variant": variant,
        "path": str(path.relative_to(here.parent)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "all_non_timing_row_fields_and_number_lexemes_equal": rows == reference_rows,
        "call_wall_seconds": call["call_wall_ms"] / 1000,
        "detector_cpu_seconds": call["detector_cpu_ms"] / 1000,
    })
reduction = 100 * (1 - runs[1]["call_wall_seconds"] / runs[0]["call_wall_seconds"])
result = {
    "schema": "leo-interval-layout-physical-comparison/v1",
    "status": "pass" if all(run["all_non_timing_row_fields_and_number_lexemes_equal"]
                              for run in runs) else "fail",
    "scope": "one saved DS9 dwell, two receivers, serial CPU-only ARM runs",
    "runs": runs,
    "single_run_reduction_percent": reduction,
    "interpretation": "The small single-run difference is insufficient to demonstrate a speedup; no repeat or promotion is warranted.",
    "real_time_qualified": False,
    "production_changed": False,
}
(here / "physical-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["status"] == "pass" else 1)
