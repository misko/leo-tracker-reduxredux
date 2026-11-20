"""Fit eight independent installed phase-release offers and run the public edge decision."""

import argparse
import gzip
import json
import os
import secrets
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, encoded, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import compact_tile_decision, compact_tile_interior, v5_secant_fit
from . import compact_blind_generator as generator
from . import compact_blind_trial as earlier
from . import portable_v5_transfer as native
from .armijo_finish_results import pack

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
OUT = SCREEN / "receiver-core/boundary-policy"
GUARD = SCREEN / "deployment/transfer-budget/interior-guard"
OLDER = SCREEN / "receiver-core/compact-blind"
ROOF = SCREEN / "acquisition-support/fresh-waveform"
OLD_PUBLIC = Path("/home/mouse9911/.cache/compact-blind-20261119-v2/public")
INSTALL = OLD_PUBLIC.parent / "phase-release"
CPUS = (14, 15)
DEADLINE_S = 175
BOXES = ((33.0, 138.0), (-41.0, -72.0))
ANCHOR_S = (6700, 21750)
MODES = {"center": 3.0, "near-inside": 11.0, "near-outside": 14.0, "far-omission": 40.0}
METHODS = ("compact_tile_interior", "phase-release")
TIME_PREFIX = "BOUNDARY-RESOURCE "

read, digest = earlier.read, earlier.digest


def lock_sources(out, install):
    guard = Path(compact_tile_interior.__file__)
    if digest(guard) != read(GUARD / "source-lock.json")[guard.name]:
        raise ValueError("the historical paired guard changed")
    if v5_secant_fit.STOP_KM != 0.020:
        raise ValueError("the original secant stopping scale changed")
    installed = whole_iq.receiver_identity(install)
    if installed != read(OLDER / "executables.json")["phase-release"]:
        raise ValueError("the requested receiver differs from the actual prior installed release")
    paths = [
        Path(__file__),
        guard,
        Path(v5_secant_fit.__file__),
        Path(compact_tile_decision.__file__),
        Path(generator.__file__),
        Path(earlier.__file__),
        Path(native.__file__),
        Path(generator.orbit.__file__),
        out / "PROTOCOL.md",
        GUARD / "source-lock.json",
        OLDER / "executables.json",
        OLDER / "prediction-lock.json",
        OLDER / "score-lock.json",
        ROOF / "prediction-lock.json",
        ROOF / "source-lock.json",
    ]
    return dict(
        files={str(p): digest(p) for p in paths},
        stop_km=v5_secant_fit.STOP_KM,
        install=str(install),
        installed_files=installed,
        limit_s=DEADLINE_S,
        cpus=list(CPUS),
        decision_route="exact installed JSON bytes passed once through stdin filter in both modes",
    )


def mapped_offers(site, ordinary):
    lat, lon = site
    point = ordinary["omitted"]
    axis = 0 if point[1] != lon else 1
    delta = point[1] - lon if axis == 0 else point[0] - lat
    sign = 1 if delta > 0 else -1
    return {
        mode: generator.regional_offer(site, axis, sign, offset) for mode, offset in MODES.items()
    }


def previously_bound_locations():
    old = read(OLDER / "truth-after-lock.json")["targets"]
    locations = {tuple(t["site"]) for t in old.values()}
    for folder in (GUARD, GUARD.parent):
        truth = read(folder / "released-truth.json")["location"]
        locations.add(tuple(truth))
    for row in read(SCREEN / "integration/edge-holdouts/released-labels.json").values():
        locations.add(tuple(row["location"]))
    return sorted(locations)


