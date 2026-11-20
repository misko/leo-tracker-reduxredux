"""Score the sealed Doppler shortlist replays and render matched evidence."""

import argparse
import gzip
import json
from collections import Counter

from ..__main__ import local_output, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, validate_result
from . import broad_search_budget as prior
from . import projector_roof, screening_figures
from . import track_quadrature_trial as trial
from .fresh_scenes import _read, _sha
from .prefix_figures import csv_file

ALL, UNIFORM, QUADRATURE = trial.METHODS
LABELS = {ALL: "Full track times", UNIFORM: "Uniform 8 times", QUADRATURE: "Lobatto 8 times"}
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "tile")
STAGES = {
    "archive_and_peak_selection": "Read GLRT archive",
    "graph": "Graph tracks",
    "setup": "Worker setup and track packing",
    "orbit": "Causal sky and tile",
    "nomination": "All-orbit nomination",
    "exact_rescore": "Exact shortlist rescore",
    "assignment": "Held prediction and joint fit",
    "final_correction": "Exact range-rate corrections",
}
COUNTS = (
    "screen_tracks",
    "compressed_tracks",
    "full_possible_cells",
    "screen_cells",
    "rescore_cells",
    "screen_visibility_losses",
    "final_fit_calls",
    "final_correction_cells",
)
STAGE_ID = "track-quadrature-actual-stage"


def sealed(output):
    seal = _read(output / "prediction-lock.json")
    for name, expected in seal["files"].items():
        if _sha(output / name) != expected:
            raise ValueError(f"sealed prediction input changed: {name}")
    plan = _read(output / "source-lock.json")
    jobs = {j["id"]: j for j in plan["jobs"]}
    with gzip.open(output / trial.POSITIONS, "rt") as stream:
        rows = list(map(json.loads, stream))
    if len(rows) != len(jobs) * len(trial.METHODS) or {(r["id"], r["method"]) for r in rows} != {
        (i, m) for i in jobs for m in trial.METHODS
    }:
        raise ValueError("a sealed recording/method pair is missing or duplicated")
    if list(jobs) != seal["cases"]:
        raise ValueError("source and prediction roster differ")
    for row in rows:
        job = jobs[row["id"]]
        validate_result(row["result"])
        if row.get("observation_sha256", job["observation_sha256"]) != job["observation_sha256"]:
            raise ValueError("prior and fresh original track projections differ")
        if row["cpu"] != job["cpu"] or row["tile"] != job["packet"]["offer"]:
            raise ValueError("attempt used a different affinity or supplied tile")
    for ident in jobs:
        paired = [r for r in rows if r["id"] == ident]
        if any(any(r[k] != paired[0][k] for k in MATCH) for r in paired[1:]):
            raise ValueError("the three receivers require the same sealed request")
    return seal, rows


def reference_control(rows):
    """Bind the extra published v5 projector comparison to its original v5 request."""
    inputs = prior.frozen_inputs()
    archive, hashes = prior._stock_archive()
    records, proofs = {}, {}
    for row in rows:
        if row["method"] != ALL:
            continue
        ident = row["id"]
        item = inputs[ident]
        case = prior._case(item)
        if (row["native_sha256"], row["catalog_sha256"], [row["tile"]]) != (
            item["native"]["sha256"],
            item["catalog"]["sha256"],
            item["regions"],
        ):
            raise ValueError(
                f"projector authority has a different native input or tile for {ident}"
            )
        record = projector_roof.validate_prediction(
            archive[ident], hashes, case=case, allow_failure=True
        )
        records[ident] = record
        proofs[ident] = dict(
            native_sha256=row["native_sha256"],
            catalog_sha256=row["catalog_sha256"],
            supplied_tile=row["tile"],
            input_sha256=record["input_sha256"],
            archive_source=record["source"],
            observation_binding=(
                "Matched native factors and tile. "
                "The projector uses its own track model and priors."
            ),
            wall_s=record.get("worker_wall_s"),
        )
    receipt = projector_roof.REPORT / projector_roof.ARCHIVE_RECEIPT
    return records, dict(
        receipt=str(receipt.relative_to(trial.ROOT)), sha256=_sha(receipt), cases=proofs
    )


