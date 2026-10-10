"""Reuse136 reporting explicitly at138 paths; retain failed predecessor costs."""

import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
API = runpy.run_path(str(HERE.parent / "2026_10_10_position_error_iter136/report.py"))


def prepare(here=HERE, root=ROOT):
    plan, receipts, hashes = API["load"](here, root)
    result = API["summarize"](plan, receipts)
    lineage = plan["predecessor_failures"]
    if len(lineage) != 12 or {x["label"] for x in lineage} != {x["label"] for x in plan["members"]}:
        raise ValueError("predecessor coverage changed")
    predecessor_cost = sum(x["elapsed_s"] for x in lineage)
    result.update(
        protocol_sha256=API["sha"](here / "protocol.json"),
        raw_sha256=hashes,
        predecessor_failures=lineage,
        predecessor_elapsed_s=predecessor_cost,
        lineage_elapsed_s=result["runtime_s"] + predecessor_cost,
    )
    return result


def main():
    result = prepare(HERE, ROOT)
    text = API["markdown"](result)
    text += (
        "\n## Explicit successor lineage\n\n"
        "Iteration 136 failed for all twelve members before model reconstruction because "
        "of an import-name collision. Those failures were not overwritten. Iteration 138 "
        "changes only import isolation and result paths; the audit mathematics and "
        "membership are unchanged.\n\n"
        f"Original failed-run elapsed time: {result['predecessor_elapsed_s']:.6f} seconds. "
        f"Combined predecessor and successor elapsed time: {result['lineage_elapsed_s']:.6f} "
        "seconds. Source-bound predecessor receipt paths and costs are in `summary.json`.\n"
    )
    (HERE / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    (HERE / "RESULTS.md").write_text(text)
    if result["complete"]:
        API["plot"](result, HERE / "conditional-scores.png")


if __name__ == "__main__":
    main()
