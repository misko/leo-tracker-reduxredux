"""Measure and score the sealed secant and phase-budget combination."""

import argparse
import gzip
import json
import os
import resource
from hashlib import sha256
from pathlib import Path

from ..__main__ import ROOT, encoded, local_output, references, run_one, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import orbit_projector, v5_core, v5_lean, v5_secant_two_refresh
from .broad_search_budget import _case, frozen_inputs
from .phase_budget import check_record as check_phase_record
from .phase_budget import source_lock as phase_source_lock
from .prefix_figures import csv_file
from .projector_roof import input_hash

REPORT = ROOT / "reports/2026_11_19_receiver_convergence/combined-fit"
RUNS = Path("/srv/bulk/leo-dev/receiver-convergence-20261119/combined-fit")
PHASE = RUNS.with_name("phase-budget")
SECANT = Path("/tmp/leo-secants-results-20261119")
METHOD = "v5_secant_two_refresh"
DEADLINE = 480
CONTROLS = ("orbit_projector", "v5_two_refresh", "v5_secant_fit")
FILES = {
    METHOD: "positions.jsonl.gz",
    CONTROLS[0]: "stock-positions.jsonl.gz",
    CONTROLS[1]: "two-refresh-positions.jsonl.gz",
    CONTROLS[2]: "secant-positions.jsonl.gz",
}
SCHEDULE = (
    (10, "DS26-0036", "DS26-0122", "DS29-0174"),
    (11, "DS29-0082", "DS26-0237", "DS29-0247"),
)
PRIMARY = tuple(first for _, first, *_ in SCHEDULE)
CASES = PRIMARY + tuple(case for _, _, *lane in SCHEDULE for case in lane)


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def source_lock():
    parents = v5_secant_two_refresh.verified_sources()
    return dict(
        files=dict(
            parents,
            **{
                path.name: digest(path)
                for path in (
                    Path(v5_secant_two_refresh.__file__),
                    Path(orbit_projector.__file__),
                    Path(v5_core.__file__),
                    Path(v5_lean.__file__),
                    orbit_projector.KERNEL,
                )
            },
        ),
        scientific_source=v5_lean.SOURCE_SHA256,
        cases=list(CASES),
        schedule=[list(row) for row in SCHEDULE],
        cap_s=DEADLINE,
    )


def _check_candidate(row, case, item, seal):
    result = row["result"]
    validate_result(result)
    if (
        row["id"] != case["id"]
        or row["method"] != METHOD
        or row["input_sha256"] != input_hash(case)
        or row["source_sha256"] != seal["files"]
        or row["native_sha256"] != item["native"]["sha256"]
        or row["catalog_sha256"] != item["catalog"]["sha256"]
        or row["request_sha256"] != item["request"]["sha256"]
        or row["cap_s"] != DEADLINE
        or row["worker_cpu_s"] < 0
        or row["worker_wall_s"] <= 0
    ):
        raise ValueError("combined worker input, source, or timing binding differs")
    if result["status"] == "ok":
        metrics = result["metrics"]
        if (
            set(result["arms"]) != set(ARMS)
            or metrics["kernel_sha256"] != seal["files"]["orbit_projector.c"]
            or metrics["combined_source_sha256"] != v5_secant_two_refresh.DEPENDENCIES
            or metrics["outer_phase_limit"] != 2
            or max(metrics["initial_phase_refresh_counts"], default=0) != 2
            or metrics["position_optimizer"]["calls"] <= 0
            or metrics["position_optimizer"]["jacobian_refreshes"] <= 0
        ):
            raise ValueError("combined worker did not execute both locked policies")
    return row


def replay(ident, runs, report):
    seal = json.loads((report / "source-lock.json").read_bytes())
    if seal != source_lock():
        raise ValueError("combined scientific source differs from pre-input seal")
    cpu = next(c for c, *cases in SCHEDULE if ident in cases)
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError(f"pin this worker to CPU {cpu}")
    destination = runs / ident / "prediction.json"
    if ident not in PRIMARY and any(not (runs / c / "prediction.json").exists() for c in PRIMARY):
        raise ValueError("both primary attempts must finish before confirmation")
    item = frozen_inputs()[ident]
    case = _case(item)
    if any(digest(case[k + "_path"]) != item[k]["sha256"] for k in ("catalog", "native")):
        raise ValueError("stored native GLRT or causal catalogue differs from frozen manifest")
    if destination.is_file():
        return _check_candidate(json.loads(destination.read_bytes()), case, item, seal)
    runs.mkdir(exist_ok=True, parents=True)
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    row = run_one(METHOD, case, runs, DEADLINE, cpu)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    if seal != source_lock():
        raise ValueError("combined scientific source changed during replay")
    row.update(
        method=METHOD,
        cpu=cpu,
        cap_s=DEADLINE,
        source_sha256=seal["files"],
        native_sha256=item["native"]["sha256"],
        catalog_sha256=item["catalog"]["sha256"],
        request_sha256=item["request"]["sha256"],
        worker_user_s=after.ru_utime - before.ru_utime,
        worker_system_s=after.ru_stime - before.ru_stime,
        worker_cpu_s=(after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime),
    )
    _check_candidate(row, case, item, seal)
    save_json(destination, row)
    print(ident, row["result"]["status"], round(row["worker_wall_s"], 2), flush=True)
    return row