def scores(rows, refs, compact):
    output = []
    for row in rows:
        ident = row["id"]
        result = row["result"]
        ref = refs[ident]
        for arm in ARMS:
            endpoint = result["arms"][arm]
            prior_arm = compact[ident]["result"]["arms"][arm]
            output.append(
                dict(
                    id=ident,
                    stratum=row["stratum"],
                    method=row["method"],
                    arm=arm,
                    status=result["status"],
                    reason=result.get("reason"),
                    error_km=distance_km(ref["truth"], endpoint["latlon"]),
                    forced_km=distance_km(ref["truth"], endpoint.get("forced_latlon")),
                    conditional_rf_rms_hz=endpoint.get("rf_rms_hz"),
                    held_frequency_loss=endpoint.get("held_normalized_mean_loss"),
                    held_score=endpoint.get("held_score"),
                    frequency_score=endpoint.get("frequency_score"),
                    c_hz_per_ghz=endpoint.get("c_hz_per_ghz"),
                    archived_projector_km=distance_km(ref["truth"], prior_arm["latlon"]),
                    **{f"{role}_km": ref["reference"][role][arm].get("error_km") for role in ROLES},
                )
            )
    return output


def timing(row):
    metrics = row["result"]["metrics"]
    work = metrics.get("work", {})
    clocks = {}
    for unit in ("cpu_s", "wall_s"):
        mode = unit.split("_")[0]
        stages = {
            k: float(v[unit]) for k, v in row.get("stages", {}).items() if k != "same_exact_backend"
        }
        stages.update(metrics.get(f"stage_{mode}_s", {}))
        completed = row.get("worker", {}).get(unit)
        clocks[f"worker_{unit}"] = completed
        clocks.update(
            {
                f"{k}_{unit}": stages.get(k)
                for k in (
                    "backend_import",
                    "catalogue_read",
                    "archive_and_peak_selection",
                    "graph",
                    "validate_pack",
                    "catalogue_init",
                    "regional_propagation",
                    "node_pack",
                    "screen",
                    "exact_rescore",
                    "held_validation",
                    "shared_association_and_fit",
                    "final_correction",
                )
            }
        )
        for group, names in (
            ("orbit", ("catalogue_init", "regional_propagation")),
            ("nomination", ("screen",)),
            ("assignment", ("held_validation", "shared_association_and_fit")),
            ("screen_path", ("node_pack", "screen", "exact_rescore")),
        ):
            clocks[f"{group}_{unit}"] = sum(stages.get(n, 0) for n in names) if completed else None
        clocks[f"setup_{unit}"] = (
            completed
            - sum(
                stages.get(k, 0)
                for k in (
                    "archive_and_peak_selection",
                    "graph",
                    "catalogue_init",
                    "regional_propagation",
                    "screen",
                    "exact_rescore",
                    "held_validation",
                    "shared_association_and_fit",
                    "final_correction",
                )
            )
            if completed
            else None
        )
    tracks = metrics.get("shortlists", [])
    return dict(
        id=row["id"],
        method=row["method"],
        stratum=row["stratum"],
        cpu=row["cpu"],
        status=row["result"]["status"],
        worker_total_wall_s=row["worker_wall_s"],
        resident_peak_kib=row.get("resident_peak_kib"),
        vm_peak_kib=row.get("proc_memory_kib", {}).get("VmPeak"),
        points=metrics.get("input_points"),
        tracks=metrics.get("input_tracks"),
        unique_fit_points=metrics.get("unique_fit_points"),
        median_track_span_s=distribution(r["t1_s"] - r["t0_s"] for r in tracks)["p50"],
        short_tracks=sum(t["points"] <= 8 for t in tracks),
        max_track_points=max((t["points"] for t in tracks), default=None),
        coarse_state_evaluations=metrics.get("coarse_state_evaluations"),
        fine_state_evaluations=metrics.get("fine_state_evaluations"),
        **clocks,
        screen_million_cells=work.get("screen_cells", 0) / 1e6,
        rescore_million_cells=work.get("rescore_cells", 0) / 1e6,
        **{k: work.get(k, 0) for k in COUNTS},
    )


