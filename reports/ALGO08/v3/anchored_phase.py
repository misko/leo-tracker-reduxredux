"""Compare guarded re-anchored phase in the actual mixed signed receiver and tail."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from . import short_cfo_exact_cost as exact, short_cfo_refine as ref
from .centered_primary import BUILD_PIN, RELEASE_BUILD, RELEASE_PIN
from .directed_verifier_trial import replace_once
from .tail_confirm import SOURCE as FULL_SOURCE_PIN


HERE = Path(__file__).resolve().parent
EXACT_GATHER = Path("/dev/shm/leo-short-cfo-exact-cost-results02/build/tail.so")
GATHER_PIN = "a09cf653bcb90fb6b05d29650c41d259e2c867824bf0091e3a9a43a10f5dab13"
SCHEDULED_RECEIPT_PIN = "85f44c98774591b12a60c7a14b24b040866a6bc18528d394455a0aa18dc38999"
WEAK = Path("/dev/shm/leo-v3-short-cfo-dev02/weak-clips.zip")
SHORT_OBJECTS = Path("/var/tmp/leo-short-signed-02/short")
VERIFY_PIN = "4cceaa68fe8d7f93608d1d07f585e2bc5c68955a22619d989052d6cde2e70def"
STENCIL_PIN = "8b2f4162d9637991e45b3e47eea28aadd9ff254bee02389569be69180f064a63"
ARMS = ("stock", "anchored")
ORDER = (ARMS, ARMS[::-1]) * 2
GLRT = "static int glrt(PortableVerifier"
MARK = "    return 0;\n}\n\nint portable_verifier_glrt("


def recurrence():
    text = ref.verified(exact.FRACTIONAL, exact.FRACTIONAL_PIN).decode()
    text = replace_once(text, "absolute_fractional_correlations", "anchored_correlations")
    text = replace_once(text, "double offset)", "double offset, double *maximum_mass)")
    text = replace_once(text, "    double old_fraction", "    const PortableFineComplex step = rotate(-tau * cfo / rate);\n"
                        "    *maximum_mass = 0.;\n    double old_fraction")
    text = replace_once(text, "        for (int k = 0;", "        PortableFineComplex z = {0., 0.};\n        for (int k = 0;")
    text = replace_once(text, "                double norm = 0.;", "                double norm = 0., mass = 0.;")
    text = replace_once(text, "                for (int t = 0; t < 16; ++t) w->weights[row][t] /= norm;",
                        "                for (int t = 0; t < 16; ++t) {\n"
                        "                    w->weights[row][t] /= norm;\n"
                        "                    mass += fabs(w->weights[row][t]);\n"
                        "                }\n                *maximum_mass = fmax(*maximum_mass, mass);")
    return replace_once(text, "            PortableFineComplex z = rotate(-tau * cfo * position / rate);",
                        "            if (k % anchor_stride == 0) z = rotate(-tau * cfo * position / rate);\n"
                        "            else z = multiply(z, step);")


def receiver_source(source, enable):
    shared = (HERE / "anchored_phase.inc").read_text()
    source = replace_once(source, GLRT, shared + recurrence() + "\n" + GLRT)
    source = replace_once(source, MARK, "    if (!diagnostics) track_rotation(epoch, out);\n" + MARK)
    if enable:
        source = replace_once(source, "!phase_free_fractional(w, frames, starts", "!anchored_fractional(w, frames, starts")
        source = replace_once(source, "int portable_verifier_factor(PortableVerifier *w, unsigned epoch, PortableVerifierResult *out) {\n"
                              "    return verify_glrt(w, epoch, out, 0, 0);",
                              "int portable_verifier_factor(PortableVerifier *w, unsigned epoch, PortableVerifierResult *out) {\n"
                              "    return verify_glrt(w, epoch, out, 0, 1);")
    return source + """
