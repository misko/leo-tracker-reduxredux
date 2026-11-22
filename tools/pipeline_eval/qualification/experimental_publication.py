"""Experimental receiver/solver composition for an isolated full publication."""
import argparse
from contextlib import ExitStack
from functools import partial
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest.mock import patch

RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
TABLE_MODES = ("shared-tables", "track-moments")
DISCOVERY_MODES = ("combined-shared-discovery", *TABLE_MODES)
SALVAGE_MODES = ("combined", *DISCOVERY_MODES)
CAUSAL_MODES = ("causal-reuse", *SALVAGE_MODES)
RENDERING_MODES = ("individual", "shared-orbits", "shared-pixels", "raster-layout")


def run(args, specification):
    root = args.bulk_root.resolve(strict=True)
    if not root.is_dir() or any(root.iterdir()):
        raise ValueError("Research publication requires a new, empty output root")
    detector = Path(specification["detector"]).resolve(strict=True)
    digest = specification["detector_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Expected a pinned detector SHA-256")
    mode = specification["solver"]
    if mode not in ("stock", *CAUSAL_MODES):
        raise ValueError("Unknown experimental solver")
    rendering = specification.get("rendering", "individual")
    if rendering not in RENDERING_MODES:
        raise ValueError("Unknown publication renderer")
    ingress = specification.get("ingress", "stock")
    if ingress not in ("stock", "compressed-buffer"):
        raise ValueError("Unknown experimental I/Q reader")
    schedule = specification.get("schedule", "all")
    if schedule not in ("all", "bursts", "alternate", "deferred"):
        raise ValueError("Unknown receiver schedule")
    startup = specification.get("startup", "stock")
    if startup not in ("stock", "lazy-exports"):
        raise ValueError("Unknown package startup mode")
    if startup == "lazy-exports":
        from tools.pipeline_eval.variants.experimental.lean_startup import install
        install()
    from leo.contracts.algo08_region import Algo08Region
    from tools import algo08_position, algo08_scan

    with TemporaryDirectory() as scratch, ExitStack() as stack:
        assets = Path(scratch)
        for name in (*algo08_scan.PINS, "native", "projector.so"):
            source = detector if name == "cancellation-factors.so" else RELEASE/"assets"/name
            (assets/name).symlink_to(source)
        # The normal publication path checks these pins before it opens the I/Q.
        stack.enter_context(patch.dict(algo08_scan.PINS, {"cancellation-factors.so": digest}))
        if ingress == "compressed-buffer":
            from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
            acquire = algo08_scan.acquire
            def buffered(*args, **kwargs):
                with compressed_input_buffer():
                    return acquire(*args, **kwargs)
            stack.enter_context(patch.object(algo08_scan, "acquire", buffered))
        if schedule in ("alternate", "bursts"):
            from tools.pipeline_eval.variants.experimental.receiver_cadence import AlternatingCadence, BurstCadence
            cadence = AlternatingCadence() if schedule == "alternate" else BurstCadence()
            stack.enter_context(patch.object(algo08_scan, "detector", cadence.wrap(algo08_scan.detector)))
        if schedule == "deferred":
            from tools.pipeline_eval.variants.experimental.deferred_receiver import DeferredReceiver
            deferred = DeferredReceiver(max_pending=64)
            stack.enter_context(patch.object(algo08_scan, "detector", deferred.wrap(algo08_scan.detector)))
        if rendering in ("shared-orbits", "shared-pixels"):
            from leo.presentation import fast_standard_analysis
            from tools.pipeline_eval.variants.experimental.shared_orbit_figures import render_shared
            renderer = partial(render_shared, reuse_pixels=rendering == "shared-pixels")
            stack.enter_context(patch.object(fast_standard_analysis, "render_fast_scan_orbits", renderer))
        if rendering == "raster-layout":
            from tools.pipeline_eval.variants.experimental.raster_layout import render_layout
            stack.enter_context(patch.object(algo08_scan, "render", render_layout))
        if mode != "stock":
            from tools.pipeline_eval.variants.algo08_causal_reuse import prepare
            scoped = partial(prepare, algo08_position.prepare_native_scan, statistics={})
            stack.enter_context(patch.object(algo08_position, "prepare_native_scan", scoped))
        if mode in SALVAGE_MODES:
            from tools.pipeline_eval.variants.algo08_salvage_statistics import salvage_statistics
            stack.enter_context(salvage_statistics())
        if mode in DISCOVERY_MODES:
            from tools.pipeline_eval.variants import v5_core
            from tools.pipeline_eval.variants.algo08_dense_discovery import dense_discovery
            rank = v5_core.ranked_initial_nodes
            def shared_rank(scan):
                with dense_discovery(scan, reuse_associations=True):
                    return rank(scan)
            stack.enter_context(patch.object(v5_core, "ranked_initial_nodes", shared_rank))
        if mode in TABLE_MODES:
            from tools.pipeline_eval.variants.algo08_causal_table import causal_table
            from tools.pipeline_eval.variants.algo08_cavity_projection import shared_projection
            from tools.pipeline_eval.variants.algo08_salvage_bound import stable_pruning
            stack.enter_context(causal_table(canonical_exports=True, previous_catalogues=True))
            stack.enter_context(shared_projection())
            stack.enter_context(stable_pruning("gate"))
        if mode == "track-moments":
            from tools.pipeline_eval.variants import algo08_track_moments
            context = partial(algo08_track_moments.prepare_context, v5_core.scan_context)
            select = partial(algo08_track_moments.select, detail={})
            stack.enter_context(patch.object(v5_core, "scan_context", context))
            stack.enter_context(patch.object(v5_core, "infer", partial(v5_core.infer, select_initial=select)))
        offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
        result = algo08_scan.analyze(args.recording, root, assets, args.archive, offer)
        if schedule in ("alternate", "bursts"):
            result["research_sampling"] = cadence.receipt(result)
        if schedule == "deferred":
            result["deferred_continuation"] = dict(pending_lane_budget=64, native_calls=deferred.native_calls,
                                                   query_cpu_ns=deferred.query_cpu_ns, **deferred.planner.counts)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("recording", "bulk-root", "archive", "region"):
        parser.add_argument("--"+field, type=Path, required=True)
    args = parser.parse_args()
    config = Path(os.environ["ALGO08_EXPERIMENT_CONFIG"])
    print(json.dumps(run(args, json.loads(config.read_bytes()))))