def stage(work, out, install, seed_hex=None):
    if (out / "source-lock.json").exists():
        raise FileExistsError("the output already has a prospective source lock")
    work.mkdir(mode=0o700)
    public = work / "public"
    (public / "native").mkdir(mode=0o700, parents=True)
    save_json(out / "source-lock.json", lock_sources(out, install))
    prior = read(OLDER / "input-lock.json")
    history = OLDER / "catalogue-authority.json"
    if digest(history) != prior["catalogue_authority_sha256"]:
        raise ValueError("prior causal authority changed")
    archive = public / "tle/archive/space-track"
    archive.mkdir(parents=True)
    evidence = read(history)
    for filename, auth in evidence.items():
        raw = (OLD_PUBLIC / "tle/archive/space-track" / filename).read_bytes()
        if sha256(raw).hexdigest() != auth["sha256"]:
            raise ValueError("causal collection no longer matches the immutable history")
        write(archive / filename, raw)
    last = max(evidence, key=lambda path: evidence[path]["collected_utc_ns"])
    nominal, received = (archive / last).read_bytes(), evidence[last]["collected_utc_ns"]
    config = (OLDER / "track-config.json").read_bytes()
    if sha256(config).hexdigest() not in {
        r["config_sha256"] for r in read(OLDER / "requests.json")
    }:
        raise ValueError("track configuration differs from the earlier installed release")
    write(public / "track-config.json", config)
    write(out / "track-config.json", config)
    write(out / "catalogue-authority.json", history.read_bytes())
    (out / "native").mkdir()
    nearby = previously_bound_locations()
    seed = bytes.fromhex(seed_hex) if seed_hex else secrets.token_bytes(32)
    if len(seed) != 32:
        raise ValueError("use one 32-byte seeded draw")
    random = np.random.default_rng(int.from_bytes(seed, "big"))
    requests, labels = [], {}
    with patch.multiple(generator, BOXES=BOXES, ANCHOR_OFFSETS_S=ANCHOR_S):
        for i in range(2):
            anchor, probes, counter, offers, truth = generator.make_case(
                nominal, received, i, random
            )
            nearest = min(distance_km(truth["site"], location) for location in nearby)
            if nearest < 1000:
                raise ValueError("the frozen draw is nearer than 1,000 km to a bound earlier site")
            session = random.bytes(16).hex()
            obj = native.simulated_document(session, anchor, probes, counter)
            doc = encoded(obj) + b"\n"
            name = f"native/{session}.json"
            write(public / name, doc)
            write(out / (name + ".gz"), gzip.compress(doc, mtime=0))
            cutoff = obj["clock_anchor"]["before"]["realtime_ns"]
            if cutoff <= received:
                raise ValueError("a collection is unavailable at the capture cutoff")
            for mode, tile in mapped_offers(truth["site"], offers).items():
                key = random.bytes(16).hex()
                requests.append(
                    dict(
                        id=key,
                        session=session,
                        native=name,
                        native_sha256=sha256(doc).hexdigest(),
                        track_config="track-config.json",
                        config_sha256=sha256(config).hexdigest(),
                        archive="tle",
                        catalog_sha256=sha256(nominal).hexdigest(),
                        cutoff_utc_ns=cutoff,
                        tile=tile,
                        screen_center=tile,
                    )
                )
                labels[key] = dict(
                    mode=mode, session=session, nearest_older_site_km=nearest, **truth
                )
    random.shuffle(requests)
    save_json(public / "requests.json", requests)
    write(out / "requests.json", (public / "requests.json").read_bytes())
    save_json(work / "private.json", dict(seed_hex=seed.hex(), labels=labels))
    save_json(
        out / "input-lock.json",
        dict(
            requests_sha256=digest(out / "requests.json"),
            source_sha256=digest(out / "source-lock.json"),
            private_sha256=digest(work / "private.json"),
            history_sha256=digest(out / "catalogue-authority.json"),
        ),
    )


def timed_command(work, public, install, case, cpu):
    cmd = earlier.isolated(work, public, install, case, cpu)
    cmd = cmd[cmd.index("taskset") :]
    start = cmd.index("-IB") - 1
    if cmd[start] != sys.executable:
        raise ValueError("could not bind the installed numerical process time")
    cmd[start:start] = ["/usr/bin/time", "-f", TIME_PREFIX + "%U %S %M", "--"]
    return cmd


