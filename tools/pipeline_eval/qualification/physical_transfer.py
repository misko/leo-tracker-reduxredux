"""Bind and score anonymous measured StarLoc track packets in isolated workers."""

import argparse
import gzip
import json
import os
import secrets
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from .cold_missing import _sandbox

STUDY = ROOT / "reports/2026_11_18_blind_regional_receiver"
OUTPUT = ROOT / "reports/2026_11_19_short_receiver/physical-transfer"
SOLVER = Path(__file__).with_name("physical_transfer_solver.py")
CPU = (10, 11)
MODES = ("global", "supplied-tile", "omitted-tile")
METHOD = "anonymous_beacon_arcs"
TRACK_FIELDS = {"channel", "receiver", "rf_hz", "times", "values"}
OBS_FIELDS = {"anchor_utc_ns", "cutoff_utc_ns", "duration_s", "catalog_timestamp_ns", "tracks"}
WORKER = """
import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

import solver

start = perf_counter()
request = json.load(sys.stdin)
if hashlib.sha256(Path(solver.__file__).read_bytes()).hexdigest() != request['solver_sha256']:
    raise ValueError('the isolated solver differs from the predeclared release')
position = solver.solve(request['observation'], request['catalogue'], tile=request.get('tile'))
json.dump(dict(id=request['id'], result=position, wall_s=perf_counter()-start), sys.stdout,
          separators=(',', ':'), allow_nan=False)
"""


def _read(path, digest=None):
    raw = path.read_bytes()
    if digest is not None and sha256(raw).hexdigest() != digest:
        raise ValueError(f"frozen input hash mismatch for {path.name}")
    return raw


def _verified_truth(receipt):
    return _read(STUDY / "field_private/truth.json", receipt["sealed_truth_sha256"])


def cohort(captures):
    """Select one release-ordered occurrence for each of the last four groups."""
    first = {}
    for row in captures:
        first.setdefault(row["site_group"], row["pair"])
    return [(group, first[group]) for group in sorted(first)[-4:]]


def packet(alias, observation, catalogue, implementation, tile):
    if (
        set(observation) != OBS_FIELDS
        or any(set(t) != TRACK_FIELDS for t in observation["tracks"])
        or observation["catalog_timestamp_ns"] > observation["cutoff_utc_ns"]
    ):
        raise ValueError(
            "an anonymous capture contains undeclared fields or future orbit authority"
        )
    value = dict(
        id=alias, observation=observation, catalogue=catalogue, solver_sha256=implementation
    )
    if tile is not None:
        value["tile"] = tile
    return encoded(value)


def stage():
    public = STUDY / "public_field"
    manifest = json.loads((STUDY / "field-receipt.json").read_bytes())
    # The controller routes published offer conditions and the containing-tile ID.
    # It discards the geographic truth fields before constructing any request.
    route_fields = ("id", "condition", "pair", "site_group", "true_region")
    routing = [
        {key: row[key] for key in route_fields}
        for row in json.loads(_verified_truth(manifest))["cases"]
    ]
    captures = json.loads((STUDY / "field_private/source_provenance.json").read_bytes())["captures"]
    implementation = sha256(SOLVER.read_bytes()).hexdigest()
    staged = []
    groups = cohort(captures)
    if len(groups) != 4:
        raise ValueError("four distinct physical site groups are required")
    for group, pair in groups:
        arms = {
            r["condition"]: r for r in routing if r["pair"] == pair and r["site_group"] == group
        }
        if set(arms) != {"present", "missing"}:
            raise ValueError("captured site lacks its paired frozen offers")
        present, missing = (arms[k] for k in ("present", "missing"))
        pub, omitted = (
            json.loads(
                _read(
                    public / "queries" / f"{r['id']}.json", manifest["public_query_sha256"][r["id"]]
                )
            )
            for r in (present, missing)
        )
        if pub["observation"] != omitted["observation"] or pub["catalog"] != omitted["catalog"]:
            raise ValueError("the frozen queries do not match the same physical capture")
        (correct,) = [r["center"] for r in pub["regions"] if r["id"] == present["true_region"]]
        wrong = omitted["regions"][0]["center"]
        observation = json.loads(
            _read(public / "observations" / f"{pub['observation']}.json", pub["observation"])
        )
        catalog = _read(public / "orbits" / f"{pub['catalog']}.tle", pub["catalog"]).decode("ascii")
        for mode, tile in zip(MODES, (None, correct, wrong), strict=True):
            alias = secrets.token_hex(16)
            request = packet(alias, observation, catalog, implementation, tile)
            staged.append(
                (
                    dict(
                        alias=alias,
                        mode=mode,
                        site_group=group,
                        original_case=present["id"],
                        observation_sha256=pub["observation"],
                        catalogue_sha256=pub["catalog"],
                        input_sha256=sha256(request).hexdigest(),
                        tile_center=tile,
                    ),
                    request,
                )
            )
    return staged, implementation, manifest["sealed_truth_sha256"]


