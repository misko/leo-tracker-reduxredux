"""Compare exact absolute-phase verification on the frozen spectral receiver."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import json
from pathlib import Path
from statistics import median
import subprocess
from time import process_time_ns

import numpy as np

from . import receiver_cfo_lineage_trial as lineage
from . import receiver_cfo_native_trial as native
from . import receiver_cfo_restore_object as restore
from .receiver_cfo_wrap_build import exports, run
from .receiver_spectral_vectors_check import CANDIDATE_SHA as PARENT_SHA
from .screened_stock_salvage_trial import require_spec
from tools.algo08_scan import PINS
from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental import receiver_fractional_exact
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Factor, Receiver, digest
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical


SPEC = "sha256:445744b4401d14d42a62130dca85882fd9062eb32627a9046e62205650dddb28"
ORIGINAL_SOURCE = "f7deb83f0f1fad1b04f64962d8b06a493f83f964a129102ee63c6b6ad59e98a4"
TIMING_OBJECT = "5ffc8eb34785b7d20535549da23ba521cf954f86b6cfabce96c0c71ac664292d"
PARENT = "integration-spectral-vectors-wrapped-longitude"
TERMINAL_PAIR = "c241b36434359d6dfde2756f179c661a03af35edd6dc9aaed686de3e3ac11de8"
TERMINAL_DETECTION = "635db6d0488a48a94208c1cd5d984d952e9034fd8d7d616bcf6759fe0f808558"
PHYSICAL_BINDING = "c781d10abe126bdc40d75a6e202d09a7542e92ef932a535f42700fe95d9ac38c"
PHYSICAL_IQ = "71dbe0d47a51992022584fdc797f0e64b216a62b3c37744bcc25f9958319e605"
HEADERS = {
    "receiver_phase_free_verify.inc": "9c41b48fc3bb3c7eb42456d0d589da3e9f16fe67e0dd82b3e188785e9bc45a36",
    "receiver_stencil_verify.inc": "cc8128035f99faa0ce9b45482d7db9278c5c0d1713879fc7a271b2a37f47a957",
}
ARMS = ("parent", "exact", "deployed")
COMPARISONS = (("parent", "exact"), ("deployed", "parent"), ("deployed", "exact"))


def build(work, bench, *, defer=False):
    require_spec(bench / PARENT, SPEC)
    work.mkdir()
    recipe_file = restore.PINNED / "build.json"
    restore.digest(recipe_file, restore.RECIPE_SHA)
    recipe = json.loads(recipe_file.read_bytes())
    flags, _ = restore.compiler_inputs(recipe, work, work)
    former = json.loads((bench / "d97b-planes-and-fir/build.json").read_bytes())
    timing = bench / "spectral-vectors-combined-v1/packed/timing_first_receiver.o"
    verifier = work / "portable_verifier.o"
    pins = former["objects"] | {timing.name: TIMING_OBJECT}
    link = [str(timing) if Path(part).name == timing.name else part for part in former["link"][:-1]]
    for part in link:
        if part.endswith(".o"):
            restore.digest(Path(part), pins[Path(part).name])
    combined = work / "parent.so"
    parent_command = run([*link, combined], cwd=restore.PINNED)
    restore.digest(combined, PARENT_SHA)
    restore.digest(bench / PARENT / "receiver.so", PARENT_SHA)
    index, = [i for i, part in enumerate(link) if Path(part).name == verifier.name]
    source = Path(link[index]).with_suffix(".c")
    restore.digest(source, ORIGINAL_SOURCE)
    for name in ("portable_verifier.h", "portable_fine.h"):
        relative = Path("tools/pipeline_eval/variants") / name
        restore.digest(restore.PINNED / relative, recipe["source_digests"][str(relative)])
    header = next(name for name in recipe["source_digests"] if name.endswith("/fft.h"))
    restore.digest(restore.PINNED / header, recipe["source_digests"][header])
    for name, expected in HEADERS.items():
        restore.digest(restore.HERE / name, expected)
    generated = verifier.with_suffix(".c")
    generated.write_text(receiver_fractional_exact.overlay(source.read_text(), defer=defer))
    compiler = recipe["cc"]

    def compiled(text):
        return run([compiler, *flags, "-I", restore.PINNED / "tools/pipeline_eval/variants",
                    "-I", restore.HERE, "-c", text, "-o", text.with_suffix(".o")], cwd=restore.PINNED)

    commands = [parent_command, compiled(generated)]
    link[index] = str(verifier)
    if defer:
        measurement = work / "two_carrier_receiver.c"
        index, = [i for i, part in enumerate(link) if Path(part).name == measurement.with_suffix(".o").name]
        archived = Path(link[index]).with_suffix(".c")
        restore.digest(archived, "4f3326eee5522f02ee05a236f22a41fc1af5bb0f21b6e3fe337711a66226f5f7")
        restore.digest(restore.HERE / "receiver_resident_cancel.h",
                       "e076929cd8e57eb5e296bbd7f2f355af931ef89a3084dd7b708a739756b0988c")
        measurement.write_text(receiver_fractional_exact.deferred_measurement(archived.read_text()))
        commands.append(compiled(measurement))
        link[index] = str(measurement.with_suffix(".o"))
    binary = work / ("selected.so" if defer else "exact.so")
    exact_command = run([*link, binary], cwd=restore.PINNED)
    added = {("T", name) for name in (
        "experimental_exact_fractional_score", "experimental_repair_fractional_selection",
    )} if defer else set()
    if set(exports(binary)) != set(exports(combined)) | added:
        raise ValueError("Exact fractional verification changed the receiver ABI")
    result = dict(
        parent_sha256=PARENT_SHA, exact_sha256=restore.digest(binary),
        archived_verifier_sha256=ORIGINAL_SOURCE, verifier_object_sha256=restore.digest(verifier),
        verifier_source_sha256=restore.digest(generated), parent_objects=pins,
        overlay_sources={name: restore.digest(restore.HERE / name) for name in (
            "receiver_fractional_exact.py", "receiver_fractional_exact.inc",
            "receiver_phase_free_verify.inc", "receiver_stencil_verify.inc",
        )},
        compiler=subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
        cwd=str(restore.PINNED), commands=[*commands, exact_command],
    )
    if defer:
        result["measurement_source_sha256"] = restore.digest(measurement)
        result["measurement_object_sha256"] = restore.digest(measurement.with_suffix(".o"))
        result["overlay_sources"]["receiver_fractional_selected.inc"] = restore.digest(
            restore.HERE / "receiver_fractional_selected.inc",
        )
    (work / "build.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def build_selected(work, bench):
    return build(work, bench, defer=True)


def selected_bytes(readout):
    _, selected, _ = readout["continuation"]
    return b"" if selected is None else native.factor_bytes([readout["factors"][selected]])


def compare(work, assets, groups):
    build_doc = json.loads((work / "build.json").read_bytes())
    paths = dict(parent=work / "parent.so", exact=work / "exact.so",
                 deployed=assets / "cancellation-factors.so")
    pins = dict(parent=PARENT_SHA, exact=build_doc["exact_sha256"], deployed=native.SHA256["deployed"])
    for arm, path in paths.items():
        restore.digest(path, pins[arm])
    with ExitStack() as stack:
        radios = {}
        for edge in ("lower", "upper"):
            asset = assets / f"{edge}.f32"
            restore.digest(asset, PINS[asset.name])
            template = np.fromfile(asset, dtype="<f4")
            for label, path in paths.items():
                radio = Receiver(path, template)
                stack.callback(radio.close)
                radios[edge, label] = radio
        batches = {label: native.measure(rows, radios, ARMS, COMPARISONS, cycles=2)
                   for label, rows in groups.items()}
    for batch in batches.values():
        for base, other in COMPARISONS:
            receipt = batch["paired"][f"{base}_to_{other}"]
            receipt["counts"]["selected_factor_changed"] = sum(
                selected_bytes(row["arms"][base]) != selected_bytes(row["arms"][other])
                for row in batch["rows"]
            )
        batch["factor_count"] = {arm: sum(len(row["arms"][arm]["factors"]) for row in batch["rows"])
                                 for arm in ARMS}
        batch["selection_count"] = {arm: sum(bool(selected_bytes(row["arms"][arm])) for row in batch["rows"])
                                    for arm in ARMS}
    return dict(binaries=pins, samples=batches)


def saved(work, assets, weak, archive, source_audit, wide_reference):
    return compare(work, assets, native.inputs(weak, archive, source_audit, wide_reference))


def dense(work, assets, pair, baseline, candidate, binding, bulk):
    batch = json.loads(lineage.pin(pair, TERMINAL_PAIR))
    rows = lineage.saved_rows(baseline, "baseline", batch)
    source = json.loads(lineage.pin(candidate, TERMINAL_DETECTION))["source"]
    if source["raw_recording_authority_digest"] != batch["runs"]["candidate"]["raw_authority"]:
        raise ValueError("Historical receiver publication and paired raw authority disagree")
    earlier = {(row["visit_index"], row["receiver_id"]): row for row in source["probes"]
               if (row["visit_index"], row["receiver_id"]) in rows}
    if earlier.keys() != rows.keys():
        raise ValueError("Historical receiver publication is missing selected lanes")
    windows = lineage.load_samples(binding, bulk, batch, rows)
    group = []
    for visit, row in sorted(windows.items()):
        saved = rows[visit, row["lane"]]
        meta = dict(receiver_id=row["lane"], channel=row["channel"],
                    actual_rf_hz=saved["actual_rf_hz"], valid_start_counter=saved["valid_start_counter"])
        group.append(("DS30-0008", str(visit), "lower", row["center"], row["iq_sha256"],
                      meta, row["samples"]))
    receipt = compare(work, assets, {"DS30-0008-regressions": group})
    receipt["archived_pair_sha256"] = TERMINAL_PAIR
    receipt["archived_detections"] = dict(baseline=lineage.DETECTION_PINS["baseline"],
                                           terminal_guard=TERMINAL_DETECTION)
    for row in receipt["samples"]["DS30-0008-regressions"]["rows"]:
        key = int(row["key"]), row["receiver_id"]
        baseline_pick, = rows[key]["candidates"]
        terminal_pick, = earlier[key]["candidates"]
        if baseline_pick["candidate_rank"] != terminal_pick["candidate_rank"]:
            raise ValueError(f"The earlier publication retained a different rank at {key}")
        for arm, pick in (("deployed", baseline_pick), ("exact", baseline_pick), ("parent", terminal_pick)):
            retained = tuple(pick[name] for name in lineage.FIELDS)
            same_rank, = (record for record in row["arms"][arm]["factors"] if record[0] == retained[0])
            if native.factor_bytes([same_rank]) != native.factor_bytes([retained]):
                raise ValueError(f"The archived chronological selection differs at {key} on {arm}")
        row["archived_continuation_retention"] = dict(baseline=baseline_pick, terminal_guard=terminal_pick)
    return receipt


def physical(work, selection_work, assets, binding, bulk):
    """Time one historical 128-visit prefix with independently replayed histories."""
    paths = dict(parent=work / "parent.so", exact=work / "exact.so",
                 selected=selection_work / "selected.so", deployed=assets / "cancellation-factors.so")
    pins = {arm: json.loads((folder / "build.json").read_bytes())["exact_sha256"]
            for arm, folder in (("exact", work), ("selected", selection_work))}
    pins.update(parent=PARENT_SHA, deployed=native.SHA256["deployed"])
    for arm, path in paths.items():
        restore.digest(path, pins[arm])
    restore.digest(binding, PHYSICAL_BINDING)
    original = list(read_physical(binding, bulk, 128))
    if len(original) != 116:
        raise ValueError("Unexpected capture-quality eligibility on the 128-visit prefix")
    iq = digest(json.dumps([row["sha256"] for row, _ in original]).encode())
    if iq != PHYSICAL_IQ:
        raise ValueError("The historical I/Q prefix differs from the previous chronological experiment")
    with ExitStack() as stack:
        radios = {}
        for edge in sorted({row["edge"] for row, _ in original}):
            asset = assets / f"{edge}.f32"
            restore.digest(asset, PINS[asset.name])
            template = np.fromfile(asset, dtype="<f4")
            for arm, path in paths.items():
                radio = Receiver(path, template)
                stack.callback(radio.close)
                radios[edge, arm] = radio
        trials = [physical_repeat(original, radios, tuple(paths), repeat) for repeat in range(4)]
    selection = trials[0]["selection"]
    if not selection or any(trial["selection"] != selection for trial in trials):
        raise ValueError("Chronological selection changed between balanced repeats")
    return dict(binaries=pins, visits=128, eligible=len(original), iq_sha256=iq, trials=trials,
                median_cpu_ns={arm: median(t["native_cpu_ns"][arm] for t in trials) for arm in paths},
                median_repair_cpu_ns=median(t["repair_cpu_ns"] for t in trials),
                median_repaired_factor_cpu_ns=median(t["repair_cpu_ns"] / t["counts"]["repairs"] for t in trials),
                selected_over_parent=median((t["native_cpu_ns"]["selected"] + t["repair_cpu_ns"])
                                            / t["native_cpu_ns"]["parent"] - 1 for t in trials),
                all_over_parent=median(t["native_cpu_ns"]["exact"] / t["native_cpu_ns"]["parent"] - 1
                                       for t in trials))


def physical_repeat(original, radios, arms, repeat):
    cpu = dict.fromkeys(arms, 0)
    history = {arm: Continuation() for arm in arms}
    counts = Counter()
    selected = []
    repair_ns = 0
    for index, (row, samples) in enumerate(original):
        acq, target = row["acquisition"], row["target"]
        actual = acq["actual_if_center_hz"] + target["lnb_lo_hz"]
        center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
        for lane in (0, 1):
            offset = (index * 2 + lane + repeat) % len(arms)
            factors, choices, kept = {}, {}, {}
            for arm in arms[offset:] + arms[:offset]:
                receiver = radios[row["edge"], arm]
                factors[arm], elapsed, _ = receiver.timed(samples, lane, center)
                cpu[arm] += elapsed
                choices[arm] = history[arm].select(dict(
                    receiver_id=lane, channel=target["channel"], actual_rf_hz=actual,
                    valid_start_counter=acq["sample_start"],
                    candidates=[receiver.criteria(*factor) for factor in factors[arm]],
                ))
                _, winner, _ = choices[arm]
                if winner is None:
                    kept[arm] = ()
                    continue
                row_factor = factors[arm][winner]
                if arm == "selected":
                    repair = lineage.bind(receiver.lib, "experimental_repair_fractional_selection", ct.c_int,
                                          ct.c_void_p, ct.POINTER(Factor))
                    repaired = Factor(*row_factor)
                    pointer = ct.byref(repaired)
                    start = process_time_ns()
                    status = repair(receiver.ctx, pointer)
                    repair_ns += process_time_ns() - start
                    if status not in (0, 1):
                        raise ValueError(f"Selected row cannot be repaired: {row['key']} / {lane}")
                    counts["repairs"] += status
                    row_factor = tuple(getattr(repaired, name) for name, _ in Factor._fields_)
                kept[arm] = (row_factor,)
            checks = (("exact", "deployed"), ("selected", "parent"))
            for left, right in checks:
                counts[f"{left}_ordered_factor_different"] += (
                    native.factor_bytes(factors[left]) != native.factor_bytes(factors[right])
                )
            counts["continuation_different"] += any(choice != choices["deployed"] for choice in choices.values())
            counts["exact_selected_different"] += native.factor_bytes(kept["exact"]) != native.factor_bytes(kept["deployed"])
            counts["repaired_selected_different"] += native.factor_bytes(kept["selected"]) != native.factor_bytes(kept["deployed"])
            counts["deployed_factors"] += len(factors["deployed"])
            if kept["deployed"]:
                preferred, chosen, votes = choices["deployed"]
                selected.append(dict(visit=row["acquisition"]["global_visit"], lane=lane, preferred=preferred,
                                     selected=chosen, votes=votes, factor=kept["deployed"][0]))
    return dict(native_cpu_ns=cpu, repair_cpu_ns=repair_ns, counts=counts, selection=selected)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in ((build, ("work", "bench")), (build_selected, ("work", "bench")),
                            (saved, ("work", "assets", "weak", "archive", "source_audit", "wide_reference")),
                            (dense, ("work", "assets", "pair", "baseline", "candidate", "binding", "bulk")),
                            (physical, ("work", "selection_work", "assets", "binding", "bulk"))):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for name in fields:
            command.add_argument(name, type=lambda value: Path(value).resolve())
    arguments = vars(parser.parse_args())
    handler = arguments.pop("handler")
    arguments.pop("action")
    print(json.dumps(handler(**arguments), allow_nan=False, indent=2))
