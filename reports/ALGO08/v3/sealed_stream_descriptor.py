"""Retest descriptor time and compressed SHA alone on the enrolled files."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import stat
from time import perf_counter_ns, process_time_ns

from . import cross_lag_eight_ms as stage, sparse_cold_input as release
from .eight_ms_primary import write
from .scout_readout_trial import check_machine


BLOCK = 256 * 1024
ORDERS = (("whole", "bounded"), ("bounded", "whole"))


def bounded_digest(fd, size, buffer):
    digest = sha256()
    remaining = size
    while remaining:
        target = buffer[:min(remaining, len(buffer))]
        sent = 0
        while sent < len(target):
            count = os.readv(fd, [target[sent:]])
            if not count:
                raise ValueError("The signed compressed member ended early")
            sent += count
        digest.update(target)
        remaining -= sent
    if os.read(fd, 1):
        raise ValueError("The signed compressed member exceeds its extent")
    return digest.hexdigest()


def inode(fd):
    entry = os.fstat(fd)
    if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
        raise ValueError("The bound input must be a single ordinary regular file")
    auxiliary = Path(f"/proc/self/fdinfo/{fd}").read_text()
    mount_id = next(line.split()[1] for line in auxiliary.splitlines() if line.startswith("mnt_id:"))
    line, = (row for row in Path("/proc/self/mountinfo").read_text().splitlines() if row.split()[0] == mount_id)
    mount, filesystem = line.split(" - ", 1)
    return dict(st_dev=entry.st_dev, st_ino=entry.st_ino, mode=oct(entry.st_mode), links=entry.st_nlink,
                size=entry.st_size, mtime_ns=entry.st_mtime_ns, fd_flags=os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                name=os.readlink(f"/proc/self/fd/{fd}"), mount_id=mount_id, mount_point=mount.split()[4],
                filesystem=filesystem.split()[0], fs_source=filesystem.split()[1])


def measure(path, size, pin, read, mode):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    clocks = {}
    try:
        identity = inode(fd)
        if identity["size"] != size or identity["name"] != str(path) or identity["filesystem"] != "tmpfs":
            raise ValueError("The descriptor differs from its enrolled original tmpfs alias")
        before = resource.getrusage(resource.RUSAGE_SELF)
        started = process_time_ns(), perf_counter_ns()
        if mode == "whole":
            contents = read(fd, size)
            clocks["whole_read_cpu_ns"] = process_time_ns() - started[0]
            if len(contents) != size:
                raise ValueError("The released complete descriptor returned a changed extent")
            digest = sha256(contents).hexdigest()
        else:
            digest = bounded_digest(fd, size, memoryview(bytearray(BLOCK)))
        clocks |= dict(cpu_ns=process_time_ns()-started[0], wall_ns=perf_counter_ns()-started[1])
        after = resource.getrusage(resource.RUSAGE_SELF)
        if digest != pin.removeprefix("sha256:") or inode(fd) != identity:
            raise ValueError("The authorized compressed bytes or descriptor changed")
    finally:
        os.close(fd)
    return dict(**clocks, descriptor=identity, compressed_sha256=pin,
                faults=after.ru_minflt-before.ru_minflt, major=after.ru_majflt-before.ru_majflt,
                input_blocks=after.ru_inblock-before.ru_inblock)


def run(path, case):
    machine = check_machine()
    scope, _, member = stage.assignment(case)
    payload = scope / member["payload_relative_path"]
    if payload.resolve(strict=True) != payload or not payload.is_relative_to("/dev/shm"):
        raise ValueError("Only the original staged compressed artifact is eligible")
    spec = json.loads(release.verified(release.PAYLOAD / "spec.json", release.SPEC_SHA))
    view = release.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    read = view.__wrapped__.__globals__["read_regular_descriptor"]
    before = stage.residency(case)
    runs = [{mode: measure(payload, member["compressed_bytes"], member["compressed_sha256"], read, mode) for mode in order}
            for order in ORDERS]
    after = stage.residency(case)
    write(path, dict(case=case, machine=machine, runs=runs, orders=ORDERS, resident_before=before,
                     resident_after=after, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("case", choices=("0008", "0169"))
    args = parser.parse_args()
    run(args.path, args.case)
