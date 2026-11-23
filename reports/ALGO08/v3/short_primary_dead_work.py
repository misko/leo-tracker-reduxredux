"""Price and trim dead FIR and loader outputs in the authenticated short primary."""

import argparse
from collections import defaultdict
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
import json
from math import remainder
from pathlib import Path
from statistics import mean, median
import subprocess
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.qualification.cache_residency import load_query
from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from .centered_primary import BUILD_PIN, ORIGINAL, PREFIX_PIN, RELEASE_BUILD, RELEASE_PIN, WEAK_PIN
from .directed_verifier_trial import Timing, replace_once
from .fractional_reject_ceiling import ShortTrace, VerifierResult
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, verified
from .mixed_aperture_trial import center, window
from .scout_readout_trial import check_machine, factor_bytes
from .sparse_cold_input import CACHE_LIBRARY, CACHE_SHA, PAYLOAD, RELEASE
from .warm_six_prefetch import ResidentTmpfsReads


SHORT_OBJECTS = Path("/var/tmp/leo-short-signed-02/short")
ARCHIVE = RELEASE_BUILD.parent.parent
TILE_BUILD_PIN = "c883317586466068d065f9ead944990f8959df4ac8ef60819d9909738b616b62"
TILE_PIN = "46d4a1e2e60049467d87055634cf60dd47e4f82616d136063a0016eb51877c2f"
VERIFY_PIN = "4cceaa68fe8d7f93608d1d07f585e2bc5c68955a22619d989052d6cde2e70def"
STENCIL_PIN = "8b2f4162d9637991e45b3e47eea28aadd9ff254bee02389569be69180f064a63"
TIMING_PIN = "a8fa28b5997ee7b4537ebaca4e41982b4976de4b00fde82011871570a616e1cc"
FIRST, LAST = 22, 28_098
LOAD_LIMIT = 109_600
REPEATS = 5


def digest(data):
    return sha256(data).hexdigest()


def tile_source(original):
    start = original.index('__attribute__((target("avx2")))\nstatic void tiled_fir(')
    end = original.index("static int overlaps(", start)
    selected = replace_once(original[start:end], "static void tiled_fir(", "static void tiled_fir_used(")
    selected = replace_once(selected, "    enum { output_samples = input_samples / stride_four, pad = radius / stride_four };\n", "")
    selected = replace_once(selected, "    for (int j = 0; j < pad; ++j)\n        edge_output(in, coeff, out, j);\n", "")
    selected = replace_once(selected, "for (int j = pad; j < output_samples - pad; j += 4)",
                            f"for (int j = {FIRST}; j < {LAST}; j += 4)")
    selected = replace_once(selected, "    for (int j = output_samples - pad; j < output_samples; ++j)\n        edge_output(in, coeff, out, j);\n", "")
    wrapper = original[original.index("int delay_decimate("):]
    wrapper = replace_once(wrapper, "int delay_decimate(", "int delay_decimate_scout_used(")
    wrapper = replace_once(wrapper, "return leo_pgo_delay_decimate(in, coeff, taps, stride, out);",
                           "return delay_decimate(in, coeff, taps, stride, out);")
    wrapper = replace_once(wrapper, "tiled_fir(in, coeff, out);", "tiled_fir_used(in, coeff, out);")
    declaration = "int delay_decimate(const float *, const float *, int, int, float *);\n"
    return (original[:original.index("static void edge_output(")]
            + original[end:original.index("int delay_decimate(")] + selected + declaration + wrapper)


def verifier_source(original):
    s = original.index("int portable_verifier_load(")
    e = original.index("static unsigned bounded_grid(", s)
    load = replace_once(original[s:e], "int portable_verifier_load(", "int portable_verifier_load_scout_fractional(")
    load = replace_once(load, "sample < loaded_samples;", f"sample < {LOAD_LIMIT};")
    return original + "\n" + load


