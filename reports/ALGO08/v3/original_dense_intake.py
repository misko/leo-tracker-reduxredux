"""Run named and current first-use detections on one unchanged signed dense member."""

import argparse
from contextlib import ExitStack, contextmanager, closing
from hashlib import sha256
from importlib.machinery import PathFinder
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from time import time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

INPUT = Path("/dev/shm/leo-seekable-member-0008-case1/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000")
MANIFEST = "sha256:5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759"
NAMES = ("manifest.json", "windows-000000.jsonl", "iq-000000.ci16.zst")
REQUEST = Path("/dev/shm/leo-held-anchor-selected-dense-01/request.json")
REQUEST_PIN = "8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502"
INPUT_SIZE = 77_442_779
ORDERS = (("named", "first_use"), ("first_use", "named"))
LIB = Path("/dev/shm/leo-v3-first-map-pytest")
ARTIFACTS = {
    "history": (LIB / "history0/history.so", "70d834e0d148f22f3b08cdd74fc14ee6c589b45bf1e7a1949894ae9b01d9054e"),
    "replay": (LIB / "test_first_use_map_reopens_fro0/replay.so", "ebe28b1326a99d49191616726195dc20bfdd2b59dcb63884cae1c959a1154ca4"),
    "short": (Path("/var/tmp/leo-v3-eight-ms-build-padded/8ms/short-primary.so"), None),
    **{key: (Path("/dev/shm/leo-v3-saved-0402-pair-01") / f"{key}_library.so", None)
       for key in ("geographic", "regional_track", "frontier_block")},
}


class Published(Exception):
    """Intentional stop immediately after the installed detection file was written."""


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def sha(path):
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def source_binding():
    import empty_bootstrap as boot
    from leo.contracts.digests import canonical_digest
    from leo.storage.short_window import ShortWindowReader

    full = json.loads(boot.checked(REQUEST, REQUEST_PIN))
    reader = ShortWindowReader(INPUT)
    chunk = reader.manifest.chunks[0]
    if (reader.manifest_sha256 != MANIFEST or chunk.compressed_bytes != INPUT_SIZE or chunk.first_sequence != 0
            or chunk.window_count != 64 or (chunk.index_relative_path, chunk.payload_relative_path) != NAMES[1:]
            or chunk.compressed_sha256 != "sha256:556772d5619b710cae8030050b8f8a4a7b18f4b196e57cddc14562c8ca73404a"):
        raise ValueError("The complete first original signed member changed")
    boot.checked(Path(full["offer"]), full["offer_sha256"])
    if INPUT.resolve(strict=True) != INPUT or INPUT.stat().st_dev != Path("/dev/shm").stat().st_dev:
        raise ValueError("Use the existing local original member, never a backing path")
    entry = dict(path=str(INPUT), manifest_digest=MANIFEST, windows=chunk.window_count)
    inventory = dict(schema_version=1, kind="research-original-recording-prefix", recording_name=Path(full["recording"]).name,
        window_count=chunk.window_count, segments=[entry], original_recording=full["recording"],
        original_inventory_sha256=full["inventory"], prefix_members=[chunk.model_dump(mode="json")])
    digest = canonical_digest(inventory)
    return dict(case="DS30-0008", session="fast-" + digest[7:39], digest=digest, inventory=inventory, original=full,
                stop=chunk.window_count, input_bytes=chunk.compressed_bytes)


def guard(event, arguments):
    if event != "open" or not isinstance(arguments[0], (str, bytes, os.PathLike)):
        return
    path = Path(os.path.abspath(os.fsdecode(arguments[0])))
    if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01"):
        raise PermissionError("The original-member trial never opens backing files")
    if (path.name.endswith(".ci16.zst") or path.name.startswith("windows-0000")) and path not in {INPUT/name for name in NAMES}:
        raise PermissionError("A waveform or index outside the single original member is forbidden")


@contextmanager
def scoped_scanner(scan, binding, audit):
    from empty_bootstrap import clock, now

    original, acquire = scan.FastSegmentSource, scan.acquire

    class Prefix(original):
        def __init__(self, entry):
            if entry != binding["inventory"]["segments"][0]:
                raise ValueError("Unexpected original segment in a prefix trial")
            super().__init__(entry, stop_sequence=binding["stop"])

        def windows(self):
            with closing(super().windows()) as source:
                for window in source:
                    audit["stock_iq"].append(window.iq_sha256)
                    yield window

    def inventory(_store, path, *, verify_windows=True):
        if Path(path) != INPUT or verify_windows:
            raise ValueError("Only scoped metadata may enter before the original waveform verifier")
        return binding["session"], binding["digest"], binding["inventory"]

    def timed(*args):
        started = now()
        try:
            return acquire(*args)
        finally:
            audit["receiver_acquire"] = clock(started)

    with (patch.object(scan, "FastSegmentSource", Prefix), patch.object(scan.FastScanStore, "inventory", inventory),
          patch.object(scan, "acquire", timed)):
        yield


