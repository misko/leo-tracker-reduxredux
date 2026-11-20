"""Replay one frozen ordinary-factor filter and the same standalone stock path."""

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

from ..__main__ import encoded, local_output, save_json, write
from ..variants import coherent_peak_filter
from . import cavity_payload_transfer as receiver
from .input_factor_bridge import BULK, REPO, _load_case, _sha, check, checked_history, read

SCREEN = REPO / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "detector-origins/coherent-peaks"
ORDINARY_RECEIPT = REPO / "reports/2026_11_19_receiver_frontend/ordinary/recording-receipts.json"
ARCHIVE_AUDIT = SCREEN / "streamlined/whole-pair"
PUBLISHED_RELEASE = SCREEN / "next/cavity-payload"
MATCHED = ("DS26-0036", "DS26-0237", "DS29-0082", "DS29-0174")
CPUS = (14, 15)
METHODS = ("coherent_peak", "strict_ordinary")


def roster(ordinary):
    remaining = set(ordinary).difference(MATCHED)
    held = [
        min(
            (name for name in remaining if name.startswith(family)),
            key=lambda name: sha256(f"coherent-peaks-v1/{name}".encode()).digest(),
        )
        for family in ("DS26-", "DS29-")
    ]
    return sorted(set(MATCHED).union(held))


def source_authority(report):
    inventory_path = ARCHIVE_AUDIT / "archive-authority.json.gz"
    inventory_lock = read(ARCHIVE_AUDIT / "archive-authority-lock.json")
    check(inventory_path, inventory_lock["files"][inventory_path.name])
    inventory = json.loads(gzip.decompress(inventory_path.read_bytes()))
    check(ORDINARY_RECEIPT, inventory["previous_ordinary_receipts_sha256"])
    ordinary = read(ORDINARY_RECEIPT)["recordings"]
    packages = receiver.bound_packages(receiver.RELEASE)
    package = PUBLISHED_RELEASE / "package.json"
    published = read(PUBLISHED_RELEASE / "prediction-lock.json")
    check(package, published["files"][package.name])
    declared = read(package)
    if declared["count"] != 78 or any(
        packages["small"][key] != declared[key] for key in ("files", "binaries", "archive_sha256")
    ):
        raise ValueError("expected the published 78-source receiver")
    files = (
        Path(__file__),
        Path(coherent_peak_filter.__file__),
        Path(receiver.__file__),
        receiver.OBSERVER,
        report / "PROTOCOL.md",
        inventory_path,
        ARCHIVE_AUDIT / "archive-authority-lock.json",
        ORDINARY_RECEIPT,
        package,
    )
    lock = dict(
        files={str(path.relative_to(REPO)): _sha(path) for path in files},
        cases=roster(ordinary),
        matched=list(MATCHED),
        cpu=list(CPUS),
        service_memory_bytes=receiver.MEMORY,
        service_deadline_s=receiver.LIMIT_S,
        package_plan_sha256=_sha(receiver.RELEASE / "plan.json"),
        package_sha256=declared["archive_sha256"],
        package_source_count=declared["count"],
    )
    save_json(report / "source-lock.json", lock)
    return lock, inventory["cases"], ordinary


