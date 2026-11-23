"""Relink the reviewed shortened receiver and measure the actual mixed callback."""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
from itertools import groupby
import json
from pathlib import Path
from statistics import median
import subprocess
from time import process_time_ns, perf_counter_ns
from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import digest, read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical

from .mixed_aperture_receiver import (INSTALLED_SHA, PILOT_SHA, MixedApertureDetector, NativePath,
                                     StereoSchedule, verified)
from .scout_readout_trial import check_machine, factor_bytes
from .stereo_fft_trial import CARRIER_SOURCE_SHA


HERE = Path(__file__).resolve().parent
SHORT_SHA = "74464b62ae5cc5763dd62fa611e14133ef602578e11200c3152b0dc9555cd169"
SHORT_RECEIPT_SHA = "cb369f55ceaaced0ddc87ff7c9bdff48b6cb78ea4ee7eff8ebf7754983b7234d"
BUILD_MANIFEST_SHA = "5566ddd22345982e1b7673c7d65a8ce5799ce8229275365e1e6e237ab3f0e86d"
REPEATS = 5
PATHS = ("installed_full", "short_full", "short_primary", "mixed_callback")
PANEL_SHA = {
    "weak": "cd540df70741181116b57e105d87568ab554323d9687e211c7aec20f23316f6c",
    "dense": "01c4d5c80ed3feefbb3ee072d76b40d7566768522b5cc2cede25cb2365a10294",
}


def exports(path):
    rows = subprocess.check_output(["nm", "--defined-only", "-D", str(path)], text=True)
    return {row.split()[-1] for row in rows.splitlines() if row}


def build(archive, output):
    machine = check_machine()
    earlier = json.loads(gzip.decompress(verified(HERE / "measurements/short-signed.json.gz", SHORT_RECEIPT_SHA)))
    manifest = json.loads(verified(archive / "receiver-fractional-exact-v1/build.json", BUILD_MANIFEST_SHA))
    short = earlier["build"]["arms"]["short"]
    link = short["commands"][-1]
    original = Path(link[-1])
    verified(original, SHORT_SHA)
    output.mkdir()
    baseline = output / "original-short-relinked.so"
    subprocess.run([*link[:-1], baseline], cwd=manifest["cwd"], check=True)
    verified(baseline, SHORT_SHA)
    object_idx, = (i for i, item in enumerate(link) if Path(item).name == "two_carrier_receiver.o")
    archived = Path(link[object_idx]).with_suffix(".c")
    extension = HERE / "short_primary_entry.inc"
    source = output / "two_carrier_receiver.c"
    source.write_bytes(verified(archived, CARRIER_SOURCE_SHA) + b"\n" + extension.read_bytes())
    native_object = source.with_suffix(".o")
    compiler = manifest["commands"][-2]
    compile = [*compiler[:-4], "-Wall", "-Werror", "-c", str(source), "-o", str(native_object)]
    subprocess.run(compile, cwd=manifest["cwd"], check=True)
    linker = link[:-2]
    linker[object_idx] = str(native_object)
    candidate = output / "short-primary.so"
    relink = [*linker, "-Wl,-Bsymbolic-functions", "-o", str(candidate)]
    subprocess.run(relink, cwd=manifest["cwd"], check=True)
    if exports(candidate) != exports(original) | {"cancellation_primary_factors"}:
        raise ValueError("The research build changed the previously qualified ABI")
    body = subprocess.check_output(["objdump", "--disassemble=cancellation_primary_factors", str(candidate)], text=True)
    if (not all(f"<{name}>" in body for name in ("timing_first_detect", "portable_verifier_load"))
            or "<verify_peaks" not in body):
        raise ValueError("The primary entry failed to bind the shortened scout and verifier locally")
    ordinary_code = body.replace("<__stack_chk_fail@plt>", "")
    if any(phrase in ordinary_code for phrase in ("@plt", "pilot_cancel", "timing_first_cancel_resident")):
        raise ValueError("The primary entry can call a residual search or an interposable symbol")
    binary_info = subprocess.check_output(["readelf", "-dW", str(candidate)], text=True)
    if any(name in binary_info for name in ("receiver.so", "use.so")):
        raise ValueError("The shortened entry depends on an external receiver DSO")
    receipt = dict(binary=str(candidate), binary_sha256=digest(candidate.read_bytes()),
                   short_relink_sha256=SHORT_SHA, source_wrapper_sha256=digest(source.read_bytes()),
                   extension_sha256=digest(extension.read_bytes()),
                   callback_sha256=digest((HERE / "mixed_aperture_receiver.py").read_bytes()),
                   short_object_sha256={Path(item).name: digest(Path(item).read_bytes())
                                        for item in link if str(item).endswith(".o")},
                   primary_disassembly=body, compile=compile, relink=relink, machine=machine)
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True))


