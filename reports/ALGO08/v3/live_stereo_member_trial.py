"""Time one signed DS30-0016 member through the original publication entry."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
PLANNER = Path("/dev/shm/leo-v3-whole-stereo-blocks/reports/ALGO08/v3/whole_stereo_blocks.py")
PREHISTORY = Path("/dev/shm/leo-cumulative-grid-projection-01/weak-pair/detections.json")
PREHISTORY_PIN = "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"
ORDER = ("unmasked", "masked")


def worker(mode, output):
    import empty_bootstrap as staged
    from continued_cfo_first_0016 import MANIFEST, OFFER, SEGMENT, SOURCE, WINDOWS, check_manifest, mapped_files

    _, files = mapped_files()
    opened, decoded = [], []
    original_scanner = staged.staged_scanner
    staged.checked(SOURCE / "offer.json", OFFER)
    output.mkdir()
    with ExitStack() as scope:
        def scanner(sources, detector=None):
            from leo.contracts.digests import canonical_digest
            from leo.storage.short_window import ShortWindowReader

            scan = original_scanner(sources, detector=detector)
            member = ShortWindowReader._member

            def read_member(reader, name, size, digest):
                if reader.path != SEGMENT or files.get(name) != (size, digest):
                    raise ValueError("Physical read outside the two signed original member files")
                result = member(reader, name, size, digest)
                opened.append(dict(name=name, bytes=size, sha256=digest))
                return result

            class PrefixStore(scan.FastScanStore):
                def inventory(self, recording, *, verify_windows=True):
                    if recording != SEGMENT or verify_windows:
                        raise ValueError("Expected one bounded original signed member")
                    _, _, inventory = super().inventory(recording, verify_windows=False)
                    (entry,) = inventory["segments"]
                    if entry["path"] != str(SEGMENT) or entry["manifest_digest"] != "sha256:" + MANIFEST:
                        raise ValueError("The original staged manifest changed")
                    prefix = dict(inventory, segments=[dict(entry, windows=WINDOWS)], window_count=WINDOWS,
                                  receiver_test_scope="one original signed DS30-0016 member")
                    digest = canonical_digest(prefix)
                    return "fast-" + digest[7:39], digest, prefix

            class PrefixSource(scan.FastSegmentSource):
                def __init__(self, entry, *, start_sequence=0, stop_sequence=None):
                    stop = WINDOWS if stop_sequence is None else stop_sequence
                    if entry["path"] != str(SEGMENT) or not 0 <= start_sequence < stop <= WINDOWS:
                        raise ValueError("A source attempted to exceed the signed first member")
                    super().__init__(entry, start_sequence=start_sequence, stop_sequence=stop)
                    check_manifest(self.reader.manifest.model_dump(mode="json"))

                def windows(self):
                    for window in super().windows():
                        decoded.append(window.iq_sha256)
                        yield window

            scan.FastScanStore, scan.FastSegmentSource = PrefixStore, PrefixSource
            scope.enter_context(patch.object(ShortWindowReader, "_member", read_member))
            return scan

        scope.enter_context(patch.object(staged, "staged_scanner", scanner))
        entry = HERE / "unified_short_bootstrap.py"
        args = [entry, "--recording", SEGMENT, "--archive", SOURCE / "tle", "--region", SOURCE / "offer.json",
                "--output", output / "publication", "--prove-empty-graph", "--prove-graph-time-support",
                "--prove-no-active-curvature"]
        for flag, asset in (("short-binary", "short"), ("geographic-library", "geographic"),
                            ("regional-track-library", "regional"), ("frontier-block-library", "block")):
            args.extend(("--" + flag, SOURCE / (asset + ".so")))
        if mode == "masked":
            args.append("--whole-stereo-blocks")
        with patch.object(sys, "argv", list(map(str, args))):
            runpy.run_path(str(entry), run_name="__main__")
    from aperture_trial import write

    if len(decoded) != WINDOWS or len(opened) != len(files) or {row["name"] for row in opened} != set(files):
        raise ValueError("The worker did not read and verify the complete original member and index")
    write(output / "decoded.json", dict(opened=opened, ordered_iq_sha256=decoded))


def verify(root, runs):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from live_stereo_blocks import PLANNER_SHA, PROTOCOL_SHA, RULE
    from raw_cfo_north_trial import native_file

    checked(PLANNER, PLANNER_SHA)
    checked(PLANNER.parent / "whole-stereo-blocks-protocol.md", PROTOCOL_SHA)
    plan = runpy.run_path(str(PLANNER))
    packets, views = {}, {}
    for mode in ORDER:
        path = root / mode
        target = path / "publication"
        raw = read(target / "unified-short-bootstrap.json")
        receipt = raw["receipt"]
        native = json.loads(checked(native_file(target), raw["native_sha256"][7:]))
        decoded = read(path / "decoded.json")
        expected = canonical_digest([native["source"]["input_manifest_sha256"], decoded["ordered_iq_sha256"]])
        if (expected != native["source"]["raw_recording_authority_digest"] or raw["raw_acquisitions"] != 1
                or raw["verified_handoffs"] != 1 or receipt["window_count"] != 64
                or receipt["decision"] != "withheld" or artifacts(target, receipt) != {"images": {}}
                or raw.get("held_anchor_route") or "fixed_epoch_cfo_refinement" in raw["receiver_recipe"]):
            raise ValueError("Expected original unrefined complete acquisition and ordinary no-media short withholding")
        (terminal_file,) = (target / "fast-scan-automatic-work").glob("*/terminal.json")
        terminal = read(terminal_file)
        if terminal["reason"] != "no_active_curvature" or any(a["latlon"] is not None for a in terminal["arms"].values()):
            raise ValueError("Both calibration arms must preserve original withholding on the short member")
        packets[mode] = native
        views[mode] = dict(process=runs[mode], decoded=decoded, native=raw["native_sha256"], terminal=terminal,
                           phases=raw["phases"], receiver_audit=raw["receiver_audit"], recipe=raw["receiver_recipe"],
                           receipt=receipt, prefetch=raw["prefetch"])
    original, masked = (packets[mode] for mode in ORDER)
    archive = json.loads(checked(PREHISTORY, PREHISTORY_PIN))
    original_probes = [p for p in archive["source"]["probes"] if p["visit_index"] < 64]
    if (original_probes != original["source"]["probes"] or views["unmasked"]["decoded"] != views["masked"]["decoded"]
            or views["unmasked"]["receipt"]["region"] != views["masked"]["receipt"]["region"]
            or masked["source"]["raw_recording_authority_digest"] != original["source"]["raw_recording_authority_digest"]
            or plan["BLACKOUT_RULE"] != RULE):
        raise ValueError("The live baseline differs from the original physical pre-continuation prefix or frozen policy")
    replay, frozen = plan["project"](original, plan["schedule"](original))
    if replay["source"]["probes"] != masked["source"]["probes"]:
        raise ValueError("The observed live probes differ from the exact offline schedule")
    calls = {mode: views[mode]["receiver_audit"]["native"]["native_calls"] for mode in ORDER}
    if (calls["masked"] != frozen["kept_native_lanes"]
            or any(calls["unmasked"][k] != calls["masked"][k] + frozen["skipped_native_lanes"].get(k, 0) for k in calls["unmasked"])):
        raise ValueError("Native invocation counts differ from the reviewed policy")
    history = plan["exposure"](original, masked, set(frozen["skipped_visits"]))
    write(root / "result.json", dict(runs=views, order=ORDER, history=history, frozen=frozen, original_archive_sha256=PREHISTORY_PIN,
          cache={mode: read(root / f"{mode}-cache.json") for mode in ORDER}, bounded_windows=64, full_physical_runs=0,
          source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest()
                         for name in ("live-stereo-blocks-protocol.md", "live_stereo_blocks.py", Path(__file__).name)}))


def run(root):
    from aperture_trial import RELEASE, write
    from continued_cfo_first_0016 import mapped_files, resident
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    host()
    if root.parent.resolve() != Path("/dev/shm") and not root.parent.resolve().is_relative_to(Path("/dev/shm")):
        raise ValueError("Use fresh private tmpfs output")
    _, files = mapped_files()
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    runs = {}
    for mode in ORDER:
        path = root / mode
        before = resident(files)
        runs[mode] = measure([RELEASE / "venv/bin/python", "-IB", __file__, "worker", mode, path], env, path)
        write(root / f"{mode}-clock.json", runs[mode])
        write(root / f"{mode}-cache.json", dict(before=before, after=resident(files)))
        if runs[mode]["exit_code"]:
            raise ValueError(runs[mode]["stderr_tail"])
    verify(root, runs)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("worker", "run", "verify"))
    cli.add_argument("args", nargs="+")
    args = cli.parse_args()
    if args.action == "worker":
        mode, output = args.args
        worker(mode, Path(output))
    elif args.action == "run":
        (root,) = map(Path, args.args)
        run(root)
    else:
        from aperture_trial import read

        (root,) = map(Path, args.args)
        verify(root, {mode: read(root / f"{mode}-clock.json") for mode in ORDER})
