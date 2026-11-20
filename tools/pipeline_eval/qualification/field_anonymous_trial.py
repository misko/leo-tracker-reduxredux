"""Replay blinded anonymous StarLoc measurements and attach survey truth after sealing."""

import argparse
import csv
import json
import platform
import subprocess
import sys
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import perf_counter

import numpy as np
import scipy
from scipy.io import loadmat
from sgp4 import __version__ as sgp4_version
from sgp4 import api as sgp4_api
from sgp4 import wrapper

from ..__main__ import ROOT, encoded, read_predictions, save_json
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import field_anonymous_doppler as receiver
from . import physical_differences as extraction
from . import physical_transfer as authority
from .armijo_finish_results import pack

OUT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-support/field-anonymous"
SOLVER = Path(receiver.__file__)
CPU = 2
TIMEOUT_S = 75
DEV = {f"field-site-{i:02}" for i in range(1, 5)}
MODES = ("worldwide", "containing", "omitted")
METHOD = "field_anonymous_doppler"
WORKER = """
import hashlib
import json
import sys
from pathlib import Path
import solver

doc = json.load(sys.stdin)
actual = hashlib.sha256(Path(solver.__file__).read_bytes()).hexdigest()
if doc['solver_sha256'] != actual:
    raise ValueError('worker source differs from its predeclared release')
r = solver.solve(doc['observation'], doc['catalogue'], regions=doc['regions'])
json.dump(dict(id=doc['id'], result=r), sys.stdout, allow_nan=False)
"""


def digest(raw):
    return sha256(raw).hexdigest()


def from_mat(data):
    released = loadmat(BytesIO(data), variable_names=["main_tone_dict"])["main_tone_dict"].ravel()
    curves = [extraction.consolidate(w) for w in released]
    _, evidence = extraction.simultaneous(curves)
    copies = {
        min(pair["track_rows"], key=lambda i: (np.ptp(curves[i][0]), -i))
        for pair in evidence
        if pair["harmonic_like"]
    }
    tracks = []
    for i, (times, values) in enumerate(curves):
        if i in copies or len(times) < receiver.SAMPLES or times[-1] - times[0] < 12:
            continue
        pick = np.rint(np.linspace(0, len(times) - 1, receiver.SAMPLES)).astype(int)
        if times[-1] - times[pick[receiver.EARLY]] >= 3:
            tracks.append(dict(times=times[pick].tolist(), values=values[pick].tolist()))
    return tracks, len(curves), len(copies)


def runtime():
    provider = getattr(wrapper, "__file__", None)
    extensions = sorted(Path(provider).parent.glob("vallado_cpp*.so")) if provider else []
    return dict(
        python=sys.version,
        python_compiler=platform.python_compiler(),
        numpy=np.__version__,
        scipy=scipy.__version__,
        sgp4=sgp4_version,
        sgp4_accelerated=sgp4_api.accelerated,
        sgp4_extension_sha256={p.name: digest(p.read_bytes()) for p in extensions},
        machine=platform.machine(),
        cpu=CPU,
        threads=1,
    )


