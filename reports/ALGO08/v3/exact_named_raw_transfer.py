"""Measure one complete resident North raw pair and one saved omitted offer."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import patch

import exact_named_raw as entry


HERE = Path(__file__).resolve().parent
ORDER = ("named", "candidate", "north-far-saved")
RAW_PACKET = "sha256:77d3552cc660e3492b74bb853e3e88d697e7b7d48751de6085dac3e0320cf47b"
SOURCES = ("exact-named-raw-protocol.md", "exact_named_raw.py", "exact_named_raw_transfer.py",
           "unified_short_bootstrap.py", "exact_named_route.py", "held_adaptive_0160.py", "named_hybrid_baseline.py")


def read(path):
    return json.loads(path.read_bytes())


def pins():
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCES}


def authenticate_packet(root, req, expected, detector):
    from empty_bootstrap import bind_native, checked
    from raw_cfo_north_trial import native_file

    packet = native_file(root)
    native = json.loads(checked(packet, expected.removeprefix("sha256:")))
    bind_native(native, req["session"], req["inventory"], detector, expected=expected)
    if (native["source"]["raw_recording_authority_digest"] != req["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != req["cutoff_utc_ns"]
            or len(native["source"]["probes"]) != 2400):
        raise ValueError("The native packet differs from the enrolled full North acquisition")
    return native


def named(root, binding):
    import empty_bootstrap as boot
    from raw_cfo_north_trial import STOCK_PACKET

    sys.addaudithook(entry.deny_backing(Path(binding["request"]["recording"])))
    launcher, specification, _, publication, checks = boot.load_runtime()
    from tools import algo08_position, algo08_scan

    req, output = binding["request"], root/"named"
    timings, owners = {name: [] for name in ("analyze", "acquire", "solve", "render")}, []
    original_run = publication.run
    receipts = []

    def observed_run(args, spec):
        if spec != specification:
            raise ValueError("The original named launcher must use its unchanged scientific specification")
        result = original_run(args, spec)
        receipts.append(result)
        return result

    output.mkdir()
    started = boot.now()
    with ExitStack() as stack:
        entry.observe(algo08_scan, algo08_position, stack, timings, owners)
        stack.enter_context(patch.object(publication, "run", observed_run))
        launcher["main"](["--recording", req["recording"], "--archive", req["archive"]["root"],
                          "--region", req["inside_offer"], "--bulk-root", str(output)])
    installed = boot.clock(started)
    (receipt,) = receipts
    if any(len(scopes) != 1 for scopes in timings.values()) or read(output/"algo08v3-release.json")["decision"] != "complete":
        raise ValueError("Expected one real complete raw named acquisition, solve and rendering")
    started = boot.now()
    authenticate_packet(output, req, STOCK_PACKET, specification["detector_sha256"])
    verified = entry.evidence(output, receipt, STOCK_PACKET, owners)
    entry.write(output/"named-raw-witness.json", dict(receipt=receipt, evidence=verified, timing=timings,
        installed=installed, checks=checks, verification=boot.clock(started), native_sha256=STOCK_PACKET))


def omitted(root, binding):
    import empty_bootstrap as boot
    from cumulative_grid_projection import saved_inventory_port
    from raw_cfo_north_trial import native_file
    from unified_short_bootstrap import Handoff

    req, positive = binding["request"], root/"candidate"
    raw = read(positive/"unified-short-bootstrap.json")
    if (raw["native_sha256"] != RAW_PACKET or raw["raw_acquisitions"] != 1
            or raw["verified_handoffs"] != 1):
        raise ValueError("The omission must reuse exactly the real authenticated containing packet")
    sys.addaudithook(entry.deny_backing(Path(req["recording"])))
    _, specification, _, publication, _ = boot.load_runtime()
    detector = raw["detector_recipe_sha256"].removeprefix("sha256:")
    native = authenticate_packet(positive, req, RAW_PACKET, detector)
    offer_path = root/"omitted-offer.json"
    boot.checked(offer_path, binding["omitted_offer_sha256"])
    args = entry.parser().parse_args(binding["candidate_args"])
    args.output, args.region = root/"north-far-saved", offer_path
    handoff = Handoff(req["session"], req["inventory"], detector, native)
    with saved_inventory_port(req | {"receiver": "native-20-8-held-history"}) as inventory:
        terminal, _ = entry.publish_active(args, publication, specification, handoff)
    if (not inventory or handoff.calls != 1
            or native_file(args.output).read_bytes() != native_file(positive).read_bytes()):
        raise ValueError("The omission must publish the same verified packet and consume no waveform")
    entry.write(args.output/"saved-omitted-witness.json", dict(raw_acquisitions=0, handoffs=handoff.calls,
                receipt=terminal, native_sha256=RAW_PACKET))


def referenced_binding(root):
    from adaptive_raw_trial import control, work
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from north_combined import assignments

    old_root, previous, seal, _ = control("north")
    req, snapshot = work("north", root)
    if previous["request"] != req or seal["raw"]["native_sha256"] != RAW_PACKET:
        raise ValueError("Changed original signed North or the qualified 20/8 reference")
    command = previous["command"]
    flags = ("--recording", "--archive", "--region", "--short-binary", "--geographic-library",
             "--regional-track-library", "--frontier-block-library", "--portable-orbit-index",
             "--portable-orbit-index-sha256", "--portable-orbit-producer-sha256")
    args = [value for flag in flags for value in (flag, command[command.index(flag)+1])]
    args += ["--archive-sha256", req["archive"]["snapshots_sha256"], "--output", str(root/"candidate")]
    for value in previous["libraries"].values():
        checked(Path(value["path"]), value["sha256"])
    _, offers = assignments()
    omitted = offers["results"]["north-far"]["offer"]
    return old_root, snapshot, omitted, dict(request=req, order=ORDER, machine=host(), sources=pins(),
                                             candidate_args=args, original_omitted=offers["results"]["north-far"])


def launch(root):
    from eight_ms_south_transfer import environment_for
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from short_raw_diagnostic import measure

    old_root, snapshot, omitted_offer, binding = referenced_binding(root)
    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(old_root/"fonts", root/"fonts")
    offer = root/"omitted-offer.json"
    entry.write(offer, omitted_offer)
    binding["omitted_offer_sha256"] = sha256(offer.read_bytes()).hexdigest()
    python = Path(sys.executable)
    prefix = ["/usr/bin/timeout", "--kill-after=2s", "75s", str(python), "-IB"]
    binding["commands"] = {
        "named": [*prefix, str(Path(__file__)), "named", str(root)],
        "candidate": [*prefix, str(HERE/"exact_named_raw.py"), *binding["candidate_args"]],
        "north-far-saved": [*prefix, str(Path(__file__)), "north-far-saved", str(root)],
    }
    entry.write(root/"binding.json", binding)
    env = environment_for(root)
    for name, command in binding["commands"].items():
        cache_before = snapshot() if name != "north-far-saved" else None
        result = measure(command, env, root/name)
        entry.write(root/f"{name}-clock.json", result)
        if cache_before is not None:
            entry.write(root/f"{name}-original-cache.json", dict(before=cache_before, after=snapshot()))
        if result["exit_code"]:
            raise ValueError(f"{name} failed through exit: {result['stderr_tail']}")


if __name__ == "__main__":
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("action", choices=("launch", "named", "north-far-saved"))
    command.add_argument("root", type=Path)
    args = command.parse_args()
    if args.action == "launch":
        launch(args.root)
    else:
        binding = read(args.root/"binding.json")
        if binding["sources"] != pins():
            raise ValueError("The frozen raw comparison sources changed")
        if args.action == "named":
            named(args.root, binding)
        else:
            omitted(args.root, binding)