def _binding(case, item):
    return dict(
        id=case["id"],
        input_sha256=input_hash(case),
        native_sha256=item["native"]["sha256"],
        catalog_sha256=item["catalog"]["sha256"],
        request_sha256=item["request"]["sha256"],
        tile=case["regions"][0],
    )


def _pending(binding, method, reason):
    return dict(
        binding,
        method=method,
        worker_cpu_s=None,
        worker_wall_s=None,
        cpu=None,
        result=dict(
            status="missing",
            reason=reason,
            boundary=v5_secant_two_refresh.BOUNDARY,
            metrics={},
            arms={a: {"latlon": None} for a in ARMS},
        ),
    )


def _control(method, case, item, phase, secant):
    binding = _binding(case, item)
    ident = item["id"]
    phase_path = phase / ident / (method + ".json")
    if method == "v5_secant_fit" or (method == "orbit_projector" and not phase_path.is_file()):
        use_secant = method == "v5_secant_fit"
        stem = "secant" if use_secant else "reference"
        expected_variant = "v5_secant_fit" if use_secant else "compact-v5-bounded-gn"
        path = secant / ident / (stem + "-prediction.json")
        if not path.is_file():
            return _pending(binding, method, "input-bound control receipt pending")
        raw = path.read_bytes()
        row = json.loads(raw)
        seal = REPORT.parent / "position-fit/seal.json"
        if (
            row["source_seal_sha256"] != digest(seal)
            or row["input_sha256"] != binding["request_sha256"]
            or row["id"] != ident
            or row["variant"] != expected_variant
            or any(row[k] != binding[k] for k in ("native_sha256", "catalog_sha256"))
            or json.loads(seal.read_bytes())["compact_source_sha256"]["v5_secant_fit.py"]
            != v5_secant_two_refresh.DEPENDENCIES["v5_secant_fit.py"]
        ):
            raise ValueError("single-change secant receipt does not use the locked input")
        validate_result(row["result"])
        return dict(
            row,
            **binding,
            method=method,
            worker_cpu_s=None,
            measurement="independent secant study",
            control_receipt_sha256=sha256(raw).hexdigest(),
        )

    if not phase_path.is_file():
        return _pending(binding, method, "phase-budget control receipt pending")
    raw = phase_path.read_bytes()
    row = check_phase_record(json.loads(raw), case, item, method, phase_source_lock())
    return dict(
        row,
        **binding,
        control_receipt_sha256=sha256(raw).hexdigest(),
        measurement="independent phase-budget timing pair",
    )


def seal_predictions(runs, report, phase, secant):
    source = json.loads((report / "source-lock.json").read_bytes())
    if source != source_lock():
        raise ValueError("combined study source changed since the initial seal")
    groups = {m: [] for m in FILES}
    inputs = frozen_inputs()
    for ident in CASES:
        item = inputs[ident]
        case = _case(item)
        binding = _binding(case, item)
        path = runs / ident / "prediction.json"
        if path.is_file():
            row = _check_candidate(json.loads(path.read_bytes()), case, item, source)
            row = dict(row, **binding, measurement="combined controlled replay")
        else:
            row = _pending(binding, METHOD, "combined worker has no completed receipt")
        groups[METHOD].append(row)
        for method in CONTROLS:
            groups[method].append(_control(method, case, item, phase, secant))
    files = {}
    for method, name in FILES.items():
        data = b"".join(encoded(row) + b"\n" for row in groups[method])
        path = report / name
        write(path, gzip.compress(data, mtime=0))
        files[name] = digest(path)
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=CASES,
            files=files,
            source_lock_sha256=digest(report / "source-lock.json"),
            completed={
                method: sum(row["result"]["status"] != "missing" for row in rows)
                for method, rows in groups.items()
            },
        ),
    )
    return groups


