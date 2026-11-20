"""Seal, score and chart the causal startup replay on both ordinary acquisitions."""

import argparse
import gzip
import json
from collections import Counter

from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import v5_causal_startup as startup
from . import causal_startup_replay as trial
from .full_receiver_comparison import read, require_fields, roster_matches, seal, sha
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

STOCK = "v5_direct_cavity"
METHOD = startup.METHOD
FILES = {"stock": "stock-positions.jsonl.gz", "early": "positions.jsonl.gz"}
WORK = (
    "initial_branches",
    "initial_arm_fits",
    "cavity_offered",
    "observations",
    "tracks",
    "compact_projections",
)


def timing(row):
    if "result_ready_ns" not in row:
        return dict(
            release_to_result_s=None,
            release_to_read_s=None,
            prepared_lead_s=None,
            preparation_wall_s=None,
            preparatory_wall_before_release_s=None,
            preparation_cpu_s=None,
            after_ready_cpu_s=None,
            idle_rss_kib=None,
            ready_rss_kib=None,
            peak_rss_kib=None,
            native_preparation_s=None,
            sky_s=None,
            history_s=None,
            forecast_s=None,
            reused=None,
            fitted_horizon_s=None,
        )
    seconds = 1e9
    release, read_at, end = (
        row[k] for k in ("input_released_ns", "input_received_ns", "result_ready_ns")
    )
    if (
        not row["prepare_started_ns"] <= row["prepare_ready_ns"] <= read_at <= end
        or release > read_at
    ):
        raise ValueError("invalid replay release chronology")
    metrics = row["result"]["metrics"]
    return dict(
        release_to_result_s=(end - release) / seconds,
        release_to_read_s=(read_at - release) / seconds,
        prepared_lead_s=(release - row["prepare_ready_ns"]) / seconds,
        preparation_wall_s=(row["prepare_ready_ns"] - row["prepare_started_ns"]) / seconds,
        preparatory_wall_before_release_s=max(
            0, min(release, row["prepare_ready_ns"]) - row["prepare_started_ns"]
        )
        / seconds,
        preparation_cpu_s=row["prepare_cpu_s"],
        after_ready_cpu_s=row["fitted_cpu_s"],
        idle_rss_kib=row["prep_rss_before_kib"],
        ready_rss_kib=row["prep_rss_ready_kib"],
        peak_rss_kib=row["rss_peak_kib"],
        native_preparation_s=metrics["stage_s"]["native_preparation"],
        sky_s=row["early_stages_s"].get("sky"),
        history_s=row["early_stages_s"].get("history"),
        forecast_s=row["early_stages_s"].get("forecast"),
        reused=metrics.get("early_orbit_reused"),
        fitted_horizon_s=metrics.get("final_track_horizon_s"),
    )


def checks(candidate, stock):
    a, b = (r["result"] for r in (candidate, stock))
    matches = {"same_status": a["status"] == b["status"]}
    if a["status"] == b["status"] == "ok":
        matches.update(
            both_positions_and_rms=a["arms"] == b["arms"],
            decisions=all(a["metrics"][k] == b["metrics"][k] for k in WORK),
            rf_frequency_scores=all(
                a["metrics"].get(f"{arm}_frequency_score")
                == b["metrics"].get(f"{arm}_frequency_score")
                for arm in ARMS
            ),
        )
    return dict(
        matches, exact_both_fixes=all(matches.values()) and "both_positions_and_rms" in matches
    )


def position_rows(plan, receipts):
    out = {key: {} for key in FILES}
    for row in receipts:
        ident, mode = row["id"], row["mode"]
        if ident in out[mode]:
            raise ValueError("a scientific attempt cannot be replaced")
        require_fields(row, {k: plan["rows"][ident][k] for k in (*trial.MATCH, "cpu")})
        validate_result(row["result"])
        roster_matches(row["result"]["arms"], ARMS, f"{ident} {mode}")
        out[mode][ident] = dict(row, method=METHOD if mode == "early" else STOCK)
    for key, records in out.items():
        roster_matches(records, plan["cases"], key)
    return out


def pack(path, rows):
    write(path, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))


