"""Freeze two blind simulated captures and replay exact native omission diagnostics."""

import argparse
import json
import os
import secrets
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.optimize import root

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import validate_result
from ..variants import portable_v5, region_halo
from . import boundary_roof_offers as geometry
from . import cold_scenes as simulator
from . import exterior_evidence_trial as exterior
from . import native_clock_full as clock
from . import native_clock_model_worker
from . import portable_v5_transfer as capture
from . import standalone_majority as majority
from .armijo_finish_results import pack

phase = clock.phase
REPORT = clock.REPORT.parent.parent / "detector-origins/region-halo"
WORK = clock.WORK.with_name("region-halo")
WORKER = Path(__file__).with_name("region_halo_worker.py")
CPUS = (8, 9)
TIMEOUT = 80
WALL_S = 720
METHOD = region_halo.METHOD
MAJORITY_INPUTS = Path("/srv/bulk/leo-dev/stm.1Zyx8VvG/near-input/public")
BOXES = ((44, -116), (-37, 175))
AGES_H = (0.75, 3.25)
MARGINS = {"centered": 12.5, "near-inside": 1.5, "near-outside": -1.5, "far-outside": -15}


def sources(bundle):
    original, jobs = clock.prepare(bundle)
    files = (
        Path(__file__),
        WORKER,
        Path(region_halo.__file__),
        Path(simulator.__file__),
        Path(capture.__file__),
        Path(geometry.__file__),
        REPORT / "PROTOCOL.md",
    )
    return dict(
        files={p.name: phase.digest(p) for p in files},
        smooth=original["source"],
        majority_lock=phase.digest(majority.REPORT / "prediction-lock.json"),
        exterior_lock=phase.digest(exterior.REPORT / "diagnostic-stress/prediction-lock.json"),
    ), jobs


def offer(truth, axis, sign, along, margin, ident):
    surface = geometry.Region(
        "", truth, geometry.geodetic_to_ecef_km(*truth, 0), geometry.ecef_to_enu_matrix(*truth)
    )
    center = truth
    if margin != 12.5:
        desired = np.full(2, along)
        desired[axis] = sign * (12.5 - margin)

        def residual(x):
            return geometry.tangent(truth, surface.site(x)[1]) - desired

        fit = root(residual, -desired)
        if np.max(np.abs(residual(fit.x))) > 1e-6:
            raise ValueError("cannot place the declared face in native tangent coordinates")
        center = surface.site(fit.x)[1]
    actual = 12.5 - max(abs(geometry.tangent(truth, center)))
    if abs(actual - margin) > 1e-6:
        raise ValueError("offer truth margin differs from declared simulator condition")
    return dict(id=ident, center=center, width_km=25.0)


def native_query(ident, recording, cohort, doc, media, tile, catalogue_when):
    packet = dict(
        mode="native",
        cutoff=doc["clock_anchor"]["before"]["realtime_ns"],
        catalog_timestamp=catalogue_when,
        probe_limit=len(doc["source"]["probes"]),
        offer=tile,
        **{k: dict(path=f"/input/{k}", sha256=phase.digest(p)) for k, p in media.items()},
    )
    if catalogue_when > packet["cutoff"]:
        raise ValueError("halo catalogue postdates the bounded receiver capture")
    return dict(id=ident, recording=recording, cohort=cohort, packet=packet)