def prepare(ident, inventory, ordinary, root):
    case = _load_case(ident)
    ordinary_path = Path(inventory["ordinary_factor_file"])
    digest = check(ordinary_path, ordinary["native_sha256"])
    if digest != inventory["ordinary_factor_sha256"]:
        raise ValueError("ordinary archive authorities disagree")
    original_path = BULK / case["request"]["path"]
    original_sha = check(original_path, case["request"]["sha256"])
    if original_sha != ordinary["frozen_request_sha256"]:
        raise ValueError("ordinary factors do not bind the requested configuration")
    original = read(original_path)
    job = original["job"]
    config = Path(job["track_config"]["path"])
    archive = Path(job["tle_root"])
    history = checked_history(job, original["causal_snapshots"], case["cutoff_utc_ns"])
    catalog = dict(utc_ns=case["catalog_timestamp_ns"], sha256=case["catalog"]["sha256"])
    if history[-1] != catalog or case["regions"][0]["center"] != job["search_center"]:
        raise ValueError("causal catalogue or offered tile differs")
    document = read(ordinary_path)
    source = document["source"]
    if (
        source["session_id"] != case["session_id"]
        or source["analysis_manifest_sha256"] != ordinary["analysis_manifest_sha256"]
        or source["input_manifest_sha256"] != ordinary["input_manifest_sha256"]
        or document["provenance"]["detector_sha256"] != ordinary["detector_sha256"]
    ):
        raise ValueError("ordinary document does not match acquisition and producer")
    began, cpu = perf_counter(), process_time()
    filtered, counts = coherent_peak_filter.filter_document(document)
    filter_time = dict(filter_wall_s=perf_counter() - began, filter_cpu_s=process_time() - cpu)
    filtered_path = root / f"{ident}.filtered.json"
    write(filtered_path, encoded(filtered))
    shared = dict(
        id=ident,
        capture_id=case["session_id"],
        origin_native_sha256=digest,
        native_sha256=digest,
        expected_capture_era_native_sha256=case["native"]["sha256"],
        request_sha256=original_sha,
        catalog_sha256=catalog["sha256"],
        history_sha256=sha256(encoded(history)).hexdigest(),
        track_config_sha256=check(config, case["track_config"]["sha256"]),
        screen_center=job["screen_center"],
        tile=dict(case["regions"][0], width_km=25),
    )
    shared["input_sha256"] = sha256(encoded(shared)).hexdigest()
    changed = dict(shared, native_sha256=_sha(filtered_path))
    jobs = {
        METHODS[0]: (changed, filtered_path, config, archive, history),
        METHODS[1]: (shared, ordinary_path, config, archive, history),
    }
    return jobs, counts | filter_time


def run(root, report):
    if (report / "source-lock.json").exists():
        raise ValueError("study source lock already exists")
    root.mkdir(parents=True, exist_ok=False)
    lock, inventory, ordinary = source_authority(report)
    pairs, counts = {}, {}
    for ident in lock["cases"]:
        pairs[ident], counts[ident] = prepare(ident, inventory[ident], ordinary[ident], root)
    save_json(report / "factor-counts.json", counts)
    requests = {
        ident: {method: job[0] for method, job in pair.items()} for ident, pair in pairs.items()
    }
    save_json(report / "requests.json", requests)
    save_json(
        report / "causal-history.json",
        {ident: pair[METHODS[0]][-1] for ident, pair in pairs.items()},
    )

    def lane(index):
        rows = []
        for position in range(index, len(lock["cases"]), len(CPUS)):
            ident = lock["cases"][position]
            order = METHODS if position % 2 == 0 else METHODS[::-1]
            for method in order:
                job = pairs[ident][method]
                fit = receiver.capped(root / method, receiver.RELEASE, job, "small", CPUS[index])
                rows.append(dict(fit, method=method))
                save_json(root / f"partial-{index}.json", rows)
        return rows

    began = perf_counter()
    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        rows = sorted(
            [row for batch in pool.map(lane, range(len(CPUS))) for row in batch],
            key=lambda row: (row["id"], row["method"]),
        )
    for path, digest in lock["files"].items():
        check(REPO / path, digest)
    for pair in pairs.values():
        for job in pair.values():
            check(job[1], job[0]["native_sha256"])
    receiver.bound_packages(receiver.RELEASE)
    observations = report / "predictions.jsonl.gz"
    write(observations, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    filenames = (
        "source-lock.json",
        "requests.json",
        "causal-history.json",
        "factor-counts.json",
        observations.name,
    )
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=lock["cases"],
            methods=list(METHODS),
            wall_s=perf_counter() - began,
            files={name: _sha(report / name) for name in filenames},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=local_output)
    run(parser.parse_args().root, REPORT)
