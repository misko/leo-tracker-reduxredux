"""Authenticate and attribute stock Zstandard decoding on one resident member."""

import argparse
from bisect import bisect_right
from collections import Counter
import ctypes as ct
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
from time import process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from . import sparse_cold_input as release
from .dense_zstd_backend_trial import BUNDLED_SHA
from .warm_six_prefetch import ColdPage, read_nowait
from .zstd_structure import inspect


HERE = Path(__file__).resolve().parent
PHYSICAL = Path("/srv/bulk/leo-dev/leo-physical-stage-envelope-2j7mlwtt/recovered-request.json")
PHYSICAL_SHA = "efb7e7eb718d790330d971bb6a7e704057e3b8de062394bda0b88bb12cc997c0"
PUBLIC = Path("/dev/shm/leo-v3-warm-six-public-03/request.json")
PUBLIC_SHA = "6b291a8da703ff7817d74c4f5ff56a106d91626a376ab2325ec7833e8aa8f16a"
MEMBER_SHA = "sha256:556772d5619b710cae8030050b8f8a4a7b18f4b196e57cddc14562c8ca73404a"
READER_SHA = "0884ab7ca630d59dd041e50e0ef89cd847ca842c11097f8bde06b869645eafa2"
PROFILE_ITERATIONS, SAMPLE_US = 16, 500


class HeldReads:
    def __init__(self, root, filesystem, query):
        self.root, self.filesystem, self.query = root, filesystem, query
        self.pages, self.files = {}, {}

    def read(self, path, limit):
        if path.parent != self.root:
            raise ValueError("Unexpected signed reader member")
        if path in self.files:
            return self.files[path]
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= limit:
                raise ValueError("Unexpected signed member extent")
            page = os.sysconf("SC_PAGE_SIZE")
            resident, expected = self.query(fd, before.st_size), (before.st_size+page-1)//page
            self.pages[path.name] = [resident, expected]
            if resident != expected:
                raise ColdPage(f"{path.name} has {resident}/{expected} resident pages")
            if self.filesystem == "xfs":
                data = bytearray(before.st_size)
                try:
                    count = read_nowait(fd, [data], 0)
                except OSError as exc:
                    raise ColdPage(f"{path.name}: cache-only read unavailable, errno {exc.errno}") from exc
                if count != before.st_size:
                    raise ColdPage(f"{path.name}: incomplete cache-only read")
                payload = bytes(data)
            else:
                with os.fdopen(os.dup(fd), "rb") as stream:
                    payload = stream.read(before.st_size)
            after = os.fstat(fd)
            if len(payload) != before.st_size or any(getattr(before, key) != getattr(after, key)
                    for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")):
                raise ValueError("Signed member changed while held")
        finally:
            os.close(fd)
        self.files[path] = payload
        return payload


def admission(short_window, query):
    candidates = (("DS30-0008-private", PHYSICAL, PHYSICAL_SHA, "xfs"), ("public-north", PUBLIC, PUBLIC_SHA, "tmpfs"))
    decisions = []
    for case, request, pin, fs in candidates:
        source = json.loads(release.verified(request, pin))
        entry = source["entry"]
        root = Path(entry["path"]).resolve(strict=True)
        if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root], text=True).strip() != fs:
            raise ValueError("Candidate source has an unexpected filesystem")
        view = HeldReads(root, fs, query)
        # Check all three original names before any content read on this source.
        from tools.pipeline_eval.qualification.cache_residency import cache_snapshot

        plan = [(root, name, (root / name).stat().st_size)
                for name in ("manifest.json", "windows-000000.jsonl", "iq-000000.ci16.zst")]
        state = cache_snapshot(plan, os.sysconf("SC_PAGE_SIZE"), query)
        row = dict(case=case, filesystem=fs, pre_snapshot=state, descriptor_pages=view.pages)
        decisions.append(row)
        if state["observed_members"] != 3 or state["cached_pages"] != state["observed_file_pages"]:
            row["stop"] = "missing resident pages"
            continue
        try:
            with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(view.read)):
                reader = short_window.ShortWindowReader(root)
                chunk = reader.manifest.chunks[0]
                pin_chunk = MEMBER_SHA if case == "DS30-0008-private" else source["chunks"][0]["compressed_sha256"]
                if (reader.manifest_sha256 != entry["manifest_digest"] or chunk.compressed_sha256 != pin_chunk
                        or chunk.window_count != 64 or chunk.first_sequence != 0 or chunk.uncompressed_bytes != 102400000):
                    raise ValueError("Member does not match its original sealed recording")
                windows = tuple(w.index.iq_sha256 for w in reader.windows(stop_sequence=64))
        except ColdPage as exc:
            row["stop"] = str(exc)
            continue
        row["admitted"] = True
        return reader, chunk, view, windows, decisions
    raise ValueError(f"No fully resident verified member was readable: {decisions}")


class Samples:
    def __init__(self, library):
        self.lib = ct.CDLL(str(library))
        self.lib.start_samples.argtypes = (ct.c_int,)
        self.lib.mark_decode.argtypes = (ct.c_int,)
        self.lib.mark_decode.restype = None
        self.lib.sample_at.argtypes = (ct.c_int,)
        self.lib.sample_at.restype = ct.c_size_t

    def start(self):
        if self.lib.start_samples(SAMPLE_US):
            raise RuntimeError("Cannot establish diagnostic thread CPU timer")

    def stop(self):
        count = self.lib.stop_samples()
        if count >= 32768:
            raise ValueError("The bounded PC buffer filled")
        return [self.lib.sample_at(i) for i in range(count)], self.lib.sample_overruns()

    def mark(self, value):
        self.lib.mark_decode(value)


