"""Continue a sealed physical first member during one new quiet opportunity."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import shutil
import stat
import subprocess
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from first_member_0163_idle import CASE, DEVICE, INVENTORY_PIN, REQUEST_PIN, SIZE, bindings
from first_member_0419_idle import verified_local
from guarded_cfo_0016_stage import BLOCK, LOCK, RATE, Pacing, copy_member
from guarded_stage_checkpoint import Extent, checked_local, identity, staging_lock, verified_extents, write_checkpoint
from guarded_stage_idle import IdleAdmission, IdleWindowExpired


OLD = Path("/tmp/leo-v3-0163-first-idle-stage01")
OLD_RECEIPT = Path("/tmp/leo-v3-0163-first-idle-result01.json")
OLD_RECEIPT_PIN = "e6dfabaf402fd84179fe69d5f971a906258dd3446456cacc018a6cccff57a6a9"
OLD_JOURNAL_PIN = "ff9839d5b4ddf5ea088dbe31c035be510a6c2b19ba41ecd31241b0a725c793bd"
PREFIX_BYTES = 35_651_584
PREFIX_SHA = "sha256:49429adbd0ca6ac5fbf47f1f14fef10a97a3a9487bf2fb893a9b6549f57a55c0"
ADDITIONAL_BYTES = 43_068_882
SECONDS = 120
TARGET = Path("/tmp/leo-v3-0163-first-idle-resume01")


def immutable_small(path, pin):
    if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_size > 100_000:
        raise ValueError("Expected a direct small sealed checkpoint file")
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"Frozen checkpoint changed at {path}")
    return json.loads(body)


def extent_and_checkpoint(source, member, inode, saved, journal):
    extent = Extent(Path(source.parent.name) / source.name, SIZE, member["compressed_sha256"])
    meta = source.lstat()
    if (not stat.S_ISREG(meta.st_mode) or meta.st_dev != DEVICE or meta.st_ino != inode
            or meta.st_size != SIZE or tuple(journal["source_identity"]) != identity(meta)):
        raise ValueError("Original source inode, extent or version differs from sealed checkpoint")
    if (saved["verified_partial_bytes"] != PREFIX_BYTES or saved["verified_partial_sha256"] != PREFIX_SHA
            or saved["checkpoint_sha256"] != OLD_JOURNAL_PIN or saved["permit_analysis"] is not False
            or str(extent.relative) != journal["relative"] or journal["size"] != SIZE
            or journal["sha256"] != extent.sha256 or dict(journal["prefixes"]).get(PREFIX_BYTES) != PREFIX_SHA
            or SIZE - PREFIX_BYTES != ADDITIONAL_BYTES or (BLOCK, RATE) != (1_048_576, 2_097_152)):
        raise ValueError("Prior committed prefix, full signed extent or remaining read budget differs")
    return extent


def prepare(root):
    request, first, member, source, inode = bindings()
    saved = immutable_small(OLD_RECEIPT, OLD_RECEIPT_PIN)
    journal = immutable_small(OLD / "checkpoint.json", OLD_JOURNAL_PIN)
    extent = extent_and_checkpoint(source, member, inode, saved, journal)
    old_payload = OLD / extent.relative
    old_manifest = old_payload.parent / "manifest.json"
    old_index = old_payload.parent / member["index_relative_path"]
    local = [(old_payload, PREFIX_BYTES, PREFIX_SHA),
             (old_manifest, old_manifest.stat().st_size, first["manifest_digest"]),
             (old_index, member["index_bytes"], member["index_sha256"])]
    for path, size, pin in local:
        if path.resolve(strict=True) != path or path.lstat().st_dev != root.parent.stat().st_dev:
            raise ValueError("The previous checkpoint must remain directly on the new stage's local filesystem")
        checked_local(path, size, pin)
    if json.loads(old_manifest.read_bytes())["chunks"][0] != member:
        raise ValueError("Signed local original manifest no longer binds the enrolled first member")
    if shutil.disk_usage(root.parent).free < SIZE + 128_000_000:
        raise ValueError("Insufficient local headroom to preserve both checkpoints")
    root.mkdir(mode=0o700)
    target = root / extent.relative
    target.parent.mkdir(mode=0o700)
    for path, size, pin in local:
        dest = target.parent / path.name
        shutil.copyfile(path, dest)
        checked_local(dest, size, pin)
    write_checkpoint(root / "checkpoint.json", journal)
    _, partial = verified_extents(root, [extent], journal)
    if partial is None or partial.offset != PREFIX_BYTES:
        raise ValueError("Copied local checkpoint did not retain its exact signed prefix")
    return first, member, source, extent, partial, old_payload


def run(root):
    if (root != TARGET or root.parent.resolve(strict=True) != root.parent or root.exists() or root.is_symlink()
            or os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "idle"):
        raise ValueError("Use the single new low-priority checkpoint path and idle CPU2 worker")
    prepared = perf_counter()
    with staging_lock(root.with_suffix(".lock")):
        first, member, source, extent, partial, old_payload = prepare(root)
        preparation = perf_counter() - prepared
        started, cpu = perf_counter(), process_time()
        input_before = resource.getrusage(resource.RUSAGE_SELF).ru_inblock
        device = Path(f"/sys/dev/block/{os.major(DEVICE)}:{os.minor(DEVICE)}/stat")
        deadline = started + SECONDS
        pacing = Pacing(root, SIZE, PREFIX_BYTES, idle=True, device=device, deadline=deadline)
        admission = IdleAdmission(device, deadline, pacing.record)
        target = root / extent.relative
        reason = None
        try:
            with LOCK.open("rb") as lock:
                copy_member(source, target, SIZE, extent.sha256, lock, pacing, partial=partial,
                            journal=root / "checkpoint.json", admission=admission, required_device=DEVICE)
        except IdleWindowExpired as error:
            reason = str(error)
        opportunity_elapsed = perf_counter() - started
        opportunity_cpu = process_time() - cpu
        input_blocks = resource.getrusage(resource.RUSAGE_SELF).ru_inblock - input_before
        complete, stopped = verified_extents(root, [extent], json.loads((root / "checkpoint.json").read_bytes()))
        if bool(complete) == bool(stopped):
            raise ValueError("Expected exactly one complete or independently verified partial local extent")
        verified = SIZE if complete else stopped.offset
        if verified != pacing.copied or not PREFIX_BYTES <= verified <= SIZE or (reason is None) != bool(complete):
            raise ValueError("Quiet slot bytes and checkpoint terminal disagree")
        decoded = verified_local(target.parent, first["manifest_digest"], member) if complete else None
        checked_local(old_payload, PREFIX_BYTES, PREFIX_SHA)
        immutable_small(OLD / "checkpoint.json", OLD_JOURNAL_PIN)
        for path in (target, target.parent / "manifest.json", target.parent / member["index_relative_path"]):
            path.chmod(0o440)
        result = dict(case=CASE, scope="one original first member only", previous_receipt_sha256=OLD_RECEIPT_PIN,
                      previous_journal_sha256=OLD_JOURNAL_PIN, previous_checkpoint_preserved=True,
                      source=str(source), member=member, manifest_sha256=first["manifest_digest"],
                      device_identity=partial.source_identity, original_request_sha256=REQUEST_PIN,
                      original_inventory_sha256=INVENTORY_PIN,
                      reused_local_prefix_bytes=PREFIX_BYTES, local_setup_s=preparation,
                      original_prefix_bytes_reread=0, original_new_bytes=verified - PREFIX_BYTES,
                      original_new_byte_limit=ADDITIONAL_BYTES, result_verified_bytes=verified,
                      prefix_or_complete_sha256=extent.sha256 if complete else "sha256:" + stopped.checksum.hexdigest(),
                      verified_complete=bool(complete), decoded=decoded, quiet_window_s=SECONDS,
                      opportunity_elapsed_s=opportunity_elapsed, opportunity_cpu_s=opportunity_cpu,
                      input_blocks=input_blocks, accepted_reads=admission.reads, wait_for_quiet_s=admission.wait_s,
                      max_read_request_bytes=BLOCK, rate_limit_bytes_per_s=RATE,
                      slowest_admitted_read_s=pacing.slowest, stop_reason=reason, media_receiver_jobs=0)
        with (root / "resumed-stage.json").open("x") as stream:
            json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    print(json.dumps(run(cli.parse_args().output), sort_keys=True))
