"""Post-hoc multi-start diagnostics from immutable training results."""
# ruff: noqa: E501 -- Markdown prose and tables.

import math
import sys

from study import HERE, read, save, verify


def main(arm):
    verify(read(HERE / "input-seal.json")["sha256"])
    rows = []
    for unit in read(HERE / "plan.json")["units"]:
        if unit["arm"] != arm:
            continue
        parent = HERE / "runs" / unit["unit_id"]
        selection = read(parent / "selection.json")
        for start in unit["starts"]:
            verify(read(parent / "fit" / start["source_dataset"] / "seal.json")["sha256"])
        chosen = selection["selected"]
        alternatives = []
        for r in selection["runs"]:
            if not r or not r["qualified"] or not chosen:
                continue
            alternatives.append(
                {
                    "start": r["start_id"],
                    "training_score_gap": chosen["training_log_score"] - r["training_log_score"],
                    "horizontal_separation_km": math.hypot(
                        r["x"][0] - chosen["x"][0], r["x"][1] - chosen["x"][1]
                    ),
                    "x": r["x"],
                }
            )
        rows.append(
            {
                "unit": unit["unit_id"],
                "selected_start": chosen["start_id"] if chosen else None,
                "alternatives": alternatives,
            }
        )
    assert len(rows) == 18
    save(HERE / f"start-diagnostics-{arm}.json", {"rows": rows})
    lines = [
        "# Training-start ambiguity",
        "",
        "All four predeclared starts are retained. Separations below are horizontal E/N coordinate differences from the training-selected fit. "
        "They are optimizer diagnostics, not confidence intervals. A small score gap between separated solutions is a reason to avoid a precision claim; "
        "agreement of these four starts does not prove global uniqueness.",
        "",
        "| Unit | Selected start | Qualified starts | Farthest qualified start (km) | Its training score deficit (nats) |",
        "|---|---|---:|---:|---:|",
    ]
    for row in rows:
        far = max(row["alternatives"], key=lambda r: r["horizontal_separation_km"], default=None)
        if far:
            lines.append(
                f"| {row['unit']} | {row['selected_start']} | {len(row['alternatives'])}/4 | {far['horizontal_separation_km']:.6f} | {far['training_score_gap']:.6f} |"
            )
        else:
            lines.append(f"| {row['unit']} | None | 0/4 | — | — |")
    lines += [
        "",
        f"[All start coordinates and training score gaps](start-diagnostics-{arm}.json).",
        "",
    ]
    with (HERE / f"STARTS-{arm}.md").open("x") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])
