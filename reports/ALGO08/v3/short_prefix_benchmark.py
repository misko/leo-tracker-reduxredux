"""Compare guarded exact reuse with independent gather on the enrolled saved lanes."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import numpy as np

from . import short_prefix_correlations as audit
from . import short_cfo_refine as ref
from .centered_primary import RELEASE_BUILD, RELEASE_PIN
from .directed_verifier_trial import replace_once


ORDERS = (("independent", "reuse"), ("reuse", "independent")) * 3
ORACLE_PIN = "2c68098355f351be54c4892c2e7688028e85f9933e95f12f381e0c097c5b7dd9"
ORACLE = Path("/dev/shm/leo-v3-prefix-correlations-results-01/result.json")


def build_full(work):
    # The dated, verified verifier and exact gather source are built as before.
    implementation = work/"prepared"
    implementation.mkdir()
    audit.extension(implementation)
    extension = (implementation/"rows.inc").read_text()
    fractional = ref.verified(audit.exact.FRACTIONAL, audit.exact.FRACTIONAL_PIN).decode()
    shifted = replace_once(fractional, "absolute_fractional_correlations", "absolute_fractional_tail")
    for pilot in range(2):
        shifted = replace_once(shifted, f"w->correlations[{pilot}] + frame * 64",
                               f"w->correlations[{pilot}] + (frame + 8) * 64")
    at = extension.index("int short_prefix_score(")
    score = replace_once(extension[at:], "int short_prefix_score(const GlrtComplex *input,",
                        "static int score_parts(const GlrtComplex *exact_rows, const GlrtComplex *control_rows,")
    score = replace_once(score, "input + 64*f", "exact_rows + 64*f")
    score = replace_once(score, "input + 64*(frames+f)", "control_rows + 64*f")
    body = ref.HERE/"short_prefix_refine.inc"
    source = work/"extension.inc"
    source.write_text(extension + shifted + score + body.read_text())
    return ref.build(work/"full", ref.PAYLOAD/"receiver.so", source)


def build_primary(work):
    source = ref.ORIGINAL/"two_carrier_receiver.c"
    archive = json.loads(ref.verified(ref.ORIGINAL/"build-receipt.json", audit.BUILD_PIN))
    build = json.loads(ref.verified(RELEASE_BUILD, RELEASE_PIN))
    original = ref.verified(source, archive["source_wrapper_sha256"]).decode()
    old_object = archive["compile"][-1]
    for f in archive["relink"]:
        if f.endswith(".o"):
            ref.verified(f, archive["short_object_sha256"][Path(f).name])
    at = original.index("int cancellation_primary_factors(")
    method = original[at:]
    method = replace_once(method, "cancellation_primary_factors", "short_primary_and_cfo")
    method = replace_once(method, "ScanFactor out[2])",
                          "ScanFactor out[2], PortableVerifier *whole, PrefixFinish finish, double diagnostic[8], "
                          "int *used, uint64_t *cpu)")
    method = replace_once(method, "    return verify_peaks(r, scouts, peaks, out, 1);", """    const int count = verify_peaks(r, scouts, peaks, out, 1);
    if (count != 1 || !whole || !finish) return count;
    const uint64_t started = cfo_stage_clock();
    const int status = finish(whole, r->verify, iq, (unsigned)lane, (unsigned)out[0].integer,
                              out[0].offset, scouts[0].hz, out[0].hz, diagnostic, used);
    *cpu = cfo_stage_clock() - started;
    if (status) *used = -1;
    return count;""")
    callback = """typedef int (*PrefixFinish)(PortableVerifier *, const PortableVerifier *, const int16_t *,
                            unsigned, unsigned, double, double, double, double *, int *);
