"""Score anonymous carrier transfer and its measured identifiability ceiling."""

import gzip
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np

from ..__main__ import save_json
from ..scoring import ARMS, arm_outcome, distance_km
from . import beacon_transfer_trial as trial
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .prefix_figures import csv_file

OUT, prior, model = trial.OUT, trial.prior, trial.model
PREFIX = "beacon_transfer_"
PLOT = "beacon-transfer-support.png"
METRICS = (
    "nominal_matches",
    "target_level_rank",
    "carried_norads",
    "target_offset_hz",
    "same_endpoint_free_held_hz",
    "anchor_permutation_held_rms_hz",
    "same_endpoint_permutation_held_rms_hz",
    "held_rms_hz",
    "held_region_lead",
    "arcs",
    "training_cost",
    "held_cost",
)
CONDITIONS = ("containing", "near-missing", "far-missing")


def locked():
    permit = prior.read(OUT / "prediction-lock.json")
    for n, v in permit["files"].items():
        if prior.digest((OUT / n).read_bytes()) != v:
            raise ValueError("changed prediction authority")
    plan = prior.read(OUT / "blind-plan.json")
    with gzip.open(OUT / trial.ARCHIVE, "rt") as f:
        rows = {(r["id"], r["method"]): r for r in map(json.loads, f)}
    expected = {(q["id"], PREFIX + m) for q in plan["cases"] for m in model.METHODS}
    if rows.keys() != expected or len(plan["cases"]) != permit["calls"]:
        raise ValueError("incomplete nominal and negative-control roster")
    for p in plan["cases"]:
        for m in model.METHODS:
            r = rows[p["id"], PREFIX + m]
            if any(r[k] != v for k, v in p.items()):
                raise ValueError("a solver saw a different offer or data")
            orig = p["recording"] + "-containing"
            if any(r[k] != rows[orig, PREFIX + m][k] for k in trial.BIND if k != "input_sha256"):
                raise ValueError("the omitted squares altered radio, time or donor inputs")
    return rows, permit, plan


def raw_graph(ledger):
    return model.graph(
        {row["id"]: [r | {"wrapped_level_hz": 0} for r in row["identity"]] for row in ledger}
    )


def summarise_components(graph):
    return dict(
        components=len(graph),
        capture_nodes=sum(len(r["captures"]) for r in graph),
        satellite_nodes=sum(len(r["levels"]) for r in graph),
        edges=sum(r["edges"] for r in graph),
        cycle_rank=sum(r["cycle_rank"] for r in graph),
        design_rank=sum(r["rank"] for r in graph),
    )


def coverage(graph, ids):
    counts = [len(ids.intersection(row["levels"])) for row in graph]
    return max(counts, default=0)


def topology(ledger):
    by_id = {r["id"]: r for r in ledger}
    shared = defaultdict(list)
    for r in ledger:
        for sat in r["identity"]:
            shared[sat["norad"]].append((r, sat["arc"]))
    observed = []
    for norad, rows in shared.items():
        for (a, ia), (b, ib) in combinations(rows, 2):
            if a["site"] == b["site"]:
                continue
            found = [
                next((x for x in node["label_profiles"] if x["arc"] == i), None)
                for node, i in ((a, ia), (b, ib))
            ]
            raw = found[1]["raw_level_hz"] - found[0]["raw_level_hz"] if all(found) else None
            observed.append(
                dict(
                    norad=norad,
                    first=a["id"],
                    second=b["id"],
                    separation_hours=(b["start_utc_ns"] - a["start_utc_ns"]) / 3.6e12,
                    apparent_level_shift_hz=raw,
                    comb_folded_shift_hz=float(model.fold(raw)) if raw is not None else None,
                    profiles=found,
                )
            )
    ceilings = {}
    for ident, target in by_id.items():
        if not ident.endswith("-first"):
            continue
        ids = {str(r["norad"]) for r in target["identity"]}
        strict = model.partition(ledger, target)
        future = model.partition(ledger, target, strict=False)
        banks, provenance = trial.fit_banks(ledger, target)
        raw_early, raw_all = (coverage(raw_graph(p), ids) for p in (strict, future))
        ceilings[ident] = dict(
            strict_prior_labels=raw_early,
            later_oracle_labels=raw_all,
            strict_identifiable_rank=max(0, raw_early - 1),
            later_identifiable_rank=max(0, raw_all - 1),
            matched_after_gates={k: coverage(v, ids) for k, v in banks.items()},
            donor_counts={k: len(v) for k, v in provenance.items()},
            bank_graphs={k: summarise_components(v) for k, v in banks.items()},
        )
    return dict(
        cross_site_repeated_satellites=observed,
        target_author_ceilings=ceilings,
        raw_graph=summarise_components(raw_graph(ledger)),
        gated_author_graph=summarise_components(
            model.graph({r["id"]: r["author"] for r in ledger})
        ),
        gated_anonymous_graph=summarise_components(
            model.graph({r["id"]: r["anonymous"] for r in ledger})
        ),
    )


