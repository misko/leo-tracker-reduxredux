"""Observe first-touch costs without changing the release's owned window delivery."""

import argparse
from contextlib import ExitStack, contextmanager
import ctypes as ct
from hashlib import sha256
import importlib
import os
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

import continued_cfo_first_0016 as prefix
from empty_bootstrap import RELEASE, checked


MMAP_THRESHOLD = -3  # glibc M_MMAP_THRESHOLD, from malloc.h
WINDOW_HEAP_LIMIT = 2 * 1024**2
MODES = (("stock", "heap"), ("heap", "stock"))
ZSTD_BACKEND = "7eb41c8b36cd99ed6c67e39f8574e42472687a14c6038c512bb3a90b7082616d"
PINNED_PREFIX = "ce5af5611b56a42ba960e6d1296040b2bbf4ad8e60aea96d182e9ff6f94e3111"
PHYSICAL_WINDOW_BYTES = 1_600_000
TRACE = "allocations.json"


class Mallinfo2(ct.Structure):
    _fields_ = [(name, ct.c_size_t) for name in
                ("arena", "ordblks", "smblks", "hblks", "hblkhd", "usmblks", "fsmblks", "uordblks", "fordblks", "keepcost")]


class Allocator:
    def __init__(self):
        libc = ct.CDLL(None)
        self.mallopt = libc.mallopt
        self.mallopt.argtypes, self.mallopt.restype = (ct.c_int, ct.c_int), ct.c_int
        self.mallinfo = libc.mallinfo2
        self.mallinfo.argtypes, self.mallinfo.restype = (), Mallinfo2
        version = libc.gnu_get_libc_version
        version.argtypes, version.restype = (), ct.c_char_p
        self.version = version().decode("ascii")
        self.brk = libc.sbrk
        self.brk.argtypes, self.brk.restype = (ct.c_ssize_t,), ct.c_void_p
        self.payload_address = ct.pythonapi.PyBytes_AsString
        self.payload_address.argtypes, self.payload_address.restype = (ct.py_object,), ct.c_void_p
        (line,) = (line for line in Path("/proc/self/maps").read_text().splitlines() if line.endswith("[heap]"))
        self.heap_start = int(line.split("-", 1)[0], 16)

    def policy(self, mode):
        if mode == "stock":
            return
        if mode != "heap" or not self.mallopt(MMAP_THRESHOLD, WINDOW_HEAP_LIMIT):
            raise ValueError("The isolated glibc threshold was not accepted")

    def info(self):
        info = self.mallinfo()
        return {name: getattr(info, name) for name in ("arena", "hblks", "hblkhd", "uordblks", "fordblks", "keepcost")}

    def classify(self, raw):
        address = self.payload_address(raw)
        return ("heap" if self.heap_start <= address < self.brk(0) else "outside_heap"), address


def clock():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return dict(cpu_ns=process_time_ns(), elapsed_ns=perf_counter_ns(), minor_faults=usage.ru_minflt,
                major_faults=usage.ru_majflt, system_cpu_s=usage.ru_stime, user_cpu_s=usage.ru_utime,
                input_blocks=usage.ru_inblock, max_rss_kib=usage.ru_maxrss)


def difference(before, after):
    return {name: after[name]-value for name, value in before.items() if name != "max_rss_kib"}


def resident_memory():
    names = {"VmRSS", "RssAnon", "RssFile", "RssShmem", "VmHWM"}
    values = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        name, _, value = line.partition(":")
        if name in names:
            values[name] = int(value.split()[0])
    return values


class Monitor:
    def __init__(self, allocator):
        self.allocator = allocator
        self.reads = []
        self.members = []
        self.addresses = {}

    def read(self, operation, count):
        before = clock()
        raw = operation(count)
        after = clock()
        if type(raw) is not bytes:
            raise ValueError("The exact release stream must return independently owned bytes")
        row = dict(difference(before, after), requested=count, returned=len(raw))
        if count == PHYSICAL_WINDOW_BYTES and raw:
            kind, address = self.allocator.classify(raw)
            row.update(storage=kind, slot=self.addresses.setdefault(address, len(self.addresses)))
        self.reads.append(row)
        return raw

    def member(self, operation, reader, name, size, digest):
        before = clock()
        data = operation(reader, name, size, digest)
        self.members.append(dict(difference(before, clock()), name=name, size=size, sha256=digest))
        return data

    def decoder(self, zstd):
        monitor = self

        class Decoder:
            def __init__(self, *args, **kwargs):
                self.stored = zstd.ZstdDecompressor(*args, **kwargs)

            @contextmanager
            def stream_reader(self, *args, **kwargs):
                with self.stored.stream_reader(*args, **kwargs) as original:
                    yield SimpleNamespace(read=lambda count: monitor.read(original.read, count))

        return SimpleNamespace(ZstdDecompressor=Decoder, ZstdError=zstd.ZstdError)


