"""Measure scoped verifier staging at complete original member acquisition."""

import argparse
from contextlib import nullcontext
import ctypes as ct
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

from . import cross_lag_eight_ms as first_member
from . import live_stereo_0008 as live
from .eight_ms_primary import write
from .four_frame_primary import reference
from .scout_readout_trial import check_machine
from .verifier_pilot_support import digest


ORDERS = (("original", "support"), ("support", "original"))
PROTOCOL = Path(__file__).with_name("verifier-pilot-support-protocol.md")


def worker(output, case, arm, artifacts, build_pin):
    from full_short_run import checked_recipe
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from leo.storage.short_window import ShortWindowReader
    import mixed_aperture_receiver as mixed

    source = live.original
    member, manifest, chunk = first_member.assignment(case)
    if member.resolve(strict=True) != member or not member.is_relative_to("/dev/shm"):
        raise ValueError("The original signed member must already be staged privately")
    allowed = {chunk["index_relative_path"]: (chunk["index_bytes"], chunk["index_sha256"]),
               chunk["payload_relative_path"]: (chunk["compressed_bytes"], chunk["compressed_sha256"])}
    original_member = ShortWindowReader._member
    opened = []

    def admit(reader, name, size, digest):
        if reader.path != member or allowed.get(name) != (size, digest) or name in opened:
            raise ValueError("A read escaped the one staged signed member")
        opened.append(name)
        return original_member(reader, name, size, digest)

    recipe = checked_recipe(eight_ms=True)
    short, pin = first_member.EIGHT, first_member.EIGHT_SHA
    engines, executed = {}, {"full": mixed.INSTALLED_SHA, "short": pin}
    replacement = nullcontext()
    if arm == "support":
        build = json.loads(source.verified(artifacts / "build.json", build_pin))
        native = {mode: artifacts / mode / "support.so" for mode in ("full", "short")}
        executed = {mode: row["candidate"] for mode, row in build["binaries"].items()}
        for mode, path in native.items():
            source.verified(path, executed[mode])
        short, pin = native["short"], executed["short"]
        recipe = dict(recipe, verifier_pilot_support=executed)
        stock = mixed.NativePath

        def configure(path, asset, mode):
            key = "short" if mode == "short_primary" else "full"
            engine = stock(native[key], asset, mode)
            engines[key] = engine.native.lib
            return engine

        replacement = patch.object(mixed, "NativePath", configure)
    specification = json.loads(source.verified(source.PAYLOAD / "spec.json", source.SPEC_SHA))
    source.verified(source.PAYLOAD / "paired-sha256.so", specification["paired_sha256"]["sha256"])
    ingress = source.frozen_function(specification, "receiver_ingress.py", "compressed_input_buffer")
    with patch.object(live, "MEMBER", member), patch.object(ShortWindowReader, "_member", admit), replacement:
        acquired, probes = live.receive("unmasked", short, manifest, ingress,
            create_mixer=lambda: mixed.MixedApertureDetector(short, pin, full_coverage=True),
            detector_pin=canonical_digest(recipe))
    native_calls = {"full": 16, "short_primary": 112 if case == "0008" else 86}
    if (acquired["receiver"]["native_calls"] != native_calls or acquired["issued"] != 64
            or acquired["chunk"] != chunk or set(opened) != set(allowed)):
        raise ValueError("Original full anchors, verified stereo coverage or archive scope changed")
    support = {}
    for mode, library in engines.items():
        count = (ct.c_uint64 * 3)()
        stats = library.portable_verifier_support_counts
        stats.argtypes = [ct.POINTER(ct.c_uint64), ct.c_int]
        stats.restype = None
        stats(count, 1)
        loads, written, fallback = count
        maximum = loads * (200_000 if mode == "full" else 80_000)
        if not loads or not 0 < written <= maximum or fallback > loads:
            raise ValueError("Expected paid verifier loads and bounded support accounting")
        support[mode] = dict(loads=loads, converted=written, original=maximum, wrap_fallback=fallback)
    output.mkdir()
    packet = dict(probes=probes, acquisition=acquired, recipe=recipe, native_executed_sha256=executed,
                  original_manifest=manifest, opened=opened, support=support)
    destination = output / "signed.json"
    immutable_json(destination, packet)
    source.verified(destination, canonical_digest(packet))


def launch(root, case, artifacts):
    from leo.contracts.digests import canonical_digest
    from short_raw_diagnostic import measure

    machine = check_machine()
    if root.parent.resolve() != Path("/dev/shm") or not artifacts.resolve(strict=True).is_relative_to("/dev/shm"):
        raise ValueError("Use a fresh tmpfs result and the pinned tmpfs build")
    archive, _, input_pin = reference(case)
    expected = canonical_digest(archive)
    build_pin = digest(artifacts / "build.json")
    root.mkdir()
    comparisons = []
    for index, order in enumerate(ORDERS):
        runs = {}
        for arm in order:
            target = root / f"{index}-{arm}"
            before = first_member.residency(case)
            command = [sys.executable, "-Bm", "reports.ALGO08.v3.verifier_pilot_support_trial", "worker",
                       str(target), str(artifacts), case, "--arm", arm, "--build-pin", build_pin]
            clock = measure(command, dict(os.environ), target)
            after = first_member.residency(case)
            if clock["exit_code"]:
                raise RuntimeError(clock["stderr_tail"])
            packet = json.loads((target / "signed.json").read_bytes())
            if canonical_digest(packet["probes"]) != expected or packet["acquisition"]["ordered_input_sha256"] != input_pin:
                raise ValueError("Ordered signed factors, empty lanes or original IQ authority changed")
            runs[arm] = dict(clock=clock, before=before, after=after, packet=packet,
                             sealed_sha256=digest(target / "signed.json"))
        original, support = (runs[mode]["packet"]["acquisition"] for mode in ORDERS[0])
        for key in ("chunk", "admitted", "issued", "exclusions", "probes"):
            if original[key] != support[key]:
                raise ValueError(f"Paid acquisition scope changed on {key}")
        native = [row["receiver"]["native_cpu_ns"] for row in (original, support)]
        comparisons.append(dict(order=order, runs=runs,
            saved_ns=original["timing"]["cpu_ns"] - support["timing"]["cpu_ns"],
            native_saved_ns={key: native[0][key] - native[1][key] for key in native[0]}))
    write(root / "result.json", dict(case=case, machine=machine, comparisons=comparisons,
                                  build_sha256=build_pin, original_probe_sha256=expected,
                                  protocol_sha256=digest(PROTOCOL), source_sha256=digest(Path(__file__))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("worker", "launch"))
    parser.add_argument("path", type=Path)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("case", choices=("0008", "0169"))
    parser.add_argument("--arm", choices=ORDERS[0])
    parser.add_argument("--build-pin")
    args = parser.parse_args()
    if args.mode == "launch":
        launch(args.path, args.case, args.artifacts)
    else:
        worker(args.path, args.case, args.arm, args.artifacts, args.build_pin)