def wrapper_source(original):
    entry = "int cancellation_primary_factors("
    declaration = "int portable_verifier_load_scout_fractional(PortableVerifier *, const int16_t *, unsigned);\n"
    start = original.index(entry)
    return original[:start] + declaration + replace_once(original[start:], "portable_verifier_load(",
                                                          "portable_verifier_load_scout_fractional(")


def build(root):
    saved = json.loads(verified(ORIGINAL / "build-receipt.json", BUILD_PIN))
    release = json.loads(verified(RELEASE_BUILD, RELEASE_PIN))
    tile_build = json.loads(verified(ARCHIVE / "d97b-fir-tile-v1.json", TILE_BUILD_PIN))
    reference = ORIGINAL / "short-primary.so"
    verified(reference, PREFIX_PIN)
    old_objects = {Path(item).name: Path(item) for item in saved["relink"] if item.endswith(".o")}
    for name, item in old_objects.items():
        # The primary wrapper was added after the recorded short-object census.
        if item != Path(saved["compile"][-1]):
            verified(item, saved["short_object_sha256"][name])
    binary = root / "scoped-primary.so"
    full_relink = root / "unmodified.so"
    compiler = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    if compiler != release["compiler"]:
        raise ValueError("The original build compiler changed")
    commands = []

    def run(command):
        commands.append(list(map(str, command)))
        subprocess.run(command, cwd=release["cwd"], check=True)

    run([*saved["relink"][:-1], full_relink])
    verified(full_relink, PREFIX_PIN)
    verified(SHORT_OBJECTS / "timing_first_receiver.c", TIMING_PIN)
    tile = verified(SHORT_OBJECTS / "tile.c", TILE_PIN).decode()
    ver = verified(SHORT_OBJECTS / "portable_verifier.c", VERIFY_PIN).decode()
    wrapper = verified(saved["compile"][-3], saved["source_wrapper_sha256"]).decode()
    (root / "receiver_stencil_verify.inc").write_bytes(verified(SHORT_OBJECTS / "receiver_stencil_verify.inc", STENCIL_PIN))
    new_objects = {}
    for name, text, flags in (("tile_scope", tile_source(tile), tile_build["build"]["commands"][2][:-4]),
                              ("portable_verifier", verifier_source(ver), release["commands"][-2][:-4]),
                              ("two_carrier_receiver", wrapper_source(wrapper), saved["compile"][:-4])):
        source, obj = root / (name+".c"), root / (name+".o")
        source.write_text(text)
        run([*flags, "-c", source, "-o", obj])
        new_objects[name+".o"] = obj
    scout = root / "timing_first_receiver.o"
    run(["objcopy", "--redefine-sym", "delay_decimate=delay_decimate_scout_used", old_objects[scout.name], scout])
    new_objects[scout.name] = scout
    link = [new_objects.get(Path(item).name, item) for item in saved["relink"][:-2]]
    run([*link, new_objects["tile_scope.o"], "-o", binary])
    return binary, dict(commands=commands, prototype_sha256=digest(binary.read_bytes()), original=PREFIX_PIN,
                        objects=saved["short_object_sha256"], fir_source=TILE_PIN, verifier_source=VERIFY_PIN,
                        scout_source=TIMING_PIN, stencil_source=STENCIL_PIN)


def north_rows():
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.scanner import ScannerIqStore
    from .public_short_prefetch import MANIFEST_SHA, RECORDING

    checked = ResidentTmpfsReads(RECORDING, load_query(CACHE_LIBRARY))
    verified(CACHE_LIBRARY, CACHE_SHA)
    scope = dict(path=str(RECORDING), manifest_digest="sha256:"+MANIFEST_SHA)
    with patch.dict(ScannerIqStore._read_regular.__globals__, {"os": checked}):
        source = FastSegmentSource(scope, stop_sequence=48)
        rows = [(dict(edge=item.target["edge"], target=item.target, acquisition=item.acquisition,
                      sha256=item.iq_sha256), item.samples) for item in source.windows()]
    if len(rows) != 48:
        raise ValueError("The staged public prefix changed")
    return rows


