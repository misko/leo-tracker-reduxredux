"""Apply one locked causal gain scale to complete wide replay factors."""

import argparse
import gzip
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import distribution
from ..variants import peak_null
from . import cavity_payload_transfer as receiver
from .input_factor_bridge import BULK, REPO, _load_case, _sha, check, checked_history, read

SCREEN = REPO / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "acquisition-support/peak-null"
SOURCE = SCREEN / "detector-origins/whole-band"
PHASE = SCREEN / "detector-origins/whole-pressure/installed-profile.json"
ORDINARY = REPO / "reports/2026_11_19_receiver_frontend/ordinary/recording-receipts.json"
DEVELOPMENT = ("DS26-0036", "DS29-0082")
RESERVE = ("DS26-0122", "DS26-0237", "DS29-0174", "DS29-0247")
METHODS = ("peak_null_excess", "wide_unchanged")
CPUS = (10, 11)


def locked_archives(report):
    source = read(SOURCE / "prediction-lock.json")
    cases = sorted((*DEVELOPMENT, *RESERVE))
    if sorted(source["cases"]) != cases:
        raise ValueError("wide authority does not have the exact six recordings")
    resources = SOURCE / "resources.json"
    check(resources, source["files"][resources.name])
    profile = read(PHASE)["plan"]
    bundle = Path(profile["receiver"])
    for filename, digest in profile["receiver_files"].items():
        check(bundle / filename, digest)
    if "PROFILE = 'phase-release'" not in (bundle / "tools/__init__.py").read_text():
        raise ValueError("expected the released phase-release receiver")
    paths = {ident: SOURCE / "native" / f"{ident}.json.gz" for ident in cases}
    for path in paths.values():
        check(path, source["files"][str(path.relative_to(SOURCE))])
    files = (
        Path(__file__),
        Path(peak_null.__file__),
        Path(receiver.__file__),
        receiver.OBSERVER,
        report / "PROTOCOL.md",
        SOURCE / "prediction-lock.json",
        PHASE,
        ORDINARY,
        resources,
        *paths.values(),
    )
    lock = dict(
        cases=cases,
        development=list(DEVELOPMENT),
        reserve=list(RESERVE),
        threads=1,
        worker_cpus=CPUS,
        memory_bytes=receiver.MEMORY,
        deadline_s=receiver.LIMIT_S,
        receiver_path=str(bundle),
        files={str(path.relative_to(REPO)): _sha(path) for path in files},
        phase_release_files=profile["receiver_files"],
    )
    save_json(report / "source-lock.json", lock)
    return lock, bundle, paths, read(resources)


def exchanged_controls(document):
    """Diagnostic only. Keep exact scores and candidate cardinality in every probe."""
    groups = defaultdict(list)
    values = []
    for i, probe in enumerate(document["source"]["probes"]):
        scores = [c["fractional_control_score"] for c in probe["candidates"]]
        values.append(scores)
        groups[(*peak_null.lane_key(probe), len(scores))].append(i)
    exchange = values.copy()
    for indices in groups.values():
        half = len(indices) // 2
        for left, right in zip(indices, indices[half:] + indices[:half], strict=True):
            exchange[left] = values[right]
    return exchange


