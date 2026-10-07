"""Paired, scan-clustered confirmation evidence on an unlabeled frozen cohort."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
from array import array
from pathlib import Path

import numpy as np

PRIMARY_METHODS = (
    "current_coherent_margin", "gaussian_coherent", "segment8",
    "segment16", "segment32", "phase_kernel32",
)
COMMON_REFERENCES = ("gaussian", "phase_kernel32")
BASELINE = "current_coherent_margin"
BOOTSTRAP_SEED = 2026100703
BOOTSTRAP_REPLICATES = 5000
FFT_BIN_HZ = 1 / (512 * 4.4e-6)
PAIR_STATISTICS = (
    "margin_difference", "winner_margin", "baseline_margin",
    "winner_exact_score", "winner_control_score",
    "baseline_exact_score", "baseline_control_score",
)


def evaluation(case):
    return case.get("evaluation", case)


def scan_id(record):
    return str(record.get("scan_id", record.get("session_id", record.get("id", ""))))


def finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def pair_values(case, method, reference):
    """Return validated scores, or an explicit reason the pair is unavailable."""
    result = evaluation(case)
    if result.get("status") != "complete":
        return None, f"case_status:{result.get('status', 'missing')}"
    item = result.get("methods", {}).get(method)
    if item is None:
        return None, "method_missing"
    confirmation = item.get("common_confirmation", {}).get(reference)
    if confirmation is None:
        return None, "common_confirmation_missing"
    values = {}
    for hypothesis in ("winner", "baseline"):
        for statistic in ("exact_score", "control_score", "margin"):
            value = finite_number(confirmation.get(hypothesis, {}).get(statistic))
            if value is None:
                return None, f"nonfinite_or_missing:{hypothesis}.{statistic}"
            values[f"{hypothesis}_{statistic}"] = value
        recomputed = values[f"{hypothesis}_exact_score"] - values[f"{hypothesis}_control_score"]
        if not math.isclose(recomputed, values[f"{hypothesis}_margin"],
                            abs_tol=1e-12, rel_tol=1e-10):
            raise ValueError(f"Inconsistent {method}/{reference}/{hypothesis} margin")
    difference = values["winner_margin"] - values["baseline_margin"]
    supplied_difference = finite_number(confirmation.get("margin_difference"))
    if supplied_difference is not None and not math.isclose(
        supplied_difference, difference, abs_tol=1e-12, rel_tol=1e-10
    ):
        raise ValueError(f"Inconsistent {method}/{reference} margin difference")
    values["margin_difference"] = difference
    return values, None


def candidate_metrics(case, method):
    result = evaluation(case)
    item = result.get("methods", {}).get(method, {})
    winner = item.get("winner", {})
    baseline = result.get("baseline_winner", {})
    winner_cfo = finite_number(winner.get("total_cfo_hz"))
    baseline_cfo = finite_number(baseline.get("total_cfo_hz"))
    shift = None if winner_cfo is None or baseline_cfo is None else winner_cfo - baseline_cfo
    winner_id, baseline_id = winner.get("candidate_id"), baseline.get("candidate_id")
    agreement = None if winner_id is None or baseline_id is None else winner_id == baseline_id
    return {
        "candidate_agreement": agreement,
        "candidate_and_cfo_1bin_agreement": None if agreement is None or shift is None
        else bool(agreement and abs(shift) <= FFT_BIN_HZ),
        "signed_cfo_shift_hz": shift,
        "abs_cfo_shift_hz": None if shift is None else abs(shift),
        "cfo_shift_within_1khz": None if shift is None else abs(shift) <= 1000,
        "cfo_shift_within_5khz": None if shift is None else abs(shift) <= 5000,
    }


def mean_or_none(values):
    usable = [value for value in values if value is not None]
    return None if not usable else float(np.mean(usable))


def summarize_values(values):
    if not values:
        return {"count": 0, "mean": None, "median": None, "p90": None}
    array = np.asarray(values, dtype=float)
    return {"count": len(array), "mean": float(array.mean()),
            "median": float(np.median(array)), "p90": float(np.quantile(array, 0.9))}


def bootstrap_scan_means(values, seed, replicates):
    """Resample complete scan means, preserving every receiver/probe within scan."""
    array = np.asarray(values, dtype=float)
    if not len(array):
        return None
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    means = array[rng.integers(0, len(array), (replicates, len(array)))].mean(axis=1)
    return [float(x) for x in np.quantile(means, [0.025, 0.975])]


def describe_pairs(pairs):
    return {statistic: summarize_values([pair[statistic] for pair in pairs])
            for statistic in PAIR_STATISTICS}


def build_summary(inventory, cases, *, replicates=BOOTSTRAP_REPLICATES, seed=BOOTSTRAP_SEED):
    """Keep all inventory scans and use one complete-case mask for primary methods."""
    identifiers = [scan_id(scan) for scan in inventory]
    if not all(identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("Scan inventory requires unique nonempty identifiers")
    known = set(identifiers)
    unknown = sorted({scan_id(case) for case in cases} - known)
    if unknown:
        raise ValueError(f"Cases outside frozen cohort: {unknown}")
    methods = list(PRIMARY_METHODS)
    for case in cases:
        for method in evaluation(case).get("methods", {}):
            if method not in methods:
                methods.append(method)
    methods = list(PRIMARY_METHODS) + sorted(set(methods) - set(PRIMARY_METHODS))
    per_scan = []
    paired_rows = []
    for metadata in inventory:
        identifier = scan_id(metadata)
        observed = [case for case in cases if scan_id(case) == identifier]
        status_counts = {}
        failures = []
        analyzed = []
        for case in observed:
            result = evaluation(case)
            status = str(result.get("status", "missing"))
            status_counts[status] = status_counts.get(status, 0) + 1
            values, exclusions = {}, {}
            for method in methods:
                values[method] = {}
                for reference in COMMON_REFERENCES:
                    pair, reason = pair_values(case, method, reference)
                    values[method][reference] = pair
                    if reason:
                        exclusions[f"{method}/{reference}"] = reason
            primary_complete = all(
                values[method][reference] is not None
                for method in PRIMARY_METHODS for reference in COMMON_REFERENCES
            )
            if primary_complete:
                # All methods' common baseline must be the identical frozen
                # current hypothesis in this later window.
                for reference in COMMON_REFERENCES:
                    base = values[BASELINE][reference]
                    for method in PRIMARY_METHODS:
                        for statistic in ("exact_score", "control_score", "margin"):
                            if not math.isclose(
                                base[f"baseline_{statistic}"],
                                values[method][reference][f"baseline_{statistic}"],
                                abs_tol=1e-12, rel_tol=1e-10,
                            ):
                                raise ValueError("Common baseline varies across primary methods")
            else:
                failures.append({
                    "case_id": case.get("case_id"), "status": status,
                    "reason": case.get("reason", case.get("error", result.get("reason"))),
                    "primary_pair_exclusions": {key: value for key, value in exclusions.items()
                                                if key.split("/")[0] in PRIMARY_METHODS},
                })
            analyzed.append((case, values, primary_complete, exclusions))
        scan_record = {
            "scan_id": identifier, "metadata": metadata, "observed_cases": len(observed),
            "status_counts": status_counts,
            "primary_complete_cases": sum(record[2] for record in analyzed),
            "primary_excluded_cases": len(failures), "failures": failures, "methods": {},
        }
        for method in methods:
            common_case_mask = method in PRIMARY_METHODS
            selected = [(case, values[method]) for case, values, complete, _ in analyzed
                        if complete] if common_case_mask else [
                            (case, values[method]) for case, values, _, _ in analyzed
                            if all(values[method][reference] is not None
                                   for reference in COMMON_REFERENCES)
                        ]
            confirmations = {
                reference: describe_pairs([values[reference] for _, values in selected])
                for reference in COMMON_REFERENCES
            }
            available = sum(all(values[method][reference] is not None
                                for reference in COMMON_REFERENCES)
                            for _, values, _, _ in analyzed)
            comparison = [candidate_metrics(case, method) for case, _ in selected]
            metrics = {
                "candidate_agreement_rate": mean_or_none(
                    [value["candidate_agreement"] for value in comparison]
                ),
                "candidate_and_cfo_1bin_agreement_rate": mean_or_none(
                    [value["candidate_and_cfo_1bin_agreement"] for value in comparison]
                ),
                "cfo_shift_within_1khz_rate": mean_or_none(
                    [value["cfo_shift_within_1khz"] for value in comparison]
                ),
                "cfo_shift_within_5khz_rate": mean_or_none(
                    [value["cfo_shift_within_5khz"] for value in comparison]
                ),
                "abs_cfo_shift_hz": summarize_values(
                    [value["abs_cfo_shift_hz"] for value in comparison
                     if value["abs_cfo_shift_hz"] is not None]
                ),
            }
            scan_record["methods"][method] = {
                "n_analyzed_pairs": len(selected), "n_available_pairs": available,
                "uses_shared_primary_complete_mask": common_case_mask,
                "common_confirmation": confirmations, "candidate_metrics": metrics,
            }
            for case, values in selected:
                for reference in COMMON_REFERENCES:
                    paired_rows.append({
                        "scan_id": identifier, "case_id": case.get("case_id"),
                        "receiver": case.get("receiver"), "method": method,
                        "reference": reference, "primary_shared_mask": common_case_mask,
                        **values[reference], **candidate_metrics(case, method),
                    })
        per_scan.append(scan_record)
    return finish_summary(per_scan, methods, len(cases), replicates, seed), paired_rows


def finish_summary(per_scan, methods, observed_count, replicates, seed):
    aggregate = {}
    for method_index, method in enumerate(methods):
        aggregate[method] = {"common_confirmation": {}, "candidate_metrics": {}}
        for reference_index, reference in enumerate(COMMON_REFERENCES):
            scan_statistics = [scan["methods"][method]["common_confirmation"][reference]
                               for scan in per_scan]
            deltas = [value["margin_difference"]["mean"] for value in scan_statistics
                      if value["margin_difference"]["mean"] is not None]
            paired_count = sum(value["margin_difference"]["count"] for value in scan_statistics)
            weighted_sum = sum(value["margin_difference"]["mean"]
                               * value["margin_difference"]["count"]
                               for value in scan_statistics
                               if value["margin_difference"]["count"])
            aggregate[method]["common_confirmation"][reference] = {
                "equal_scan_mean_margin_difference": mean_or_none(deltas),
                "scan_bootstrap_95": bootstrap_scan_means(
                    deltas, [seed, method_index, reference_index], replicates
                ),
                "scans_with_pairs": len(deltas), "cohort_scan_count": len(per_scan),
                "positive_scan_mean_differences": sum(value > 0 for value in deltas),
                "negative_scan_mean_differences": sum(value < 0 for value in deltas),
                "zero_scan_mean_differences": sum(value == 0 for value in deltas),
                "case_weighted_mean_margin_difference": (
                    weighted_sum / paired_count if paired_count else None
                ),
                "analyzed_pair_count": paired_count,
                "equal_scan_winner_margin_mean": mean_or_none(
                    [value["winner_margin"]["mean"] for value in scan_statistics]
                ),
                "equal_scan_baseline_margin_mean": mean_or_none(
                    [value["baseline_margin"]["mean"] for value in scan_statistics]
                ),
                "equal_scan_winner_exact_score_mean": mean_or_none(
                    [value["winner_exact_score"]["mean"] for value in scan_statistics]
                ),
                "equal_scan_winner_control_score_mean": mean_or_none(
                    [value["winner_control_score"]["mean"] for value in scan_statistics]
                ),
                "uses_shared_primary_complete_mask": method in PRIMARY_METHODS,
            }
        for statistic in ("candidate_agreement_rate", "candidate_and_cfo_1bin_agreement_rate",
                          "cfo_shift_within_1khz_rate", "cfo_shift_within_5khz_rate"):
            aggregate[method]["candidate_metrics"][f"equal_scan_{statistic}"] = mean_or_none([
                scan["methods"][method]["candidate_metrics"][statistic] for scan in per_scan
            ])
    summary = {
        "scope": "Descriptive fixed later-window confirmation on an unlabeled scan cohort",
        "candidate_bank_scope": (
            "Available fractional-complete archived candidates, retaining their integer seeds. "
            "The public archive discarded integer seeds of fractional-incomplete candidates; "
            "this is not every originally acquired seed, and no margin gate is added."
        ),
        "primary_methods": list(PRIMARY_METHODS), "common_references": list(COMMON_REFERENCES),
        "bootstrap": {
            "seed": seed, "replicates": replicates, "unit": "scan",
            "interval": "paired scan-mean percentile bootstrap, conditional on frozen cohort",
            "limitations": "Does not model dependence shared across separate scans/recordings",
        },
        "primary_case_rule": "Both references present for all six primary methods",
        "candidate_cfo_agreement_tolerance_hz": FFT_BIN_HZ,
        "cfo_shift_policy": "Absolute physical total CFO difference; no symbol-rate wrapping",
        "coverage": {
            "cohort_scans": len(per_scan), "observed_cases": observed_count,
            "primary_complete_cases": sum(scan["primary_complete_cases"] for scan in per_scan),
            "primary_excluded_cases": sum(scan["primary_excluded_cases"] for scan in per_scan),
            "scans_without_primary_pairs": [scan["scan_id"] for scan in per_scan
                                            if not scan["primary_complete_cases"]],
        },
        "per_scan": per_scan, "aggregate": aggregate,
        "interpretation": (
            "Margin signs, candidate agreement, and CFO shifts are evidence comparisons; "
            "they do not estimate detection recall, RF false alarms, or position accuracy. "
            "Raw scores from different common-reference formulas are not directly comparable."
        ),
    }
    return summary


def build_stream_summary(inventory, cases, *, row_sink=None,
                         replicates=BOOTSTRAP_REPLICATES, seed=BOOTSTRAP_SEED):
    """Consume each evaluator record once; retain compact numeric scan columns."""
    identifiers = [scan_id(scan) for scan in inventory]
    if not all(identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("Scan inventory requires unique nonempty identifiers")
    methods = list(PRIMARY_METHODS)
    states = {identifier: {"metadata": metadata, "observed": 0, "status_counts": {},
                           "complete": 0, "failures": [], "methods": {}}
              for identifier, metadata in zip(identifiers, inventory, strict=True)}

    def method_state(state, method):
        if method not in state["methods"]:
            state["methods"][method] = {
                "available": 0, "selected": 0,
                "columns": {reference: {key: array("d") for key in PAIR_STATISTICS}
                            for reference in COMMON_REFERENCES},
                "candidate_columns": {key: array("d") for key in (
                    "candidate_agreement", "candidate_and_cfo_1bin_agreement",
                    "cfo_shift_within_1khz", "cfo_shift_within_5khz", "abs_cfo_shift_hz",
                )},
            }
        return state["methods"][method]

    observed_count = 0
    seen_case_ids = set()
    for case in cases:
        identifier = scan_id(case)
        if identifier not in states:
            raise ValueError(f"Cases outside frozen cohort: {identifier}")
        case_id = case.get("case_id")
        if not case_id or case_id in seen_case_ids:
            raise ValueError("Case identifiers must be nonempty and unique")
        seen_case_ids.add(case_id)
        observed_count += 1
        state = states[identifier]
        result = evaluation(case)
        for method in result.get("methods", {}):
            if method not in methods:
                methods.append(method)
        state["observed"] += 1
        status = str(result.get("status", "missing"))
        state["status_counts"][status] = state["status_counts"].get(status, 0) + 1
        values, exclusions = {}, {}
        for method in methods:
            values[method] = {}
            for reference in COMMON_REFERENCES:
                pair, reason = pair_values(case, method, reference)
                values[method][reference] = pair
                if reason and method in PRIMARY_METHODS:
                    exclusions[f"{method}/{reference}"] = reason
        complete = all(values[method][reference] is not None
                       for method in PRIMARY_METHODS for reference in COMMON_REFERENCES)
        if complete:
            state["complete"] += 1
            for reference in COMMON_REFERENCES:
                base = values[BASELINE][reference]
                for method in PRIMARY_METHODS:
                    for statistic in ("exact_score", "control_score", "margin"):
                        if not math.isclose(
                            base[f"baseline_{statistic}"],
                            values[method][reference][f"baseline_{statistic}"],
                            abs_tol=1e-12, rel_tol=1e-10,
                        ):
                            raise ValueError("Common baseline varies across primary methods")
        else:
            state["failures"].append({
                "case_id": case.get("case_id"), "status": status,
                "reason": case.get("reason", case.get("error", result.get("reason"))),
                "primary_pair_exclusions": exclusions,
            })
        for method in methods:
            accum = method_state(state, method)
            available = all(values[method][reference] is not None
                            for reference in COMMON_REFERENCES)
            accum["available"] += int(available)
            primary = method in PRIMARY_METHODS
            if not (complete if primary else available):
                continue
            accum["selected"] += 1
            metrics = candidate_metrics(case, method)
            for key, column in accum["candidate_columns"].items():
                if metrics[key] is not None:
                    column.append(float(metrics[key]))
            for reference in COMMON_REFERENCES:
                for key, column in accum["columns"][reference].items():
                    column.append(values[method][reference][key])
                if row_sink is not None:
                    row_sink({
                        "scan_id": identifier, "case_id": case.get("case_id"),
                        "receiver": case.get("receiver"), "method": method,
                        "reference": reference, "primary_shared_mask": primary,
                        **values[method][reference], **metrics,
                    })
    methods = list(PRIMARY_METHODS) + sorted(set(methods) - set(PRIMARY_METHODS))
    per_scan = []
    for identifier in identifiers:
        state = states[identifier]
        scan_record = {
            "scan_id": identifier, "metadata": state["metadata"],
            "observed_cases": state["observed"], "status_counts": state["status_counts"],
            "primary_complete_cases": state["complete"],
            "primary_excluded_cases": len(state["failures"]),
            "failures": state["failures"], "methods": {},
        }
        for method in methods:
            accum = method_state(state, method)
            columns = accum["candidate_columns"]
            metrics = {
                f"{key}_rate": mean_or_none(columns[key]) for key in (
                    "candidate_agreement", "candidate_and_cfo_1bin_agreement",
                    "cfo_shift_within_1khz", "cfo_shift_within_5khz",
                )
            }
            metrics["abs_cfo_shift_hz"] = summarize_values(columns["abs_cfo_shift_hz"])
            scan_record["methods"][method] = {
                "n_analyzed_pairs": accum["selected"], "n_available_pairs": accum["available"],
                "uses_shared_primary_complete_mask": method in PRIMARY_METHODS,
                "common_confirmation": {
                    reference: {key: summarize_values(column) for key, column in values.items()}
                    for reference, values in accum["columns"].items()
                },
                "candidate_metrics": metrics,
            }
        per_scan.append(scan_record)
    return finish_summary(per_scan, methods, observed_count, replicates, seed)


def add_descriptive_strata(summary):
    """Repeat fixed endpoints within frozen rate/edge groups; no method selection."""
    summary["descriptive_strata"] = {}
    methods = list(summary["aggregate"])
    for field in ("sample_rate_hz", "edge"):
        groups = {}
        for scan in summary["per_scan"]:
            value = scan["metadata"].get(field)
            label = str(value) if value is not None else "unspecified"
            groups.setdefault(label, []).append(scan)
        summary["descriptive_strata"][field] = {}
        for label, scans in groups.items():
            subset = finish_summary(
                scans, methods, sum(scan["observed_cases"] for scan in scans),
                summary["bootstrap"]["replicates"], summary["bootstrap"]["seed"],
            )
            summary["descriptive_strata"][field][label] = {
                "coverage": subset["coverage"], "aggregate": subset["aggregate"],
                "scan_ids": [scan["scan_id"] for scan in scans],
                "interpretation": "Descriptive subgroup, not an independent method-selection stage",
            }


def write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_artifacts(output, summary, paired_rows):
    output.mkdir(parents=True, exist_ok=True)
    per_scan_directory = output / "per_scan"
    per_scan_directory.mkdir(exist_ok=True)
    scan_rows = []
    for scan in summary["per_scan"]:
        safe_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", scan["scan_id"])
        suffix = hashlib.sha256(scan["scan_id"].encode()).hexdigest()[:8]
        (per_scan_directory / f"{safe_id}_{suffix}.json").write_text(
            json.dumps(scan, indent=2, sort_keys=True) + "\n"
        )
        for method, values in scan["methods"].items():
            for reference, scores in values["common_confirmation"].items():
                scan_rows.append({
                    "scan_id": scan["scan_id"], "method": method, "reference": reference,
                    "observed_cases": scan["observed_cases"],
                    "primary_complete_cases": scan["primary_complete_cases"],
                    "n_analyzed_pairs": values["n_analyzed_pairs"],
                    "n_available_pairs": values["n_available_pairs"],
                    "margin_difference_mean": scores["margin_difference"]["mean"],
                    "winner_margin_mean": scores["winner_margin"]["mean"],
                    "baseline_margin_mean": scores["baseline_margin"]["mean"],
                    **{key: value for key, value in values["candidate_metrics"].items()
                       if not isinstance(value, dict)},
                })
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    write_csv(output / "per_scan.csv", scan_rows)
    if paired_rows is not None:
        write_csv(output / "paired_cases.csv", paired_rows)


def make_figures(output, summary):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures = output / "summary_figures"
    figures.mkdir(exist_ok=True)
    methods = [method for method in PRIMARY_METHODS if method != BASELINE]
    labels = [method.replace("gaussian_coherent", "Gaussian64")
              .replace("phase_kernel32", "Kernel32") for method in methods]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.1))
    for reference, ax in zip(COMMON_REFERENCES, axes, strict=True):
        for index, method in enumerate(methods):
            item = summary["aggregate"][method]["common_confirmation"][reference]
            mean, interval = item["equal_scan_mean_margin_difference"], item["scan_bootstrap_95"]
            if mean is not None:
                ax.errorbar(mean, index, xerr=[[mean - interval[0]], [interval[1] - mean]],
                            fmt="o", color="#007a87")
        ax.axvline(0, color="gray", lw=1)
        ax.set_yticks(range(len(methods)), labels)
        ax.set_title(f"Common later {reference} confirmation")
        ax.set_xlabel("Equal-scan mean margin change vs current choice")
        ax.grid(axis="x", alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Frozen first-window choices, fixed later timing/CFO")
    fig.tight_layout()
    for extension in ("png", "svg"):
        fig.savefig(figures / f"paired_confirmation.{extension}", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, max(5, len(summary["per_scan"]) * 0.32)))
    scan_labels = [scan["metadata"].get("label", scan["scan_id"]) for scan in summary["per_scan"]]
    for reference, ax in zip(COMMON_REFERENCES, axes, strict=True):
        values = np.array([
            [scan["methods"][method]["common_confirmation"][reference]["margin_difference"]["mean"]
             for method in methods] for scan in summary["per_scan"]
        ], dtype=float)
        usable = values[np.isfinite(values)]
        limit = max(float(np.max(np.abs(usable))) if usable.size else 0, 1e-12)
        image = ax.imshow(np.ma.masked_invalid(values), cmap="RdBu_r", vmin=-limit, vmax=limit,
                          aspect="auto")
        ax.set_xticks(range(len(methods)), labels, rotation=30, ha="right")
        ax.set_yticks(range(len(scan_labels)), scan_labels, fontsize=8)
        ax.set_title(f"Common later {reference} margin change")
        fig.colorbar(image, ax=ax, fraction=0.05)
    fig.suptitle("Per-scan mean evidence differences; blank means no paired coverage")
    fig.tight_layout()
    for extension in ("png", "svg"):
        fig.savefig(figures / f"per_scan_confirmation.{extension}", dpi=180)
    plt.close(fig)


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def iter_cases(path):
    """Read JSONL/GZ incrementally; regular JSON remains available for small inputs."""
    if path.is_dir():
        for child in sorted(path.glob("R*/results.jsonl.gz")):
            yield from iter_cases(child)
        return
    opener = gzip.open if path.suffix == ".gz" else open
    if ".jsonl" in path.name or ".ndjson" in path.name:
        with opener(path, "rt") as stream:
            for line_number, line in enumerate(stream, 1):
                if line.strip():
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError(f"Case on line {line_number} must be an object")
                    yield record
    else:
        with opener(path, "rt") as stream:
            raw = json.load(stream)
        cases = raw if isinstance(raw, list) else raw.get("cases", raw.get("results"))
        if cases is None:
            raise ValueError("Results require a cases/results list")
        yield from cases


def run(results_path, selection_path, output, coverage_path=None):
    selection = json.loads(selection_path.read_text())
    inventory = selection["scans"]
    result_files = [results_path]
    if results_path.is_dir():
        if not (results_path / "index.json").is_file():
            raise ValueError("Result directory has no finalized index.json")
        for scan in inventory:
            receipt = results_path / str(scan["label"]) / "receipt.json"
            if not receipt.is_file():
                raise ValueError(f"Final receipt missing for {scan['label']}")
        result_files = sorted(results_path.glob("R*/results.jsonl.gz"))
        if coverage_path is None:
            coverage_path = results_path / "index.json"
    output.mkdir(parents=True, exist_ok=True)
    source_hash = file_hash(Path(__file__))
    with (output / "paired_cases.csv").open("w", newline="") as stream:
        writer = None

        def write_row(row):
            nonlocal writer
            if writer is None:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader()
            writer.writerow(row)

        summary = build_stream_summary(inventory, iter_cases(results_path), row_sink=write_row)
    add_descriptive_strata(summary)
    summary["producer_coverage"] = (
        json.loads(coverage_path.read_text()) if coverage_path is not None else {}
    )
    summary["selection_coverage"] = selection.get("coverage", {})
    summary["provenance"] = {
        "results_path": str(results_path.resolve()),
        "results_files": [{"path": str(path.resolve()), "sha256": file_hash(path),
                           "bytes": path.stat().st_size} for path in result_files],
        "selection_path": str(selection_path.resolve()),
        "selection_sha256": file_hash(selection_path),
        "summarize_source_sha256": source_hash,
        "coverage_path": str(coverage_path.resolve()) if coverage_path is not None else None,
        "coverage_sha256": file_hash(coverage_path) if coverage_path is not None else None,
    }
    summary["provenance"]["results_manifest_sha256"] = hashlib.sha256(
        json.dumps(summary["provenance"]["results_files"], sort_keys=True).encode()
    ).hexdigest()
    if file_hash(Path(__file__)) != source_hash:
        raise RuntimeError("Summarizer source changed during evaluation")
    write_artifacts(output, summary, None)
    make_figures(output, summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True,
                        help="JSONL/GZ file or finalized directory containing R*/results.jsonl.gz")
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, help="producer coverage/failure receipt")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    result = run(args.results, args.selection, args.output, args.coverage)
    print(json.dumps(result["coverage"], indent=2))
