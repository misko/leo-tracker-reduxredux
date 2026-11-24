"""Price exact common-prefix SHA-256 reuse on authentic resident CI16 windows."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import process_time_ns

from .ci16_grouped_trial import make, inputs, SOURCES
from .ci16_packing import Packing, SOURCE
from .direct_packed_capture import Capture, PREFIX, write_capture
from .north_direct_multichunk import checked_lease
from .seekable_eight_raw import clocks, elapsed
from .seekable_member import SAMPLE_BYTES, digest


ORDERS = {"North": (False, True, True, False), "DS30-0008": (True, False, False, True)}


def profile(owned, chunk, reuse):
    paid = Counter()
    aggregate = sha256()
    block_fingerprint = sha256()

    def part(name, call, *args):
        started = process_time_ns()
        result = call(*args)
        paid[name] += process_time_ns()-started
        return result

    started = process_time_ns()
    for item in owned:
        raw = memoryview(item.samples).cast("B")
        prefix, tail = raw[:PREFIX*SAMPLE_BYTES], raw[PREFIX*SAMPLE_BYTES:]
        if reuse:
            prefix_state = part("prefix_update", sha256, prefix)
            prefix_pin = part("prefix_finish", prefix_state.digest)
        else:
            prefix_pin = part("prefix_update_and_finish", digest, prefix)
        tail_pin = part("tail", digest, tail)
        joined = part("join", b"".join, (prefix, tail))
        if reuse:
            part("continue_window", prefix_state.update, tail)
            window_pin = "sha256:" + part("window_finish", prefix_state.hexdigest)
            prefix_pin = "sha256:" + prefix_pin.hex()
        else:
            window_pin = part("repeat_window", digest, joined)
        part("member", aggregate.update, joined)
        if window_pin != item.index.iq_sha256:
            raise ValueError("Window hashing did not preserve the signed input")
        block_fingerprint.update(bytes.fromhex(prefix_pin[7:]))
        block_fingerprint.update(bytes.fromhex(tail_pin[7:]))
    elapsed = process_time_ns()-started
    if "sha256:"+aggregate.hexdigest() != chunk.uncompressed_sha256:
        raise ValueError("Original ordered full-member digest changed")
    return dict(reuse=reuse, profile_cpu_ns=dict(paid), complete_cpu_ns=elapsed,
                block_digests_sha256=block_fingerprint.hexdigest())


def census():
    result = {}
    for name in SOURCES:
        _, chunk, owned, source = inputs(name)
        rows = [profile(owned, chunk, mode) for mode in ORDERS[name]]
        if len({row["block_digests_sha256"] for row in rows}) != 1:
            raise ValueError("Prefix reuse changed the original part pins")
        result[name] = dict(source=source, rounds=rows, prefix_extent_bytes=len(owned)*PREFIX*SAMPLE_BYTES)
    return result


def first_use(path, header, chunk, owned, codec, reuse):
    began = clocks()
    pin, document = write_capture(path, header, owned, (len(owned),), codec, reuse_prefix_sha=reuse)
    writer = elapsed(began)
    read = clocks()
    source = Capture(path, pin, codec, reuse_prefix_sha=reuse)
    _, _, inventory = source.inventory(path)
    hashes = [window.iq_sha256 for window in source.segment(inventory["segments"][0]).windows()]
    complete = elapsed(began)
    reader = elapsed(read)
    status, = source.audit
    stored, = document["chunks"]
    if (hashes != [window.index.iq_sha256 for window in owned] or status["checks"]["full_checks"] != 64
            or status["original_decoded_sha256"] != chunk.uncompressed_sha256 or status["encoded_blocks"] != 128
            or stored["index_sha256"] != chunk.index_sha256):
        raise ValueError("The signed full first readback changed")
    return dict(reuse=reuse, writer=writer, reader=reader, total=complete, capture_sha256=pin, checks=status)


def compare(root):
    binary = root/"packing.so"
    build = make(SOURCE, binary)
    codec = Packing(binary)
    cases = {}
    for name, order in ORDERS.items():
        header, chunk, owned, source = inputs(name)
        with TemporaryDirectory(dir=root, prefix=name+"-") as temporary:
            rows = [first_use(Path(temporary)/str(i), header, chunk, owned, codec, reuse)
                    for i, reuse in enumerate(dict.fromkeys(order))]
        if len({row["capture_sha256"] for row in rows}) != 1:
            raise ValueError("Prefix reuse changed the exact captured representation")
        cases[name] = dict(source=source, order=rows)
    return dict(cases=cases, build=build)


def require_slot(root):
    checked_lease()
    io = subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True)
    if (root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) < 15 or "prio 7" not in io):
        raise ValueError("Use the shared low-priority Gauss core and a new tmpfs path")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--compare", action="store_true")
    options = parser.parse_args()
    require_slot(options.root)
    options.root.mkdir()
    result = compare(options.root) if options.compare else census()
    with (options.root/("compare.json" if options.compare else "census.json")).open("x") as stream:
        json.dump(result, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