def window(row, samples):
    target = dict(row["target"], edge=row["edge"])
    acquisition = dict(row["acquisition"])
    if "global_visit" not in acquisition:
        acquisition["global_visit"] = row["visit"]
    return SimpleNamespace(samples=samples, target=target, acquisition=acquisition,
                           receiver_ids=(0, 1), sample_rate_hz=10_000_000)


def center(w):
    return w.target["rf_center_hz"] - w.target["lnb_lo_hz"] - w.acquisition["actual_if_center_hz"]


def ordered(rows):
    if not rows:
        return ()
    return (max(rows, key=lambda f: (f[4] - f[5], -f[0])),)


def encoded(probe):
    return tuple((row["candidate_rank"], row["integer_epoch_sample"], row["fractional_epoch_offset_samples"],
                  row["fractional_tracking_cfo_hz"], row["fractional_exact_score"], row["fractional_control_score"])
                 for row in probe["candidates"])


def audit(stereo, native, original, short_full, primary):
    counts, installed_out, expected_primary = Counter(), [], []
    for row, samples in stereo:
        ci = window(row, samples)
        key, tune = row["edge"], center(ci)
        altered = np.copy(samples)
        altered[120_000:, :, :] = np.iinfo(np.int16).max
        installed_pair, primary_pair = [], []
        for lane in (0, 1):
            stock, _ = native[key].run(samples, lane, tune)
            full, _ = original[key].run(samples, lane, tune)
            relinked, _ = short_full[key].run(samples, lane, tune)
            kept, _ = primary[key].run(samples, lane, tune)
            poisoned, _ = primary[key].run(altered, lane, tune)
            rank0 = tuple(row for row in full if row[0] == 0)
            if factor_bytes(full) != factor_bytes(relinked):
                raise ValueError("Relinking altered the original shortened full-scanner factors")
            if factor_bytes(kept) != factor_bytes(rank0) or factor_bytes(kept) != factor_bytes(poisoned):
                raise ValueError("The short primary differs from the short rank-zero or reads the original suffix")
            counts["lanes"] += 1
            counts["installed_factors"] += len(stock)
            counts["short_full_factors"] += len(full)
            counts["primary_retained"] += len(kept)
            counts["short_residual_only"] += bool(full and not rank0)
            counts["primary_empty"] += not kept
            counts["suffix_exact"] += 1
            counts["relinked_short_exact"] += 1
            installed_pair.append(stock)
            primary_pair.append(kept)
        installed_out.append(installed_pair)
        expected_primary.append(primary_pair)
    return installed_out, expected_primary, dict(counts)


