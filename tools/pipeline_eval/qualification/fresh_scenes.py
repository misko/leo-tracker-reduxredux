"""Prepare and score new supplied tiles without giving truth to receiver workers."""

import argparse
import gzip
import hashlib
import json
import os
import secrets
import site
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import numpy as np

from ..__main__ import THREAD_ENV, encoded, save_json, write
from ..scoring import ARMS, distance_km, distribution, thresholds, validate_result
from . import cold_scenes

REPO = cold_scenes.REPO
REPORT = REPO / "reports/2026_11_19_short_receiver/fresh-scenes"
PROTOCOL = REPORT / "PROTOCOL.md"
METHODS = ("joint_pass_id", "pass_geometry")
MAX_SECONDS = 120
WORKER = """
import importlib
import json
import sys
from types import SimpleNamespace

request = json.load(sys.stdin)
solver = importlib.import_module('tools.pipeline_eval.variants.' + request['method'])
capture = dict(request['capture'])
capture['catalog'] = capture['catalog'].encode('ascii')
result = solver.run(SimpleNamespace(**capture), tile=request['tile'])
json.dump(result, sys.stdout, allow_nan=False)
"""


def _read(path):
    return cold_scenes._read(path)


def _sha(path):
    return cold_scenes._sha(path.read_bytes())


def _new(path, obj):
    cold_scenes._new(path, encoded(obj) + b"\n")


def _sources(methods):
    paths = [
        Path(__file__).resolve(),
        PROTOCOL,
        REPO / "tools/pipeline_eval/variants/rate_triplets.py",
        REPO / "tools/pipeline_eval/qualification/cold_input.py",
        REPO / "tools/pipeline_eval/qualification/cold_scenes.py",
        REPO / "src/leo/sky/frames.py",
        REPO / "src/leo/sky/propagation.py",
    ]
    for m in methods:
        path = REPO / f"tools/pipeline_eval/variants/{m}.py"
        paths.append(path)
        if path.with_suffix(".c").exists():
            paths.append(path.with_suffix(".c"))
    return {str(path.relative_to(REPO)): _sha(path) for path in paths}


def _destination(center, radius, bearing):
    # Spherical destination with exact great-circle range and no solver dependency.
    lat, lon = np.deg2rad(center)
    angle = radius / 6371.0088
    new_lat = np.arcsin(np.sin(lat) * np.cos(angle) + np.cos(lat) * np.sin(angle) * np.cos(bearing))
    new_lon = lon + np.arctan2(
        np.sin(bearing) * np.sin(angle) * np.cos(lat),
        np.cos(angle) - np.sin(lat) * np.sin(new_lat),
    )
    return [float(np.rad2deg(new_lat)), float((np.rad2deg(new_lon) + 180) % 360 - 180)]


def _offers(cases, labels, rng):
    queries, targets = [], {}
    first_tile = None
    for case in cases:
        truth = labels[case]["latlon"]
        if truth is None:
            identifier = rng.bytes(12).hex()
            queries.append(dict(id=identifier, capture_id=case, tile=first_tile))
            targets[identifier] = dict(condition="shuffle", latlon=None, capture_id=case)
            continue
        for condition, interval in (("present", (8, 10)), ("missing", (45, 115))):
            center = _destination(truth, rng.uniform(*interval), rng.uniform(0, 2 * np.pi))
            tile = dict(center=center, width_km=25.0)
            if first_tile is None:
                first_tile = tile
            identifier = rng.bytes(12).hex()
            queries.append(dict(id=identifier, capture_id=case, tile=tile))
            targets[identifier] = dict(condition=condition, latlon=truth, capture_id=case)
    rng.shuffle(queries)
    return queries, targets


def prepare(folder, releases):
    sources = _sources(releases)
    for method, digest in releases.items():
        if sources[f"tools/pipeline_eval/variants/{method}.py"] != digest:
            raise ValueError(f"{method} differs from its predeclared release")
    folder.mkdir(mode=0o700)
    _new(folder / "source-lock.json", dict(sources=sources, methods=list(releases)))
    captures = folder / "captures"
    cold_scenes.generate(captures)
    label_source = captures / "private/truth.json"
    manifest = _read(captures / "public/manifest.json")
    # This is the generator's custodian entry point. The predictor never calls it.
    seed = secrets.token_bytes(32)
    cold_scenes._new(captures / "private/offer-seed.bin", seed)
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    queries, targets = _offers(manifest["order"], _read(label_source), rng)
    public = captures / "public/offers.json"
    private = captures / "private/offer-labels.json"
    _new(public, queries)
    _new(private, targets)
    _new(
        folder / "input-lock.json",
        dict(
            sources_sha256=_sha(folder / "source-lock.json"),
            captures_sha256=_sha(captures / "input-lock.json"),
            offers_sha256=_sha(public),
            labels_sha256=_sha(private),
            offer_seed_sha256=hashlib.sha256(seed).hexdigest(),
        ),
    )


