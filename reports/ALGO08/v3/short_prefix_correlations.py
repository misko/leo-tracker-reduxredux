"""Check whether released short-primary rows can replace exact CFO prefix work."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import gzip
from hashlib import sha256
import json
from math import floor, isfinite
from pathlib import Path

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from . import short_cfo_exact_cost as exact
from . import short_cfo_refine as ref
from .centered_primary import BUILD_PIN
from .directed_verifier_trial import replace_once
from .mixed_aperture_trial import center, window


WEAK = Path("/dev/shm/leo-v3-short-cfo-dev02/weak-clips.zip")
SHORT_SOURCE = Path("/var/tmp/leo-short-signed-02/short/portable_verifier.c")
SHORT_SOURCE_PIN = "4cceaa68fe8d7f93608d1d07f585e2bc5c68955a22619d989052d6cde2e70def"
PANELS = ("dense", "weak", "held-0169")
PREFIX, FRAME_TAPS, SYMBOL_TAPS, FIRST, LIMIT = 8, 64*44, 44, 88, 120_000
RATE = 10_000_000


def frame_geometry(epoch, offset):
    integer = abs(offset-round(offset)) <= 1e-12
    starts, groups, supports = [], [], []
    for frame in range(15):
        start = epoch + (40_000*frame+1)//3
        lo = floor(start+FIRST+offset)-(0 if integer else 7)
        hi = floor(start+FIRST+FRAME_TAPS-1+offset)+(0 if integer else 8)
        if lo < 0 or hi >= 200_000:
            break
        starts.append(start)
        groups.append(0 if hi < LIMIT else 1 if lo >= LIMIT else -1)
        supports.append(hi-lo+1)
    if len(starts) < PREFIX or groups[:PREFIX] != [0]*PREFIX:
        raise ValueError("Original aperture does not contain the inspected eight frames")
    return np.array(starts), np.array(groups, dtype=np.intc), np.array(supports)


def extension(work):
    body = ref.verified(exact.SOURCE, exact.SOURCE_PIN).decode()
    prefix, main = body.split(exact.BODY_MARK, maxsplit=1)
    gather = (ref.HERE/"short_cfo_exact_cost.inc").read_text().split("/* Preserve the multiply/divide", maxsplit=1)[0]
    main = replace_once(exact.BODY_MARK + main, exact.LOAD, exact.GATHER)
    begin = main.index("    DelayProduct all")
    post = main[begin:]
    row = "const GlrtComplex *row = w->correlations[0] + 64*f;"
    post = replace_once(post, row, "const GlrtComplex *row = input + 64*f;")
    post = replace_once(post, "w->correlations[1] + 64*f", "input + 64*(frames+f)")
    reducer = "int short_prefix_score(const GlrtComplex *input, int frames, const int *group, double out[8]) {\n"+post
    path = work/"rows.inc"
    path.write_text(prefix + gather + main + (ref.HERE/"short_prefix_rows.inc").read_text() + reducer)
    return ref.build(work/"build", ref.PAYLOAD/"receiver.so", path)


class Scout(ct.Structure):
    _fields_ = [("epoch", ct.c_double), ("hz", ct.c_double), ("score", ct.c_double), ("confirmation", ct.c_int)]


def signature(lib, name, args, result):
    function = getattr(lib, name)
    function.argtypes = args
    function.restype = result
    return function


class Audit(exact.RefineEntry):
    def __init__(self, binary):
        super().__init__(binary, "short_cfo_refine")
        self.copy = signature(self.library, "short_prefix_rows", (ct.c_void_p, ct.c_int,
                              ct.POINTER(ct.c_double), ct.c_void_p), ct.c_int)
        self.score = signature(self.library, "short_prefix_score", (ct.c_void_p, ct.c_int,
                               ct.c_void_p, ct.POINTER(ct.c_double)), ct.c_int)
        self.size = signature(self.library, "portable_verifier_workspace_bytes", (), ct.c_size_t)()

    @staticmethod
    def context(path, index):
        return ct.cast(path.native.ctx, ct.POINTER(ct.c_void_p))[index]

    def rows(self, path, frames):
        out = np.empty((2, frames, 64), dtype=np.complex128)
        state = (ct.c_double*2)()
        size = signature(path.native.lib, "portable_verifier_workspace_bytes", (), ct.c_size_t)()
        if size != self.size or self.copy(self.context(path, 1), frames, state, out.ctypes.data):
            raise ValueError("Verifier workspace or row extent differs from the reviewed layout")
        return out, tuple(state)

    def diagnostics_from_rows(self, rows, groups):
        frames = len(groups)
        data = np.ascontiguousarray(rows, dtype=np.complex128)
        out = (ct.c_double*8)()
        if self.score(data.ctypes.data, frames, groups.ctypes.data, out):
            raise ValueError("Could not evaluate the original frozen reduction over saved rows")
        return tuple(out)

    def scout(self, row, path):
        fn = signature(path.native.lib, "timing_first_detect",
                       (ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.POINTER(Scout)), ct.c_int)
        out = Scout()
        if fn(self.context(path, 0), row["iq"].ctypes.data, row["lane"],
              row["tune"]-800_000, row["tune"]+800_000, ct.byref(out)) or not out.confirmation:
            raise ValueError("Actual short scout could not reproduce an accepted primary's seed")
        return out


def panel(name):
    if name != "weak":
        return ref.signed_rows(name)
    ref.verified(WEAK, ref.WEAK_PIN)
    rows = []
    for metadata, samples in read_archive(WEAK, 18):
        visit = window(metadata, samples)
        for lane in (0, 1):
            rows.append(dict(key=metadata["key"], edge=metadata["edge"], lane=lane, iq=samples,
                             tune=center(visit), mode="short_primary", short=None))
    if len(rows) != 36:
        raise ValueError("Expected the complete prior staged weak stereo fixture")
    return rows, dict(staged_zip=str(WEAK), sha256=ref.WEAK_PIN, bytes=WEAK.stat().st_size)


def same_bytes_by_frame(left, right):
    return [left[:, f].tobytes() == right[:, f].tobytes() for f in range(PREFIX)]


def normalized_rms(a, b):
    return float(np.linalg.norm(a-b)/max(np.linalg.norm(b), np.finfo(float).tiny))


def audit_lane(row, expected, receiver, diagnostic):
    pilot, full = (receiver[row["edge"], mode] for mode in ("short_primary", "full"))
    iq, lane, tune = (row[key] for key in ("iq", "lane", "tune"))
    short, _ = pilot.run(iq, lane, tune)
    if ref.factor_bytes(short) != ref.factor_bytes(expected["short"]):
        raise ValueError("The untouched short DSO does not reproduce the sealed factor")
    if not short:
        return None
    original, = short
    epoch, offset, reported = original[1:4]
    starts, groups, sizes = frame_geometry(epoch, offset)
    prefix, (integer_seed, radius) = diagnostic.rows(pilot, PREFIX)
    scout = diagnostic.scout(row, pilot)
    if round(scout.epoch) % 13_333 != epoch or isfinite(integer_seed) and integer_seed != scout.hz:
        raise ValueError("Retained verifier state differs from the reproduced original short scout")
    original_diag = diagnostic.diagnostics(full, iq, lane, short)
    all_rows, _ = diagnostic.rows(full, len(starts))
    exact_prefix = all_rows[:, :PREFIX]
    exact_result, exact_flag = ref.amend(short, original_diag, 1., tune)
    frozen, frozen_flag = expected["choices"]["1.0"]
    if (exact.diag_bytes(original_diag) != exact.diag_bytes(expected["diagnostics"])
            or ref.factor_bytes(exact_result) != ref.factor_bytes(frozen) or exact_flag != frozen_flag
            or exact.diag_bytes(original_diag) != exact.diag_bytes(diagnostic.diagnostics_from_rows(all_rows, groups))):
        raise ValueError("Independent exact-gather rows and diagnostics differ from the frozen reference")

    seed, delta = scout.hz, reported-scout.hz
    seed_factor = (original[:3]+(seed,)+original[4:],)
    diagnostic.diagnostics(full, iq, lane, seed_factor)
    seed_rows, _ = diagnostic.rows(full, len(starts))
    seed_rows = seed_rows[:, :PREFIX]
    phasefree = radius > 0
    origin_phase = np.exp(-2j*np.pi*seed*starts[:PREFIX]/RATE) if phasefree else np.ones(PREFIX)
    symbol = FIRST + offset + (np.arange(64)+.5)*SYMBOL_TAPS-.5
    adjustment = np.exp(-2j*np.pi*delta*(starts[:PREFIX,None]+symbol)/RATE)
    corrected = prefix*origin_phase[None,:,None]*adjustment[None,:,:]
    trial = all_rows.copy()
    trial[:, :PREFIX] = corrected
    estimate = diagnostic.diagnostics_from_rows(trial, groups)
    changed, flag = ref.amend(short, estimate, 1., tune)
    same_frequency = seed == reported
    exact_seed = same_bytes_by_frame(prefix, seed_rows)
    same_cfo_row = same_bytes_by_frame(prefix, exact_prefix)
    return dict(key=row["key"], lane=lane, edge=row["edge"], epoch=epoch, offset=offset, seed=seed, reported=reported,
                delta=delta, phase_free=phasefree, integer=abs(offset-round(offset)) <= 1e-12,
                framed_groups=groups.tolist(), original_prefix_support=int(sizes[:PREFIX].sum()),
                total_support=int(sizes.sum()), same_frequency=same_frequency,
                exact_prefix_at_seed=exact_seed, exact_prefix_at_reported=same_cfo_row,
                eligible_bitwise_prefix=same_frequency and not phasefree and all(same_cfo_row),
                seed_rephased_relative_rms=normalized_rms(prefix*origin_phase[None,:,None], seed_rows),
                adjusted_relative_rms=normalized_rms(corrected, exact_prefix),
                exact_diag=original_diag, adjusted_diag=estimate, exact_flag=exact_flag, adjusted_flag=flag,
                exact_emitted_cfo=exact_result[0][3], adjusted_emitted_cfo=changed[0][3],
                bitwise_diagnostics=exact.diag_bytes(original_diag) == exact.diag_bytes(estimate),
                bitwise_emitted=ref.factor_bytes(exact_result) == ref.factor_bytes(changed))


def summary(rows):
    c = Counter(delta_bins=0, reused_rows=0, prefix_rows=0, original_rows=0, replaced_support=0, original_support=0)
    for row in rows:
        for key in ("same_frequency", "phase_free", "integer", "eligible_bitwise_prefix", "bitwise_diagnostics",
                    "bitwise_emitted"):
            c[key] += int(row[key])
        c["delta_bins"] += int(not row["same_frequency"])
        c["reused_rows"] += sum(row["exact_prefix_at_reported"])
        c["prefix_rows"] += PREFIX
        c["original_rows"] += len(row["framed_groups"])
        c["replaced_support"] += row["original_prefix_support"]
        c["original_support"] += row["total_support"]
        c["extra_old_or_crossing"] += int(row["framed_groups"][PREFIX] in (-1, 0))
        c["changed_gate"] += int(row["exact_flag"] != row["adjusted_flag"])
    return dict(positives=len(rows), **c)


def run(work):
    machine = ref.check_machine()
    if work.resolve().parent != Path("/dev/shm"):
        raise ValueError("Use a private tmpfs output root")
    ref.verified(ref.PAYLOAD/"receiver.so", ref.INSTALLED_SHA)
    ref.verified(ref.ORIGINAL/"short-primary.so", ref.PREFIX_PIN)
    ref.verified(ref.ORIGINAL/"build-receipt.json", BUILD_PIN)
    ref.verified(SHORT_SOURCE, SHORT_SOURCE_PIN)
    evidence = json.loads(gzip.decompress(ref.verified(exact.EVIDENCE, exact.EVIDENCE_PIN)))
    work.mkdir()
    start = ref.clock()
    binary, build = extension(work)
    setup = ref.since(start)
    diagnostic = Audit(binary)
    results = {}
    with ExitStack() as scope:
        receiver = {}
        for edge, pin in ref.PILOT_SHA.items():
            asset = np.frombuffer(ref.verified(ref.RELEASE/"assets"/f"{edge}.f32", pin), dtype="<f4")
            for mode in ("short_primary", "full"):
                lib = ref.ORIGINAL/"short-primary.so" if mode == "short_primary" else ref.PAYLOAD/"receiver.so"
                receiver[edge, mode] = ref.NativePath(lib, asset, mode)
                scope.callback(receiver[edge, mode].close)
        for name in PANELS:
            current = evidence["held" if name.startswith("held") else "development"]["panels"][name]
            expected = {(r["key"], r["lane"]): r for r in current["rows"]}
            blocks = ref.input_bytes()
            rows, sources = panel(name)
            if ref.input_bytes() != blocks:
                raise ValueError("Only resident staged waveform inputs may be opened")
            measured = []
            for row in rows:
                if row["mode"] == "short_primary":
                    key = row["key"], row["lane"]
                    result = audit_lane(row, expected.pop(key), receiver, diagnostic)
                    if result:
                        measured.append(result)
            if expected:
                raise ValueError("Staged rows differ from the frozen positive and empty denominator")
            results[name] = dict(sources=sources, rows=measured, opportunities=sum(r["mode"] == "short_primary" for r in rows),
                                 original_stage_evidence_sha256=exact.EVIDENCE_PIN, summary=summary(measured))
    ref.save(work/"result.json", dict(machine=machine, results=results, build=build, build_ns=setup,
             source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), short_source_sha256=SHORT_SOURCE_PIN,
             short_library_sha256=ref.PREFIX_PIN, independent_definition_sha256=exact.SOURCE_PIN))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)
