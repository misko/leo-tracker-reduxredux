"""Replay measured labelled beacon observability without receiver coordinates in the worker."""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np
from scipy.io import loadmat

from ..__main__ import ROOT, encoded, read_predictions, save_json
from ..reference import grid
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import beacon_observability as model
from . import physical_differences
from . import physical_transfer as authority
from .armijo_finish_results import pack
from .physical_differences import consolidate, simultaneous

REPORT = ROOT / "reports/2026_11_19_receiver_screening/streamlined/measured-transfer"
MODE = ("supplied-tile", "omitted-tile")
METHOD = "beacon_observability"
CPUS = (12, 13)
FIELDS = ("anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns", "duration_s")


def digest(data):
    return sha256(data).hexdigest()


def shared_epochs(arcs):
    """Pick at most one exact common timestamp in each half-second bin."""
    if not arcs:
        return dict(time_s=[], arc_index=[], frequency_hz=[])
    time = np.concatenate([t for t, _ in arcs])
    arcs_id = np.repeat(np.arange(len(arcs)), [len(t) for t, _ in arcs])
    hz = np.concatenate([hz for _, hz in arcs])
    exact, inverse, counts = np.unique(time, return_inverse=True, return_counts=True)
    supported = np.flatnonzero(counts >= 2)
    block = np.floor(2 * exact[supported]).astype(int)
    _, begin, number = np.unique(block, return_index=True, return_counts=True)
    picked = []
    for first, length in zip(begin, number, strict=True):
        options = supported[first : first + length]
        common = options[counts[options] == counts[options].max()]
        picked.append(common[(len(common) - 1) // 2])
    use = np.isin(inverse, picked)
    return dict(time_s=time[use].tolist(), arc_index=arcs_id[use].tolist(),
                frequency_hz=hz[use].tolist())


def read_measurements(raw, expected):
    source = authority._read(raw, expected)
    mat = loadmat(BytesIO(source), variable_names=["main_tone_dict", "id_dict"])
    windows = mat["main_tone_dict"].ravel()
    names = [str(label.item()) for label in mat["id_dict"].ravel()]
    if len(names) != len(windows) or len(set(names)) != len(names):
        raise ValueError("author labels must uniquely bind the corresponding measured arcs")
    arcs = [consolidate(window) for window in windows]
    _, audit = simultaneous(arcs)
    omit = set()
    for pair in audit:
        if pair["harmonic_like"]:
            omit.add(min(pair["track_rows"], key=lambda i: (np.ptp(arcs[i][0]), -i)))
    kept = [i for i in range(len(arcs)) if i not in omit]
    observation = shared_epochs([arcs[i] for i in kept])
    observation["arc_labels"] = [names[i] for i in kept]
    coverage = dict(available_arcs=len(arcs), removed_harmonic_rows=sorted(omit),
                    edges=len(observation["time_s"]),
                    shared_epochs=len(set(observation["time_s"])))
    return observation, coverage


def contract(receipt):
    return dict(
        protocol_sha256=digest((REPORT / "PROTOCOL.md").read_bytes()),
        source_sha256=digest(Path(model.__file__).read_bytes()),
        runner_sha256=digest(Path(__file__).read_bytes()),
        grid_sha256=digest(Path(grid.__file__).read_bytes()),
        original_preparation_sha256=digest(Path(authority.__file__).read_bytes()),
        coincidence_preparation_sha256=digest(Path(physical_differences.__file__).read_bytes()),
        checked_field_receipt_sha256=digest((authority.STUDY / "field-receipt.json").read_bytes()),
        measurement_provenance_sha256=digest(
            (authority.STUDY / "field_private/source_provenance.json").read_bytes()
        ),
        reference_sha256=receipt["sealed_truth_sha256"],
    )


def stage(raw):
    source_root = authority.STUDY
    original = json.loads((source_root / "field-receipt.json").read_bytes())
    source = json.loads((source_root / "field_private/source_provenance.json").read_bytes())
    public = source_root / "public_field"
    route = [
        {key: record[key] for key in ("pair", "condition", "id", "true_region")}
        for record in json.loads(authority._verified_truth(original))["cases"]
    ]
    seen, packets = set(), []
    source_lock = contract(original)
    for recording in source["captures"]:
        group = recording["site_group"]
        if group in seen:
            continue
        seen.add(group)
        bindings = {r["condition"]: r for r in route if r["pair"] == recording["pair"]}
        present, missing = (bindings[k] for k in ("present", "missing"))
        paired = [json.loads(authority._read(public / "queries" / f"{row['id']}.json",
                    original["public_query_sha256"][row["id"]])) for row in (present, missing)]
        full, omit = paired
        if any(full[key] != omit[key] for key in ("observation", "catalog")):
            raise ValueError("offered tiles differ in measured signal or causal catalogue")
        metadata = json.loads(authority._read(
            public / "observations" / f"{full['observation']}.json", full["observation"]
        ))
        catalogue = authority._read(public / "orbits" / f"{full['catalog']}.tle", full["catalog"])
        raw_sha = recording["track_file_sha256"]
        observation, coverage = read_measurements(raw / recording["date"] / "tracked_tones.mat",
                                                  raw_sha)
        observation.update({key: metadata[key] for key in FIELDS})
        (correct,) = [r["center"] for r in full["regions"] if r["id"] == present["true_region"]]
        for mode, center in zip(MODE, (correct, omit["regions"][0]["center"]), strict=True):
            ident = digest(encoded([full["observation"], group, mode, METHOD]))[:32]
            packet = dict(id=ident, observation=observation, catalogue=catalogue.decode("ascii"),
                          tile=center, solver_sha256=source_lock["source_sha256"])
            payload = encoded(packet)
            packets.append((dict(
                id=ident, group=group, mode=mode, original_case=present["id"],
                native_mat_sha256=raw_sha, observation_sha256=full["observation"],
                catalogue_sha256=full["catalog"], tile_center=center, capture=recording["date"],
                input_sha256=digest(payload), coverage=coverage,
            ), payload))
    if len(seen) != 8 or len(packets) != 16:
        raise ValueError("measured observability requires all eight sealed sites and both offers")
    return packets, source_lock


def _worker():
    request = json.load(sys.stdin)
    if request["solver_sha256"] != digest(Path(model.__file__).read_bytes()):
        raise ValueError("worker differs from the prespecified measured observability source")
    output = model.solve(request["observation"], request["catalogue"], request["tile"])
    print(json.dumps(dict(id=request["id"], result=output), allow_nan=False))


def _lane(jobs, cpu):
    rows = []
    for binding, payload in jobs:
        started = perf_counter()
        command = ["taskset", "-c", str(cpu), sys.executable, "-B", "-m", __spec__.name, "worker"]
        try:
            process = subprocess.run(command, input=payload, capture_output=True, check=True,
                                     timeout=12, env=dict(os.environ, OPENBLAS_NUM_THREADS="1",
                                     OMP_NUM_THREADS="1", MKL_NUM_THREADS="1"))
            outcome = json.loads(process.stdout)
            if outcome["id"] != binding["id"]:
                raise ValueError("isolated worker returned the wrong recording")
            result = outcome["result"]
        except (ValueError, subprocess.SubprocessError) as error:
            stderr = (getattr(error, "stderr", None) or b"").decode(errors="replace")
            result = dict(status="timed_out" if isinstance(error, subprocess.TimeoutExpired)
                          else "failed", reason=(stderr[-650:] or str(error)),
                          boundary=model.BOUNDARY, metrics={},
                          arms={arm: dict(latlon=None) for arm in ARMS})
        validate_result(result)
        rows.append(dict(binding, method=METHOD, result=result,
                         worker_wall_s=perf_counter() - started, worker_cpu=cpu))
    return rows


def predict(raw):
    jobs, source = stage(raw)
    if (REPORT / "prediction-lock.json").is_file():
        raise ValueError("an existing measured observability result cannot be replaced")
    save_json(REPORT / "source-lock.json", source)
    save_json(REPORT / "plan.json", [binding for binding, _ in jobs])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_lane, jobs[index::len(CPUS)], cpu)
                   for index, cpu in enumerate(CPUS)]
        rows = {row["id"]: row for task in futures for row in task.result()}
    latest = contract(json.loads((authority.STUDY / "field-receipt.json").read_bytes()))
    if source != latest:
        raise ValueError("worker or field evidence changed during evaluation")
    cases = [item["id"] for item, _ in jobs]
    pack(REPORT, "positions.jsonl.gz", [rows[key] for key in cases])
    names = ("positions.jsonl.gz", "plan.json", "source-lock.json")
    save_json(REPORT / "prediction-lock.json", dict(
        cases=cases, files={name: digest((REPORT / name).read_bytes()) for name in names},
    ))