def run_panel(stereo, installed, output, assets, previous_path, build_receipt):
    short = Path(build_receipt["binary"])
    verified(installed, INSTALLED_SHA)
    verified(previous_path, SHORT_SHA)
    verified(short, build_receipt["binary_sha256"])
    with ExitStack() as close:
        controls = {arm: {} for arm in PATHS[:3]}
        short_full = {}
        for edge in sorted({row["edge"] for row, _ in stereo}):
            asset = np.frombuffer(verified(assets / f"{edge}.f32", PILOT_SHA[edge]), dtype="<f4")
            for arm, binary in (("installed_full", installed), ("short_full", previous_path), ("short_primary", short)):
                ctx = NativePath(binary, asset, arm)
                controls[arm][edge] = ctx
                close.callback(ctx.close)
            ctx = NativePath(short, asset, "short_full")
            short_full[edge] = ctx
            close.callback(ctx.close)
        original, primaries, audit_counts = audit(stereo, controls["installed_full"], controls["short_full"],
                                                short_full, controls["short_primary"])
        measurements = []
        for repeat in range(REPEATS):
            timings = {key: [0, 0] for key in PATHS}
            keys, native_totals, selected, visits = Counter(), Counter(), Counter(), Counter()
            packets = []
            for _, recording in groupby(enumerate(stereo), key=lambda item: item[1][0]["case"]):
                scope = MixedApertureDetector(short, build_receipt["binary_sha256"])
                expected = StereoSchedule()
                with ExitStack() as releases:
                    active = {}
                    for i, (row, samples) in recording:
                        w = window(row, samples)
                        edge = row["edge"]
                        if edge not in active:
                            active[edge] = releases.enter_context(scope.detector(
                                "cancellation", edge, binary=installed, pilot=assets / f"{edge}.f32"))
                        method = expected.visit(edge, w.target, w.acquisition)[1]
                        for arm in PATHS if (i + repeat) % 2 else PATHS[::-1]:
                            if arm == "mixed_callback":
                                begin = process_time_ns(), perf_counter_ns()
                                rows = active[edge](w)
                                clocks = process_time_ns()-begin[0], perf_counter_ns()-begin[1]
                                expected_samples = ([(), ()] if method == "skip" else
                                                    primaries[i] if method == "short_primary" else
                                                    [ordered(row) for row in original[i]])
                                if len(rows) != 2 or any(
                                    r["receiver_id"] != lane
                                    or r["valid_start_counter"] != w.acquisition["sample_start"]
                                    or r["visit_index"] != w.acquisition["global_visit"]
                                    or factor_bytes(encoded(r)) != factor_bytes(expected_samples[lane])
                                    for lane, r in enumerate(rows)
                                ):
                                    raise ValueError("Mixed callback changed a counter, antenna or chosen factor")
                                packets.extend(rows)
                            else:
                                clocks = [0, 0]
                                for lane in (0, 1):
                                    _, tick = controls[arm][edge].run(samples, lane, center(w))
                                    clocks[0] += tick[0]
                                    clocks[1] += tick[1]
                            timings[arm][0] += clocks[0]
                            timings[arm][1] += clocks[1]
                receipt = scope.receipt()
                keys.update(receipt["native_calls"])
                native_totals.update(receipt["native_cpu_ns"])
                selected.update(receipt["factors"])
                visits.update(receipt["visits"])
            measurements.append(dict(cpu_wall_ns=timings, scheduled_calls=keys, scheduled_visits=visits,
                                     selected=selected, mixed_native_cpu_ns=native_totals,
                                     probe_document_sha256=digest(json.dumps(packets, sort_keys=True).encode())))
    if len({repeat["probe_document_sha256"] for repeat in measurements}) != 1:
        raise ValueError("Repeated mix runs changed genuine native evidence")
    result = dict(validation=audit_counts, input_sha256=[(row["key"], row["sha256"]) for row, _ in stereo],
                  repeats=measurements, machine=check_machine(), build=build_receipt)
    with output.open("x") as stream:
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False), file=stream)


def measure(work, installed, assets, weak, binding, bulk, cohort, output):
    check_machine()
    earlier = json.loads(gzip.decompress(verified(HERE / "measurements/short-signed.json.gz", SHORT_RECEIPT_SHA)))
    original = Path(earlier["build"]["arms"]["short"]["commands"][-1][-1])
    rows = read_archive(weak, 18) if cohort == "weak" else read_physical(binding, bulk, 48)
    run_panel(list(rows), installed, output, assets, original, json.loads((work / "build-receipt.json").read_bytes()))


def setup(work, installed, assets, output):
    from tools.pipeline_eval.qualification.blind_compact_run import detector

    machine = check_machine()
    build_receipt = json.loads((work / "build-receipt.json").read_bytes())
    short = Path(build_receipt["binary"])
    short_sha = build_receipt["binary_sha256"]
    verified(installed, INSTALLED_SHA)
    verified(short, short_sha)
    timings = []
    allocated = {}
    for edge in PILOT_SHA:
        pilot = assets / (edge + ".f32")
        for repeat in range(6):
            arms = ("installed", "mixed") if repeat % 2 == 0 else ("mixed", "installed")
            for arm in arms:
                start = process_time_ns(), perf_counter_ns()
                prepare = detector if arm == "installed" else MixedApertureDetector(short, short_sha).detector
                with prepare("cancellation", edge, binary=installed, pilot=pilot):
                    timing = process_time_ns()-start[0], perf_counter_ns()-start[1]
                close = process_time_ns()-start[0]-timing[0], perf_counter_ns()-start[1]-timing[1]
                timings.append(dict(edge=edge, repeat=repeat, arm=arm, enter_cpu_wall_ns=timing,
                                    close_cpu_wall_ns=close))
        asset = np.frombuffer(verified(pilot, PILOT_SHA[edge]), dtype="<f4")
        with ExitStack() as paths:
            allocated[edge] = {}
            for mode, binary in (("full", installed), ("short_primary", short)):
                native = NativePath(binary, asset, mode)
                paths.callback(native.close)
                allocated[edge][mode] = native.native.bytes
    with output.open("x") as stream:
        print(json.dumps(dict(machine=machine, short_primary_sha256=short_sha,
                              accounted_native_workspace_bytes=allocated, scopes=timings), indent=2), file=stream)