def terminal(public, install, case, work, cpu):
    work.mkdir(parents=True)
    start = perf_counter()
    with (work / "stderr.log").open("wb") as log:
        proc = subprocess.Popen(
            timed_command(work, public, install, case, cpu),
            stdout=subprocess.PIPE,
            stderr=log,
            start_new_session=True,
        )
        try:
            raw, _ = proc.communicate(timeout=DEADLINE_S)
            status = "failed" if proc.returncode else None
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raw, status = b"", "timed_out"
    wall = perf_counter() - start
    logs = (work / "stderr.log").read_text(errors="replace").splitlines()
    timed = [line[len(TIME_PREFIX) :] for line in logs if line.startswith(TIME_PREFIX)]
    user, system, rss = timed[-1].split() if timed else (None, None, None)
    issued = status is None
    if not issued:
        reason = (
            f"Reached {DEADLINE_S} s wall limit"
            if status == "timed_out"
            else (
                next(
                    (line for line in reversed(logs) if line and not line.startswith(TIME_PREFIX)),
                    f"receiver exit {proc.returncode}",
                )
            )
        )
        raw = (
            encoded(
                dict(
                    status=status,
                    reason=reason,
                    boundary=earlier.BOUNDARY,
                    metrics={},
                    arms={a: dict(latlon=None) for a in ARMS},
                )
            )
            + b"\n"
        )
    module = [sys.executable, "-B", "-m", "tools.pipeline_eval.variants.compact_tile_decision"]
    original = subprocess.run(module, input=raw, capture_output=True, check=True, timeout=15).stdout
    if original != raw:
        raise ValueError("flag-off policy CLI altered the installed result bytes")
    tick = perf_counter()
    guarded = subprocess.run(
        module + ["--interior-guard", "--tile", *map(str, case["tile"])],
        input=original,
        capture_output=True,
        check=True,
        timeout=15,
    ).stdout
    guard_wall = perf_counter() - tick
    write(work / "installed.stdout.json", original)
    write(work / "guarded.stdout.json", guarded)
    rows = []
    for method, blob in zip(METHODS, (guarded, original), strict=True):
        result = json.loads(blob)
        validate_result(result)
        rows.append(
            dict(
                id=case["id"],
                method=method,
                result=result,
                cpu=cpu,
                worker_wall_s=wall,
                worker_cpu_s=float(user) + float(system) if timed else None,
                peak_rss_kib=int(rss) if timed else None,
                decision_cli_wall_s=guard_wall if method == METHODS[0] else None,
                input_sha256=sha256(encoded(case)).hexdigest(),
                native_sha256=case["native_sha256"],
                catalogue_sha256=case["catalog_sha256"],
                off_exact_byte_match=True,
                installed_cli_returned=issued,
                installed_stdout_sha256=sha256(raw).hexdigest(),
                decision_bytes_sha256=sha256(blob).hexdigest(),
            )
        )
    save_json(work / "rows.json", rows)
    print(
        case["id"],
        rows[1]["result"]["status"],
        rows[0]["result"]["status"],
        round(wall, 2),
        flush=True,
    )
    return rows


def predict(work, out):
    plan = read(out / "source-lock.json")
    install = Path(plan["install"])
    if plan != lock_sources(out, install):
        raise ValueError("frozen guard, simulator, or installed receiver changed")
    public = work / "public"
    pin = read(out / "input-lock.json")
    if (
        digest(out / "source-lock.json") != pin["source_sha256"]
        or digest(public / "requests.json") != pin["requests_sha256"]
        or digest(out / "catalogue-authority.json") != pin["history_sha256"]
        or any(
            digest(public / "tle/archive/space-track" / k) != r["sha256"]
            for k, r in read(out / "catalogue-authority.json").items()
        )
    ):
        raise ValueError("public request or history changed")
    requests = read(public / "requests.json")
    if len(requests) != 8 or any(
        digest(public / r["native"]) != r["native_sha256"]
        or digest(public / r["track_config"]) != r["config_sha256"]
        for r in requests
    ):
        raise ValueError("wrong native panel or TrackConfig")

    def fit_lane(i, cpu):
        return [
            r
            for case in requests[i::2]
            for r in terminal(
                public,
                install,
                case,
                work / "attempts" / case["id"],
                cpu,
            )
        ]

    start = perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(fit_lane, i, cpu) for i, cpu in enumerate(CPUS)]
        rows = [row for job in jobs for row in job.result()]
    pack(out, "positions.jsonl.gz", rows)
    with (out / "cli-outputs.tar.gz").open("xb") as stream:
        import tarfile

        with tarfile.open(fileobj=stream, mode="w:gz") as tape:
            for case in requests:
                for name in ("installed.stdout.json", "guarded.stdout.json", "stderr.log"):
                    path = work / "attempts" / case["id"] / name
                    tape.add(path, arcname=f"{case['id']}/{name}")
    names = (
        "positions.jsonl.gz",
        "cli-outputs.tar.gz",
        "source-lock.json",
        "input-lock.json",
        "requests.json",
        "catalogue-authority.json",
    )
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=[r["id"] for r in requests],
            files={name: digest(out / name) for name in names},
            worker_wall_s=perf_counter() - start,
            decision_route=plan["decision_route"],
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("stage", "predict"))
    p.add_argument("work", type=Path)
    p.add_argument("--out", default=OUT, type=Path)
    p.add_argument("--install", default=INSTALL, type=Path)
    p.add_argument("--seed-hex")
    args = p.parse_args()
    if args.action == "stage":
        stage(args.work.resolve(), args.out.resolve(), args.install.resolve(), args.seed_hex)
    else:
        predict(args.work.resolve(), args.out.resolve())


if __name__ == "__main__":
    main()
