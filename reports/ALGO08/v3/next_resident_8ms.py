"""Observe only frozen prior physical sources for an exact, resident 20/8 ms pair."""

import argparse
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from stat import S_ISREG
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
BULK = Path("/srv/bulk")
PROTOCOL = HERE / "next-resident-8ms-protocol.md"
ROSTER = HERE / "measurements/small-raw-passive-residency.json.gz"
ROSTER_SHA = "9ba0d638be09a0d4f1053968d5f5ca642ba379abeef06bca27b017b488c58705"
ALTERNATE = HERE / "measurements/alternate-physical-source.json"
ALTERNATE_SHA = "740596489e716270e718bd99631723f44a45a37f50c79efcdc47b6f999a07280"
LEGACY = Path("/dev/shm/leo-v3-short-raw-0180-01/stock/fast-scan-inputs/fast-9c76fca7dc99683b14fab3cbdd3a6614.json")
LEGACY_SHA = "9c76fca7dc99683b14fab3cbdd3a661457193bbe3a00525a18a24f5086c0150f"
ASSIGNED = frozenset(("DS30-0102", "DS30-0084", "DS30-0249", "DS30-0398", "DS30-0306", "DS30-0340", "DS30-0016"))
LOCALS = (
    "leo-v3-continued-cfo-0107-pair01", "leo-v3-short-raw-0180-01", "leo-v3-graph-time-transfer-0102-pair01",
    "leo-v3-raw-band-pair-0306-result02", "leo-v3-raw-combined-0340-result01", "leo-v3-raw-empty-family-0340-result01",
    "leo-v3-raw-0016-best-results-01", "leo-v3-guarded-selective-0016-stage01", "leo-receiver-ceiling-0169-results01",
    "leo-future-capture-storage-0016-result02", "leo-v3-packed-combined-0016-02", "leo-seekable-member-0008-case1",
)
NAMES = {"payload": re.compile(r"iq-\d{6}\.ci16\.zst\Z"), "index": re.compile(r"windows-\d{6}\.jsonl\Z")}


def read_checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"The source manifest or frozen roster changed at {path}")
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def enrollment():
    old = read_checked(ROSTER, ROSTER_SHA)
    cases = [row for row in old["rows"] if row["case"] in ASSIGNED]
    if {row["case"] for row in cases} != ASSIGNED:
        raise ValueError("The small prior census no longer covers the frozen cohort")
    legacy = read_checked(LEGACY, LEGACY_SHA)
    cases.append(dict(case="DS30-0180", visits=legacy["window_count"], bytes=111_464_875,
                      segments=[dict(path=str(Path(item["path"]) / "manifest.json"), sha256=item["manifest_digest"][7:])
                                for item in legacy["segments"]]))
    return sorted(cases, key=lambda case: (case["visits"] < 64, case["visits"], case["case"]))


def fully_resident(snapshot):
    return (not snapshot["unavailable"] and snapshot["members"] == snapshot["observed_members"] > 0
            and snapshot["cached_pages"] == snapshot["observed_file_pages"] > 0)


def member_stubs(folder, group):
    """Names and lengths only when the authenticated manifest itself is missing from cache."""
    seen = []
    for pathname in sorted(folder.iterdir()):
        if NAMES[group].fullmatch(pathname.name):
            info = pathname.lstat()
            if S_ISREG(info.st_mode):
                seen.append((folder, pathname.name, info.st_size))
    return seen


def observe(case, sample):
    known = {"payload": [], "index": []}
    signed_identifiers = {"payload": [], "index": [], "manifest": []}
    manifest_reports = []
    all_verified = True
    for row in case["segments"]:
        path = BULK / row["path"]
        if not path.is_relative_to(BULK / "leo/fast-scan-recordings") or path.name != "manifest.json":
            raise ValueError("Only canonical, archive-proven physical data are enrolled")
        size = path.lstat().st_size
        watch = sample([(path.parent, path.name, size)])
        manifest_reports.append(dict(path=str(path), expected_sha256=row["sha256"], bytes=size, pages=watch))
        signed_identifiers["manifest"].append((size, row["sha256"]))
        if not fully_resident(watch):
            all_verified = False
            for kind in known:
                known[kind].extend(member_stubs(path.parent, kind))
            continue
        value = read_checked(path, row["sha256"])
        for chunk in value["chunks"]:
            for kind, size_key in (("payload", "compressed_bytes"), ("index", "index_bytes")):
                known[kind].append((path.parent, chunk[f"{kind}_relative_path"], chunk[size_key]))
                key = "compressed_sha256" if kind == "payload" else "index_sha256"
                signed_identifiers[kind].append((chunk[size_key], chunk[key].removeprefix("sha256:")))
    observed = {kind: sample(entries) for kind, entries in known.items()}
    complete_lengths = sum(r[2] for r in known["payload"]) == case["bytes"]
    return dict(case=case["case"], issued=case["visits"], official_bytes=case["bytes"],
                manifests=manifest_reports, admitted_original=all_verified and complete_lengths and all(map(fully_resident, observed.values())),
                fully_verified_original_manifest=all_verified, match_prior_payload_extent=complete_lengths,
                scope="authenticated" if all_verified else "segment basename and extent census only",
                observed=observed, files={kind: [dict(path=str(folder/name), bytes=size) for folder,name,size in entries]
                                          for kind,entries in known.items()},
                signed_identifiers=signed_identifiers)


def local_scope(rows):
    from alternate_physical_source import bytes_by_inode, compare_lengths, unique_files

    stage = Path("/dev/shm")
    files, roots = {}, {}
    for name in LOCALS:
        path = stage / name
        found, audit = unique_files(path, stage.stat().st_dev)
        roots[name] = dict(audit, logical_bytes=bytes_by_inode(found),
                           largest=[(found[file].st_size, str(file.relative_to(path)))
                                    for file in sorted(found, key=lambda p: found[p].st_size, reverse=True)[:3]])
        files.update(found)
    prior = read_checked(ALTERNATE, ALTERNATE_SHA)
    shape = {}
    for row in rows:
        groups = {kind: compare_lengths([part["bytes"] for part in parts], files) for kind, parts in row["files"].items()}
        shape[row["case"]] = dict(groups=groups, complete_shape=all(item["all_lengths_present"] for item in groups.values()))
    return dict(roots=roots, candidates=shape, earlier_sha256=ALTERNATE_SHA,
                earlier_0016_missing_payload_bytes=prior["ds30_0016_extents"]["payload"]["missing_by_length"],
                checked_waveform_bodies=0, exact_complete_reconstruction_verified=False)


def run(output):
    from aperture_trial import write
    from empty_bootstrap import checked
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query

    if output.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Use a fresh passive receipt on private tmpfs")
    pressure = Path("/proc/pressure/io")
    before = pressure.read_text()
    checked(CACHE_LIB, CACHE_SHA)
    query = load_query(CACHE_LIB)
    size = os.sysconf("SC_PAGE_SIZE")
    rows = [observe(case, lambda entries: cache_snapshot(entries, size, query)) for case in enrollment()]
    local = local_scope(rows)
    eligible = next((row["case"] for row in rows if row["admitted_original"]), None)
    write(output, dict(order=[row["case"] for row in rows], eligible_official=eligible, cases=rows,
          local=local, io_before=before, io_after=pressure.read_text(), process_euid=os.geteuid(),
          source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),
          roster_sha256=ROSTER_SHA, legacy_inventory_sha256=LEGACY_SHA, original_waveform_bytes=0,
          conditioning_bytes=0, raw_launches=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
