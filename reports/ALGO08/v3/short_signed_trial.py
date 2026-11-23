"""Build and compare two-scan ALGO08v3 receivers with 20 ms and 12 ms apertures."""

import argparse
from collections import Counter
from contextlib import ExitStack
from itertools import permutations
import json
import math
from pathlib import Path
from statistics import median
import subprocess
import sys

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, digest, read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound import TIMING_SOURCE_SHA, V3_SHA

from .directed_verifier_trial import continuation, replace_once
from .low_bit_pilot_screen import adc, carrier_wave
from .scout_readout_trial import ACQUISITION, ACQUISITION_SHA, PILOT_SHA, check_machine, factor_bytes


ROOT = Path(__file__).resolve().parents[3]
ARM_NAMES = ("installed", "control", "short")
SAMPLES, FRAMES = 120000, 8
PERIOD = 13333
HISTORY = {
    "receiver-fractional-exact-v1/build.json":
        "5566ddd22345982e1b7673c7d65a8ce5799ce8229275365e1e6e237ab3f0e86d",
    "receiver-cfo-lineage-fix/build.json":
        "cb926e55cd9c7cb7a4eec8fc83adc4450e22a32facfa3838de186f7bbb224862",
    "receiver-cfo-wrap-fix/build.json":
        "3c3b065154061d956346bd9620fd82478fb40542567b7eff71d4d3eccb01196b",
    "d97b-fir-tile-v1.json":
        "c883317586466068d065f9ead944990f8959df4ac8ef60819d9909738b616b62",
    "spectral-vectors-combined-v1.json":
        "dea6143babd712336d871efd560631e0fb4308238178d78c16f4fba56b4ecc6d",
}
SOURCES = {
    "timing_first_receiver": TIMING_SOURCE_SHA,
    "delay_product_kernel": "d014fe0670ff7a926bbd302ada1f4d021fe2f488f91b32dae8b4fe1634a07f1c",
    "pilot_cancel": "34e186b48005ec68ad9a16024a691b12c9ad71d06e40985104ce086cf077d3f0",
    "portable_verifier": "3f62918238ad9107474d2f1509e953c61776eb70123ecd880c514f6e6483a707",
    "receiver_stencil_verify.inc": "cc8128035f99faa0ce9b45482d7db9278c5c0d1713879fc7a271b2a37f47a957",
    "tile": "a45f25bee6ceffe35258f2e10f2d5af009b577bd064016fcc4a2db5c409058ab",
}


def verified(path, expected):
    contents = path.read_bytes()
    if digest(contents) != expected:
        raise ValueError(f"Unexpected digest for {path}")
    return contents


def geometry(samples=SAMPLES, frames=FRAMES):
    # At 10 MS/s the frame spacing is exactly 40000 ticks at 3 ticks/sample.
    origin = (40000 * (frames - 1) + 1) // 3
    last_epoch = PERIOD - 1
    return dict(sample_rate_hz=10000000, stored_samples=200000, short_samples=samples,
                short_frames=frames, last_origin=origin,
                first_unused_fir_sample=origin + last_epoch + 128 * 44 + 41,
                first_unused_latest_confirmation_sample=origin + last_epoch + 88 + (232 + 64) * 44,
                first_unused_integer_stencil_sample=origin + last_epoch + (2 + 64) * 44 + 4,
                first_unused_fractional_sample=origin + last_epoch + (2 + 64) * 44 + 10)


