"""Bind and replay the frozen exterior evidence gate on archived roof offers."""

import argparse
import json
import os
import subprocess
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import perf_counter

from ..__main__ import encoded, local_output, read_predictions, save_json
from ..scoring import ARMS, validate_result
from ..variants import tile_region_empirical, tile_region_support
from . import boundary_roof_offers as edge
from . import native_clock_full as clock
from . import recenter_verify_trial as recenter
from . import tile_region_empirical_trials as frozen
from .armijo_finish_results import pack
from .portable_v5_trials import preferred_history

phase = clock.phase
REPORT = clock.REPORT.parent.parent / "recovery/exterior-evidence"
WORK = clock.WORK.with_name("exterior-evidence")
WORKER = Path(__file__).with_name("exterior_evidence_worker.py")
METHOD = "native_smooth_exterior_evidence"
SOURCE_COHORTS = (edge.REPORT / "primary", edge.REPORT / "reserve", recenter.REPORT / "prospective")
WALL_S = 720
GATE_S = 90


def keyed(purpose, ident):
    return phase.corpus._sha(f"roof-exterior-v1:{purpose}:{ident}".encode())


def sources(bundle):
    historic = frozen.OUT / "source-lock.json"
    if frozen.source() != phase._read(historic):
        raise ValueError("development-noise scientific source differs from the frozen gate")
    standalone, jobs = clock.prepare(bundle)
    files = (historic, Path(__file__), WORKER, REPORT / "PROTOCOL.md")
    return dict(
        gate={p.name: phase.digest(p) for p in files},
        native_smooth=standalone["source"],
        histories=phase.digest(clock.base.secant_full.REPORT / "original-v5-inputs.json"),
        former={p.name: phase.digest(p / "prediction-lock.json") for p in SOURCE_COHORTS},
    ), jobs


def prior_cases():
    cases, original = [], {}
    for folder in SOURCE_COHORTS:
        lock = phase._read(folder / "prediction-lock.json")
        clock.base.secant_full._verify_files(folder, lock["files"])
        plan = phase._read(folder / "roster.json")
        rows = read_predictions(folder / f"{clock.METHOD}.jsonl.gz")
        for query in plan["cases"]:
            ident = query["id"]
            expected = clock.bindings(query)
            if ident in original or any(rows[ident].get(k) != v for k, v in expected.items()):
                raise ValueError("prior smooth query is duplicated or unbound")
            original[ident] = rows[ident]
            cases.append(query)
    if len(cases) != 104 or len({q["recording"] for q in cases}) != 26:
        raise ValueError("expected all original edge-challenge offers")
    return cases, original


def reserve_cases(work, originals, stress):
    past = {r["recording"] for r in stress}
    originals = {q["recording"]: q for q, _ in originals if q["cohort"] == "roof"}
    ids = sorted(
        (i for i in originals.keys() - past if i.startswith("DS26-")),
        key=lambda i: keyed("reserve", i),
    )[:6]
    truth = {r["id"]: r["truth"] for r in phase.corpus.references("ds26-common127")}
    cases, labels = [], []
    for ident in ids:
        original = originals[ident]["packet"]
        for tile, label in recenter.new_offers(ident, truth[ident], original["offer"]):
            packet = dict(original, offer=tile)
            cases.append(dict(id=label["id"], recording=ident, cohort="reserve", packet=packet))
            labels.append(dict(label, tile=tile, input_sha256=phase.corpus._sha(encoded(packet))))
    save_json(work / "reserve-evaluator.json", dict(labels=labels, recording_ids=ids))
    return cases


def history(case, binding):
    ident = case["id"]
    root = phase.ARCHIVE if ident.startswith("DS26-") else phase.DS29
    path = root / f"{ident}-r0/baseline/experimental-request.json"
    request = phase._read(path)
    job = request["job"]
    if (
        "sha256:" + phase.corpus._sha(encoded(request)) != binding["baseline"]["request_sha256"]
        or job["evaluation_reference"] is not None
        or job["native_input"]["sha256"] != "sha256:" + case["native"]["sha256"]
    ):
        raise ValueError("the authentic causal history is not bound to the frozen native recording")
    stamps, objects = [], {}
    for name, digest in request["causal_snapshots"].items():
        collected, from_name = Path(name).stem.split("-", 1)
        digest = digest.removeprefix("sha256:")
        path = Path(job["tle_root"]) / "archive/space-track" / name
        if digest != from_name or not path.is_file():
            raise ValueError("causal history object is missing or unbound")
        stamps.append(dict(collected_utc_ns=int(collected), sha256=digest))
        objects[digest] = path
    ready = preferred_history(stamps, case["cutoff_utc_ns"])
    if ready[-1] != dict(
        collected_utc_ns=case["catalog_timestamp_ns"], sha256=case["catalog"]["sha256"]
    ):
        raise ValueError("the gate and smooth receiver latest causal catalogue differ")
    return ready, {r["sha256"]: objects[r["sha256"]] for r in ready}


def gate_command(cpu, objects, kernel, native):
    prior = frozen.trials.prior
    modules = (
        frozen.trials.portable_gate,
        frozen.trials.portable_gate_coverage,
        tile_region_support,
        tile_region_empirical,
    )
    argv = prior.worker_command(cpu, objects, kernel, WORKER, modules)
    argv[-4:-4] = ["--ro-bind", str(native), "/input/native"]
    return argv