def _check(folder):
    lock = _read(folder / "input-lock.json")
    files = {
        "sources": folder / "source-lock.json",
        "captures": folder / "captures/input-lock.json",
        "offers": folder / "captures/public/offers.json",
    }
    if any(lock[f"{name}_sha256"] != _sha(path) for name, path in files.items()):
        raise ValueError("fresh packet is inconsistent with its input commitment")
    source = _read(files["sources"])
    if source["sources"] != _sources(source["methods"]):
        raise ValueError("source changed after the fresh generator lock")
    cold_scenes._check_lock(folder / "captures")
    queries = _read(files["offers"])
    if len(queries) != 9 or len({q["id"] for q in queries}) != 9:
        raise ValueError("expected the complete nine-query fresh panel")
    return source["methods"], queries


def _sandbox(cpu):
    (packages,) = site.getsitepackages()
    command = [
        "taskset",
        "-c",
        str(cpu),
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--clearenv",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--chdir",
        "/tmp",
        "--setenv",
        "PYTHONPATH",
        "/code:/packages",
        "--setenv",
        "PATH",
        "/usr/bin",
    ]
    for key, value in THREAD_ENV.items():
        command.extend(("--setenv", key, value))
    for source, target in (
        ("/usr", "/usr"),
        ("/lib", "/lib"),
        ("/lib64", "/lib64"),
        ("/etc/alternatives", "/etc/alternatives"),
        (sys.base_prefix, "/python"),
        (packages, "/packages"),
        (str(REPO / "tools/pipeline_eval"), "/code/tools/pipeline_eval"),
        (str(REPO / "src/leo"), "/code/leo"),
    ):
        command.extend(("--ro-bind", source, target))
    interpreter = f"/python/bin/python{sys.version_info.major}.{sys.version_info.minor}"
    return [*command, interpreter, "-B", "-c", WORKER]


def _attempt(folder, method, query, cpu):
    cap = cold_scenes._capture(folder / "captures/public", query["capture_id"])
    payload = encoded(
        dict(
            method=method,
            capture=asdict(cap) | {"catalog": cap.catalog.decode("ascii")},
            tile=query["tile"],
        )
    )
    started = perf_counter()
    try:
        done = subprocess.run(
            _sandbox(cpu), input=payload, capture_output=True, check=True, timeout=MAX_SECONDS
        )
        result = json.loads(done.stdout)
    except subprocess.TimeoutExpired:
        result = dict(
            status="timed_out",
            reason="fixed fresh packet deadline",
            metrics={},
            boundary="Native GLRT candidates and causal TLE to a supplied-tile estimate",
        )
    except subprocess.CalledProcessError as exc:
        result = dict(
            status="failed",
            reason=exc.stderr.decode(errors="replace")[-1600:],
            metrics={},
            boundary="Native GLRT candidates and causal TLE to a supplied-tile estimate",
        )
    validate_result(result)
    return dict(
        id=query["id"],
        capture_id=query["capture_id"],
        method=method,
        native_sha256=cap.native_sha256,
        catalog_sha256=cap.catalog_sha256,
        tile=query["tile"],
        mode="supplied-tile",
        wall_s=perf_counter() - started,
        result=result,
    )


def predict(folder):
    methods, queries = _check(folder)
    cpus = sorted(os.sched_getaffinity(0))
    if not cpus or not set(cpus) <= {17, 18, 19}:
        raise ValueError("pin this worker to CPUs 17–19")
    jobs = [(method, query) for query in queries for method in methods]

    def work(cpu, requests):
        return [_attempt(folder, method, query, cpu) for method, query in requests]

    with ThreadPoolExecutor(len(cpus)) as pool:
        futures = [pool.submit(work, cpu, jobs[i :: len(cpus)]) for i, cpu in enumerate(cpus)]
        rows = [r for future in futures for r in future.result()]
    _check(folder)
    raw = gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0)
    cold_scenes._new(folder / "predictions.jsonl.gz", raw)
    _new(
        folder / "prediction-lock.json",
        dict(
            input_lock_sha256=_sha(folder / "input-lock.json"),
            predictions_sha256=hashlib.sha256(raw).hexdigest(),
            mode="supplied-tile",
            cpus=cpus,
            timeout_s=MAX_SECONDS,
            methods=methods,
            cases=[q["id"] for q in queries],
        ),
    )


def _score_rows(records, targets):
    for record in records:
        target = targets[record["id"]]
        true_site = target["latlon"]
        result = record["result"]
        center = record["tile"]["center"]
        for arm in ARMS:
            point = result.get("arms", {}).get(arm, {})
            fix = point.get("latlon")
            published = fix is not None
            status = result["status"]
            yield dict(
                id=record["id"],
                capture_id=record["capture_id"],
                method=record["method"],
                arm=arm,
                condition=target["condition"],
                mode="supplied-tile",
                status="withheld" if status == "ok" and not published else status,
                reason=result.get("reason"),
                published=published,
                false_publication=published and target["condition"] != "present",
                latlon=fix,
                forced_latlon=point.get("forced_latlon"),
                tile_latlon=center,
                center_error_km=distance_km(center, true_site),
                error_km=distance_km(fix, true_site),
                forced_error_km=distance_km(point.get("forced_latlon"), true_site),
                rf_rms_hz=point.get("rf_rms_hz"),
                conditional_rms_hz=point.get("conditional_rms_hz"),
                heldout_frame_rms_us=point.get("heldout_frame_rms_us"),
                wall_s=record["wall_s"],
            )


