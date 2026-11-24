"""Pair the ordinary and packed guarded combined CLI on the signed DS30-0016 first member."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from combined_raw_research import main as combined
from continued_cfo_first_0016 import MANIFEST, OFFER, PACK, SEGMENT, SOURCE, WINDOWS, mapped_files, resident
import empty_bootstrap as installed


ORDERS = (("ordinary", "packed"), ("packed", "ordinary"))


def worker(mode, root, destination, map_pin):
    from continued_cfo_small_raw import ROUTE_FLAGS
    from guarded_cfo_small_raw import LIBRARIES

    _, files = mapped_files()
    original_scanner = installed.staged_scanner
    opened = []

    with ExitStack() as scope:
        def scanner(sources, detector=None):
            from leo.contracts.digests import canonical_digest
            from leo.storage.short_window import ShortWindowReader

            scan = original_scanner(sources, detector=detector)
            original_member = ShortWindowReader._member

            def read_member(reader, name, size, digest):
                if reader.path != SEGMENT or files.get(name) != (size, digest):
                    raise ValueError("Physical read outside the one staged member")
                opened.append(name)
                return original_member(reader, name, size, digest)

            class PrefixStore(scan.FastScanStore):
                def inventory(self, recording, *, verify_windows=True):
                    if recording != SEGMENT or verify_windows:
                        raise ValueError("Expected the bounded original acquisition scope")
                    _, _, inventory = super().inventory(recording, verify_windows=False)
                    entry, = inventory["segments"]
                    if entry["path"] != str(SEGMENT) or entry["manifest_digest"] != "sha256:" + MANIFEST:
                        raise ValueError("Source manifest differs from the original first member")
                    prefix = dict(inventory, segments=[dict(entry, windows=WINDOWS)], window_count=WINDOWS,
                                  receiver_test_scope="one original signed DS30-0016 member")
                    digest = canonical_digest(prefix)
                    return "fast-" + digest[7:39], digest, prefix

            class PrefixSource(scan.FastSegmentSource):
                def __init__(self, entry, *, start_sequence=0, stop_sequence=None):
                    stop = WINDOWS if stop_sequence is None else stop_sequence
                    if entry["path"] != str(SEGMENT) or not 0 <= start_sequence < stop <= WINDOWS:
                        raise ValueError("Source attempted to exceed the original first member")
                    super().__init__(entry, start_sequence=start_sequence, stop_sequence=stop)

            scan.FastScanStore = PrefixStore
            scan.FastSegmentSource = PrefixSource
            scope.enter_context(patch.object(ShortWindowReader, "_member", read_member))
            return scan

        scope.enter_context(patch.object(installed, "staged_scanner", scanner))
        installed.checked(SOURCE / "offer.json", OFFER)
        argv = ["--anchored-cfo-pack", PACK, "--recording", SEGMENT, "--archive", SOURCE / "tle",
                "--region", SOURCE / "offer.json", "--output", destination / "publication",
                "--catalogue-block-rank", *ROUTE_FLAGS]
        for flag, name in LIBRARIES.items():
            argv.extend((flag, SOURCE / f"{name}.so"))
        if mode == "packed":
            argv.extend(("--packed-ci16-map", root / "map.json", "--packed-ci16-map-sha256", map_pin,
                         "--packed-ci16-codec", root / "packing.so"))
        combined(list(map(str, argv)))
    expected = list(files) if mode == "ordinary" else []
    if opened != expected:
        raise ValueError(f"Unexpected original member reads for {mode}: {opened}")
    (destination / "opened.json").write_text(json.dumps(opened) + "\n")


def stage(root):
    from ci16_packing import Packing, SOURCE as CODEC_SOURCE
    from leo.storage.short_window import ShortWindowReader
    from packed_combined_input import SCHEMA, now, spent
    from reports.ALGO08.v3.ci16_packed_storage_trial import BUILD
    import seekable_member as seek

    _, files = mapped_files()
    before = resident(files)
    binary = root / "packing.so"
    start = now()
    subprocess.run([*BUILD, str(CODEC_SOURCE), "-o", str(binary)], check=True)
    compiler = spent(start)
    start = now()
    codec = Packing(binary)
    pack = root / "member-000000"
    seek_pin = seek.create(ShortWindowReader(SEGMENT), 0, pack, codec=codec)
    encoding = spent(start)
    mapping = dict(schema=SCHEMA, codec_sha256=seek.digest(binary.read_bytes()),
                   members=[dict(directory=pack.name, manifest_sha256="sha256:" + MANIFEST,
                                 chunk_index=0, seek_sha256=seek_pin)])
    raw = json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode()
    seek.write(root / "map.json", raw)
    return dict(map=mapping, map_sha256=seek.digest(raw), path=str(SEGMENT),
                original_members=files, compiler_wall_ns=compiler["wall_ns"],
                parent_conversion_cpu_ns=encoding["cpu_ns"], conversion_wall_ns=encoding["wall_ns"],
                original_residency=before, packed_file_sizes={p.name: p.stat().st_size for p in pack.iterdir()},
                packed_word_widths=codec.counts(), sources={name: sha256((HERE / name).read_bytes()).hexdigest()
                    for name in ("packed_combined_trial.py", "packed_combined_input.py", "packed-combined-input-protocol.md",
                                 "combined_raw_research.py", "unified_short_bootstrap.py", "seekable_member.py", "ci16_packing.c")})


def evidence(directory, mode):
    import seekable_member as seek

    publication = directory / "publication"
    raw = json.loads((publication / "unified-short-bootstrap.json").read_bytes())
    (native,) = (publication / "fast-scan-automatic-work").glob("*/detections.json")
    native_sha = seek.digest(native.read_bytes())
    (inventory,) = (publication / "fast-scan-inputs").glob("*.json")
    receipt = raw["receipt"]
    terminal_path = publication / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json"
    terminal = json.loads(terminal_path.read_bytes())
    if (native_sha != raw["native_sha256"] or raw["requested_offer_sha256"] != OFFER
            or receipt["decision"] != "withheld" or terminal["reason"] != "no_active_curvature"
            or any(arm["latlon"] is not None for arm in terminal["arms"].values())
            or receipt.get("artifacts") or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1):
        raise ValueError("Expected the ordinary publication guard, original offer and one bound native handoff")
    storage = raw.get("packed_ci16_input")
    if mode == "packed" and (storage is None or storage["fallback"] is not None or storage["original_windows"]
                             or [row["state"] for row in storage["members"]] != ["packed"]):
        raise ValueError("Verified packed input was requested but did not activate")
    native_audit = raw["receiver_audit"]
    times = {key: native_audit["native"][key] for key in ("native_cpu_ns", "native_wall_ns", "cfo_refinement")}
    schedule = dict(native_audit["native"])
    for key in times:
        schedule.pop(key)
    schedule["cfo_counts"] = times["cfo_refinement"]["lanes"]
    return dict(native_sha256=native_sha, inventory_sha256=seek.digest(inventory.read_bytes()),
                held=raw["held_anchor_route"], region=raw["receipt"]["region"], graph=raw["graph_proof"],
                receipt=receipt, terminal=terminal, cutoff=raw["causal_cutoff_utc_ns"],
                authority=native_audit["recording_authority"], schedule=schedule, receiver_phase=times,
                phases=raw["phases"], storage=storage, opened=json.loads((directory / "opened.json").read_bytes()))


def run(root):
    import seekable_member as seek
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm") or os.sched_getaffinity(0) != {2}:
        raise ValueError("Use a fresh tmpfs destination and the shared CPU2 slot")
    root.mkdir(mode=0o700)
    setup = stage(root)
    seek.write(root / "setup.json", json.dumps(setup, sort_keys=True, indent=2).encode() + b"\n")
    pairs = []
    compared = ("native_sha256", "inventory_sha256", "held", "region", "graph", "receipt", "terminal", "cutoff", "authority", "schedule")
    reference = None
    for number, order in enumerate(ORDERS):
        pair = {}
        for mode in order:
            destination = root / f"pair-{number}-{mode}"
            destination.mkdir()
            args = [sys.executable, "-B", str(HERE / "packed_combined_trial.py"), str(root),
                    "--worker", mode, "--destination", str(destination), "--map-pin", setup["map_sha256"]]
            clocks = measure(args, dict(os.environ), destination)
            if clocks["exit_code"]:
                raise ValueError(f"Worker {mode} failed: {clocks['stderr_tail']}")
            result = evidence(destination, mode)
            projection = {key: result[key] for key in compared}
            if reference is None:
                reference = projection
            if projection != reference:
                differing = sorted(key for key in compared if projection[key] != reference[key])
                raise ValueError(f"Packed exactness check failed: {differing}")
            pair[mode] = dict(clocks=clocks, evidence={key: value for key, value in result.items() if key not in compared})
        pairs.append(dict(order=order, measurements=pair))
    _, files = mapped_files()
    receipt = dict(setup=setup, pairs=pairs, common=reference, source_residency_after=resident(files),
                   raw_original_backing_reads=0, scope="one original first DS30-0016 member")
    seek.write(root / "result.json", json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--worker", choices=("ordinary", "packed"))
    cli.add_argument("--destination", type=Path)
    cli.add_argument("--map-pin")
    args = cli.parse_args()
    if args.worker:
        worker(args.worker, args.root, args.destination, args.map_pin)
    else:
        run(args.root)
