"""Score the frozen detector audit, keeping geographic and resource evidence explicit."""

import argparse
import csv
import gzip
from collections import Counter
from hashlib import sha256
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution
from . import cascade_audit_trial as trial
from . import complete_detector_roster as fixed
from . import screening_figures, staggered_benchmark, study_benchmark
from . import two_rate_holdout_results as timing
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
METHOD = "cascade_audit"
METHODS = (METHOD, "fast", "original", "random", "oracle")
LABELS = {
    METHOD: "Frozen audit rule",
    "fast": "Always fast",
    "original": "Always original",
    "random": "Rate-matched random",
    "oracle": "Truth oracle ceiling",
}


def seal_endpoints(work, source, route):
    fast, original = trial.controls(source)
    path = trial.two_rate.REPORT
    parent = whole_iq.read(
        whole_iq.checked(path / "prediction-lock.json", source["pins"]["two_rate"])
    )
    first = fixed.select(
        rows_from(fixed.member(path, parent, "positions-first.jsonl.gz")),
        "two_rate_original",
        parent["cases"],
    )
    archive_retries = []
    for ident, row in first.items():
        case = source["cases"][ident]
        bound = {key: case[key] for key in fixed.BINDINGS}
        if row["result"]["status"] != original[ident]["result"]["status"]:
            archive_retries.append(original[ident])
        original[ident] = trial.bind_control(row, bound, "original", case["paired_capture_sha256"])
    for job in source["jobs"]:
        ident = job["id"]
        path = work / ident / job["condition"]
        row = whole_iq.read(path / "attempt.json")
        if any(row[key] != value for key, value in job.items()):
            raise ValueError(f"{ident} changed its prespecified compact job")
        whole_iq.checked(path / "recording/native.json", job["native_sha256"])
        whole_iq.checked(path / "recording/request.json", job["prepared_request_sha256"])
        log = whole_iq.checked(path / "service.log", row["log_sha256"])
        write(REPORT / "logs" / (ident + ".gz"), gzip.compress(log.read_bytes(), mtime=0))
        for mark in (row.get("position_resources") or {}).values():
            if isinstance(mark, dict) and "cpus" in mark and mark["cpus"] != [job["cpu"]]:
                raise ValueError(f"{ident} exceeded the recorded CPU pin")
        original[ident] = trial.bind_control(
            row, {key: job[key] for key in fixed.BINDINGS}, "original", job["paired_capture_sha256"]
        )
    if set(fast) != set(original) or set(fast) != source["cases"].keys():
        raise ValueError("every recording needs two authenticated terminal endpoints")
    development = {
        ident: dict(
            disagreement=source["cases"][ident]["disagreement"],
            target=trial.requires_original(fast[ident]["result"], original[ident]["result"]),
        )
        for ident in trial.DEVELOPMENT
    }
    threshold = trial.threshold(
        (row["disagreement"], row["target"]) for row in development.values()
    )
    held = sorted(set(fast) - set(development))
    choices = {ident: row["disagreement"] >= threshold for ident, row in source["cases"].items()}
    order = sorted(
        held,
        key=lambda ident: trial.digest("random-escalation", source["cases"][ident]["manifest"]),
    )
    if (
        route["development"] != development
        or route["threshold"] != threshold
        or route["holdout"] != held
        or route["escalation"] != choices
        or route["random_escalation"] != sorted(order[: sum(choices[ident] for ident in held)])
    ):
        raise ValueError("paired controls or the sealed signal-only choices changed")
    for ident, case in source["cases"].items():
        whole_iq.checked(REPORT / f"audit/{ident}.jsonl.gz", case["witness_sha256"])
        fixed.same_capture(fast[ident], original[ident])
    pack(
        REPORT / "endpoints.jsonl.gz",
        [row for branch in (fast, original) for row in branch.values()],
    )
    pack(REPORT / "archived-retries.jsonl.gz", archive_retries)
    save_json(
        REPORT / "endpoint-lock.json",
        dict(
            cases=sorted(fast),
            held=route["holdout"],
            scoring_program_sha256=_sha(Path(__file__)),
            files={
                name: _sha(REPORT / name)
                for name in (
                    "source-lock.json",
                    "route-lock.json",
                    "endpoints.jsonl.gz",
                    "archived-retries.jsonl.gz",
                )
            },
        ),
    )
    return fast, original


