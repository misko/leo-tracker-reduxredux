"""Score one causal track builder against identical native factors and Graph."""

import gzip
import json
from collections import Counter
from pathlib import Path

from ..__main__ import save_json
from ..scoring import ARMS, distance_km, distribution
from .alias_attribution_results import arms, owners
from .epoch_tracks_trial import BAND, CASES, REPORT, STRIDE
from .factor_cross_results import checked_result
from .factor_cross_trial import write_members
from .full_held_scores import held_references
from .input_factor_bridge import REPO, _sha, check, read
from .input_factor_comparison import ledger, sealed
from .peak_support_results import systemd_runtime
from .prefix_figures import csv_file

CANDIDATE = "causal_epoch_tracks"
CONTROL = "same_factors_graph"


def archived():
    result = {}
    for folder, method, cohort in (
        (BAND, "regional_wide_full_iq", CASES[0]),
        (STRIDE, "wide-cfo-stride_control", CASES[1]),
    ):
        sealed(folder, "prediction-lock.json")
        with gzip.open(folder / "positions.jsonl.gz", "rt") as source:
            for row in map(json.loads, source):
                if row["id"] in cohort and row["method"] == method:
                    result[row["id"]] = row
    return result


def compare_tracks(first, second):
    stocks, candidates = owners(first), owners(second)
    overlaps = []
    for track in second["tracks"]:
        shared = [stocks[i][0] for i in track["ids"] if i in stocks]
        if shared:
            overlaps.append(Counter(shared).most_common(1)[0][1] / len(shared))
    return dict(
        points_in_both=len(stocks.keys() & candidates.keys()),
        stock_only=len(stocks.keys() - candidates.keys()),
        epoch_only=len(candidates.keys() - stocks.keys()),
        epoch_track_dominant_stock_fraction=distribution(overlaps),
        stock_span_s=distribution([t["times_s"][-1] - t["times_s"][0] for t in first["tracks"]]),
        epoch_span_s=distribution([t["times_s"][-1] - t["times_s"][0] for t in second["tracks"]]),
    )


def publish():
    pin = sealed(REPORT, "prediction-lock.json")
    plan = read(REPORT / "plan.json")
    for path, value in plan["sources"].items():
        check(REPO / path, value)
    measured = ledger(REPORT / "results.jsonl.gz")
    if set(measured) != set(pin["cases"]):
        raise ValueError("the terminal replay roster differs from the prediction receipt")
    for job in plan["inputs"]:
        if job["id"] in measured:
            checked_result(measured[job["id"]], job, plan)
    ids = [i for batch in CASES for i in batch]
    archive = archived()
    truth = {r["id"]: r["truth"] for r in held_references("", ids)[1]}
    position, metrics, trace, counts = [], [], {}, Counter()
    for ident in ids:
        gs = measured.get(ident + "-graph")
        ep = measured.get(ident + "-epoch")
        stock = archive[ident]
        cam = plan["authorities"][ident]
        if stock["native_sha256"] != cam["native_sha256"]:
            raise ValueError("archived Graph and substitute used different wide factors")
        if gs is not None:
            counts["fresh_stock_exact"] += gs["result"]["status"] == "ok" and arms(
                gs["result"]
            ) == arms(stock["result"])
            stock_result = gs["result"]
        else:
            stock_result = stock["result"]
        if ep and gs and ep["tracks"] and gs["tracks"]:
            if ep["track-stage"]["observations"] != gs["track-stage"]["observations"]:
                raise ValueError("candidate changed the stock accepted native winners")
            trace[ident] = compare_tracks(gs["tracks"], ep["tracks"])
        if ep is not None:
            candidate_result = ep["result"]
        else:
            candidate_result = dict(
                status="missing",
                reason="No terminal substitute worker receipt",
                boundary="Stored native wide factors through the unchanged phase-release solver",
                metrics={"position_attempted": False},
            )
        counts[f"epoch_{candidate_result['status']}"] += 1
        counts[f"graph_{stock_result['status']}"] += 1
        for method, result, run in ((CONTROL, stock_result, gs), (CANDIDATE, candidate_result, ep)):
            position.append(
                dict(
                    id=ident,
                    method=method,
                    tile=stock["tile"],
                    native_sha256=cam["native_sha256"],
                    origin_native_sha256=cam["origin_native_sha256"],
                    catalog_sha256=stock["catalog_sha256"],
                    result=result,
                )
            )
            stage = run["track-stage"] if run and run["track-stage"] else {}
            for arm in ARMS:
                finish = result.get("arms", {}).get(arm, {})
                error = distance_km(finish.get("latlon"), truth[ident])
                base = distance_km(
                    stock_result.get("arms", {}).get(arm, {}).get("latlon"), truth[ident]
                )
                resource = run["runtime"]["finish"] if run else []
                metrics.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        status=result["status"],
                        geo_error_km=error,
                        graph_geo_error_km=base,
                        within_10pct_graph=error is not None
                        and base is not None
                        and error <= base * 1.10,
                        conditional_rms_hz=finish.get("rf_rms_hz"),
                        observations=stage.get(
                            "observations", result["metrics"].get("observations")
                        ),
                        tracks=stage.get("tracks", result["metrics"].get("tracks")),
                        curved_tracks=stage.get("curved"),
                        owned_track_points=stage.get("points"),
                        stage_cpu_s=stage.get("cpu_s"),
                        stage_wall_s=stage.get("wall_s"),
                        ambiguous_links=stage.get("ambiguous_probes"),
                        cgroup_cpu_s=resource[0]["cgroup_cpu_s"] if resource else None,
                        cgroup_peak_bytes=resource[0]["cgroup_peak"] if resource else None,
                        systemd_runtime_s=systemd_runtime(run["diagnostics"]) if run else None,
                        source="fresh identical factor service"
                        if run
                        else "sealed wide Graph position",
                    )
                )
    save_json(
        REPORT / "summary.json",
        dict(
            cases=ids,
            outcomes=dict(counts),
            fresh_attempts_by_id=sorted(measured),
            same_factor_track_diagnostics=trace,
        ),
    )
    csv_file(REPORT / "scores.csv", metrics)
    write_members(REPORT / "figure-positions.jsonl.gz", position)
    save_json(
        REPORT / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="causal-epoch-tracks",
                    method=CANDIDATE,
                    scope="roof",
                    cases=ids,
                    title="Causal epoch-and-CFO tracks through phase-release",
                    caption=(
                        "Both builders consume exactly the same four-start wide factors. "
                        "Diagnostic Graph controls are fresh. Confirmations use "
                        "sealed wide controls. The chart includes original capture-era v5."
                    ),
                    seal="figure-lock.json",
                    provenance=["scores.csv", "summary.json", "prediction-lock.json"],
                    series=[
                        dict(
                            key=key,
                            label=title,
                            value=method,
                            file="figure-positions.jsonl.gz",
                            native_authority="frozen",
                            native_field="origin_native_sha256",
                            **(
                                {"match": ["native_sha256", "tile", "catalog_sha256"]}
                                if key == "stock"
                                else {}
                            ),
                        )
                        for key, title, method in (
                            ("one", "Causal epoch and folded-CFO tracks", CANDIDATE),
                            ("stock", "Graph on identical wide factors", CONTROL),
                        )
                    ],
                )
            ],
        ),
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=ids,
            score_source_sha256=_sha(Path(__file__)),
            files={
                n: _sha(REPORT / n)
                for n in (
                    "summary.json",
                    "scores.csv",
                    "figure-positions.jsonl.gz",
                    "prediction-lock.json",
                )
            },
        ),
    )


if __name__ == "__main__":
    publish()