def short_source(name, source, samples=SAMPLES, frames=FRAMES):
    cuts = {
        "timing_first_receiver": [
            ("points = 200000", f"points = {samples}"),
            ("count = 14", f"count = {frames}"),
            ("early ? 7 : 2", "early ? count / 2 : 2"),
        ],
        "delay_product_kernel": [
            ("samples = 200000", f"samples = {samples}"),
            ("frames = 14", f"frames = {frames}"),
        ],
        "pilot_cancel": [("samples = 200000", f"samples = {samples}")],
        "portable_verifier": [
            # The unchanged conditioned/stencil objects use the 15-frame array stride.
            ("max_frames = 15", f"max_frames = 15, analysis_frames = {frames}"),
            ("samples = PORTABLE_FINE_SAMPLES", f"samples = PORTABLE_FINE_SAMPLES, loaded_samples = {samples}"),
            ("sample < samples;", "sample < loaded_samples;"),
            ("frame < max_frames;", "frame < analysis_frames;"),
            ("start + stop - 1 + offset >= samples", "start + stop - 1 + offset >= loaded_samples"),
        ],
        "receiver_stencil_verify.inc": [
            ("f < max_frames;", "f < analysis_frames;"),
            ("start + aperture > samples", "start + aperture > loaded_samples"),
            ("start + aperture + 4 > samples", "start + aperture + 4 > loaded_samples"),
        ],
        "tile": [("input_samples = 200000", f"input_samples = {samples}")],
    }
    if name == "timing_first_receiver" and frames % 2:
        # The AVX frame-plane layout stores two lanes per stripe, including the final partial pair.
        cuts[name].append(("w->frames = reserve(w, count * w->width, sizeof(Sample));",
                           "w->frames = reserve(w, ((count + 1) / 2) * 2 * w->width, sizeof(Sample));"))
    for old, new in cuts[name]:
        source = replace_once(source, old, new)
    return source


def wrapped_profile(command, original, temporary):
    # GCC labels this function cold only in builds where the profile warrants it.
    symbols = subprocess.check_output(["objdump", "-t", original], text=True).splitlines()
    symbol, = [row.split() for row in symbols if row.split()[-1:] == ["delay_refine"]]
    address, scope, kind, section, size, _ = symbol
    if scope != "g" or kind != "F" or not section.startswith(".text.") or not int(size, 16):
        raise ValueError("Cannot bind the released wrap dispatcher to the profiled refinement")
    return [*command[:2], f"--add-symbol=leo_pgo_delay_refine={section}:0x{address},global,function",
            original, temporary]


def build(archive, work, installed, assets, *, apertures=None):
    verified(installed, V3_SHA)
    recipes = {name: json.loads(verified(archive / name, sha)) for name, sha in HISTORY.items()}
    release = recipes["receiver-fractional-exact-v1/build.json"]
    lineage = recipes["receiver-cfo-lineage-fix/build.json"]
    wrap = recipes["receiver-cfo-wrap-fix/build.json"]["commands"]
    tile = recipes["d97b-fir-tile-v1.json"]["build"]["commands"]
    pgo = recipes["spectral-vectors-combined-v1.json"]["build"]["builds"]["packed"]["commands"]
    link = release["commands"][-1]
    cwd = release["cwd"]
    compiler = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    if compiler != release["compiler"]:
        raise ValueError("Unexpected native compiler")
    work.mkdir()
    reference = work / "archived.so"
    subprocess.run([*link[:-1], reference], check=True, cwd=cwd)
    verified(reference, V3_SHA)
    source_paths = {
        "timing_first_receiver": Path(pgo[0][-3]),
        "delay_product_kernel": Path(lineage["compile"][-3]),
        "pilot_cancel": Path(next(item for item in link if item.endswith("/pilot_cancel.o"))).with_suffix(".c"),
        "portable_verifier": Path(release["commands"][-2][-3]),
        "receiver_stencil_verify.inc": Path(release["commands"][-2][-5]) / "receiver_stencil_verify.inc",
        "tile": Path(tile[2][-3]),
    }
    trainer = ROOT / "reports/ALGO08/single-core-2x/receiver_mixer_profile_trial.py"
    inputs = {name: verified(path, SOURCES[name]).decode() for name, path in source_paths.items()}
    result = {}
    if apertures is None:
        apertures = {"control": None, "short": (SAMPLES, FRAMES)}
    for arm, aperture in apertures.items():
        out = work / arm
        out.mkdir()
        feedback = out / "feedback"
        feedback.mkdir()
        commands = []

        def run(command, **kwargs):
            command = list(map(str, command))
            commands.append(command)
            return subprocess.run(command, check=True, cwd=cwd, **kwargs)

        def compile_unit(flags, name, output):
            run([*flags, "-c", out / f"{name}.c", "-o", output])

        names = {name: name if name.endswith(".inc") else f"{name}.c" for name in inputs}
        for name, source in inputs.items():
            (out / names[name]).write_text(short_source(name, source, *aperture) if aperture is not None else source)
        compile_unit(release["commands"][-2][:-4], "portable_verifier", out / "portable_verifier.o")
        compile_unit(tile[2][:-4], "tile", out / "tile.o")
        compile_unit(lineage["compile"][:-4], "delay_product_kernel", out / "delay_plain.o")
        run([*wrap[2][:-2], out / "delay_plain.o", out / "delay_reference.o"])
        swaps = ("timing_first_receiver", "pilot_cancel", "delay_pgo", "delay_reference", "tile",
                 "portable_verifier")
        objects = [out / Path(item).name if Path(item).stem in swaps else item for item in link[3:-2]]
        for phase, template in (("generate", pgo[0]), ("use", pgo[2])):
            binary = out / f"{phase}.so"
            profile_flags = [template[0], f"-fprofile-{phase}={feedback}", *template[2:-4]]
            for name in ("timing_first_receiver", "pilot_cancel", "delay_product_kernel"):
                compile_unit(profile_flags, name, out / f"{name}.o")
            run(wrapped_profile(wrap[1], out / "delay_product_kernel.o", out / "delay_wrap.o"))
            run([*tile[1][:-2], out / "delay_wrap.o", out / "delay_pgo.o"])
            run([*profile_flags[:3], *link[1:3], *objects, "-o", binary])
            if phase == "generate":
                proc = run([sys.executable, trainer, "train", binary, assets], capture_output=True, text=True)
                training = json.loads(proc.stdout)
                profiles = {file.stem: digest(file.read_bytes()) for file in feedback.rglob("*.gcda")}
                if len(profiles) != 3:
                    raise ValueError("Incomplete matched profile coverage")
        result[arm] = dict(binary_sha256=digest(binary.read_bytes()), profiles=profiles, training=training,
                           source_sha256={name: digest((out / file).read_bytes()) for name, file in names.items()},
                           commands=commands)
    return dict(installed_sha256=V3_SHA, compiler=compiler, input_sources=SOURCES, archive_json=HISTORY,
                trainer_sha256=digest(trainer.read_bytes()), arms=result)


