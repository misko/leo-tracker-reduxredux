"""Compare the Huffman assembly selector in one installed libzstd build."""

import argparse
from collections import Counter
import ctypes as ct
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from . import physical_stage_envelope as ladder, sparse_cold_input as cold, warm_six_prefetch as warm
from .dense_zstd_backend import Backend, StreamBridge, _bytes_data
from .dense_zstd_backend_trial import SYSTEM_STATIC, SYSTEM_STATIC_SHA
from .native_verified_drain import ZSTD, ZSTD_SHA
from .zstd_structure import inspect
from .zstd_structure_trial import HeldReads, PUBLIC, PUBLIC_SHA, READER_SHA, Samples


HERE = Path(__file__).resolve().parent
HEADER = Path("/usr/include/zstd.h")
HEADER_SHA = "9b4bc8245565c98ccfc61c07749928b57e7c0f6fddb0530c4f6aa1971893d88b"
REFERENCE_SHA = "4e90828fb7f194693f405eaddd0bed1789b7e36291d3babd5d0edd1087687548"
ORDERS = ("asm", "c", "c", "asm")
PARAM = 1004
WINDOWS, WINDOW_BYTES = 64, 1600000
MICRO_ITERATIONS = 4


def backend(mode):
    result = Backend.system(ZSTD)
    if result.version != 10507:
        raise ValueError("Expected the verified libzstd version")
    control, query = result.library.ZSTD_DCtx_setParameter, result.library.ZSTD_DCtx_getParameter
    control.argtypes = (ct.c_void_p, ct.c_int, ct.c_int)
    query.argtypes = (ct.c_void_p, ct.c_int, ct.POINTER(ct.c_int))
    control.restype = query.restype = ct.c_size_t
    disabled = int(mode == "c")
    original = result.init

    def configure(dctx):
        value = ct.c_int()
        if (result.is_error(control(dctx, PARAM, disabled)) or result.is_error(query(dctx, PARAM, ct.byref(value)))
                or value.value != disabled):
            raise ValueError("Native decoder did not accept the matching Huffman assembly setting")

    def init(context):
        status = original(context)
        if not result.is_error(status):
            configure(context)
        return status

    result.configure = configure
    result.init = init
    return result


def worker(mode, request, binary, output):
    from leo.storage import short_window

    cold.verified(ZSTD, ZSTD_SHA)
    cold.verified(HEADER, HEADER_SHA)
    cold.verified(Path(short_window.__file__), READER_SHA)
    reader = short_window.zstd
    system, stats = backend(mode), Counter()
    bridge = SimpleNamespace(ZstdDecompressor=lambda: StreamBridge(system, reader, stats), ZstdError=reader.ZstdError)
    with (patch.object(short_window, "zstd", bridge), patch.object(warm, "WINDOWS", WINDOWS)):
        warm.worker("serial", request, binary, output)
    if (stats["standard_frames"] != 1 or not WINDOWS <= stats["steps"] <= WINDOWS+2
            or stats["layout_fallbacks"] or stats["error_fallbacks"]):
        raise ValueError("The compared system decoder fell back or changed its signed reads")
    warm.full.freeze(output.with_suffix(".zstd.json"), dict(stats, mode=mode, parameter=PARAM, disabled=int(mode == "c")))


def assert_header(root):
    source = root / "parameter.c"
    source.write_text("#define ZSTD_STATIC_LINKING_ONLY\n#include <zstd.h>\n"
                      "_Static_assert(ZSTD_VERSION_NUMBER == 10507, \"wrong decoder header\");\n"
                      "_Static_assert(ZSTD_d_disableHuffmanAssembly == 1004, \"wrong option\");\n")
    env = dict(os.environ, TMPDIR=str(root))
    subprocess.run(["cc", "-fsyntax-only", str(source)], check=True, env=env)
    pc_library = root / "pc.so"
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-O2", "-shared", "-fPIC", str(HERE / "zstd_decoder_pc.c"),
                    "-o", str(pc_library)], check=True, env=env)
    return pc_library


