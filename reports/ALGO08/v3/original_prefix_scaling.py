"""Scale the verified-once original receiver through signed detections."""

import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
PRIOR = Path("/dev/shm/leo-v3-verify-original-once-result01")
PRIOR_PIN = "4446a97aeba1b496a4c96ed949b43d3d6984432b4ac8f3087d8c8fafbd6c1555"
STAGE = Path("/dev/shm/leo-v3-guarded-selective-0016-stage01")
ORDER = ((1, 4), (4, 1))
ALLOWANCE = 280.5
SEGMENT_0008 = "fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000"


class DetectionPublished(Exception):
    """Stop after an authenticated detector commit and before the numerical route."""


def pinned(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Expected previously pinned contents: {path}")
    return data


def prefixes(entry, chunks, recording, staged, original_pin):
    from leo.contracts.digests import canonical_digest

    answers = {}
    for count in ORDER[0]:
        members = chunks[:count]
        if len(members) != count or any(
                (r["chunk_index"], r["first_sequence"], r["window_count"]) != (i, 64 * i, 64)
                for i, r in enumerate(members)):
            raise ValueError("Require consecutive original whole members")
        stop = 64 * count
        inventory = dict(schema_version=1, kind="research-original-recording-prefix",
                         original_inventory_sha256=original_pin, original_recording=recording,
                         window_count=stop, prefix_members=members,
                         segments=[dict(entry, path=str(staged), windows=stop)])
        pin = canonical_digest(inventory)
        answers[str(count)] = dict(inventory=inventory, digest=pin, session="fast-" + pin[7:39], stop=stop,
                                   bytes=sum(member["compressed_bytes"] for member in members))
    return answers


def census():
    from exact_named_raw import staged_path

    pin = "sha256:5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759"
    folders = [staged_path(Path("/dev/shm") / root / SEGMENT_0008)
               for root in ("leo-seekable-member-0008-case1", "leo-v3-catalogue-read-overlap-run01")]
    original = json.loads(pinned(folders[0] / "manifest.json", pin))
    observations = []
    for folder in folders:
        paths = [folder / chunk["payload_relative_path"] for chunk in original["chunks"][:4]]
        observations.append(dict(path=str(folder), manifest_sha256=sha256((folder / "manifest.json").read_bytes()).hexdigest(),
                                 extents={path.name: path.stat().st_size if path.is_file() else None for path in paths}))
    if list(value for value in observations[0]["extents"].values() if value is not None) != [77_442_779]:
        raise ValueError("The previously witnessed DS30-0008 availability changed")
    if observations[1]["manifest_sha256"] == pin[7:]:
        raise ValueError("The reframe now has original manifest identity")
    return dict(case="DS30-0008", original_manifest=pin, available_prefix_members=1,
                candidates=observations, prior_bulk_xfs_excluded=True)


def admit(census_path, census_pin):
    from exact_named_raw import staged_path

    prior = json.loads(pinned(PRIOR / "verified-once.json", PRIOR_PIN))
    request = prior["admission"]["inputs"]["DS30-0016"]["request"]
    output = PRIOR / "DS30-0016" / "once"
    inventory = json.loads(pinned(output / "fast-scan-inputs" / (request["session"] + ".json"), request["inventory"]))
    entry = inventory["segments"][0]
    source = staged_path(STAGE / Path(request["recording"]).name / Path(entry["path"]).name)
    manifest = json.loads(pinned(staged_path(source / "manifest.json", root=source), entry["manifest_digest"]))
    scopes = prefixes(entry, manifest["chunks"], request["recording"], source, request["inventory"])
    authority = prior["checked"]["DS30-0016"]["original"]["members"]
    for chunk, signed in zip(scopes["4"]["inventory"]["prefix_members"], authority[:4], strict=True):
        fields = ("compressed_sha256", "index_sha256", "uncompressed_sha256", "compressed_bytes", "uncompressed_bytes")
        wanted = ("member_sha256", "index_sha256", "raw_sha256", "encoded", "decoded")
        if tuple(chunk[k] for k in fields) != tuple(signed[k] for k in wanted):
            raise ValueError("The staged prefix differs from previously verified originals")
    options = prior["checked"]["DS30-0016"]["clock"]["command"][6:]
    if "--verify-original-once" not in options or "--legacy-first-map-replay" in options:
        raise ValueError("Expected the current original verify-once receiver")
    old_native, = output.glob("fast-scan-automatic-work/*/detections.json")
    selected = json.loads((output / "unified-short-bootstrap.json").read_bytes())["held_anchor_route"]
    if selected["choice"]["route"] != "unfiltered" or selected["native_sha256"] != request["native"]:
        raise ValueError("The same-mode archival packet must retain unfiltered factors")
    available = json.loads(pinned(census_path, census_pin))
    if (available["case"], available["available_prefix_members"], available["prior_bulk_xfs_excluded"]) != (
            "DS30-0008", 1, True):
        raise ValueError("Expect the earlier metadata-only single-member original census")
    return dict(case="DS30-0016", source=str(source), scopes=scopes, original=request, candidate_options=options,
                reference_native=str(old_native), input_census=available, input_census_sha256=census_pin,
                reference_choice="unfiltered")


def files(binding, scope):
    root = Path(binding["source"])
    return [root / "manifest.json", *(root / chunk[k] for chunk in scope["inventory"]["prefix_members"]
                                     for k in ("index_relative_path", "payload_relative_path"))]


def guard(paths):
    names = {path.name for path in paths}

    def access(event, arguments):
        if event != "open" or not isinstance(arguments[0], (str, bytes)):
            return
        path = Path(os.fsdecode(arguments[0]))
        absolute = Path(os.path.abspath(path))
        if absolute.is_relative_to("/srv/bulk") or absolute.is_relative_to("/mnt/qnap01"):
            raise PermissionError("A prefix worker cannot open backing input")
        if path.name.endswith(".ci16.zst") or path.name.startswith("windows-000"):
            # The existing prefetch helper anchors its dir_fd to the signed source.
            if path not in paths and (len(path.parts) != 1 or path.name not in names):
                raise PermissionError("A prefix worker cannot open a following payload")

    return access


def detection_hook(root, live, windows, scientific_imports, immutable_json):
    def publish(native, _specific):
        state = live["source"]
        if (state["authority_mode"] != "verified-once" or state["verified_source"]["windows"] != windows
                or native["source"]["raw_recording_authority_digest"] != state["finished_raw_authority"]
                or any(name in sys.modules for name in scientific_imports)):
            raise ValueError("Signed detector publication must follow exact prefix EOF")
        immutable_json(root / "detections.json", native)
        live["detector_published_unix_ns"] = time_ns()
        raise DetectionPublished

    return publish


def bound_source(source, entry, stop):
    """Set the prefix frontier before the released class receives lookahead."""
    ordinary = source.__init__

    def initialize(segment, item, **options):
        if item != entry or options:
            raise ValueError("Unexpected signed acquisition segment or range for the exact prefix")
        ordinary(segment, item, stop_sequence=stop)

    return patch.object(source, "__init__", initialize)


def worker(root, binding, size, *, entrypoint=None, preserve_lookahead=False):
    import empty_bootstrap as boot
    from exact_named_raw import staged_path
    import legacy_first_map_entry as entry

    assigned = binding["scopes"][str(size)]
    source = staged_path(Path(binding["source"]))
    sys.addaudithook(guard(files(binding, assigned)))
    options = list(binding["candidate_options"])
    for flag, value in (("--recording", source), ("--output", root)):
        options[options.index(flag) + 1] = str(value)
    args = entry.parser().parse_args(options) if entrypoint is None else None
    live = {}
    load, staged = boot.load_runtime, boot.staged_scanner
    with ExitStack() as patches:
        def scoped(*values, **options):
            scan = staged(*values, **options)
            original, acquire = scan.FastSegmentSource, scan.acquire

            class Prefix(original):
                def __init__(self, item):
                    if item != assigned["inventory"]["segments"][0]:
                        raise ValueError("Unexpected signed acquisition segment")
                    super().__init__(item, stop_sequence=assigned["stop"])

            def inventory(store, path, *, verify_windows=True):
                if Path(path) != source or verify_windows:
                    raise ValueError("Only the predeclared prefix metadata may enter the scanner")
                return assigned["session"], assigned["digest"], assigned["inventory"]

            if preserve_lookahead:
                patches.enter_context(bound_source(original, assigned["inventory"]["segments"][0], assigned["stop"]))
            else:
                patches.enter_context(patch.object(scan, "FastSegmentSource", Prefix))
            patches.enter_context(patch.object(scan.FastScanStore, "inventory", inventory))

            def observed(*args):
                started = boot.now()
                try:
                    return acquire(*args)
                finally:
                    live["receiver_acquire"] = boot.clock(started)

            if entrypoint is not None and not preserve_lookahead:
                patches.enter_context(patch.object(scan, "acquire", observed))
            return scan

        def loaded():
            runtime = load()
            import eight_ms_native_receiver as selector
            import full_short_raw
            from leo.storage.fast_scan import immutable_json
            from leo.storage.short_window import ShortWindowReader
            with patch.object(sys, "path", [*sys.path, str(ROOT)]):
                from reports.ALGO08.v3 import legacy_first_map_input as once, legacy_block_input as port

            binder, observer, select = once.binding, full_short_raw.observe_acquisition, selector.prepare

            def checked_chunks(reader):
                wanted = assigned["inventory"]["prefix_members"]
                found = reader.manifest.chunks[:len(wanted)]
                if (reader.path != source or reader.manifest_sha256 != assigned["inventory"]["segments"][0]["manifest_digest"]
                        or [chunk.model_dump(mode="json") for chunk in found] != wanted):
                    raise ValueError("Original first signed prefix changed")
                return found

            def ordered(inventory):
                if inventory != assigned["inventory"]:
                    raise ValueError("Unexpected original prefix inventory")
                reader = ShortWindowReader(source)
                yield from ((reader, chunk) for chunk in checked_chunks(reader))

            def selected(segment, parts, history, hasher, replay, pending, audit, hashes, **mode):
                if (segment.start_sequence, segment.stop_sequence, replay, mode) != (
                        0, assigned["stop"], None, {"accelerate": True, "build_maps": False}):
                    raise ValueError("Expected the real verify-once reader with a bounded prefix")
                for chunk in checked_chunks(segment.reader):
                    key = segment.reader.manifest_sha256, chunk.chunk_index
                    evidence, saved = yield from once.member_windows(
                        segment, chunk, parts[key], None, history, hasher, replay, hashes, **mode)
                    if saved is not None or pending or not evidence["owned_window_capacity"]:
                        raise ValueError("Expected the original native owned decoder without replay capture")
                    audit.append(evidence)
                live["iq"] = hashes

            @contextmanager
            def bound(boot, expected, history, hasher, replay, pending, audit, **mode):
                live["source"] = audit
                with binder(boot, expected, history, hasher, replay, pending, audit, **mode):
                    yield

            def observe(scan, mixer, pin, audit):
                live["receiver"] = audit
                return observer(scan, mixer, pin, audit)

            def chosen(original, recipe, session, inventory, path):
                live["before_selection"] = original["source"]["probes"]
                output = select(original, recipe, session, inventory, path)
                live["selection"] = output[3]
                return output

            for module, name, patch_value in (
                (once, "binding", bound), (once, "first_windows", selected), (port, "ordered_members", ordered),
                (full_short_raw, "observe_acquisition", observe), (selector, "prepare", chosen),
                (boot, "empty_reason", detection_hook(root, live, assigned["stop"], boot.SCIENTIFIC_IMPORTS,
                                                     immutable_json)),
            ):
                patches.enter_context(patch.object(module, name, patch_value))
            return runtime

        patches.enter_context(patch.object(boot, "staged_scanner", scoped))
        patches.enter_context(patch.object(boot, "load_runtime", loaded))
        try:
            if entrypoint is None:
                entry.run(args)
            else:
                with patch.object(sys, "argv", [__file__, *options]):
                    entrypoint()
        except DetectionPublished:
            pass
    if "detector_published_unix_ns" not in live or any(root.rglob("terminal.json")) or list(root.rglob("*.png")):
        raise ValueError("Expected only the completed signed detector publication")
    (root / "worker.json").write_text(json.dumps(live, sort_keys=True, allow_nan=False) + "\n")


def launch(root, census_path, census_pin):
    from aperture_trial import write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from eight_ms_south_transfer import environment_for
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    binding = admit(census_path, census_pin) | {"machine": host(), "driver_sha256": sha256(Path(__file__).read_bytes()).hexdigest()}
    root.mkdir(mode=0o700)
    request = root / "binding.json"
    write(request, binding)
    (root / "tmp").mkdir()
    (root / "fonts").mkdir()
    trials = []
    for orientation, order in enumerate(ORDER):
        pair = {}
        for size in order:
            scope = binding["scopes"][str(size)]
            path = root / f"{orientation}-{size}"
            before = resident(files(binding, scope))
            command = [str(RELEASE / "venv/bin/python"), "-IB", str(Path(__file__).resolve()),
                       "worker", str(path), "--binding", str(request), "--size", str(size)]
            clock = measure(command, environment_for(root), path)
            after = resident(files(binding, scope))
            pair[str(size)] = dict(clock=clock, command=command, before=before, after=after, output=str(path))
            write(root / f"clock-{orientation}-{size}.json", pair[str(size)])
            if clock["exit_code"]:
                raise RuntimeError(clock["stderr_tail"])
        trials.append(pair)
    write(root / "launch.json", dict(order=ORDER, records=trials, binding_sha256=sha256(request.read_bytes()).hexdigest()))


def marginal(first, last, first_bytes, last_bytes):
    slope = (last - first) / ((last_bytes - first_bytes) / 1e6)
    if slope <= 0:
        raise ValueError("Incremental timing must be positive")
    return dict(additional_s=last - first, intercept_s=first - slope * first_bytes / 1e6,
                marginal_mb_s=1 / slope, clears_allowance=1 / slope >= ALLOWANCE)


def score(root):
    from aperture_trial import write
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest
    from visit_frame_raw_0016 import read

    book, launched = read(root / "binding.json"), read(root / "launch.json")
    if sha256((root / "binding.json").read_bytes()).hexdigest() != launched["binding_sha256"]:
        raise ValueError("The frozen original prefix scope changed")
    reference = json.loads(pinned(Path(book["reference_native"]), book["original"]["native"]))
    times, exact = [], {}
    for pair in launched["records"]:
        observation = {}
        for key, row in pair.items():
            scope, clock, folder = book["scopes"][key], row["clock"], Path(row["output"])
            worker, native = read(folder / "worker.json"), read(folder / "detections.json")
            probes = [p for p in reference["source"]["probes"] if p["visit_index"] < scope["stop"]]
            digest = canonical_digest(native)
            bind_native(native, scope["session"], scope["digest"], native["provenance"]["detector_sha256"][7:], expected=digest)
            excluded = [p for p in reference["provenance"]["excluded_windows"] if p["visit"] < scope["stop"]]
            if (clock["exit_code"] or worker["before_selection"] != probes or len(worker["iq"]) != scope["stop"]
                    or native["delivery_clocks"] != reference["delivery_clocks"][:scope["stop"]]
                    or native["clock_anchor"] != reference["clock_anchor"] or native["provenance"]["excluded_windows"] != excluded
                    or native["source"]["raw_recording_authority_digest"] != canonical_digest([scope["digest"], worker["iq"]])
                    or sha256((folder / "detections.json").read_bytes()).hexdigest() != digest[7:]
                    or not clock["started_unix_ns"] <= (folder / "detections.json").stat().st_mtime_ns
                        <= worker["detector_published_unix_ns"]):
                raise ValueError("The receiver prefix differs from independently signed opportunities or evidence")
            selected = native["source"]["probes"]
            evidence = dict(digest=digest, choice=worker["selection"]["choice"]["route"],
                            original_probe_parity=selected == probes, probes=len(probes), excluded=len(excluded),
                            factors=sum(len(p["candidates"]) for p in selected))
            if key in exact and evidence != exact[key]:
                raise ValueError("A reversed repeat changed signed receiver bytes")
            exact[key] = evidence
            acquire = worker["receiver"]["acquire"]
            observation[key] = dict(bytes=scope["bytes"],
                                    detection=(worker["detector_published_unix_ns"] - clock["started_unix_ns"]) / 1e9,
                                    inner_wall=acquire["wall_ns"] / 1e9, inner_cpu=acquire["cpu_ns"] / 1e9,
                                    through_exit=clock["elapsed_s"], process_cpu=clock["cpu_s"],
                                    native=worker["receiver"]["native"])
        rates = {metric: marginal(observation["1"][metric], observation["4"][metric],
                                  observation["1"]["bytes"], observation["4"]["bytes"])
                 for metric in ("detection", "inner_wall", "inner_cpu")}
        times.append(dict(scopes=observation, growth=rates))
    write(root / "result.json", dict(scope=book, launches=launched, exact=exact, times=times,
                                   allowance_mb_s=ALLOWANCE, solver_children=0, waveform_backing_bytes=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("census", "launch", "worker", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--size", type=int)
    parser.add_argument("--census", type=Path)
    parser.add_argument("--census-sha256")
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.root, json.loads(args.binding.read_bytes()), args.size)
    elif args.action == "census":
        with args.root.open("x") as stream:
            json.dump(census(), stream, indent=2, sort_keys=True)
            stream.write("\n")
    elif args.action == "launch":
        launch(args.root, args.census, args.census_sha256)
    else:
        score(args.root)
