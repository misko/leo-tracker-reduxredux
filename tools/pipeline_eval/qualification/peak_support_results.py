"""Bind the shared-support ablations to full authentic position and input receipts."""

import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from ..__main__ import save_json
from ..scoring import ARMS, distance_km, validate_result
from .factor_cross_results import checked_result
from .factor_cross_trial import write_members
from .full_held_scores import held_references
from .input_factor_bridge import REPO, SCREEN, _sha, check, read
from .input_factor_comparison import ledger, sealed
from .peak_support import SOURCES
from .peak_support_trial import BAND, ORDER, REPORT
from .prefix_figures import csv_file

LABELS = {"capture-era": "Capture-era", "ordinary": "Narrow ordinary", "wide": "Wide"}
METHODS = {"ordinary_narrow_full_iq": "ordinary", "regional_wide_full_iq": "wide"}


def systemd_runtime(diagnostics):
    """Read measured unit lifetime independently of the orchestration timer."""
    units = {"h": 3600, "min": 60, "s": 1, "ms": 1e-3, "us": 1e-6}
    for line in diagnostics:
        label, _, value = line.strip().partition(":")
        if label == "Service runtime":
            parts = re.findall(r"(\d+(?:\.\d+)?)(h|min|ms|us|s)", value)
            if parts:
                return sum(float(x) * units[unit] for x, unit in parts)
    return None


def controls():
    capture = SCREEN / "secant-full"
    sealed(capture, "receipt.json")
    sealed(BAND, "prediction-lock.json")
    archived = ledger(capture / "v5_secant_fit.jsonl.gz")
    ret = {(ident, "capture-era"): archived[ident] for ident in ORDER[:4]}
    with gzip.open(BAND / "positions.jsonl.gz", "rt") as stream:
        for row in map(json.loads, stream):
            if row["id"] in ORDER[:4]:
                ret[row["id"], METHODS[row["method"]]] = row
    return ret


def charts():
    return dict(
        version=1,
        charts=[
            dict(
                id=f"peak-support-{source}",
                method="peak_support",
                scope="roof",
                title=f"{LABELS[source]} positions on strict shared probe support",
                caption=(
                    "Shared probes hold a reciprocal gate-passing family in all three "
                    "detectors. The control is hash-thinned to matching lane and time counts."
                ),
                cases=list(ORDER[:4]),
                seal="figure-lock.json",
                provenance=["scores.csv", "summary.json", "prediction-lock.json"],
                series=[
                    dict(
                        key=slot,
                        label=label,
                        file="figure-positions.jsonl.gz",
                        value=f"{source}-{kind}",
                        native_field="origin_native_sha256",
                        native_authority="frozen" if source == "capture-era" else "ordinary",
                    )
                    for slot, label, kind in (
                        ("one", "Observed reciprocal common probes", "common"),
                        ("stock", "Full recipient factors", "full"),
                        ("one_native_factors", "Matched random thinning", "random"),
                    )
                ],
            )
            for source in SOURCES
        ],
    )