def gate_attempt(query, history_item, native, kernel, cpu, deadline):
    stamps, objects = history_item
    packet = dict(
        tile=query["packet"]["offer"],
        history=stamps,
        native_sha256=query["packet"]["native"]["sha256"],
    )
    start = perf_counter()
    try:
        done = subprocess.run(
            gate_command(cpu, objects, kernel, native),
            input=encoded(packet),
            capture_output=True,
            check=True,
            timeout=deadline,
        )
        output = json.loads(done.stdout)
        gate = output.get("gate")
        state = "unavailable" if gate is None else "accepted" if gate["admitted"] else "denied"
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        message = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-2300:]
        output = dict(prior_result_reason=message or str(error))
        state = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
    print(query["id"], state, round(perf_counter() - start, 2), flush=True)
    return dict(
        output,
        state=state,
        worker_wall_s=perf_counter() - start,
        history_sha256=phase.corpus._sha(encoded(stamps)),
        cpu=cpu,
    )


def combine(original, gate):
    result = original["result"]
    new = dict(result, boundary="Native smooth oscillator after independent exterior held evidence")
    state = gate["state"]
    if result["status"] == "ok" and state != "accepted":
        status = "withheld" if state == "denied" else state
        new.update(
            status=status,
            reason=f"independent exterior gate: {state}",
            arms={arm: dict(result["arms"][arm], latlon=None, region_id=None) for arm in ARMS},
        )
    validate_result(new)
    return dict(
        original,
        result=new,
        method=METHOD,
        exterior=gate,
        smooth_wall_s=original.get("worker_wall_s"),
    )


def lanes(items, operation, limit):
    queue, lock = deque(items), Lock()

    def lane(cpu):
        while perf_counter() < limit:
            with lock:
                if not queue:
                    return
                item = queue.popleft()
            operation(cpu, item)

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lane, clock.CPUS))


def run(work, output, bundle):
    started = perf_counter()
    if not set(clock.CPUS) <= os.sched_getaffinity(0):
        raise ValueError("expected the four designated CPU pins")
    work = local_output(work)
    work.mkdir(exist_ok=False, parents=True)
    source, originals = sources(bundle)
    stress, prior = prior_cases()
    reserve = reserve_cases(work, originals, stress)
    base = {q["recording"]: (q["packet"], paths) for q, paths in originals if q["cohort"] == "roof"}
    if any(
        q["packet"] != dict(base[q["recording"]][0], offer=q["packet"]["offer"])
        for q in stress + reserve
    ):
        raise ValueError("a challenge changed the calibrated capture or native files")
    input_items = phase.frozen_inputs()
    authority = phase._read(clock.base.secant_full.REPORT / "original-v5-inputs.json")
    contexts = {
        i: history(input_items[i], authority[i]) for i in {q["recording"] for q in stress + reserve}
    }
    kernel = work / "projector.so"
    frozen.trials.orbit_projector.compile_kernel(kernel)
    plan = dict(
        source=source,
        stress=stress,
        reserve=reserve,
        cpus=list(clock.CPUS),
        batch_s=WALL_S,
        kernel_sha256=phase.digest(kernel),
        causal_histories={i: rows for i, (rows, _) in contexts.items()},
        reserve_evaluator_sha256=phase.digest(work / "reserve-evaluator.json"),
    )
    save_json(output / "plan.json", plan)
    smooth, gates = work / "smooth", work / "gate"
    smooth.mkdir()
    gates.mkdir()
    expiry = started + WALL_S

    def full_gate(cpu, query):
        ident = query["recording"]
        result = gate_attempt(
            query,
            contexts[ident],
            base[ident][1]["native"],
            kernel,
            cpu,
            min(GATE_S, max(1, expiry - perf_counter() - 10)),
        )
        save_json(gates / f"{query['id']}.json", result)

    def process(cohort, queries, stock):
        requested = [q for q in queries if stock[q["id"]]["result"]["status"] == "ok"]
        ordered = sorted(requested, key=lambda q: keyed("queue", q["id"]))
        lanes(ordered, full_gate, expiry - 75)
        dest = output / cohort
        rows = []
        for q in queries:
            ident = q["id"]
            src = stock[ident]
            path = gates / f"{ident}.json"
            if path.is_file():
                gate = phase._read(path)
            else:
                state = "missing" if src["result"]["status"] == "ok" else "initial_not_published"
                gate = dict(state=state)
            rows.append(combine(src, gate))
        files = {
            f"{m}.jsonl.gz": pack(dest, f"{m}.jsonl.gz", ordered)
            for m, ordered in ((METHOD, rows), (clock.METHOD, stock.values()))
        }
        save_json(
            dest / "prediction-lock.json",
            dict(
                cases=[q["id"] for q in queries],
                files=files,
                plan_sha256=phase.digest(output / "plan.json"),
                states=dict(Counter(r["exterior"]["state"] for r in rows)),
                elapsed_s=perf_counter() - started,
            ),
        )

    process("diagnostic-stress", stress, prior)
    if expiry - perf_counter() >= 120:

        def run_smooth(cpu, q):
            row = clock.attempt(cpu, q, base[q["recording"]][1], bundle)
            save_json(smooth / f"{q['id']}.json", row)

        lanes(reserve, run_smooth, expiry - 75)
    stock = {}
    for q in reserve:
        target = smooth / f"{q['id']}.json"
        if target.is_file():
            stock[q["id"]] = phase._read(target)
        else:
            stock[q["id"]] = dict(
                clock.bindings(q),
                worker_wall_s=None,
                result=clock.failed("missing", "reserve not reached before wall cap"),
            )
    process("reserve", reserve, stock)
    if sources(bundle)[0] != source:
        raise ValueError("receiver sources changed during exterior evidence replay")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, default=WORK)
    cli.add_argument("--output", type=Path, default=REPORT)
    cli.add_argument("--bundle", type=Path, default=clock.base.BUNDLE)
    args = cli.parse_args()
    run(args.work, args.output, args.bundle)


if __name__ == "__main__":
    main()
