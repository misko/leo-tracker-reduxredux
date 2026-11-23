"""Compare both genuine raw CLIs through the seal of one authenticated staged member."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

import empty_bootstrap as installed

STAGED = Path("/dev/shm/leo-receiver-ceiling-0169-results01")
SCOPE_SHA = "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a"
LEGACY_SHA = "2f9102ffead53766ccc71317243618ff415de7c537cd4bb81b7b8b57488eea13"
INPUTS = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
EXACT = Path("/dev/shm/leo-v3-short-cfo-held01/build/tail.so")
SHORT = Path("/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so")
WINDOWS = 64
ORDER = (("exact", "anchored"), ("anchored", "exact"))


class ReceiverSealed(Exception):
    """The actual raw acquisition has passed its normal authenticated handoff."""


def write(path, value):
    with path.open("x") as output:
        json.dump(value, output, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")


def worker(mode, pack, output, *, launch=None):
    import anchored_cfo_raw as anchored
    import short_cfo_raw as exact

    if launch is None:
        launch = {"anchored": partial(anchored.run_cli, pack), "exact": partial(exact.run_cli, EXACT)}[mode]

    start = installed.now()
    if Path("/dev/shm") not in output.resolve().parents:
        raise ValueError("Use a fresh tmpfs worker output")
    output.mkdir()
    bought = json.loads(installed.checked(STAGED / "scope.json", SCOPE_SHA))
    prior = json.loads(installed.checked(STAGED / "1-full-short.json", LEGACY_SHA))
    segment = Path(bought["entry"]["path"])
    if segment.parent != STAGED or segment.resolve(strict=True) != segment or segment.stat().st_dev != output.stat().st_dev:
        raise ValueError("Use only the existing bounded DS30-0169 tmpfs copy")
    for name in ("manifest.json", bought["member"]["payload_relative_path"], bought["member"]["index_relative_path"]):
        path = segment / name
        if path.resolve(strict=True) != path or path.stat().st_dev != output.stat().st_dev:
            raise ValueError("The staged source escaped the authenticated tmpfs boundary")
    if bought["member"]["first_sequence"] != 0 or bought["member"]["window_count"] != WINDOWS:
        raise ValueError("Expected the original first signed member")

    hashes, vectors = [], []
    active = -1
    evidence = {}
    observer = {}
    base_scanner, base_runtime, base_bind = installed.staged_scanner, installed.load_runtime, installed.bind_native

    def scanner(sources, detector=None):
        from leo.contracts.digests import canonical_digest

        scan = base_scanner(sources, detector=detector)

        class PrefixStore(scan.FastScanStore):
            def inventory(self, recording, *, verify_windows=True):
                if recording != segment or verify_windows:
                    raise ValueError("The fixture must traverse only the original first member")
                _, original_digest, original = super().inventory(recording, verify_windows=False)
                entry, = original["segments"]
                if entry != bought["entry"]:
                    raise ValueError("The staged header differs from the exact authenticated boundary")
                limited = dict(original, segments=[dict(entry, windows=WINDOWS)], window_count=WINDOWS,
                               receiver_test_scope="one original signed member")
                digest = canonical_digest(limited)
                evidence.update(scope=limited, staged_manifest_only_inventory=original_digest,
                                prefix_inventory=digest)
                return "fast-" + digest[7:39], digest, limited

        class PrefixSource(scan.FastSegmentSource):
            def __init__(self, entry):
                if Path(entry["path"]) != segment or entry["manifest_digest"] != bought["entry"]["manifest_digest"]:
                    raise ValueError("The acquisition offered a different source")
                super().__init__(entry, stop_sequence=WINDOWS)
                if self.reader.manifest.chunks[0].model_dump(mode="json") != bought["member"]:
                    raise ValueError("The original member declaration changed")

            def windows(self):
                nonlocal active
                for window in super().windows():
                    active = window.acquisition["global_visit"]
                    hashes.append(window.iq_sha256)
                    yield window

        scan.FastScanStore = PrefixStore
        scan.FastSegmentSource = PrefixSource
        return scan

    def bind(native, session, inventory, pin, **kwargs):
        from leo.contracts.digests import canonical_digest
        from leo.storage.fast_scan import immutable_json
        from full_short_run import checked_recipe

        base_bind(native, session, inventory, pin, **kwargs)
        if hashes != prior["iq"] or canonical_digest([inventory, hashes]) != native["source"]["raw_recording_authority_digest"]:
            raise ValueError("The genuine CLI did not bind every original decoded window")
        if observer["acquisition"]["native"]["native_calls"] != {"full": 16, "short_primary": 86}:
            raise ValueError("Both original native apertures must run on the staged scope")
        if len(vectors) != 102 or not any(factor[0] == 1 for row in vectors if row["mode"] == "full" for factor in row["factors"]):
            raise ValueError("The staged replay did not include real signed cancellation")
        recipe = checked_recipe()
        if "sha256:"+pin != canonical_digest(recipe) or observer["prefetch"]["submitted"] != 0:
            raise ValueError("The guarded recipe or genuine async input context differs")
        library_path = output / "detections.json"
        immutable_json(library_path, native)
        if canonical_digest(native) != "sha256:" + sha256(library_path.read_bytes()).hexdigest():
            raise ValueError("The sealed packet changed after acquisition")
        evidence.update(recipe=recipe, native_sha256=canonical_digest(native), receiver_audit=observer["acquisition"],
                        prefetch=observer["prefetch"], iq=hashes, vectors=vectors,
                        elapsed_through_seal=installed.clock(start), full_publication=False)
        raise ReceiverSealed()

    common = ["--recording", str(segment), "--output", str(output / "no-publication"), "--archive", str(output),
              "--region", str(INPUTS / "offer.json"), "--short-binary", str(SHORT),
              "--geographic-library", str(INPUTS / "geographic.so"),
              "--regional-track-library", str(INPUTS / "regional.so"),
              "--frontier-block-library", str(INPUTS / "block.so")]
    began = resource.getrusage(resource.RUSAGE_SELF)
    with ExitStack() as boundary:
        def runtime():
            result = base_runtime()
            import combined_frontier_run
            import full_short_raw
            from mixed_aperture_receiver import NativePath

            observe_original = full_short_raw.observe_acquisition
            fetch_original = combined_frontier_run.load_prefetch
            native_run = NativePath.run

            def traced(path, iq, lane, center):
                factors, clock = native_run(path, iq, lane, center)
                vectors.append(dict(visit=active, lane=lane, mode="full" if path.maximum == 2 else "short_primary",
                                    factors=factors))
                return factors, clock

            def observe(scan, receiver, pin, audit):
                observer["acquisition"] = audit
                return observe_original(scan, receiver, pin, audit)

            def load():
                actual = fetch_original()

                @contextmanager
                def fetch():
                    with actual() as stats:
                        yield stats
                    observer["prefetch"] = asdict(stats)

                return fetch

            boundary.enter_context(patch.object(NativePath, "run", traced))
            boundary.enter_context(patch.object(full_short_raw, "observe_acquisition", observe))
            boundary.enter_context(patch.object(combined_frontier_run, "load_prefetch", load))
            return result

        boundary.enter_context(patch.object(installed, "staged_scanner", scanner))
        boundary.enter_context(patch.object(installed, "load_runtime", runtime))
        boundary.enter_context(patch.object(installed, "bind_native", bind))
        try:
            launch(common)
        except ReceiverSealed:
            pass
        else:
            raise ValueError("The previously staged prefix cannot enter the original solver")
    finish = resource.getrusage(resource.RUSAGE_SELF)
    write(output / "scope-receipt.json", dict(evidence, mode=mode, supported_original_scope=True,
          blocks=finish.ru_inblock-began.ru_inblock))


def compare(old, new, a, b):
    if a["iq"] != b["iq"] or a["prefix_inventory"] != b["prefix_inventory"] or old["clock_anchor"] != new["clock_anchor"]:
        raise ValueError("Acquisition authority changed")
    if old["delivery_clocks"] != new["delivery_clocks"] or old["provenance"]["excluded_windows"] != new["provenance"]["excluded_windows"]:
        raise ValueError("An original delivered or excluded opportunity changed")
    if old["source"]["raw_recording_authority_digest"] != new["source"]["raw_recording_authority_digest"]:
        raise ValueError("Signed decoded span changed")
    if a["recipe"] == b["recipe"] or old["provenance"]["detector_sha256"] == new["provenance"]["detector_sha256"]:
        raise ValueError("The guarded receiver must have its own detector identity")
    count = Counter()
    native_max = emitted_max = cfo_max = 0.
    short = {(row["visit"], row["lane"]) for row in a["vectors"] if row["mode"] == "short_primary"}
    for left, right in zip(a["vectors"], b["vectors"], strict=True):
        if dict(left, factors=[]) != dict(right, factors=[]) or len(left["factors"]) != len(right["factors"]):
            raise ValueError("Native candidate or signed traversal changed")
        for x, y in zip(left["factors"], right["factors"], strict=True):
            if x[:4] != y[:4]:
                raise ValueError("Original native rank, timing or signed CFO changed")
            native_max = max(native_max, *(abs(c-d) for c, d in zip(x[4:], y[4:], strict=True)))
            count.update(native_factors=1, native_residuals=x[0] == 1)
    continuous = {"fractional_tracking_cfo_hz", "fractional_exact_score", "fractional_control_score", "fractional_margin"}
    for left, right in zip(old["source"]["probes"], new["source"]["probes"], strict=True):
        if dict(left, candidates=[]) != dict(right, candidates=[]) or len(left["candidates"]) != len(right["candidates"]):
            raise ValueError("Selected detector membership or original timing metadata changed")
        for x, y in zip(left["candidates"], right["candidates"], strict=True):
            if {k: v for k, v in x.items() if k not in continuous} != {k: v for k, v in y.items() if k not in continuous}:
                raise ValueError("Selected timing, rank or gate changed")
            cfo = abs(x["fractional_tracking_cfo_hz"]-y["fractional_tracking_cfo_hz"])
            if cfo and (left["visit_index"], left["receiver_id"]) not in short:
                raise ValueError("The full anchor's signed CFO changed")
            cfo_max = max(cfo_max, cfo)
            emitted_max = max(emitted_max, *(abs(x[k]-y[k]) for k in continuous if k != "fractional_tracking_cfo_hz"))
            count["selected"] += 1
    if max(native_max, emitted_max) > 1e-8 or cfo_max > .001:
        raise ValueError("The guarded receiver exceeded the reviewed continuous tolerance")
    if a["receiver_audit"]["native"]["cfo_refinement"]["lanes"] != b["receiver_audit"]["native"]["cfo_refinement"]["lanes"]:
        raise ValueError("The original refinement policy decisions changed")
    return dict(counts=count, max_native_score_delta=native_max, max_selected_score_delta=emitted_max,
                max_refined_cfo_delta_hz=cfo_max)


def run(pack, root):
    import os

    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Run the bounded pair under the shared low-priority CPU2 lock")
    if root.resolve().parent != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs comparison directory")
    root.mkdir()
    timings, references, rows = [], {}, []
    for index, order in enumerate(ORDER, 1):
        pair = []
        for mode in order:
            scope = root / f"{index}-{mode}"
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            start = perf_counter_ns()
            result = subprocess.run([sys.executable, "-IB", str(Path(__file__)), "worker", str(pack), str(scope),
                                     "--mode", mode], check=False, timeout=20)
            stop = perf_counter_ns()-start
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            result.check_returncode()
            packet = json.loads((scope / "detections.json").read_bytes())
            receipt = json.loads((scope / "scope-receipt.json").read_bytes())
            prior = references.setdefault(mode, (packet, receipt))
            if prior[0] != packet or prior[1]["vectors"] != receipt["vectors"]:
                raise ValueError("The signed CLI output did not reproduce in reverse order")
            pair.append(dict(mode=mode, acquisition=receipt["receiver_audit"]["acquire"],
                 native=receipt["receiver_audit"]["native"], prefetch=receipt["prefetch"],
                 elapsed_through_seal=receipt["elapsed_through_seal"], process_wall_ns=stop,
                 process_cpu_s=(after.ru_utime-before.ru_utime)+(after.ru_stime-before.ru_stime),
                 input_blocks=after.ru_inblock-before.ru_inblock, exit=result.returncode))
        timings.append(pair)
    old, a = references["exact"]
    new, b = references["anchored"]
    rows.extend([dict(mode=arm, receipt=references[arm][1]) for arm in ("exact", "anchored")])
    write(root / "receipt.json", dict(paired=timings, audited=compare(old, new, a, b), arms=rows,
                                     scope="original signed member only", completed_solver=False))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("command", choices=("run", "worker"))
    cli.add_argument("pack", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("--mode", choices=("exact", "anchored"))
    args = cli.parse_args()
    if args.command == "worker":
        worker(args.mode, args.pack, args.output)
    else:
        run(args.pack, args.output)