def bind(lib, name, types):
    fn = getattr(lib, name)
    fn.argtypes, fn.restype = types, ct.c_int
    return fn


def traced(stage, iq, lane, tune, *, short_load=None, diagnostic=None):
    scout = Timing()
    start = process_time_ns()
    status = stage.timing_first_detect(stage.scout, iq.ctypes.data, lane, tune-800000, tune+800000, ct.byref(scout))
    scout_ns = process_time_ns()-start
    if status:
        raise ValueError("Released scout failed")
    if not scout.confirmation:
        return (), [scout_ns, 0, 0]
    load = short_load or stage.portable_verifier_load
    start = process_time_ns()
    status = load(stage.verify, iq.ctypes.data, lane)
    load_ns = process_time_ns()-start
    if status:
        raise ValueError("Released loader failed")
    epoch = round(scout.epoch) % 13333
    result = VerifierResult(acquired_hz=scout.hz)
    verify = diagnostic or stage.portable_verifier_factor
    start = process_time_ns()
    status = verify(stage.verify, epoch, ct.byref(result))
    verify_ns = process_time_ns()-start
    if status:
        raise ValueError("Released verifier failed")
    rows = ()
    if (result.flags & 2 and abs(remainder(epoch+result.offset_samples-scout.epoch, 13333)) <= 2
            and abs(result.fractional_residual_hz) <= 1000):
        rows = ((0, epoch, result.offset_samples, scout.hz+result.fractional_residual_hz,
                 result.fractional_exact, result.fractional_control),)
    return rows, [scout_ns, load_ns, verify_ns]


def fir_measure(lib, iq, lane, coeff):
    full = bind(lib, "delay_decimate", (ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p))
    used = bind(lib, "delay_decimate_scout_used", full.argtypes)
    samples = np.ascontiguousarray(iq[:120_000, lane, :], dtype=np.float32)
    all_outputs = np.empty((30_000, 2), dtype=np.float32)
    scoped = np.full_like(all_outputs, np.nan)
    ticks = []
    for fn, out in ((full, all_outputs), (used, scoped)):
        start = process_time_ns()
        status = fn(samples.ctypes.data, coeff.ctypes.data, 81, 4, out.ctypes.data)
        ticks.append(process_time_ns()-start)
        if status:
            raise ValueError("The scoped FIR failed")
    if (not np.array_equal(all_outputs[FIRST:LAST].view("u4"), scoped[FIRST:LAST].view("u4"))
            or not np.isnan(scoped[:FIRST]).all() or not np.isnan(scoped[LAST:]).all()):
        raise ValueError("The FIR changed a consumed value or touched a dead output")
    return ticks


