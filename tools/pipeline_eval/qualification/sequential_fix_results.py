"""Score the sealed prefix policy and render separately labeled timing evidence."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from math import cos, radians
from pathlib import Path

from .. import corpus, figure_books, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, validate_result
from ..variants import final_region
from .full_v5_check import FROZEN, _sha
from .prefix_figures import csv_file
from .sequential_fix_timing import raw_inputs, service_metrics, timing
from .sequential_fix_trial import CHECKPOINTS, REPORT

LOCK = "prediction-lock.json"
ATTEMPTS = "checkpoint-predictions.jsonl.gz"
POSITIONS = "positions.jsonl.gz"
DECISIONS = "release-decisions.json"
SCORES = "scores.csv"
TIMING = "timing.csv"


def sealed(report):
    lock = whole_iq.read(report / LOCK)
    for name, digest in lock["files"].items():
        whole_iq.checked(report / name, digest)
    plan = whole_iq.read(report / "source-lock.json")
    expected = {(r["id"], r["offer"], r["cpu"]) for r in plan["assignment"]}
    rows = list(map(json.loads, gzip.decompress((report / ATTEMPTS).read_bytes()).splitlines()))
    groups = defaultdict(list)
    for row in rows:
        validate_result(row["result"])
        groups[row["id"], row["offer"], row["cpu"]].append(row)
    if (
        len(rows) != lock["rows"]
        or groups.keys() != expected
        or any(tuple(r["checkpoint"] for r in group) != CHECKPOINTS for group in groups.values())
    ):
        raise ValueError("sealed position ledger does not cover the full planned roster")
    decisions = {(r["id"], r["offer"]): r for r in whole_iq.read(report / DECISIONS)}
    if decisions.keys() != {(i, o) for i, o, _ in expected}:
        raise ValueError("sealed decisions do not cover the full planned roster")
    return plan, groups, decisions


def roof_references(ids):
    refs = {
        r["id"]: r
        for panel in ("ds26-all159", "roof16")
        for r in corpus.references(panel)
        if r["id"] in ids
    }
    if refs.keys() != ids or any(
        not all(set(r["reference"][role]) == set(ARMS) for role in ROLES) for r in refs.values()
    ):
        raise ValueError("frozen original v5 roles must cover both arms of every recording")
    return refs


def outcome(row, method, *, ident=None, result=None):
    return dict(
        id=ident or row["id"],
        method=method,
        native_sha256=row["recorded_native_sha256"],
        checkpoint_native_sha256=row["input_native_sha256"],
        catalog_sha256=row["catalog_sha256"],
        original_request_sha256=row["original_request_sha256"],
        tile=row["tile"],
        result=result or row["result"],
    )


def unpublished(result, reason):
    if result["status"] != "ok":
        return result
    arms = {arm: dict(latlon=None, forced_latlon=result["arms"][arm]["latlon"]) for arm in ARMS}
    return dict(
        status="withheld", reason=reason, boundary=result["boundary"], metrics={}, arms=arms
    )


def omitted_clearance(tile, truth):
    lat, lon = tile["center"]
    north = (truth[0] - lat) * 111.0
    east = (truth[1] - lon) * 111.32 * cos(radians(lat))
    return max(abs(north), abs(east)) - tile["width_km"] / 2


def score_arm(ident, offer, checkpoint, arm, result, reference, released):
    selected = result["arms"][arm]
    truth = reference["truth"]
    error = distance_km(selected["latlon"], truth)
    record = dict(
        id=ident,
        offer=offer,
        checkpoint=checkpoint,
        arm=arm,
        status=result["status"],
        reason=result.get("reason"),
        released_at_255=released,
        geographic_error_km=error,
        forced_error_km=distance_km(selected.get("forced_latlon"), truth),
        rf_rms_hz=selected.get("rf_rms_hz"),
        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
    )
    for role in ROLES:
        ref = reference["reference"][role][arm]
        candidate_error = ref["error_km"]
        prefix = role.replace("-", "_")
        applicable = offer == "original" and candidate_error is not None
        record.update(
            {
                f"{prefix}_reference_status": ref["status"] if offer == "original" else None,
                f"{prefix}_reference_km": candidate_error if applicable else None,
                f"{prefix}_reference_rf_rms_hz": ref["rf_rms_hz"] if applicable else None,
                f"{prefix}_error_excess_km": error - candidate_error
                if applicable and error is not None
                else None,
                f"{prefix}_within_5pct": (error is not None and error <= 1.05 * candidate_error)
                if applicable
                else None,
                f"{prefix}_within_10pct": (error is not None and error <= 1.10 * candidate_error)
                if applicable
                else None,
            }
        )
    return record


def summarize(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["offer"], str(row["checkpoint"]), row["arm"])].append(row)
    summaries = []
    for (offer, checkpoint, arm), group in sorted(grouped.items()):
        roles = {}
        if offer == "original":
            for role in ROLES:
                prefix = role.replace("-", "_")
                expected = [r for r in group if r[f"{prefix}_within_10pct"] is not None]
                roles[role] = dict(
                    attempted=len(group),
                    reference_available=len(expected),
                    misses_5pct=sum(not row[f"{prefix}_within_5pct"] for row in expected),
                    misses_10pct=sum(not row[f"{prefix}_within_10pct"] for row in expected),
                    error_excess_km=distribution(
                        row[f"{prefix}_error_excess_km"] for row in expected
                    ),
                )
        summaries.append(
            dict(
                offer=offer,
                checkpoint=checkpoint,
                arm=arm,
                cases=len(group),
                statuses=dict(Counter(r["status"] for r in group)),
                returned=sum(r["geographic_error_km"] is not None for r in group),
                geographic_error_km=distribution(r["geographic_error_km"] for r in group),
                rf_rms_hz=distribution(r["rf_rms_hz"] for r in group),
                conditional_frequency_score=distribution(r["frequency_score"] for r in group),
                paired_original_roles=roles,
            )
        )
    return summaries


def ablation(rows):
    pairs = defaultdict(dict)
    for row in rows:
        pairs[row["id"], row["offer"], row["checkpoint"]][row["arm"]] = row
    result = []
    for (ident, offer, checkpoint), pair in pairs.items():
        changes = {}
        for field in ("geographic_error_km", "rf_rms_hz", "frequency_score"):
            zero, fitted = (pair[arm][field] for arm in ARMS)
            changes[field] = fitted - zero if None not in (zero, fitted) else None
        result.append(dict(id=ident, offer=offer, checkpoint=checkpoint, **changes))
    return result


def chart_descriptors(report, ids, queries):
    proof = [LOCK, SCORES, TIMING, "summary.json"]
    roof_lock = "roof-figure-lock.json"
    shifted_lock = "shifted-figure-lock.json"
    queries_file = "shifted-queries.json"
    save_json(report / queries_file, dict(queries=queries))
    roof = dict(
        id="sequential-fix-roof",
        method="sequential_fix",
        scope="roof",
        cases="sealed",
        seal=roof_lock,
        provenance=proof,
        title="Cumulative compact release and full fallback",
        caption=(
            "Six recordings with the original roof offer. The two prefix fits share earlier "
            "GLRT visits. Early release requires agreement and causal support in both arms."
        ),
        series=[
            dict(
                file=POSITIONS,
                key=key,
                label=label,
                value=method,
                match=["native_sha256", "catalog_sha256", "tile"],
            )
            for key, method, label in (
                ("one", "sequential_fix", "255 s gate or complete fallback"),
                ("stock", "full_compact", "Complete compact"),
                ("one_native_factors", "compact_210", "210 s checkpoint"),
                ("all_visits", "compact_255", "255 s checkpoint"),
            )
        ],
    )
    shifted = dict(
        id="sequential-fix-shifted",
        method="sequential_fix_shifted",
        scope="transfer",
        cases="sealed",
        seal=shifted_lock,
        provenance=proof,
        queries=queries_file,
        title="Cumulative compact with the offered square moved east",
        caption=(
            "Two anchor recordings at the same physical site. The supplied position square "
            "moves 15 km east while the causal catalogue and detector observations stay paired."
        ),
        condition_labels={"shifted": "25 km offer moved 15 km east"},
        series=[
            dict(
                file=POSITIONS,
                key="candidate",
                label="Early release",
                value="shifted_early",
                forced_label="255 s constrained diagnostic",
            ),
            dict(file=POSITIONS, key="stock", label="Complete compact", value="shifted_full"),
        ],
    )
    for name, files, cases in (
        (roof_lock, [POSITIONS, *proof], sorted(ids)),
        (shifted_lock, [POSITIONS, queries_file, *proof], [q["id"] for q in queries]),
    ):
        save_json(report / name, dict(cases=cases, files={f: _sha(report / f) for f in files}))
    save_json(report / "figures.json", dict(version=2, charts=[roof, shifted]))


def stage_plot(report, positions, time_rows, summaries):
    import matplotlib.pyplot as plt

    ids = sorted({r["id"] for r in positions if r["offer"] == "original"})
    fig, ((fits, cpu), (elapsed, release)) = plt.subplots(
        2, 2, figsize=(14, 9), layout="constrained"
    )
    palette = ("#39779b", "#d08a33", "#576472")
    for index, (checkpoint, color) in enumerate(zip(CHECKPOINTS, palette, strict=True)):
        values = {
            r["id"]: r
            for r in positions
            if r["offer"] == "original" and r["checkpoint"] == checkpoint
        }
        fits.bar(
            [i + (index - 1) * 0.25 for i in range(len(ids))],
            [values[i]["cpu_s"] for i in ids],
            width=0.24,
            color=color,
            label=str(checkpoint),
        )
        for i, ident in enumerate(ids):
            if values[ident]["status"] == "timed_out":
                fits.text(
                    i + (index - 1) * 0.25,
                    values[ident]["cpu_s"] + 1.0,
                    "cap",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )
    fits.set_xticks(range(len(ids)), ids, rotation=25, ha="right")
    fits.set(
        ylabel="Measured compact service CPU (s)",
        title="Both coefficient arms in each checkpoint fit",
    )
    fits.legend(title="Input seconds", frameon=False)

    anchors = [
        r for r in time_rows if r.get("raw_workers") is not None and r["offer"] == "original"
    ]
    labels = [f"{r['id']}\n{r['raw_workers']}" for r in anchors]
    indices = range(len(anchors))
    for axis, names, ylabel, title in (
        (
            cpu,
            (
                "raw_det_tail_opportunity_cpu_s",
                "total_cpu_saved_eager_s",
                "total_cpu_saved_barrier_s",
            ),
            "CPU saved (s)",
            "Raw saving opportunity and net policy cost",
        ),
        (
            elapsed,
            (
                "model_full_original_finish_s",
                "model_eager_policy_finish_s",
                "model_barrier_policy_finish_s",
            ),
            "Elapsed from original start (s)",
            "Modeled critical path with a separate position lane",
        ),
    ):
        legends = (
            ("Available raw tail", "Eager net", "Barrier net")
            if axis is cpu
            else ("Full original", "Eager policy", "Barrier policy")
        )
        for i, (name, color, label) in enumerate(zip(names, palette, legends, strict=True)):
            axis.bar(
                [n + (i - 1) * 0.24 for n in indices],
                [r[name] for r in anchors],
                width=0.23,
                color=color,
                label=label,
            )
        axis.axhline(0, color="#bbbbbb", lw=0.7)
        axis.set_xticks(indices, labels, fontsize=8)
        axis.set(ylabel=ylabel, title=title)
        axis.set_xlabel("Raw workers")
        lo, hi = axis.get_ylim()
        axis.set_ylim(lo, hi * 1.19)
        axis.legend(frameon=False, fontsize=8)

    for i, arm in enumerate(ARMS):
        fits_by_checkpoint = {
            r["checkpoint"]: r for r in summaries if r["offer"] == "original" and r["arm"] == arm
        }
        series = [
            fits_by_checkpoint[name]["geographic_error_km"]["p50"]
            for name in ("210", "255", "full", "policy")
        ]
        release.plot(
            range(4),
            series,
            marker="o",
            color=palette[i],
            label=("c = 0" if arm == "c0" else "Fitted c"),
        )
    returned = {
        r["checkpoint"]: r for r in summaries if r["offer"] == "original" and r["arm"] == ARMS[0]
    }
    labels = [
        f"{label}\n{returned[key]['returned']}/{returned[key]['cases']} returned"
        for key, label in (
            ("210", "210 s"),
            ("255", "255 s"),
            ("full", "Complete"),
            ("policy", "Policy"),
        )
    ]
    release.set_xticks(range(4), labels)
    release.set(
        ylabel="Median returned geographic error (km)", title="Accuracy from independent scoring"
    )
    release.legend(frameon=False)
    fig.suptitle("Cumulative original-GLRT compact checkpoints", fontsize=17, weight="bold")
    fig.savefig(report / "stage.png", dpi=160)
    fig.savefig(report / "stage.pdf")
    plt.close(fig)


def publish(report, *, interior_guard=False):
    plan, groups, decisions = sealed(report)
    refs = roof_references(plan["cases"].keys())
    raw = {
        ident: raw_inputs(plan["cases"][ident], binding)
        for ident, binding in plan["raw_anchor_timings"].items()
    }
    positions, scores, stages, times, queries = [], [], [], [], []
    for (ident, offer, cpu), rows in sorted(groups.items()):
        first, current, terminal = rows
        accepted = decisions[(ident, offer)]["released"]
        chosen = final_region.select(current, terminal, released=accepted, enabled=interior_guard)
        full = (
            chosen
            if not accepted
            else final_region.select(current, terminal, released=False, enabled=interior_guard)
        )
        block = timing(rows, accepted, raw.get(ident, (None,))[0])
        scenarios = block.pop("scenarios", [dict(raw_workers=None)])
        times.extend(dict(id=ident, offer=offer, **block, **scenario) for scenario in scenarios)
        for row in rows:
            metrics = row["result"]["metrics"]
            stages.append(
                dict(
                    id=ident,
                    offer=offer,
                    checkpoint=row["checkpoint"],
                    cpu=cpu,
                    status=row["result"]["status"],
                    **service_metrics(row),
                    **{
                        stage + "_wall_s": metrics.get("stage_s", {}).get(stage)
                        for stage in (
                            "native_preparation",
                            "initial",
                            "conservative",
                            "family",
                            "signed",
                            "cavity",
                        )
                    },
                    support_diagnostic_wall_s=metrics.get("support_diagnostic_wall_s"),
                )
            )
        for name, row in zip((*CHECKPOINTS, "policy"), (first, current, full, chosen), strict=True):
            scores.extend(
                score_arm(ident, offer, name, arm, row["result"], refs[ident], accepted)
                for arm in ARMS
            )
        if offer == "original":
            positions.extend(
                outcome(row, method)
                for row, method in zip(
                    (first, current, full, chosen),
                    ("compact_210", "compact_255", "full_compact", "sequential_fix"),
                    strict=True,
                )
            )
        else:
            tag = f"{ident}-shifted"
            positions.append(outcome(full, "shifted_full", ident=tag))
            diagnosis = (
                chosen["result"]
                if accepted
                else unpublished(current["result"], "early gate rejected shifted offer")
            )
            positions.append(outcome(current, "shifted_early", ident=tag, result=diagnosis))
            for arm in ARMS:
                scores.append(
                    score_arm(ident, offer, "early", arm, diagnosis, refs[ident], accepted)
                )
            queries.append(
                dict(
                    id=tag,
                    condition="shifted",
                    recording=ident,
                    truth=refs[ident]["truth"],
                    bindings=dict(
                        native_sha256=current["recorded_native_sha256"],
                        catalog_sha256=current["catalog_sha256"],
                        tile=current["tile"],
                    ),
                )
            )
    for row in stages:
        if (
            row["memory_peak_mib"] is None
            or row["memory_peak_mib"] > 512
            or row["swap_peak_bytes"] != 0
        ):
            raise ValueError("measured position work lacks an authenticated memory-limit receipt")
    summary = summarize(scores)
    write(
        report / POSITIONS, gzip.compress(b"".join(encoded(r) + b"\n" for r in positions), mtime=0)
    )
    csv_file(report / SCORES, scores)
    csv_file(report / "coefficient-ablation.csv", ablation(scores))
    csv_file(report / "position-stages.csv", stages)
    time_fields = dict.fromkeys(k for row in times for k in row)
    csv_file(report / TIMING, [{k: row.get(k) for k in time_fields} for row in times])
    save_json(
        report / "summary.json",
        dict(
            groups=summary,
            shifted_true_tile_miss_km={
                q["recording"]: omitted_clearance(q["bindings"]["tile"], q["truth"])
                for q in queries
            },
            previous_actual_raw={i: evidence for i, (_, evidence) in raw.items()},
        ),
    )
    stage_plot(report, stages, times, summary)
    chart_descriptors(report, plan["cases"], queries)
    figure_books.generate(
        report / "charts",
        ARMS,
        methods=("sequential_fix", "sequential_fix_shifted"),
        panel="screening",
        evidence=report,
    )
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="sequential-fix-cost",
            title="Raw and compact cost of cumulative prefix release",
            sample=(
                "Six matched roof recordings and two shifted offers. "
                "Complete raw timing on both anchors."
            ),
            boundary=(
                "Authenticated original GLRT timing and measured compact services "
                "through release or complete fallback"
            ),
            note=(
                "Compact CPU was measured. Raw scheduling and end-to-end elapsed time "
                "are modeled from complete prior per-visit timing ledgers."
            ),
            csv=TIMING,
            image="stage.png",
            pdf="stage.pdf",
            seal="score-lock.json",
        ),
    )
    files = (
        LOCK,
        SCORES,
        "coefficient-ablation.csv",
        "position-stages.csv",
        TIMING,
        "summary.json",
        POSITIONS,
        "stage-figure.json",
        "stage.png",
        "stage.pdf",
        "figures.json",
        "roof-figure-lock.json",
        "shifted-figure-lock.json",
        "shifted-queries.json",
        "charts/manifest.json",
    )
    authority = whole_iq.read(FROZEN / "provenance.json")["files"]
    save_json(
        report / "score-lock.json",
        dict(
            files={f: _sha(report / f) for f in files},
            sources={
                Path(__file__).name: _sha(Path(__file__)),
                "sequential_fix_timing.py": _sha(
                    Path(__file__).with_name("sequential_fix_timing.py")
                ),
            },
            frozen_scorer={f: authority[f] for f in ("targets.jsonl", "scores.csv")},
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
