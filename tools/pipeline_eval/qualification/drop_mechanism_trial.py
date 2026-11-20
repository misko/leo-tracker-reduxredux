"""Pair authentic queue loss with a hash-selected loss pattern."""

import argparse
import gzip
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from . import arrival_queue as arrival
from . import arrival_queue_position, bracketed_position, locked_assignments_trial
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows
from .rescue_attribution import sealed
from .whole_pressure_trial import rows_from

REPORT = arrival.PARENT.parent.parent / "arrival-and-timing/drop-mechanism"
PINS = {"DS26-0197": 8, "DS29-0316": 9}
METHODS = {
    "full": "full",
    "retained": "real",
    "hash": "hash",
    "corrected-real": "real",
    "corrected-hash": "hash",
}
LIMIT = 210
WORKER = Path(__file__).with_name("drop_mechanism_worker.py")
SALT = "lane-gaps-v1"
read = whole_iq.read


def count_match(ident, visits, actual):
    size = len(actual)
    possible = sorted(
        visits - actual, key=lambda n: sha256(f"{SALT}:{ident}:{n}".encode()).digest()
    )
    if len(possible) < size:
        raise ValueError("not enough independent valid visits to match actual loss count")
    return set(possible[:size])


def missing_clock(full, dropped):
    source = full["source"]
    start = full["clock_anchor"]["sample_counter"]
    return [
        dict(
            visit=p["visit_index"],
            receiver=p["receiver_id"],
            channel=p["channel"],
            actual_rf_hz=p["actual_rf_hz"],
            time_s=(p["valid_start_counter"] - start) / source["sample_rate_hz"]
            + source["probe_ms"] * 0.0005,
        )
        for p in source["probes"]
        if p["visit_index"] in dropped
    ]


def set_diff(full, retained):
    old, new = (d["source"]["probes"] for d in (full, retained))

    def key(p):
        return p["visit_index"], p["receiver_id"]

    still = {key(p) for p in new}
    if len(still) != len(new) or [p for p in old if key(p) in still] != new:
        raise ValueError("derived factors changed a retained original packet")
    return [p for p in old if key(p) not in still]