def publish():
    lock = sealed(REPORT, "prediction-lock.json")
    inputs = read(REPORT / "plan.json")
    for relpath, expected in inputs["sources"].items():
        check(REPO / relpath, expected)
    for name, expected in inputs["files"].items():
        check(REPORT / name, expected)
    attempted = ledger(REPORT / "results.jsonl.gz")
    if set(attempted) != set(lock["cases"]):
        raise ValueError("computed positions differ from the frozen result roster")
    coverage = defaultdict(Counter)
    for rows in read(REPORT / "peak-census.json").values():
        for k, count in rows.items():
            coverage[k].update(count)
    save_json(REPORT / "pooled-peak-census.json", dict(coverage))
    full = controls()
    truth = {r["id"]: r["truth"] for r in held_references("", ORDER[:4])[1]}
    metrics, figure = [], []
    for binding in inputs["inputs"]:
        ident, source, kind = (binding[k] for k in ("recording", "factor_source", "condition"))
        parent = full[ident, source]
        origin = binding["origin_native_sha256"]
        expected = (
            parent["native_sha256"] if source == "capture-era" else parent["paired_ordinary_sha256"]
        )
        if expected != origin or parent["catalog_sha256"] != binding["catalog_sha256"]:
            raise ValueError("figure control has different factor authority or catalogue")
        expected_native = parent["native_sha256"] if source != "ordinary" else expected
        if expected_native != binding["parent_native_sha256"]:
            raise ValueError("ablation input has a different recipient native document")
        run = attempted.get(binding["id"])
        if run:
            result = checked_result(
                run,
                binding,
                dict(
                    cpus=inputs["cpus"],
                    memory_bytes=inputs["memory_bytes"],
                    swap_bytes=inputs["swap_bytes"],
                ),
            )
        else:
            result = dict(
                status="missing",
                reason="No terminal service receipt at this checkpoint",
                boundary="Stored native probes through the compact position worker",
                metrics=dict(position_attempted=False),
            )
        validate_result(result)
        figure.append(
            dict(
                id=ident,
                method=f"{source}-{kind}",
                tile=parent["tile"],
                native_sha256=binding["native_sha256"],
                origin_native_sha256=origin,
                catalog_sha256=binding["catalog_sha256"],
                result=result,
            )
        )
        for arm in ARMS:
            candidate = result.get("arms", {}).get(arm, {})
            older = parent["result"]["arms"][arm]
            error = distance_km(candidate.get("latlon"), truth[ident])
            full_err = distance_km(older["latlon"], truth[ident])
            frequency = candidate.get("rf_rms_hz")
            peak = (
                run["runtime"]["finish"][0]["cgroup_peak"]
                if run and run["runtime"]["finish"]
                else None
            )
            service_runtime = systemd_runtime(run["diagnostics"]) if run else None
            metrics.append(
                dict(
                    id=ident,
                    source=source,
                    condition=kind,
                    arm=arm,
                    status=result["status"],
                    selected_probes=binding["selected_probes"],
                    error_km=error,
                    full_error_km=full_err,
                    delta_km=None if error is None or full_err is None else error - full_err,
                    conditional_rms_hz=frequency,
                    full_conditional_rms_hz=older.get("rf_rms_hz"),
                    observations=result["metrics"].get("observations"),
                    tracks=result["metrics"].get("tracks"),
                    cgroup_peak_bytes=peak,
                    controller_wall_s=run["wall_s"] if run else None,
                    systemd_runtime_s=service_runtime,
                    within_10pct=error is not None
                    and full_err is not None
                    and error <= 1.1 * full_err,
                )
            )
    for (_ident, source), parent in full.items():
        baseline = dict(parent, method=f"{source}-full")
        baseline["origin_native_sha256"] = (
            parent["native_sha256"] if source == "capture-era" else parent["paired_ordinary_sha256"]
        )
        figure.append(baseline)
    tally = defaultdict(Counter)
    for row in metrics:
        key = "/".join(row[k] for k in ("source", "condition", "arm"))
        tally[key][row["status"]] += 1
        tally[key]["within_10pct_full"] += row["within_10pct"]
    save_json(
        REPORT / "summary.json",
        dict(
            status=attempted.keys() == set(row["id"] for row in inputs["inputs"]),
            tallies=dict(tally),
            run_lock_sha256=_sha(REPORT / "prediction-lock.json"),
        ),
    )
    write_members(REPORT / "figure-positions.jsonl.gz", figure)
    csv_file(REPORT / "scores.csv", metrics)
    save_json(REPORT / "figures.json", charts())
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=list(ORDER[:4]),
            scorer_sha256=_sha(Path(__file__)),
            files={
                name: _sha(REPORT / name)
                for name in (
                    "prediction-lock.json",
                    "summary.json",
                    "scores.csv",
                    "figure-positions.jsonl.gz",
                    "pooled-peak-census.json",
                )
            },
        ),
    )


if __name__ == "__main__":
    publish()
