"""Bound paired 10 MS/s real-background and synthetic-background Qin qualification."""

import argparse
import gzip
import json
import os
import secrets
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from ..__main__ import encoded, save_json, write
from . import hybrid_site_donor as donor
from . import hybrid_site_model as model
from . import raw_stream_reader
from . import waveform_holdout_trial as holdout
from . import waveform_site_interior as interior
from . import waveform_site_trial as stock
from .full_v5_check import BULK, PRODUCERS, _load_case
from .recording_to_v5 import ARCHIVE_PYTHON

REPORT = stock.REPORT.parents[1] / "support-preserving/hybrid-site"
DONORS = ("DS26-0036", "DS29-0082")
PINS = (10, 11)
ANCHOR_DELAY_S = 9340
DETECT_LIMIT_S = 240
MODULE = "tools.pipeline_eval.qualification.hybrid_site_trial"
READER = "tools.pipeline_eval.qualification.hybrid_site_donor"
METHODS = ("hybrid_site_compact", "hybrid_site_interior")


def freeze(out):
    value = holdout.freeze(out)
    paths = (
        Path(__file__),
        Path(donor.__file__),
        Path(raw_stream_reader.__file__),
        Path(holdout.__file__),
        ARCHIVE_PYTHON.resolve(),
    )
    value["sources"].update({str(p): stock.digest(p) for p in paths})
    return dict(
        value,
        detector_cpus=list(PINS),
        position_cpus=list(PINS),
        detector_limit_s=DETECT_LIMIT_S,
        anchor_delay_s=ANCHOR_DELAY_S,
        prospective_methods=list(METHODS),
    )


def prepare(work, out, seed):
    seed = seed or secrets.token_hex(32)
    salt = stock.raw_digest(bytes.fromhex(seed) + b"hybrid-donor-resampling-v1")
    inputs = {}
    for case in DONORS:
        item = _load_case(case)
        native = item["native"]
        when = item["recording"]["segments"][:2]
        inputs[case] = dict(
            source_authority_native_sha256=native["sha256"],
            source_authority_native_path=str(BULK / native["path"]),
            segments=[dict(x, path=str(BULK / x["path"])) for x in when],
        )
    if (out / "donor-plan.json").exists():
        raise FileExistsError("hybrid donor salt and authority already frozen")
    save_json(
        out / "donor-plan.json",
        dict(salt=salt, donors=inputs, selection="first two sealed segments, salted channel rank"),
    )
    stock.prepare(work, out, seed)
    lock = stock.read(out / "input-lock.json")
    lock["files"]["donor-plan.json"] = stock.digest(out / "donor-plan.json")
    save_json(out / "input-lock.json", lock)


def reader_command(case):
    return [
        "sudo",
        "-n",
        "-u",
        "leo",
        "--",
        "env",
        f"PYTHONPATH={PRODUCERS[case].root}:{stock.ROOT}",
        "OPENBLAS_NUM_THREADS=1",
        "OMP_NUM_THREADS=1",
        str(ARCHIVE_PYTHON),
        "-B",
        "-m",
        READER,
    ]


def projected(detector, iq, visit, counter):
    before = process_time()
    body = detector.analyze(iq)
    cpu = process_time() - before
    if [r["receiver_id"] for r in body["rows"]] != [0, 1]:
        raise ValueError("unchanged wide GLRT must return both lane IDs")
    probes = []
    for r in body["rows"]:
        ports = [stock._from_native(rank, c) for rank, c in enumerate(r["candidates"])]
        j = visit["visit"]
        probes.append(
            dict(
                visit_index=j,
                receiver_id=r["receiver_id"],
                probe_index=0,
                probe_start_ms=0,
                channel=visit["channel"],
                edge=visit["edge"],
                actual_rf_hz=visit["rf_hz"],
                valid_start_counter=counter + visit["relative_counter"],
                payload_start_sample=j * model.SAMPLES,
                candidates=[c for c in ports if c is not None],
            )
        )
    return dict(
        probes=probes,
        stock_sha256=stock.raw_digest(encoded(body)),
        iq_sha256=stock.raw_digest(iq.tobytes()),
        detector_cpu_s=cpu,
    )


