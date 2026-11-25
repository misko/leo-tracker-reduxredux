"""Measure same-lane reuse of the shipped 8 ms verifier's integer phasor table."""

import argparse
from contextlib import ExitStack
import ctypes as ct
import fcntl
import gzip
import json
import os
from pathlib import Path
import resource
from statistics import median
import subprocess
import sys
from time import monotonic, perf_counter_ns, process_time_ns, time_ns

from .sparse8_native_profile import (
    BASE, CUSTODY, Factor, ORIGINAL, PILOTS, RELEASE, REPEATS, RECIPE_SOURCE, SPARSE, STOCK,
    THREADS, Receiver, checked, digest, fixture, one,
)


HERE = Path(__file__).resolve().parent
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
DRIVER = Path("/tmp/leo-v3-ds30-paired-evaluation/reports/ALGO08/v3/ds30_paired_evaluation.py")
SOURCE = Path("/var/tmp/leo-v3-eight-ms-build-padded/scouts/8ms")
SOURCE_PINS = {
    "portable_verifier.c": "bae3798db85b2682ae88d7ce545aac0d084c5f3a747d34cf5c43edd908e0996b",
    "receiver_stencil_verify.inc": "8b2f4162d9637991e45b3e47eea28aadd9ff254bee02389569be69180f064a63",
    "receiver_phase_free_verify.inc": "9c41b48fc3bb3c7eb42456d0d589da3e9f16fe67e0dd82b3e188785e9bc45a36",
    "receiver_fractional_exact.inc": "7e6e4d0d0bd3074963a50340e645f66023c3a273ea2fc7cd6279496f2bef2a2b",
}
FIELD = "bb6942d2d7dc750ca51cbeeb7c5787427acd2df2f845641bf2ed8b456781536d"
TOLERANCE = 1e-8
ARMS = ("exact", "shared")
CAP_SECONDS = 6


def share_table(source):
    source = one(source, "static int phase_free_fractional(",
                 """int shared_phase_safe(double margin, double egap, double cgap, double er, double cr)
{
    double radius = er + cr;
    return egap > 2. * er && cgap > 2. * cr &&
           fabs(margin - gate) > radius && fabs(margin - .1) > radius;
}

static int phase_free_fractional(""")
    source = one(source, "    ++phase_attempts;", """    ++phase_attempts;
    if (w->integer_hz != cfo || fegetround() != FE_TONEAREST) return 0;""")
    source = one(source, "PortableFineComplex p = rotate(-tau * cfo * (first + k + offset) / rate);",
                 """/* Frame start and the vertex offset contribute only a shared phase to
         * each frame. Keep the exact relative tap table the integer stencil paid. */
        GlrtComplex p = w->glrt_rotation[k];""")
    source = one(source, "p.r - a.im * p.i, a.re * p.i + a.im * p.r",
                 "p.re - a.im * p.im, a.re * p.im + a.im * p.re")
    source = one(source, "p.r - b.im * p.i, b.re * p.i + b.im * p.r",
                 "p.re - b.im * p.im, b.re * p.im + b.im * p.re")
    source = one(source, "128. * DBL_EPSILON", "256. * DBL_EPSILON")
    source = one(source, "if (!(egap > 2. * er && cgap > 2. * cr &&\n"
                 "          fabs(margin - gate) > radius && fabs(margin - .1) > radius)) return 0;",
                 "if (!shared_phase_safe(margin, egap, cgap, er, cr)) return 0;")
    return one(source, "    ++phase_accepted;",
               """    /* Preserve the stock absolute branch's cross-call cache invalidation. */
    w->integer_hz = NAN;
    ++phase_accepted;""")


def instrument(source, enabled):
    prefix = "#include <fenv.h>\n"
    source = one(source, '#include "receiver_phase_free_verify.inc"', '#include "frozen_phase_free.inc"')
    body = """#include "shared_integer_phase_audit.h"

int portable_verifier_factor(PortableVerifier *w, unsigned epoch, PortableVerifierResult *out) {
    int status = verify_glrt(w, epoch, out, 0, %d);
    if (!status) shared_phase_record(epoch, out);
    return status;
}""" % int(enabled)
    return prefix + one(source, """int portable_verifier_factor(PortableVerifier *w, unsigned epoch, PortableVerifierResult *out) {
    return verify_glrt(w, epoch, out, 0, 0);
}""", body)


