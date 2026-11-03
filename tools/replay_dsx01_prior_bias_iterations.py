"""Rebuild the prior-bias comparison exclusively from its frozen source closure."""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "reports/2026_10_18_dsx01_prior_bias_iterations"
FROZEN = CHECKPOINT / "run_sources"


def run():
    sys.path[:0] = [str(FROZEN / "tools"), str(FROZEN / "src")]
    import compare_dsx01_prior_bias_iterations as compare

    for name, module in tuple(sys.modules.items()):
        if name == "__main__" or module is None:
            continue
        for key, value in tuple(vars(module).items()):
            if isinstance(value, Path) and value.is_relative_to(FROZEN):
                setattr(module, key, ROOT / value.relative_to(FROZEN))
    destination = CHECKPOINT / "replay_products"
    destination.mkdir(exist_ok=True)
    shutil.copy2(
        CHECKPOINT / "precision_convergence_checks.json",
        destination / "precision_convergence_checks.json",
    )
    compare.OUTPUT = destination
    for case in compare.CASES:
        compare.run(case)
    import report_dsx01_prior_bias_iterations as report

    report.run()
    print(json.dumps(dict(frozen_sources_only=True, output=str(destination))), flush=True)


if __name__ == "__main__":
    run()