class OnScannerImport:
    def __init__(self, prepare):
        self.prepare = prepare

    def find_spec(self, name, path, target=None):
        if name != "tools.algo08_scan":
            return None
        spec = PathFinder.find_spec(name, path, target)
        released = spec.loader
        prepare = self.prepare

        class Loader:
            create_module = released.create_module

            def exec_module(self, module):
                released.exec_module(module)
                prepare(module)

        spec.loader = Loader()
        return spec


def named(binding, root, audit):
    import empty_bootstrap as boot

    boot.checked(boot.BASELINE, boot.BASELINE_PIN)
    launcher = runpy.run_path(str(boot.BASELINE))
    with ExitStack() as stack:
        def prepare(scan):
            if Path(scan.__file__).resolve() != boot.PAYLOAD / boot.SCANNER:
                raise ValueError("Named arm must enter the installed ALGO08v3 scanner")
            stack.enter_context(scoped_scanner(scan, binding, audit))
            immutable = scan.immutable_json

            def stop(path, document):
                immutable(path, document)
                if path.name == "detections.json":
                    audit["detector_published_unix_ns"] = time_ns()
                    audit["native"] = str(path.relative_to(root))
                    raise Published

            stack.enter_context(patch.object(scan, "immutable_json", stop))

        stack.enter_context(patch.object(sys, "meta_path", [OnScannerImport(prepare), *sys.meta_path]))
        original = binding["original"]
        root.mkdir()
        launcher["main"](["--recording", str(INPUT), "--archive", original["archive"]["root"],
                          "--bulk-root", str(root), "--region", original["offer"]])


def first_use(binding, root, audit):
    import empty_bootstrap as boot
    import legacy_first_map_entry as entry
    import legacy_block_raw_entry as full
    import unified_short_bootstrap as raw

    opts = ["--recording", str(INPUT), "--archive", binding["original"]["archive"]["root"],
            "--archive-sha256", binding["original"]["archive"]["snapshots_sha256"],
            "--region", binding["original"]["offer"], "--output", str(root), "--history-risk-route", "--cairo-residual-layout"]
    for label, (path, pin) in ARTIFACTS.items():
        if label in ("history", "replay"):
            opts.extend((f"--legacy-first-map-{label}", str(path), f"--legacy-first-map-{label}-sha256", "sha256:" + pin))
        else:
            opts.extend(("--short-binary" if label == "short" else "--" + label.replace("_", "-") + "-library", str(path)))
    args = entry.parser().parse_args(opts)
    with ExitStack() as stack:
        original_scan = boot.staged_scanner

        def scoped(*values, **options):
            scan = original_scan(*values, **options)
            stack.enter_context(scoped_scanner(scan, binding, audit))
            return scan

        installed_load = boot.load_runtime

        def load():
            runtime = installed_load()
            from leo.storage.fast_scan import immutable_json
            from leo.storage.short_window import ShortWindowReader

            with patch.object(sys, "path", [*sys.path, str(ROOT)]):
                from reports.ALGO08.v3 import legacy_block_input as port, legacy_first_map_input as producing

            member_writer = producing.binding
            state = {}

            @contextmanager
            def admit(boot, expected, history, hasher, replay, pending, member_audit):
                state.update(pending=pending, audit=member_audit)
                with member_writer(boot, expected, history, hasher, replay, pending, member_audit):
                    yield

            def members(inventory):
                if inventory != binding["inventory"]:
                    raise ValueError("Unexpected first-use scoped inventory")
                reader = ShortWindowReader(INPUT)
                first = reader.manifest.chunks[0]
                if (reader.manifest_sha256 != MANIFEST or first.first_sequence or first.window_count != binding["stop"]
                        or first.model_dump(mode="json") != inventory["prefix_members"][0]):
                    raise ValueError("Unexpected first-use input member")
                yield reader, first

            def selected(source, parts, history, hasher, replay, pending, records, hashes):
                member, = (chunk for chunk in source.reader.manifest.chunks if chunk.first_sequence == 0)
                key = source.reader.manifest_sha256, member.chunk_index
                if (source.start_sequence, source.stop_sequence, len(parts), len(records)) != (0, binding["stop"], 1, 0):
                    raise ValueError("First use must exhaust precisely one original member without prehistory")
                name = port.map_name(0)
                record, payload = yield from producing.member_windows(source, member, parts[key], name, history, hasher, replay, hashes)
                records.append(record)
                if payload is not None:
                    pending[name] = payload
                audit["first_use_iq"] = list(hashes)

            def publish(native, _evidence):
                checked = state["audit"]
                plan = checked["verified_plan"]
                if (plan["windows"] != binding["stop"] or len(plan["members"]) != 1 or not state["pending"]
                        or not native["source"]["probes"] or native["source"]["raw_recording_authority_digest"] != plan["raw_authority"]
                        or any(name in sys.modules for name in boot.SCIENTIFIC_IMPORTS)):
                    raise ValueError("Only the completed authenticated intake may publish the native file and prepared map")
                path = root / "detections.json"
                immutable_json(path, native)
                audit.update(native=path.name, detector_published_unix_ns=time_ns(), first_use=checked)
                started = boot.now()
                audit["first_use_bundle_sha256"] = producing.publish_bundle(root / "legacy-first-maps", plan, state["pending"])
                audit["first_use_bundle_publication"] = boot.clock(started)
                raise Published

            stack.enter_context(patch.object(producing, "binding", admit))
            stack.enter_context(patch.object(producing, "first_windows", selected))
            stack.enter_context(patch.object(port, "ordered_members", members))
            stack.enter_context(patch.object(boot, "empty_reason", publish))
            return runtime

        stack.enter_context(patch.object(boot, "staged_scanner", scoped))
        # This boundary has no solver-side portable index or later TLE dependency.
        stack.enter_context(patch.object(full, "run", raw.run))
        stack.enter_context(patch.object(boot, "load_runtime", load))
        entry.run(args)