def worker(mode, output):
    import empty_bootstrap as installed

    starts = clock()
    original_runtime = installed.load_runtime
    allocator = Allocator()
    monitor = Monitor(allocator)
    audit = {}
    with ExitStack() as resources:
        def bind_runtime():
            runtime = original_runtime()
            from leo.storage.short_window import ShortWindowReader

            extension = importlib.import_module("zstandard.backend_c")
            checked(Path(extension.__file__), ZSTD_BACKEND)
            before = clock()
            allocator.policy(mode)
            audit.update(policy_clock=difference(before, clock()), pre_acquisition=allocator.info(),
                         memory_before=resident_memory())
            reader = ShortWindowReader.windows
            scope = reader.__globals__
            observed = monitor.decoder(scope["zstd"])
            original_member = ShortWindowReader._member

            def member(*args):
                return monitor.member(original_member, *args)

            # Paired SHA clones these globals into its privately scoped release reader.
            resources.enter_context(patch.dict(scope, {"zstd": observed}))
            resources.enter_context(patch.object(ShortWindowReader, "_member", member))
            return runtime

        resources.enter_context(patch.object(installed, "load_runtime", bind_runtime))
        prefix.worker("guarded", output)
    final = clock()
    if (len(monitor.reads) != prefix.WINDOWS+1 or monitor.reads[-1]["requested"] != 1
            or monitor.reads[-1]["returned"] or len(monitor.members) != 2
            or any(row["returned"] != PHYSICAL_WINDOW_BYTES or row["requested"] != PHYSICAL_WINDOW_BYTES
                   for row in monitor.reads[:-1])):
        raise ValueError("Expected one installed stream with all 64 signed window deliveries and exact EOF")
    prefix.write(output/TRACE, dict(mode=mode, runtime_libc=allocator.version, post_allocation=allocator.info(),
                 memory_after=resident_memory(), process_scope=difference(starts, final), max_rss_kib=final["max_rss_kib"],
                 distinct_payload_addresses=len(monitor.addresses), reads=monitor.reads,
                 members=monitor.members, **audit))


def run(root):
    from anchored_cfo_raw import verified_pack
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    current = host()
    chunk, files = prefix.mapped_files()
    checked(prefix.PACK/"pack.json", prefix.PACK_SHA)
    verified_pack(prefix.PACK)
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the frozen launch and scorer first")
    if root.parent.resolve() != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs output")
    root.mkdir()
    (root/"tmp").mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root/"tmp")
    inputs = (Path(__file__), HERE/"decoded-allocation-protocol.md", HERE/"decoded_allocation_score.py",
              Path(prefix.__file__), HERE/"continued_cfo.py", HERE/"anchored_cfo_raw.py", HERE/"unified_short_bootstrap.py")
    prefix.write(root/"binding.json", dict(modes=MODES, machine=current, segment=str(prefix.SEGMENT), chunk=chunk,
                 manifest_sha256=prefix.MANIFEST, guard_pack_sha256=prefix.PACK_SHA, backend_sha256=ZSTD_BACKEND,
                 commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
                 sources={p.name: sha256(p.read_bytes()).hexdigest() for p in inputs}))
    for ordered, cases in enumerate(MODES, 1):
        for mode in cases:
            output = root/f"{ordered}-{mode}"
            args = ["/usr/bin/timeout", "--kill-after=1s", "20s", RELEASE/"venv/bin/python", "-IB", Path(__file__),
                    "worker", output, mode]
            before = prefix.resident(files)
            result = measure(args, env, output)
            prefix.write(root/(output.name+"-clock.json"), dict(command=list(map(str, args)), clock=result,
                         resident_before=before, resident_after=prefix.resident(files)))
            if result["exit_code"]:
                raise RuntimeError(result["stderr_tail"])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "worker"))
    cli.add_argument("root", type=Path)
    cli.add_argument("mode", nargs="?", choices=("stock", "heap"))
    args = cli.parse_args()
    if args.action == "run":
        run(args.root)
    elif args.mode:
        worker(args.mode, args.root)
    else:
        cli.error("worker requires one exact allocator arm")
