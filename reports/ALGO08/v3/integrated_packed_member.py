"""Qualify the new strict port on one already resident original/packed member."""

import argparse
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.append(str(ROOT))
import original_prefix_scaling as prefix

PACK = Path("/dev/shm/leo-v3-strict-cairo-0016-result01")
PACK_PINS = {"conversion.json": "bf45309c533abb57805c9a5d8167c07e06d24252e815bc0e2dd558e5c0c0f3d7",
             "conversion/map.json": "3bf73850eb526bc909ed81c244eb16d6a81f8ea8ec8330ef08fd07be722666e5",
             "packing.so": "ed03bfb0d075d8e94c616a39f0d03ad05f79ab4b37df02cf1fca52127013557e"}
INTEGRATED = "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff"
BASE = Path("/tmp/leo-v3-original-prefix-scaling-0016-result01/binding.json")
BASE_PIN = "a506518c90dd3867b8f2f35af07bd024b44687622c5ca7d506f935b4b44bfe9c"
ORDER = ("ordinary", "packed")


def book():
    from exact_named_raw import staged_path

    roster = json.loads(prefix.pinned(BASE, BASE_PIN))
    assignment = roster["scopes"]["1"]
    scope = assignment["inventory"]["prefix_members"][0]
    for name, expected in PACK_PINS.items():
        prefix.pinned(staged_path(PACK / name, root=staged_path(PACK)), expected)
    prepared = json.loads((PACK / "conversion.json").read_bytes())
    mapping = json.loads((PACK / "conversion/map.json").read_bytes())
    first = mapping["members"][0]
    member = staged_path(PACK / "conversion" / first["directory"], root=PACK)
    if (not prepared["independent_check"] or first["chunk_index"] != 0
            or first["manifest_sha256"] != assignment["inventory"]["segments"][0]["manifest_digest"]):
        raise ValueError("Expected complete independent original decoded readback for the prepared member")
    prefix.pinned(staged_path(member / "seek.json", root=PACK), first["seek_sha256"])
    files = [staged_path(member / name, root=PACK) for name in ("seek.json", "prefix.ci16p", "tail.ci16p",
                                                                "source-manifest.json", "source-index.jsonl")]
    present = HERE / "measurements/integrated-original.json.gz"
    original = json.loads(gzip.decompress(prefix.pinned(present, INTEGRATED)))
    proof = original["runs"]["positive_first"]["DS30-0016"]["result"]["document"]
    if not proof["qualified"] or not proof["checks"]["original_lookahead"]:
        raise ValueError("Expected the qualified integrated original reference")
    return dict(scope=assignment, reference_native=roster["reference_native"], original=roster["original"],
                source=roster["source"], original_paths=[str(p) for p in prefix.files(roster, assignment)],
                packed_paths=[str(p) for p in files], packed=first, raw_sha256=scope["uncompressed_sha256"],
                options=proof["admission"]["command"][6:],
                expected_original_inventory=proof["rebound_request"]["inventory"])


def arguments(assigned, mode, output):
    argv = list(assigned["options"])
    for key, value in (("--recording", assigned["source"]), ("--output", str(output))):
        argv[argv.index(key) + 1] = value
    if mode == "packed":
        for name in ("--legacy-first-map-history", "--legacy-first-map-history-sha256"):
            start = argv.index(name)
            del argv[start:start+2]
        argv.remove("--verify-original-once")
        argv.extend(("--strict-packed-eight", "--packed-ci16-map", str(PACK / "conversion/map.json"),
                     "--packed-ci16-map-sha256", "sha256:" + PACK_PINS["conversion/map.json"],
                     "--packed-ci16-codec", str(PACK / "packing.so")))
    return argv


