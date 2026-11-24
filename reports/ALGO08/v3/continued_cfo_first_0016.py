"""Read only the signed first DS30-0016 member with the two authentic receivers."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

import empty_bootstrap as installed
from anchored_cfo_stage import ReceiverSealed, write


RECORDING = "fast8-auto-20261113-112146-b04f5461-1-lower"
SEGMENT = Path("/dev/shm/leo-v3-guarded-selective-0016-stage01") / RECORDING / (RECORDING+"-segment-00000000")
MANIFEST = "1530e4a7376f569f52d2b41dfdfc732489b036df73a8cff9b0feabecbc8cb3cc"
COMPRESSED = "4773bee9d16a0291338408540c4b4e83c6ce960bb2ed01ef1e5e65a25d38ea4a"
INDEX = "dfe2b6d4971a48811462a2ad1f97e85a7574fa949c0b8f10fe4222e0ab20c609"
DECLARATION = dict(chunk_index=0, first_sequence=0, window_count=64, compressed_bytes=78_554_951,
                   uncompressed_bytes=102_400_000, index_bytes=173_091, compressed_sha256="sha256:"+COMPRESSED,
                   index_sha256="sha256:"+INDEX, payload_relative_path="iq-000000.ci16.zst",
                   index_relative_path="windows-000000.jsonl")
WINDOWS = DECLARATION["window_count"]
SOURCE = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
OFFER = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
PACK = Path("/dev/shm/leo-anchored-cfo-raw-pack01")
PACK_SHA = "0d590b0c7e4ffc468fb17804146362b8534d33d115d83055ae7bbc1dafd967a9"
SOURCE_FILES = ("continued_cfo_first_0016.py", "continued-cfo-first-0016-protocol.md", "continued_cfo.py",
                "anchored_cfo_raw.py", "short_cfo_raw.py", "held_cycle_refined.py", "unified_short_bootstrap.py",
                "empty_bootstrap.py", "full_short_raw.py", "continued_cfo_first_0016_score.py")
ORDER = (("named", "guarded"), ("guarded", "named"))


def read(path):
    return json.loads(path.read_bytes())


def check_manifest(manifest):
    chunk = manifest["chunks"][0]
    if (any(chunk[name] != value for name, value in DECLARATION.items()) or manifest["receiver_ids"] != [0, 1]
            or manifest["sample_rate_hz"] != 10_000_000 or manifest["window_ms"] != 20):
        raise ValueError("The staged member differs from the original first signed 64 visits")
    return chunk


def mapped_files():
    if SEGMENT.resolve(strict=True) != SEGMENT or SEGMENT.stat().st_dev != Path("/dev/shm").stat().st_dev:
        raise ValueError("Only the original copied member on tmpfs is authorized")
    chunk = check_manifest(json.loads(installed.checked(SEGMENT / "manifest.json", MANIFEST)))
    pairs = {chunk[f"{kind}_relative_path"]: (chunk[size], chunk[digest]) for kind, size, digest in
             (("index", "index_bytes", "index_sha256"), ("payload", "compressed_bytes", "compressed_sha256"))}
    for name, (size, _) in pairs.items():
        path = SEGMENT / name
        if path.resolve(strict=True) != path or path.stat().st_size != size:
            raise ValueError("Authorized first member or index has changed extent")
    return chunk, pairs


def resident(files):
    from full_short_physical import CACHE_LIB, CACHE_SHA
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query

    installed.checked(CACHE_LIB, CACHE_SHA)
    scope = cache_snapshot([(SEGMENT, name, size) for name, (size, _) in files.items()],
                           os.sysconf("SC_PAGE_SIZE"), load_query(CACHE_LIB))
    if (scope["unavailable"] or scope["observed_members"] != len(files)
            or scope["cached_pages"] != scope["observed_file_pages"]):
        raise ValueError("The copied original member and index must already be fully resident")
    return scope


def worker(mode, output):
    from continued_cfo import ContinuedChanges, raw_entry
    import continued_cfo as continued

    started = installed.now()
    _, files = mapped_files()
    output.mkdir()
    iq, opened, evidence, audit, holding = [], [], {}, {}, {}
    original_scanner, original_bind = installed.staged_scanner, installed.bind_native

    with ExitStack() as scope:
        def scanner(sources, detector=None):
            from leo.contracts.digests import canonical_digest
            from leo.storage.short_window import ShortWindowReader
            from tools.pipeline_eval.qualification import blind_compact_run
            from full_short_raw import observe_acquisition

            scanner_module = original_scanner(sources, detector=blind_compact_run.detector if mode == "named" else detector)
            original_member = ShortWindowReader._member

            def read_member(reader, name, size, digest):
                if reader.path != SEGMENT or files.get(name) != (size, digest):
                    raise ValueError("A read tried to leave the two authorized member files")
                content = original_member(reader, name, size, digest)
                opened.append(dict(name=name, bytes=size, sha256=digest))
                return content

            class PrefixStore(scanner_module.FastScanStore):
                def inventory(self, recording, *, verify_windows=True):
                    if recording != SEGMENT or verify_windows:
                        raise ValueError("Expected the single original manifest and bounded acquisition scope")
                    _, manifest_inventory, original = super().inventory(recording, verify_windows=False)
                    entry, = original["segments"]
                    if (entry["path"] != str(SEGMENT) or entry["manifest_digest"] != "sha256:"+MANIFEST
                            or entry["windows"] < WINDOWS):
                        raise ValueError("The original signed manifest was replaced")
                    prefix = dict(original, segments=[dict(entry, windows=WINDOWS)], window_count=WINDOWS,
                                  receiver_test_scope="one original signed DS30-0016 member")
                    digest = canonical_digest(prefix)
                    evidence.update(prefix_inventory=digest, original_segment_inventory=manifest_inventory,
                                    scope=prefix)
                    return "fast-"+digest[7:39], digest, prefix

            class PrefixSource(scanner_module.FastSegmentSource):
                def __init__(self, entry):
                    if entry["path"] != str(SEGMENT) or entry["manifest_digest"] != "sha256:"+MANIFEST:
                        raise ValueError("The signed original source path changed")
                    super().__init__(entry, stop_sequence=WINDOWS)
                    check_manifest(self.reader.manifest.model_dump(mode="json"))

                def windows(self):
                    for window in super().windows():
                        iq.append(window.iq_sha256)
                        yield window

            scanner_module.FastScanStore = PrefixStore
            scanner_module.FastSegmentSource = PrefixSource
            scope.enter_context(patch.object(ShortWindowReader, "_member", read_member))
            if mode == "named":
                pin = runtime_spec["detector_sha256"]
                scope.enter_context(observe_acquisition(scanner_module, None, pin, audit))
            return scanner_module

        def seal(native, session, inventory, pin, *, recipe, original, acquired, route, paid):
            from leo.contracts.digests import canonical_digest
            from leo.storage.fast_scan import immutable_json

            original_bind(native, session, inventory, pin)
            source = native["source"]
            if (len(iq) != WINDOWS or len(opened) != len(files) or {row["name"] for row in opened} != set(files)
                    or source["raw_recording_authority_digest"] != canonical_digest([inventory, iq])):
                raise ValueError("Complete decoded prefix and ordered source authority were not authenticated")
            output_path = output / "detections.json"
            immutable_json(output_path, native)
            native_digest = canonical_digest(native)
            if "sha256:"+sha256(output_path.read_bytes()).hexdigest() != native_digest:
                raise ValueError("The sealed prefix bytes differ from the authenticated handoff")
            evidence.update(native_sha256=native_digest, recipe=recipe, iq=iq, opened=opened, acquisition=audit,
                            diagnostics=holding, original_probes=original, acquired_probes=acquired,
                            held_choice=route, paid=paid, receiver_through_seal=installed.clock(started))
            raise ReceiverSealed()

        def named_bind(native, session, inventory, pin, **kwargs):
            seal(native, session, inventory, pin, recipe=dict(installed_sha256=pin),
                 original=None, acquired=None, route=None, paid=[])

        original_select = continued.select_refined

        def selected(native, preparation, changes, session, inventory, receipt_path):
            start = installed.now()
            final, recipe, pin, route = original_select(native, preparation, changes, session, inventory, receipt_path)
            holding["held_cycle"] = installed.clock(start)
            acquired = native["source"]["probes"]
            if not isinstance(changes, ContinuedChanges) or len(changes.lanes) != len(acquired):
                raise ValueError("The live continuation did not advance all original probes")
            seal(final, session, inventory, pin, recipe=recipe, original=changes.original_rows(acquired),
                 acquired=acquired, route=route, paid=changes.paid)

        base_runtime = installed.load_runtime
        runtime_spec = {}

        def runtime():
            result = base_runtime()
            runtime_spec.update(result[1])
            if mode == "guarded":
                import full_short_raw

                underlying = full_short_raw.observe_acquisition

                def observed(scan, mixer, pin, counts):
                    return underlying(scan, mixer, pin, audit)

                scope.enter_context(patch.object(full_short_raw, "observe_acquisition", observed))
            return result

        scope.enter_context(patch.object(installed, "load_runtime", runtime))
        scope.enter_context(patch.object(installed, "staged_scanner", scanner))
        scope.enter_context(patch.object(continued, "select_refined", selected))
        installed.checked(SOURCE / "offer.json", OFFER)
        try:
            if mode == "named":
                bulk = output / "no-publication"
                bulk.mkdir()
                scope.enter_context(patch.object(installed, "bind_native", named_bind))
                installed.run(SimpleNamespace(recording=SEGMENT, bulk_root=bulk, region=SOURCE/"offer.json",
                                              archive=SOURCE/"tle", saved=None, saved_digest=None))
            else:
                args = ["--recording", SEGMENT, "--output", output/"no-publication", "--archive", SOURCE/"tle",
                        "--region", SOURCE/"offer.json", "--short-binary", SOURCE/"short.so",
                        "--geographic-library", SOURCE/"geographic.so", "--regional-track-library", SOURCE/"regional.so",
                        "--frontier-block-library", SOURCE/"block.so"]
                raw_entry(None, list(map(str, args)), guarded_pack=PACK)
        except ReceiverSealed:
            pass
        else:
            raise ValueError("Scoped acquisition must stop before scientific publication")
    write(output / "scope-receipt.json", dict(evidence, mode=mode, position_runs=0))


def run(root):
    from anchored_cfo_raw import verified_pack
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    settings = host()
    chunk, files = mapped_files()
    installed.checked(PACK / "pack.json", PACK_SHA)
    verified_pack(PACK)
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Freeze the scoped receiver before launch")
    if root.parent.resolve() != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs output directly under /dev/shm")
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = installed.RELEASE / "venv/bin/python"
    write(root / "binding.json", dict(machine=settings, order=ORDER, segment=str(SEGMENT), member=chunk,
          manifest_sha256=MANIFEST, pack_sha256=PACK_SHA, original_offer_sha256=OFFER,
          commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
          sources={name: sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCE_FILES}))
    for pair, labels in enumerate(ORDER, 1):
        for mode in labels:
            output = root / f"{pair}-{mode}"
            command = ["/usr/bin/timeout", "--kill-after=1s", "20s", python, "-Bsm",
                       "reports.ALGO08.v3.continued_cfo_first_0016", "worker", output, "--mode", mode]
            before = resident(files)
            clock = measure(command, env, output)
            write(root / (output.name+"-clock.json"), dict(clock=clock, before=before, after=resident(files), command=list(map(str, command))))
            if clock["exit_code"]:
                raise RuntimeError(clock["stderr_tail"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--mode", choices=("named", "guarded"))
    args = parser.parse_args()
    if args.action == "run":
        run(args.root)
    elif args.mode:
        worker(args.mode, args.root)
    else:
        parser.error("worker requires --mode")
