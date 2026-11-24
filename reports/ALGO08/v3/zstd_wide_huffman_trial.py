"""Measure native multi-symbol versus upstream X2 decoding on signed literal streams."""

import argparse
import ctypes as ct
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter_ns, process_time_ns

from .dense_zstd_backend_trial import SYSTEM_STATIC, SYSTEM_STATIC_SHA
from .zstd_wide_huffman import CASES, HERE, WIDTHS, admit, huffman_blocks, release


ORDERS = ((0, *WIDTHS), (*WIDTHS[::-1], 0)) * 2
FLAGS = ("-std=c11", "-O3", "-march=native", "-fPIC", "-shared", "-Wall", "-Wextra", "-Werror",
         "-Wl,--exclude-libs,ALL")


class Block(ct.Structure):
    _fields_ = [(name, ct.c_uint32) for name in ("offset", "encoded", "decoded", "new")]


class Clock(ct.Structure):
    _fields_ = [("table_ns", ct.c_uint64), ("decode_ns", ct.c_uint64),
                ("max_code_log", ct.c_uint32), ("builds", ct.c_uint32)]


def build(out):
    library = out / "wide-huffman.so"
    source = HERE / "zstd_wide_huffman.c"
    release.verified(SYSTEM_STATIC, SYSTEM_STATIC_SHA)
    subprocess.run(["cc", *FLAGS, str(source), str(SYSTEM_STATIC), "-o", str(library)], check=True)
    return library


def load(library):
    fn = ct.CDLL(str(library)).huffman_trial
    fn.argtypes = (ct.c_char_p, ct.c_size_t, ct.POINTER(Block), ct.c_size_t, ct.c_uint,
                   ct.c_void_p, ct.c_size_t, ct.POINTER(Clock))
    fn.restype = ct.c_int
    return fn


def decode(fn, frame, blocks, width, output, *, expected_error=False):
    output_owner = (ct.c_uint8 * len(output)).from_buffer(output)
    stats = Clock()
    wall, cpu = perf_counter_ns(), process_time_ns()
    rc = fn(frame, len(frame), blocks, len(blocks), width, ct.addressof(output_owner), len(output), ct.byref(stats))
    result = dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall,
                  table_ns=stats.table_ns, decode_ns=stats.decode_ns, max_code_log=stats.max_code_log, builds=stats.builds)
    result["rejected"] = bool(rc)
    if expected_error is not None and bool(rc) != expected_error:
        raise ValueError(f"Unexpected native literal status {rc} at width {width}")
    return result


def corruption(fn, frame, first, header_bytes):
    original = frame[first["offset"]:first["offset"] + first["encoded"]]
    changed_jump = original[:header_bytes] + b"\x00\x00" + original[header_bytes + 2:]
    corrupt = {"empty_first_stream": changed_jump, "zero_last_stop_byte": original[:-1] + b"\x00",
               "truncated_jump_table": original[:header_bytes + 4], "truncated_member_literal_section": original[:-7]}
    output = bytearray(first["decoded"])
    outcomes = {}
    for name, payload in corrupt.items():
        table = (Block * 1)(Block(0, len(payload), first["decoded"], 1))
        outcomes[name] = {}
        for width in (0, *WIDTHS):
            rejected = decode(fn, payload, table, width, output, expected_error=None)["rejected"]
            if width and not rejected:
                raise ValueError(f"Wide literal kernel accepted {name}")
            outcomes[name][width] = dict(rejected=rejected, decoded_sha256=None if rejected else sha256(output).hexdigest())
    return outcomes


def run(root, case):
    if root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}:
        raise ValueError("Expected a fresh tmpfs output on the shared CPU2 slot")
    _, _, reader, member, view, windows, admitted = admit(case)
    frame = view.files[reader.path / member.payload_relative_path]
    structure, groups, rows, eligibility = huffman_blocks(frame, member.uncompressed_bytes)
    if len(rows) != structure["block_counts"]["compressed"] or any(row["streams"] != 4 for row in rows):
        raise ValueError("Expected complete four-stream literal scope")
    root.mkdir()
    library = build(root)
    fn = load(library)
    blocks = (Block * len(rows))(*(Block(row["offset"], row["encoded"], row["decoded"], row["new"]) for row in rows))
    output = bytearray(sum(row["decoded"] for row in rows))
    decode(fn, frame, blocks, 0, output)
    expected = sha256(output).hexdigest()
    if not structure["sequences"] and "sha256:" + expected != member.uncompressed_sha256:
        raise ValueError("Literal-only scope does not agree with original complete decoded SHA")
    parity = []
    for order in ORDERS:
        results = {}
        for width in order:
            measurement = decode(fn, frame, blocks, width, output)
            if sha256(output).hexdigest() != expected or measurement["builds"] != len(groups):
                raise ValueError("A native width changed literal bytes, output extent, or table schedule")
            results[width] = measurement
        parity.append(dict(order=order, results=results))
    medians = {width: {key: median(row["results"][width][key] for row in parity)
                       for key in ("cpu_ns", "wall_ns", "table_ns", "decode_ns")} for width in (0, *WIDTHS)}
    payload = dict(case=case, input=member.model_dump(mode="json"), source=str(reader.path), admission=admitted,
                   original_window_hashes=windows, structure=structure, eligible=eligibility,
                   setup=dict(library_sha256=sha256(library.read_bytes()).hexdigest(), flags=FLAGS,
                              static_archive_sha256=SYSTEM_STATIC_SHA, widths=[0, *WIDTHS]),
                   paired=parity, medians=medians, literal_sha256=expected,
                   corruption=corruption(fn, frame, rows[0], groups[0]["bytes"]),
                   sources={name: sha256((HERE / name).read_bytes()).hexdigest() for name in
                            ("zstd_wide_huffman.c", "zstd_wide_huffman.py", "zstd_wide_huffman_trial.py")})
    with (root / "kernels.json").open("x") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--case", choices=tuple(CASES), default="DS30-0016")
    args = parser.parse_args()
    run(args.root, args.case)