int anchored_zero_probe(PortableVerifier *w, const int16_t *iq, unsigned lane,
                        double exact[3], double guarded[3], unsigned flags[2]) {
    if (portable_verifier_load(w, iq, lane)) return -1;
    if (glrt(w, 100, -120000., .375, exact, exact+1, exact+2, flags, 0)) return -1;
    return glrt(w, 100, -120000., .375, guarded, guarded+1, guarded+2, flags+1, 1);
}
"""


def tail_source():
    original = (HERE / "short_cfo_refine.inc").read_text()
    prefix, body = original.split(exact.BODY_MARK, maxsplit=1)
    body = exact.BODY_MARK + body
    gathered = replace_once(replace_once(body, exact.BODY_MARK, "static int exact_tail("), exact.LOAD, exact.GATHER)
    fast = replace_once(gathered, "static int exact_tail(", "static int recurrence_tail(")
    fast = replace_once(fast, "    if (integer) {", "    double weight_mass;\n    if (integer) {")
    fast = replace_once(fast, exact.CORRELATION, "anchored_correlations(w, frames, starts, cfo, offset, &weight_mass)")
    body = """
static _Thread_local uint64_t tail_retries;
uint64_t anchored_take_tail_retries(void) {
    uint64_t count = tail_retries;
    tail_retries = 0;
    return count;
}
int short_cfo_reanchored(PortableVerifier *w, const int16_t *iq, unsigned lane, unsigned epoch,
                         double offset, double cfo, double out[8]) {
    if (fegetround() == FE_TONEAREST && !recurrence_tail(w, iq, lane, epoch, offset, cfo, out)
        && !tail_needs_exact(out)) return 0;
    ++tail_retries;
    return exact_tail(w, iq, lane, epoch, offset, cfo, out);
}
"""
    return ((HERE / "anchored_phase.inc").read_text() + recurrence() + prefix +
            (HERE / "short_cfo_exact_cost.inc").read_text() + gathered + fast + body)


def build(root):
    installed, original_short = ref.PAYLOAD / "receiver.so", ref.ORIGINAL / "short-primary.so"
    ref.verified(installed, ref.INSTALLED_SHA)
    ref.verified(original_short, ref.PREFIX_PIN)
    saved = json.loads(ref.verified(ref.ORIGINAL / "build-receipt.json", BUILD_PIN))
    full = json.loads(ref.verified(RELEASE_BUILD, RELEASE_PIN))
    compile_flags = full["commands"][-2][:-4]
    if subprocess.check_output(["cc", "--version"], text=True).splitlines()[0] != full["compiler"]:
        raise ValueError("Compiler differs from the frozen receiver")
    paths, commands = {}, []

    def run(command):
        commands.append(list(map(str, command)))
        subprocess.run(command, cwd=full["cwd"], check=True)

    for mode, link, source, pin, binary_pin in (
        ("full", full["commands"][-1], RELEASE_BUILD.with_name("portable_verifier.c"), FULL_SOURCE_PIN, ref.INSTALLED_SHA),
        ("short", saved["relink"], SHORT_OBJECTS / "portable_verifier.c", VERIFY_PIN, ref.PREFIX_PIN),
    ):
        control = root / (mode + "-pristine.so")
        run([*link[:-1], control])
        ref.verified(control, binary_pin)
        source_text = ref.verified(source, pin).decode()
        for arm in ARMS:
            folder = root / (mode + "-" + arm)
            folder.mkdir()
            if mode == "short":
                stencil = SHORT_OBJECTS / "receiver_stencil_verify.inc"
                (folder / stencil.name).write_bytes(ref.verified(stencil, STENCIL_PIN))
            obj, path, combined = folder / "portable_verifier.o", folder / "receiver.so", folder / "verifier.c"
            combined.write_text(receiver_source(source_text, arm == "anchored"))
            run([*compile_flags, "-c", combined, "-o", obj])
            # The released link keeps its existing symbol binding and object order.
            run([*(obj if v.endswith("/portable_verifier.o") else v for v in link[:-1]), path])
            paths[arm, mode] = path
    extension = root / "anchored-tail.inc"
    extension.write_text(tail_source())
    binary, metadata = ref.build(root / "tail", installed, extension)
    return paths, binary, dict(commands=commands, tail=metadata,
                receivers={"/".join(k): sha256(p.read_bytes()).hexdigest() for k, p in paths.items()},
                source_pins=[FULL_SOURCE_PIN, VERIFY_PIN], exact_gather_sha256=GATHER_PIN)


class Event(ct.Structure):
    _fields_ = [("epoch", ct.c_uint), ("flags", ct.c_uint)] + [
        (name, ct.c_double) for name in ("frequency", "offset", "residual", "exact", "control")]


def audit(path):
    take = path.native.lib.anchored_take_audit
    take.argtypes, take.restype = (ct.POINTER(Event), ct.POINTER(ct.c_uint64)), ct.c_int
    out, n = (Event * 8)(), (ct.c_uint64 * 2)()
    size = take(out, n)
    if not 0 <= size <= 8:
        raise ValueError("Verifier audit overflow")
    rows = [tuple(getattr(row, field) for field, _ in Event._fields_) for row in out[:size]]
    return rows, tuple(n)


def continuous_control(lhs, rhs, maximum, limit):
    if len(lhs) != len(rhs):
        raise ValueError("Native signed candidate membership changed")
    for a, b in zip(lhs, rhs, strict=True):
        if a[:4] != b[:4]:
            raise ValueError("Signed order, rank, original timing or residual frequency changed")
        for key, x, y in zip(("exact", "rolled"), a[4:], b[4:], strict=True):
            delta = abs(x-y)
            if delta > limit:
                raise ValueError("Continuous receiver score exceeds the frozen tolerance")
            maximum[key] = max(maximum[key], delta)


def audited_flags(a, b, maximum):
    # The existing two-factor order check may request an exact retry. Its final
    # evaluation replaces the tentative result on the same native input.
    keyed = [{(r[0], r[2]): r for r in events} for events in (a, b)]
    if list(keyed[0]) != list(keyed[1]):
        raise ValueError("Verifier scouts or evaluation order changed")
    for first, second in zip(*[m.values() for m in keyed], strict=True):
        if first[:5] != second[:5]:
            raise ValueError("Native verifier flags, fractional epoch or residual CFO changed")
        for key, x, y in zip(("verified_exact", "verified_rolled"), first[5:], second[5:], strict=True):
            delta = abs(x-y)
            if delta > 1e-8:
                raise ValueError("Verifier score exceeds the frozen tolerance")
            maximum[key] = max(maximum[key], delta)


def weak_rows():
    ref.verified(WEAK, ref.WEAK_PIN)
    schedule = ref.StereoSchedule(full_coverage=True)
    rows = []
    for index, (metadata, samples) in enumerate(read_archive(WEAK, 18)):
        w = ref.window(metadata, samples)
        # The archive clips are independent. Group only the saved capture
        # cases and keep the released cadence within each case.
        case = metadata["case"]
        if index == 0 or case != last:
            schedule = ref.StereoSchedule(full_coverage=True)
        last = case
        _, mode = schedule.visit(w.target["edge"], w.target, w.acquisition)
        for lane in (0, 1):
            rows.append(dict(key=index, iq=samples, lane=lane, mode=mode, edge=w.target["edge"], tune=ref.center(w),
                             short=None, stock=None))
    return rows, dict(archive_sha256=ref.WEAK_PIN, visits=18)


def compare(rows, receivers, pristine, tails):
    details, paired, timings, maxima = [], [], {}, Counter()
    counts = Counter()
    for order in ORDER:
        round_rows = {}
        for arm in order:
            total = Counter()
            outputs = []
            began = ref.clock()
            for row in rows:
                edge, lane, tune, iq = (row[k] for k in ("edge", "lane", "tune", "iq"))
                mode = "full" if row["mode"] == "full" else "short"
                engine = receivers[arm, edge, mode]
                factors, clock = engine.run(iq, lane, tune)
                events, stage = audit(engine)
                total.update(native_cpu_ns=clock[0], native_wall_ns=clock[1], attempted=stage[0], accepted=stage[1])
                total[mode+"_cpu_ns"] += clock[0]
                kept = ref.ordered(factors) if mode == "full" else factors
                ticks = ref.clock()
                diag, flag, adjusted, alias_retry = None, "anchor", kept, False
                if mode == "short":
                    context = receivers[arm, edge, "full"]
                    diag = tails[arm].diagnostics(context, iq, lane, kept)
                    if arm == "anchored" and diag is not None and kept:
                        cfo = kept[0][3]+diag[0]
                        if abs(abs(cfo-tune)-800_000) < .001:
                            alias_retry = True
                            diag = tails["stock"].diagnostics(context, iq, lane, kept)
                    adjusted, flag = ref.amend(kept, diag, 1.0, tune)
                tail_clock = ref.since(ticks)
                total.update(tail_cpu_ns=tail_clock[0], tail_wall_ns=tail_clock[1], tail_alias_retries=alias_retry)
                outputs.append((factors, events, stage, adjusted, flag, diag))
            total["batch_cpu_ns"], total["batch_wall_ns"] = ref.since(began)
            round_rows[arm] = outputs
            if arm == "anchored":
                total["tail_exact_retries"] = tails[arm].library.anchored_take_tail_retries()
            timings[arm] = dict(total)
        paired.append(dict(order=order, arms=dict(timings)))
        for row, a, b in zip(rows, round_rows["stock"], round_rows["anchored"], strict=True):
            continuous_control(a[0], b[0], maxima, 1e-8)
            audited_flags(a[1], b[1], maxima)
            if a[4] != b[4] or len(a[3]) != len(b[3]):
                raise ValueError("The independent CFO rule or retained membership changed")
            for x, y in zip(a[3], b[3], strict=True):
                if x[:3] != y[:3]:
                    raise ValueError("The tail changed rank or timing")
                maxima["tail_hz"] = max(maxima["tail_hz"], abs(x[3]-y[3]))
                if maxima["tail_hz"] > .001:
                    raise ValueError("Tail error exceeds the frozen 1 mHz allowance")
            if (a[5] is None) != (b[5] is None):
                raise ValueError("The independent CFO diagnostic changed availability")
            if a[5] is not None:
                differences = [abs(x-y) for x, y in zip(a[5], b[5], strict=True)]
                if max(differences[:3]) > .001 or max(differences[3:]) > 1e-7:
                    raise ValueError("The independent continuous diagnostics exceed their frozen tolerance")
                maxima["diagnostic_hz"] = max(maxima["diagnostic_hz"], max(differences[:3]))
                maxima["diagnostic_score"] = max(maxima["diagnostic_score"], max(differences[3:]))
            if len(paired) == 1:
                mode = "full" if row["mode"] == "full" else "short"
                stock, _ = pristine[row["edge"], mode].run(row["iq"], row["lane"], row["tune"])
                if ref.factor_bytes(stock) != ref.factor_bytes(a[0]):
                    raise ValueError("Instrumented stock does not reproduce the pinned binary")
                if row["short"] is not None:
                    selected = ref.ordered(stock) if mode == "full" else stock
                    if ref.factor_bytes(selected) != ref.factor_bytes(row["short"]):
                        raise ValueError("Stock factors differ from the signed archived packet")
                counts.update(lanes=1, short_lanes=mode == "short", full_lanes=mode == "full", factors=len(a[0]),
                              native_rank1=sum(x[0] == 1 for x in a[0]), updates=a[4] == "updated", flags=len(a[1]))
                details.append(dict(visit=row["key"], edge=row["edge"], lane=row["lane"], mode=mode,
                                    exact=a, anchored=b))
    return dict(paired=paired, maxima=dict(maxima), counts=dict(counts), signed=details)


def guard_controls(path, tails):
    lib = path.native.lib
    score = lib.anchored_guard_fixture
    score.argtypes, score.restype = (ct.c_double,) * 6, ct.c_int
    cases = [(0.3, 0.025, 0.02, 0.02, 1e-9, 1e-9), (0.2, 0.175, 0.01, 0.01, 1e-9, 1e-9),
             (0.205, 0.105, 0.01, 0.01, 1e-9, 1e-9), (0.3, 0.025, 1.9e-9, 0.01, 1e-9, 1e-9)]
    if [score(*case) for case in cases] != [1, 0, 0, 0]:
        raise ValueError("Near gate, strong margin or bin ties did not fall back")
    zeros = np.zeros((200_000, 2, 2), dtype=np.int16)
    zero = lib.anchored_zero_probe
    zero.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_uint, ct.POINTER(ct.c_double), ct.POINTER(ct.c_double), ct.POINTER(ct.c_uint))
    zero.restype = ct.c_int
    a, b, flags = (ct.c_double*3)(), (ct.c_double*3)(), (ct.c_uint*2)()
    w = ct.cast(path.native.ctx, ct.POINTER(ct.c_void_p))[1]
    if zero(w, zeros.ctypes.data, 0, a, b, flags) or bytes(a) != bytes(b) or flags[0] != flags[1] or audit(path)[1] != (1, 0):
        raise ValueError("A zero-energy trial did not use the original exact verifier")
    guard = tails["anchored"].library.anchored_tail_guard_fixture
    guard.argtypes, guard.restype = (ct.POINTER(ct.c_double),), ct.c_int
    baseline = [100., 100., 100., .95, .95, .4, .1, 5.]
    outcomes = []
    for field, near in [(0, 250.), (2, 500.), (3, .7), (5, .125)]:
        changed = baseline.copy()
        changed[field] = near
        outcomes.append(guard((ct.c_double*8)(*changed)))
    if guard((ct.c_double*8)(*baseline)) or outcomes != [1]*4:
        raise ValueError("Tail decision collars did not require exact work")
    return dict(verified_guard_cases=4, tail_guard_cases=4, real_zero_exact_retry=True)


@contextmanager
def engines(binaries, native_tail):
    ref.verified(EXACT_GATHER, GATHER_PIN)
    tails = {"stock": exact.RefineEntry(EXACT_GATHER, "short_cfo_gather"),
             "anchored": exact.RefineEntry(native_tail, "short_cfo_reanchored")}
    tails["anchored"].library.anchored_take_tail_retries.restype = ct.c_uint64
    with ExitStack() as stack:
        receivers, pristine = {}, {}
        for edge, pin in ref.PILOT_SHA.items():
            asset = np.frombuffer(ref.verified(ref.RELEASE / "assets" / (edge+".f32"), pin), dtype="<f4")
            for mode, original in (("full", ref.PAYLOAD / "receiver.so"), ("short", ref.ORIGINAL / "short-primary.so")):
                scope = "short_primary" if mode == "short" else "full"
                baseline = pristine[edge, mode] = ref.NativePath(original, asset, scope)
                stack.callback(baseline.close)
                for arm in ARMS:
                    path = receivers[arm, edge, mode] = ref.NativePath(binaries[arm, mode], asset, scope)
                    stack.callback(path.close)
        yield receivers, pristine, tails


def main(root):
    machine = ref.check_machine()
    root.mkdir()
    start = ref.clock()
    binaries, native_tail, builds = build(root)
    builds["setup_cpu_wall_ns"] = ref.since(start)
    panels = {}
    with engines(binaries, native_tail) as (receivers, pristine, tails):
        controls = guard_controls(receivers["anchored", "lower", "full"], tails)
        for name in ("dense", "weak", "held-0169"):
            before = ref.input_bytes()
            rows, scope = weak_rows() if name == "weak" else ref.signed_rows(name)
            if ref.input_bytes() != before:
                raise ValueError("A receiver waveform intake touched block storage")
            panels[name] = compare(rows, receivers, pristine, tails) | {"scope": scope}
            del rows
    ref.save(root / "receipt.json", dict(machine=machine, builds=builds, controls=controls, panels=panels,
                                         maximum_score_delta=1e-8, maximum_independent_hz_delta=.001))


def weak_primary(output, original):
    machine = ref.check_machine()
    prior = json.loads(ref.verified(original / "receipt.json", SCHEDULED_RECEIPT_PIN))
    commands = prior["builds"]
    binaries = {(arm, mode): original / f"{mode}-{arm}" / "receiver.so"
                for arm in ARMS for mode in ("full", "short")}
    for identity, path in binaries.items():
        ref.verified(path, commands["receivers"]["/".join(identity)])
    native_tail = original / "tail/tail.so"
    ref.verified(native_tail, commands["tail"]["binary_sha256"])
    with engines(binaries, native_tail) as (receivers, pristine, tails):
        before = ref.input_bytes()
        rows, scope = weak_rows()
        if ref.input_bytes() != before:
            raise ValueError("The weak primary fixture must remain in tmpfs")
        panel = compare([dict(row, mode="short_primary") for row in rows], receivers, pristine, tails)
    ref.save(output, dict(machine=machine, scope=scope, scheduled_receipt_sha256=SCHEDULED_RECEIPT_PIN,
                          panel=panel))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--weak-primary-from", type=Path)
    args = parser.parse_args()
    if args.root.resolve().parent != Path("/dev/shm"):
        parser.error("use a fresh tmpfs result directory")
    if args.weak_primary_from:
        weak_primary(args.root, args.weak_primary_from)
    else:
        main(args.root)
