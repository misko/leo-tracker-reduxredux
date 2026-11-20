"""Release region decisions and separate position evidence from sealed predictions."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..__main__ import ROOT, save_json
from ..scoring import distance_km, distribution, validate_result
from ..variants import site_region_set as model
from . import site_region_set_trial as trial
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .prefix_figures import csv_file

OUT = trial.OUT
CANDIDATE, BASELINE = trial.METHODS
METHODS = (CANDIDATE, BASELINE, "shuffled_held", "geometric_medoid")
MATCH = ("input_sha256", "sample_sha256", "catalogue_sha256")
PLOT = "region-evidence.png"
RETRY = "recovery-attempts.jsonl.gz"
STAGE_CSV = "region-figure-data.csv"
DECISION_BARS = (
    ("correct_region", "Correct region", "#126683"),
    ("correct_none", "Correct none", "#daa65f"),
    ("wrong_decision", "Wrong decision", "#a62639"),
    ("withheld_or_failed", "Withheld or failed", "#b3b7c0"),
)
GROUPS = {
    "near-present": "Near rivals · containing",
    "near-omitted": "Near rivals · omitted",
    "far-present": "Far rivals · containing",
    "far-omitted": "Far rivals · omitted",
}


def checked():
    lock = trial.prior.read(OUT / "prediction-lock.json")
    for name, expected in lock["files"].items():
        trial.prior.authority._read(OUT / name, expected)
    for path, expected in trial.prior.read(OUT / "source-lock.json").items():
        trial.prior.authority._read(ROOT / path, expected)
    plan = trial.prior.read(OUT / "blind-plan.json")
    with gzip.open(OUT / trial.ARCHIVE, "rt") as archive:
        rows = [json.loads(line) for line in archive]
    known = {(r["id"], r["method"]): r for r in rows}
    if len(rows) != lock["calls"] or len(known) != len(rows) or len(rows) != len(plan["rows"]):
        raise ValueError("incomplete region set prediction roster")
    for planned in plan["rows"]:
        actual = known[planned["id"], planned["method"]]
        if any(actual[k] != value for k, value in planned.items()):
            raise ValueError("prediction binding differs from the planned request")
    return plan, known


def recover(raw, known):
    """Replay the same packet once for each execution failure in the sealed first pass."""
    jobs = {
        (r["id"], r["method"]): (r, packet)
        for r, packet in trial.cases(raw)
        if known[r["id"], r["method"]]["status"] != "done"
    }
    recovered = []
    for key, (binding, packet) in jobs.items():
        failed = known[key]
        if any(failed[k] != v for k, v in binding.items()):
            raise ValueError("recovery would change the originally scheduled packet")
        recovered.append(trial.run_one(failed["cpu"], binding, packet))
    selected = pack(OUT, RETRY, recovered)
    save_json(
        OUT / "recovery-lock.json",
        dict(
            files={
                RETRY: selected,
                "prediction-lock.json": trial.digest((OUT / "prediction-lock.json").read_bytes()),
            },
            calls=len(recovered),
            cap_s=trial.CAP,
        ),
    )


def recovery(known):
    lock_path = OUT / "recovery-lock.json"
    if not lock_path.is_file():
        return {}
    lock = trial.prior.read(lock_path)
    for name, expected in lock["files"].items():
        trial.prior.authority._read(OUT / name, expected)
    with gzip.open(OUT / RETRY, "rt") as archive:
        rows = [json.loads(line) for line in archive]
    matched = {(r["id"], r["method"]): r for r in rows}
    if len(matched) != len(rows) or len(matched) != lock["calls"]:
        raise ValueError("recovery archive must contain a single retry per attempted packet")
    if matched.keys() != {k for k, row in known.items() if row["status"] != "done"}:
        raise ValueError("recovery attempt roster differs from original execution failures")
    for key, row in matched.items():
        failed = known[key]
        if row["cpu"] != failed["cpu"] or any(row[k] != failed[k] for k in MATCH):
            raise ValueError("recovery does not match the original evidence or CPU")
    return matched


def geo(point, offer):
    frame = ecef_to_enu_matrix(*offer["center"])
    up = ecef_to_enu_matrix(*point)[2]
    delta = geodetic_to_ecef_km(*point, 0) - geodetic_to_ecef_km(*offer["center"], 0)
    tangent = delta - up * ((frame[2] @ delta) / (frame[2] @ up))
    excess = np.maximum(abs(frame[:2] @ tangent) - 12.5, 0)
    return float(np.linalg.norm(excess))


def truth_join(plan, known):
    source = trial.prior.authority._read(
        trial.STUDY / "field_private/truth.json", plan["truth_sha256"]
    )
    survey = {r["id"]: r["latlon"] for r in json.loads(source)["cases"]}
    panels = []
    for (ident, method), row in known.items():
        if method != CANDIDATE:
            continue
        truth = (
            survey[row["original_case"]] if row["cohort"] == "physical" else list(trial.SIM_TRUTH)
        )
        containing, wrong = [], []
        for offer in row["offers"]:
            if roi_margin(truth, offer) >= 0:
                containing.append(offer["id"])
            else:
                wrong.append(geo(truth, offer))
        tier = row["tier"]
        panels.append(
            dict(
                id=ident,
                site=row["site"],
                cohort=row["cohort"],
                tier=tier,
                trial=row["trial"],
                slide=row["slide"],
                containing=containing,
                condition=f"{tier}-{'present' if containing else 'omitted'}",
                nearest_wrong_km=min(wrong),
                truth=truth,
            )
        )
    return panels


def calibration(panels, known, metric, excluded=None):
    groups = {}
    for p in panels:
        site = p["site"]
        if p["cohort"] != "physical" or site == excluded:
            continue
        present, wrong = groups.setdefault(site, ([], []))
        row = known[p["id"], CANDIDATE]
        if row["status"] != "done":
            return None
        top, _ = model.rankings(row["raw"]["offers"], metric)
        if top is None:
            continue
        if p["containing"]:
            present.append(top[metric])
        if top["id"] not in p["containing"]:
            wrong.append(top[metric])
    return model.fold(groups)


def medoid(offers):
    ranks = [(corner_sum(a, offers), a) for a in offers]
    best = min(value for value, _ in ranks)
    tied = [offer for value, offer in ranks if value <= best + 1e-8]
    return min(tied, key=lambda offer: offer["id"])


def corner_sum(corner, offers):
    return sum(distance_km(corner["center"], other["center"]) for other in offers)


def outcome(row, method, fold_data):
    if method == "geometric_medoid":
        typical = medoid(row["offers"])
        return dict(
            region_decision="withheld",
            forced=typical["id"],
            forced_point=typical["center"],
            reason="geometry_only",
        )
    if row["status"] != "done":
        return dict(region_decision=row["status"], reason=row["reason"])
    if method == BASELINE:
        raw = row["raw"]
        diagnostics = raw["diagnostics"]
        verify = diagnostics["region_result"]
        forced = raw["best_region"]
        fixed = diagnostics.get("held_evidence", {})
        rms = diagnostics.get("regional_scores", {}).get(forced, {}).get("held")
        return dict(
            region_decision="region" if verify["status"] == "accepted" else "withheld",
            region=verify["region_id"],
            forced=forced,
            forced_point=raw["best_latlon"],
            point=raw["latlon"],
            reason=verify["reason"],
            point_reason=raw["reason"],
            margin=fixed.get("region_lead"),
            specificity_margin=fixed.get("null_lead"),
            held_rms_hz=rms["rms_hz"] if rms is not None else None,
            held_similarity=fixed.get("score"),
            work=sum(diagnostics["work"].values()),
        )
    offers = row["raw"]["offers"]
    metric = "sham" if method == "shuffled_held" else "held"
    decision = model.decide(offers, fold_data, metric=metric)
    top = next((o for o in offers if o["id"] == decision["forced"]), {})
    ids = {o["id"] for o in row["offers"]}
    if (ids != {o["id"] for o in offers} and offers) or len(ids) != model.OFFER_COUNT:
        raise ValueError("prediction does not represent every offered square")
    point = top.get("point", {})
    return dict(
        decision,
        forced_point=top.get("latlon"),
        held_rms_hz=top.get("held_rms_hz") if metric == "held" else None,
        point_reason=point.get("reason") if metric == "held" else "held_shuffle_control",
        local_ring_lead=point.get("ring_lead"),
        span_km=point.get("split_span_km"),
        disjoint_orbits=point.get("independent_orbits_per_half"),
        work=sum(o["training_sites"] for o in offers)
        + sum(o["point"].get("evaluated_sites", 0) for o in offers),
    )


def as_position(result, method):
    forced, point = result.get("forced_point"), result.get("point")
    state = result["region_decision"]
    metrics = dict(
        position_attempted=forced is not None,
        region_decision=state,
        point_reason=result.get("point_reason"),
    )
    if forced is None and state in ("region", "none", "withheld"):
        metrics["terminal_position_decision"] = True
    status = (
        "ok" if point is not None else (state if state in ("failed", "timed_out") else "withheld")
    )
    value = dict(
        status=status,
        boundary={
            CANDIDATE: "Four offered squares and alternating held Doppler blocks",
            BASELINE: "Frozen early and late whole-track estimator on the same panel",
            "geometric_medoid": "Diagnostic centre of the geometric medoid offer",
            "shuffled_held": "Circularly shuffled held frequency at the fixed nominees",
        }[method],
        reason=None if point is not None else result.get("point_reason") or result["reason"],
        metrics=metrics,
        arms=dict(
            c0=dict(latlon=point, forced_latlon=forced, rf_rms_hz=result.get("held_rms_hz")),
            fitted_c=dict(
                status="unavailable",
                reason="single_RF_per_arc_intercept_gauge",
                latlon=None,
                forced_latlon=None,
            ),
        ),
    )
    validate_result(value)
    return value


def score(panels, known):
    folds = {
        (site, metric): calibration(panels, known, metric, excluded=site)
        for site in {p["site"] for p in panels}
        for metric in ("held", "sham")
    }
    table, chart_rows, queries = [], [], []
    conditions = defaultdict(set)
    for panel in panels:
        ident, cohort, site = (panel[k] for k in ("id", "cohort", "site"))
        measured = known[ident, CANDIDATE]
        by_id = {o["id"]: o for o in measured["offers"]}
        sums = [corner_sum(o, measured["offers"]) for o in measured["offers"]]
        bindings = {k: measured[k] for k in MATCH}
        conditions[cohort].add(panel["condition"])
        queries.append(
            {k: panel[k] for k in ("id", "condition", "truth")}
            | dict(
                recording=f"{site} / trial {panel['trial'] + 1}", bindings=bindings, cohort=cohort
            )
        )
        for method in METHODS:
            row = known[ident, BASELINE] if method == BASELINE else measured
            if any(row[k] != measured[k] for k in MATCH):
                raise ValueError("candidate and frozen comparator used different receiver inputs")
            metric = "sham" if method == "shuffled_held" else "held"
            result = outcome(row, method, folds[site, metric])
            point = as_position(result, method)
            containing = panel["containing"]
            region_decision = result["region_decision"]
            accepted = result.get("region") in containing if region_decision == "region" else None
            if result.get("point") is not None:
                offer = next(o for o in measured["offers"] if o["id"] == result["region"])
                if roi_margin(result["point"], offer) < -0.01:
                    raise ValueError("a declared fix is outside its selected rectangle")
            timed = method in trial.METHODS
            fields = dict(
                id=ident,
                site=site,
                cohort=cohort,
                method=method,
                trial=panel["trial"] + 1,
                condition=panel["condition"],
                tier=panel["tier"],
                nominal_slide=int(panel["slide"]),
                containing_offers=len(containing),
                nearest_wrong_km=panel["nearest_wrong_km"],
                contains_offer=bool(containing),
                forced_correct=result.get("forced") in containing,
                forced_region=result.get("forced"),
                offered_centre_sum_spread_m=1000 * (max(sums) - min(sums)),
                forced_winner_centre_error_km=distance_km(
                    by_id.get(result.get("forced"), {}).get("center"), panel["truth"]
                ),
                selected_region=result.get("region"),
                region_decision=region_decision,
                region_accepted_correct=accepted,
                position_status=point["status"],
                reason=result["reason"],
                point_reason=result.get("point_reason"),
                forced_error_km=distance_km(result.get("forced_point"), panel["truth"]),
                published_error_km=distance_km(result.get("point"), panel["truth"]),
                best_loss=result.get("best_loss"),
                margin=result.get("margin"),
                specificity_margin=result.get("specificity_margin"),
                held_similarity=result.get("held_similarity"),
                held_rms_hz=result.get("held_rms_hz"),
                p_containing=result.get("p_containing"),
                p_wrong=result.get("p_wrong"),
                point_group_span_km=result.get("span_km"),
                point_independent_orbits_per_group=result.get("disjoint_orbits"),
                held_local_ring_lead=result.get("local_ring_lead"),
                search_work=result.get("work"),
                elapsed_s=row.get("elapsed_s") if timed else None,
                worker_wall_s=row.get("worker_wall_s") if timed else None,
                cpu_s=row.get("cpu_s") if timed else None,
                rss_kib=row.get("rss_kib") if timed else None,
            )
            table.append(fields)
            chart_rows.append(
                dict(id=ident, method=method, cohort=cohort, result=point, **bindings)
            )
    return table, chart_rows, queries, conditions, folds


def ablation(known):
    audits = []
    for (ident, method), shifted in known.items():
        if method != "c_invariance":
            continue
        original = known[ident, CANDIDATE]
        after = {o["id"]: o for o in shifted.get("raw", {}).get("offers", [])}
        before = {o["id"]: o for o in original.get("raw", {}).get("offers", [])}
        row = dict(
            site=original["site"],
            id=ident,
            base=original["status"],
            perturb=shifted["status"],
            compared_offers=0,
            max_held_loss_change=None,
            max_held_rms_change_hz=None,
            max_forced_coordinate_change_km=None,
        )
        if before and after and before.keys() == after.keys():
            keys = before.keys()
            row.update(
                compared_offers=len(keys),
                max_held_loss_change=max(abs(before[k]["held"] - after[k]["held"]) for k in keys),
                max_held_rms_change_hz=max(
                    (
                        abs(before[k]["held_rms_hz"] - after[k]["held_rms_hz"])
                        for k in keys
                        if before[k]["held_rms_hz"] is not None
                        and after[k]["held_rms_hz"] is not None
                    ),
                    default=None,
                ),
                max_forced_coordinate_change_km=max(
                    distance_km(before[k]["latlon"], after[k]["latlon"]) for k in keys
                ),
            )
        audits.append(row)
    return audits


def summarize(sample):
    decisions = Counter(row["region_decision"] for row in sample)
    return dict(
        scheduled=len(sample),
        containing=sum(r["contains_offer"] for r in sample),
        forced_correct=sum(r["forced_correct"] for r in sample),
        forced_with_coordinate=sum(r["forced_error_km"] is not None for r in sample),
        region_decisions=dict(decisions),
        correct_region_accepts=sum(r["region_accepted_correct"] is True for r in sample),
        wrong_region_accepts=sum(r["region_accepted_correct"] is False for r in sample),
        correct_none=sum(
            r["region_decision"] == "none" and not r["contains_offer"] for r in sample
        ),
        wrong_none=sum(r["region_decision"] == "none" and r["contains_offer"] for r in sample),
        point_outcomes=dict(Counter(r["position_status"] for r in sample)),
        **{
            column: distribution(r[column] for r in sample)
            for column in (
                "forced_error_km",
                "published_error_km",
                "held_rms_hz",
                "best_loss",
                "margin",
                "cpu_s",
                "elapsed_s",
                "worker_wall_s",
                "rss_kib",
                "nearest_wrong_km",
                "search_work",
            )
        },
    )


def distributions(rows):
    grouped = defaultdict(list)
    context = {}
    for r in rows:
        cohort, condition, method = (r[k] for k in ("cohort", "condition", "method"))
        grouped[cohort, condition, method].append(r)
        grouped[cohort, "all", method].append(r)
        context[r["id"], method] = r
    totals = [
        dict(cohort=a, condition=b, method=c, **summarize(sample))
        for (a, b, c), sample in sorted(grouped.items())
    ]
    comparisons = []
    for (cohort, condition, method), sample in sorted(grouped.items()):
        if method != CANDIDATE:
            continue
        for other in METHODS[1:]:
            pairs = [(r, context[r["id"], other]) for r in sample]
            comparisons.append(
                dict(
                    cohort=cohort,
                    condition=condition,
                    other=other,
                    scheduled=len(pairs),
                    **{
                        suffix + "_delta_km": distribution(
                            a[column] - b[column]
                            for a, b in pairs
                            if a[column] is not None and b[column] is not None
                        )
                        for suffix, column in (
                            ("forced", "forced_error_km"),
                            ("published", "published_error_km"),
                        )
                    },
                )
            )
    return dict(version=2, totals=totals, paired_comparisons=comparisons)


def pair_scores(panels, rows):
    paired = defaultdict(dict)
    for p in panels:
        paired[p["site"], p["trial"] + 1][p["slide"]] = p["id"]
    known = {(r["id"], r["method"]): r for r in rows}
    output = []
    for (site, number), match in sorted(paired.items()):
        for method in METHODS:
            a, b = (known[match[slide], method] for slide in (False, True))
            nominal = a["contains_offer"] and not b["contains_offer"]
            comparable = a["best_loss"] is not None and b["best_loss"] is not None
            output.append(
                dict(
                    site=site,
                    trial=number,
                    tier=a["tier"],
                    method=method,
                    unreflected_id=a["id"],
                    reflected_id=b["id"],
                    containing_then_omitted=nominal,
                    reflected_minus_unreflected_loss=(
                        b["best_loss"] - a["best_loss"] if comparable else None
                    ),
                    unreflected_decision=a["region_decision"],
                    reflected_decision=b["region_decision"],
                )
            )
    return output


def stage_data(rows):
    panels = [r for r in rows if r["cohort"] == "physical" and r["method"] == CANDIDATE]
    data = [
        dict(
            kind="panel",
            site=r["site"],
            id=r["id"],
            trial=r["trial"],
            tier=r["tier"],
            contains_offer=r["contains_offer"],
            best_loss=r["best_loss"],
            nominal_slide=r["nominal_slide"],
            decision=None,
            count=None,
        )
        for r in panels
    ]
    for site in sorted({r["site"] for r in panels}):
        counts = Counter()
        for r in panels:
            if r["site"] != site:
                continue
            accepted = r["region_accepted_correct"]
            rejected = r["region_decision"] == "none"
            if accepted is True:
                counts["correct_region"] += 1
            elif accepted is False or (rejected and r["contains_offer"]):
                counts["wrong_decision"] += 1
            elif rejected:
                counts["correct_none"] += 1
            else:
                counts["withheld_or_failed"] += 1
        data.extend(
            dict(
                kind="aggregate",
                site=site,
                id=None,
                trial=None,
                tier=None,
                contains_offer=None,
                best_loss=None,
                nominal_slide=None,
                decision=name,
                count=counts[name],
            )
            for name, _, _ in DECISION_BARS
        )
    return data


def plot(data):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    sites = sorted({r["site"] for r in data})
    fig, (loss_ax, decision_ax) = plt.subplots(
        1, 2, figsize=(12.1, 5.5), gridspec_kw=dict(width_ratios=[1.4, 1])
    )
    fig.subplots_adjust(left=0.105, right=0.975, top=0.82, bottom=0.20, wspace=0.13)
    for i, site in enumerate(sites):
        subset = [r for r in data if r["site"] == site and r["kind"] == "panel"]
        for r in subset:
            colour = "#126683" if r["contains_offer"] else "#c86615"
            symbol = "o" if r["trial"] < 3 else "^"
            y = i + (r["trial"] - 2) * 0.18 + (r["nominal_slide"] - 0.5) * 0.11
            if r["best_loss"] is not None:
                loss_ax.scatter(r["best_loss"], y, c=colour, marker=symbol, s=40, alpha=0.9)
        counts = {
            r["decision"]: r["count"]
            for r in data
            if r["site"] == site and r["kind"] == "aggregate"
        }
        start = 0
        for name, label, colour in DECISION_BARS:
            width = counts[name]
            decision_ax.barh(i, width, left=start, height=0.51, color=colour, label=label)
            start += width
    loss_ax.set(
        yticks=range(len(sites)),
        yticklabels=[s.replace("field-site-", "Site ") for s in sites],
        xlabel="Best held loss across four squares",
        xscale="log",
        ylim=(len(sites) - 0.5, -0.5),
        title="Each point is one offered set",
    )
    decision_ax.set(
        yticks=range(len(sites)),
        yticklabels=[],
        xlim=(0, 6),
        xticks=range(7),
        xlabel="Scheduled decisions per site",
        ylim=loss_ax.get_ylim(),
        title="Leave-one-site-out decisions",
    )
    for ax in (loss_ax, decision_ax):
        ax.grid(axis="x", alpha=0.22)
        ax.set_axisbelow(True)
        ax.spines[["right", "top"]].set_visible(False)
    loss_ax.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="", color="#126683", label="Contains receiver"),
            Line2D([], [], marker="o", linestyle="", color="#c86615", label="Receiver omitted"),
            Line2D([], [], marker="^", linestyle="", color="#656970", label="Far rivals"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.145),
        ncol=3,
        frameon=False,
        fontsize=9,
    )
    handles = [Patch(color=color, label=label) for _, label, color in DECISION_BARS]
    decision_ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.145),
        ncol=2,
        frameon=False,
        fontsize=9,
    )
    fig.suptitle(
        "Anonymous Doppler evidence across eight physical StarLoc sites", fontsize=16, y=0.96
    )
    fig.text(0.5, 0.885, "Two near pairs and one far pair per site", ha="center", fontsize=11)
    fig.savefig(OUT / PLOT, dpi=160, facecolor="white")
    plt.close(fig)


def write_figures(chart_rows, queries, conditions, recovered):
    rows_file = "positions.jsonl.gz"
    packed = pack(OUT, rows_file, chart_rows)
    specs = []
    for cohort, labels in conditions.items():
        query_file, lock_file = f"{cohort}-queries.json", f"{cohort}-figure-lock.json"
        selected = [r for r in queries if r["cohort"] == cohort]
        cases = [r["id"] for r in selected]
        save_json(
            OUT / query_file,
            dict(queries=[{k: v for k, v in r.items() if k != "cohort"} for r in selected]),
        )
        names = (query_file, "prediction-lock.json", "score-lock.json")
        files = {name: trial.digest((OUT / name).read_bytes()) for name in names} | {
            rows_file: packed
        }
        save_json(OUT / lock_file, dict(cases=cases, files=files))
        title = (
            "Competing regions on eight StarLoc sites"
            if cohort == "physical"
            else "Competing regions at a simulated Portuguese site"
        )
        caption = (
            "Four offered squares and matching anonymous Doppler samples. "
            "Forced coordinates are diagnostics."
        )
        if recovered:
            caption += " Includes the sealed, identical-packet recovery attempts."
        specs.append(
            dict(
                id=f"site-region-sets-{cohort}",
                scope="transfer",
                method=CANDIDATE,
                title=title,
                caption=caption,
                condition_labels={k: v for k, v in GROUPS.items() if k in labels},
                cases=cases,
                provenance=["prediction-lock.json", "score-lock.json"],
                queries=query_file,
                seal=lock_file,
                series=[
                    dict(
                        key=series,
                        file=rows_file,
                        value=method,
                        label=label,
                        where=dict(cohort=cohort),
                        match=list(MATCH),
                        forced_label=label + " · forced",
                    )
                    for series, method, label in (
                        ("candidate", CANDIDATE, "Doppler shape"),
                        ("stock", BASELINE, "Frozen rerun"),
                        ("one", "shuffled_held", "Held shuffle"),
                        ("four", "geometric_medoid", "Tile medoid"),
                    )
                ],
            )
        )
    save_json(OUT / "figures.json", dict(version=2, charts=specs))


def run(replay=None):
    plan, known = checked()
    if replay is not None:
        recover(replay, known)
    recovered = recovery(known)
    panels = truth_join(plan, known)
    best_available = known | {k: row for k, row in recovered.items() if row["status"] == "done"}
    rows, chart_rows, queries, conditions, folds = score(panels, best_available)
    first, _, _, _, first_folds = score(panels, known)
    csv_file(OUT / "scores.csv", rows)
    csv_file(OUT / "matched-pairs.csv", pair_scores(panels, rows))
    csv_file(OUT / "first-attempt-scores.csv", first)
    csv_file(
        OUT / "execution-attempts.csv",
        [
            {
                k: r.get(k)
                for k in (
                    "id",
                    "site",
                    "cohort",
                    "method",
                    "cpu",
                    "status",
                    "elapsed_s",
                    "worker_wall_s",
                    "cpu_s",
                    "rss_kib",
                )
            }
            | dict(attempt=attempt)
            for attempt, attempts in ((1, known), (2, recovered))
            for r in attempts.values()
        ],
    )
    save_json(OUT / "distributions.json", distributions(rows))
    save_json(OUT / "first-attempt-distributions.json", distributions(first))
    save_json(
        OUT / "folds-and-calibration.json",
        dict(
            folds=[
                dict(site=site, score=metric, envelopes=calibration)
                for (site, metric), calibration in sorted(folds.items())
            ],
            raw_first_attempt_folds=[
                dict(site=site, score=metric, envelopes=calibration)
                for (site, metric), calibration in sorted(first_folds.items())
            ],
            ablation=ablation(best_available),
            minimum_physical_calibration_rank=1 / 8,
        ),
    )
    evidence = stage_data(rows)
    csv_file(OUT / STAGE_CSV, evidence)
    plot(evidence)
    save_json(
        OUT / "stage-figure.json",
        dict(
            version=1,
            id="site-region-set-evidence",
            title="Held Doppler loss and decisions across eight StarLoc sites",
            sample="Three paired four-offer sets at each physical site.",
            boundary="Held Doppler blocks, anonymous tracks and causal orbit snapshots.",
            note="Lower held loss is stronger. Region and position decisions are separate.",
            seal="score-lock.json",
            image=PLOT,
            csv=STAGE_CSV,
        ),
    )
    artifacts = (
        "scores.csv",
        "matched-pairs.csv",
        "first-attempt-scores.csv",
        "first-attempt-distributions.json",
        "execution-attempts.csv",
        "distributions.json",
        "folds-and-calibration.json",
        STAGE_CSV,
        PLOT,
        "stage-figure.json",
        "prediction-lock.json",
    ) + (("recovery-lock.json",) if recovered else ())
    save_json(
        OUT / "score-lock.json",
        dict(
            files={name: trial.digest((OUT / name).read_bytes()) for name in artifacts},
            scorer_sha256=trial.digest(Path(__file__).read_bytes()),
            panels=len(panels),
            rows=len(rows),
            truth_sha256=plan["truth_sha256"],
        ),
    )
    write_figures(chart_rows, queries, conditions, recovered)
    print(f"{len(panels)} panels and {len(rows)} score rows at {OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path)
    run(parser.parse_args().replay)
