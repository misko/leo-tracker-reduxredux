"""Compare completed real deadline workers to the sealed, independently run solvers."""

import argparse
import math
from pathlib import Path

from .. import corpus
from ..__main__ import local_output, read_predictions, save_json
from ..scoring import ARMS, distance_km, validate_result
from . import deadline_live as live
from . import roof_completion
from .full_receiver_comparison import read, require_fields, seal, sha
from .prefix_figures import csv_file


def check_run(row, key, lock, controls):
    ident, total, cpu = live.CASES[key]
    require_fields(row, dict(id=ident, key=key, total_s=total, cpu=cpu, plan_sha256=lock))
    names = dict(zip(("compact", "smooth"), live.METHODS, strict=True))
    calls = row["calls"]
    sequence = [c["method"] for c in calls]
    if (
        sequence not in (["compact"], ["compact", "smooth"])
        or {names[name] for name in sequence} != row["measurements"].keys()
    ):
        raise ValueError("inconsistent deadline worker sequence")
    elapsed = row["elapsed_s"]
    if (
        not math.isfinite(elapsed)
        or sum(call["wall_s"] for call in calls) > elapsed
        or calls[0]["budget_s"] > total - live.deadline_receiver.RESERVE_S
        or (len(calls) == 2 and calls[1]["budget_s"] > total - calls[0]["wall_s"])
    ):
        raise ValueError("deadline workers exceed the recorded time allowances")
    for call in calls:
        name = call["method"]
        worker = row["measurements"][names[name]]
        require_fields(worker, {"id": ident})
        authority = controls[name][ident]
        for field in ("native_sha256", "catalog_sha256", "tile"):
            if row[field] != authority[field]:
                raise ValueError("deadline solver and archive have different inputs")
        expected = live.classify(worker) if name == "compact" else worker["result"]
        if (
            call["worker_status"] != expected["status"]
            or not math.isfinite(call["budget_s"])
            or not 0 < call["budget_s"] <= total
            or not math.isfinite(call["wall_s"])
            or call["wall_s"] < 0
            or call["late"] != (call["wall_s"] > call["budget_s"])
            or call["status"] != ("timed_out" if call["late"] else expected["status"])
        ):
            raise ValueError("deadline outcome is inconsistent with the numerical process")
        if name == "smooth" and worker["result"]["status"] in ("ok", "withheld"):
            receipt = worker["input_binding"]
            for field in ("native_sha256", "catalog_sha256", "track_config_sha256", "tile"):
                if receipt[field] != row[field]:
                    raise ValueError("portable numerical process used different native inputs")
    validate_result(row["result"])
    final = calls[-1]
    if row["selected"] == "none":
        if row["result"]["status"] != "timed_out" or not final["late"]:
            raise ValueError("a late worker cannot publish a position")
    elif row["selected"] != final["method"] or final["late"] or row["result"] != expected:
        raise ValueError("published result differs from its timely solver")
    if len(calls) == 2 and calls[0]["status"] not in ("failed", "timed_out"):
        raise ValueError("fallback requires a numerical failure or timeout")


def publish(output):
    plan = read(output / "plan.json")
    if plan != live.plan():
        raise ValueError("live controller source changed")
    names = ("plan.json", *(f"{key}.json" for key in live.CASES))
    prediction_file = output / "prediction-lock.json"
    receipt = {"files": {f: sha(output / f) for f in names}}
    if prediction_file.exists() and read(prediction_file) != receipt:
        raise ValueError("live predictions differ from their original seal")
    save_json(prediction_file, receipt)
    archive = roof_completion.REPORT
    filename = {"compact": "all159-one.jsonl.gz", "smooth": "all159-stock.jsonl.gz"}
    seal(archive, "all159-figure-lock.json", tuple(filename.values()))
    controls = {method: read_predictions(archive / name) for method, name in filename.items()}
    runs = {key: read(output / f"{key}.json") for key in live.CASES}
    for key, row in runs.items():
        check_run(row, key, sha(output / "plan.json"), controls)
    refs = {r["id"]: r for r in corpus.references("ds26-all159")}
    scores, charts = [], []
    for total in sorted({r["total_s"] for r in runs.values()}):
        subset = [r for r in runs.values() if r["total_s"] == total]
        cases = [r["id"] for r in subset]
        positions = []
        for row in subset:
            ident = row["id"]
            series = {
                "deadline": row["result"],
                **{method: controls[method][ident]["result"] for method in controls},
            }
            for method, result in series.items():
                positions.append(
                    {
                        **{k: row[k] for k in ("id", "native_sha256", "catalog_sha256", "tile")},
                        "method": method,
                        "result": result,
                    }
                )
                for arm in ARMS:
                    endpoint = result.get("arms", {}).get(arm, {})
                    scores.append(
                        dict(
                            case=ident,
                            total_s=total,
                            arm=arm,
                            method=method,
                            selected=row["selected"] if method == "deadline" else method,
                            status=result["status"],
                            error_km=distance_km(endpoint.get("latlon"), refs[ident]["truth"]),
                            rf_rms_hz=endpoint.get("rf_rms_hz"),
                            held_score=endpoint.get("held_score"),
                            live_wall_s=row["elapsed_s"] if method == "deadline" else None,
                        )
                    )
            if row["result"]["status"] == "ok":
                selected = controls[row["selected"]][ident]["result"]
                for arm in ARMS:
                    for field in ("latlon", "rf_rms_hz"):
                        if selected["arms"][arm][field] != row["result"]["arms"][arm][field]:
                            raise ValueError("fresh solver did not reproduce its archive endpoint")
        source = f"positions-{total}.jsonl.gz"
        roof_completion.pack(output / source, positions)
        receipt = f"figure-{total}.json"
        members = ("prediction-lock.json", *names, source)
        save_json(output / receipt, dict(cases=cases, files={n: sha(output / n) for n in members}))
        charts.append(
            dict(
                id=f"deadline_live-{total}s",
                method="deadline_live",
                scope="roof",
                cases=cases,
                seal=receipt,
                provenance=["prediction-lock.json", *names],
                title=f"Position fixes with a {total}-second deadline",
                caption="Real pinned workers started with archived detections. Both calibration "
                "arms followed the same decision. The two standalone controls use the same "
                "recordings and original search region.",
                series=[
                    dict(
                        key=key,
                        file=source,
                        value=method,
                        label=label,
                        match=["native_sha256", "catalog_sha256", "tile"],
                    )
                    for key, method, label in (
                        ("one", "deadline", f"Live deadline · {total} s"),
                        ("stock", "compact", "Compact v5 · standalone"),
                        ("all_visits", "smooth", "Smooth clock · standalone"),
                    )
                ],
            )
        )
    csv_file(output / "scores.csv", scores)
    save_json(output / "figures.json", dict(version=1, charts=charts))
    save_json(
        output / "score-lock.json",
        dict(
            independent_controls=sha(archive / "all159-figure-lock.json"),
            files={
                n: sha(output / n) for n in ("prediction-lock.json", "scores.csv", "figures.json")
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=live.REPORT)
    publish(local_output(parser.parse_args().out))
