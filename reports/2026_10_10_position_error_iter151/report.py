"""Cohort-terminal report adapter; no numerical or reference calls on import."""

import hashlib
import json
import math
from pathlib import Path

from ports import PARENT, ROOT


def reporter():
    source = (PARENT / "report_cohort.py").read_text()
    if source.count('BRANCHES = ("native", "fixed")') != 1:
        raise ValueError("129 report source shape changed")
    source = source.replace('"fixed"', '"zero"')
    namespace = {"__name__": "report129_for151", "__file__": str(PARENT / "report_cohort.py")}
    exec(compile(source, str(PARENT / "report_cohort.py"), "exec"), namespace)
    return namespace


def verify(plan, groups=("source_sha256", "input_sha256")):
    for group in groups:
        for name, expected in plan[group].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("closure changed " + name)


def stage_coverage(directory, label, phase, digest):
    folder = Path(directory) / label / phase
    rows = []
    hashes = {}

    def compact(value, path=""):
        records = []
        if isinstance(value, dict):
            fields = {
                k: value[k]
                for k in (
                    "status",
                    "qualified",
                    "converged",
                    "stationarity",
                    "stop_reason",
                    "error",
                    "reason",
                    "evaluations",
                )
                if k in value
            }
            if fields:
                records.append(dict(payload_path=path, **fields))
            for k, v in value.items():
                if k not in ("vector", "clock_coefficients", "knots_hz", "association"):
                    records.extend(compact(v, path + "/" + k))
        elif isinstance(value, list) and len(value) < 20:
            for i, v in enumerate(value):
                records.extend(compact(v, path + "/" + str(i)))
        return records

    for path in sorted((folder / "stages").glob("*.json")):
        data = path.read_bytes()
        value = json.loads(data)
        if value.get("protocol_sha256") != digest:
            raise ValueError("foreign partial stage/claim")
        hashes[str(path)] = hashlib.sha256(data).hexdigest()
        claimed = path.name.endswith(".claim.json")
        completed = (
            path.with_name(path.name.replace(".claim.json", ".json")).exists() if claimed else True
        )
        payload = value.get("value", {})
        rows.append(
            dict(
                path=str(path),
                key=value.get("key"),
                claim=claimed,
                completed=completed,
                status=payload.get("status") if isinstance(payload, dict) else None,
                elapsed_s=value.get("elapsed_s"),
                attempt_qualification=(
                    payload.get("converged") if isinstance(payload, dict) else None
                ),
                payload_keys=(sorted(payload) if isinstance(payload, dict) else []),
                qualification_records=compact(payload),
            )
        )
    for subfolder in ("slices", "points", "traces"):
        for path in sorted((folder / subfolder).rglob("*.json")):
            data = path.read_bytes()
            value = json.loads(data)
            if value.get("protocol_sha256") != digest:
                raise ValueError("foreign partial artifact")
            hashes[str(path)] = hashlib.sha256(data).hexdigest()
            rows.append(
                dict(
                    path=str(path),
                    artifact_kind=subfolder,
                    status=value.get("status"),
                    phase=phase,
                    label=label,
                )
            )
    return rows, hashes


def progression(summary):
    rows = summary["rows"]
    complete = summary.get("full_comparison_complete") and len(rows) == 12
    paired = [r["arms"]["fitted-c"] for r in rows if "delta_km" in r["arms"]["fitted-c"]]
    valid = all(math.isfinite(a[b]["error_km"]) for a in paired for b in ("native", "zero"))
    mean_delta = sum(a["delta_km"] for a in paired) / len(paired) if paired else None
    worst = max((a["delta_km"] for a in paired), default=None)
    return dict(
        members=12,
        paired_fitted=len(paired),
        complete_pair_coverage=bool(complete and len(paired) == 12),
        mean_fitted_delta_km=mean_delta,
        worst_fitted_regression_km=worst,
        passed=bool(complete and len(paired) == 12 and valid and mean_delta < 0 and worst <= 1),
        scope="Consumed observational pilot gate; "
        "not independent validation or deployment authorization",
    )


def build(plan, directory, digest, *, evaluation_factory=None):
    verify(plan)
    labels = [m["label"] for m in plan["members"]]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError("exact twelve identities required")
    api = reporter()
    rows, hashes = api["load_rows"](plan, directory, digest)
    if not api["sealed"](rows):
        raise ValueError("all twelve member branches must seal before reporting/evaluation")
    partial = {}
    for row in rows:
        partial[row["label"]] = {}
        for branch in ("search", "native", "zero"):
            stages, stagehashes = stage_coverage(directory, row["label"], branch, digest)
            partial[row["label"]][branch] = stages
            hashes.update(stagehashes)
    verify(plan, ("evaluation_source_sha256",))
    evaluate = (evaluation_factory or api["evaluation_callback"])(plan, rows)
    summary = api["summarize"](rows, evaluate=evaluate)
    summary.update(
        receipt_sha256=hashes,
        aggregates=api["aggregate"](summary),
        progression=progression(summary),
    )
    # Never present omitted budget-exhausted terminal regions as completed zeros.
    for row in summary["rows"]:
        row["partial_stage_coverage"] = {"search": partial[row["label"]]["search"]}
        row["membership"] = next(
            m.get("membership", {}) for m in plan["members"] if m["label"] == row["label"]
        )
        for branch in ("native", "zero"):
            row["partial_stage_coverage"][branch] = partial[row["label"]][branch]
            byname = {r["name"]: r for r in row["regions"][branch]}
            row["regions"][branch] = [
                byname.get(
                    "retained-" + str(i),
                    dict(
                        name="retained-" + str(i),
                        status="unavailable-in-terminal",
                        finals=None,
                        calibration_available=None,
                        association_available=None,
                    ),
                )
                for i in range(3)
            ]
    summary["protocol_sha256"] = digest
    return summary