def worker(mode, root, request):
    binding = read(request)
    sys.addaudithook(guard)
    audit = {"stock_iq": []}
    try:
        {"named": named, "first_use": first_use}[mode](binding, root, audit)
    except Published:
        pass
    if "native" not in audit or any(root.rglob("terminal.json")) or tuple(root.rglob("*.png")):
        raise ValueError("The measured child must seal one detection file and skip the entire solve")
    write(root / "worker.json", audit)


def pages():
    paths = [str(INPUT / name) for name in NAMES]
    status = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE,PAGES,FILE", *paths], text=True))
    rows = status["fincore"]
    if len(rows) != 3 or any(row["res"] < row["size"] for row in rows):
        raise ValueError("All exact local scope files must already be resident")
    return rows


def recover(root, binding):
    first = root / "1-named"
    failed = root / "1-first_use.clock.json"
    witness = read(failed)["process"]
    if (read(first.with_suffix(".clock.json"))["process"]["exit_code"] or not (first / "worker.json").is_file()
            or witness["exit_code"] != 1 or "in ordered_members" not in witness["stderr_tail"]
            or "Ordinary recording inventory changed" not in witness["stderr_tail"]
            or (root / "1-first_use").exists() or (root / "resume.json").exists()
            or any((root / f"2-{mode}").exists() for mode in ORDERS[0])):
        raise ValueError("Only the exact pre-waveform first-use inventory admission error is recoverable")
    if read(root / "binding.json")["inventory"] != binding["inventory"]:
        raise ValueError("Recovery changed the original source scope")
    audit = {}
    for suffix in ("clock.json", "stderr", "stdout"):
        source = root / f"1-first_use.{suffix}"
        dest = root / f"rejected-1-first_use.{suffix}"
        audit[dest.name] = sha(source)
        source.rename(dest)
    write(root / "resume.json", dict(rejected=audit, source_sha256=sha(Path(__file__)), preserved_first_named=True,
                                     failure_before_original_member_or_detector=True))


def launch(root, *, resume=False):
    from empty_bootstrap import RELEASE, clock, now
    from short_raw_diagnostic import measure

    started = now()
    if (root.parent.resolve(strict=True) != Path("/tmp") or root.exists() != resume or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) != 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "best-effort: prio 7"):
        raise ValueError("Require fresh /tmp output and the shared low-priority CPU2 appointment")
    binding = source_binding()
    first_resident = pages()
    request = root / "binding.json"
    if resume:
        recover(root, binding)
    else:
        root.mkdir(mode=0o700)
        (root / "tmp").mkdir()
        write(request, binding | {"initial_residency": first_resident, "orders": ORDERS,
                                  "source_sha256": {name: sha(HERE / name) for name in (
                                      Path(__file__).name, "original-dense-intake-protocol.md", "legacy_first_map_entry.py",
                                      "legacy_first_map_input.py", "legacy_fused_map.py", "unified_short_bootstrap.py")},
                                  "admission": clock(started)})
    env = dict(os.environ, TMPDIR=str(root / "tmp"), MPLCONFIGDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    for pair, order in enumerate(ORDERS, 1):
        for mode in order:
            if resume and pair == 1 and mode == "named":
                continue
            destination = root / f"{pair}-{mode}"
            before = pages()
            command = ["/usr/bin/timeout", "--kill-after=2s", "20s", str(RELEASE / "venv/bin/python"), "-IB",
                       str(Path(__file__).resolve()), "worker", str(destination), "--mode", mode, "--binding", str(request)]
            record = measure(command, env, destination)
            write(destination.with_suffix(".clock.json"), dict(command=command, process=record, before=before, after=pages()))
            if record["exit_code"]:
                raise RuntimeError(record["stderr_tail"])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--mode", choices=ORDERS[0])
    cli.add_argument("--binding", type=Path)
    cli.add_argument("--resume", action="store_true")
    args = cli.parse_args()
    if args.action == "worker":
        worker(args.mode, args.root, args.binding)
    elif args.action == "launch":
        launch(args.root, resume=args.resume)
    else:
        from original_dense_intake_score import score

        score(args.root)
