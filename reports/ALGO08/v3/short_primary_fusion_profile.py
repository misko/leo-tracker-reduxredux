"""Profile disjoint stages and causal pilot overlap in the guarded short primary."""

import argparse
from collections import Counter
from contextlib import ExitStack, closing
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean, median
import subprocess

from .anchored_phase import STENCIL_PIN, audit
from .dense_geographic_trial import host
from .mixed_aperture_receiver import NativePath, verified
from .short_cfo_refine import signed_rows
from .timing_only_oracle import asset_for, one
from .whole_group_receiver_bound import FULL_BUILD, FULL_BUILD_SHA, SHORT_BUILD, SHORT_BUILD_SHA, SOURCE_SHA


HERE = Path(__file__).resolve().parent
ASSETS = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/assets")
PACK = Path("/dev/shm/leo-anchored-cfo-raw-pack01/short.so")
PACK_PIN = "f20605e5a4e487d13548411b0430ea262b9b9c6fba89dae973313d3d0008bb6a"
GUARDED = Path("/dev/shm/leo-anchored-phase-results02/short-anchored")
GUARDED_C = "2442d86271d6aa55729a49156a46d02b50554fdaa24ba9e769d2ed72a1c88435"
GUARDED_O = "68c8e294db5e6bfa6c6abf7e9d6cc9c65c8cd6fe1d9ef211fa685c81f8255e21"
WRAPPER_PIN = "6f21e36a55caa489f5992a3fbae6006c2af549c30753b7053fae926d0cefb48e"
STAGES = ("input_mix", "fir", "frame_modes", "lag_timing", "carrier_grid", "seed_preparation", "full_rate_bank",
          "pilot_confirm", "verifier_load", "integer_stencil", "fractional_vertex", "fractional_correlations",
          "fractional_spectrum_guard", "residual_readout")
ARMS = ("pack", "rebuilt", "trace")
ORDER = (ARMS, ARMS[::-1], ("rebuilt", "pack", "trace"), ("trace", "pack", "rebuilt")) * 2


class ShortTrace(ct.Structure):
    _fields_ = [("ns", ct.c_uint64 * len(STAGES)), ("total", ct.c_uint64), ("attempts", ct.c_int * 3),
                ("gate_ns", ct.c_uint64 * 3)] + [
        (name, ct.c_int) for name in ("witness", "confirmed_epoch", "verifier_epoch", "requests",
                                    "residual_reads", "winner_request")
    ] + [("seed_epoch", ct.c_int * 16), ("seed_hz", ct.c_double * 16),
         ("confirmed_hz", ct.c_double), ("verifier_hz", ct.c_double)]

    def document(self):
        remainder = self.total - sum(self.ns)
        if self.requests < 0 or self.requests > len(self.seed_epoch) or remainder < 0 or sum(self.gate_ns) > self.ns[7]:
            raise ValueError("The 12 ms trace has inconsistent exclusive stage totals")
        return dict(ns=dict(zip(STAGES, self.ns, strict=True), other=remainder), total=self.total,
                    attempts=list(self.attempts), gate_ns=list(self.gate_ns), witness=self.witness,
                    confirmed_epoch=self.confirmed_epoch, confirmed_hz=self.confirmed_hz,
                    verifier_epoch=self.verifier_epoch, verifier_hz=self.verifier_hz, winner_request=self.winner_request,
                    bank=list(zip(self.seed_epoch[:self.requests], self.seed_hz[:self.requests], strict=True)),
                    residual_reads=self.residual_reads)


