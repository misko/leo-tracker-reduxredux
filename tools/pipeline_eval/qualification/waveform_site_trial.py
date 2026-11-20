"""Bound a blind synthesized CI16 → stock wide GLRT → installed position replay."""

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
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from leo.analysis.starlink import native_short_window, templates

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, save_json, write
from ..scoring import ARMS, validate_result
from . import boundary_policy_trial as compact
from . import clock_transfer_inputs, cold_scenes
from . import waveform_site_model as model
from .armijo_finish_results import pack
from .full_v5_check import _from_native
from .wide_regional_eval import templates as detector_templates

REPORT = ROOT / "reports/2026_11_19_receiver_screening/track-recovery/waveform-site"
LIBRARY = Path("/srv/bulk/leo-dev/20261119-wide-regional/wide/libleo-adaptive-detector.so")
LIBRARY_SHA = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"
INSTALL = compact.INSTALL
DET_CPUS = (20, 21)
POS_CPUS = (21, 23)
DET_LIMIT, POS_LIMIT = 210, 225
MEMORY = 536870912
ANCHOR_DELAY_S = 3740
METHOD = "waveform_site_phase_release"
BOUNDARY = "Synthetic dual CI16 Qin waveform through stock wide GLRT and installed phase release"

digest, read = compact.digest, compact.read


def raw_digest(data):
    return sha256(data).hexdigest()


def freeze(out):
    paths = (
        Path(__file__),
        Path(model.__file__),
        Path(cold_scenes.__file__),
        Path(clock_transfer_inputs.__file__),
        Path(compact.__file__),
        Path(native_short_window.__file__),
        Path(templates.__file__),
        out / "PROTOCOL.md",
        ROOT / "tools/pipeline_eval/qualification/full_v5_check.py",
        ROOT / "tools/pipeline_eval/qualification/wide_regional_eval.py",
    )
    if digest(LIBRARY) != LIBRARY_SHA:
        raise ValueError("stock compiled wide detector differs from the approved release")
    installed = whole_iq.receiver_identity(INSTALL)
    if installed != read(compact.OLDER / "executables.json")["phase-release"]:
        raise ValueError("installed phase-release identity differs from its release receipt")
    template_hashes = {
        edge: [raw_digest(t.tobytes()) for t in detector_templates(model.RATE, edge)]
        for edge in ("lower", "upper")
    }
    return dict(
        sources={str(p): digest(p) for p in paths},
        library_sha256=LIBRARY_SHA,
        installed=installed,
        detector_templates=template_hashes,
        detector_cpus=list(DET_CPUS),
        position_cpus=list(POS_CPUS),
        memory_max=MEMORY,
        swap_max=0,
        detector_limit_s=DET_LIMIT,
        position_limit_s=POS_LIMIT,
        numpy=np.__version__,
        python=sys.version.split()[0],
    )


def revised(received, digest_old):
    candidates = []
    for p in cold_scenes.SNAPSHOT.parent.glob("*.json"):
        r = read(p)
        stamp = cold_scenes._stamp(datetime.fromisoformat(r["retrieved_at"]))
        latest = cold_scenes._stamp(datetime.fromisoformat(r["tle_epoch_max"]))
        if (
            latest <= stamp
            and received + 10800 * cold_scenes.NS <= stamp <= (received + 21600 * cold_scenes.NS)
            and r["raw_sha256"] != digest_old
        ):
            candidates.append((stamp, p, r))
    stamp, path, authority = min(candidates)
    blob = (cold_scenes.TLE_ARCHIVE / authority["raw_object"]).read_bytes()
    if raw_digest(blob) != authority["raw_sha256"]:
        raise ValueError("revised generating effect differs from authenticated TLE")
    return (
        blob,
        stamp,
        dict(
            collection_utc_ns=stamp,
            metadata_sha256=digest(path),
            raw_sha256=raw_digest(blob),
            raw_object=authority["raw_object"],
        ),
    )