def publish(plan_path, receipts, output):
    plan = read(plan_path)
    if plan["cases"] != list(trial.CASES) or plan["lead_s"] != trial.LEAD:
        raise ValueError("the sealed cases or delayed-input schedule changed")
    if any(r["source_lock_sha256"] != sha(plan_path) for r in receipts):
        raise ValueError("a worker attempt uses a different source lock")
    archive = trial.direct.REPORT
    released = seal(archive, "receipt.json", ("positions.jsonl.gz",))
    if sha(archive / "receipt.json") != plan["sources"]["direct_prediction_lock_sha256"]:
        raise ValueError("the earlier direct-cavity prediction lock changed")
    original = read_predictions(archive / "positions.jsonl.gz")
    if not set(plan["cases"]) <= set(released["cases"]):
        raise ValueError("the matched earlier direct-cavity archive is incomplete")
    methods = position_rows(plan, receipts)
    refs, _ = _frozen_roof()
    geometry, clocks, verdict = [], [], {}
    for ident in plan["cases"]:
        candidate, stock = (methods[m][ident] for m in ("early", "stock"))
        require_fields(original[ident], {k: candidate[k] for k in trial.MATCH})
        verdict[ident] = dict(
            same_release_experiment=checks(candidate, stock),
            stock_vs_archived=checks(stock, original[ident]),
        )
        for row in (candidate, stock):
            result = row["result"]
            clocks.append(
                dict(
                    id=ident,
                    method=row["method"],
                    cpu=row["cpu"],
                    status=result["status"],
                    launcher_wall_s=row["launcher_wall_s"],
                    **timing(row),
                )
            )
            for arm in ARMS:
                point = result["arms"][arm]
                geometry.append(
                    dict(
                        id=ident,
                        arm=arm,
                        method=row["method"],
                        status=result["status"],
                        position_error_km=distance_km(point["latlon"], refs[ident]["truth"]),
                        conditional_rms_hz=point.get("rf_rms_hz"),
                        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    )
                )
    for mode, name in FILES.items():
        pack(output / name, (methods[mode][i] for i in plan["cases"]))
    csv_file(output / "timing.csv", clocks)
    csv_file(output / "scores.csv", geometry)
    save_json(output / "comparison.json", verdict)
    write(output / "source-lock.json", plan_path.read_bytes())
    names = (*FILES.values(), "comparison.json", "timing.csv", "scores.csv")
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=plan["cases"],
            files={name: sha(output / name) for name in names},
            source_lock_sha256=sha(output / "source-lock.json"),
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="causal-startup",
                    method=METHOD,
                    scope="roof",
                    cases=plan["cases"],
                    title="Causal startup before factor release",
                    caption=(
                        "Genuine first-delivery clocks and a timed release of stored ordinary "
                        "factors. Both paths use the same compact cavity."
                    ),
                    seal="prediction-lock.json",
                    provenance=["comparison.json", "timing.csv", "scores.csv"],
                    source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                    series=[
                        dict(
                            key=key,
                            label=label,
                            file=FILES[mode],
                            value=method,
                            native_authority="ordinary",
                            match=list(trial.MATCH),
                        )
                        for key, label, mode, method in (
                            ("one", "Early causal orbit preparation", "early", METHOD),
                            ("stock", "After-release direct cavity", "stock", STOCK),
                        )
                    ],
                )
            ],
        ),
    )
    return Counter(r["status"] for r in clocks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=local_output)
    parser.add_argument("--published", type=local_output)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    if (args.work is None) == (args.published is None):
        parser.error("supply a fresh work directory or a published report")
    if args.work is not None:
        plan = args.work / "plan.json"
        attempts = [read(p) for p in sorted(args.work.glob("*/*/attempt.json"))]
    else:
        report = args.published
        plan = report / "source-lock.json"
        lock = seal(report, "prediction-lock.json", tuple(FILES.values()))
        require_fields(lock, dict(source_lock_sha256=sha(plan)))
        attempts = [
            row
            for name in FILES.values()
            for row in map(json.loads, gzip.decompress((report / name).read_bytes()).splitlines())
        ]
    publish(plan, attempts, args.out)


if __name__ == "__main__":
    main()