"""
    source, obj, binary = (work/f"prefix-primary.{suffix}" for suffix in ("c", "o", "so"))
    source.write_text(original + audit.exact.CPU_CLOCK + callback + method)
    compile_ = [*archive["compile"][:-4], "-c", str(source), "-o", str(obj)]
    link = [str(obj) if p == old_object else p for p in archive["relink"][:-1]] + [str(binary)]
    for cmd in (compile_, link):
        subprocess.run(cmd, cwd=build["cwd"], check=True)
    return binary, dict(commands=[compile_, link], source_sha256=sha256(source.read_bytes()).hexdigest(),
                        binary_sha256=sha256(binary.read_bytes()).hexdigest())


class Primary:
    def __init__(self, short, full, asset, callback):
        self.detector = ref.NativePath(short, asset, "short_primary")
        self.full = ref.NativePath(ref.PAYLOAD/"receiver.so", asset, "full")
        self.workspace = audit.Audit.context(self.full, 1)
        self.callback = ct.cast(getattr(full, "short_cfo_"+callback), ct.c_void_p)
        self.invoke = audit.signature(self.detector.native.lib, "short_primary_and_cfo",
            (ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.c_void_p, ct.c_void_p, ct.c_void_p,
             ct.POINTER(ct.c_double), ct.POINTER(ct.c_int), ct.POINTER(ct.c_uint64)), ct.c_int)

    def close(self):
        self.detector.close()
        self.full.close()

    def measure(self, row):
        records = (self.detector.factor*2)()
        diag, used, cost = (ct.c_double*8)(), ct.c_int(), ct.c_uint64()
        clock = ref.clock()
        status = self.invoke(self.detector.native.ctx, row["iq"].ctypes.data, row["lane"],
                             row["tune"]-800_000, row["tune"]+800_000, records, self.workspace,
                             self.callback, diag, ct.byref(used), ct.byref(cost))
        if status not in (0, 1):
            raise ValueError("Pinned signed short and refinement callback failed")
        factors = tuple(tuple(getattr(r, k) for k,_ in self.detector.factor._fields_) for r in records[:status])
        diagnostics = tuple(diag) if factors and used.value >= 0 else None
        updated, flag = ref.amend(factors, diagnostics, 1., row["tune"])
        times = ref.since(clock)
        return (ref.factor_bytes(factors), audit.exact.diag_bytes(diagnostics), ref.factor_bytes(updated), flag), (
            cost.value, times[0], times[1], used.value)


def run(work):
    machine = ref.check_machine()
    if work.resolve().parent != Path("/dev/shm"):
        raise ValueError("Require a fresh tmpfs output directory")
    oracle = ref.load(ORACLE, ORACLE_PIN)
    frozen = json.loads(gzip.decompress(ref.verified(audit.exact.EVIDENCE, audit.exact.EVIDENCE_PIN)))
    work.mkdir()
    started = ref.clock()
    full, full_build = build_full(work)
    short, short_build = build_primary(work)
    build_time = ref.since(started)
    library = ct.CDLL(str(full))
    results = {}
    with ExitStack() as scope:
        paths = {}
        for arm in ORDERS[0]:
            for edge, pin in ref.PILOT_SHA.items():
                asset = np.frombuffer(ref.verified(ref.RELEASE/"assets"/f"{edge}.f32", pin), dtype="<f4")
                paths[arm, edge] = Primary(short, library, asset, arm)
                scope.callback(paths[arm, edge].close)
        for name in audit.PANELS:
            blocks = ref.input_bytes()
            staged, input_sources = audit.panel(name)
            if ref.input_bytes() != blocks:
                raise ValueError("Expect already staged, resident signed inputs")
            rows = [r for r in staged if r["mode"] == "short_primary"]
            signed = frozen["held" if name.startswith("held") else "development"]["panels"][name]
            norms = {(r["key"], r["lane"]): r for r in signed["rows"]}
            can_reuse = {(r["key"], r["lane"]): r["eligible_bitwise_prefix"]
                         for r in oracle["results"][name]["rows"]}
            expected = {}
            times = []
            for order in ORDERS:
                pair = {}
                for arm in order:
                    totals = Counter()
                    for row in rows:
                        key = row["key"], row["lane"]
                        value, cost = paths[arm, row["edge"]].measure(row)
                        wanted = norms[key]
                        choice, flag = wanted["choices"]["1.0"]
                        reference = (ref.factor_bytes(wanted["short"]), audit.exact.diag_bytes(wanted["diagnostics"]),
                                     ref.factor_bytes(choice), flag)
                        prior = expected.setdefault(key, value)
                        desired = can_reuse.get(key, False) and arm == "reuse"
                        if value != prior or value != reference or cost[3] != (8 if desired else 0):
                            raise ValueError(f"Signed receiver, exact refinement or reuse decision changed at {key}")
                        totals.update(refinement_cpu_ns=cost[0], signed_lane_cpu_ns=cost[1],
                                      signed_lane_wall_ns=cost[2], reused_frames=cost[3],
                                      independent_fallbacks=int(arm == "reuse" and bool(wanted["short"]) and not desired))
                    pair[arm] = dict(totals)
                times.append(dict(order=order, arms=pair))
            results[name] = dict(sources=input_sources, positives=len(can_reuse), opportunities=len(rows),
                                 paired=times, exact_frozen_outputs_equal=True)
    ref.save(work/"result.json", dict(machine=machine, original_census_sha256=ORACLE_PIN, build_time_ns=build_time,
          short_build=short_build, full_build=full_build, results=results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)