def lane(work, out, index):
    lock = stock.sealed(out, "input-lock.json")
    if (
        freeze(out) != stock.read(out / "source-lock.json")
        or stock.digest(work / "custodian.json") != lock["private_sha256"]
    ):
        raise ValueError("locked model, archive authority or detector changed")
    pri = stock.read(work / "custodian.json")
    plan = stock.read(out / "donor-plan.json")
    case = DONORS[index]
    edge = ("lower", "upper")[index]
    visits = {r["visit"]: r for r in pri["visits"] if r["edge"] == edge}
    public = stock.read(out / "schedule.json")["visits"]
    reader_input = dict(
        case=case,
        salt=plan["salt"],
        segments=plan["donors"][case]["segments"],
        visits=[r for r in public if r["edge"] == edge],
    )
    start = perf_counter()
    frame = model.pulse_bank()[edge]
    with ExitStack() as stack:
        proc = stack.enter_context(
            subprocess.Popen(reader_command(case), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        )
        proc.stdin.write(encoded(reader_input))
        proc.stdin.close()
        analysis = stack.enter_context(
            stock.native_short_window.NativeShortWindow(
                str(stock.LIBRARY),
                *stock.detector_templates(model.RATE, edge),
                sample_rate_hz=model.RATE,
                receiver_count=2,
                fractional_epoch=True,
            )
        )
        ledger = stack.enter_context((work / f"lane-{index}.jsonl").open("xb"))
        seen, stats = set(), None
        for line in proc.stdout:
            rec = json.loads(line)
            if rec.get("terminal") is True:
                stats = rec
                break
            v = visits[rec["visit"]]
            if v["visit"] in seen or (v["rf_hz"], v["edge"]) != (rec["donor_rf_hz"], rec["edge"]):
                raise ValueError("donor samples changed frozen target binding")
            raw = proc.stdout.read(rec["nbytes"])
            if stock.raw_digest(raw) != rec["iq_sha256"]:
                raise ValueError("actual archived IQ changed after sealed donor extraction")
            cpu = process_time()
            iq = np.frombuffer(raw, dtype="<i2").reshape((model.SAMPLES, 2, 2))
            emission = model.plant_iq(v, pri["scene"], frame)
            triplet, gain = model.mixes(iq, emission, v["sample_seed"])
            cpu = process_time() - cpu
            records = {
                name: projected(analysis, signal_iq, v, pri["scene"]["counter"])
                for name, signal_iq in triplet.items()
            }
            record = dict(
                visit=v["visit"],
                donor=rec,
                arms=records,
                normalization=gain,
                emitted_signal_sha256=stock.raw_digest(emission.tobytes()),
                mix_cpu_s=cpu,
            )
            ledger.write(encoded(record) + b"\n")
            ledger.flush()
            seen.add(v["visit"])
        if proc.wait(timeout=8) or stats is None or seen != set(visits):
            raise ValueError("closed original donor stream did not cover every planned dual visit")
    save_json(work / f"lane-{index}-receipt.json", dict(stats, wall_s=perf_counter() - start))


def publish_arm(work, out, arm, rows, schedule):
    dest = out / arm
    pub = work / "public" / arm
    pub.mkdir()
    for name in ("track-config.json", "tle"):
        (pub / name).symlink_to(pub.parent / name, target_is_directory=name == "tle")
    probes = [p for v in rows for p in v["arms"][arm]["probes"]]
    # Same opaque physical session and fixed time/counter/RF across alternatives.
    session = schedule["session"]
    native = stock.compact.native.simulated_document(
        session, schedule["anchor_utc_ns"], probes, probes[0]["valid_start_counter"]
    )
    native["provenance"].update(
        scope="Synthetic Qin over archived IQ or matched synthetic/no-injection control",
        detector_sha256=stock.LIBRARY_SHA,
        waveform_digest=stock.raw_digest(encoded([v["arms"][arm]["iq_sha256"] for v in rows])),
        panel_arm=arm,
    )
    payload = encoded(native) + b"\n"
    write(pub / "native.json", payload)
    write(dest / "native.json.gz", gzip.compress(payload, mtime=0))
    config_sha = stock.digest(pub / "track-config.json")
    requests = [
        dict(
            o,
            session=session,
            native="native.json",
            native_sha256=stock.raw_digest(payload),
            track_config="track-config.json",
            config_sha256=config_sha,
            archive="tle",
            catalog_sha256=schedule["catalog_sha256"],
        )
        for o in schedule["offers"]
    ]
    save_json(dest / "requests.json", requests)
    for name in ("track-config.json", "causal-authority.json", "schedule.json", "source-lock.json"):
        write(dest / name, (out / name).read_bytes())
    # Name-based adapters can authenticate each arm without mounting the parent privately.
    source_lock = stock.read(out / "input-lock.json")
    source_lock["files"] = {
        name: stock.digest(dest / name) for name in source_lock["files"] if (dest / name).is_file()
    }
    save_json(dest / "input-lock.json", source_lock)
    names = (
        "native.json.gz",
        "requests.json",
        "track-config.json",
        "causal-authority.json",
        "schedule.json",
        "source-lock.json",
        "input-lock.json",
    )
    save_json(
        dest / "detector-lock.json",
        dict(
            ready=True,
            completed_visits=len(rows),
            scheduled_visits=len(schedule["visits"]),
            files={n: stock.digest(dest / n) for n in names},
            parent_ledger_sha256=stock.digest(out / "visit-ledger.jsonl.gz"),
        ),
    )


def detect(work, out):
    schedule = stock.read(out / "schedule.json")
    start = perf_counter()
    jobs = [
        subprocess.Popen(
            [
                "taskset",
                "-c",
                str(cpu),
                sys.executable,
                "-B",
                "-m",
                MODULE,
                "lane",
                str(work),
                "--out",
                str(out),
                "--lane",
                str(i),
            ],
            start_new_session=True,
        )
        for i, cpu in enumerate(PINS)
    ]
    try:
        status = [j.wait(timeout=max(0.1, DETECT_LIMIT_S - (perf_counter() - start))) for j in jobs]
    except subprocess.TimeoutExpired:
        for j in jobs:
            if j.poll() is None:
                os.killpg(j.pid, signal.SIGKILL)
                j.wait()
        status = [j.returncode for j in jobs]
    paths = [work / f"lane-{i}.jsonl" for i in range(len(PINS))]
    rows = sorted(
        [json.loads(line) for p in paths if p.is_file() for line in p.read_bytes().splitlines()],
        key=lambda r: r["visit"],
    )
    ready = status == [0, 0] and [r["visit"] for r in rows] == list(range(len(schedule["visits"])))
    stock.pack(out, "visit-ledger.jsonl.gz", rows)
    names = ["source-lock.json", "input-lock.json", "visit-ledger.jsonl.gz"]
    if ready:
        for arm in model.ARMS:
            publish_arm(work, out, arm, rows, schedule)
            names.append(f"{arm}/detector-lock.json")
    save_json(
        out / "detector-lock.json",
        dict(
            ready=ready,
            completed_visits=len(rows),
            scheduled_visits=len(schedule["visits"]),
            statuses=status,
            lane_receipts=[stock.read(work / f"lane-{i}-receipt.json") for i in range(len(PINS))]
            if ready
            else [],
            worker_wall_s=perf_counter() - start,
            files={n: stock.digest(out / n) for n in names},
        ),
    )


def solve(work, out):
    detector = stock.sealed(out, "detector-lock.json")
    if not detector["ready"] or freeze(out) != stock.read(out / "source-lock.json"):
        raise ValueError("profile execution needs a complete authenticated dual-IQ/numerical panel")
    table = stock.read(out / "causal-authority.json")
    archive = work / "public/tle/archive/space-track"
    if {p.name: stock.digest(p) for p in archive.glob("*.tle")} != {
        k: v["sha256"] for k, v in table.items()
    }:
        raise ValueError("causal catalogues differ from one or more exact frozen snapshots")
    all_rows, traces = [], []
    for arm in model.ARMS:
        stock.sealed(out / arm, "detector-lock.json")
        requests = stock.read(out / arm / "requests.json")
        public = work / "public" / arm
        if len(requests) != 2 or any(
            stock.digest(public / r["native"]) != r["native_sha256"]
            or stock.digest(public / r["track_config"]) != r["config_sha256"]
            for r in requests
        ):
            raise ValueError(
                "each background has two identical geometry offers bound to native and config"
            )
        for method, install in zip(METHODS, (stock.INSTALL, interior.PROFILE), strict=True):
            scratch = work / f"{arm}-{method}"
            scratch.mkdir()
            (scratch / "public").symlink_to(public, target_is_directory=True)
            with (
                patch.multiple(stock, INSTALL=install, METHOD=method),
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                jobs = [
                    pool.submit(stock.position_attempt, scratch, r, cpu)
                    for r, cpu in zip(requests, PINS, strict=True)
                ]
                rows = [j.result() for j in jobs]
            for r in rows:
                trace = scratch / "attempts" / r["id"]
                traces.append(
                    dict(
                        arm=arm,
                        method=method,
                        id=r["id"],
                        launch=(trace / "stderr.log").read_text(errors="replace"),
                    )
                )
                r.update(variant=arm, document_sha256=stock.digest(out / "schedule.json"))
                print(arm, method, r["id"], r["result"]["status"], flush=True)
            all_rows.extend(rows)
    stock.pack(out, "positions.jsonl.gz", all_rows)
    save_json(out / "runtime-proofs.json", traces)
    names = (
        "positions.jsonl.gz",
        "runtime-proofs.json",
        "detector-lock.json",
        "source-lock.json",
        "input-lock.json",
    )
    save_json(
        out / "prediction-lock.json",
        dict(cases=[r["id"] for r in requests], files={n: stock.digest(out / n) for n in names}),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("prepare", "detect", "lane", "position"))
    p.add_argument("work", type=Path)
    p.add_argument("--out", default=REPORT, type=Path)
    p.add_argument("--seed-hex")
    p.add_argument("--lane", type=int, choices=range(2))
    a = p.parse_args()
    with patch.multiple(
        stock, model=model, freeze=freeze, revised=holdout.revised, ANCHOR_DELAY_S=ANCHOR_DELAY_S
    ):
        if a.action == "prepare":
            prepare(a.work, a.out, a.seed_hex)
        elif a.action == "detect":
            detect(a.work, a.out)
        elif a.action == "lane":
            lane(a.work, a.out, a.lane)
        else:
            solve(a.work, a.out)


if __name__ == "__main__":
    main()