def references(ids):
    frozen, _ = screening_figures._roof_authority()
    auth, positions = staggered_benchmark.fresh_references()
    spec, fresh = staggered_benchmark.export_references(REPORT, "fresh", ids, auth, positions)
    refs = {ident: frozen[ident] for ident in ids if ident in frozen} | fresh
    if set(refs) != set(ids):
        raise ValueError("an authenticated four-role original v5 reference is missing")
    for row in positions:
        if row["id"] in fresh:
            for arm in ARMS:
                fresh[row["id"]]["reference"][row["method"]][arm]["rf_rms_hz"] = row["result"][
                    "arms"
                ][arm].get("rf_rms_hz")
    return refs, spec


def oracle_score(rows):
    """Lexicographic truth ceiling prioritizes matched allowance hits, then coverage."""
    return (
        sum(row["within_10pct"] for row in rows),
        sum(row["error_km"] is not None for row in rows),
        -sum(row["error_km"] or 0.0 for row in rows),
    )


def rank_benefit(scores, held):
    gain = {}
    for ident in held:
        a, b = (oracle_score(scores[ident, method]) for method in ("original", "fast"))
        gain[ident] = tuple(x - y for x, y in zip(a, b, strict=True))
    order = sorted(held, key=gain.__getitem__, reverse=True)
    return [ident for ident in order if gain[ident] > (0, 0, 0)], order