def prepare(work, out, seed_hex):
    if (out / "source-lock.json").exists():
        raise FileExistsError("choose an unused report and prospective seed")
    work.mkdir(mode=0o700)
    public = work / "public"
    archive = public / "tle/archive/space-track"
    archive.mkdir(parents=True)
    save_json(out / "source-lock.json", freeze(out))
    previous = compact.OLDER
    history_path = previous / "catalogue-authority.json"
    if digest(history_path) != read(previous / "input-lock.json")["catalogue_authority_sha256"]:
        raise ValueError("previous causal archive authority changed")
    history = read(history_path)
    for filename, r in history.items():
        raw = (compact.OLD_PUBLIC / "tle/archive/space-track" / filename).read_bytes()
        if raw_digest(raw) != r["sha256"]:
            raise ValueError("causal snapshot no longer matches the archive authority")
        write(archive / filename, raw)
    latest = max(history, key=lambda f: history[f]["collected_utc_ns"])
    nominal = (archive / latest).read_bytes()
    old_sha, received = raw_digest(nominal), history[latest]["collected_utc_ns"]
    anchor = received + ANCHOR_DELAY_S * cold_scenes.NS
    truth_orbits, later, authority = revised(received, old_sha)
    if later <= anchor + 300 * cold_scenes.NS or authority["raw_sha256"] in {
        x["sha256"] for x in history.values()
    }:
        raise ValueError("truth orbit collection cannot be visible to the estimator")
    seed = bytes.fromhex(seed_hex) if seed_hex else secrets.token_bytes(32)
    if len(seed) != 32:
        raise ValueError("expected one 32-byte prospective seed")
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    truth_bank = clock_transfer_inputs._true_bank(nominal, truth_orbits, anchor, later)
    scan, info = model.make_scene(
        truth_bank, cold_scenes._constellation(nominal, received), anchor, rng
    )
    config = (previous / "track-config.json").read_bytes()
    if raw_digest(config) not in {r["config_sha256"] for r in read(previous / "requests.json")}:
        raise ValueError("old TrackConfig does not bind the installed release")
    write(public / "track-config.json", config)
    write(out / "track-config.json", config)
    write(out / "causal-authority.json", history_path.read_bytes())
    public_scan = [
        {k: x[k] for k in ("visit", "channel", "edge", "rf_hz", "relative_counter")} for x in scan
    ]
    session = rng.bytes(16).hex()
    uses = []
    for condition, center in info["offers"].items():
        ident = rng.bytes(16).hex()
        uses.append(dict(id=ident, tile=center, screen_center=center))
        info.setdefault("conditions", {})[ident] = condition
    rng.shuffle(uses)
    save_json(
        out / "schedule.json",
        dict(
            session=session,
            visits=public_scan,
            offers=uses,
            anchor_utc_ns=anchor,
            catalog_sha256=old_sha,
        ),
    )
    save_json(
        work / "custodian.json", dict(seed=seed.hex(), scene=info, visits=scan, truth_tle=authority)
    )
    save_json(
        out / "input-lock.json",
        dict(
            files={
                name: digest(out / name)
                for name in (
                    "source-lock.json",
                    "schedule.json",
                    "causal-authority.json",
                    "track-config.json",
                )
            },
            private_sha256=digest(work / "custodian.json"),
            seed_sha256=raw_digest(seed),
        ),
    )


def sealed(out, name):
    lock = read(out / name)
    if any(digest(out / path) != expected for path, expected in lock["files"].items()):
        raise ValueError(f"{name} does not authenticate this stage")
    return lock


def detector_lane(work, out, index):
    lock = sealed(out, "input-lock.json")
    if digest(work / "custodian.json") != lock["private_sha256"] or freeze(out) != read(
        out / "source-lock.json"
    ):
        raise ValueError("generator or stock detector changed")
    private = read(work / "custodian.json")
    frames = model.pulse_bank()
    first = private["scene"]["counter"]
    native_invoke = native_short_window.NativeShortWindow
    started = perf_counter()
    with ExitStack() as stack:
        detector = {
            edge: stack.enter_context(
                native_invoke(
                    str(LIBRARY),
                    *detector_templates(model.RATE, edge),
                    sample_rate_hz=model.RATE,
                    receiver_count=2,
                    fractional_epoch=True,
                )
            )
            for edge in frames
        }
        output = stack.enter_context((work / f"lane-{index}.jsonl").open("xb"))
        for visit in private["visits"][index :: len(DET_CPUS)]:
            j, edge = visit["visit"], visit["edge"]
            wall, cpu = perf_counter(), process_time()
            iq = model.iq(visit, private["scene"], frames[edge])
            gen_s = process_time() - cpu
            cpu = process_time()
            actual = detector[edge].analyze(iq)
            native_s = process_time() - cpu
            if [r["receiver_id"] for r in actual["rows"]] != [0, 1]:
                raise ValueError("stock detector changed the receiver order")
            rows = []
            for r in actual["rows"]:
                converted = [_from_native(rank, c) for rank, c in enumerate(r["candidates"])]
                rows.append(
                    dict(
                        visit_index=j,
                        receiver_id=r["receiver_id"],
                        probe_index=0,
                        probe_start_ms=0,
                        channel=visit["channel"],
                        edge=edge,
                        actual_rf_hz=visit["rf_hz"],
                        valid_start_counter=first + visit["relative_counter"],
                        payload_start_sample=j * model.SAMPLES,
                        candidates=[c for c in converted if c is not None],
                    )
                )
            record = dict(
                visit=j,
                iq_sha256=raw_digest(iq.tobytes()),
                stock_sha256=raw_digest(encoded(actual)),
                nbytes=int(iq.nbytes),
                generation_cpu_s=gen_s,
                detector_cpu_s=native_s,
                wall_s=perf_counter() - wall,
                probes=rows,
            )
            output.write(encoded(record) + b"\n")
            output.flush()
    print(f"Lane {index} completed in {perf_counter() - started:.2f} s", flush=True)