def build(root):
    if os.sched_getaffinity(0) != {3} or os.nice(0) < 15:
        raise ValueError("Build off the shared timing CPU")
    root.mkdir()
    recipe = json.loads(checked(BASE/"build-receipt.json", STOCK["build-receipt.json"]))
    checked(SPARSE/"use.so", ORIGINAL)
    checked(SPARSE/"timing_first_receiver.o", STOCK["timing_first_receiver.o"])
    for arg in recipe["relink"]:
        if arg.endswith(".o"):
            obj = Path(arg)
            name = obj.name
            pin = STOCK[name] if name == "two_carrier_receiver.o" else recipe["short_object_sha256"][name]
            checked(obj, pin)
    closure = RECIPE_SOURCE/"tools/pipeline_eval/variants/experimental"
    source, stencil, phase, fractional = (
        checked(folder/name, SOURCE_PINS[name]) for folder, name in (
            (SOURCE, "portable_verifier.c"), (SOURCE, "receiver_stencil_verify.inc"),
            (closure, "receiver_phase_free_verify.inc"), (closure, "receiver_fractional_exact.inc")))
    commands = []

    def run(arguments):
        command = list(map(str, arguments))
        commands.append(command)
        subprocess.run(command, cwd=RECIPE_SOURCE/"native/algo08v2", check=True)

    def link(path, verifier=None):
        objects = {"timing_first_receiver.o": SPARSE/"timing_first_receiver.o"}
        if verifier is not None:
            objects["portable_verifier.o"] = verifier
        args = recipe["relink"]
        run([args[0], *[objects.get(Path(arg).name, arg) for arg in args[3:-1]], path])

    pristine = root/"installed.so"
    link(pristine)
    checked(pristine, ORIGINAL)
    for arm in ARMS:
        folder = root/arm
        folder.mkdir()
        (folder/"receiver_stencil_verify.inc").write_bytes(stencil)
        (folder/"receiver_fractional_exact.inc").write_bytes(fractional)
        (folder/"frozen_phase_free.inc").write_text(share_table(phase.decode()) if arm == "shared" else phase.decode())
        cfile, obj = folder/"portable_verifier.c", folder/"portable_verifier.o"
        cfile.write_text(instrument(source.decode(), arm == "shared"))
        run([*recipe["compile"][:-4], "-I", HERE, "-c", cfile, "-o", obj])
        link(root/(arm+".so"), obj)
    value = dict(binaries={arm: digest((root/(arm+".so")).read_bytes()) for arm in ("installed", *ARMS)},
                 source_sha256=SOURCE_PINS, sparse_timing_sha256=STOCK["timing_first_receiver.o"], commands=commands,
                 experimental_source_sha256=digest(Path(__file__).read_bytes()),
                 audit_header_sha256=digest((HERE/"shared_integer_phase_audit.h").read_bytes()))
    path = root/"build.json"
    path.write_text(json.dumps(value, sort_keys=True))
    return digest(path.read_bytes())


class Event(ct.Structure):
    _fields_ = [("epoch", ct.c_uint), ("flags", ct.c_uint)] + [
        (name, ct.c_double) for name in ("carrier", "offset", "residual", "exact", "rolled")]


class CheckedReceiver(Receiver):
    def __init__(self, path, pilot, audit):
        super().__init__(path, pilot, False)
        self.audited = audit
        if audit:
            self.take = self.lib.shared_phase_take
            self.take.argtypes, self.take.restype = (ct.POINTER(Event), ct.POINTER(ct.c_uint64)), ct.c_int

    def checked_call(self, iq, lane, center):
        out = (Factor * 2)()
        cpu, elapsed = process_time_ns(), perf_counter_ns()
        count = self.call(self.ctx, iq, lane, center - 800_000., center + 800_000., out)
        clock = [process_time_ns()-cpu, perf_counter_ns()-elapsed]
        if count not in (0, 1) or count and out[0].rank != 0:
            raise ValueError("Expected one saved 8 ms primary or an empty lane")
        event, stats, records = Event(), (ct.c_uint64*3)(), 0
        if self.audited:
            records = self.take(ct.byref(event), stats)
            if records not in (0, 1) or count > records or stats[2] or not 0 <= stats[1] <= stats[0] <= records:
                raise ValueError("The ordinary short callback has an invalid verifier audit")
        result = tuple(getattr(out[0], name) for name, _ in Factor._fields_) if count else ()
        measured = tuple(getattr(event, name) for name, _ in Event._fields_) if records else ()
        return result, measured, tuple(stats), clock


