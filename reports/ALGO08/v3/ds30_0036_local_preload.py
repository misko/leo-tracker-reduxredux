"""Copy only the two approved cold official saved JSON inputs to private RAM."""

import argparse
from hashlib import sha256
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ds30_next_moment_publication as replay_entry  # noqa: E402
from ds30_next_moment_publication import elapsed, held, replay, saved, started  # noqa: E402


AMENDMENT = "c6d9bb408dc27ce2aa77b568d38e71d1bc9caf122c1ea5d4725da8ce9d3fefb4"
PAIR = "576795db6a0c7152eee4d523eeb9aa9f1ec5ac38c3873c1eaab3533a7670ed3d"
ENROLLMENT = "942e9affd9d80c57e651cb8824fb62b241d1f1ec1e260100e89f125c0e487be4"
SIZES = {"detections.json": 3_884_274, "inventory.json": 4_118}


def io_stats():
    rows = dict(line.split(": ") for line in Path("/proc/self/io").read_text().splitlines())
    return {"storage_bytes": int(rows["read_bytes"]), "input_blocks": getrusage(RUSAGE_SELF).ru_inblock}


def snapshot(source, output, expected_size, expected_digest):
    path = source.resolve(strict=True)
    if source != path or path.stat().st_dev != held.CAMPAIGN.stat().st_dev:
        raise ValueError("Require a direct file on the independent local official-output filesystem")
    with source.open("rb") as handle:
        info = os.fstat(handle.fileno())
        if info.st_size != expected_size:
            raise ValueError("The saved file extent differs from the approved local preload")
        body = handle.read()
        after = os.fstat(handle.fileno())
        if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("The official saved input changed during local preload")
    digest = sha256(body).hexdigest()
    if len(body) != expected_size or digest != expected_digest.removeprefix("sha256:"):
        raise ValueError("The local saved input differs from its official digest")
    with output.open("xb") as handle:
        handle.write(body)
    output.chmod(0o400)
    return dict(source=str(source), bytes=len(body), sha256=digest, logical_reads=1)


def prepare(root, enrollment):
    if saved.identifier(HERE/"ds30-0036-local-preload-amendment.md") != AMENDMENT:
        raise ValueError("The approved local preload amendment changed")
    if (root.parent != Path("/tmp") or root.resolve() != root or root.exists()
            or os.sched_getaffinity(0) != {3} or os.getpriority(os.PRIO_PROCESS, 0) != 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "idle"):
        raise ValueError("Use a fresh private /tmp root on CPU3, nice 15 and idle I/O")
    replay_entry.registration()
    row = replay_entry.enrolled(enrollment, ENROLLMENT)
    state = replay.status(row)
    if not state["verified_pair"] or state["pair_sha256"] != "sha256:"+PAIR:
        raise ValueError("Require the same two verified rank-71 official roles")
    authority = replay.field_authority(row, state)
    case = held.CAMPAIGN/"cases"/row["case"]
    pair = saved.document(case/"pair.json", PAIR)
    attempt = case/"successor"/f"attempt-{pair['generation']:06d}"
    result = saved.document(attempt/"result.json", pair["attempt_result_sha256"]["successor"])
    if result["raw_identity"] != authority:
        raise ValueError("The scanner result does not bind the original recording and cutoff")
    public = attempt/"publication"
    native, = public.glob("fast-scan-automatic-work/*/detections.json")
    inventory = public/"fast-scan-inputs"/(authority["session_id"]+".json")
    copies = {
        "detections.json": (native, result["native_sha256"]),
        "inventory.json": (inventory, authority["inventory_sha256"]),
    }
    root.mkdir(mode=0o700)
    accounting, inputs = started(), io_stats()
    files = {name: snapshot(source,root/name,SIZES[name],pin) for name,(source,pin) in copies.items()}
    end = io_stats()
    measured = dict(elapsed(accounting), **{key:end[key]-inputs[key] for key in end})
    return saved.write(root/"preload.json", dict(case=row["case"], amendment_sha256=AMENDMENT,
        enrollment_sha256=ENROLLMENT, pair_sha256=PAIR, source_attempt_sha256=pair["attempt_result_sha256"]["successor"],
        clock=measured, files=files, payload_bytes=sum(SIZES.values()), original_waveform_reads=0, backing_archive_reads=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("enrollment", type=Path)
    args = parser.parse_args()
    sys.addaudithook(saved.deny_backing)
    print(prepare(args.root, args.enrollment))


if __name__ == "__main__":
    main()