def leave_out_scales(fits, group):
    other = [v for site, v in fits.items() if site != group and v is not None]
    return max(model.BIN_SIGMA_HZ, median(other)) if other else None


def score():
    lock = json.loads((REPORT / "prediction-lock.json").read_bytes())
    if any(digest((REPORT / name).read_bytes()) != value for name, value in lock["files"].items()):
        raise ValueError("measured observability bytes changed after sealing")
    receipt = json.loads((authority.STUDY / "field-receipt.json").read_bytes())
    source = json.loads((REPORT / "source-lock.json").read_bytes())
    if source["reference_sha256"] != receipt["sealed_truth_sha256"]:
        raise ValueError("evaluation coordinates differ from the original measured site archive")
    records = read_predictions(REPORT / "positions.jsonl.gz")
    if list(records) != lock["cases"]:
        raise ValueError("sealed positions do not cover the sixteen scheduled offers")
    truth = {r["id"]: r["latlon"] for r in json.loads(authority._verified_truth(receipt))["cases"]}
    noise = {r["group"]: r["result"]["metrics"].get("held_rf_rms_hz") for r in records.values()
             if r["mode"] == MODE[0]}
    queries, rows = [], []
    for ident, row in records.items():
        ref = truth[row["original_case"]]
        group, mode = row["group"], row["mode"]
        queries.append(dict(id=ident, recording=group, condition=mode, truth=ref,
                            bindings=dict(input_sha256=row["input_sha256"])))
        result = row["result"]
        state = result["metrics"]
        scales = state.get("held_singular_hz_per_km")
        sigma = leave_out_scales(noise, group)
        sd = sigma / scales[-1] if sigma is not None and scales and scales[-1] > 1e-8 else None
        for arm in ARMS:
            out = result["arms"][arm]
            rows.append(dict(
                id=ident, site=group, mode=mode, arm=arm, status=result["status"],
                reason=result.get("reason"),
                forced_error_km=distance_km(out.get("forced_latlon"), ref),
                tile_center_error_km=distance_km(row["tile_center"], ref),
                leave_site_out_sigma_hz=sigma, leave_site_out_worst_sd_km=sd,
                qualified_at_5km=sd is not None and sd <= 5.0,
                worker_wall_s=row["worker_wall_s"], **state,
            ))
    summaries = {}
    for mode in MODE:
        group = [x for x in rows if x["mode"] == mode and x["arm"] == "c0"]
        summaries[mode] = dict(
            attempts=len(group), finite_held=sum("held_rf_rms_hz" in x for x in group),
            forced=sum(x["forced_error_km"] is not None for x in group),
            qualifies=sum(x["qualified_at_5km"] for x in group),
            **{field: distribution(x.get(field) for x in group) for field in (
                "forced_error_km", "tile_center_error_km", "held_rf_rms_hz",
                "leave_site_out_worst_sd_km", "quantization_only_worst_sd_km", "worker_wall_s",
            )},
        )
    save_json(REPORT / "scores.json", dict(summary=summaries, rows=rows))
    save_json(REPORT / "figure-queries.json", dict(queries=queries))
    names = (*lock["files"], "prediction-lock.json", "scores.json", "figure-queries.json")
    save_json(REPORT / "figure-lock.json", dict(
        cases=lock["cases"], files={name: digest((REPORT / name).read_bytes()) for name in names},
        scorer_sha256=digest(Path(__file__).read_bytes()),
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("predict", "score", "worker"))
    parser.add_argument("--raw", type=Path)
    args = parser.parse_args()
    if args.mode == "worker":
        _worker()
    elif args.mode == "score":
        score()
    elif args.raw is None:
        parser.error("predict requires the directory with released capture MAT files")
    else:
        predict(args.raw)


if __name__ == "__main__":
    main()
