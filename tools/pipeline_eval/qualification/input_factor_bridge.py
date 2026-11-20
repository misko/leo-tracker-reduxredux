"""Measure one fixed-input-boundary crossover using the released small receiver."""

import argparse
import gzip
import json
from pathlib import Path

from ..__main__ import encoded, local_output, save_json, write
from . import cavity_payload_transfer as trial
from .fractional_runtime_whole import verify_request
from .full_v5_check import BULK, REPO, _load_case, _sha

SCREEN = REPO / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "next/input-factor-comparison"
RUN = BULK / "leo-dev/receiver-screening-20261119"
IDENT = "DS26-0237"
CPU = 18


def read(path):
    return json.loads(path.read_bytes())


def check(path, expected):
    value = _sha(path)
    if value != expected.removeprefix("sha256:"):
        raise ValueError(f"recorded digest differs for {path}")
    return value


def checked_history(job, snapshots, cutoff):
    paths = list(Path(job["tle_root"]).rglob("*.tle"))
    by_name = {path.name: path for path in paths}
    if len(by_name) != len(paths) or by_name.keys() != snapshots.keys():
        raise ValueError("archived TLE history membership changed")
    history = []
    for name in sorted(by_name):
        stamp = int(name.split("-", 1)[0])
        if stamp >= cutoff:
            raise ValueError("TLE history contains a noncausal snapshot")
        history.append(dict(utc_ns=stamp, sha256=check(by_name[name], snapshots[name])))
    if len(history) < 2:
        raise ValueError("both current and prior catalogue snapshots are required")
    return sorted(history, key=lambda entry: entry["utc_ns"])


def prepare():
    case = _load_case(IDENT)
    held_report = SCREEN / "next/full-held-pair"
    held_lock = read(held_report / "prediction-lock.json")
    source_lock = held_report / "source-lock.json"
    check(source_lock, held_lock["source_lock_sha256"])
    stages = held_report / "stages.json.gz"
    check(stages, held_lock["files"][stages.name])
    replay = json.loads(gzip.decompress(stages.read_bytes()))[IDENT]["optimized_whole_iq"]["raw"]
    old_path = BULK / case["request"]["path"]
    old_sha = check(old_path, case["request"]["sha256"])
    old = read(old_path)
    ordinary = RUN / "full-held-pair" / IDENT
    new_path = ordinary / "position/request.json"
    new_sha = check(new_path, replay["worker_request_sha256"])
    new = read(new_path)
    native = ordinary / "native.json"
    verify_request(new, old, native_path=native, native_sha256=replay["native_sha256"])
    if not replay["factor_parity"]["complete_native_science_exact"]:
        raise ValueError("optimized detector lacks complete ordinary factor parity")
    job = old["job"]
    config = Path(job["track_config"]["path"])
    archive = Path(job["tle_root"])
    history = checked_history(job, old["causal_snapshots"], case["cutoff_utc_ns"])
    if history[-1] != dict(utc_ns=case["catalog_timestamp_ns"], sha256=case["catalog"]["sha256"]):
        raise ValueError("current catalogue changed")
    settings = dict(
        capture_id=case["session_id"],
        catalog_sha256=case["catalog"]["sha256"],
        track_config_sha256=check(config, case["track_config"]["sha256"]),
        screen_center=job["screen_center"],
        tile=dict(case["regions"][0], width_km=25),
    )
    if settings["tile"]["center"] != job["search_center"]:
        raise ValueError("original offered tile differs")
    jobs = []
    for mode, path, digest, request_sha in (
        ("capture-era", BULK / case["native"]["path"], case["native"]["sha256"], old_sha),
        ("ordinary", native, replay["native_sha256"], new_sha),
    ):
        binding = dict(
            settings,
            id=f"{mode}-{IDENT}",
            factor_source=mode,
            native_sha256=check(path, digest),
            request_sha256=request_sha,
        )
        jobs.append((binding, path, config, archive, history))
    return jobs


def run(root, report):
    root.mkdir(parents=True, exist_ok=False)
    release = trial.RELEASE
    package = trial.bound_packages(release)["small"]
    release_path = SCREEN / "next/cavity-payload"
    published = read(release_path / "prediction-lock.json")
    package_path = release_path / "package.json"
    package_sha = check(package_path, published["files"][package_path.name])
    published_package = read(package_path)
    if published_package["count"] != 78 or any(
        package[key] != published_package[key] for key in ("archive_sha256", "files", "binaries")
    ):
        raise ValueError("runtime is not the released 78-source compact package")
    jobs = prepare()
    plan = dict(
        recordings=[dict(job[0], archive=str(job[3]), history=job[-1]) for job in jobs],
        memory_bytes=trial.MEMORY,
        swap_bytes=0,
        deadline_s=trial.LIMIT_S,
        cpu=CPU,
        package_sha256=package_sha,
        sources={
            str(path.relative_to(REPO)): _sha(path)
            for path in (
                Path(__file__),
                Path(trial.__file__),
                trial.OBSERVER,
                report / "PROTOCOL.md",
            )
        },
    )
    save_json(report / "bridge-plan.json", plan)
    rows = []
    for job in jobs:
        rows.append(trial.capped(root, release, job, "small", CPU))
        save_json(root / "partial.json", rows)
    path = report / "bridge-positions.jsonl.gz"
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    save_json(
        report / "bridge-lock.json",
        dict(
            cases=[job[0]["id"] for job in jobs],
            files={p.name: _sha(p) for p in (report / "bridge-plan.json", path)},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=local_output)
    run(parser.parse_args().root, REPORT)
