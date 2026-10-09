"""Full148 sensitivity report, preserving original DS17 failure provenance."""

import functools
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
    path.write_text(text)


if __name__ == "__main__":
    main()
