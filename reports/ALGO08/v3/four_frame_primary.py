"""Measure a fully supported four-origin primary on two signed first members."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from statistics import median
import sys
from unittest.mock import patch

from . import cross_lag_eight_ms as first_member
from . import eight_ms_primary as primary
from . import live_stereo_0008 as live
from .mixed_aperture_receiver import strongest
from .scout_readout_trial import check_machine
from .short_signed_trial import PERIOD, geometry


ARM = "four"
FRAMES = 4
SAMPLES = 66_444
ORDERS = (("eight", ARM), (ARM, "eight"))
WORK = Path("/tmp/leo-algo08v2-2x-bench")
FULL = {
    "0008": (live.ARCHIVE, "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"),
    "0169": (first_member.CURRENT / "1-stock.json",
             "b1d8a32033373c5996217fe3a70e9e7fe5ae58ba3f75439052eacd2ff55cb453"),
}
PROTOCOL = Path(__file__).with_name("four-frame-primary-protocol.md")


def shape():
    required = max(value for key, value in geometry(SAMPLES, FRAMES).items() if key.startswith("first_unused"))
    if SAMPLES != (required + 3) // 4 * 4:
        raise ValueError("The frozen aperture must be the shortest stride-four complete shape")
    return primary.checked_shape(SAMPLES, FRAMES)


def build(output):
    shape()
    primary.build(WORK, output, live.original.PAYLOAD / "receiver.so", live.original.RELEASE / "assets",
                  shapes={ARM: (SAMPLES, FRAMES)})


def paired_row(left, right):
    if ({k: v for k, v in left.items() if k != "candidates"}
            != {k: v for k, v in right.items() if k != "candidates"}):
        raise ValueError("Probe opportunity, antenna, clock, channel or sample identity changed")


def error(left, right):
    if left is None or right is None:
        return None
    t = "fractional_epoch_offset_samples"
    a, b = left["integer_epoch_sample"] + left[t], right["integer_epoch_sample"] + right[t]
    return (math.remainder(b - a, PERIOD),
            right["fractional_tracking_cfo_hz"] - left["fractional_tracking_cfo_hz"])


def hit(residual):
    return residual is not None and abs(residual[0]) <= 2 and abs(residual[1]) <= 250


def statistics(values):
    values = sorted(abs(value) for value in values)
    if not values:
        return None
    return dict(n=len(values), median=median(values), p90=values[math.ceil(0.9*len(values))-1],
                rms=math.sqrt(math.fsum(x*x for x in values)/len(values)), maximum=values[-1])


def scientific_gate(eight, four, full):
    anchors = {(row["visit_index"], row["receiver_id"]) for row in first_member.anchor_lanes(eight)}
    counts = [Counter(), Counter()]
    errors = {name: [] for name in ("eight_four", "full_eight_common", "full_four_common", "full_four")}
    details = []
    for a, b, c in zip(eight, four, full, strict=True):
        paired_row(a, b)
        paired_row(a, c)
        lane = (a["visit_index"], a["receiver_id"])
        if lane in anchors:
            if a != b:
                raise ValueError("Original two-scan anchor bytes changed")
            continue
        old, new, reference = (strongest(row["candidates"]) for row in (a, b, c))
        old_new, full_old, full_new = error(old, new), error(reference, old), error(reference, new)
        matched_8, matched_full_8, matched_full_4 = map(hit, (old_new, full_old, full_new))
        tally = counts[lane[1]]
        tally.update(lanes=1, eight=bool(old), four=bool(new), full=bool(reference),
                     eight_retained=matched_8, full_eight=matched_full_8, full_four=matched_full_4,
                     full_retained=matched_full_8 and matched_full_4,
                     strong_eight_loss=bool(old and old["fractional_margin"] >= 0.10 and not matched_8),
                     newly_positive=bool(new and not old), became_empty=bool(old and not new))
        if matched_8:
            errors["eight_four"].append(old_new)
        if matched_full_4:
            errors["full_four"].append(full_new)
        if matched_full_8 and matched_full_4 and matched_8:
            errors["full_eight_common"].append(full_old)
            errors["full_four_common"].append(full_new)
        details.append(dict(visit=lane[0], antenna=lane[1], eight_to_four=old_new, full_to_eight=full_old,
                            full_to_four=full_new, signed_eight_match=matched_8,
                            signed_full_eight_match=matched_full_8, signed_full_four_match=matched_full_4))
    summaries = {name: dict(epoch_samples=statistics(row[0] for row in values),
                            cfo_hz=statistics(row[1] for row in values)) for name, values in errors.items()}
    common = summaries["full_four_common"]["cfo_hz"]
    original = summaries["full_eight_common"]["cfo_hz"]
    direct = summaries["eight_four"]["cfo_hz"]
    gates = dict(
        eight_support=all(lane["eight"] > 0 and 10*lane["eight_retained"] >= 9*lane["eight"] for lane in counts),
        eight_strong=all(not lane["strong_eight_loss"] for lane in counts),
        full_support=all(10*lane["full_retained"] >= 9*lane["full_eight"] for lane in counts),
        common_support=common is not None and common["n"] >= 3,
        cfo_eight=direct is not None and direct["p90"] <= 200,
        cfo_full=common is not None and common["rms"] <= max(70, 1.25*original["rms"]),
    )
    return dict(passed=all(gates.values()), gates=gates, antennas=counts, residuals=summaries, differences=details)


def reference(case):
    from leo.contracts.digests import canonical_digest

    eight_path, eight_pin = first_member.ARCHIVES[case]
    full_path, full_pin = FULL[case]
    eight = json.loads(live.original.verified(eight_path, eight_pin))
    full = json.loads(live.original.verified(full_path, full_pin))
    if case == "0169":
        if eight["iq"] != full["iq"] or len(full["iq"]) != 64:
            raise ValueError("The installed full reference must bind exactly the same original first-member samples")
        sample_pin = canonical_digest(list(enumerate(full["iq"])))
        eight = eight["packet"]["source"]
        full = full["packet"]
    else:
        sample_pin = eight["sample_sha256"]
    if full["source"]["probe_ms"] != 20:
        raise ValueError("The reference must be the original full 20 ms receiver")
    full_probes = [row for row in full["source"]["probes"] if row["visit_index"] < 64]
    for left, right in zip(eight["probes"], full_probes, strict=True):
        paired_row(left, right)
    return eight["probes"], full_probes, sample_pin


def binary_recipe(arm, artifacts, build_pin):
    from full_short_run import checked_recipe

    recipe = checked_recipe(eight_ms=True)
    binary, pin = first_member.EIGHT, first_member.EIGHT_SHA
    if arm == ARM:
        build = json.loads(live.original.verified(artifacts / "build.json", build_pin))
        if build["geometry"] != {ARM: shape()}:
            raise ValueError("The native artifact does not use the frozen four-frame geometry")
        binary, pin = artifacts / ARM / "short-primary.so", build["primary"][ARM]["binary_sha256"]
        recipe.update(shortened_sha256=pin, aperture_samples=[200_000, SAMPLES])
    live.original.verified(binary, pin)
    return binary, pin, recipe


def worker(output, case, arm, artifacts, build_pin):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from leo.storage.short_window import ShortWindowReader
    from mixed_aperture_receiver import MixedApertureDetector

    source = live.original
    member, manifest, chunk = first_member.assignment(case)
    if member.resolve(strict=True) != member or not member.is_relative_to("/dev/shm"):
        raise ValueError("The assigned original first member must be staged on tmpfs")
    paths = {chunk["index_relative_path"]: (chunk["index_bytes"], chunk["index_sha256"]),
             chunk["payload_relative_path"]: (chunk["compressed_bytes"], chunk["compressed_sha256"])}
    read = ShortWindowReader._member
    opened = []

    def allow(reader, name, size, digest):
        if reader.path != member or paths.get(name) != (size, digest) or name in opened:
            raise ValueError("A read escaped the one prescribed signed member")
        opened.append(name)
        return read(reader, name, size, digest)

    specification = json.loads(source.verified(source.PAYLOAD / "spec.json", source.SPEC_SHA))
    source.verified(source.PAYLOAD / "paired-sha256.so", specification["paired_sha256"]["sha256"])
    ingress = source.frozen_function(specification, "receiver_ingress.py", "compressed_input_buffer")
    binary, pin, recipe = binary_recipe(arm, artifacts, build_pin)
    with patch.object(live, "MEMBER", member), patch.object(ShortWindowReader, "_member", allow):
        acquired, probes = live.receive("unmasked", binary, manifest, ingress,
            create_mixer=lambda: MixedApertureDetector(binary, pin, full_coverage=True),
            detector_pin=canonical_digest(recipe))
    short = 86 if case == "0169" else 112
    if (set(opened) != set(paths) or acquired["chunk"] != chunk or acquired["issued"] != 64
            or acquired["receiver"]["native_calls"] != {"full": 16, "short_primary": short}):
        raise ValueError("Authenticated coverage, stereo lanes or the two-scan anchors changed")
    output.mkdir()
    sealed = output / "signed.json"
    packet = dict(probes=probes, acquisition=acquired, recipe=recipe, opened=opened, manifest=manifest)
    immutable_json(sealed, packet)
    source.verified(sealed, canonical_digest(packet))


def launch(root, case, artifacts):
    from short_raw_diagnostic import measure

    machine = check_machine()
    if root.parent.resolve() != Path("/dev/shm") or not artifacts.resolve(strict=True).is_relative_to("/dev/shm"):
        raise ValueError("Use a new tmpfs result and a pinned tmpfs build")
    build_pin = sha256((artifacts / "build.json").read_bytes()).hexdigest()
    _, pin, _ = binary_recipe(ARM, artifacts, build_pin)
    archive, full, sample_pin = reference(case)
    anchors = list(first_member.anchor_lanes(archive))
    if len(anchors) != 16:
        raise ValueError("Expected all 16 reference two-scan anchor lanes")
    root.mkdir()
    comparisons, candidate_probes = [], None
    for number, order in enumerate(ORDERS):
        runs = {}
        for arm in order:
            path = root / f"{number}-{arm}"
            before = first_member.residency(case)
            command = [sys.executable, "-Bm", "reports.ALGO08.v3.four_frame_primary", "worker",
                       str(path), str(artifacts), "--case", case, "--arm", arm, "--build-pin", build_pin]
            process = measure(command, dict(os.environ), path)
            after = first_member.residency(case)
            if process["exit_code"]:
                raise RuntimeError(process["stderr_tail"])
            sealed = path / "signed.json"
            runs[arm] = dict(process=process, packet=json.loads(sealed.read_bytes()),
                             signed_sha256=sha256(sealed.read_bytes()).hexdigest(), before=before, after=after)
        eight, four = (runs[arm]["packet"] for arm in ORDERS[0])
        if eight["probes"] != archive or eight["acquisition"]["ordered_input_sha256"] != sample_pin:
            raise ValueError("The ordinary eight-millisecond arm failed to reproduce its signed prior identity")
        if list(first_member.anchor_lanes(four["probes"])) != anchors:
            raise ValueError("The original two-scan anchors failed exact parity")
        if candidate_probes is not None and candidate_probes != four["probes"]:
            raise ValueError("Candidate factors changed between reversed measured orders")
        candidate_probes = four["probes"]
        a, b = eight["acquisition"], four["acquisition"]
        for key in ("ordered_input_sha256", "exclusions", "admitted", "issued", "probes", "chunk"):
            if a[key] != b[key]:
                raise ValueError(f"Both acquisitions must match on {key}")
        native = a["receiver"]["native_cpu_ns"]["short_primary"] - b["receiver"]["native_cpu_ns"]["short_primary"]
        paid = a["timing"]["cpu_ns"] - b["timing"]["cpu_ns"]
        comparisons.append(dict(order=order, runs=runs, short_native_cpu_saving_ns=native,
                                acquisition_cpu_saving_ns=paid))
    science = scientific_gate(archive, candidate_probes, full)
    faster = all(pair["short_native_cpu_saving_ns"] > 0 and pair["acquisition_cpu_saving_ns"] > 0
                 for pair in comparisons)
    primary.write(root / "result.json", dict(case=case, machine=machine, faster=faster, science=science,
        passed=faster and science["passed"], comparisons=comparisons, full_reference=full,
        full_reference_sha256=FULL[case][1], eight_reference_sha256=first_member.ARCHIVES[case][1],
        build_sha256=build_pin, binary_sha256=pin, geometry=shape(),
        protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("build", "launch", "worker"))
    cli.add_argument("output", type=Path)
    cli.add_argument("artifacts", type=Path, nargs="?")
    cli.add_argument("--case", choices=FULL)
    cli.add_argument("--arm", choices=ORDERS[0])
    cli.add_argument("--build-pin")
    args = cli.parse_args()
    if args.mode == "build":
        build(args.output)
    elif args.mode == "launch":
        launch(args.output, args.case, args.artifacts)
    else:
        worker(args.output, args.case, args.arm, args.artifacts, args.build_pin)
