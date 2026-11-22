"""Measure exact oscillator argument preparation on the frozen all-factor receiver."""

import argparse
import json
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
from statistics import median

import numpy as np

from tools.algo08_scan import PINS
from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, digest
from tools.pipeline_eval.variants.experimental.receiver_build import replace

from . import receiver_cfo_lineage_trial as lineage
from . import receiver_cfo_native_trial as native
from . import receiver_cfo_restore_object as restore
from .freeze_fractional_exact_receiver import ALL_SHA, GENERATED_SHA, OBJECT_SHA
from .receiver_cfo_wrap_build import exports, run
from .receiver_fractional_exact_trial import TERMINAL_PAIR
from .screened_stock_salvage_trial import require_spec

PARENT_SPEC = "sha256:a546069457b70491949d3b500f65cffd26939e693d9079ddc6b37a55d26e2afa"
PARENT_BUNDLE = "integration-fractional-absolute-all"
PARENT_INCLUDE = "7e6e4d0d0bd3074963a50340e645f66023c3a273ea2fc7cd6279496f2bef2a2b"
PARENT_BUILD = "5566ddd22345982e1b7673c7d65a8ce5799ce8229275365e1e6e237ab3f0e86d"
ARMS = ("frozen", "hoisted", "avx", "deployed")
COMPARISONS = (("frozen", "hoisted"), ("frozen", "avx"), ("deployed", "hoisted"),
               ("deployed", "avx"), ("hoisted", "avx"))


def overlay(source, variant):
    row = "    int row = -1;"
    source = replace(source, row, row + "\n    const double omega = -tau * cfo;")
    calculation = "            PortableFineComplex z = rotate(-tau * cfo * position / rate);"
    if variant == "hoisted":
        return replace(source, calculation, calculation.replace("-tau * cfo", "omega"))
    source = '#include "receiver_absolute_phase_avx.inc"\n\n' + source
    invalidate = "    w->integer_hz = NAN;"
    prepare = "    const int batch = absolute_phase_batch_supported(cfo);\n"
    source = replace(source, invalidate, prepare + "    double arguments[aperture];\n" + invalidate)
    frame = "    for (int frame = 0; frame < frames; ++frame) {"
    source = replace(source, frame, frame + "\n"
                     "        if (batch) absolute_phase_batch(arguments, starts[frame] + first, "
                     "aperture, omega, offset);")
    return replace(source, calculation,
                   "            const double argument = batch ? arguments[k] : "
                   "omega * position / rate;\n"
                   "            PortableFineComplex z = rotate(argument);")


