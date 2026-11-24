"""Compare complete signed ordinary-archive acquisition with stable output staging."""

import argparse
from contextlib import contextmanager, nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch

from . import cross_lag_eight_ms as stage, live_stereo_0008 as live
from . import sealed_stream
from .eight_ms_primary import write
from .four_frame_primary import reference
from .scout_readout_trial import check_machine
from .signed_ingress_reuse import AcquisitionCosts, measured_ingress


ORDERS = (("original", "slab"), ("slab", "original"))
PROTOCOL = Path(__file__).with_name("sealed-stream-protocol.md")


@contextmanager
def installed_symbols():
    import empty_bootstrap as boot
    from unified_short_bootstrap import receiver_import
    from tools.pipeline_eval import variants

    sources = {name: boot.checked(boot.PAYLOAD / name, pin) for name, pin in boot.EXTRA_SOURCES.items()}
    continuation = ModuleType("tools.pipeline_eval.variants.carrier_continuation")
    continuation.__file__ = str(boot.PAYLOAD / boot.CONTINUATION)
    exec(compile(sources[boot.CONTINUATION], continuation.__file__, "exec"), vars(continuation))
    name = boot.RECEIVER.removesuffix(".py").replace("/", ".")
    with patch.object(variants, "carrier_continuation", continuation, create=True):
        symbols = boot.receiver_symbols(sources)
    with receiver_import(name, symbols):
        yield


def worker(path, case, arm, build, build_pin):
    from full_short_run import checked_recipe
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from leo.storage.short_window import ShortWindowReader
    from mixed_aperture_receiver import MixedApertureDetector

    sources = live.original
    member, manifest, chunk = stage.assignment(case)
    if member.resolve(strict=True) != member or not member.is_relative_to("/dev/shm"):
        raise ValueError("Only the already staged original may be read")
    allowed = {chunk["index_relative_path"]: (chunk["index_bytes"], chunk["index_sha256"]),
               chunk["payload_relative_path"]: (chunk["compressed_bytes"], chunk["compressed_sha256"])}
    opened = []
    member_port = ShortWindowReader._member

    def stock_member(reader, name, size, pin):
        if reader.path != member or allowed.get(name) != (size, pin) or name in opened:
            raise ValueError("The original reader accessed a different signed member")
        opened.append(name)
        return member_port(reader, name, size, pin)

    spec = json.loads(sources.verified(sources.PAYLOAD / "spec.json", sources.SPEC_SHA))
    paired = sources.PAYLOAD / "paired-sha256.so"
    sources.verified(paired, spec["paired_sha256"]["sha256"])
    stock = sources.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    costs = AcquisitionCosts()
    stats = {}
    deployed = arm == "original"
    scope = patch.object(ShortWindowReader, "_member", stock_member) if deployed else +        patch.object(live, "paired_decoded_hashes", lambda _: nullcontext())

    @contextmanager
    def ingress():
        if deployed:
            with measured_ingress(stock, costs):
                yield
        else:
            recipe = json.loads(sources.verified(build / "build.json", build_pin))
            binary = build / "sealed-stream.so"
            sources.verified(binary, recipe["sha256"])
            with stock(), sealed_stream.sealed_windows(sealed_stream.Native(binary), paired, member, chunk, stats):
                yield

    recipe = checked_recipe(eight_ms=True)
    with installed_symbols(), scope:
        acquired, probes = live.receive("unmasked", stage.EIGHT, manifest, ingress,
            create_mixer=lambda: MixedApertureDetector(stage.EIGHT, stage.EIGHT_SHA, full_coverage=True),
            detector_pin=canonical_digest(recipe))
    calls = {"full": 16, "short_primary": 112 if case == "0008" else 86}
    if acquired["chunk"] != chunk or acquired["issued"] != 64 or acquired["receiver"]["native_calls"] != calls:
        raise ValueError("Original issued scope or stereo receiver schedule changed")
    if deployed and (set(opened) != set(allowed) or costs.decoded_members != [chunk["uncompressed_sha256"]]):
        raise ValueError("The original member integrity checks did not complete")
    if not deployed and (stats.get("fallback") or stats.get("decoded_sha256") != chunk["uncompressed_sha256"]
                         or stats["compressed_bytes"] != chunk["compressed_bytes"]
                         or stats["decoded_bytes"] != chunk["uncompressed_bytes"] or stats["windows"] != 64):
        raise ValueError("Neither a fallback nor incomplete decode qualifies on this original member")
    path.mkdir()
    packet = dict(acquisition=acquired, probes=probes, manifest=manifest, receiver_recipe=recipe,
                  costs=costs.receipt() if deployed else stats)
    immutable_json(path / "signed.json", packet)
    sources.verified(path / "signed.json", canonical_digest(packet))


def launch(output, case, build):
    from leo.contracts.digests import canonical_digest
    from short_raw_diagnostic import measure

    host = check_machine()
    if output.parent.resolve() != Path("/dev/shm") or not build.resolve(strict=True).is_relative_to("/dev/shm"):
        raise ValueError("Use a new tmpfs output and the declared tmpfs build")
    original, _, input_pin = reference(case)
    expected = canonical_digest(original)
    build_pin = sealed_stream.binary_digest(build / "build.json")
    output.mkdir()
    pairs = []
    for index, order in enumerate(ORDERS):
        runs = {}
        for arm in order:
            target = output / f"{index}-{arm}"
            before = stage.residency(case)
            command = [sys.executable, "-Bm", "reports.ALGO08.v3.sealed_stream_trial", "worker", str(target), case,
                       str(build), "--arm", arm, "--build-pin", build_pin]
            clock = measure(command, dict(os.environ), target)
            after = stage.residency(case)
            if clock["exit_code"]:
                raise RuntimeError(clock["stderr_tail"])
            raw = target / "signed.json"
            record = json.loads(raw.read_bytes())
            if canonical_digest(record["probes"]) != expected or record["acquisition"]["ordered_input_sha256"] != input_pin:
                raise ValueError("Original ordered signed probe or I/Q identity changed")
            runs[arm] = dict(entry=clock, before=before, after=after, result=record,
                             sealed_sha256=sealed_stream.binary_digest(raw))
        first, second = (runs[arm]["result"]["acquisition"] for arm in ORDERS[0])
        for key in ("chunk", "exclusions", "issued", "admitted", "analysis_sha256"):
            if first[key] != second[key]:
                raise ValueError(f"The candidate changed the signed acquisition boundary on {key}")
        cpu, wall = (first["timing"][key] - second["timing"][key] for key in ("cpu_ns", "wall_ns"))
        cpu_percent = cpu / first["timing"]["cpu_ns"] * 100
        pairs.append(dict(order=order, runs=runs, cpu_saving_ns=cpu, wall_saving_ns=wall,
                          cpu_percent=cpu_percent, passes=cpu_percent > 5 and wall > 0))
    write(output / "result.json", dict(case=case, host=host, pairs=pairs, ordered_probe_sha256=expected,
            passed=all(pair["passes"] for pair in pairs), build_sha256=build_pin,
            source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("worker", "launch"))
    parser.add_argument("path", type=Path)
    parser.add_argument("case", choices=("0008", "0169"))
    parser.add_argument("build", type=Path)
    parser.add_argument("--arm", choices=ORDERS[0])
    parser.add_argument("--build-pin")
    args = parser.parse_args()
    if args.mode == "launch":
        launch(args.path, args.case, args.build)
    else:
        worker(args.path, args.case, args.arm, args.build, args.build_pin)
