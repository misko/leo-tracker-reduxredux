"""Stage just the signed DS30-0419 first member, one idle read at a time."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
from shutil import disk_usage
import subprocess
from time import perf_counter, process_time

from first_member_0419 import CACHE, CACHE_PIN, INVENTORY_PIN, REQUEST_PIN, SAVED, metadata, payload_cache, select_first
from guarded_cfo_0016_stage import BLOCK, LOCK, RATE, Pacing, copy_member
from guarded_stage_idle import IdleAdmission, IdleWindowExpired
from leo.storage.short_window import ShortWindowReader
from tools.pipeline_eval.qualification.cache_residency import load_query


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE / "measurements/first-member-0419.json"
PREVIOUS_PIN = "bbeda34d3481ee75d9b52de477fa79bbb6817ab6a565578c65dfd83127de42a4"
IDLE_PIN = "a4d2575cb5ec65014f6415ca61adf8423dd1c1ded84d56af06f38cb13b1b5c56"
SIZE, DEVICE, SECONDS = 79_163_761, 64517, 120


def verified_local(folder, manifest_pin, member):
    reader = ShortWindowReader(folder)
    if reader.manifest_sha256 != manifest_pin:
        raise ValueError("The staged manifest changed")
    digest = sha256()
    count = total = 0
    for visit in reader.windows(stop_sequence=member["window_count"]):
        if visit.index.sequence != count:
            raise ValueError("Decoded visit sequence changed")
        values = memoryview(visit.samples).cast("B")
        total += len(values)
        digest.update(values)
        count += 1
    if (count, total, "sha256:" + digest.hexdigest()) != (
            member["window_count"], member["uncompressed_bytes"], member["uncompressed_sha256"]):
        raise ValueError("Standard reader did not verify the entire first member")
    return dict(visits=count, bytes=total, raw_sha256="sha256:" + digest.hexdigest())


def bindings():
    metadata(HERE / "guarded_stage_idle.py", IDLE_PIN, 20_000)
    original_case = json.loads(metadata(PREVIOUS, PREVIOUS_PIN, 80_000))
    request = json.loads(metadata(SAVED / "request.json", REQUEST_PIN, 96_000))
    inventory = json.loads(metadata(SAVED / "inventory.json", INVENTORY_PIN, 96_000))
    original, first = select_first(request, inventory)
    member = original_case["member"]
    if (original_case["first_segment"] != first or member["compressed_bytes"] != SIZE
            or member["window_count"] != 64 or original_case["cache"]["device"] != DEVICE
            or member["first_sequence"] != 0 or (BLOCK, RATE) != (1_048_576, 2_097_152)
            or original.resolve(strict=True) != original):
        raise ValueError("The original first-member enrollment changed")
    payload = original / member["payload_relative_path"]
    if payload.resolve(strict=True) != payload:
        raise ValueError("The selected payload traverses a symlink")
    return request, first, member, payload, original_case["cache"]["inode"]


def stage_metadata(source, dest, manifest_pin, member, admission, lock):
    with admission.slot(lock):
        manifest = metadata(source / "manifest.json", manifest_pin, 256_000)
    if json.loads(manifest)["chunks"][0] != member:
        raise ValueError("First member differs from the signed manifest")
    (dest / "manifest.json").write_bytes(manifest)
    index = member["index_relative_path"]
    with admission.slot(lock):
        body = metadata(source / index, member["index_sha256"], member["index_bytes"])
    if len(body) != member["index_bytes"]:
        raise ValueError("The signed index length changed")
    (dest / index).write_bytes(body)
    return len(manifest) + len(body)


def stage(root):
    started, cpu = perf_counter(), process_time()
    io_before = resource.getrusage(resource.RUSAGE_SELF).ru_inblock
    if (root.parent != Path("/tmp") or root.exists() or root.is_symlink()
            or disk_usage(root.parent).free < 240_000_000
            or os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "idle"):
        raise ValueError("Expected a fresh private /tmp stage on the idle-only CPU 2 route")
    request, first, member, payload, inode = bindings()
    metadata(CACHE, CACHE_PIN, 80_000)
    query = load_query(CACHE)
    page = os.sysconf("SC_PAGE_SIZE")
    before = payload_cache(payload, SIZE, query, page)
    if before["device"] != DEVICE or before["inode"] != inode:
        raise ValueError("The original signed physical payload identity changed")
    root.mkdir(mode=0o700)
    folder = root / payload.parent.name
    folder.mkdir()
    stats = Path(f"/sys/dev/block/{os.major(DEVICE)}:{os.minor(DEVICE)}/stat")
    deadline = started + SECONDS
    pacing = Pacing(root, SIZE, 0, idle=True, device=stats, deadline=deadline)
    admission = IdleAdmission(stats, deadline, pacing.record)
    verified, meta_bytes, stopped, copy_done = None, 0, None, None
    try:
        with LOCK.open("rb") as lock:
            meta_bytes = stage_metadata(payload.parent, folder, first["manifest_digest"], member, admission, lock)
            copy_member(payload, folder / payload.name, SIZE, member["compressed_sha256"], lock, pacing,
                        journal=root / "checkpoint.json", admission=admission, required_device=DEVICE)
        copy_done = perf_counter() - started
        verified = verified_local(folder, first["manifest_digest"], member)
    except IdleWindowExpired as error:
        stopped = str(error)
    finally:
        cached = payload_cache(payload, SIZE, query, page)
        io_after = resource.getrusage(resource.RUSAGE_SELF).ru_inblock
        events = [json.loads(row) for row in pacing.log.read_text().splitlines()]
        result = dict(schema="leo.research.ds30-0419-first-member-idle.v1", case="DS30-0419",
                      previous_sha256=PREVIOUS_PIN, allowlisted_idle_source_sha256=IDLE_PIN,
                      complete=verified is not None, stop_reason=stopped, source=str(payload), stage=str(folder),
                      request_sha256=REQUEST_PIN, inventory_sha256=INVENTORY_PIN,
                      original_session=request["session"], raw_authority=request["raw_authority"],
                      manifest_sha256=first["manifest_digest"], member=member, verified=verified,
                      slot=dict(cpu=2, nice=os.getpriority(os.PRIO_PROCESS, 0), ionice="idle",
                                max_elapsed_s=SECONDS, block_bytes=BLOCK, rate_bytes_s=RATE,
                                source_advice="POSIX_FADV_RANDOM"),
                      elapsed_s=perf_counter()-started, cpu_s=process_time()-cpu,
                      elapsed_through_copy_s=copy_done, payload_bytes=pacing.copied, metadata_bytes=meta_bytes,
                      input_blocks=io_after-io_before, admitted_io_calls=admission.reads,
                      wait_s=admission.wait_s, abort_pauses=pacing.pauses, slowest_read_s=pacing.slowest,
                      before=before, after=cached, events=events)
        (root / "stage.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    stage(cli.parse_args().root)
