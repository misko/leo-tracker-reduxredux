"""Replay the sealed measured StarLoc cohort using portable Doppler curvature."""

import argparse
import gzip
import json
import subprocess
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import physical_transfer as prior
from .screening_physical_solver import BOUNDARY

OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/physical"
CPU = 7
METHOD = "affine_beacon_curvature"
SOLVER = Path(__file__).with_name("screening_physical_solver.py")
REFERENCE = "/worker/tools/pipeline_eval/qualification/physical_transfer_solver.py"


def digest(raw):
    return sha256(raw).hexdigest()


def stage(output):
    old = json.loads((prior.OUTPUT / "prediction-lock.json").read_bytes())
    previous = json.loads(prior._read(prior.OUTPUT / "plan.json", old["plan_sha256"]))
    if digest(prior.SOLVER.read_bytes()) != previous["implementation_sha256"]:
        raise ValueError("the matched earlier geometry source changed")
    source = dict(
        solver_sha256=digest(SOLVER.read_bytes()),
        reference_geometry_sha256=previous["implementation_sha256"],
        prior_plan_sha256=old["plan_sha256"],
        harness_sha256=digest(Path(__file__).read_bytes()),
        protocol_sha256=digest((output / "PROTOCOL.md").read_bytes()),
    )
    jobs = []
    public = prior.STUDY / "public_field"
    for row in previous["cases"]:
        obs, catalogue = (row[key] for key in ("observation_sha256", "catalogue_sha256"))
        data = json.loads(prior._read(public / "observations" / f"{obs}.json", obs))
        tles = prior._read(public / "orbits" / f"{catalogue}.tle", catalogue).decode("ascii")
        payload = prior.packet(
            row["alias"], data, tles, source["solver_sha256"], row["tile_center"]
        )
        jobs.append((dict(row, input_sha256=digest(payload)), payload))
    if len(jobs) != 12 or len({r["alias"] for r, _ in jobs}) != len(jobs):
        raise ValueError("expected the same twelve distinct measured-site queries")
    return jobs, source, previous["scoring_truth_sha256"]


def run_one(binding, payload, solver_sha):
    start = perf_counter()
    command = prior._sandbox(CPU, [SOLVER])
    command[-4:-4] = ["--ro-bind", str(prior.SOLVER), REFERENCE]
    command[-1] = prior.WORKER
    try:
        process = subprocess.run(
            command, input=payload, capture_output=True, timeout=40, check=True
        )
        row = json.loads(process.stdout)
        if row["id"] != binding["alias"]:
            raise ValueError("unexpected query identity")
    except (subprocess.SubprocessError, OSError, ValueError) as error:
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        message = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-1200:]
        row = dict(
            id=binding["alias"],
            result=dict(
                status=status,
                boundary=BOUNDARY,
                reason=message or str(error),
                metrics={},
                arms={arm: {"latlon": None, "forced_latlon": None} for arm in ARMS},
            ),
        )
    validate_result(row["result"])
    elapsed = perf_counter() - start
    print(
        binding["site_group"],
        binding["mode"],
        row["result"]["status"],
        round(elapsed, 3),
        flush=True,
    )
    return dict(
        row,
        method=METHOD,
        mode=binding["mode"],
        cpu=CPU,
        worker_wall_s=elapsed,
        input_sha256=binding["input_sha256"],
        implementation_sha256=solver_sha,
    )


def predict(output):
    if (output / "prediction-lock.json").exists():
        raise FileExistsError("the curvature transfer run is sealed")
    jobs, source, truth = stage(output)
    save_json(output / "source-lock.json", source)
    save_json(
        output / "plan.json",
        dict(
            cpus=[CPU],
            implementation_sha256=source["solver_sha256"],
            scoring_truth_sha256=truth,
            cases=[row for row, _ in jobs],
        ),
    )
    rows = [run_one(row, payload, source["solver_sha256"]) for row, payload in jobs]
    payload = gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0)
    write(output / "positions.jsonl.gz", payload)
    save_json(
        output / "prediction-lock.json",
        dict(
            positions_sha256=digest(payload),
            plan_sha256=digest((output / "plan.json").read_bytes()),
            source_lock_sha256=digest((output / "source-lock.json").read_bytes()),
        ),
    )


def score(output):
    lock = json.loads((output / "prediction-lock.json").read_bytes())
    plan = json.loads(prior._read(output / "plan.json", lock["plan_sha256"]))
    prior._read(output / "source-lock.json", lock["source_lock_sha256"])
    path = output / "positions.jsonl.gz"
    prior._read(path, lock["positions_sha256"])
    predictions = read_predictions(path)
    if set(predictions) != {r["alias"] for r in plan["cases"]}:
        raise ValueError("measured cohort mismatch")
    truth_raw = prior._read(prior.STUDY / "field_private/truth.json", plan["scoring_truth_sha256"])
    labels = {row["id"]: row for row in json.loads(truth_raw)["cases"]}
    rows = []
    for binding in plan["cases"]:
        entry = predictions[binding["alias"]]
        label = labels[binding["original_case"]]
        if (
            entry["input_sha256"] != binding["input_sha256"]
            or entry["mode"] != binding["mode"]
            or entry["implementation_sha256"] != plan["implementation_sha256"]
            or label["site_group"] != binding["site_group"]
        ):
            raise ValueError("input, source or scoring binding mismatch")
        for arm, endpoints in entry["result"]["arms"].items():
            published, forced = endpoints["latlon"], endpoints.get("forced_latlon")
            rows.append(
                dict(
                    id=entry["id"],
                    method=METHOD,
                    mode=entry["mode"],
                    arm=arm,
                    site_group=label["site_group"],
                    status=entry["result"]["status"],
                    publication=published is not None,
                    false_publication=published is not None and entry["mode"] == "omitted-tile",
                    published_error_km=distance_km(published, label["latlon"]),
                    forced_error_km=distance_km(forced, label["latlon"]),
                    tile_center_error_km=distance_km(binding["tile_center"], label["latlon"]),
                    held_rf_rms_hz=endpoints.get("rf_rms_hz"),
                    validation_lead=entry["result"]["metrics"].get("validation_lead"),
                    wall_s=entry["worker_wall_s"],
                )
            )
    summary = {}
    for mode in prior.MODES:
        selected = [row for row in rows if row["mode"] == mode and row["arm"] == "c0"]
        summary[mode] = dict(
            attempts=len(selected),
            publications=sum(r["publication"] for r in selected),
            false_publications=sum(r["false_publication"] for r in selected),
            **{
                key: distribution(r[key] for r in selected)
                for key in (
                    "published_error_km",
                    "forced_error_km",
                    "tile_center_error_km",
                    "wall_s",
                )
            },
        )
    save_json(output / "scores.json", dict(rows=rows, summary=summary))
    save_json(
        output / "score-lock.json",
        dict(
            scores_sha256=digest((output / "scores.json").read_bytes()),
            prediction_lock_sha256=digest((output / "prediction-lock.json").read_bytes()),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("predict", "score"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    arguments = parser.parse_args()
    (predict if arguments.phase == "predict" else score)(arguments.output)


if __name__ == "__main__":
    main()