def timing_source(stock):
    entry = "static int detect_lane(TimingFirst *w"
    before, after = stock.split(entry, 1)
    before = one(before, "static int gate(TimingFirst *w,", "static int gate_support(TimingFirst *w,")
    gate = """
static int gate(TimingFirst *w, const Peak *p, int start_symbol, int early) {
    const int index = early ? 2 : start_symbol == 160 ? 0 : 1;
    ++sp_trace.attempts[index];
    uint64_t start = sp_now();
    int pass = gate_support(w, p, start_symbol, early);
    sp_trace.gate_ns[index] += sp_now() - start;
    if (pass) {
        sp_trace.witness = start_symbol;
        sp_trace.confirmed_epoch = p->sample;
        sp_trace.confirmed_hz = p->hz;
    }
    return pass;
}

"""
    replacements = (
        ("    if (!resident) input(w, iq, lane, center);", "    uint64_t tick = sp_now();\n"
         "    if (!resident) input(w, iq, lane, center);\n    tick = sp_mark(tick, sp_input);"),
        ("    principal_modes(w, low);", "    tick = sp_mark(tick, sp_fir);\n"
         "    principal_modes(w, low);\n    tick = sp_mark(tick, sp_modes);"),
        ("    find_times(w, epochs);", "    find_times(w, epochs);\n    tick = sp_mark(tick, sp_timing);"),
        ("    Peak peaks[max_peaks];", "    tick = sp_mark(tick, sp_carrier);\n    Peak peaks[max_peaks];"),
        ("    double v[max_peaks][4];", "    sp_trace.requests = done;\n"
         "    for (int i = 0; i < done; ++i) {\n        sp_trace.seed_epoch[i] = request[i].epoch;\n"
         "        sp_trace.seed_hz[i] = request[i].hz;\n    }\n"
         "    tick = sp_mark(tick, sp_prepare);\n    double v[max_peaks][4];"),
        ("    for (int k = 0; k < done; ++k)\n        peaks[k]", "    tick = sp_mark(tick, sp_refine);\n"
         "    for (int k = 0; k < done; ++k)\n        peaks[k]"),
        ("        if (why) {", "        if (why) {\n            sp_trace.winner_request = best;"),
        ("    return 0;\n}\n\nint timing_first_detect(", "    sp_mark(tick, sp_confirm);\n"
         "    return 0;\n}\n\nint timing_first_detect("),
    )
    for old, new in replacements:
        after = one(after, old, new)
    return before + gate + entry + after


def wrapper_source(stock):
    entry = "int cancellation_primary_factors("
    before, after = stock.split(entry, 1)
    bridge = """
_Thread_local ShortTrace sp_trace;

void short_primary_trace_read(ShortTrace *out) {
    memcpy(out, &sp_trace, sizeof(*out));
}

"""
    after = one(after, "    TimingFirstResult scouts", "    sp_trace = (ShortTrace){.witness = -1, .confirmed_epoch = -1,\n"
                "                            .verifier_epoch = -1, .winner_request = -1};\n"
                "    uint64_t start = sp_now();\n    TimingFirstResult scouts")
    after = one(after, "    if (!scouts[0].confirmation) return 0;", """    if (!scouts[0].confirmation) {
        sp_trace.total = sp_now() - start;
        return 0;
    }
    uint64_t tick = sp_now();""")
    after = one(after, "    TwoCarrierPeak peaks[2];\n    return verify_peaks(r, scouts, peaks, out, 1);", """    sp_mark(tick, sp_load);
    TwoCarrierPeak peaks[2];
    int count = verify_peaks(r, scouts, peaks, out, 1);
    sp_trace.total = sp_now() - start;
    return count;""")
    return before + bridge + entry + after