def fast_loops(root):
    """Locate exact static routine bytes in the pinned stripped shared build."""
    data = cold.verified(ZSTD, ZSTD_SHA)
    load_lines = subprocess.check_output(["readelf", "-Wl", str(ZSTD)], text=True)
    loads = [line.split() for line in load_lines.splitlines() if line.lstrip().startswith("LOAD")]
    offset, virtual, length = next((int(p[1], 16), int(p[2], 16), int(p[4], 16)) for p in loads if "E" in p[6:])
    result = {}
    for kind, filename in (("asm", "huf_decompress_amd64.o"), ("c", "huf_decompress.o")):
        obj, raw = root / filename, root / (filename+".bin")
        obj.write_bytes(subprocess.check_output(["ar", "p", str(SYSTEM_STATIC), filename]))
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text", str(obj), str(raw)], check=True)
        text = raw.read_bytes()
        symbols = subprocess.check_output(["nm", "-n", "-S", "--defined-only", str(obj)], text=True)
        for lane in (1, 2):
            name = f"HUF_decompress4X{lane}_usingDTable_internal_fast_{kind}_loop"
            row, = [line.split() for line in symbols.splitlines() if line.split()[-1] == name]
            begin = int(row[0], 16)
            end = begin + int(row[1], 16) if len(row) == 4 else (
                int(next(line.split()[0] for line in symbols.splitlines() if "4X2_usingDTable" in line), 16)
                if lane == 1 else len(text))
            start = begin+4 if text[begin:begin+4] == b"\xf3\x0f\x1e\xfa" else begin
            needle = text[start:start+128]
            found = data.find(needle, offset, offset+length)
            if found < 0 or data.find(needle, found+1, offset+length) >= 0:
                if kind == "asm":
                    raise ValueError(f"Cannot resolve exact shipped assembly dispatch for {name}")
                continue
            # The core routines have no external relocations. Validate the matched extent.
            full = text[start:end]
            if data[found:found+len(full)] != full:
                if kind == "asm":
                    raise ValueError(f"Assembly signature did not bind the full routine for {name}")
                continue
            low = virtual + found-offset
            result[name] = [low, low+len(full)]
    return result


def micro(root, request, expected_windows, profile_library):
    """Run Zstd's own block API on all Huffman-only blocks of the same frame."""
    from leo.storage import short_window
    from tools.pipeline_eval.qualification.cache_residency import load_query

    location = Path(request["entry"]["path"])
    held = HeldReads(location, "tmpfs", load_query(cold.CACHE_LIBRARY))
    with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(held.read)):
        reader = short_window.ShortWindowReader(location)
        windows = [w.index.iq_sha256 for w in reader.windows(stop_sequence=WINDOWS)]
    chunk = reader.manifest.chunks[0]
    if windows != expected_windows or reader.manifest_sha256 != request["entry"]["manifest_digest"]:
        raise ValueError("Huffman block trial needs the same independently checked signed source")
    body = held.files[location / chunk.payload_relative_path]
    spans = []
    structure = inspect(body, chunk.uncompressed_bytes, block_spans=spans)
    if structure["zero_sequence_blocks"] != 802 or structure["block_counts"] != {"compressed": 802}:
        raise ValueError("The Huffman block trial requires the pinned only-literal frame")
    encoded = _bytes_data(body)
    decoded = (ct.c_ubyte * chunk.uncompressed_bytes)()
    destination = ct.addressof(decoded)
    loops = fast_loops(root)
    library = ct.CDLL(str(ZSTD))
    begin, block = library.ZSTD_decompressBegin, library.ZSTD_decompressBlock
    begin.argtypes, begin.restype = (ct.c_void_p,), ct.c_size_t
    block.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_void_p, ct.c_size_t)
    block.restype = ct.c_size_t

    def decode(mode, sampler=None):
        decoder = backend(mode)
        context = decoder.create()
        if not context:
            raise MemoryError("Native Zstandard block context unavailable")
        try:
            if decoder.is_error(begin(context)):
                raise ValueError("Native block decoder initialization failed")
            decoder.configure(context)
            offset = 0
            if sampler:
                sampler.mark(1)
            start = process_time_ns()
            for position, size, plain, _ in spans:
                if block(context, destination+offset, plain, encoded+position, size) != plain:
                    raise ValueError("Same-build Huffman block returned a different extent")
                offset += plain
            cost = process_time_ns()-start
            if sampler:
                sampler.mark(0)
        finally:
            decoder.free(context)
        view = memoryview(decoded).cast("B")
        hashes = ["sha256:" + sha256(view[begin:begin+WINDOW_BYTES]).hexdigest()
                  for begin in range(0, len(view), WINDOW_BYTES)]
        if (offset != len(view) or hashes != expected_windows
                or "sha256:"+sha256(view).hexdigest() != chunk.uncompressed_sha256):
            raise ValueError("Huffman block output does not match the verified signed member")
        return cost

    rows = [dict(mode=mode, cpu_ns=[decode(mode) for _ in range(MICRO_ITERATIONS)]) for mode in ORDERS]
    samples = Samples(profile_library)
    collect = []
    samples.start()
    try:
        for mode in ("asm", "c"):
            first = samples.lib.samples_size()
            for _ in range(4):
                decode(mode, samples)
            collect.append((mode, first, samples.lib.samples_size()))
    finally:
        pcs, overruns = samples.stop()

    symbols = subprocess.check_output(["nm", "-D", "--defined-only", str(ZSTD)], text=True)
    anchor, = [int(row.split()[0], 16) for row in symbols.splitlines() if row.split()[-1] == "ZSTD_versionNumber"]
    base = ct.cast(library.ZSTD_versionNumber, ct.c_void_p).value-anchor
    profile = {}
    for mode, first, after in collect:
        counts = Counter(next((name for name, (lo, hi) in loops.items() if lo <= pc-base < hi), "unresolved_other")
                         for pc in pcs[first:after])
        profile[mode] = dict(counts)
    asm = "HUF_decompress4X2_usingDTable_internal_fast_asm_loop"
    if profile["asm"].get(asm, 0) == 0 or any("_asm_loop" in k for k in profile["c"]):
        raise ValueError("PC samples did not establish the assembly activation contrast")
    return dict(rows=rows, profile=profile, overruns=overruns, matched_loop_offsets=loops,
                sha256=chunk.uncompressed_sha256, blocks=len(spans), verified_windows=WINDOWS)