def stage(raw_root, out):
    base = authority.STUDY
    public = base / "public_field"
    receipt_path = base / "field-receipt.json"
    source_path = base / "field_private/source_provenance.json"
    receipt = json.loads(receipt_path.read_bytes())
    # Staging uses only which pre-existing paired query to route. The solve gets neither label.
    route = {
        (row["pair"], row["condition"]): row["id"]
        for row in json.loads(authority._verified_truth(receipt))["cases"]
    }
    captures = json.loads(source_path.read_bytes())["captures"]
    files = (
        SOLVER,
        Path(__file__),
        Path(extraction.__file__),
        Path(authority.__file__),
        base / "results/field/per_query.csv",
        receipt_path,
        source_path,
        out / "PROTOCOL.md",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
    )
    sources = {
        str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name: digest(p.read_bytes())
        for p in files
    }
    jobs, groups = [], set()
    solver_hash = digest(SOLVER.read_bytes())
    for capture in captures:
        group = capture["site_group"]
        part = "development" if group in DEV else "holdout"
        visit = "repeat" if group in groups else "primary"
        groups.add(group)
        queries, query_ids = {}, {}
        for mode, condition in zip(MODES[1:], ("present", "missing"), strict=True):
            key = route[capture["pair"], condition]
            query_ids[mode] = key
            queries[mode] = json.loads(
                authority._read(
                    public / "queries" / f"{key}.json", receipt["public_query_sha256"][key]
                )
            )
        first, second = (queries[k] for k in MODES[1:])
        if any(first[k] != second[k] for k in ("observation", "catalog")):
            raise ValueError("archived offers do not share capture and catalogue")
        obs, cat = first["observation"], first["catalog"]
        catalogue = authority._read(public / "orbits" / f"{cat}.tle", cat).decode("ascii")
        former = json.loads(authority._read(public / "observations" / f"{obs}.json", obs))
        mat = authority._read(
            raw_root / capture["date"] / "tracked_tones.mat", capture["track_file_sha256"]
        )
        tracks, original_count, duplicates = from_mat(mat)
        observation = {
            k: former[k]
            for k in (
                "anchor_utc_ns",
                "cutoff_utc_ns",
                "catalog_timestamp_ns",
                "duration_s",
            )
        } | {"arcs": tracks}
        for mode in MODES:
            tiles = queries[mode]["regions"] if mode in queries else []
            if tiles and (len(tiles) != 4 or any(r.get("width_km", 25) != 25 for r in tiles)):
                raise ValueError("a legacy full offer must be four 25 km tiles")
            opaque = digest(encoded([METHOD, obs, mode]))[:32]
            regions = [r["center"] for r in tiles] or None
            request = encoded(
                dict(
                    id=opaque,
                    observation=observation,
                    catalogue=catalogue,
                    regions=regions,
                    solver_sha256=solver_hash,
                )
            )
            jobs.append(
                (
                    dict(
                        id=opaque,
                        mode=mode,
                        cohort=part,
                        visit=visit,
                        site=group,
                        capture=capture["date"],
                        pair=capture["pair"],
                        query_id=query_ids.get(mode),
                        regions=tiles,
                        mat_sha256=capture["track_file_sha256"],
                        source_observation_sha256=obs,
                        catalogue_sha256=cat,
                        receiver_observation_sha256=digest(encoded(observation)),
                        input_sha256=digest(request),
                        source_curves=original_count,
                        harmonic_copy_curves=duplicates,
                        usable_curves=len(tracks),
                    ),
                    request,
                )
            )
    if len(jobs) != 33 or len(groups) != 8 or not groups > DEV:
        raise ValueError("qualification expects the complete pinned eight-site panel")
    jobs.sort(key=lambda j: (j[0]["cohort"], j[0]["capture"], MODES.index(j[0]["mode"])))
    lock = dict(
        sources=sources,
        runtime=runtime(),
        scoring_truth_sha256=receipt["sealed_truth_sha256"],
        timeout_s=TIMEOUT_S,
        queries=[p for p, _ in jobs],
    )
    return jobs, lock


def attempt(binding, request):
    cmd = authority._sandbox(CPU, [SOLVER])
    cmd[-1] = WORKER
    started = perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            input=request,
            capture_output=True,
            check=True,
            timeout=TIMEOUT_S,
        )
        row = json.loads(proc.stdout)
        if row["id"] != binding["id"]:
            raise ValueError("isolated worker returned the wrong opaque request ID")
    except (subprocess.SubprocessError, OSError) as error:
        detail = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-1400:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        row = dict(
            id=binding["id"],
            result=dict(
                status=status,
                reason=detail or str(error),
                metrics={},
                boundary=receiver.BOUNDARY,
                arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
            ),
        )
    validate_result(row["result"])
    print(binding["site"], binding["mode"], row["result"]["status"], flush=True)
    return dict(
        row,
        method=METHOD,
        mode=binding["mode"],
        worker_wall_s=perf_counter() - started,
        input_sha256=binding["input_sha256"],
        catalogue_sha256=binding["catalogue_sha256"],
    )


def predict(raw, out):
    if any((out / name).exists() for name in ("source-lock.json", "positions.jsonl.gz")):
        raise ValueError("choose an unused output directory for a new locked replay")
    jobs, lock = stage(raw, out)
    save_json(out / "source-lock.json", lock)
    start = perf_counter()
    rows = [attempt(*job) for job in jobs]
    pack(out, "positions.jsonl.gz", rows)
    names = ("source-lock.json", "positions.jsonl.gz")
    save_json(
        out / "prediction-lock.json",
        dict(
            files={name: digest((out / name).read_bytes()) for name in names},
            worker_batch_wall_s=perf_counter() - start,
        ),
    )


def _reference():
    with (authority.STUDY / "results/field/per_query.csv").open(newline="") as source:
        return {row["id"]: row for row in csv.DictReader(source)}