def verifier_source(stock):
    replacements = (
        ("    ++phase_count[0];\n    double weight_mass;", "    uint64_t tick = sp_now();\n"
         "    ++phase_count[0];\n    double weight_mass;"),
        ("    if (fegetround() != FE_TONEAREST || anchored_correlations(w, frames, starts, cfo, offset, &weight_mass))\n"
         "        return 0;", "    int invalid = fegetround() != FE_TONEAREST ||\n"
         "        anchored_correlations(w, frames, starts, cfo, offset, &weight_mass);\n"
         "    tick = sp_mark(tick, sp_frac_corr);\n    if (invalid) return 0;"),
        ("    if (!anchored_decision(exact, control, egap, cgap, er, cr)) return 0;",
         "    int allowed = anchored_decision(exact, control, egap, cgap, er, cr);\n"
         "    sp_mark(tick, sp_fractional_spectra);\n    if (!allowed) return 0;"),
        ("        !anchored_fractional(w, frames, starts, cfo, offset, exact, control, &best, flags)) {",
         "        !anchored_fractional(w, frames, starts, cfo, offset, exact, control, &best, flags)) {\n"
         "        uint64_t tick = residual && control ? sp_now() : 0;"),
        ("        int unused;\n        *exact = glrt_spectrum(", "        if (tick) tick = sp_mark(tick, sp_frac_corr);\n"
         "        int unused;\n        *exact = glrt_spectrum("),
        ("        if (control) *control = glrt_spectrum(w, w->correlations[1], frames, &unused, flags);",
         "        if (control) *control = glrt_spectrum(w, w->correlations[1], frames, &unused, flags);\n"
         "        if (tick) sp_mark(tick, sp_fractional_spectra);"),
        ("    double steps[max_frames * 63];", "    uint64_t tick = sp_now();\n"
         "    if (control) ++sp_trace.residual_reads;\n    double steps[max_frames * 63];"),
        ("    *residual = (best < 256 ? best : best-512) * (1.0/(glrt_size*median));",
         "    *residual = (best < 256 ? best : best-512) * (1.0/(glrt_size*median));\n"
         "    if (control) sp_mark(tick, sp_residual);"),
        ("    int first_epoch = diagnostics ? 0 :", "    sp_trace.verifier_epoch = (int)epoch;\n"
         "    sp_trace.verifier_hz = freq;\n    uint64_t tick = sp_now();\n    int first_epoch = diagnostics ? 0 :"),
        ("    if (diagnostics) {\n        out->integer_exact =", "    tick = sp_mark(tick, sp_integer);\n"
         "    if (diagnostics) {\n        out->integer_exact ="),
        ("    if (peak < 0) return -1;\n    if (peak) {", "    sp_mark(tick, sp_vertex);\n"
         "    if (peak < 0) return -1;\n    if (peak) {"),
    )
    for old, new in replacements:
        stock = one(stock, old, new)
    return stock


def build(root):
    full = json.loads(verified(FULL_BUILD, FULL_BUILD_SHA))
    available = json.loads(verified(SHORT_BUILD, SHORT_BUILD_SHA))["relink"]
    old = {Path(v).name: Path(v) for v in available if v.endswith(".o")}
    names = ("two_carrier_receiver", "timing_first_receiver", "portable_verifier")
    source_rows = ((old["two_carrier_receiver.o"].with_suffix(".c"), WRAPPER_PIN, wrapper_source),
                   (old["timing_first_receiver.o"].with_suffix(".c"), SOURCE_SHA["short"], timing_source),
                   (GUARDED / "verifier.c", GUARDED_C, verifier_source))
    sources = [(verified(path, pin).decode(), transform) for path, pin, transform in source_rows]
    obj = GUARDED / "portable_verifier.o"
    verified(obj, GUARDED_O)
    verified(PACK, PACK_PIN)
    flags = full["commands"][-2][:-4]
    commands = []

    def execute(command):
        commands.append(list(map(str, command)))
        subprocess.run(command, cwd=full["cwd"], check=True)

    native = {"pack": root / "packed-relink.so"}
    execute([*(obj if Path(x).name == "portable_verifier.o" else x for x in available[:-1]), native["pack"]])
    verified(native["pack"], PACK_PIN)
    for arm in ("rebuilt", "trace"):
        output = root / arm
        output.mkdir()
        stencil = GUARDED / "receiver_stencil_verify.inc"
        (output / stencil.name).write_bytes(verified(stencil, STENCIL_PIN))
        objects = {}
        for name, (text, transform) in zip(names, sources, strict=True):
            cfile, ofile = (output / name).with_suffix(".c"), (output / name).with_suffix(".o")
            cfile.write_text(transform(text) if arm == "trace" else text)
            trace_flags = ["-D_POSIX_C_SOURCE=200809L", "-include", HERE / "short_primary_trace.h"] if arm == "trace" else []
            execute([*flags, *trace_flags, "-c", cfile, "-o", ofile])
            objects[ofile.name] = ofile
        native[arm] = output / "receiver.so"
        execute([*(objects.get(Path(x).name, x) for x in available[:-1]), native[arm]])
    return native, dict(commands=commands, libraries={arm: sha256(path.read_bytes()).hexdigest() for arm, path in native.items()},
                        stock_sources={str(path): pin for path, pin, _ in source_rows})