def detect(work, out):
    if (out / "detector-lock.json").exists():
        raise FileExistsError("two complete detector lanes already sealed")
    jobs = []
    start = perf_counter()
    for i, cpu in enumerate(DET_CPUS):
        command = [
            "taskset",
            "-c",
            str(cpu),
            sys.executable,
            "-B",
            "-m",
            "tools.pipeline_eval.qualification.waveform_site_trial",
        ]
        jobs.append(
            subprocess.Popen(
                command + ["lane", str(work), "--out", str(out), "--lane", str(i)],
                start_new_session=True,
            )
        )
    try:
        statuses = [j.wait(timeout=max(0.1, DET_LIMIT - (perf_counter() - start))) for j in jobs]
    except subprocess.TimeoutExpired:
        for j in jobs:
            if j.poll() is None:
                os.killpg(j.pid, signal.SIGKILL)
                j.wait()
        statuses = [j.returncode for j in jobs]
    streams = [work / f"lane-{i}.jsonl" for i in range(len(DET_CPUS))]
    measured = [
        json.loads(line) for p in streams if p.exists() for line in p.read_bytes().splitlines()
    ]
    measured.sort(key=lambda x: x["visit"])
    pack(out, "visit-ledger.jsonl.gz", measured)
    design = read(out / "schedule.json")
    ready = statuses == [0, 0] and [m["visit"] for m in measured] == list(
        range(len(design["visits"]))
    )
    names = ["schedule.json", "source-lock.json", "input-lock.json", "visit-ledger.jsonl.gz"]
    if ready:
        probes = [p for v in measured for p in v["probes"]]
        start_counter = probes[0]["valid_start_counter"]
        doc = compact.native.simulated_document(
            design["session"], design["anchor_utc_ns"], probes, start_counter
        )
        doc["provenance"].update(
            scope="Generated Qin CI16 through the unchanged stock wide GLRT",
            detector_sha256=LIBRARY_SHA,
            waveform_digest=raw_digest(encoded([v["iq_sha256"] for v in measured])),
        )
        native = encoded(doc) + b"\n"
        write(work / "public/native.json", native)
        write(out / "native.json.gz", gzip.compress(native, mtime=0))
        requests = [
            dict(
                o,
                session=design["session"],
                native="native.json",
                native_sha256=raw_digest(native),
                track_config="track-config.json",
                config_sha256=digest(work / "public/track-config.json"),
                archive="tle",
                catalog_sha256=design["catalog_sha256"],
            )
            for o in design["offers"]
        ]
        save_json(out / "requests.json", requests)
        names.extend(("native.json.gz", "requests.json"))
    save_json(
        out / "detector-lock.json",
        dict(
            files={name: digest(out / name) for name in names},
            ready=ready,
            statuses=statuses,
            completed_visits=len(measured),
            scheduled_visits=len(design["visits"]),
            worker_wall_s=perf_counter() - start,
        ),
    )


ACCOUNTING = r'path=$(sed -n "s/^0:://p" /proc/self/cgroup); '
ACCOUNTING += r'cg="/sys/fs/cgroup$path"; '
ACCOUNTING += r'printf "SCIENTIFIC-CGROUP %s %s\n" "$(cat "$cg/memory.max")" '
ACCOUNTING += r'"$(cat "$cg/memory.swap.max")" >&2; exec "$@"'


def no_estimate(status, reason):
    return dict(
        status=status,
        reason=reason,
        boundary=BOUNDARY,
        metrics={},
        arms={arm: dict(latlon=None) for arm in ARMS},
    )


