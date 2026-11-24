"""Inspect only receipt-named local experimental storage for original inputs."""

import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from time import perf_counter_ns, time_ns


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE/"measurements"
MAX_DEPTH = 5
MAX_ENTRIES = 1500
NON_WAVEFORM_DIRS = {"tle", "fonts", "font-cache"}
STAGE = "leo-v3-guarded-selective-0016-stage01"
ROOTS = {
    "/dev/shm": (
        (STAGE, "first complete original member, stopped staging"),
        ("leo-v3-continued-first-0016-result02", "first-member receiver comparison"),
        ("leo-future-capture-storage-0016-result01", "first-member future layout exploratory output"),
        ("leo-future-capture-storage-0016-result02", "first-member future layout exact recovery"),
        ("leo-v3-raw-0016-best-results-01", "full original 0016 named and mixed publications"),
        ("leo-v3-raw-cfo-0016-result03", "full physical candidate output"),
        ("leo-eight-ms-DS30-0016-warm", "8/12 ms full original 0016 comparison"),
        ("leo-v3-saved-0191-pair-01", "0191 clock-only staged packet"),
        ("leo-v3-raw-band-pair-0306-result02", "405-visit physical raw withhold"),
        ("leo-v3-saved-0316-pair-01", "medium 0316 staged saved publication"),
        ("leo-v3-block-portable-0316-result01", "medium 0316 combined saved publication"),
        ("leo-v3-raw-combined-0340-result01", "larger physical acquisition outputs"),
        ("leo-receiver-ceiling-0169-results01", "signed original 0169 first-member stage"),
        ("leo-v3-continued-cfo-0107-pair01", "29-visit original 0107 route and retained input"),
        ("leo-v3-ready-io-original-0008", "earlier dense read-only readiness envelope"),
        ("leo-v3-mixed-final-0008-01", "dense complete saved numerical publication"),
    ),
    "/var/tmp": (
        ("leo-full-short-DS30-0016-pair", "previous full physical 0016 tight pair"),
        ("leo-full-short-dense-DS30-0008", "previous full dense physical publication"),
    ),
}


def unique_files(root, device, *, depth=MAX_DEPTH, entry_limit=MAX_ENTRIES):
    """Use lexically bounded on-device lstat only, never follow symlinks."""
    paths, unavailable, skipped = {}, [], []
    visited, pending = 0, [(root, 0)]
    while pending:
        path, level = pending.pop()
        visited += 1
        if visited > entry_limit:
            raise ValueError("Targeted local metadata scope exceeded its entry cap")
        try:
            info = path.lstat()
        except OSError as exc:
            unavailable.append(dict(path=str(path), errno=exc.errno))
            continue
        if info.st_dev != device or stat.S_ISLNK(info.st_mode):
            skipped.append(str(path))
        elif stat.S_ISREG(info.st_mode):
            paths[path] = info
        elif stat.S_ISDIR(info.st_mode):
            if path.name in NON_WAVEFORM_DIRS:
                skipped.append(str(path))
            elif level > depth:
                skipped.append(str(path))
            else:
                try:
                    pending.extend((child, level+1) for child in sorted(path.iterdir(), reverse=True))
                except OSError as exc:
                    unavailable.append(dict(path=str(path), errno=exc.errno))
    return paths, dict(entries=visited, unavailable=unavailable, policy_skipped=skipped)


def bytes_by_inode(paths):
    return sum({(info.st_dev, info.st_ino): info.st_size for info in paths.values()}.values())


def compare_lengths(required, paths):
    """Nominate names by verified expected length, with hard links counted once."""
    candidates = defaultdict(dict)
    lengths = Counter(required)
    for path, info in paths.items():
        if info.st_size in lengths:
            candidates[info.st_size].setdefault((info.st_dev, info.st_ino), str(path))
    matches = {size: list(entries.values()) for size, entries in sorted(candidates.items())}
    missing = {size: count-len(candidates.get(size, {})) for size, count in lengths.items()
               if len(candidates.get(size, {})) < count}
    return dict(potential_matches=matches, missing_by_length=missing, all_lengths_present=not missing)


