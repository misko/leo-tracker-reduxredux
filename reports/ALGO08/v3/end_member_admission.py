"""Inspect only the first and last original member of three frozen DS30 cases."""

import argparse
from ctypes import CDLL, c_int, c_longlong, c_size_t, c_ubyte, c_void_p, get_errno
import csv
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import stat
from time import time_ns


HERE = Path(__file__).resolve().parent
STAGED = Path("/tmp/ds30-v2-stage-all-6cdbac")
ORIGINAL = Path("/srv/bulk/leo/fast-scan-recordings")
HISTORICAL_SHA = "53e41acd9a52ce18309fa102848ab949b9277b5d29c1597cf4978de94104fc7e"
ENROLLMENT_SHA = "0ce4e6ee4925c114d2723514082548b327ecd144e848adfbc55b5b83bfe12313"
SPEC = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
ASSIGNED = {
    "DS30-0169": (4219, "f71f4c94569ed0f41343aa21d042e21f0f0fbfcf530736f80ee0dc2b4f1b8b7f",
                  "be9e6e39a10a89a298054d08ea51db53b5aec7667ecf9a725373582ac092972d"),
    "DS30-0445": (4312, "ef215da32bca05cd909b3d0d5ab698b90174789a9483acfa3e26d0827fdbeb8a",
                  "bbe565e510db05d42a8a4b68d5687cf33c0cb4885796d674fb6c20b028740312"),
    "DS30-0083": (4807, "bfb61d8973b0981a5fdaf1d43cb4939909ccff289cac4d27118aac720e227fe1",
                  "3a2f3102b548bbcb04a3fa5277ef058bd4e9e6d3ad23f3ec9c38c7306536257c"),
}


def pinned(path, digest):
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest:
        raise ValueError(f"Unexpected saved metadata at {path}")
    return data


def members(segment_windows):
    if type(segment_windows) is not int or not 0 < segment_windows <= 512:
        raise ValueError("Invalid original segment visit count")
    return (segment_windows + 63)//64


def assignments():
    roster = pinned(HERE.parents[1]/"2026_11_21_ds30_full/paired.csv", HISTORICAL_SHA)
    prior = json.loads(pinned(HERE/"measurements/family-endpoint-transfer-enrollment.json", ENROLLMENT_SHA))
    if prior["band"][:3] != [[case, row[0]] for case,row in ASSIGNED.items()]:
        raise ValueError("The local inherited eligibility band changed")
    labels = list(csv.DictReader(StringIO(roster.decode())))
    enrolled = {}
    for case, (issued, pair_sha, inventory_sha) in ASSIGNED.items():
        fixes = [r for r in labels if r["case"] == case and r["original_fix"] == r["compact_fix"] == "True"]
        if {(r["calibration"], r["recording_state"]) for r in fixes} != {
                ("c0", "incomplete"), ("fitted_c", "incomplete")}:
            raise ValueError("Historical captured roster or double-positive label changed")
        root = STAGED/case
        pair = json.loads(pinned(root/"pair.json", pair_sha))
        named = pair["runs"]["candidate"]
        old_cache = pair["cache_observation"]["arms"]["candidate"]
        receipt = named["receipt"]
        session = "fast-" + inventory_sha[:32]
        inventory = json.loads(pinned(root/"candidate/fast-scan-inputs"/f"{session}.json", inventory_sha))
        recording = Path(pair["recording"])
        if (recording.parent != ORIGINAL or pair["candidate_specification_digest"] != SPEC
                or receipt["decision"] != "complete" or receipt["session_id"] != session
                or receipt["window_count"] != issued or inventory["window_count"] != issued
                or inventory["recording_name"] != recording.name or named["elapsed_s"] <= 0):
            raise ValueError("Saved named identity or physical capture changed")
        segments = inventory["segments"]
        paths = [Path(row["path"]) for row in segments]
        captured = [row["windows"] for row in segments]
        if (not all(path.parent == recording and path.name == f"{recording.name}-segment-{i:08d}"
                    for i,path in enumerate(paths))
                or sum(captured) != issued or sum(map(members,captured)) != old_cache["members"]
                or [[str(path/"manifest.json"),row["manifest_digest"]] for path,row in zip(paths,segments,strict=True)]
                != [[row["path"],row["sha256"]] for row in pair["cache_observation"]["manifests"]]):
            raise ValueError("Exact original segment shape, authority or member count changed")
        ends = [(paths[0]/"iq-000000.ci16.zst", segments[0]["manifest_digest"]),
                (paths[-1]/f"iq-{members(captured[-1])-1:06d}.ci16.zst", segments[-1]["manifest_digest"])]
        enrolled[case] = dict(issued=issued, recording_state="incomplete", pair_sha256=pair_sha,
                             inventory_sha256=inventory_sha, recorded_named_seconds=named["elapsed_s"],
                             archived_original_cache=old_cache, ends=[[str(path), pin] for path,pin in ends])
    return enrolled