def prepare(ident, path, resource, ordinary, root):
    case = _load_case(ident)
    request_path = BULK / case["request"]["path"]
    request_sha = check(request_path, case["request"]["sha256"])
    if ordinary["frozen_request_sha256"] != request_sha:
        raise ValueError("ordinary comparison authority uses a different frozen request")
    request = read(request_path)
    job = request["job"]
    config, archive = Path(job["track_config"]["path"]), Path(job["tle_root"])
    history = checked_history(job, request["causal_snapshots"], case["cutoff_utc_ns"])
    catalog = dict(utc_ns=case["catalog_timestamp_ns"], sha256=case["catalog"]["sha256"])
    if history[-1] != catalog or case["regions"][0]["center"] != job["search_center"]:
        raise ValueError("frozen catalogue or region changed")
    payload = gzip.decompress(path.read_bytes())
    document = json.loads(payload)
    source = document["source"]
    if (
        source["session_id"] != case["session_id"]
        or source["input_manifest_sha256"] != resource["input_manifest_sha256"]
        or document["provenance"]["detector_sha256"] != "sha256:" + resource["detector_sha256"]
        or document["clock_anchor"]["before"]["realtime_ns"] != case["cutoff_utc_ns"]
        or len(source["probes"]) != resource["counts"]["probe_rows"]
    ):
        raise ValueError("sealed wide factors do not match the frozen acquisition")
    original = root / f"{ident}.wide.json"
    write(original, payload)
    started, cpu = perf_counter(), process_time()
    adjusted, counts, floors, changes = peak_null.adjusted_document(document)
    elapsed = dict(wall_s=perf_counter() - started, cpu_s=process_time() - cpu)
    if (
        counts["original_candidates"] != resource["counts"]["candidate_rows"]
        or counts["original_passing"] != resource["counts"]["positive_candidates"]
    ):
        raise ValueError("wide detector candidate and gate counts differ")
    changed_path = root / f"{ident}.adjusted.json"
    write(changed_path, encoded(adjusted))
    shared = dict(
        id=ident,
        capture_id=case["session_id"],
        cohort="development" if ident in DEVELOPMENT else "reserve",
        wide_native_sha256=_sha(original),
        wide_archive_sha256=_sha(path),
        paired_ordinary_sha256=ordinary["native_sha256"],
        expected_capture_era_native_sha256=case["native"]["sha256"],
        original_request_sha256=request_sha,
        catalog_sha256=catalog["sha256"],
        history_sha256=sha256(encoded(history)).hexdigest(),
        track_config_sha256=check(config, case["track_config"]["sha256"]),
        screen_center=job["screen_center"],
        tile=dict(case["regions"][0], width_km=25),
    )
    shared["input_sha256"] = sha256(encoded(shared)).hexdigest()
    cases = dict(zip(METHODS, (changed_path, original), strict=True))
    jobs = {
        method: (dict(shared, native_sha256=_sha(native)), native, config, archive, history)
        for method, native in cases.items()
    }
    _, exchanged, _, exchanged_changes = peak_null.adjusted_document(
        document,
        proxy_controls=exchanged_controls(document),
    )
    mapped = {row["probe_index"]: row["new_rank"] for row in exchanged_changes}
    audit = dict(
        adjusted_counts=counts,
        floor=distribution(floors),
        prefilter=elapsed,
        exchange_counts=exchanged,
        same_changed_probe=sum(row["probe_index"] in mapped for row in changes),
        same_replacement=sum(mapped.get(row["probe_index"]) == row["new_rank"] for row in changes),
    )
    return jobs, audit, changes


def run(root, report):
    if (report / "source-lock.json").exists():
        raise ValueError("existing peak-scale source lock")
    root.mkdir(parents=True, exist_ok=False)
    lock, bundle, paths, resources = locked_archives(report)
    ordinary = read(ORDINARY)["recordings"]
    jobs, audit, changes = {}, {}, {}
    for ident in lock["cases"]:
        jobs[ident], audit[ident], changes[ident] = prepare(
            ident,
            paths[ident],
            resources[ident]["wide"],
            ordinary[ident],
            root,
        )
    save_json(
        report / "requests.json",
        {ident: {method: job[0] for method, job in pair.items()} for ident, pair in jobs.items()},
    )
    save_json(
        report / "causal-history.json",
        {ident: pair[METHODS[0]][-1] for ident, pair in jobs.items()},
    )
    save_json(report / "factor-audit.json", audit)
    change_archive = report / "winner-changes.json.gz"
    write(change_archive, gzip.compress(encoded(changes), mtime=0))

    def lane(index):
        rows = []
        for step, ident in enumerate(lock["cases"][index :: len(CPUS)]):
            order = METHODS if (index + step) % 2 == 0 else METHODS[::-1]
            for method in order:
                fit = receiver.capped(
                    root / method, bundle.parent, jobs[ident][method], bundle.name, CPUS[index]
                )
                rows.append(dict(fit, method=method))
                save_json(root / f"partial-{index}.json", rows)
        return rows

    began = perf_counter()
    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        rows = sorted(
            (r for batch in pool.map(lane, range(len(CPUS))) for r in batch),
            key=lambda row: (row["id"], row["method"]),
        )
    for path, digest in lock["files"].items():
        check(REPO / path, digest)
    for path, digest in lock["phase_release_files"].items():
        check(bundle / path, digest)
    for pair in jobs.values():
        for job in pair.values():
            check(job[1], job[0]["native_sha256"])
    observations = report / "predictions.jsonl.gz"
    write(observations, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    files = (
        "source-lock.json",
        "requests.json",
        "causal-history.json",
        "factor-audit.json",
        observations.name,
        change_archive.name,
    )
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=lock["cases"],
            methods=list(METHODS),
            wall_s=perf_counter() - began,
            files={name: _sha(report / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=local_output)
    run(parser.parse_args().root, REPORT)