def sources():
    variant = WORKER.parent.parent / "variants/drop_reconnect.py"
    paths = (
        Path(__file__),
        WORKER,
        REPORT / "PROTOCOL.md",
        variant,
        Path(arrival_queue_position.__file__),
        *(ROOT / name for name in locked_assignments_trial.sources()),
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def stage(work):
    work.mkdir(exist_ok=False)
    if (REPORT / "plan.json").exists():
        raise FileExistsError("drop mechanism experiment already frozen")
    group = arrival.PARENT
    queue = arrival.REPORT
    archive = rows_from(sealed(group, "prediction-lock.json", "positions.jsonl.gz"))
    original = {r["id"]: r for r in archive if r["method"] == arrival.whole_center_union.METHOD}
    retained = {
        r["id"]: r
        for r in rows_from(
            sealed(queue, "positions-candidate-lock.json", "positions-candidate.jsonl.gz")
        )
    }
    paced = read(
        sealed(queue, "positions-candidate-lock.json", "position-candidate-input-lock.json")
    )
    release = read(sealed(group, "prediction-lock.json", "source-lock.json"))
    bracketed_position.check_release(release)
    plans = {}
    for ident in PINS:
        case, request = whole_iq.binding(ident)
        job = request["job"]
        reference, real_control, drop = original[ident], retained[ident], paced["cases"][ident]
        a = sealed(group, "prediction-lock.json", f"native/candidate/{ident}.json.gz")
        blob = gzip.decompress(a.read_bytes())
        if (
            sha256(blob).hexdigest() != reference["native_sha256"]
            or reference["native_sha256"] != drop["archive_native_sha256"]
            or reference["catalog_sha256"] != case["catalog"]["sha256"]
            or reference["original_request_sha256"] != case["request"]["sha256"]
            or reference["tile"]["center"] != job["search_center"]
            or case["session_id"] != json.loads(blob)["source"]["session_id"]
        ):
            raise ValueError("complete native, position or causal catalogue authority differs")
        actual_path = Path(drop["out"])
        prior_request = read(whole_iq.checked(actual_path / "request.json", drop["request_sha256"]))
        actual_path_file = whole_iq.checked(
            actual_path / "native.json", real_control["native_sha256"]
        )
        if prior_request["native_sha256"] != real_control["native_sha256"]:
            raise ValueError("retained factors differ from their actual position experiment")
        full, reduced = json.loads(blob), read(actual_path_file)
        actual = {r["visit"] for r in drop["dropped"]}
        available = {p["visit_index"] for p in full["source"]["probes"]}
        sham = count_match(ident, available, actual)
        synthetic = arrival_queue_position.subtract(
            full, sham, sha256(encoded(sorted(sham))).hexdigest()
        )
        data = {}
        for name, doc, native, visits in (
            ("full", full, blob, set()),
            ("real", reduced, actual_path_file.read_bytes(), actual),
            ("hash", synthetic, encoded(synthetic) + b"\n", sham),
        ):
            gone = set_diff(full, doc)
            if len(gone) != 2 * len(visits) or {p["visit_index"] for p in gone} != visits:
                raise ValueError("expected exactly both packets on every missing visit")
            folder = work / ident / name
            file, gapfile = folder / "native.json", folder / "gaps.json"
            write(file, native)
            save_json(gapfile, missing_clock(full, visits))
            data[name] = dict(
                native=str(file),
                native_sha256=_sha(file),
                gaps=str(gapfile),
                gaps_sha256=_sha(gapfile),
                omitted_visits=sorted(visits),
                lost_positive_ids=[
                    "sha256:"
                    + sha256(
                        f"{case['session_id']}:{p['receiver_id']}:{p['valid_start_counter']}".encode()
                    ).hexdigest()
                    for p in gone
                    if any(c["passed_fractional_margin_gate"] for c in p["candidates"])
                ],
            )
        plans[ident] = dict(
            source=data,
            session=case["session_id"],
            config=job["track_config"],
            archive=job["tle_root"],
            tile=reference["tile"],
            screen=job["screen_center"],
            catalogue=case["catalog"]["sha256"],
            request_sha256=case["request"]["sha256"],
            paired_capture_sha256=case["native"]["sha256"],
        )
    save_json(
        REPORT / "plan.json",
        dict(
            cases=plans,
            sources=sources(),
            pins=PINS,
            limit_s=LIMIT,
            memory_bytes=whole_iq.MEMORY,
            receiver=release["receiver"],
            receiver_files=release["receiver_files"],
            native_sources=release["native_sources"],
            parents={
                str(path.relative_to(ROOT)): _sha(path)
                for path in (
                    queue / "positions-candidate-lock.json",
                    group / "prediction-lock.json",
                )
            },
        ),
    )
    print("Frozen physical drop comparison", _sha(REPORT / "plan.json"), flush=True)


def launch(work, plan, ident, method):
    cell = plan["cases"][ident]
    inp = cell["source"][METHODS[method]]
    for field in ("native", "gaps"):
        whole_iq.checked(Path(inp[field]), inp[f"{field}_sha256"])
    whole_iq.checked(Path(cell["config"]["path"]), cell["config"]["sha256"])
    out = work / ident / method / "observation"
    out.mkdir(parents=True, exist_ok=False)
    unit = "leo-drop-mechanism-" + uuid4().hex[:10]
    pin = plan["pins"][ident]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--collect",
        f"--unit={unit}",
        f"--working-directory={plan['receiver']}",
        "-p",
        f"MemoryMax={whole_iq.MEMORY}",
        "-p",
        "MemorySwapMax=0",
        "-p",
        "Nice=10",
        "-p",
        f"RuntimeMaxSec={LIMIT}s",
        f"--setenv=TMPDIR={out}",
        "taskset",
        "-c",
        str(pin),
        sys.executable,
        "-IB",
        str(WORKER),
        plan["receiver"],
        str(out),
        str(pin),
        inp["gaps"],
        "corrected" if method.startswith("corrected-") else "ordinary",
        "--native",
        inp["native"],
        "--native-sha256",
        inp["native_sha256"],
        "--session",
        cell["session"],
        "--track-config",
        cell["config"]["path"],
        "--config-sha256",
        cell["config"]["sha256"],
        "--archive",
        cell["archive"],
        "--tile",
        *map(str, cell["tile"]["center"]),
        "--screen-center",
        *map(str, cell["screen"]),
    ]
    log = out / "service.log"
    start = monotonic()
    with log.open("xb") as stream:
        process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
    result = dict(
        id=ident,
        method=method,
        pin=pin,
        returncode=process.returncode,
        supervisor_wall_s=monotonic() - start,
        log_sha256=_sha(log),
        plan_sha256=_sha(REPORT / "plan.json"),
        native_sha256=inp["native_sha256"],
        outcome_sha256=_sha(out / "outcome.json") if (out / "outcome.json").is_file() else None,
        terminal=[
            line.strip()
            for line in log.read_text(errors="replace").splitlines()
            if line.strip().startswith(("Finished with result:", "Memory peak:"))
        ],
    )
    save_json(out / "attempt.json", result)
    print(ident, method, process.returncode, round(result["supervisor_wall_s"], 2), flush=True)
    return result


def run(work):
    plan = read(REPORT / "plan.json")
    if sources() != plan["sources"]:
        raise ValueError("sealed scientific worker changed")
    bracketed_position.check_release(plan)

    def lane(ident):
        return [launch(work, plan, ident, method) for method in METHODS]

    with ThreadPoolExecutor(2) as pool:
        results = [row for lane in pool.map(lane, PINS) for row in lane]
    write(REPORT / "attempts.jsonl.gz", compressed_rows(results))
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(PINS),
            files={name: _sha(REPORT / name) for name in ("plan.json", "attempts.jsonl.gz")},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    stage(args.work)
    run(args.work)
