"""Prepare and evaluate blinded single-offer anonymous paired-beacon replays."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.io import loadmat

from ..__main__ import ROOT, encoded, read_predictions, save_json
from ..reference import grid
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import anonymous_frozen_pairing_solver as solver
from . import physical_differences as earlier
from . import physical_differences_solver as baseline_solver
from . import physical_transfer as authority
from .armijo_finish_results import pack

REPORT = ROOT / "reports/2026_11_19_receiver_screening/next/anonymous-transfer"
METHOD = "anonymous_frozen_pairing"
MODES = ("supplied-tile", "omitted-tile", "shuffled-late")
CPUS = (7, 8)
SOLVER = Path(solver.__file__)
PRIOR = earlier.OUTPUT
POSITION_FILE = "positions.jsonl.gz"
SOURCE_FILE = "source-lock.json"
digest = earlier.digest


def late_control(pair):
    n = baseline_solver.train_count(pair["times"])
    return dict(pair, **{
        key: pair[key][:n] + solver.rotate_late(np.asarray(pair[key][n:])).tolist()
        for key in ("first_hz", "second_hz")
    })


def early_hash(pairs):
    data = []
    for pair in pairs:
        n = baseline_solver.train_count(pair["times"])
        data.append({key: values[:n] for key, values in pair.items()})
    return digest(encoded(data))


def locked_dependencies():
    paths = (SOLVER, Path(grid.__file__), Path(baseline_solver.__file__),
             Path(earlier.__file__), Path(authority.__file__), Path(__file__))
    return {p.name: digest(p.read_bytes()) for p in paths}


def stage(raw, out):
    base = authority.STUDY
    public = base / "public_field"
    field = json.loads((base / "field-receipt.json").read_bytes())
    captures = json.loads((base / "field_private/source_provenance.json").read_bytes())
    fields = ("id", "pair", "condition", "site_group", "true_region")
    route = [{key: row[key] for key in fields}
             for row in json.loads(authority._verified_truth(field))["cases"]]
    source = dict(
        sources=locked_dependencies(),
        protocol_sha256=digest((out / "PROTOCOL.md").read_bytes()),
        measured_manifest_sha256=digest((base / "field-receipt.json").read_bytes()),
        reference_sha256=field["sealed_truth_sha256"],
        baseline_prediction_sha256=digest((PRIOR / "prediction-lock.json").read_bytes()),
        cpus=list(CPUS), timeout_s=30,
    )
    seen, jobs = set(), []
    for capture in captures["captures"]:
        group = capture["site_group"]
        cohort = "repeat" if group in seen else "primary"
        seen.add(group)
        options = {r["condition"]: r for r in route if r["pair"] == capture["pair"]}
        present, absent = (options[k] for k in ("present", "missing"))
        present_offer, absent_offer = [json.loads(authority._read(
            public / "queries" / f"{item['id']}.json", field["public_query_sha256"][item["id"]]
        )) for item in (present, absent)]
        if any(present_offer[k] != absent_offer[k] for k in ("observation", "catalog")):
            raise ValueError("matched physical offers disclose different recorded inputs")
        obs_hash, cat_hash = (present_offer[k] for k in ("observation", "catalog"))
        obs_path = public / "observations" / f"{obs_hash}.json"
        observed = json.loads(authority._read(obs_path, obs_hash))
        catalogue = authority._read(public / "orbits" / f"{cat_hash}.tle", cat_hash).decode("ascii")
        raw_sha = capture["track_file_sha256"]
        data = authority._read(raw / capture["date"] / "tracked_tones.mat", raw_sha)
        arrays = loadmat(BytesIO(data), variable_names=["main_tone_dict"])["main_tone_dict"].ravel()
        arcs = [earlier.consolidate(window) for window in arrays]
        chosen, _ = earlier.simultaneous(arcs)
        pairs = chosen[:2]
        clock = {key: observed[key] for key in (
            "anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns", "duration_s"
        )}
        if any(t[0] < 0 or t[-1] > clock["duration_s"] for t, _ in arcs):
            raise ValueError("anonymous measurements fall outside their recorded acquisition")
        (known_center,) = [r["center"] for r in present_offer["regions"]
                           if r["id"] == present["true_region"]]
        centers = (known_center, absent_offer["regions"][0]["center"], known_center)
        for mode, center in zip(MODES, centers, strict=True):
            trial_pairs = [late_control(pair) for pair in pairs] if mode == MODES[2] else pairs
            ident = digest(encoded([METHOD, obs_hash, mode]))[:32]
            payload = encoded(dict(
                id=ident, tile=center, catalogue=catalogue,
                observation=dict(clock, rf_hz=earlier.RF_HZ, pairs=trial_pairs),
                solver_sha256=source["sources"][SOLVER.name],
            ))
            jobs.append((dict(
                id=ident, site=group, cohort=cohort, capture=capture["date"], mode=mode,
                tile_center=center, original_case=present["id"], measured_mat_sha256=raw_sha,
                observation_sha256=obs_hash, catalogue_sha256=cat_hash,
                input_sha256=digest(payload), early_data_sha256=early_hash(trial_pairs),
                retained_pairs=len(pairs), anonymous_arcs=len(arcs),
            ), payload))
    if len(jobs) != 33 or len(seen) != 8 or sum(r["cohort"] == "repeat" for r, _ in jobs) != 9:
        raise ValueError("this study requires eight primary sites and three second captures")
    return jobs, source


def one(binding, payload, cpu):
    started = perf_counter()
    command = authority._sandbox(cpu, [SOLVER])
    command[-4:-4] = [
        "--ro-bind", str(Path(grid.__file__)), "/worker/tools/pipeline_eval/reference/grid.py",
        "--ro-bind", str(Path(baseline_solver.__file__)),
        "/worker/tools/pipeline_eval/qualification/physical_differences_solver.py",
    ]
    command[-1] = authority.WORKER
    try:
        run = subprocess.run(command, input=payload, capture_output=True, timeout=30, check=True)
        row = json.loads(run.stdout)
        if row["id"] != binding["id"]:
            raise ValueError("worker returned a different anonymous offer identifier")
        result = row["result"]
    except (ValueError, subprocess.SubprocessError, OSError) as error:
        stderr = (getattr(error, "stderr", None) or b"").decode(errors="replace")
        result = dict(
            status="timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed",
            reason=stderr[-900:] or str(error), boundary=solver.BOUNDARY, metrics={},
            arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
        )
    validate_result(result)
    return dict(binding, method=METHOD, worker_wall_s=perf_counter() - started, cpu=cpu,
                result=result)


def predict(raw, out):
    if (out / "prediction-lock.json").exists():
        raise ValueError("use a clean output directory for the committed transfer panel")
    jobs, sources = stage(raw, out)
    save_json(out / SOURCE_FILE, sources)
    save_json(out / "plan.json", [binding for binding, _ in jobs])

    def lane(slot):
        return [one(binding, payload, CPUS[slot]) for binding, payload in jobs[slot::len(CPUS)]]

    start = perf_counter()
    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        outcome = {r["id"]: r for rows in pool.map(lane, range(len(CPUS))) for r in rows}
    elapsed = perf_counter() - start
    if sources["sources"] != locked_dependencies():
        raise ValueError("the committed sources changed during measurement")
    cases = [r["id"] for r, _ in jobs]
    pack(out, POSITION_FILE, [outcome[key] for key in cases])
    files = ("plan.json", SOURCE_FILE, POSITION_FILE)
    save_json(out / "prediction-lock.json", dict(
        cases=cases, files={name: digest((out / name).read_bytes()) for name in files},
        wall_s=elapsed,
    ))


def _prior(source):
    lock_path = PRIOR / "prediction-lock.json"
    if digest(lock_path.read_bytes()) != source["baseline_prediction_sha256"]:
        raise ValueError("prior anonymous coincidence prediction lock changed")
    lock = json.loads(lock_path.read_bytes())
    plan, positions = (PRIOR / key for key in ("plan.json", POSITION_FILE))
    if any(digest(p.read_bytes()) != lock["files"][p.name] for p in (plan, positions)):
        raise ValueError("prior anonymous results do not verify")
    rows = read_predictions(positions)
    return {(v["original_case"], v["mode"]): (v, rows[v["id"]])
            for v in json.loads(plan.read_bytes())["cases"] if v["mode"] in MODES[:2]}


def score(out):
    lock = json.loads((out / "prediction-lock.json").read_bytes())
    if any(digest((out / name).read_bytes()) != v for name, v in lock["files"].items()):
        raise ValueError("anonymous transfer changed after the position commitment")
    source = json.loads((out / SOURCE_FILE).read_bytes())
    field = json.loads((authority.STUDY / "field-receipt.json").read_bytes())
    if source["reference_sha256"] != field["sealed_truth_sha256"]:
        raise ValueError("measured GNSS references changed after the commitment")
    truth = {r["id"]: r["latlon"] for r in json.loads(authority._verified_truth(field))["cases"]}
    records = read_predictions(out / POSITION_FILE)
    if list(records) != lock["cases"]:
        raise ValueError("positions do not match the scheduled primary and repeat roster")
    baseline = _prior(source)
    queries, outputs, map_rows = [], [], {}
    for ident, row in records.items():
        ref, result = truth[row["original_case"]], row["result"]
        matches = baseline.get((row["original_case"], row["mode"]))
        prior = None
        if matches:
            bound, found = matches
            for key in ("observation_sha256", "catalogue_sha256", "tile_center"):
                if row[key] != bound[key]:
                    raise ValueError("prior anonymous comparison does not share the offered input")
            if row["measured_mat_sha256"] != bound["native_mat_sha256"]:
                raise ValueError("prior anonymous comparison uses different measured evidence")
            prior = found["result"]
        queries.append(dict(id=ident, recording=row["capture"], condition=row["mode"], truth=ref,
                            bindings=dict(input_sha256=row["input_sha256"])))
        map_rows[(row["capture"], row["mode"])] = row
        for arm in ARMS:
            prediction = result["arms"][arm]
            endpoint = prior["arms"][arm] if prior else {}
            outputs.append(dict(
                id=ident, arm=arm, mode=row["mode"], site=row["site"], cohort=row["cohort"],
                capture=row["capture"], status=result["status"], reason=result.get("reason"),
                issued_km=distance_km(prediction.get("latlon"), ref),
                forced_km=distance_km(prediction.get("forced_latlon"), ref),
                previous_status=prior["status"] if prior else None,
                previous_forced_km=distance_km(endpoint.get("forced_latlon"), ref),
                tile_center_km=distance_km(row["tile_center"], ref),
                worker_wall_s=row["worker_wall_s"], metrics=result["metrics"],
            ))
    input_challenge = []
    for (capture, mode), row in map_rows.items():
        if mode != MODES[0]:
            continue
        shifted = map_rows[(capture, MODES[2])]
        if row["early_data_sha256"] != shifted["early_data_sha256"]:
            raise ValueError("late negative changed the early block")
        a, b = (r["result"]["metrics"] for r in (row, shifted))
        fields = ("trained_orbit_rows", "trained_pair_offsets_hz", "early_rms_hz")
        input_challenge.append(dict(capture=capture,
                                    identical_frozen_map=all(a.get(k) == b.get(k) for k in fields)))
    summary = {}
    for cohort in ("primary", "repeat"):
        for mode in MODES:
            values = [r for r in outputs if r["cohort"] == cohort and r["mode"] == mode
                      and r["arm"] == "c0"]
            summary[cohort + "/" + mode] = dict(
                attempts=len(values), issued=sum(r["issued_km"] is not None for r in values),
                **{k: distribution(r[k] for r in values) for k in (
                    "issued_km", "forced_km", "previous_forced_km", "tile_center_km",
                    "worker_wall_s",
                )},
            )
    scores = dict(summary=summary, rows=outputs, late_control=input_challenge)
    save_json(out / "scores.json", scores)
    save_json(out / "figure-queries.json", dict(queries=queries))
    names = ("scores.json", "figure-queries.json", "prediction-lock.json", *lock["files"])
    save_json(out / "figure-lock.json", dict(
        cases=lock["cases"], files={n: digest((out / n).read_bytes()) for n in names}
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("predict", "score"))
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--out", type=Path, default=REPORT)
    options = parser.parse_args()
    if options.stage == "score":
        score(options.out)
    elif options.raw is None:
        parser.error("predict requires the staged measured MAT directory")
    else:
        predict(options.raw, options.out)


if __name__ == "__main__":
    main()