def _run(cpu, binding, request, implementation):
    start = perf_counter()
    command = _sandbox(cpu, [SOLVER])
    command[-1] = WORKER
    try:
        proc = subprocess.run(command, input=request, capture_output=True, timeout=90, check=True)
        row = json.loads(proc.stdout)
        if row["id"] != binding["alias"]:
            raise ValueError("the isolated worker returned a different opaque alias")
    except (subprocess.SubprocessError, OSError) as error:
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        detail = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-1400:]
        row = dict(
            id=binding["alias"],
            result=dict(
                status=status,
                reason=detail or str(error),
                metrics={},
                boundary="Prepared anonymous tracks and causal TLE to receiver decision",
                arms={arm: {"latlon": None, "forced_latlon": None} for arm in ARMS},
            ),
        )
    validate_result(row["result"])
    print(binding["site_group"], binding["mode"], row["result"]["status"], flush=True)
    return dict(
        row,
        method=METHOD,
        mode=binding["mode"],
        cpu=cpu,
        worker_wall_s=perf_counter() - start,
        input_sha256=binding["input_sha256"],
        implementation_sha256=implementation,
    )


def predict(output):
    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ("plan.json", "positions.jsonl.gz", "scores.json")):
        raise ValueError("use a new output directory for a new truth-separated evaluation")
    jobs, implementation, truth_sha = stage()
    plan = dict(
        cpus=CPU,
        implementation_sha256=implementation,
        scoring_truth_sha256=truth_sha,
        cases=[binding for binding, _ in jobs],
    )
    save_json(output / "plan.json", plan)

    def run(index, cpu):
        return [_run(cpu, b, raw, implementation) for b, raw in jobs[index :: len(CPU)]]

    with ThreadPoolExecutor(max_workers=len(CPU)) as workers:
        runs = [workers.submit(run, index, cpu) for index, cpu in enumerate(CPU)]
        rows = {r["id"]: r for run in runs for r in run.result()}
    ordered = (rows[binding["alias"]] for binding, _ in jobs)
    payload = gzip.compress(b"".join(encoded(row) + b"\n" for row in ordered), mtime=0)
    write(output / "positions.jsonl.gz", payload)
    save_json(
        output / "prediction-lock.json",
        dict(
            plan_sha256=sha256((output / "plan.json").read_bytes()).hexdigest(),
            positions_sha256=sha256(payload).hexdigest(),
        ),
    )


def score(output):
    lock = json.loads((output / "prediction-lock.json").read_bytes())
    plan = json.loads(_read(output / "plan.json", lock["plan_sha256"]))
    path = output / "positions.jsonl.gz"
    _read(path, lock["positions_sha256"])
    predictions = read_predictions(path)
    if set(predictions) != {r["alias"] for r in plan["cases"]}:
        raise ValueError("sealed prediction cohort changed")
    labels = {
        r["id"]: r
        for r in json.loads(
            _read(
                STUDY / "field_private/truth.json",
                plan["scoring_truth_sha256"],
            )
        )["cases"]
    }
    rows = []
    for binding in plan["cases"]:
        prediction = predictions[binding["alias"]]
        if (
            binding["input_sha256"] != prediction["input_sha256"]
            or binding["mode"] != prediction["mode"]
            or prediction["implementation_sha256"] != plan["implementation_sha256"]
        ):
            raise ValueError("sealed prediction's declared input identity differs")
        truth = labels[binding["original_case"]]
        if truth["site_group"] != binding["site_group"]:
            raise ValueError("scoring alias moved to another physical subject")
        result = prediction["result"]
        for arm in ARMS:
            endpoint = result["arms"][arm]
            loc = endpoint.get("latlon")
            rows.append(
                dict(
                    id=binding["alias"],
                    method=METHOD,
                    mode=binding["mode"],
                    arm=arm,
                    site_group=binding["site_group"],
                    status=result["status"],
                    publication=loc is not None,
                    false_publication=loc is not None and binding["mode"] == "omitted-tile",
                    published_error_km=distance_km(loc, truth["latlon"]),
                    forced_error_km=distance_km(endpoint.get("forced_latlon"), truth["latlon"]),
                    tile_center_error_km=distance_km(binding["tile_center"], truth["latlon"]),
                    held_rf_rms_hz=endpoint.get("rf_rms_hz"),
                    validation_lead=result["metrics"].get("validation_lead"),
                    wall_s=prediction["worker_wall_s"],
                )
            )
    summary = {}
    for mode in MODES:
        values = [r for r in rows if r["mode"] == mode and r["arm"] == "c0"]
        summary[mode] = dict(
            attempts=len(values),
            publications=sum(r["publication"] for r in values),
            false_publications=sum(r["false_publication"] for r in values),
            published_error_km=distribution(r["published_error_km"] for r in values),
            forced_error_km=distribution(r["forced_error_km"] for r in values),
            prior_center_error_km=distribution(r["tile_center_error_km"] for r in values),
            wall_s=distribution(r["wall_s"] for r in values),
        )
    save_json(output / "scores.json", dict(rows=rows, summary=summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("predict", "score"))
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.action == "predict":
        if not set(CPU) <= os.sched_getaffinity(0):
            parser.error("use the two preregistered worker CPUs")
        predict(args.out)
    else:
        score(args.out)


if __name__ == "__main__":
    main()