def error(reference, proposed):
    samples = abs(math.remainder((reference[1] + reference[2]) - (proposed[1] + proposed[2]), PERIOD))
    return samples, abs(reference[3] - proposed[3])


def match(stock, short, *, ranks):
    """Maximize hit count without reusing a factor, then minimize total error."""
    pairings = []
    for left in permutations(range(len(stock))):
        for right in permutations(range(len(short))):
            pairs = []
            for i, j in zip(left, right, strict=False):
                if ranks and stock[i][0] != short[j][0]:
                    continue
                samples, hz = error(stock[i], short[j])
                if samples <= 2 and hz <= 250:
                    pairs.append((i, j, samples, hz))
            pairings.append(sorted(pairs))
    return min(pairings, key=lambda p: (-len(p), sum(samples/2 + hz/250 for _, _, samples, hz in p), p))


def summarize(rows):
    counts, retained, residual = Counter(), Counter(), []
    shorts = ("short_alone", "oracle_fallback", "empty_fallback", "byte_oracle_fallback")
    times = {name: [] for name in (*ARM_NAMES, *shorts)}
    elapsed = {name: [] for name in ARM_NAMES}
    for row in rows:
        a, b = row["factors"]["installed"], row["factors"]["short"]
        hits = match(a, b, ranks=True)
        physical = match(a, b, ranks=False)
        equivalent = len(a) == len(b) == len(hits)
        byte_equal = factor_bytes(a) == factor_bytes(b)
        counts.update(lanes=1, empty_stock=int(not a), empty_short=int(not b),
                      empty_lost_stock=int(not b and bool(a)), empty_stock_add=int(not a and bool(b)),
                      short_nonempty_mismatch=int(bool(b) and not equivalent),
                      oracle_retries=int(not equivalent), byte_retries=int(not byte_equal),
                      stock_factors=len(a), short_factors=len(b), hits=len(hits), physical_hits=len(physical),
                      extra=len(b)-len(hits), physical_extra=len(b)-len(physical),
                      continuation_equal=int(row["selection"]["installed"] == row["selection"]["short"]))
        if row["selection"]["installed"] is not None:
            selected = row["selection"]["short"]
            counts["stock_selections"] += 1
            counts["selected_hits"] += bool(selected is not None and match(
                [row["selection"]["installed"]], [selected], ranks=True))
        counts["short_selections"] += row["selection"]["short"] is not None
        retained.update(("stock", fact[0]) for fact in a)
        retained.update(("short", fact[0]) for fact in b)
        retained.update(("matched", a[i][0]) for i, _, _, _ in hits)
        residual.extend((samples, hz, abs((a[i][4]-a[i][5]) - (b[j][4]-b[j][5])))
                        for i, j, samples, hz in hits)
        for arm in ARM_NAMES:
            times[arm].append(row["cpu_ns"][arm])
            elapsed[arm].append(row["wall_ns"][arm])
        base, short = row["cpu_ns"]["installed"], row["cpu_ns"]["short"]
        for label, retry in zip(shorts, (False, not equivalent, not b, not byte_equal), strict=True):
            times[label].append([value + (stock if retry else 0) for stock, value in zip(base, short, strict=True)])

    def timing(values):
        totals = [sum(repeat) / 1e9 for repeat in zip(*values, strict=True)]
        return dict(median_lane_ms=median(v for lane in values for v in lane) / 1e6,
                    median_total_s=median(totals), total_s=totals)

    return dict(counts=counts, by_rank={kind: [retained[kind, n] for n in range(2)]
                                      for kind in ("stock", "short", "matched")},
                max_matched_sample_hz_margin=[max(group) for group in zip(*residual, strict=True)],
                cpu={name: timing(values) for name, values in times.items()},
                wall={name: timing(values) for name, values in elapsed.items()})