def _groups(rows, methods):
    groups = []
    for method in methods:
        for arm in ARMS:
            for condition in ("present", "missing", "shuffle"):
                selected = [
                    r
                    for r in rows
                    if (r["method"], r["arm"], r["condition"]) == (method, arm, condition)
                ]
                errors = [r["error_km"] for r in selected]
                counts = Counter(r["status"] for r in selected)
                groups.append(
                    dict(
                        method=method,
                        arm=arm,
                        condition=condition,
                        attempts=len(selected),
                        publications=sum(r["published"] for r in selected),
                        false_publications=sum(r["false_publication"] for r in selected),
                        withheld=sum(r["status"] == "withheld" for r in selected),
                        status_counts=dict(counts),
                        within_km=thresholds(errors),
                        error_km=distribution(errors),
                        forced_error_km=distribution(r["forced_error_km"] for r in selected),
                        center_error_km=distribution(r["center_error_km"] for r in selected),
                    )
                )
    return groups


def score(folder, output):
    methods, queries = _check(folder)
    lock = _read(folder / "prediction-lock.json")
    raw = folder / "predictions.jsonl.gz"
    if (
        lock["input_lock_sha256"] != _sha(folder / "input-lock.json")
        or lock["predictions_sha256"] != _sha(raw)
        or lock["methods"] != methods
        or lock["cases"] != [q["id"] for q in queries]
    ):
        raise ValueError("predictions differ from the fresh packet prediction seal")
    private = folder / "captures/private"
    truth_file = private / "offer-labels.json"
    packet_lock = _read(folder / "input-lock.json")
    capture_lock = _read(folder / "captures/input-lock.json")
    if (
        _sha(truth_file) != packet_lock["labels_sha256"]
        or _sha(private / "offer-seed.bin") != packet_lock["offer_seed_sha256"]
        or _sha(private / "seed.bin") != capture_lock["seed_sha256"]
    ):
        raise ValueError("labels differ from the fresh input seal")
    labels = _read(truth_file)
    with gzip.open(raw, "rt") as stream:
        records = list(map(json.loads, stream))
    expected = {(method, q["id"]) for q in queries for method in methods}
    if len(records) != len(expected) or {(r["method"], r["id"]) for r in records} != expected:
        raise ValueError("fresh predictions do not cover the matched panel")
    offered = {q["id"]: q for q in queries}
    manifest = _read(folder / "captures/public/manifest.json")
    for r in records:
        q = offered[r["id"]]
        if (
            r["tile"] != q["tile"]
            or r["capture_id"] != q["capture_id"]
            or labels[r["id"]]["capture_id"] != r["capture_id"]
            or r["native_sha256"] != manifest["cases"][r["capture_id"]]
            or r["catalog_sha256"] != cold_scenes.CATALOG_SHA256
        ):
            raise ValueError("sealed predictions do not correspond to their public offers")
    cases = list(_score_rows(records, labels))
    for name in (
        "source-lock.json",
        "input-lock.json",
        "prediction-lock.json",
        "predictions.jsonl.gz",
    ):
        write(output / name, (folder / name).read_bytes())
    for source, name in (
        (folder / "captures/public/manifest.json", "capture-manifest.json"),
        (folder / "captures/input-lock.json", "capture-input-lock.json"),
        (folder / "captures/source-lock.json", "capture-source-lock.json"),
        (folder / "captures/public/offers.json", "offers.json"),
    ):
        write(output / name, source.read_bytes())
    for name in ("seed.bin", "offer-seed.bin"):
        write(
            output / f"{name.removesuffix('.bin')}.hex",
            (private / name).read_bytes().hex().encode() + b"\n",
        )
    save_json(
        output / "scores.json", dict(cases=cases, groups=_groups(cases, methods), labels=labels)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "predict", "score"):
        command = commands.add_parser(name)
        command.add_argument("root", type=Path)
        if name == "prepare":
            command.add_argument(
                "--release", action="append", required=True, help="method=source_sha256"
            )
        if name == "score":
            command.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    if args.command == "prepare":
        releases = dict(text.split("=", 1) for text in args.release)
        if not releases or set(releases) - set(METHODS):
            parser.error("choose the predeclared supplied-tile methods")
        prepare(args.root, releases)
    elif args.command == "predict":
        predict(args.root)
    else:
        score(args.root, args.out)


if __name__ == "__main__":
    main()