def synthetic(work, seed):
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    received, raw, _, _ = capture.authentic_history()
    catalogue, config = work / "catalogue.tle", work / "track-config.json"
    write(catalogue, raw)
    save_json(config, dict(config=portable_v5.TRACK_CONFIG))
    constellation = simulator._constellation(raw, received)
    inputs = []
    for site, (box, age) in enumerate(zip(BOXES, AGES_H, strict=True), 1):
        truth = (np.asarray(box) + rng.uniform(-1.0, 1.0, 2)).tolist()
        recording = rng.bytes(10).hex()
        anchor = received + int(age * 3600 * simulator.NS)
        factors, counter, _ = simulator._generate_capture(constellation, anchor, truth, rng)
        doc = capture.simulated_document(recording, anchor, factors, counter)
        native = work / f"{recording}.native.json"
        write(native, encoded(doc))
        files = dict(native=native, catalogue=catalogue, track_config=config)
        axis, sign, along = int(rng.integers(2)), int(rng.choice([-1, 1])), rng.uniform(-3, 3)
        for condition, margin in MARGINS.items():
            ident = rng.bytes(10).hex()
            tile = offer(truth, axis, sign, along, margin, ident)
            query = native_query(ident, recording, "fresh-synthetic", doc, files, tile, received)
            inputs.append(
                (
                    query,
                    files,
                    dict(
                        truth=truth,
                        source_label=f"Fresh site {site}",
                        condition=condition,
                        margin_km=margin,
                        catalogue_age_h=age,
                    ),
                )
            )
    return inputs


def majority_case():
    files = majority.REPORT / "prediction-lock.json"
    receipt = phase._read(files)
    for name, checksum in receipt["files"].items():
        if phase.digest(majority.REPORT / name) != checksum:
            raise ValueError("the archived majority native query changed after sealing")
    (case,) = [
        r
        for r in phase._read(majority.REPORT / "requests.json")
        if r["id"] == majority.NEAR and r["method"] == majority.METHOD
    ]
    recording, ident = case["capture_id"], case["id"]
    label = phase._read(majority.REPORT / "scoring-targets.json")[ident]
    native = MAJORITY_INPUTS / f"{recording}.complete.json"
    config = MAJORITY_INPUTS / "track-config.json"
    candidates = list(
        (MAJORITY_INPUTS / f"tle-{recording}").rglob(f"*-{case['catalog_sha256']}.tle")
    )
    doc = phase._read(native)
    cutoff = doc["clock_anchor"]["before"]["realtime_ns"]
    when, catalogue = max(
        (int(p.name.split("-", 1)[0]), p)
        for p in candidates
        if int(p.name.split("-", 1)[0]) <= cutoff
    )
    assets = dict(native=native, track_config=config, catalogue=catalogue)
    query = native_query(ident, recording, "archived-majority", doc, assets, case["tile"], when)
    if any(
        query["packet"][asset]["sha256"] != case[k]
        for asset, k in (
            ("native", "native_sha256"),
            ("catalogue", "catalog_sha256"),
            ("track_config", "track_config_sha256"),
        )
    ):
        raise ValueError(
            "the majority comparison did not bind its exact factor/config/latest catalogue"
        )
    truth = label["latlon"]
    margin = 12.5 - max(abs(geometry.tangent(truth, case["tile"]["center"])))
    return (
        query,
        assets,
        dict(
            truth=truth,
            source_label="Archived majority near omission",
            condition="near-outside",
            margin_km=float(margin),
        ),
    )


def roofs(jobs):
    assets = {q["recording"]: paths for q, paths in jobs if q["cohort"] == "roof"}
    cases, _ = exterior.prior_cases()
    labels = {}
    for folder in exterior.SOURCE_COHORTS:
        file = folder / "evaluator.json"
        if phase.digest(file) != phase._read(folder / "prediction-lock.json")["evaluator_sha256"]:
            raise ValueError("archived roof condition differs from sealed source")
        labels.update({r["id"]: r for r in phase._read(file)["labels"]})
    selected = []
    for query in cases:
        if query["recording"] not in {"DS26-0102", "DS26-0070"}:
            continue
        row = labels[query["id"]]
        if row["condition"] == "near-outside":
            selected.append(
                (
                    dict(query, cohort="archived-roof"),
                    assets[row["recording"]],
                    dict(
                        truth=row["truth"],
                        condition="near-outside",
                        margin_km=row["true_margin_km"],
                        source_label=row["recording"],
                    ),
                )
            )
    if len(selected) != 2:
        raise ValueError("expected both earlier false near-edge roof offers")
    return selected