def causal_overlap(trace):
    if trace["verifier_epoch"] < 0:
        if trace["witness"] >= 0:
            raise ValueError("Confirmed scout did not reach the original verifier")
        return dict(confirmed=False)
    witness = trace["witness"]
    if witness not in (0, 160, 232) or trace["confirmed_hz"] != trace["verifier_hz"]:
        raise ValueError("Verifier did not receive the actual confirmed scout seed")
    winner = trace["winner_request"]
    epoch, frequency = trace["bank"][winner]
    difference = (trace["verifier_epoch"] - epoch + 6666) % 13333 - 6666
    delta_hz = trace["verifier_hz"] - frequency
    return dict(confirmed=True, same_gate_center=trace["confirmed_epoch"] == trace["verifier_epoch"],
                witness=witness, bank_center_in_stencil=abs(difference) <= 6, bank_center_in_full_rate_grid=abs(difference) <= 4,
                same_bank_frequency=delta_hz == 0.0, bank_to_verify_delta_hz=delta_hz, bank_to_verify_delta_samples=difference)


def summarize(records):
    stats, clocks = {}, {}
    positive = [row for row in records if row["rounds"][0]["pack"]["factors"]]
    empty = [row for row in records if not row["rounds"][0]["pack"]["factors"]]
    for label, scope in (("all", records), ("positive", positive), ("empty", empty)):
        for arm in ARMS:
            clocks[f"{label}/{arm}"] = [sum(row["rounds"][i][arm]["clock"][0] for row in scope) for i in range(len(ORDER))]
        if not scope:
            continue
        traces = [{name: sum(row["rounds"][i]["trace"]["detail"]["ns"][name] for row in scope)
                   for name in (*STAGES, "other")} for i in range(len(ORDER))]
        medians = {name: median(values[name] for values in traces) / len(scope) for name in (*STAGES, "other")}
        overlaps = [row["overlap"] for row in scope]
        counts = Counter()
        for row, overlap in zip(scope, overlaps, strict=True):
            t = row["rounds"][0]["trace"]["detail"]
            counts.update(late_160_attempt=t["attempts"][0], late_232_attempt=t["attempts"][1], early_attempt=t["attempts"][2],
                          residual_readouts=t["residual_reads"], bank_requests=len(t["bank"]))
            if overlap["confirmed"]:
                counts.update(confirmed=1, **{f"witness_{overlap['witness']}": 1},
                              shared_early_coarse_center=overlap["witness"] == 0 and overlap["same_gate_center"],
                              same_bank_frequency=overlap["same_bank_frequency"],
                              same_bank_frequency_and_epoch_grid=overlap["same_bank_frequency"] and overlap["bank_center_in_full_rate_grid"])
        gate_savings = [sum(row["rounds"][i]["trace"]["detail"]["gate_ns"][2] for row in scope
                            if row["overlap"].get("witness") == 0 and row["overlap"]["same_gate_center"])
                        for i in range(len(ORDER))]
        stats[label] = dict(lanes=len(scope), stage_ns_per_lane=medians, stages_total_ns=traces, counts=counts,
                            optimistic_early_reuse_ns_per_lane=median(gate_savings)/len(scope),
                            complete_cpu_ns_per_lane={arm: median(clocks[f"{label}/{arm}"])/len(scope) for arm in ARMS})
    return dict(grouped=stats, whole_cpu_ns=clocks)