def measure(paths, sample_rows, assets, repeats):
    detail = []
    with ExitStack() as closer:
        edges = {row["edge"] for row, _ in sample_rows}
        receivers = {}
        for edge in sorted(edges):
            pilot = np.frombuffer(verified(assets / f"{edge}.f32", PILOT_SHA[edge]), dtype="<f4")
            for arm, binary in paths.items():
                radio = Receiver(binary, pilot)
                closer.callback(radio.close)
                receivers[arm, edge] = radio
        for row, iq in sample_rows:
            if iq.shape != (200000, 2, 2) or iq.dtype != np.dtype("<i2") or not iq.flags.c_contiguous:
                raise ValueError(f"Unexpected stored waveform geometry for {row['key']}")
            for lane in (0, 1):
                detail.append(dict(key=row["key"], lane=lane, input_sha256=row["sha256"], edge=row["edge"],
                                   channel=row["target"]["channel"], label=row.get("label"),
                                   factors={}, selection={}, cpu_ns={arm: [] for arm in paths},
                                   wall_ns={arm: [] for arm in paths}))
        for repeat in range(repeats):
            histories = {arm: {} for arm in paths}
            for index, (row, iq) in enumerate(sample_rows):
                target, acquisition = row["target"], row["acquisition"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
                for lane in (0, 1):
                    entry = detail[2*index + lane]
                    for step in range(len(paths)):
                        arm = ARM_NAMES[(2*index + lane + repeat + step) % len(paths)]
                        radio = receivers[arm, row["edge"]]
                        factors, cpu, wall = radio.timed(iq, lane, center)
                        selection = continuation(histories[arm], row, lane, factors)
                        if repeat and factor_bytes(factors) != factor_bytes(entry["factors"][arm]):
                            raise ValueError("Ordered repeat changed factor bytes")
                        entry["factors"][arm] = factors
                        entry["selection"][arm] = selection
                        entry["cpu_ns"][arm].append(cpu)
                        entry["wall_ns"][arm].append(wall)
                    if (factor_bytes(entry["factors"]["installed"]) != factor_bytes(entry["factors"]["control"])
                            or entry["selection"]["installed"] != entry["selection"]["control"]):
                        raise ValueError(f"Matched stock rebuild differs from installed v3 at {entry['key']} lane {lane}")
        for (row, iq), pair in zip(sample_rows, zip(detail[::2], detail[1::2], strict=True), strict=True):
            suffix_changed = iq.copy()
            suffix_changed[SAMPLES:] = 32767
            target, acq = row["target"], row["acquisition"]
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            for entry in pair:
                radio = receivers["short", row["edge"]]
                result, _, _ = radio.timed(suffix_changed, entry["lane"], center)
                if factor_bytes(result) != factor_bytes(entry["factors"]["short"]):
                    raise ValueError(f"Short receiver used the excluded tail at {entry['key']}")
    return dict(summary=summarize(detail), detail=detail)


def controls(assets):
    rng = np.random.default_rng(898789)
    noise = (rng.normal(size=200000) + 1j * rng.normal(size=200000)) / np.sqrt(2)
    for edge, pin in PILOT_SHA.items():
        asset = np.frombuffer(verified(assets / f"{edge}.f32", pin), dtype="<f4")
        for index, kind in enumerate(("paired", "late_only", "noise", "rolled")):
            iq = np.zeros((200000, 2, 2), dtype="<i2")
            for lane, hz in enumerate((-639701, 554913)):
                wave = carrier_wave(asset, 10993, hz, rolled=kind == "rolled")
                if kind == "late_only":
                    wave[:SAMPLES] = 0
                if kind == "noise":
                    wave[:] = 0
                if kind == "paired":
                    wave = wave + 0.31 * carrier_wave(asset, 27113, -hz * 0.57, rolled=False)
                plant = adc(1900 * (wave + 0.39 * noise))
                iq[:, lane, 0], iq[:, lane, 1] = plant.real, plant.imag
            # Exercise both resident and nonzero-center quantized cancellation dispatch.
            center = {"lower": 0, "upper": 75000}[edge]
            row = dict(edge=edge, case=f"plants-{edge}", key=f"{edge}:{kind}", label=kind,
                       target=dict(rf_center_hz=center, lnb_lo_hz=0, channel="control"),
                       acquisition=dict(actual_if_center_hz=0, sample_start=200000 * index),
                       sha256=digest(iq.tobytes()))
            yield row, iq


def transfer(dense):
    reference = json.loads(verified(ACQUISITION, ACQUISITION_SHA))
    outside = reference["outside_detector_cpu_s"]
    callbacks = sum(row["cpu_s"] for row in reference["detector_groups"].values())
    stock = dense["summary"]["cpu"]["installed"]["median_total_s"]
    result = {}
    for arm, timer in dense["summary"]["cpu"].items():
        ratio = timer["median_total_s"] / stock
        whole = outside + ratio * callbacks
        result[arm] = dict(callback_ratio=ratio, projected_acquisition_cpu_s=whole,
                           projected_acquisition_speedup=(outside + callbacks)/whole)
    return dict(source_sha256=ACQUISITION_SHA, historical_stock_callbacks=callbacks,
                historical_outside_callbacks=outside,
                max_callback_ratio_for_half_acquisition=(callbacks-outside)/(2*callbacks),
                experiment=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "work", "installed", "assets", "weak", "binding", "bulk"):
        parser.add_argument(name, type=lambda value: Path(value).resolve())
    args = parser.parse_args()
    machine = check_machine()
    shape = geometry()
    if max(value for field, value in shape.items() if field.startswith("first_unused")) > SAMPLES:
        raise ValueError("Short aperture excludes samples required by a complete frame")
    receipt = build(args.archive, args.work, args.installed, args.assets)
    binaries = {"installed": args.installed, **{arm: args.work / arm / "use.so" for arm in ARM_NAMES[1:]}}
    groups = {}
    for label, rows in (("weak", read_archive(args.weak, 18)), ("dense", read_physical(args.binding, args.bulk, 48)),
                        ("plants", controls(args.assets))):
        groups[label] = measure(binaries, list(rows), args.assets, 5)
    input_digests = {label: digest(json.dumps([(row["key"], row["input_sha256"]) for row in detail["detail"]],
                                            sort_keys=True).encode()) for label, detail in groups.items()}
    print(json.dumps(dict(machine=machine, geometry=shape, build=receipt, input_digests=input_digests,
                          groups=groups, transfer=transfer(groups["dense"])), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