def score(groups, report):
    refs = {
        r["id"]: r
        for panel in ("ds26-common127", "roof16")
        for r in references(
            panel,
            list(c for c in CASES if c.startswith("DS26" if panel == "ds26-common127" else "DS29")),
        )[1]
    }
    names = (METHOD, *CONTROLS)
    stock = {row["id"]: row for row in groups[CONTROLS[0]]}
    scored = []
    for method in names:
        for row in groups[method]:
            ref, result = refs[row["id"]], row["result"]
            base = stock[row["id"]]["result"]
            metrics, stage = result["metrics"], result["metrics"].get("stage_s", {})
            for arm in ARMS:
                endpoint, control = result["arms"][arm], base["arms"][arm]
                delta_km = distance_km(endpoint["latlon"], control["latlon"])
                rms, stock_rms = endpoint.get("rf_rms_hz"), control.get("rf_rms_hz")
                scored.append(
                    dict(
                        id=row["id"],
                        dataset=row["id"].split("-")[0],
                        arm=arm,
                        method=method,
                        status=result["status"],
                        reason=result.get("reason"),
                        cpu=row["cpu"],
                        error_km=distance_km(ref["truth"], endpoint["latlon"]),
                        original_v5_error_km=ref["reference"]["baseline"][arm]["error_km"],
                        endpoint_shift_m=1000 * delta_km if delta_km is not None else None,
                        conditional_rms_hz=rms,
                        rms_delta_hz=rms - stock_rms
                        if rms is not None and stock_rms is not None
                        else None,
                        worker_cpu_s=row["worker_cpu_s"],
                        worker_wall_s=row["worker_wall_s"],
                        objective_evaluations=metrics.get("position_optimizer", {}).get(
                            "evaluations"
                        ),
                        **{
                            k + "_s": stage.get(k)
                            for k in (
                                "native_preparation",
                                "initial",
                                "conservative",
                                "family",
                                "signed",
                                "cavity",
                            )
                        },
                    )
                )
    csv_file(report / "scores.csv", scored)
    summary = []
    for method in names:
        for dataset in ("DS26", "DS29"):
            for arm in ARMS:
                subset = [
                    r
                    for r in scored
                    if (r["method"], r["dataset"], r["arm"]) == (method, dataset, arm)
                ]
                results = distribution(r["error_km"] for r in subset)
                original = distribution(r["original_v5_error_km"] for r in subset)
                summary.append(
                    dict(
                        method=method,
                        dataset=dataset,
                        arm=arm,
                        scheduled=len(subset),
                        issued=results["n"],
                        within_5km=sum(
                            r["error_km"] is not None and r["error_km"] <= 5 for r in subset
                        ),
                        approach_error_km=results,
                        original_v5_error_km=original,
                        meets_10pct_geographic_gate=results["n"] == original["n"] == len(subset)
                        and all(results[key] <= 1.1 * original[key] for key in ("p50", "p95")),
                    )
                )
    save_json(report / "summary.json", summary)
    return scored


def figures(scored, report):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    cases = [
        case
        for case in CASES
        if any(
            row["id"] == case and row["method"] == METHOD and row["status"] != "missing"
            for row in scored
        )
    ]
    if not cases:
        return
    x = np.arange(len(cases))
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(max(6.5, 1.35 * len(cases)), 5.6))
    variants = (
        ("orbit_projector", "Compact stock", "#4b5563", "o"),
        ("v5_two_refresh", "Two refreshes", "#ae4c14", "s"),
        ("v5_secant_fit", "Secant", "#317e60", "^"),
        (METHOD, "Combined", "#254f9b", "D"),
        ("baseline", "Original v5", "#7763a7", "x"),
    )
    lookup = {(r["id"], r["arm"], r["method"]): r for r in scored}
    for axis, arm, title in zip(axes, ARMS, ("c = 0", "Fitted c"), strict=True):
        for shift, (method, label, color, marker) in zip(
            np.linspace(-0.21, 0.21, len(variants)), variants, strict=True
        ):
            key = "error_km"
            if method == "baseline":
                key, method = "original_v5_error_km", "orbit_projector"
            errors = [lookup[case, arm, method][key] for case in cases]
            axis.scatter(
                x + shift,
                [np.nan if e is None else e for e in errors],
                marker=marker,
                color=color,
                label=label,
                s=45,
                zorder=3,
            )
        axis.set_title(title, loc="left", fontsize=11)
        axis.set_ylabel("Error (km)")
        axis.grid(axis="y", linewidth=0.5, alpha=0.4)
        axis.margins(y=0.14)
        axis.set_ylim(bottom=0)
    axes[-1].set_xticks(x, cases, rotation=20, ha="right")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center", ncol=3, frameon=False)
    fig.subplots_adjust(top=0.84, bottom=0.16, hspace=0.3)
    fig.savefig(report / "position-errors.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "replay", "summarize"))
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--runs", type=local_output, default=RUNS)
    parser.add_argument("--report", type=local_output, default=REPORT)
    parser.add_argument("--phase", type=local_output, default=PHASE)
    parser.add_argument("--secant", type=local_output, default=SECANT)
    args = parser.parse_args()
    if args.action == "seal":
        path = args.report / "source-lock.json"
        declared = source_lock()
        if path.exists() and json.loads(path.read_bytes()) != declared:
            raise ValueError("refuse to replace previous combined study seal")
        if not path.exists():
            save_json(path, declared)
    elif args.action == "replay":
        if args.case is None:
            parser.error("--case is required for replay")
        replay(args.case, args.runs, args.report)
    else:
        scored = score(
            seal_predictions(args.runs, args.report, args.phase, args.secant), args.report
        )
        figures(scored, args.report)


if __name__ == "__main__":
    main()