def build(work, bench):
    require_spec(bench / PARENT_BUNDLE, PARENT_SPEC)
    frozen = bench / "receiver-fractional-exact-v1"
    build_receipt = frozen / "build.json"
    restore.digest(build_receipt, PARENT_BUILD)
    record = json.loads(build_receipt.read_bytes())
    source = frozen / "portable_verifier.c"
    parent_include = restore.HERE / "receiver_fractional_exact.inc"
    restore.digest(source, GENERATED_SHA)
    restore.digest(parent_include, PARENT_INCLUDE)
    for pair in ((frozen / "exact.so", ALL_SHA), (bench / PARENT_BUNDLE / "receiver.so", ALL_SHA),
                 (frozen / "portable_verifier.o", OBJECT_SHA)):
        restore.digest(*pair)
    compiler, link = record["commands"][-2:]
    old_object = str(frozen / "portable_verifier.o")
    for item in link:
        if item.endswith(".o"):
            pin = OBJECT_SHA if item == old_object else record["parent_objects"][Path(item).name]
            restore.digest(Path(item), pin)
    work.mkdir()
    original = work / "frozen.so"
    replay = run([*link[:-1], original], cwd=restore.PINNED)
    restore.digest(original, ALL_SHA)
    builds = {}
    for variant in ("hoisted", "avx"):
        target = work / variant
        target.mkdir()
        cooked, obj = (target / name for name in (source.name, "portable_verifier.o"))
        generated = target / parent_include.name
        generated.write_text(overlay(parent_include.read_text(), variant))
        cooked.write_bytes(source.read_bytes())
        inputs = {str(source): str(cooked), old_object: str(obj)}
        compile_line = [inputs.get(item, item) for item in compiler]
        build_command = run(compile_line, cwd=restore.PINNED)
        binary = work / f"{variant}.so"
        patched = [str(obj) if item == old_object else item for item in link[:-1]]
        link_command = run([*patched, binary], cwd=restore.PINNED)
        if exports(binary) != exports(original):
            raise ValueError("Absolute oscillator preparation changed the receiver ABI")
        builds[variant] = dict(
            sha256=restore.digest(binary), object_sha256=restore.digest(obj),
            effective_header_sha256=restore.digest(generated),
            commands=[build_command, link_command],
        )
    phase_header = restore.HERE / "receiver_absolute_phase_avx.inc"
    receipt = dict(parent_specification=PARENT_SPEC, parent_sha256=ALL_SHA,
                   parent_build_sha256=PARENT_BUILD, parent_relink=replay,
                   phase_header_sha256=restore.digest(phase_header),
                   trial_source_sha256=restore.digest(Path(__file__)), builds=builds)
    (work / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def compare(work, assets, groups):
    builds = json.loads((work / "build.json").read_bytes())["builds"]
    pins = dict(frozen=ALL_SHA, deployed=PINS["cancellation-factors.so"])
    pins.update({name: value["sha256"] for name, value in builds.items()})
    with ExitStack() as stack:
        radios = {}
        for edge in ("lower", "upper"):
            pilot = assets / f"{edge}.f32"
            restore.digest(pilot, PINS[pilot.name])
            template = np.fromfile(pilot, dtype="<f4")
            for arm in ARMS:
                path = (assets / "cancellation-factors.so" if arm == "deployed"
                        else work / f"{arm}.so")
                restore.digest(path, pins[arm])
                radio = Receiver(path, template)
                stack.callback(radio.close)
                radios[edge, arm] = radio
        result = {group: measure(rows, radios) for group, rows in groups.items()}
    for name, group in result.items():
        for key, reading in group["paired"].items():
            if any(reading["counts"].values()):
                raise ValueError(f"Exact factor or continuation changed on {name}: {key}")
    return dict(binaries=pins, samples=result)


def measure(group, radios):
    all_times, first_readout = [], None
    for arms in (ARMS, ARMS[::-1]):
        for repetition in range(len(arms)):
            elapsed = dict.fromkeys(arms, 0)
            histories = {arm: defaultdict(Continuation) for arm in arms}
            readout = []
            for index, (case, key, edge, center, authority, meta, iq) in enumerate(group):
                offset = (index + repetition) % len(arms)
                results = {}
                for arm in arms[offset:] + arms[:offset]:
                    radio = radios[edge, arm]
                    factors, cpu, _ = radio.timed(iq, meta["receiver_id"], center)
                    selected = histories[arm][case].select(
                        dict(meta, candidates=[radio.criteria(*factor) for factor in factors]),
                    )
                    encoded = digest(native.factor_bytes(factors))
                    results[arm] = dict(factors=factors, continuation=selected,
                                        factor_sha256=encoded)
                    elapsed[arm] += cpu
                readout.append(dict(key=key, receiver_id=meta["receiver_id"], edge=edge,
                                    center_hz=center,
                                    iq_sha256=authority, arms=results))
            if first_readout is None:
                first_readout = readout
            elif first_readout != readout:
                raise ValueError("Factor bytes or continuation changed between balanced repeats")
            all_times.append(elapsed)
    return dict(
        lane_calls=len(group), cpu_ns=all_times, rows=first_readout,
        median_cpu_ns={arm: median(row[arm] for row in all_times) for arm in ARMS},
        paired={f"{a}_to_{b}": native.compare(first_readout, a, b) | dict(
            paired_change=median(row[b] / row[a] - 1 for row in all_times),
            median_delta_ns=median(row[b] - row[a] for row in all_times),
        ) for a, b in COMPARISONS},
    )


def saved(work, assets, weak, archive, source_audit, wide_reference):
    return compare(work, assets, native.inputs(weak, archive, source_audit, wide_reference))


def dense(work, assets, pair, baseline, binding, bulk):
    batch = json.loads(lineage.pin(pair, TERMINAL_PAIR))
    references = lineage.saved_rows(baseline, "baseline", batch)
    windows = lineage.load_samples(binding, bulk, batch, references)
    group = []
    for visit, row in sorted(windows.items()):
        metadata = references[visit, row["lane"]]
        probe = {name: metadata[name] for name in (
            "receiver_id", "channel", "actual_rf_hz", "valid_start_counter",
        )}
        group.append(("DS30-0008", str(visit), "lower", row["center"], row["iq_sha256"],
                      probe, row["samples"]))
    return compare(work, assets, {"DS30-0008-wrapped": group})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in (
        (build, ("work", "bench")),
        (saved, ("work", "assets", "weak", "archive", "source_audit", "wide_reference")),
        (dense, ("work", "assets", "pair", "baseline", "binding", "bulk")),
    ):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for name in fields:
            command.add_argument(name, type=lambda value: Path(value).resolve())
    args = vars(parser.parse_args())
    handler = args.pop("handler")
    args.pop("action")
    print(json.dumps(handler(**args), allow_nan=False, indent=2))