def evidence(rows):
    stock = {r["id"]: r["result"] for r in rows if r["method"] == ALL}
    data = []
    for row in rows:
        if row["method"] == ALL:
            continue
        result, baseline = row["result"], stock[row["id"]]
        before, after = (r["metrics"].get("shortlists", []) for r in (baseline, result))
        precision = []
        missed = 0
        for a, b in zip(before, after, strict=False):
            if any(a[k] != b[k] for k in ("rf_hz", "lane", "points", "t0_s", "t1_s")):
                raise ValueError("shortlist observations are in a different order or track")
            left, right = (set(t["orbit_rows"]) for t in (a, b))
            precision.append(left == right)
            missed += len(left - right)
        owners = result["metrics"].get("owners", [])
        data.append(
            dict(
                id=row["id"],
                method=row["method"],
                matched_shortlist_tracks=len(precision),
                identical_shortlist_sets=sum(precision),
                omitted_baseline_orbits=missed,
                identical_final_assignments=result["metrics"].get("owners")
                == baseline["metrics"].get("owners"),
                identical_held_assignments=result["metrics"].get("held_by_arm_rows")
                == baseline["metrics"].get("held_by_arm_rows"),
                identical_endpoints=all(
                    result["arms"][a]["latlon"] == baseline["arms"][a]["latlon"] for a in ARMS
                ),
                final_alias_count=sum(r["alias"] != 0 for r in owners),
                final_alias_histogram=dict(sorted(Counter(r["alias"] for r in owners).items())),
                fit_tracks=len(owners),
                fit_points=sum(o["points"] for o in owners),
            )
        )
    return data


def summary(scores, stages, cases):
    geo, runtime = {}, {}
    for method in trial.METHODS:
        timings = [r for r in stages if r["method"] == method]
        runtime[method] = {
            k: distribution(r[k] for r in timings)
            for k in (
                "worker_cpu_s",
                "worker_total_wall_s",
                "screen_path_cpu_s",
                "setup_cpu_s",
                "resident_peak_kib",
            )
        } | {k: sum(r[k] for r in timings) for k in COUNTS}
        geo[method] = {}
        for arm in ARMS:
            arm_rows = [r for r in scores if (r["method"], r["arm"]) == (method, arm)]
            result = {
                k: distribution(r[k] for r in arm_rows)
                for k in (
                    "error_km",
                    "conditional_rf_rms_hz",
                    "held_frequency_loss",
                    "held_score",
                    "frequency_score",
                    "archived_projector_km",
                    *(f"{r}_km" for r in ROLES),
                )
            }
            result["statuses"] = dict(Counter(r["status"] for r in arm_rows))
            for limit in (0.05, 0.10):
                measured, baseline = (result[k] for k in ("error_km", "baseline_km"))
                result[f"within_{round(100 * limit)}_percent_of_v5"] = measured["n"] == baseline[
                    "n"
                ] == len(cases) and all(
                    measured[k] <= (1 + limit) * baseline[k] for k in ("p50", "p95")
                )
            geo[method][arm] = result
    return dict(geographic_and_frequency=geo, runtime=runtime)


def charts(output, cases):
    series = []
    for key, method in (("one", QUADRATURE), ("stock", ALL), ("one_native_factors", UNIFORM)):
        spec = dict(key=key, label=LABELS[method], file=trial.POSITIONS, value=method)
        if method != QUADRATURE:
            spec["match"] = MATCH
        series.append(spec)
    save_json(
        output / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="track_quadrature_native_joint",
                    method=QUADRATURE,
                    scope="roof",
                    cases=cases,
                    title="Eight Doppler times for catalogue screening",
                    caption=(
                        "Same stored GLRT, causal TLE, and tile. "
                        "Both compressed modes refit original points."
                    ),
                    seal="prediction-lock.json",
                    series=series,
                    provenance=["source-lock.json"],
                )
            ],
        ),
    )
    screening_figures.generate(output / "charts", evidence=output)


