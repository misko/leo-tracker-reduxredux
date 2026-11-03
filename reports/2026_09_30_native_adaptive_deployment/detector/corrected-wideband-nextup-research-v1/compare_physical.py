"""Bind the serial ARM control/candidate measurements and exact row lexemes."""
import hashlib
import json
from pathlib import Path
from statistics import mean

here = Path(__file__).resolve().parent
paths = [
    ("control", here.parent / "corrected-wideband-arm-v1/visit-0301.arm.jsonl"),
    ("candidate", here / "physical-visit-0301.jsonl"),
    ("control", here / "physical-control-repeat.jsonl"),
    ("candidate", here / "physical-candidate-repeat.jsonl"),
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
    exact = rows == reference_rows
    runs.append({
        "variant": variant,
        "path": str(path.relative_to(here.parent)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "all_non_timing_row_fields_and_number_lexemes_equal": exact,
        "call_wall_seconds": call["call_wall_ms"] / 1000,
        "detector_cpu_seconds": call["detector_cpu_ms"] / 1000,
    })
means = {variant: mean(run["call_wall_seconds"] for run in runs
                       if run["variant"] == variant)
         for variant in ("control", "candidate")}
result = {
    "schema": "leo-nextup-physical-comparison/v1",
    "status": "pass" if all(run["all_non_timing_row_fields_and_number_lexemes_equal"]
                            for run in runs) else "fail",
    "scope": "one saved DS9 dwell, two receivers, serial CPU-only ARM runs",
    "order": [variant for variant, _ in paths],
    "runs": runs,
    "mean_call_wall_seconds": means,
    "mean_reduction_percent": 100 * (1 - means["candidate"] / means["control"]),
    "provenance_limit": "Unrelated serial CPU-only benchmarks occurred between the first control and first candidate; the repeated pair ran consecutively.",
    "real_time_qualified": False,
    "production_changed": False,
}
(here / "physical-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["status"] == "pass" else 1)