def panel(rows, prototype):
    installed, short = PAYLOAD / "receiver.so", ORIGINAL / "short-primary.so"
    assets, engines, stages = {}, {}, {}
    ticks = []
    setup = {}
    with ExitStack() as scope:
        for edge in sorted({row["edge"] for row, _ in rows}):
            assets[edge] = np.frombuffer(verified(RELEASE / "assets" / (edge+".f32"), PILOT_SHA[edge]), dtype="<f4")
            for label, library, kind in (("anchor", installed, "full"), ("short", short, "short_primary"),
                                         ("prototype", prototype, "short_primary")):
                start, wall = process_time_ns(), perf_counter_ns()
                engine = NativePath(library, assets[edge], kind)
                setup[edge+"/"+label] = [process_time_ns()-start, perf_counter_ns()-wall]
                scope.callback(engine.close)
                engines[edge, label] = engine
                if label != "anchor":
                    stages[edge, label] = ShortTrace(engine)
        for repeat in range(REPEATS):
            for index, (row, iq) in enumerate(rows):
                edge = row["edge"]
                tune = center(window(dict(row, visit=index), iq))
                actual = {kind: engines[edge, kind] for kind in ("anchor", "short", "prototype")}
                for lane in (0, 1):
                    orders = tuple(actual)
                    shift = (repeat+index+lane) % len(orders)
                    direct = {kind: actual[kind].run(iq, lane, tune) for kind in orders[shift:]+orders[:shift]}
                    reference, short_time = direct["short"]
                    tested, new_time = direct["prototype"]
                    stock_stage, new_stage = stages[edge, "short"], stages[edge, "prototype"]
                    new_lib = actual["prototype"].native.lib
                    loader = bind(new_lib, "portable_verifier_load_scout_fractional", (ct.c_void_p, ct.c_void_p, ct.c_uint))
                    portable = bind(actual["short"].native.lib, "portable_verifier_glrt",
                                    (ct.c_void_p, ct.c_uint, ct.POINTER(VerifierResult)))
                    original, stage_times = traced(stock_stage, iq, lane, tune)
                    changed, new_stages = traced(new_stage, iq, lane, tune, short_load=loader)
                    diagnostic, portable_stages = traced(stock_stage, iq, lane, tune, diagnostic=portable)
                    if len({factor_bytes(factors) for factors in (reference, tested, original, changed)}) != 1:
                        raise ValueError(f"The scoped prototype changed factor bytes on {edge}/{index}/{lane}")
                    fir = fir_measure(new_lib, iq, lane, assets[edge][4*13333:4*13333+81]) if repeat == 0 else None
                    ticks.append(dict(iq_sha256=row["sha256"], repeat=repeat, index=index, lane=lane, edge=edge,
                                      center=tune, short=short_time, prototype=new_time, anchor=direct["anchor"][1],
                                      anchor_factors=len(direct["anchor"][0]), factors=reference, stages=stage_times,
                                      scoped_stages=new_stages, portable_stages=portable_stages, fir=fir,
                                      diagnostic_exact=factor_bytes(diagnostic) == factor_bytes(reference)))
    return dict(setup=setup, rows=ticks)


def summarize(packets):
    summary = {}
    for name, data in packets.items():
        rows, groups = data["rows"], defaultdict(list)
        for row in rows:
            groups[bool(row["factors"])].append(row)
        result = {}
        for label, group in (("all", rows), ("confirmed", groups[True]), ("empty", groups[False])):
            fir = [row["fir"] for row in group if row["fir"]]
            result[label] = dict(count=len(group)//REPEATS, diagnostic_exact=sum(row["diagnostic_exact"] for row in group)//REPEATS,
                                 native={k: mean(row[k][0] for row in group) for k in ("anchor", "short", "prototype")},
                                 stage={k: list(map(mean, zip(*(row[k] for row in group), strict=True)))
                                        for k in ("stages", "scoped_stages", "portable_stages")},
                                 fir=list(map(mean, zip(*fir, strict=True))) if fir else None,
                                 repeat_mean_delta_ns=median(mean(row["short"][0]-row["prototype"][0]
                                                                 for row in group if row["repeat"] == repeat)
                                                             for repeat in range(REPEATS)))
        summary[name] = result
    return summary


def run(weak, output):
    host = check_machine()
    verified(PAYLOAD / "receiver.so", INSTALLED_SHA)
    verified(weak, WEAK_PIN)
    output.mkdir()
    binary, build_receipt = build(output)
    data = {"weak": panel(list(read_archive(weak, 18)), binary), "north": panel(north_rows(), binary)}
    result = dict(host=host, build=build_receipt, profile=data, summary=summarize(data), repeats=REPEATS,
                  source_sha256=digest(Path(__file__).read_bytes()), loader_end=LOAD_LIMIT, fir_tile_outputs=[FIRST, LAST])
    with (output / "receipt.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("weak", "output"):
        parser.add_argument(name, type=Path)
    run(**vars(parser.parse_args()))