def score():
    rows, lock, plan = locked()
    truthfile = prior.authority.STUDY / "field_private/truth.json"
    truth = {
        r["id"]: r["latlon"]
        for r in json.loads(
            prior.authority._read(
                truthfile,
                plan["scoring_truth_sha256"],
            )
        )["cases"]
    }
    ledger = prior.read(OUT / "donor-ledger.json")["captures"]
    audit = topology(ledger)
    ceilings = audit["target_author_ceilings"]
    labels = {row["id"]: {r["arc"]: r["norad"] for r in row["identity"]} for row in ledger}
    table, query, chart = [], defaultdict(list), []
    for q in plan["cases"]:
        ident, mode = q["id"], q["condition"]
        survey = truth[q["original_case"]]
        margin = roi_margin(survey, q["tile"])
        if (margin >= 0) != (mode == "containing"):
            raise ValueError("measured site has inconsistent offered region")
        point = q["tile"]["center"]
        key = q["recording"]
        query[mode].append(
            dict(
                id=ident,
                recording=key,
                truth=survey,
                condition=mode,
                bindings={k: q[k] for k in trial.BIND},
            )
        )
        chart.append(
            q
            | dict(
                method=PREFIX + "centre",
                result=dict(
                    status="ok",
                    reason=None,
                    boundary="Offered square centre",
                    metrics={},
                    arms={a: dict(latlon=point, forced_latlon=None) for a in ARMS},
                ),
            )
        )
        shape = rows[ident, PREFIX + "shape"]["result"]["metrics"].get("selected", [])
        matched = {r["norad"] for r in shape if r["norad"] == labels[key].get(r["arc"])}
        for method in model.METHODS:
            record = rows[ident, PREFIX + method]
            result = record["result"]
            m = result["metrics"]
            presented = result
            if result["status"] == "withheld" and not m["position_attempted"]:
                presented = result | {"metrics": m | {"terminal_position_decision": True}}
            chart.append(record | {"result": presented})
            for arm, endpoint in result["arms"].items():
                numeric = arm == "c0"
                status, reason = arm_outcome(result, endpoint)
                table.append(
                    dict(
                        id=ident,
                        recording=key,
                        site=q["group"],
                        mode=mode,
                        method=method,
                        arm=arm,
                        status=status,
                        reason=reason,
                        truth_signed_margin_km=margin,
                        center_error_km=distance_km(point, survey),
                        forced_error_km=distance_km(endpoint["forced_latlon"], survey),
                        published_error_km=distance_km(endpoint["latlon"], survey),
                        earlier_label_ceiling=ceilings[key]["strict_prior_labels"],
                        later_label_ceiling=ceilings[key]["later_oracle_labels"],
                        author_consistent_carried_norads=len(
                            matched.intersection(m.get("carried_norads", []))
                        )
                        if numeric
                        else None,
                        cpu_s=record["cpu_s"] if numeric else None,
                        elapsed_s=record["elapsed_s"] if numeric else None,
                        rss_kib=record["rss_kib"] if numeric else None,
                        **{k: m.get(k) if numeric else None for k in METRICS},
                    )
                )
    save_json(OUT / "coverage-and-gauges.json", audit)
    save_json(OUT / "scores.json", dict(rows=table))
    csv_file(OUT / "scores.csv", table)
    plot(table, audit)
    save_json(
        OUT / "stage-figure.json",
        dict(
            version=1,
            id="beacon-level-transfer-support",
            title="Beacon identity coverage and receiver offset gauge",
            sample="Eight complete held physical sites from eleven measured StarLoc captures.",
            boundary="Earlier survey donor levels with one anonymous target receiver offset.",
            note="A lone donor beacon supplies no transferable between-beacon frequency contrast.",
            seal="score-lock.json",
            image=PLOT,
            csv="scores.csv",
        ),
    )
    artifacts = (
        "coverage-and-gauges.json",
        "scores.csv",
        "scores.json",
        PLOT,
        "stage-figure.json",
        "prediction-lock.json",
    )
    files = lock["files"] | {p: prior.digest((OUT / p).read_bytes()) for p in artifacts}
    archive = "chart-positions.jsonl.gz"
    files[archive] = pack(OUT, archive, chart)
    save_json(
        OUT / "score-lock.json",
        dict(files=files, scorer_sha256=prior.digest(Path(__file__).read_bytes())),
    )
    cards(
        query,
        files | {"score-lock.json": prior.digest((OUT / "score-lock.json").read_bytes())},
        archive,
    )