def compare(exact, shared, leading):
    signed = lambda values: [x.hex() if isinstance(x, float) else x for x in values]
    if len(exact) != len(shared) or signed(exact[:leading]) != signed(shared[:leading]):
        raise ValueError("Discrete factor or verifier output changed")
    errors = [abs(a-b) for a, b in zip(exact[leading:], shared[leading:], strict=True)]
    if any(not delta <= TOLERANCE for delta in errors):
        raise ValueError("A continuous score left its frozen comparison tolerance")
    return errors


def benchmark(root, pin, *, lease_fd, event_ns):
    status = dict(cpu=list(os.sched_getaffinity(0)), nice=os.nice(0),
                  io=subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip(),
                  threads={key: os.environ.get(key) for key in THREADS})
    source = LOCK.stat()
    held = os.fstat(lease_fd)
    if ((held.st_dev, held.st_ino) != (source.st_dev, source.st_ino) or time_ns()-event_ns > 4_000_000_000
            or status["cpu"] != [2] or status["nice"] < 15 or "idle" not in status["io"]
            or set(status["threads"].values()) != {"1"}):
        raise ValueError("Only the fresh authorized one-core watcher lease can profile this bench")
    fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ready = json.loads(checked(root/"build.json", pin))
    for arm, sha in ready["binaries"].items():
        checked(root/(arm+".so"), sha)
    panels, sources = {}, {}
    with ExitStack() as stack:
        contexts = {}
        for case in CUSTODY:
            rows, sources[case] = fixture(case, stack)
            operands = [(visit, edge, center, iq, sha, rx) for visit, edge, center, iq, sha in rows for rx in (0, 1)]
            saved = {}
            for repeat in range(REPEATS):
                for visit, edge, center, iq, sha, rx in operands:
                    if edge not in contexts:
                        pilot = ct.create_string_buffer(checked(RELEASE/"assets"/(edge+".f32"), PILOTS[edge]))
                        contexts[edge] = {arm: CheckedReceiver(root/(arm+".so"), pilot, arm != "installed")
                                          for arm in ("installed", *ARMS)}
                        for context in contexts[edge].values():
                            stack.callback(context.close)
                    engines = contexts[edge]
                    key = visit, rx
                    if repeat == 0:
                        original = engines["installed"].checked_call(iq, rx, center)[0]
                        saved[key] = dict(visit=visit, rx=rx, iq_sha256=sha, original=original, rounds=[])
                    initial = saved[key]
                    order = ARMS if (repeat+visit+rx) % 2 else ARMS[::-1]
                    pair = {arm: engines[arm].checked_call(iq, rx, center) for arm in order}
                    a, b = (pair[arm] for arm in ARMS)
                    if native_bytes(a[0], Factor) != native_bytes(initial["original"], Factor) or a[2] != (0, 0, 0):
                        raise ValueError("The pristine sparse 8 ms receiver and exact control differ")
                    exact_parts = zip((a[0], a[1]), (b[0], b[1]), (Factor, Event), strict=True)
                    if not b[2][1] and any(native_bytes(x, structure) != native_bytes(y, structure)
                                          for x, y, structure in exact_parts):
                        raise ValueError("A fallback did not reproduce all absolute score bits")
                    compare(a[0], b[0], 4)
                    compare(a[1], b[1], 5)
                    initial["rounds"].append(pair)
            panels[case] = list(saved.values())
    return dict(host=status, ready_sha256=pin, build=ready, sources=sources, panels=panels,
                backing_waveform_reads=0, catalogue_reads=0, solves=0)


def native_bytes(values, structure):
    return bytes(structure(*values)) if values else b""