def read_evidence(name):
    data = (MEASUREMENTS/name).read_bytes()
    return (json.loads(gzip.decompress(data) if name.endswith(".gz") else data), sha256(data).hexdigest())


def run(output):
    started, clock = time_ns(), perf_counter_ns()
    names = ("guarded-cfo-0016-stopped-stage.json.gz", "small-raw-passive-residency.json.gz",
             "select-before-cfo-0191-preflight.json", "short-prefetch-residency.json.gz",
             "prospective-small-physical-admission.json")
    documents, pins = zip(*(read_evidence(name) for name in names), strict=True)
    stopped, roster, nineteen, older, medium = documents
    all_files, surveyed = {}, {}
    for prefix, scopes in ROOTS.items():
        parent = Path(prefix)
        device = parent.stat().st_dev
        if (prefix == "/dev/shm" and os.major(device) != 0) or (prefix == "/var/tmp" and os.minor(device) != 0):
            raise ValueError("The fixed local metadata device identity changed")
        for name, reason in scopes:
            root = parent/name
            paths, audit = unique_files(root, device)
            all_files.update(paths)
            largest = sorted(((info.st_size, str(path.relative_to(root))) for path, info in paths.items()),
                             reverse=True)[:4]
            surveyed[str(root)] = dict(reason=reason, device=[os.major(device), os.minor(device)], largest=largest,
                                       files=len(paths), distinct_logical_bytes=bytes_by_inode(paths), **audit)
    byte_source = int(nineteen["original"]["compressed_bytes"])
    small = {row["case"]: row for row in roster["rows"]}
    lengths_0057 = [row["payload"]["bytes"] for segment in older["cases"]["DS30-0057"]["segments"]
                    for row in segment["members"]]
    payloads = [row for row in stopped["files"] if row["kind"] == "payload"]
    extent = {kind: compare_lengths([row["signed_bytes"] for row in stopped["files"] if row["kind"] == kind], all_files)
              for kind in ("payload", "index", "manifest")}
    stage = Path(stopped["partial"])
    stopped_state = []
    for row in stopped["files"]:
        path = stage/row["relative"]
        measured = all_files[path].st_size if path in all_files else 0
        stopped_state.append(dict(kind=row["kind"], relative=row["relative"], required=row["signed_bytes"],
                                   observed=measured, prior_authenticated_complete=row["verified_complete"]))
    # A loose CI16 or aggregate copy needs at least the full recording volume.
    # Difference between the two encodings cannot rescue files smaller than
    # either extent, nor reconstruct missing original lane captures from factors.
    total = bytes_by_inode(all_files)
    payload_total = sum(row["signed_bytes"] for row in payloads)
    decoded = {"DS30-0016": 1_292_800_000, "DS30-0191": nineteen["original"]["decoded_bytes"],
               "DS30-0316": medium["decoded_bytes"]}
    compressed = {"DS30-0016": payload_total, "DS30-0049": small["DS30-0049"]["bytes"],
                  "DS30-0191": byte_source, "DS30-0057": sum(lengths_0057), "DS30-0316": medium["compressed_bytes"]}
    rows = {case: dict(original_compressed_bytes=volume, union_inspected_file_bytes=total,
                      enough_bytes_for_original_compressed=total >= volume,
                      min_compressed_byte_deficit=max(0, volume-total),
                      original_decoded_bytes=decoded.get(case)) for case, volume in compressed.items()}
    result = dict(authoritative_receipt_sha256=dict(zip(names, pins, strict=True)), cases=rows, paths=surveyed,
                  ds30_0016_extents=extent, ds30_0016_retained_stop=stopped_state,
                  ds30_0057_payload_members=len(lengths_0057),
                  ds30_0057_payload_length_test=compare_lengths(lengths_0057, all_files),
                  original_waveform_bytes_read=0, original_waveform_files_opened=0, original_device_paths_opened=0,
                  hash_verification="original receipts only, no candidate bodies read", launches=0,
                  total_distinct_logical_bytes=total, total_named_roots=len(surveyed),
                  source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  started_unix_ns=started, elapsed_ns=perf_counter_ns()-clock)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