def medians(panels):
    med = lambda values: median(values) / 1e6
    repeats = panels["repeats"]
    first = repeats[0]
    stock_cpu = median(row["cpu_wall_ns"]["installed_full"][0] for row in repeats)
    primary_cpu = median(row["cpu_wall_ns"]["short_primary"][0] for row in repeats)
    native_fraction = median(sum(row["mixed_native_cpu_ns"].values()) /
                             row["cpu_wall_ns"]["installed_full"][0] for row in repeats)
    per_paid_lane = {mode: med(row["mixed_native_cpu_ns"][mode] / row["scheduled_calls"][mode]
                              for row in repeats) for mode in first["scheduled_calls"]}
    return dict(cpu_wall_ms={mode: [med(row["cpu_wall_ns"][mode][axis] for row in repeats) for axis in (0, 1)]
                             for mode in PATHS}, scheduled_calls=first["scheduled_calls"],
                scheduled_visits=first["scheduled_visits"], selected=first["selected"],
                scheduled_native_cpu_ms_per_paid_lane=per_paid_lane,
                scheduled_native_cpu_ms_per_paid_stereo={mode: 2 * cost for mode, cost in per_paid_lane.items()},
                primary_panel_cpu_ms_per_lane=primary_cpu / (panels["validation"]["lanes"] * 1e6),
                scheduled_native_fraction_of_stock=native_fraction,
                nominal_steady_native_fraction_of_stock=1 / 8 + (primary_cpu / stock_cpu) / 2,
                probe_document_sha256=first["probe_document_sha256"])


def score(work, output):
    panels = {name: json.loads(verified(work / (name + ".json"), sha)) for name, sha in PANEL_SHA.items()}
    startup = json.loads((work / "setup.json").read_bytes())
    build_receipt = panels["weak"].pop("build")
    if panels["dense"].pop("build") != build_receipt or startup["short_primary_sha256"] != build_receipt["binary_sha256"]:
        raise ValueError("The two panels and setup used different compiled receivers")
    durations = {}
    for edge in PILOT_SHA:
        durations[edge] = {}
        for arm in ("installed", "mixed"):
            rows = [row for row in startup["scopes"] if row["edge"] == edge and row["arm"] == arm]
            durations[edge][arm] = {
                "first_cpu_wall_ms": [ns / 1e6 for ns in rows[0]["enter_cpu_wall_ns"]],
                "repeat_cpu_wall_ms": [median(row["enter_cpu_wall_ns"][axis] for row in rows[1:]) / 1e6
                                       for axis in (0, 1)],
                "repeat_close_cpu_wall_ms": [median(row["close_cpu_wall_ns"][axis] for row in rows[1:]) / 1e6
                                             for axis in (0, 1)],
            }
    with output.open("x") as stream:
        print(json.dumps(dict(build=build_receipt, panel_sha256=PANEL_SHA, panels=panels, startup=startup,
                              summary={name: medians(panel) for name, panel in panels.items()},
                              startup_summary=durations), indent=2, sort_keys=True, allow_nan=False), file=stream)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    building, measuring, starting, scoring = (modes.add_parser(name) for name in ("build", "measure", "setup", "score"))
    for mode, arguments in ((building, ("archive", "output")),
                            (measuring, ("work", "installed", "assets", "weak", "binding", "bulk")),
                            (starting, ("work", "installed", "assets", "output")),
                            (scoring, ("work", "output"))):
        for name in arguments:
            mode.add_argument(name, type=lambda value: Path(value).resolve())
    measuring.add_argument("cohort", choices=("weak", "dense"))
    measuring.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    {"build": build, "measure": measure, "setup": setup, "score": score}[args.pop("mode")](**args)