def score(out):
    lock = json.loads((out / "prediction-lock.json").read_bytes())
    for name, expected in lock["files"].items():
        authority._read(out / name, expected)
    plan = json.loads((out / "source-lock.json").read_bytes())
    receipt = json.loads((authority.STUDY / "field-receipt.json").read_bytes())
    if receipt["sealed_truth_sha256"] != plan["scoring_truth_sha256"]:
        raise ValueError("scoring authority changed after sealing predictions")
    references = json.loads(authority._verified_truth(receipt))["cases"]
    truth = {row["pair"]: row for row in references if row["condition"] == "present"}
    older = _reference()
    prior_file = authority.STUDY / "results/field/per_query.csv"
    if digest(prior_file.read_bytes()) != plan["sources"][str(prior_file.relative_to(ROOT))]:
        raise ValueError("legacy comparison changed after freezing the new replay")
    observed = read_predictions(out / "positions.jsonl.gz")
    if set(observed) != {k["id"] for k in plan["queries"]}:
        raise ValueError("sealed position archive does not cover the ordered plan")
    rows = []
    for job in plan["queries"]:
        reference = truth[job["pair"]]
        if job["site"] != reference["site_group"]:
            raise ValueError("physical site differs between sealed routing and survey")
        row = observed[job["id"]]
        if any(row[k] != job[k] for k in ("input_sha256", "catalogue_sha256", "mode")):
            raise ValueError("sealed worker returned a different scientific input binding")
        validate_result(row["result"])
        r = row["result"]
        metrics, true = r["metrics"], reference["latlon"]
        index = metrics.get("best_region")
        tile = None if index is None else job["regions"][index]
        historical = older.get(job["query_id"], {})
        arm = r["arms"]["c0"]
        if arm != r["arms"]["fitted_c"]:
            raise ValueError("single-RF gauge must give identical numerical endpoints")
        rows.append(
            dict(
                job,
                status=r["status"],
                reason=r["reason"],
                published_error_km=distance_km(true, arm["latlon"]),
                forced_error_km=distance_km(true, arm.get("forced_latlon")),
                selected_center_error_km=None
                if tile is None
                else distance_km(true, tile["center"]),
                correct_region=None
                if job["mode"] != "containing"
                else bool(tile is not None and tile["id"] == reference["true_region"]),
                legacy_forced_error_km=float(historical["forced_rf_error_km"])
                if historical.get("forced_rf_error_km")
                else None,
                legacy_correct_region=historical.get("forced_rf_correct_region") == "True"
                if job["mode"] == "containing"
                else None,
                null_forced_error_km=distance_km(true, metrics.get("time_control_forced_latlon")),
                worker_wall_s=row["worker_wall_s"],
                metrics=metrics,
                arms={
                    name: dict(
                        km=distance_km(true, a["latlon"]),
                        forced_km=distance_km(true, a.get("forced_latlon")),
                        rf_hz=a.get("rf_rms_hz"),
                    )
                    for name, a in r["arms"].items()
                },
            )
        )
    summary = {}
    for cohort in ("development", "holdout", "all"):
        for mode in MODES:
            subset = [r for r in rows if r["mode"] == mode and cohort in ("all", r["cohort"])]
            summary[f"{cohort}/{mode}"] = dict(
                count=len(subset),
                published=sum(r["status"] == "ok" for r in subset),
                correct_region=sum(r["correct_region"] is True for r in subset),
                legacy_correct_region=sum(r["legacy_correct_region"] is True for r in subset),
                within_5km=sum(
                    r["published_error_km"] is not None and r["published_error_km"] <= 5
                    for r in subset
                ),
                **{
                    k: distribution(r[k] for r in subset)
                    for k in (
                        "forced_error_km",
                        "published_error_km",
                        "selected_center_error_km",
                        "legacy_forced_error_km",
                        "null_forced_error_km",
                        "worker_wall_s",
                    )
                },
                **{
                    k: distribution(r["metrics"].get(k) for r in subset)
                    for k in (
                        "held_capped_rms_hz",
                        "time_control_capped_rms_hz",
                        "spatial_margin_hz2",
                        "region_margin_hz2",
                        "solve_cpu_s",
                    )
                },
            )
    save_json(out / "scores.json", dict(rows=rows, summary=summary, calibration_arms=list(ARMS)))
    names = ("prediction-lock.json", "scores.json")
    save_json(
        out / "score-lock.json",
        dict(files={name: digest((out / name).read_bytes()) for name in names}),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("predict", "score"))
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    if args.stage == "predict":
        if args.raw is None:
            parser.error("predict requires --raw with the locally staged MAT files")
        predict(args.raw, args.out)
    else:
        score(args.out)


if __name__ == "__main__":
    main()