def watch(root, pin, official_pid):
    from .profiled_grid_export_admission import observe

    if os.sched_getaffinity(0) != {3} or os.nice(0) < 15:
        raise ValueError("Run the admission watcher on low-priority CPU3")
    build_doc = json.loads(checked(root/"build.json", pin))
    if build_doc["experimental_source_sha256"] != digest(Path(__file__).read_bytes()):
        raise ValueError("Run the frozen native worker")
    process = Path("/proc")/str(official_pid)

    def launch(event):
        command_line = (process/"cmdline").read_bytes().split(b"\0")
        if (os.fsencode(DRIVER) not in command_line or b"run" not in command_line or b"--watch" not in command_line
                or (process/"task"/str(official_pid)/"children").read_text().strip()):
            raise ValueError("The official driver already owns a child or changed")
        with LOCK.open("rb") as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if time_ns()-event["unix_ns"] > 2_000_000_000:
                raise ValueError("The official deferral expired")
            command = ["taskset", "-c", "2", "nice", "-n", "15", "ionice", "-c", "3", sys.executable, "-B",
                       "-m", "reports.ALGO08.v3.short_shared_integer_phase", "bench", str(root), pin,
                       str(lease.fileno()), str(event["unix_ns"])]
            env = os.environ | {name: "1" for name in THREADS}
            started = monotonic()
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            try:
                result = subprocess.run(command, pass_fds=(lease.fileno(),), timeout=CAP_SECONDS,
                                        env=env, capture_output=True, text=True)
                status, stdout, stderr = result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired as error:
                status, stdout, stderr = 124, "", (error.stderr or b"").decode()
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            clocks = dict(elapsed_s=monotonic()-started, user_s=after.ru_utime-before.ru_utime,
                          system_s=after.ru_stime-before.ru_stime, input_blocks=after.ru_inblock-before.ru_inblock,
                          major_faults=after.ru_majflt-before.ru_majflt)
            return dict(event=event, returncode=status, clocks=clocks,
                        result=json.loads(stdout) if status == 0 else None, stderr=stderr)

    return observe(launch, None)


def price(data):
    signed = json.loads(gzip.decompress(checked(HERE/"measurements/combined-small-panel-0016-natural-pair.json.gz", FIELD)))
    result = signed["results"]["DS30-0016"]["trial"]
    native = result["receiver_audit"]["native"]
    counts = native["native_calls"]
    if native["short_primary_sha256"] != ORIGINAL:
        raise ValueError("The field donor callback differs")
    cohort = dict(positive=native["factors"]["short_primary"], empty=counts["short_primary"]-native["factors"]["short_primary"])
    report = {}
    for key, rows in data["panels"].items():
        group = {}
        for label, positive in (("positive", True), ("empty", False)):
            values = [row for row in rows if bool(row["original"]) == positive]
            per_repeat = [sum(row["rounds"][repeat]["exact"][3][0]-row["rounds"][repeat]["shared"][3][0]
                              for row in values)/len(values) for repeat in range(REPEATS)]
            group[label] = dict(lanes=len(values), median_paired_saved_ns=median(per_repeat), paired_saved_ns=per_repeat)
        saved = sum(cohort[label]*value["median_paired_saved_ns"] for label, value in group.items())
        report[key] = dict(by_outcome=group, projected_saved_cpu_s=saved/1e9,
                           projected_combined_cpu_fraction=saved/sum(native["native_cpu_ns"].values()))
    return dict(field_native=native, cohort=cohort, estimate_by_donor=report, field_sha256=FIELD)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    parsers = cli.add_subparsers(dest="mode", required=True)
    for name in ("build", "watch", "bench", "price"):
        p = parsers.add_parser(name)
        p.add_argument("path", type=lambda path: Path(path).resolve())
        if name in ("watch", "bench"):
            p.add_argument("pin")
        if name == "watch":
            p.add_argument("pid", type=int)
        if name == "bench":
            p.add_argument("lease", type=int)
            p.add_argument("event_ns", type=int)
    args = cli.parse_args()
    if args.mode == "build":
        print(build(args.path))
    else:
        if args.mode == "watch":
            result = watch(args.path, args.pin, args.pid)
        elif args.mode == "bench":
            result = benchmark(args.path, args.pin, lease_fd=args.lease, event_ns=args.event_ns)
        else:
            result = price(json.loads(args.path.read_bytes()))
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