def projection(stats, positive, short_calls, native_cpu_s, candidate_elapsed, named_elapsed, candidate_cpu, named_cpu):
    groups = stats["grouped"]
    n = (positive, short_calls-positive)
    selected = [groups["positive"], groups["empty"]]
    parts = {name: sum(count * group["stage_ns_per_lane"][name] for count, group in zip(n, selected, strict=True))
             for name in (*STAGES, "other")}
    scale = native_cpu_s / sum(parts.values())
    costs = {name: value * scale for name, value in parts.items()}
    early = scale * sum(count * group["optimistic_early_reuse_ns_per_lane"] for count, group in zip(n, selected, strict=True))
    ceilings = {"same_support_early_confirmation": early, "all_early_and_late_confirmation": costs["pilot_confirm"],
                "all_full_rate_bank_and_confirmation": costs["full_rate_bank"] + costs["pilot_confirm"],
                "all_timing_and_carrier_grids": costs["lag_timing"]+costs["carrier_grid"], "entire_short_primary": native_cpu_s}
    return dict(positive=positive, short_calls=short_calls, native_cpu_s=native_cpu_s, attributed_s=costs,
                projections={scope: dict(cpu_saved=s, candidate_elapsed_floor=candidate_elapsed-s,
                    named_elapsed_speedup=named_elapsed/(candidate_elapsed-s), candidate_cpu_floor=candidate_cpu-s,
                    named_cpu_speedup=named_cpu/(candidate_cpu-s)) for scope, s in ceilings.items()})


def run(root):
    import anchored_cfo_stage as stage
    from continued_cfo_live_trial import resident

    machine = host()
    if root.absolute() != root.resolve() or not root.is_relative_to("/dev/shm"):
        raise ValueError("Use unoccupied tmpfs output for the bounded profile")
    root.mkdir()
    paths, compiled = build(root)
    cache_before = resident(stage)
    signed, receipt = signed_rows("held")
    rows = [row for row in signed if row["mode"] == "short_primary"]
    if len(signed) != 102 or len(rows) != 86 or len(receipt["iq"]) != 64:
        raise ValueError("Unexpected change in the original 0169 issued or signed aperture counts")
    records = [dict(visit=row["key"], lane=row["lane"], edge=row["edge"], center=row["tune"],
                    rounds=[{} for _ in ORDER]) for row in rows]
    with ExitStack() as resources:
        engines = {(arm, edge): resources.enter_context(closing(NativePath(path, asset_for(ASSETS, edge), "short_primary")))
                   for arm, path in paths.items() for edge in sorted({r["edge"] for r in rows})}
        for i, order in enumerate(ORDER):
            for arm in order:
                for record, row in zip(records, rows, strict=True):
                    engine = engines[arm, row["edge"]]
                    factors, elapsed = engine.run(row["iq"], row["lane"], row["tune"])
                    observation = dict(factors=factors, clock=elapsed, audit=audit(engine))
                    if arm == "trace":
                        get = engine.native.lib.short_primary_trace_read
                        get.argtypes, get.restype = (ct.POINTER(ShortTrace),), None
                        trace = ShortTrace()
                        get(ct.byref(trace))
                        observation["detail"] = trace.document()
                    record["rounds"][i][arm] = observation
    for record, source in zip(records, rows, strict=True):
        first = record["rounds"][0]["pack"]
        for paid in record["rounds"]:
            for obs in paid.values():
                if (obs["factors"], obs["audit"]) != (first["factors"], first["audit"]):
                    raise ValueError("Profile altered a signed factor or original verifier event/flags")
        archived = source["short"]
        if len(first["factors"]) != len(archived) or any(row[:4] != ref[:4] or any(abs(a-b) > 1e-8 for a, b in zip(row[4:], ref[4:], strict=True))
                for row, ref in zip(first["factors"], archived, strict=True)):
            raise ValueError("The guarded lane does not bind its original signed archived packet")
        record["overlap"] = causal_overlap(record["rounds"][0]["trace"]["detail"])
    stats = summarize(records)
    result = dict(profile=stats, rows=records, host=machine, build=compiled, paired_order=ORDER, staged=receipt,
                  cache_before=cache_before, cache_after=resident(stage), original_archive_reads=0,
                  sources={path.name: sha256(path.read_bytes()).hexdigest() for path in
                           (Path(__file__), HERE/"short_primary_trace.h", HERE/"short-primary-fusion-profile-protocol.md")})
    with (root/"result.json").open("x") as output:
        json.dump(result, output, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
