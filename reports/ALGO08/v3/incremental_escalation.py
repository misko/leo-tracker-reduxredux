"""Measure forced 12-to-20 ms escalation with exact stride-four FIR overlap."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack, closing
import ctypes as ct
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter_ns, process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from .centered_primary import BUILD_PIN, ORIGINAL, PREFIX_PIN, RELEASE_BUILD, RELEASE_PIN, WEAK_PIN
from .directed_verifier_trial import replace_once
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, verified
from .mixed_aperture_trial import center, window
from .scout_readout_trial import check_machine, factor_bytes
from .short_signed_trial import SOURCES
from .sparse_cold_input import PAYLOAD, RELEASE


HERE = Path(__file__).resolve().parent
TILE = HERE.parents[2] / "tools/pipeline_eval/variants/experimental/receiver_fir_tile.c"
HOOK = HERE / "incremental_escalation.c"
RETAINED = (120_000 - 1 - 40) // 4 + 1
FLAGS = ["-fPIC", "-O3", "-std=c11", "-ffp-contract=off", "-fno-math-errno",
         "-fno-strict-aliasing", "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror"]
MODES = ("installed20", "linked20", "restart12_20", "resume12_20")
ORDERS = (MODES, MODES[::-1]) * 3


def digest(contents):
    return sha256(contents).hexdigest()


def suffix_source(tile):
    # Preserve the released AVX2 operations, pairing and edge arithmetic.
    if RETAINED < 10 or (RETAINED - 10) % 4:
        raise ValueError("The retained prefix must end at a released AVX2 tile boundary")
    part = tile[:tile.index("static int overlaps(")]
    part = replace_once(part, "static void tiled_fir(", "void leo_escalation_fir_suffix(")
    part = replace_once(part, "    for (int j = 0; j < pad; ++j)\n        edge_output(in, coeff, out, j);\n", "")
    return replace_once(part, "for (int j = pad; j < output_samples - pad; j += 4)",
                        f"for (int j = {RETAINED}; j < output_samples - pad; j += 4)")


def build(root):
    installed = PAYLOAD / "receiver.so"
    short = ORIGINAL / "short-primary.so"
    verified(installed, INSTALLED_SHA)
    verified(short, PREFIX_PIN)
    release = json.loads(verified(RELEASE_BUILD, RELEASE_PIN))
    archive = json.loads(verified(ORIGINAL / "build-receipt.json", BUILD_PIN))
    compiler = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    if compiler != release["compiler"]:
        raise ValueError("The native compiler differs from release provenance")
    root.mkdir()
    commands = []

    def run(command):
        command = list(map(str, command))
        commands.append(command)
        subprocess.run(command, cwd=release["cwd"], check=True)

    tile = root / "suffix.c"
    tile.write_text(suffix_source(verified(TILE, SOURCES["tile"]).decode()))
    suffix = root / "suffix.o"
    run(["cc", *FLAGS, "-c", tile, "-o", suffix])
    result = {"installed20": installed, "original12": short}
    for name, expected, original, defines, extra in (
        ("linked20", INSTALLED_SHA, release["commands"][-1], [], [suffix]),
        ("linked12", PREFIX_PIN, archive["relink"], ["-DSHORT_APERTURE"], []),
    ):
        pristine = root / (name + "-pristine.so")
        run([*original[:-1], pristine])
        verified(pristine, expected)
        obj, binary = root / (name + ".o"), root / (name + ".so")
        run(["cc", *FLAGS, *defines, "-c", HOOK, "-o", obj])
        run([*original[:-2], "-Wl,--wrap=delay_decimate", "-Wl,-z,defs", obj, *extra, "-o", binary])
        result[name] = binary
    return result, dict(compiler=compiler, commands=commands, binary_sha256={k: digest(p.read_bytes())
                       for k, p in result.items()}, pinned_recipes=[RELEASE_PIN, BUILD_PIN],
                       hook_sha256=digest(HOOK.read_bytes()), tile_sha256=SOURCES["tile"],
                       generated_suffix_sha256=digest(tile.read_bytes()))


def linked_arguments(full):
    factor = ct.POINTER(full.factor)
    call = full.native.lib.leo_escalation_run
    call.argtypes = ([ct.c_void_p] * 5 + [ct.c_int, ct.c_double, ct.c_double, ct.c_int,
                                        factor, factor, ct.POINTER(ct.c_int)])
    call.restype = ct.c_int
    return call


def measure(paths, samples, lane, offset, mode):
    short, full = paths["linked12"], paths["linked20"]
    short_out, full_out = (full.factor * 2)(), (full.factor * 2)()
    stats = (ct.c_int * 3)()
    if mode == "installed20":
        factors, clocks = paths[mode].run(samples, lane, offset)
        return factor_bytes(factors), b"", None, clocks
    flags = {"restart12_20": 0, "resume12_20": 1, "linked20": 2}
    call = linked_arguments(full)
    args = (full.native.ctx, short.native.ctx, short.call, short.native.lib.leo_escalation_capture,
            samples.ctypes.data, lane, offset-800000, offset+800000, flags[mode], short_out, full_out, stats)
    begin = process_time_ns(), perf_counter_ns()
    count = call(*args)
    clocks = process_time_ns()-begin[0], perf_counter_ns()-begin[1]
    if not 0 <= count <= 2 or not 0 <= stats[0] <= 1:
        raise ValueError("Unexpected result count from the scoped escalation")
    return b"".join(map(bytes, full_out[:count])), b"".join(map(bytes, short_out[:stats[0]])), tuple(stats), clocks


def fir_check(paths, asset, lanes, repeats=3):
    original = []
    for name in ("linked12", "linked20"):
        fn = paths[name].native.lib.delay_decimate
        fn.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p]
        fn.restype = ct.c_int
        original.append(fn)
    suffix = paths["linked20"].native.lib.leo_escalation_fir_suffix
    suffix.argtypes, suffix.restype = [ct.c_void_p] * 3, None
    coff = asset[4 * 13333:4 * 13333 + 81].ctypes.data
    short, whole, resumed = (np.empty((n, 2), dtype=np.float32) for n in (30_000, 50_000, 50_000))
    left = resumed[:RETAINED]
    clocks = []
    for samples, lane in lanes:
        source = np.ascontiguousarray(samples[:, lane], dtype=np.float32)
        if original[0](source.ctypes.data, coff, 81, 4, short.ctypes.data):
            raise ValueError("The pinned short FIR rejected its input")
        for _ in range(repeats):
            src, target = source.ctypes.data, whole.ctypes.data
            start = process_time_ns()
            status = original[1](src, coff, 81, 4, target)
            clocks.append(process_time_ns()-start)
            if status:
                raise ValueError("The pinned full FIR rejected its input")
        left[:] = short[:RETAINED]
        suffix(source.ctypes.data, coff, resumed.ctypes.data)
        if whole.tobytes() != resumed.tobytes():
            raise ValueError("The assembled 20 ms FIR changed an output byte")
    return clocks


def panel(rows, binaries, asset_directory):
    visits = [(r["edge"], r["sha256"], samples, center(window(r, samples))) for r, samples in rows]
    counts, evidence, component = Counter(), [], []
    fingerprints = {name: sha256() for name in ("full", "short")}
    with ExitStack() as stack:
        engines = {}
        for edge, expected in PILOT_SHA.items():
            lanes = [(samples, lane) for row_edge, _, samples, _ in visits if row_edge == edge for lane in (0, 1)]
            if not lanes:
                continue
            asset = np.frombuffer(verified(asset_directory / (edge + ".f32"), expected), dtype="<f4")
            paths = engines[edge] = {k: stack.enter_context(closing(NativePath(
                p, asset, "short_primary" if k.endswith("12") else "full"))) for k, p in binaries.items()}
            component.extend(fir_check(paths, asset, lanes))
        for edge, identity, samples, offset in visits:
            paths = engines[edge]
            for lane in (0, 1):
                full, _, _, _ = measure(paths, samples, lane, offset, "installed20")
                factors, _ = paths["original12"].run(samples, lane, offset)
                early = factor_bytes(factors)
                factor_type = paths["linked20"].factor
                size = ct.sizeof(factor_type)
                ranks = [factor_type.from_buffer_copy(full, p).rank for p in range(0, len(full), size)]
                counts.update({"full_count_" + str(len(ranks)): 1, "short_count_" + str(len(factors)): 1,
                               "rank1_issued": 1 in ranks, "rank1_first": ranks[:1] == [1]})
                for name, vector in (("full", full), ("short", early)):
                    fingerprints[name].update(bytes([len(vector)]) + vector)
                for mode in MODES[1:]:
                    output, prior, stats, _ = measure(paths, samples, lane, offset, mode)
                    if output != full or prior != (b"" if mode == "linked20" else early):
                        raise ValueError("A native aperture changed its complete ordered signed factor bytes")
                    if stats[1] != (mode == "resume12_20") or stats[2] not in (1, 2):
                        raise ValueError("The full primary did not take the intended FIR path")
                    counts[mode + "_secondary"] += stats[2] == 2
                evidence.append(dict(iq_sha256=identity, edge=edge, lane=lane, mixer_hz=offset, full_ranks=ranks,
                                     full_sha256=digest(full), short_sha256=digest(early)))

        # Nonzero mixer and differing FIR are exercised off-clock without modifying the timed offer.
        edge, _, samples, offset = visits[0]
        paths = engines[edge]
        offcenter = 125_000 if offset != 125_000 else -125_000
        full, _, _, _ = measure(paths, samples, 0, offcenter, "installed20")
        output, early, stats, _ = measure(paths, samples, 0, offcenter, "resume12_20")
        if output != full or early != factor_bytes(paths["original12"].run(samples, 0, offcenter)[0]) or stats[1] != 1:
            raise ValueError("The nonzero mixer violated exact reuse")
        offset_scouts = stats[2]
        silent = np.zeros_like(samples)
        full, _, _, _ = measure(paths, silent, 0, offset, "installed20")
        output, early, stats, _ = measure(paths, silent, 0, offset, "resume12_20")
        if full or output or early or stats != (0, 1, 1):
            raise ValueError("The synthetic zero lane changed the released no-confirmation branch")
        other = np.frombuffer(verified(asset_directory / (edge + ".f32"), PILOT_SHA[edge]), dtype="<f4").copy()
        other[4 * 13333 + 40] = np.nextafter(other[4 * 13333 + 40], np.float32(np.inf))
        with closing(NativePath(binaries["linked20"], other, "full")) as changed:
            altered_paths = dict(paths, linked20=changed)
            output, _, stats, _ = measure(altered_paths, samples, 0, offset, "resume12_20")
            if output != factor_bytes(changed.run(samples, 0, offset)[0]) or stats[1] != 0:
                raise ValueError("Differing FIR coefficients did not fall back to complete recomputation")

        results = []
        for order in ORDERS:
            run = {}
            for mode in order:
                work = Counter()
                begin = process_time_ns(), perf_counter_ns()
                for edge, _, samples, offset in visits:
                    for lane in (0, 1):
                        _, _, stats, (cpu, wall) = measure(engines[edge], samples, lane, offset, mode)
                        work.update(native_cpu_ns=cpu, native_wall_ns=wall)
                        if stats is not None:
                            work.update(fir_reuses=stats[1], secondary_scouts=stats[2] == 2)
                run[mode] = dict(work, batch_cpu_ns=process_time_ns()-begin[0],
                                 batch_wall_ns=perf_counter_ns()-begin[1])
            results.append(dict(order=list(order), clocks=run))
    return dict(lanes=evidence, counts=dict(counts), paired_repeats=results,
                ordered_factor_sha256={k: value.hexdigest() for k, value in fingerprints.items()},
                nonzero_mixer=dict(center_hz=offcenter, reused=True, scouts=offset_scouts),
                synthetic_zero_scouts=1, changed_filter_fell_back=True,
                complete_fir_component_ns=dict(n=len(component), median=median(component), maximum=max(component)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("weak", "work", "receipt"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    machine = check_machine()
    rows = list(read_archive(BytesIO(verified(args.weak, WEAK_PIN)), 18))
    if len(rows) != 18:
        raise ValueError("Incomplete frozen weak panel")
    binaries, provenance = build(args.work.resolve())
    receipt = dict(machine=machine, build=provenance, weak_archive_sha256=WEAK_PIN, retained_fir_outputs=RETAINED,
                   measurement=panel(rows, binaries, RELEASE / "assets"))
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