def costs(source, fast, original, decision):
    timing_folder = fixed.BASE / "complete-timing"
    ledger = whole_iq.read(timing_folder / "prediction-lock.json")
    exact_fast = {}
    with fixed.member(timing_folder, ledger, "resources.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["method"] != fixed.FOUR:
                continue
            ident = row["id"]
            if (
                row["native_sha256"] != fast[ident]["native_sha256"]
                or row["scientific_outcome_sha256"]
                != sha256(encoded(fixed.scientific_outcome(fast[ident]))).hexdigest()
            ):
                raise ValueError("fast timing source does not bind the same fit")
            if row["detector_cpu_s"] and row["detector_calls"]:
                exact_fast[ident] = row
    cases = source["cases"]
    model_fast = {
        series: median(
            float(row["detector_cpu_s"]) / int(row["detector_calls"])
            for ident, row in exact_fast.items()
            if ident.startswith(series)
        )
        for series in ("DS26", "DS29")
    }
    original_trace = {}
    timing_membership = trial.two_rate.inventory()["physical_manifest_sha256"]
    for ident, (folder, pin) in timing.TIMINGS.items():
        if timing_membership[ident] != cases[ident]["manifest"]:
            raise ValueError("original timing uses a different physical manifest")
        folder = fixed.SCREEN / folder
        receipt = whole_iq.read(whole_iq.checked(folder / "timing-lock.json", pin))
        with fixed.member(folder, receipt, "timing.csv").open(newline="") as stream:
            data = {
                int(row["visit"]): float(row["cpu_ms"]) * 1e-3
                for row in csv.DictReader(stream)
                if row["status"] == "processed"
            }
        if (
            len(data) != cases[ident]["valid_visits"]
            or not set(cases[ident]["audit_visits"]) <= data.keys()
        ):
            raise ValueError("original timing differs from sealed audit support")
        original_trace[ident] = data
    model_orig = {
        ident[:4]: sum(data.values()) / len(data) for ident, data in original_trace.items()
    }
    out = []
    for ident, case in cases.items():
        n, audit = case["valid_visits"], len(case["audit_visits"])
        if ident in exact_fast:
            measures = exact_fast[ident]
            if int(measures["detector_calls"]) != n:
                raise ValueError("timed fast detector did not cover the full capture")
            fast_cpu = float(measures["detector_cpu_s"])
            fast_fit = float(measures["position_cpu_s"]) if measures["position_cpu_s"] else None
        else:
            fast_cpu = n * model_fast[ident[:4]]
            fast_fit = (fast[ident].get("position_resources") or {}).get("cpu_s")
        if ident in original_trace:
            trace = original_trace[ident]
            orig_cpu = sum(trace.values())
            audit_cpu = sum(trace[visit] for visit in case["audit_visits"])
        else:
            orig_cpu, audit_cpu = [k * model_orig[ident[:4]] for k in (n, audit)]
        original_fit = (original[ident].get("position_resources") or {}).get("cpu_s")
        route = decision[ident]
        out.append(
            dict(
                id=ident,
                valid_visits=n,
                audit_calls=audit,
                escalated=route,
                fast_detector_cpu_s=fast_cpu,
                original_detector_cpu_s=orig_cpu,
                audit_detector_cpu_s=audit_cpu,
                fast_detector_measured=ident in exact_fast,
                original_detector_measured=ident in original_trace,
                cascade_detector_cpu_s=fast_cpu + (orig_cpu if route else audit_cpu),
                cascade_fast_calls=n,
                cascade_original_calls=n if route else audit,
                cascade_total_fits=1 + int(route),
                measured_fast_fit_cpu_s=fast_fit,
                measured_original_fit_cpu_s=original_fit,
                modeled_cascade_position_cpu_s=(
                    fast_fit + (original_fit if route else 0)
                    if fast_fit is not None and (not route or original_fit is not None)
                    else None
                ),
            )
        )
    return out


def plot_rank(rows):
    fig, axes = plt.subplots(1, 2, figsize=(11.7, 4.6), layout="constrained", sharey=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        for key, color in (("signal", "#3b677f"), ("random", "#777777"), ("oracle", "#aa5c40")):
            points = [r for r in rows if r["arm"] == arm and r["ranker"] == key]
            label = {
                "signal": "Audit rank",
                "random": "Manifest permutation",
                "oracle": "Truth oracle",
            }[key]
            ax.plot(
                [r["budget"] for r in points],
                [r["within_10pct"] for r in points],
                marker=".",
                color=color,
                label=label,
            )
        ax.set(
            title="Zero calibration" if arm == "c0" else "Fitted calibration",
            xlabel="Escalated recordings of 20",
        )
        ax.legend(loc="lower right")
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("Within 10% of original v5 (of 20)")
    fig.suptitle("Held recording rank sweep with the same escalation budget")
    fig.savefig(REPORT / "stage.png", dpi=155)
    fig.savefig(REPORT / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(work):
    source = whole_iq.read(REPORT / "source-lock.json")
    route = whole_iq.read(REPORT / "route-lock.json")
    whole_iq.checked(REPORT / "source-lock.json", route["source_sha256"])
    fast, original = seal_endpoints(work, source, route)
    cases = source["cases"]
    held = route["holdout"]
    refs, roof = references(held)
    branches = fixed.scored(
        [
            dict(row, method=key)
            for key, branch in (("fast", fast), ("original", original))
            for ident, row in branch.items()
            if ident in held
        ],
        refs,
    )
    scored = {
        (ident, method): [r for r in branches if r["id"] == ident and r["method"] == method]
        for ident in held
        for method in ("fast", "original")
    }
    oracle, oracle_rank = rank_benefit(scored, held)
    signal_rank = sorted(
        held, key=lambda i: (-cases[i]["disagreement"], trial.digest(cases[i]["manifest"]))
    )
    random_rank = sorted(
        held, key=lambda i: trial.digest("random-escalation", cases[i]["manifest"])
    )
    routes = dict(
        fast=set(),
        original=set(held),
        oracle=set(oracle),
        cascade_audit={i for i in held if route["escalation"][i]},
        random=set(route["random_escalation"]),
    )
    predictions = [
        dict(
            (original if ident in routes[k] else fast)[ident],
            method=k,
            selected_branch="original" if ident in routes[k] else "fast",
        )
        for k in METHODS
        for ident in held
    ]
    pack(REPORT / "positions.jsonl.gz", predictions)
    save_json(
        REPORT / "oracle.json",
        {
            "escalations": oracle,
            "same_budget": oracle_rank[: len(routes[METHOD])],
            "criterion": (
                "maximize both arms' +10% successes, then publications, "
                "then minimize sum of geographic errors"
            ),
        },
    )
    scores = fixed.scored(predictions, refs)
    csv_file(REPORT / "scores.csv", scores)
    summary = []
    for arm in ARMS:
        by_arm = [r for r in scores if r["arm"] == arm]
        for key in METHODS:
            selected = [r for r in by_arm if r["method"] == key]
            count = Counter(r["status"] for r in selected)
            row = fixed.summary_row(selected, held, "holdout", arm, key)
            rms = distribution(r["rf_rms_hz"] for r in selected)
            summary.append(
                dict(
                    row,
                    escalations=len(routes[key]),
                    withheld=count["withheld"],
                    timed_out=count["timed_out"],
                    failed=count["failed"],
                    missing=count["missing"],
                    unavailable=count["unavailable"],
                    rf_n=rms["n"],
                    rf_p50_hz=rms["p50"],
                    rf_p95_hz=rms["p95"],
                )
            )
    csv_file(REPORT / "summary.csv", summary)
    csv_file(
        REPORT / "original-v5-references.csv",
        [
            dict(
                id=ident,
                role=role,
                arm=arm,
                status=ref["status"],
                error_km=ref["error_km"],
                rf_rms_hz=ref.get("rf_rms_hz"),
            )
            for ident in held
            for role in ROLES
            for arm in ARMS
            if (ref := refs[ident]["reference"][role][arm])
        ],
    )
    csv_file(REPORT / "costs.csv", costs(source, fast, original, route["escalation"]))
    rank = []
    for key, order in (("signal", signal_rank), ("random", random_rank), ("oracle", oracle_rank)):
        for budget in range(len(held) + 1):
            selected = set(order[:budget])
            for arm in ARMS:
                pairs = [
                    row
                    for ident in held
                    for row in scored[ident, "original" if ident in selected else "fast"]
                    if row["arm"] == arm
                ]
                rank.append(
                    dict(
                        ranker=key,
                        budget=budget,
                        arm=arm,
                        within_10pct=sum(r["within_10pct"] for r in pairs),
                        published=sum(r["error_km"] is not None for r in pairs),
                    )
                )
    csv_file(REPORT / "rank-sweep.csv", rank)
    plot_rank(rank)
    stage = dict(
        version=1,
        id="cascade-audit-ranking",
        title="Held ranking at equal escalation counts",
        boundary="Sealed audit scores → hypothetical rank budgets against the truth ceiling",
        sample="20 held recordings · identical branch endpoints across rankers",
        note=(
            "Nonzero budgets are sensitivity diagnostics. "
            "The frozen deployable threshold is scored separately."
        ),
        seal="stage-lock.json",
        image="stage.png",
        csv="rank-sweep.csv",
        pdf="stage.pdf",
    )
    save_json(REPORT / "stage-figure.json", stage)
    save_json(
        REPORT / "stage-lock.json",
        dict(
            files={
                name: _sha(REPORT / name)
                for name in ("stage-figure.json", "stage.png", "stage.pdf", "rank-sweep.csv")
            }
        ),
    )

    configs = (
        ("cascade-audit-held", "Sparse original-detector audit on 20 held recordings", METHODS[:4]),
        (
            "cascade-audit-ceiling",
            "Sparse detector audit against a geographic hindsight ceiling",
            (METHOD, "fast", "original", "oracle"),
        ),
    )
    charts = [
        dict(
            id=ident,
            method=METHOD,
            scope="roof",
            title=title,
            cases="sealed",
            seal="figure-lock.json",
            provenance=["route-lock.json", "endpoint-lock.json", "summary.csv"],
            caption=(
                "Complete matched factors and scheduled compact fits on the fixed holdout. "
                "The truth oracle uses scored geography only as a ceiling."
            ),
            roof_references=roof,
            series=[
                dict(
                    key=k,
                    label=LABELS[m],
                    file="positions.jsonl.gz",
                    value=m,
                    native_field="paired_capture_sha256",
                    match=list(fixed.BINDINGS),
                )
                for k, m in zip(
                    ("one", "stock", "one_native_factors", "all_visits"), methods, strict=True
                )
            ],
        )
        for ident, title, methods in configs
    ]
    save_json(REPORT / "figures.json", dict(version=2, charts=charts))
    names = (
        "figures.json",
        "positions.jsonl.gz",
        "source-lock.json",
        "route-lock.json",
        "endpoint-lock.json",
        "summary.csv",
        "scores.csv",
        "original-v5-references.csv",
        "costs.csv",
        "oracle.json",
        "stage-lock.json",
        *roof.values(),
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=held, files={name: _sha(REPORT / name) for name in names}),
    )
    study_benchmark.run(REPORT, REPORT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=local_output)
    publish(parser.parse_args().work)
