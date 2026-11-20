"""Score early withholding and later publication on sealed disjoint-offer attempts."""

import argparse
import gzip
from pathlib import Path

from .. import figure_books
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS
from ..variants import final_region
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .sequential_fix_omitted import REPORT
from .sequential_fix_results import (
    LOCK,
    POSITIONS,
    omitted_clearance,
    outcome,
    roof_references,
    score_arm,
    sealed,
    unpublished,
)
from .sequential_fix_timing import service_metrics

FIGURE_LOCK = "omitted-figure-lock.json"
QUERIES = "queries.json"
METHOD = "sequential_fix_omitted"


def publish(report, *, interior_guard=False):
    plan, groups, decisions = sealed(report)
    refs = roof_references(plan["cases"].keys())
    scores, query, predictions, stages = [], [], [], []
    for (ident, offer, _), results in groups.items():
        first, current, complete = results
        truth = refs[ident]["truth"]
        geometry = plan["offers"][ident]
        tile = geometry["shifted"]
        if any(r["tile"] != tile for r in results):
            raise ValueError("the measured compact request used the wrong offer")
        clearance = omitted_clearance(tile, truth)
        if clearance <= 0 or omitted_clearance(dict(geometry["original"], width_km=25), truth) > 0:
            raise ValueError("scorer could not confirm omission and original containment")
        released = decisions[(ident, offer)]["released"]
        chosen = final_region.select(current, complete, released=released, enabled=interior_guard)
        full = (
            chosen
            if not released
            else final_region.select(current, complete, released=False, enabled=interior_guard)
        )
        early = (
            chosen["result"] if released else unpublished(current["result"], "255 s gate rejected")
        )
        versions = (
            ("compact_210", first, first["result"]),
            ("compact_255", current, current["result"]),
            ("early_gate", current, early),
            ("full_compact", full, full["result"]),
            (METHOD, chosen, chosen["result"]),
        )
        for method, row, result in versions:
            predictions.append(outcome(row, method, result=result))
            for arm in ARMS:
                score = score_arm(ident, offer, method, arm, result, refs[ident], released)
                scores.append(
                    dict(
                        score,
                        truth_outside_km=clearance,
                        false_publication=(result["arms"][arm]["latlon"] is not None)
                        if method in ("early_gate", "full_compact", METHOD)
                        else None,
                    )
                )
        for row in results:
            metrics = service_metrics(row)
            if (
                metrics["memory_peak_mib"] is None
                or metrics["memory_peak_mib"] > 512
                or metrics["swap_peak_bytes"] != 0
            ):
                raise ValueError("missing paired position resource receipt")
            stages.append(dict(id=ident, checkpoint=row["checkpoint"], **metrics))
        query.append(
            dict(
                id=ident,
                recording=ident,
                condition="omitted",
                truth=truth,
                bindings={
                    k: predictions[-1][k] for k in ("native_sha256", "catalog_sha256", "tile")
                },
            )
        )

    save_json(report / QUERIES, dict(queries=query))
    write(
        report / POSITIONS,
        gzip.compress(b"".join(encoded(r) + b"\n" for r in predictions), mtime=0),
    )
    csv_file(report / "scores.csv", scores)
    csv_file(report / "position-stages.csv", stages)
    provenance = (LOCK, "scores.csv", "position-stages.csv")
    save_json(
        report / FIGURE_LOCK,
        dict(
            cases=sorted(r["id"] for r in query),
            files={f: _sha(report / f) for f in (*provenance, QUERIES, POSITIONS)},
        ),
    )
    save_json(
        report / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="sequential-fix-omitted",
                    method=METHOD,
                    scope="transfer",
                    cases="sealed",
                    seal=FIGURE_LOCK,
                    provenance=provenance,
                    queries=QUERIES,
                    condition_labels={"omitted": "Disjoint offer, 30 km east"},
                    title="Early and fallback positions in a verified omitted square",
                    caption=(
                        "The two anchors kept their capture and causal candidate catalogue. "
                        "The supplied 25 km square moved 30 km east, leaving a 5 km gap."
                    ),
                    series=[
                        dict(
                            file=POSITIONS,
                            key="candidate",
                            value=METHOD,
                            label="Release or full fallback",
                        ),
                        dict(
                            file=POSITIONS,
                            key="stock",
                            value="full_compact",
                            label="Complete compact",
                        ),
                        dict(
                            file=POSITIONS,
                            key="one",
                            value="early_gate",
                            label="255 s gate alone",
                            forced_label="255 s constrained diagnostic",
                        ),
                    ],
                )
            ],
        ),
    )
    figure_books.generate(report / "charts", ARMS, panel="screening", evidence=report)
    names = (*provenance, QUERIES, POSITIONS, FIGURE_LOCK, "figures.json", "charts/manifest.json")
    save_json(
        report / "score-lock.json",
        dict(
            files={f: _sha(report / f) for f in names},
            source_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--report", type=local_output, default=REPORT)
    cli.add_argument("--interior-guard", action="store_true")
    args = cli.parse_args()
    if args.interior_guard and args.report == REPORT:
        cli.error("--interior-guard needs a separate --report with copies of the sealed inputs")
    publish(args.report, interior_guard=args.interior_guard)