def mincore_port():
    libc = CDLL(None, use_errno=True)
    libc.mmap.argtypes = [c_void_p,c_size_t,c_int,c_int,c_int,c_longlong]
    libc.mmap.restype = c_void_p
    libc.mincore.argtypes = [c_void_p,c_size_t,c_void_p]
    libc.mincore.restype = c_int
    libc.munmap.argtypes = [c_void_p,c_size_t]
    libc.munmap.restype = c_int
    page = os.sysconf("SC_PAGE_SIZE")

    def query(fd, size):
        count = (size+page-1)//page
        flags = (c_ubyte*count)()
        address = libc.mmap(None,size,0,2,fd,0)
        if address == c_void_p(-1).value:
            raise OSError(get_errno(), "mmap")
        try:
            if libc.mincore(address,size,flags):
                raise OSError(get_errno(), "mincore")
        finally:
            if libc.munmap(address,size):
                raise OSError(get_errno(), "munmap")
        return count, sum(value&1 for value in flags)
    return query


def end_observation(path, manifest, query, expected_length=None):
    row = dict(path=str(path), archived_segment_manifest_sha256=manifest)
    try:
        fd = os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            source = os.fstat(fd)
            if (source.st_uid != os.geteuid() or not stat.S_ISREG(source.st_mode)
                    or source.st_nlink != 1 or source.st_size <= 0
                    or expected_length is not None and source.st_size != expected_length):
                raise ValueError("Unexpected original file owner, type, link count or length")
            pages, resident = query(fd,source.st_size)
            seen = os.fstat(fd)
            if tuple(getattr(source,name) for name in ("st_dev","st_ino","st_size","st_ctime_ns","st_mtime_ns")) != tuple(
                    getattr(seen,name) for name in ("st_dev","st_ino","st_size","st_ctime_ns","st_mtime_ns")):
                raise ValueError("Source descriptor changed during mincore")
            row.update(compressed_bytes=source.st_size, file_pages=pages, cached_pages=resident,
                       source_inode=source.st_ino, source_device=[os.major(source.st_dev),os.minor(source.st_dev)])
        finally:
            os.close(fd)
    except (OSError,ValueError) as exc:
        row["unavailable"] = str(exc)
    return row


def run(output):
    cases = assignments()
    query = mincore_port()
    before = getrusage(RUSAGE_SELF)
    started = time_ns()
    for case,item in cases.items():
        rows = [end_observation(original,manifest,query,78852856 if (case,i)==("DS30-0169",0) else None)
                for i,(original,manifest) in enumerate(item["ends"])]
        item.update(end_observations=rows,both_ends_fully_resident=all(
            row.get("file_pages") and row["cached_pages"] == row["file_pages"] for row in rows))
    usage = getrusage(RUSAGE_SELF)
    result = dict(cases=cases, historical_fix_labels_sha256=HISTORICAL_SHA, enrollment_sha256=ENROLLMENT_SHA,
                  started_unix_ns=started, ended_unix_ns=time_ns(), waveform_reads=0, manifest_body_reads=0,
                  source_input_blocks=usage.ru_inblock-before.ru_inblock, major_faults=usage.ru_majflt-before.ru_majflt,
                  full_member_censuses=0, launches=0, scanner_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    with output.open("x") as stream:
        json.dump(result,stream,indent=2,sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    run(parser.parse_args().output)
