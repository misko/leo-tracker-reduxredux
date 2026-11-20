"""Score sealed peak-filter replay endpoints and paired preparation costs."""

import argparse
from pathlib import Path

from ..__main__ import local_output, save_json
from ..scoring import ARMS, distance_km, distribution, thresholds
from . import screening_figures
from .coherent_peak_trial import MATCHED, METHODS, REPORT
from .input_factor_bridge import _sha, read
from .prefix_figures import csv_file

BASELINE = "original_v5"
CHART_ID = "coherent-peak-continuation"


def point_row(ident, cohort, method, arm, status, reason, endpoint, truth):
    point, forced = endpoint.get("latlon"), endpoint.get("forced_latlon")
    return dict(
        id=ident,
        cohort=cohort,
        method=method,
        arm=arm,
        status=status,
        reason=reason,
        publication=point is not None,
        latlon=point,
        error_km=distance_km(point, truth),
        forced_latlon=forced,
        forced_error_km=distance_km(forced, truth),
        conditional_rf_rms_hz=endpoint.get("rf_rms_hz"),
    )


def losses(filtered, strict):
    """Count scientific withholds and execution failures separately."""
    if [p["id"] for p in filtered] != [p["id"] for p in strict]:
        raise ValueError("paired publications must use the same ordered cases")
    removed = [
        a
        for a, b in zip(filtered, strict, strict=True)
        if b["publication"] and not a["publication"]
    ]
    gained = [
        b
        for a, b in zip(filtered, strict, strict=True)
        if a["publication"] and not b["publication"]
    ]
    return dict(
        strict_fix_lost_to_withhold=[p["id"] for p in removed if p["status"] in {"ok", "withheld"}],
        strict_fix_lost_to_deadline=[p["id"] for p in removed if p["status"] == "timed_out"],
        strict_fix_lost_to_other_failure=[
            p["id"] for p in removed if p["status"] not in {"ok", "withheld", "timed_out"}
        ],
        new_fix=[p["id"] for p in gained],
        new_fix_after_strict_deadline=[p["id"] for p in gained if p["status"] == "timed_out"],
    )


def result_summary(rows):
    errors = [row["error_km"] for row in rows]
    return dict(
        scheduled=len(rows),
        published=sum(row["publication"] for row in rows),
        statuses={
            status: sum(row["status"] == status for row in rows)
            for status in sorted({row["status"] for row in rows})
        },
        error_km=distribution(errors),
        within_km=thresholds(errors),
        forced_error_km=distribution(row["forced_error_km"] for row in rows),
        conditional_rf_rms_hz=distribution(row["conditional_rf_rms_hz"] for row in rows),
    )


def runtime(row, filter_times):
    result = row["result"]["metrics"]
    prep = result.get("stage_s", {}).get("native_preparation")
    finish = row["runtime"]["finish"]
    finish = finish[0] if finish else {}
    filt = filter_times["filter_wall_s"] if row["method"] == METHODS[0] else 0.0
    return dict(
        id=row["id"],
        method=row["method"],
        status=row["result"]["status"],
        wall_s=row["wall_s"],
        cpu_s=finish.get("cgroup_cpu_s"),
        cgroup_peak_bytes=finish.get("cgroup_peak"),
        native_preparation_s=prep,
        filter_wall_s=filt,
        filter_plus_native_preparation_s=None if prep is None else prep + filt,
        tracks=result.get("tracks"),
        observations=result.get("observations"),
        compact_projections=result.get("compact_projections"),
        stage_s=result.get("stage_s", {}),
    )


def paired_runtime(rows):
    timings = {}
    for row in rows:
        timings.setdefault(row["id"], {})[row["method"]] = row
    fields = (
        "wall_s",
        "cpu_s",
        "cgroup_peak_bytes",
        "native_preparation_s",
        "filter_plus_native_preparation_s",
        "tracks",
        "observations",
        "compact_projections",
    )
    return {
        ident: {
            "both_completed": all(row["status"] in {"ok", "withheld"} for row in pair.values()),
            **{
                key: pair[METHODS[0]][key] - pair[METHODS[1]][key]
                if all(pair[method][key] is not None for method in METHODS)
                else None
                for key in fields
            },
        }
        for ident, pair in timings.items()
    }


def publish(report):
    (study,) = screening_figures.charts([CHART_ID], report)
    frozen = screening_figures._roof_authority()[1]
    request_rows = read(report / "requests.json")
    factor_counts = read(report / "factor-counts.json")
    points, times = [], []
    for ident in sorted(study.cases):
        cohort = "matched" if ident in MATCHED else "held"
        reference = study.references[ident]
        truth = reference["truth"]
        for method, chart_key in zip(METHODS, ("one", "stock"), strict=True):
            row = study.predictions[chart_key][ident]
            if any(row[k] != v for k, v in request_rows[ident][method].items()):
                raise ValueError(f"prediction request binding differs for {ident}")
            if row["expected_capture_era_native_sha256"] != frozen[ident]["native"]["sha256"]:
                raise ValueError(f"archived comparator native provenance differs for {ident}")
            result = row["result"]
            times.append(runtime(row, factor_counts[ident]))
            for arm in ARMS:
                points.append(
                    point_row(
                        ident,
                        cohort,
                        method,
                        arm,
                        result["status"],
                        result.get("reason"),
                        result.get("arms", {}).get(arm, {}),
                        truth,
                    )
                )
        for arm in ARMS:
            endpoint = reference["reference"]["baseline"][arm]
            points.append(
                point_row(
                    ident,
                    cohort,
                    BASELINE,
                    arm,
                    endpoint["status"],
                    endpoint.get("reason"),
                    endpoint,
                    truth,
                )
            )
    summaries, pairing = {}, {}
    for subset in ("all", "matched", "held"):
        summaries[subset], pairing[subset] = {}, {}
        for arm in ARMS:
            selected = {
                method: [
                    p
                    for p in points
                    if p["method"] == method
                    and p["arm"] == arm
                    and (subset == "all" or subset == p["cohort"])
                ]
                for method in (*METHODS, BASELINE)
            }
            summaries[subset][arm] = {m: result_summary(rows) for m, rows in selected.items()}
            pairing[subset][arm] = losses(*(selected[m] for m in METHODS))
    paired = paired_runtime(times)
    files = ("scores.csv", "summary.json", "runtime.json")
    csv_file(report / files[0], points)
    save_json(report / files[1], dict(summaries=summaries, paired_publication=pairing))
    save_json(report / files[2], dict(rows=times, filtered_minus_strict=paired))
    save_json(
        report / "score-lock.json",
        dict(
            files={name: _sha(report / name) for name in files},
            prediction_lock_sha256=_sha(report / "prediction-lock.json"),
            score_program_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=REPORT)
    publish(parser.parse_args().report)