def cards(queries, hashes, archive):
    output = []
    for mode in CONDITIONS:
        names = [r["id"] for r in queries[mode]]
        spec, lock = mode + "-queries.json", mode + "-figure-lock.json"
        save_json(OUT / spec, dict(queries=queries[mode]))
        files = hashes | {spec: prior.digest((OUT / spec).read_bytes())}
        save_json(OUT / lock, dict(files=files, cases=names))
        series = [
            dict(
                key=slot,
                label=label,
                value=PREFIX + method,
                file=archive,
                where={"condition": mode},
                match=list(trial.BIND),
            )
            for slot, label, method in (
                ("candidate", "Earlier ID donor", "earlier_author"),
                ("stock", "Doppler shapes", "shape"),
                ("one", "Earlier blind donor", "earlier_anonymous"),
                ("four", "Tile centre", "centre"),
            )
        ]
        output.append(
            dict(
                id="beacon-transfer-" + mode,
                method=PREFIX + "earlier_author",
                scope="transfer",
                title="Leave-site-out carrier levels, " + mode + " offers",
                caption="The target receives anonymous beacon measurements and one offered square.",
                cases=names,
                queries=spec,
                seal=lock,
                series=series,
                provenance=["prediction-lock.json", "score-lock.json"],
                condition_labels={mode: mode},
            )
        )
    save_json(OUT / "figures.json", dict(version=2, charts=output))


def plot(table, audit):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    rows = [
        r
        for r in table
        if r["arm"] == "c0" and r["mode"] == "containing" and r["method"] == "shape"
    ]
    rows.sort(key=lambda r: r["site"])
    ids = [r["recording"] for r in rows]
    y = np.arange(len(ids))
    lookup = audit["target_author_ceilings"]
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(13.4, 4.5), layout="constrained")
    for i, k in enumerate(("strict_prior_labels", "later_oracle_labels")):
        a.scatter(
            [lookup[q][k] for q in ids],
            y + i * 0.15,
            marker=("o", "x")[i],
            label=("Earlier donors", "All other sites")[i],
        )
    actual = {
        (r["recording"], r["method"]): r
        for r in table
        if r["arm"] == "c0" and r["mode"] == "containing"
    }
    for i, k in enumerate(model.BANKS):
        values = [actual[q, k]["nominal_matches"] for q in ids]
        b.scatter(
            values,
            y + 0.15 * (i - 1),
            marker=("o", "x", "d")[i],
            label=("Earlier author IDs", "Earlier anonymous", "All other sites")[i],
        )
    for k, label, marker in (
        ("center_error_km", "Offered centre", "o"),
        ("forced_error_km", "Doppler-only forced", "x"),
    ):
        c.scatter([r[k] for r in rows], y, marker=marker, label=label)
    for ax, name in zip(
        (a, b, c),
        ("Author label overlap", "Anonymous target matches", "Geographic error (km)"),
        strict=True,
    ):
        ax.set(yticks=y, yticklabels=[r["site"].split("-")[-1] for r in rows], xlabel=name)
        ax.tick_params(labelleft=ax is a)
        ax.invert_yaxis()
        ax.legend(frameon=False, fontsize=8)
    for ax in (a, b):
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.axvline(2, color="0.6", linestyle=":", linewidth=1)
        ax.set_xlim(-0.25, 2.25)
    a.set_ylabel("Physical site")
    fig.savefig(OUT / PLOT, dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    score()