def locations(cext, samples):
    table = subprocess.check_output(["nm", "-n", "-S", str(cext)], text=True)
    symbols = []
    for row in table.splitlines():
        fields = row.split()
        if len(fields) == 4 and fields[2] in ("t", "T"):
            start, width = (int(value, 16) for value in fields[:2])
            if width:
                symbols.append((start, start+width, fields[3]))
    anchor, = [start for start, _, name in symbols if name == "PyInit_backend_c"]
    library = ct.CDLL(str(cext))
    base = ct.cast(library.PyInit_backend_c, ct.c_void_p).value - anchor
    starts = [r[0] for r in symbols]
    counted = Counter()
    for pc in samples:
        addr = pc-base
        i = bisect_right(starts, addr)-1
        counted[symbols[i][2] if i >= 0 and addr < symbols[i][1] else "unattributed"] += 1
    modes = Counter()
    for name, count in counted.items():
        if name.startswith("HUF_") or "decodeLiteralsBlock" in name:
            modes["literal_decode"] += count
        elif any(token in name for token in ("decompressSequences", "decodeSeqHeaders", "buildFSETable")):
            modes["sequence_decode_and_execute"] += count
        else:
            modes["unresolved_other"] += count
    return dict(symbols=dict(counted), classes=dict(modes), total=len(samples))


def timed_reads(short_window, reader, view, expected, samples=None):
    backend = short_window.zstd
    clocks, calls = [], []

    class Stream:
        def __init__(self, original):
            self.original = original

        def __enter__(self):
            self.reader = self.original.__enter__()
            return self

        def __exit__(self, *args):
            return self.original.__exit__(*args)

        def read(self, n):
            if samples is not None:
                samples.mark(1)
            start = process_time_ns()
            try:
                return self.reader.read(n)
            finally:
                clocks.append(process_time_ns()-start)
                if samples is not None:
                    samples.mark(0)
                calls.append(n)

    class Decoder:
        def stream_reader(self, data):
            return Stream(backend.ZstdDecompressor().stream_reader(data))

    start = process_time_ns()
    with (patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(view.read)),
          patch.object(short_window, "zstd", SimpleNamespace(ZstdDecompressor=Decoder, ZstdError=backend.ZstdError))):
        recorded = tuple(w.index.iq_sha256 for w in reader.windows(stop_sequence=64))
    verified = process_time_ns()-start
    if recorded != expected or calls != [1600000]*64+[1]:
        raise ValueError("Released decoder did not reproduce the complete original windows or read boundary")
    return dict(decode_cpu_ns=sum(clocks), verified_cpu_ns=verified, reads=len(calls))


def run(root):
    from leo.storage import short_window
    from tools.pipeline_eval.qualification.cache_residency import load_query
    import zstandard.backend_c as cext
    from .full_short_cold import check_machine

    host = check_machine()
    release.verified(Path(cext.__file__), BUNDLED_SHA)
    release.verified(Path(short_window.__file__), READER_SHA)
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    query = load_query(release.CACHE_LIBRARY)
    root.mkdir()
    library = root / "pc.so"
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-O2", "-shared", "-fPIC", str(HERE / "zstd_decoder_pc.c"),
                    "-o", str(library)], check=True, env=dict(os.environ, TMPDIR=str(root)))
    reader, chunk, view, windows, decisions = admission(short_window, query)
    frame = view.files[reader.path / chunk.payload_relative_path]
    structure = inspect(frame, chunk.uncompressed_bytes)
    reference_first = [timed_reads(short_window, reader, view, windows) for _ in range(2)]
    samples = Samples(library)
    samples.start()
    try:
        profiled = [timed_reads(short_window, reader, view, windows, samples) for _ in range(PROFILE_ITERATIONS)]
    finally:
        pcs, overruns = samples.stop()
    reference_last = [timed_reads(short_window, reader, view, windows) for _ in range(2)]
    profile = locations(Path(cext.__file__), pcs)
    if profile["total"] < 250:
        raise ValueError("Too few actual decoder instruction samples")
    flags = next(line.split(":", 1)[1].split() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("flags"))
    data = dict(machine=host, admissions=decisions, packet=chunk.model_dump(mode="json"), structure=structure,
                cext=str(cext.__file__), cext_sha256=BUNDLED_SHA, reader_sha256=READER_SHA,
                checks=dict(decoded_windows=windows, manifest=reader.manifest_sha256,
                            snapshotted_files={p.name: len(b) for p, b in view.files.items()}),
                unprofiled_before=reference_first, profiled=profiled, unprofiled_after=reference_last,
                pc_profile=profile, pc_interval_us=SAMPLE_US, overruns=overruns,
                cpu_features={k: k in flags for k in ("bmi1", "bmi2", "avx2")},
                sources={p: sha256((HERE / p).read_bytes()).hexdigest() for p in
                         ("zstd_structure.py", "zstd_structure_trial.py", "zstd_decoder_pc.c", "zstd-structure-protocol.md")})
    (root / "result.json").write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False)+"\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    run(cli.parse_args().root)
