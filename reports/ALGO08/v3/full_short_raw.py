"""Exercise the pinned full-coverage short-primary receiver via the raw publication."""

from contextlib import contextmanager, nullcontext
import ctypes as ct
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns, thread_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import read, write
import mixed_aperture_receiver as mixed


SHORT_SHA = "06570a53032c770d99cc9678b8660e1bb502b71f30fc47c8b1a4a8e31bc19ba9"
RECIPE_SHA = "13c4ecdb521d02960e61572e8d401a54f165e2c7882112889ede0582abb3ca40"
GRAPH = dict(max_degree=2, points_per_coefficient=2, min_points=6)


def recipe():
    return dict(installed_sha256=mixed.INSTALLED_SHA, shortened_sha256=SHORT_SHA,
                callback_sha256=sha256(Path(mixed.__file__).read_bytes()).hexdigest(),
                rule=list(mixed.FULL_RULE), streams=["edge", "channel", "actual_rf_hz"],
                aperture_samples=[200000, 120000],
                selection="maximum verified fractional margin, lower native rank on tie; verified rank zero at nonanchors")


def graph_config(config):
    from dataclasses import replace

    return replace(config, **GRAPH)


@contextmanager
def observe_acquisition(scan, runner, detector_pin, audit, *, stock_symbols=None):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification import blind_compact_run as blind

    original = scan.acquire
    stock_native = blind.Native
    original_source = scan.FastSegmentSource
    window_hashes = []
    clocks = dict(calls=0, cpu_ns=0, wall_ns=0)
    native_cpu = thread_time_ns if stock_symbols is not None else process_time_ns

    class ObservedSource(original_source):
        def windows(self):
            for window in super().windows():
                window_hashes.append(window.iq_sha256)
                yield window

    class ObservedNative(stock_native):
        def __init__(self, path, pilot):
            super().__init__(path, pilot)
            operation = self.lib.cancellation_factors
            operation.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double,
                                  ct.POINTER(blind.Factor)]
            operation.restype = ct.c_int

            def counted(*args):
                cpu, wall = native_cpu(), perf_counter_ns()
                result = operation(*args)
                clocks["cpu_ns"] += native_cpu()-cpu
                clocks["wall_ns"] += perf_counter_ns()-wall
                clocks["calls"] += 1
                return result

            self.lib.cancellation_factors = counted

    def acquire(session, inventory_sha, inventory, assets):
        if audit or scan.PINS["cancellation-factors.so"] != mixed.INSTALLED_SHA:
            raise ValueError("Expected one fresh acquire with the installed full anchor asset")
        cpu, wall = process_time_ns(), perf_counter_ns()
        # analyze has authenticated actual assets before invoking this port.
        # Retain the recipe pin for its subsequent immutable-document check.
        scan.PINS["cancellation-factors.so"] = detector_pin
        native = original(session, inventory_sha, inventory, assets)
        spent = dict(cpu_ns=process_time_ns()-cpu, wall_ns=perf_counter_ns()-wall)
        raw = canonical_digest([inventory_sha, window_hashes])
        probes = native["source"]["probes"]
        bound = canonical_digest(["cancellation", raw, detector_pin, probes])
        if (raw != native["source"]["raw_recording_authority_digest"]
                or bound != native["source"]["analysis_manifest_sha256"]
                or native["provenance"]["detector_sha256"] != "sha256:" + detector_pin
                or len(window_hashes) != inventory["window_count"]):
            raise ValueError("The raw recording or independent analysis digest changed")
        selected = sum(bool(row["candidates"]) for row in probes)
        audit.update(recording_authority=raw, input_manifest=inventory_sha, analysis_manifest=bound,
                     issued=len(window_hashes), selected=selected, detector_pin=detector_pin, acquire=spent,
                     native=runner.receipt() if runner is not None else dict(native_calls={"full": clocks["calls"]},
                     native_cpu_ns={"full": clocks["cpu_ns"]}, native_wall_ns={"full": clocks["wall_ns"]}))
        return native

    namespace = patch.dict(stock_symbols, Native=ObservedNative) if stock_symbols is not None else nullcontext()
    with (namespace, patch.dict(scan.PINS, {}), patch.object(scan, "acquire", acquire),
          patch.object(scan, "FastSegmentSource", ObservedSource),
          patch.object(blind, "Native", ObservedNative if runner is None else stock_native)):
        yield


def worker(arm, output, request_path, gate):
    from functools import partial

    from full_short_physical import authorize_gate
    from joint_publication import run

    request = read(request_path)
    authorize_gate(gate)
    if sha256(gate.read_bytes()).hexdigest() != request["gate_sha256"]:
        raise ValueError("The physical launch does not bind to its regional gate receipt")
    if arm not in ("stock", "candidate"):
        raise ValueError("Only the frozen physical pair's two arms are supported")
    candidate = arm == "candidate"
    built = recipe()
    mixer = mixed.MixedApertureDetector(request["short_binary"], SHORT_SHA, full_coverage=True) if candidate else None
    args = SimpleNamespace(recording=Path(request["recording"]), archive=Path(request["archive"]["root"]),
                           region=Path(request["region_file"]), output=output, saved=None, saved_digest=None,
                           stock_control=not candidate, optimized_full_catalogue=candidate, verify_images=True)
    clocks = {}

    def context(scan):
        from leo.contracts.digests import canonical_digest

        if canonical_digest(built) != "sha256:" + RECIPE_SHA:
            raise ValueError("The installed anchor, genuine short build or full schedule changed")
        return observe_acquisition(scan, mixer, RECIPE_SHA if candidate else mixed.INSTALLED_SHA, clocks)

    def observe(prepared):
        tracks = prepared["tracks"]
        return dict(status=prepared["status"], graph_points=tracks["graph_points"],
                    tracks=len(tracks["tracks"]), curved=len(tracks["curved_indices"]))

    args.observe_prepared = observe
    run(args, detector_override=None if mixer is None else mixer.detector,
        detector_description="verified raw stereo with full anchors and 12 ms primaries",
        track_config=graph_config if candidate else None, raw_context=context,
        early_regional=candidate, keep_selected_rows=True)
    write(output / "receiver-audit.json", dict(clocks, recipe=built if candidate else None,
                                             graph=GRAPH if candidate else "installed",
                                             source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