def stage_chart(output, rows):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    colors = (
        "#9db7c3",
        "#597b88",
        "#dad3c4",
        "#8b789b",
        "#c17c4b",
        "#e4b97b",
        "#406e67",
        "#315878",
    )
    fig, (cpu, cells) = plt.subplots(
        1, 2, figsize=(12.6, 8.6), gridspec_kw={"width_ratios": (1.55, 1)}
    )
    fig.subplots_adjust(left=0.22, right=0.98, top=0.84, bottom=0.16, wspace=0.14)
    fig.suptitle(
        "Track samples used for orbit screening",
        x=0.05,
        y=0.97,
        ha="left",
        fontsize=19,
        weight="bold",
    )
    fig.text(
        0.05,
        0.912,
        "Six matched captures · complete stored-GLRT-to-position replay · one host CPU per fit",
        color="#475569",
    )
    slots = [i + 0.55 * (i // 3) for i in range(len(rows))]
    left = [0.0] * len(rows)
    for (key, label), color in zip(STAGES.items(), colors, strict=True):
        values = [r.get(f"{key}_cpu_s") or 0 for r in rows]
        cpu.barh(slots, values, left=left, height=0.72, label=label, color=color)
        left = [a + b for a, b in zip(left, values, strict=True)]
    cpu.set(
        yticks=slots,
        yticklabels=[f"{r['id']}    {LABELS[r['method']]}" for r in rows],
        title="Full worker CPU",
        xlabel="Process CPU seconds",
    )
    for y, row in zip(slots, rows, strict=True):
        first = row["screen_million_cells"]
        second = row["rescore_million_cells"]
        cells.barh(y, first, height=0.72, color=colors[4])
        cells.barh(y, second, left=first, height=0.72, color=colors[5])
        if row["status"] != "ok":
            cpu.text(0.04, y, row["status"], va="center", fontsize=7)
    cells.set(
        yticks=[],
        title="Orbit work before joint fitting",
        xlabel="Million evaluated orbit-time cells",
    )
    for ax in (cpu, cells):
        ax.set_ylim(slots[-1] + 0.65, -0.65)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(length=0, labelsize=8)
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#e1e7ec", linewidth=0.7)
    fig.legend(
        *cpu.get_legend_handles_labels(),
        loc="lower center",
        bbox_to_anchor=(0.51, 0.052),
        ncol=4,
        frameon=False,
        fontsize=8.5,
    )
    fig.text(
        0.05,
        0.028,
        "Orbit cells count actual projection times. "
        "The shortlist rescore and every later fit use the original samples.",
        fontsize=8.5,
        color="#475569",
    )
    fig.savefig(output / f"{STAGE_ID}.png", dpi=168)
    fig.savefig(output / f"{STAGE_ID}.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    save_json(
        output / "stage-figure.json",
        dict(
            version=1,
            id=STAGE_ID,
            title="Track samples used for orbit screening",
            sample="Six recordings, 18 complete host runs",
            boundary=("Stored GLRT winners through fresh Graph and paired native joint positions"),
            note=(
                "CPU includes dataset packing, TLE initialization, nomination, "
                "exact rescore, and final fitting."
            ),
            image=f"{STAGE_ID}.png",
            pdf=f"{STAGE_ID}.pdf",
            csv="stage.csv",
            seal="stage-figure-lock.json",
        ),
    )
    names = (
        "stage-figure.json",
        "stage.csv",
        "prediction-lock.json",
        f"{STAGE_ID}.png",
        f"{STAGE_ID}.pdf",
    )
    save_json(
        output / "stage-figure-lock.json", dict(files={name: _sha(output / name) for name in names})
    )


def run(output):
    seal, rows = sealed(output)
    refs = {r["id"]: r for r in projector_roof.roster()}
    compact, proofs = reference_control(rows)
    measured = scores(rows, refs, compact)
    stages = [timing(r) for r in rows]
    save_json(output / "archived-projector-binding.json", proofs)
    csv_file(output / "scores.csv", measured)
    csv_file(output / "stage.csv", stages)
    alias = evidence(rows)
    save_json(output / "alias-and-shortlist-audit.json", alias)
    save_json(output / "summary.json", summary(measured, stages, seal["cases"]))
    charts(output, seal["cases"])
    stage_chart(output, stages)
    files = (
        "prediction-lock.json",
        "summary.json",
        "scores.csv",
        "stage.csv",
        "figures.json",
        "stage-figure-lock.json",
        "alias-and-shortlist-audit.json",
        "archived-projector-binding.json",
    )
    save_json(
        output / "score-lock.json",
        dict(cases=seal["cases"], files={name: _sha(output / name) for name in files}),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=local_output, default=trial.REPORT)
    run(cli.parse_args().output)
