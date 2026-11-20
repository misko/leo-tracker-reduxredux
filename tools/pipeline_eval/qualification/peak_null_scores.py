"""Score both arms of the sealed wide-factor selector and generate chart bindings."""

import gzip
import json
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km
from . import screening_figures
from .coherent_peak_scores import BASELINE, losses, point_row, result_summary
from .input_factor_bridge import _sha, check, read
from .peak_null_trial import DEVELOPMENT, METHODS, REPORT, RESERVE, SOURCE
from .prefix_figures import csv_file

CHART_ID = "peak-null-excess-six"


def chart_inputs(report):
    seal = report / "prediction-lock.json"
    lock = read(seal)
    for name, digest in lock["files"].items():
        check(report / name, digest)
    source = report / "predictions.jsonl.gz"
    rows = [json.loads(line) for line in gzip.decompress(source.read_bytes()).splitlines()]
    if len(rows) != len(lock["cases"]) * len(METHODS):
        raise ValueError("sealed trials do not cover both methods for every case")
    audit = report / "pilot-semantics-audit.json"
    if read(audit)["winner_changes_sha256"] != lock["files"]["winner-changes.json.gz"]:
        raise ValueError("semantics audit does not cover the sealed winner replacements")
    reserve = report / "reserve-predictions.jsonl.gz"
    payload = b"".join(encoded(row) + b"\n" for row in rows if row["id"] in RESERVE)
    write(reserve, gzip.compress(payload, mtime=0))
    common = ("prediction-lock.json", "factor-audit.json", "pilot-semantics-audit.json")
    for scope, cases, path in (("six", lock["cases"], source), ("reserve", RESERVE, reserve)):
        save_json(
            report / f"{scope}-figure-lock.json",
            dict(
                cases=list(cases),
                files={name: _sha(report / name) for name in (*common, path.name)},
            ),
        )
    write(report / "figures.json", (report / "figure-plan.json").read_bytes())


def score_row(ident, cohort, method, arm, result, truth, original):
    endpoint = result.get("arms", {}).get(arm, {})
    row = point_row(
        ident, cohort, method, arm, result["status"], result.get("reason"), endpoint, truth
    )
    error = row["error_km"]
    row["original_v5_error_km"] = original
    row["within_1p05_v5"] = error is not None and original is not None and error <= 1.05 * original
    row["within_1p10_v5"] = error is not None and original is not None and error <= 1.10 * original
    row["conditional_frequency_score"] = result.get("metrics", {}).get(f"{arm}_frequency_score")
    return row


def runtime(row, audit):
    result = row["result"]
    metrics = result["metrics"]
    finish = next(iter(row["runtime"]["finish"]), {})
    prep = metrics.get("stage_s", {}).get("native_preparation")
    overhead = audit["prefilter"] if row["method"] == METHODS[0] else dict(wall_s=0.0, cpu_s=0.0)
    return dict(
        id=row["id"],
        method=row["method"],
        status=result["status"],
        cpu=row["cpu"],
        standalone_wall_s=row["wall_s"],
        standalone_cpu_s=finish.get("cgroup_cpu_s"),
        peak_cgroup_bytes=finish.get("cgroup_peak"),
        prefilter_cpu_s=overhead["cpu_s"],
        prefilter_wall_s=overhead["wall_s"],
        native_preparation_s=prep,
        total_preparation_s=None if prep is None else prep + overhead["wall_s"],
        tracks=metrics.get("tracks"),
        observations=metrics.get("observations"),
        compact_projections=metrics.get("compact_projections"),
        observed_stage_starts_s={x["name"]: x["wall_s"] for x in row["runtime"]["stage"]},
    )


def earlier_wide_parity(unchanged):
    archive = SOURCE / "positions.jsonl.gz"
    check(archive, read(SOURCE / "prediction-lock.json")["files"][archive.name])
    sealed = [json.loads(line) for line in gzip.decompress(archive.read_bytes()).splitlines()]
    earlier = {p["id"]: p for p in sealed if p["method"] == "regional_wide_full_iq"}
    if earlier.keys() != unchanged.keys():
        raise ValueError("historical wide and new unchanged runs use different rosters")
    output = {}
    for ident, new in unchanged.items():
        old = earlier[ident]
        if new["native_sha256"] != old["native_sha256"]:
            raise ValueError("historical wide endpoint used different detector output")
        output[ident] = {
            arm: {
                field: new["result"].get("arms", {}).get(arm, {}).get(field)
                == old["result"]["arms"][arm].get(field)
                for field in ("latlon", "rf_rms_hz")
            }
            for arm in ARMS
        }
    return output


def publish(report=REPORT):
    chart_inputs(report)
    (study,) = screening_figures.charts([CHART_ID], report)
    _, frozen = screening_figures._roof_authority()
    requests = read(report / "requests.json")
    factor_counts = read(report / "factor-audit.json")
    points, times = [], []
    for ident in sorted(study.cases):
        ref = study.references[ident]
        truth = ref["truth"]
        history = ref["reference"]["baseline"]
        cohort = "development" if ident in DEVELOPMENT else "reserve"
        original = {arm: distance_km(history[arm].get("latlon"), truth) for arm in ARMS}
        for method, key in zip(METHODS, ("one", "stock"), strict=True):
            row = study.predictions[key][ident]
            if any(row[k] != v for k, v in requests[ident][method].items()):
                raise ValueError(f"worker input changed after seal for {ident}")
            if row["expected_capture_era_native_sha256"] != frozen[ident]["native"]["sha256"]:
                raise ValueError(f"original v5 source binding differs for {ident}")
            times.append(runtime(row, factor_counts[ident]))
            for arm in ARMS:
                points.append(
                    score_row(ident, cohort, method, arm, row["result"], truth, original[arm])
                )
        for arm in ARMS:
            archived = dict(status=history[arm]["status"], arms={arm: history[arm]})
            points.append(score_row(ident, cohort, BASELINE, arm, archived, truth, original[arm]))
    results, coverage = {}, {}
    for subset in ("all", "development", "reserve"):
        results[subset], coverage[subset] = {}, {}
        for arm in ARMS:
            subset_rows = {
                method: [
                    p
                    for p in points
                    if p["method"] == method
                    and p["arm"] == arm
                    and (subset == "all" or p["cohort"] == subset)
                ]
                for method in (*METHODS, BASELINE)
            }
            results[subset][arm] = {
                key: dict(
                    result_summary(rows),
                    within_1p05_v5=sum(r["within_1p05_v5"] for r in rows),
                    within_1p10_v5=sum(r["within_1p10_v5"] for r in rows),
                )
                for key, rows in subset_rows.items()
            }
            coverage[subset][arm] = losses(*(subset_rows[m] for m in METHODS))
    sources = (
        "scores.csv",
        "runtime.json",
        "summary.json",
        "six-figure-lock.json",
        "reserve-figure-lock.json",
        "figures.json",
        "pilot-semantics-audit.json",
    )
    csv_file(report / "scores.csv", points)
    save_json(report / "runtime.json", times)
    save_json(
        report / "summary.json",
        dict(
            results=results,
            paired_publications=coverage,
            earlier_wide_exact_replay_parity=earlier_wide_parity(study.predictions["stock"]),
        ),
    )
    save_json(
        report / "score-lock.json",
        dict(
            files={name: _sha(report / name) for name in sources},
            prediction_lock_sha256=_sha(report / "prediction-lock.json"),
            scorer_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    publish()
