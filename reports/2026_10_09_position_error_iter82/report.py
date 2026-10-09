"""Full148 sensitivity report, preserving original DS17 failure provenance."""

import functools
import json
import runpy
import sys
from pathlib import Path

from receipt_loader import merged_result

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / "2026_10_09_position_error_iter78"


def main():
    sys.path.insert(0, str(ORIGINAL))
    namespace = runpy.run_path(str(ORIGINAL / "report.py"), run_name="merged_report")
    report = namespace["main"]
    report.__globals__["HERE"] = HERE
    report.__globals__["load_result"] = functools.partial(
        merged_result, original_dir=ORIGINAL, retry_dir=HERE
    )
    report(ORIGINAL / "protocol.json")
    path = HERE / "RESULTS.md"
    text = path.read_text().replace(
        "# Iteration78 sensitivity results",
        "# Iterations78/82: full-membership sensitivity comparison",
    )
    text += (
        "\n## Input retry provenance\n\n"
        "All 51 DS17 original input failures remain archived. The separately frozen "
        "iteration82 retries correct only protocol metadata loading. The coverage "
        "entries in summary.json record original status/error and both receipt paths. "
        "Pending or failed retries are not silently excluded from membership. "
        "No production changes or independent-validation claims.\n"
    )
    summary = json.loads((HERE / "summary.json").read_text())
    lines = ["", "## Paired comparisons on available membership", "",
             "| Dataset | Arm | Baseline mean km | .25 mean km | .125 mean km | .5 mean km | "
             ".5 improved/regressed/tied versus .25 |",
             "|---|---|---:|---:|---:|---:|---|"]
    def number(value):
        return "pending" if value is None else f"{value:.6f}"
    for name in ("DS16", "DS17", "DS18", "Pooled"):
        for arm in ("fitted-c", "zero-c"):
            row = summary["groups"][name]["arms"][arm]
            variants = row["variants"]
            comparison = variants["0.5"]["versus_new_control"]
            means = [row["baseline_matched"]["mean"]] + [
                variants[s]["position"]["mean"] for s in ("0.25", "0.125", "0.5")
            ]
            lines.append(
                f"| {name} | {arm} | " + " | ".join(number(v) for v in means)
                + f" | {comparison['improved']}/{comparison['regressed']}/{comparison['tied']} |"
            )
    lines += ["", "Sigma here is the satellite-specific slope prior in Hz/s, not timing sigma "
              "or the receiver hard60 bound. c=0 also locks the RF-time terms; other observations, "
              "banks, seeds and budgets are matched. These are conditional ablations sharing "
              "fitted-derived banks and seeds, not independent c-specific search pipelines."]
    text += "\n".join(lines) + "\n"
    path.write_text(text)


if __name__ == "__main__":
    main()