def worker(output, binding, mode):
    import empty_bootstrap as boot

    from exact_named_raw import staged_path

    source = staged_path(Path(binding["source"]))
    assignment = binding["scope"]
    original_paths = list(map(Path, binding["original_paths"]))
    sys.addaudithook(prefix.guard(original_paths))
    scan_factory = boot.staged_scanner
    opened = []
    with ExitStack() as stack:
        def scanner(*args, **kwargs):
            scan = scan_factory(*args, **kwargs)
            original = scan.FastSegmentSource
            from leo.storage.short_window import ShortWindowReader
            from reports.ALGO08.v3 import legacy_block_input as port, legacy_first_map_input as once

            class Bounded(original):
                def __init__(self, item):
                    if item != assignment["inventory"]["segments"][0]:
                        raise ValueError("Unexpected first original signed segment")
                    super().__init__(item, stop_sequence=assignment["stop"])

            def inventory(store, path, *, verify_windows=True):
                if Path(path) != source or verify_windows:
                    raise ValueError("Expected the declared bounded original inventory")
                return assignment["session"], assignment["digest"], assignment["inventory"]

            def chunk(reader):
                first = reader.manifest.chunks[0]
                if (reader.path != source or first.model_dump(mode="json")
                        != assignment["inventory"]["prefix_members"][0]):
                    raise ValueError("Original first signed member changed")
                return first

            def ordered(inventory):
                if inventory != assignment["inventory"]:
                    raise ValueError("Unexpected original member declaration")
                reader = ShortWindowReader(source)
                yield reader, chunk(reader)

            def bounded(segment, parts, history, hasher, replay, pending, audit, hashes, **options):
                first = chunk(segment.reader)
                key = segment.reader.manifest_sha256, first.chunk_index
                evidence, saved = yield from once.member_windows(segment, first, parts[key], None, history,
                                                                  hasher, replay, hashes, **options)
                if saved is not None or pending or replay is not None or not evidence["owned_window_capacity"]:
                    raise ValueError("Expected original verified once with direct owned windows")
                audit.append(evidence)

            original_member = ShortWindowReader._member

            def observed(reader, name, *args):
                if mode != "ordinary" or reader.path / name not in original_paths:
                    raise ValueError("Unexpected original I/Q or index read")
                opened.append(name)
                return original_member(reader, name, *args)

            for owner, key, value in (
                (scan, "FastSegmentSource", Bounded), (scan.FastScanStore, "inventory", inventory),
                (ShortWindowReader, "_member", observed), (port, "ordered_members", ordered),
                (once, "first_windows", bounded),
            ):
                stack.enter_context(patch.object(owner, key, value))
            return scan

        stack.enter_context(patch.object(boot, "staged_scanner", scanner))
        opts = arguments(binding, mode, output)
        if mode == "ordinary":
            import integrated_original_entry as entry

            stack.enter_context(patch.object(sys, "argv", [__file__, *opts]))
            entry.main()
        else:
            import integrated_packed_entry as entry

            entry.run(entry.parser().parse_args(opts))
    expected = [path.name for path in original_paths[1:]] if mode == "ordinary" else []
    if opened != expected:
        raise ValueError("One source only must deliver and verify this member")
    (output / "member-opens.json").write_text(json.dumps(opened) + "\n")


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from eight_ms_south_transfer import environment_for
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    binding = book() | {"host": host()}
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    write(root / "binding.json", binding)
    trials = {}
    for mode in ORDER:
        output = root / mode
        paths = binding["original_paths"] if mode == "ordinary" else binding["packed_paths"]
        before = resident(list(map(Path, paths)))
        command = [str(RELEASE / "venv/bin/python"), "-IB", str(Path(__file__).resolve()), "worker", str(output),
                   "--binding", str(root / "binding.json"), "--mode", mode]
        timed = measure(command, environment_for(root), output)
        trials[mode] = dict(clock=timed, before=before, after=resident(list(map(Path, paths))), command=command)
        write(root / f"{mode}-clock.json", trials[mode])
        if timed["exit_code"]:
            raise ValueError(timed["stderr_tail"])
    write(root / "launch.json", dict(order=ORDER, trials=trials))


def score(root):
    from aperture_trial import write
    from leo.contracts.digests import canonical_digest
    from preloaded_saved_worker import read

    book, clock = read(root / "binding.json"), read(root / "launch.json")
    old = json.loads(prefix.pinned(Path(book["reference_native"]), book["original"]["native"]))
    expected = [p for p in old["source"]["probes"] if p["visit_index"] < 64]
    excluded = [p for p in old["provenance"]["excluded_windows"] if p["visit"] < 64]
    proofs, common = {}, None
    for mode in ORDER:
        folder = root / mode
        raw = read(folder / "unified-short-bootstrap.json")
        (native,) = folder.glob("fast-scan-automatic-work/*/detections.json")
        path = native
        native = read(path)
        terminal = read(folder / "fast-scan-automatic-work" / raw["receipt"]["run_id"] / "terminal.json")
        if (native["source"]["probes"] != expected or native["provenance"]["excluded_windows"] != excluded
                or native["source"]["input_manifest_sha256"] != book["scope"]["digest"]
                or native["provenance"]["window_count"] != 64 or canonical_digest(native) != raw["native_sha256"]
                or native["clock_anchor"] != old["clock_anchor"] or native["delivery_clocks"] != old["delivery_clocks"][:64]
                or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1
                or raw["receipt"]["decision"] != "withheld" or terminal["reason"] != "no_active_curvature"
                or any(arm["latlon"] is not None for arm in terminal["arms"].values()) or list(folder.rglob("*.png"))):
            raise ValueError("Original signed scope or withdrawal differs from the prior recording")
        current = (path.read_bytes(), terminal, raw["held_anchor_route"]["choice"], raw["graph_proof"])
        if common is None:
            common = current
        if current != common:
            raise ValueError("The packed route changed native science or guarded output")
        storage = (raw["packed_ci16_input"] if mode == "packed" else read(folder / "legacy-original-acquisition.json"))
        (member,) = storage["members"]
        if mode == "packed":
            if (storage["fallback"] is not None or storage["original_windows"] != 0
                    or member["state"] != "strict-packed-eight" or member["encoded_blocks"] != 128
                    or member["original_decoded_sha256"] != book["raw_sha256"]):
                raise ValueError("Packed derivative custody did not activate")
        elif member["raw_sha256"] != book["raw_sha256"]:
            raise ValueError("Current original verification did not reproduce decoded authority")
        proofs[mode] = dict(phases=raw["phases"], receiver=raw["receiver_audit"], storage=storage,
                            raw=raw["native_sha256"], terminal=terminal)
    write(root / "result.json", dict(bound_scope="single prepared signed first member with scoped inventory",
        rules=book, clock=clock, proof=proofs, signed_probe_sha256=canonical_digest(expected),
        issued=64, admitted=len(expected)//2, lanes=len(expected),
        factors=sum(len(p["candidates"]) for p in expected), waveform_backing_bytes=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--binding", type=Path)
    cli.add_argument("--mode", choices=ORDER)
    args = cli.parse_args()
    if args.action == "worker":
        worker(args.root, json.loads(args.binding.read_bytes()), args.mode)
    elif args.action == "launch":
        launch(args.root)
    else:
        score(args.root)