def command(cpu, paths, bundle):
    argv = clock.command(cpu, paths, bundle)
    argv[argv.index(str(clock.WORKER))] = str(WORKER)
    for module, target in (
        (native_clock_model_worker, "qualification/native_clock_model_worker.py"),
        (region_halo, "variants/region_halo.py"),
    ):
        argv[-3:-3] = [
            "--ro-bind",
            str(Path(module.__file__)),
            f"/worker/tools/pipeline_eval/{target}",
        ]
    return argv


def attempt(query, paths, bundle, cpu):
    start = perf_counter()
    try:
        process = subprocess.run(
            command(cpu, paths, bundle),
            input=encoded(query["packet"]),
            check=True,
            capture_output=True,
            timeout=TIMEOUT,
        )
        result = json.loads(process.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        message = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-2200:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        result = dict(result=clock.failed(status, message or str(error)))
    validate_result(result["result"])
    row = (
        clock.bindings(query)
        | result
        | dict(method=METHOD, cpu=cpu, worker_wall_s=perf_counter() - start)
    )
    if row["result"]["status"] in ("ok", "withheld") and (
        not row.get("observation_sha256")
        or row["proc_memory_kib"]["VmPeak"] > 512 * 1024
        or any("localization_v3" in m or "/v5_" in m for m in row["imported_first_party"])
    ):
        raise ValueError("halo worker exceeded the unchanged native boundary")
    print(
        query["id"],
        query["cohort"],
        row["result"]["status"],
        row.get("halo_vote", {}).get("state"),
        round(row["worker_wall_s"], 3),
        flush=True,
    )
    return row


def run(work, output, bundle):
    start = perf_counter()
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("the experiment expects CPU8/9")
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=False)
    source, jobs = sources(bundle)
    save_json(output / "source-lock.json", source)
    seed = secrets.token_bytes(32)
    items = synthetic(work, seed)
    items.extend(roofs(jobs))
    try:
        items.append(majority_case())
        omitted = None
    except (OSError, ValueError) as error:
        omitted = str(error)
    items.sort(key=lambda entry: (entry[0]["cohort"] != "fresh-synthetic", entry[0]["id"]))
    queries = [q for q, _, _ in items]
    labels = {q["id"]: label for q, _, label in items}
    save_json(work / "evaluator.json", dict(labels=labels, seed_hex=seed.hex()))
    save_json(
        output / "roster.json",
        dict(
            cases=queries,
            optional_majority_blocker=omitted,
            cpus=list(CPUS),
            cap_s=WALL_S,
            worker_cap_s=TIMEOUT,
            evaluator_sha256=phase.digest(work / "evaluator.json"),
            source_sha256=phase.digest(output / "source-lock.json"),
        ),
    )

    def sequence(index):
        rows = []
        for query, paths, _ in items[index :: len(CPUS)]:
            if perf_counter() - start < WALL_S - TIMEOUT - 5:
                row = attempt(query, paths, bundle, CPUS[index])
            else:
                row = clock.bindings(query) | dict(
                    method=METHOD,
                    worker_wall_s=None,
                    result=clock.failed("missing", "batch budget closed before admission"),
                )
            rows.append(row)
        return rows

    with ThreadPoolExecutor(len(CPUS)) as pool:
        rows = [r for lane in pool.map(sequence, range(len(CPUS))) for r in lane]
    if source != sources(bundle)[0]:
        raise ValueError("a frozen source changed during halo verification")
    positions = f"{METHOD}.jsonl.gz"
    files = {
        positions: pack(output, positions, rows),
        **{name: phase.digest(output / name) for name in ("roster.json", "source-lock.json")},
    }
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=[q["id"] for q in queries],
            files=files,
            elapsed_s=perf_counter() - start,
        ),
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, default=WORK)
    cli.add_argument("--output", type=Path, default=REPORT)
    cli.add_argument("--bundle", type=Path, default=clock.base.BUNDLE)
    args = cli.parse_args()
    run(args.work, args.output, args.bundle)


if __name__ == "__main__":
    main()