def position_attempt(work, case, cpu):
    run = work / "attempts" / case["id"]
    run.mkdir(parents=True)
    unit = "waveform-scene-" + secrets.token_hex(6)
    command = [
        "systemd-run",
        "--user",
        "--pipe",
        "--wait",
        "--quiet",
        f"--unit={unit}",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        f"--property=RuntimeMaxSec={POS_LIMIT}s",
        "--property=KillMode=control-group",
        "--property=MemoryAccounting=yes",
        "--property=CPUAccounting=yes",
        *(f"--setenv={k}={v}" for k, v in THREAD_ENV.items()),
        "/usr/bin/bash",
        "-c",
        ACCOUNTING,
        "accounting",
        *compact.timed_command(run, work / "public", INSTALL, case, cpu),
    ]
    begin = perf_counter()
    with (run / "stderr.log").open("wb") as log:
        try:
            proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=log, timeout=235)
        except subprocess.TimeoutExpired:
            subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, timeout=5)
            proc = None
    wall = perf_counter() - begin
    logs = (run / "stderr.log").read_text(errors="replace").splitlines()
    limits = [s.split()[1:] for s in logs if s.startswith("SCIENTIFIC-CGROUP ")]
    resources = [
        s[len(compact.TIME_PREFIX) :].split() for s in logs if s.startswith(compact.TIME_PREFIX)
    ]
    resource = resources[-1] if resources else (None, None, None)
    if proc is None:
        result = no_estimate("timed_out", "Reached outer 235 s supervision deadline")
    elif not limits or limits[0] != [str(MEMORY), "0"]:
        result = no_estimate("failed", "physical 512 MiB / zero-swap service was not verified")
    elif proc.returncode:
        terminal = subprocess.run(
            ["systemctl", "--user", "show", unit, "-p", "Result", "--value"],
            capture_output=True,
            text=True,
            timeout=4,
        ).stdout.strip()
        result = no_estimate(
            "timed_out" if terminal == "timeout" else "failed",
            terminal or next(iter(reversed(logs)), f"exit {proc.returncode}"),
        )
    else:
        write(run / "installed.json", proc.stdout)
        result = json.loads(proc.stdout)
    validate_result(result)
    row = dict(
        id=case["id"],
        method=METHOD,
        result=result,
        worker_wall_s=wall,
        cpu=cpu,
        worker_cpu_s=float(resource[0]) + float(resource[1]) if resources else None,
        peak_rss_kib=int(resource[2]) if resources else None,
        verified_limits=limits,
        input_sha256=raw_digest(encoded(case)),
        native_sha256=case["native_sha256"],
        catalogue_sha256=case["catalog_sha256"],
    )
    save_json(run / "receipt.json", row)
    return row


def position(work, out):
    detector = sealed(out, "detector-lock.json")
    sealed(out, "input-lock.json")
    history = read(out / "causal-authority.json")
    leaves = work / "public/tle/archive/space-track"
    if {p.name for p in leaves.glob("*.tle")} != set(history) or any(
        digest(leaves / name) != r["sha256"] for name, r in history.items()
    ):
        raise ValueError("the solver causal archive differs from the sealed physical experiment")
    if freeze(out) != read(out / "source-lock.json"):
        raise ValueError("the installed numerical release differs from the frozen source")
    if not detector["ready"]:
        requests = [
            dict(
                o, native_sha256=None, catalog_sha256=read(out / "schedule.json")["catalog_sha256"]
            )
            for o in read(out / "schedule.json")["offers"]
        ]
        rows = [
            dict(
                id=c["id"],
                method=METHOD,
                result=no_estimate("unavailable", "Detector panel incomplete"),
                worker_wall_s=None,
                worker_cpu_s=None,
                peak_rss_kib=None,
                input_sha256=raw_digest(encoded(c)),
                native_sha256=None,
                catalogue_sha256=c["catalog_sha256"],
            )
            for c in requests
        ]
        save_json(out / "requests.json", requests)
    else:
        requests = read(out / "requests.json")
        if {r["native_sha256"] for r in requests} != {digest(work / "public/native.json")} or {
            r["config_sha256"] for r in requests
        } != {digest(work / "public/track-config.json")}:
            raise ValueError("the emitted-waveform native input changed before the actual receiver")
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [
                pool.submit(position_attempt, work, item, cpu)
                for item, cpu in zip(requests, POS_CPUS, strict=True)
            ]
            rows = [job.result() for job in jobs]
        for row in rows:
            print(row["id"], row["result"]["status"], round(row["worker_wall_s"], 2), flush=True)
    pack(out, "positions.jsonl.gz", rows)
    files = (
        "positions.jsonl.gz",
        "source-lock.json",
        "input-lock.json",
        "detector-lock.json",
        "requests.json",
        "causal-authority.json",
    )
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=[r["id"] for r in rows],
            files={name: digest(out / name) for name in files},
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("prepare", "detect", "position", "lane"))
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=REPORT)
    p.add_argument("--seed-hex")
    p.add_argument("--lane", type=int, choices=range(2))
    a = p.parse_args()
    if a.action == "prepare":
        prepare(a.work, a.out, a.seed_hex)
    elif a.action == "lane":
        detector_lane(a.work, a.out, a.lane)
    elif a.action == "detect":
        detect(a.work, a.out)
    else:
        position(a.work, a.out)


if __name__ == "__main__":
    main()