def run(output, short_binary):
    from tools.pipeline_eval.qualification.cache_residency import load_query

    host = warm.full.check_machine()
    for path, sha in ((ZSTD, ZSTD_SHA), (SYSTEM_STATIC, SYSTEM_STATIC_SHA), (HEADER, HEADER_SHA),
                      (cold.CACHE_LIBRARY, cold.CACHE_SHA), (short_binary, warm.full.SHORT_SHA)):
        cold.verified(path, sha)
    reference = gzip.decompress((HERE / "measurements/zstd-structure-north.json.gz").read_bytes())
    if sha256(reference).hexdigest() != REFERENCE_SHA:
        raise ValueError("The earlier verified structural census changed")
    prior = json.loads(reference)
    windows = prior["checks"]["decoded_windows"]
    request = json.loads(cold.verified(PUBLIC, PUBLIC_SHA))
    request["chunks"] = request["chunks"][:1]
    if request["chunks"][0] != prior["packet"]:
        raise ValueError("Expected just the one original measured public member")
    directory = Path(request["entry"]["path"])
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", directory], text=True).strip() != "tmpfs":
        raise ValueError("Do not read a nonresident bulk source")
    output.mkdir()
    profile_library = assert_header(output)
    (output / "assets").symlink_to(PUBLIC.parent / "assets", target_is_directory=True)
    job = output / "request.json"
    warm.full.freeze(job, request)
    original, _ = warm.archived("north")
    query = load_query(cold.CACHE_LIBRARY)
    rows = []
    with patch.object(warm, "WINDOWS", WINDOWS), patch.object(warm, "MEMBERS", 1):
        for index, mode in enumerate(ORDERS):
            pre, = warm.page_state(directory, request["chunks"], query)
            if not all(warm.resident(row) for row in pre.values()):
                raise ValueError("Public tmpfs member lost residency before admission")
            path = output / f"{index}-{mode}.json"
            subprocess.run([sys.executable, "-BPs", "-m", __spec__.name, "worker", mode, job, short_binary, path],
                           check=True, timeout=25)
            read = lambda file: json.loads(file.read_bytes())
            receipt, document, decoder = (read(path.with_suffix(s)) for s in (".receipt.json", ".json", ".zstd.json"))
            evidence = warm.verify(receipt, document, original, request)
            if receipt["decoded_iq_hashes"] != windows:
                raise ValueError("The same-build path changed a signed decoded window")
            post, = warm.page_state(directory, request["chunks"], query)
            if not all(warm.resident(row) for row in post.values()):
                raise ValueError("Public tmpfs member lost residency during the match")
            rows.append(dict(mode=mode, receipt=receipt, evidence=evidence, decoder=decoder, before=pre, after=post))
    if len({row["receipt"]["sha256"] for row in rows}) != 1:
        raise ValueError("Same-build native detector publications differ")
    micros = micro(output, request, windows, profile_library)
    warm.full.freeze(output / "result.json", dict(host=host, acquisition=rows, micros=micros, request=request,
                    reader_sha256=READER_SHA, header_sha256=HEADER_SHA, decoder_sha256=ZSTD_SHA,
                    static_sha256=SYSTEM_STATIC_SHA, structure_sha256=REFERENCE_SHA,
                    sources={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
                             "zstd_assembly_trial.py", "zstd_decoder_pc.c", "zstd-assembly-protocol.md")}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_subparsers(dest="operation", required=True)
    pair, single = mode.add_parser("run"), mode.add_parser("worker")
    pair.add_argument("output", type=Path)
    pair.add_argument("short_binary", type=Path)
    single.add_argument("mode", choices=("asm", "c"))
    for name in ("request", "binary", "output"):
        single.add_argument(name, type=Path)
    options = vars(cli.parse_args())
    (run if options.pop("operation") == "run" else worker)(**options)
