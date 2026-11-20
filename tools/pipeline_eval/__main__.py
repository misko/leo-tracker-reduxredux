"""Command-line runner for the frozen receiver panels and independent scoring."""

import argparse
import csv
import gzip
import hashlib
import importlib
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from pathlib import Path

from .scoring import ARMS, ROLES, baseline_rows, score, validate_result

ROOT = Path(__file__).resolve().parents[2]
COLD_VARIANTS = {
    "point_votes_global": ("point_votes", "solve", None),
    "point_votes_matched_tile": ("point_votes", "solve", "center"),
    "rate_triplets_global": ("rate_triplets", "run", None),
    "rate_triplets_matched_tile": ("rate_triplets", "run", "offer"),
    "folded_doppler_global": ("folded_doppler", "solve", None),
    "folded_doppler_matched_tile": ("folded_doppler", "solve", "center"),
    "pass_geometry_global": ("pass_geometry", "run", None),
    "pass_geometry_matched_tile": ("pass_geometry", "run", "offer"),
    "joint_pass_id_matched_tile": ("joint_pass_id", "run", "offer"),
    "region_challenge_matched_tile": ("region_challenge", "run", "offer"),
}
BOUND_CASE_VARIANTS = {
    "contiguous_prefix_180": "tools.pipeline_eval.variants.contiguous_prefix_180",
    "raw_robust": "tools.pipeline_eval.qualification.raw_robust",
    "periodic_anchor": "tools.pipeline_eval.qualification.periodic_anchor_trial",
}
NATIVE_PUBLIC_VARIANTS = {
    "portable_native_joint": "joint",
    "portable_native_clock": "smooth-clock",
}
DEADLINE_VARIANTS = {f"deadline_{seconds}s": seconds for seconds in (30, 90, 180)}
FAILED_ONLY = "v5_failed_only"
EXCEPTION_PROBE = "_compact_exception_probe"
OPT_IN_VARIANTS = DEADLINE_VARIANTS.keys() | {
    FAILED_ONLY,
    "interleaved_visits",
    "v5_causal_orbit_fit",
    "v5_previous_orbit",
    "v5_recovery_reads",
}
ID_ONLY_VARIANTS = COLD_VARIANTS.keys() | BOUND_CASE_VARIANTS.keys()
SCREEN_MODES = {"v5_screen_winner": "reference", "v5_screen_secant": "secant"}
VARIANTS = {
    "iq_stream": "Read and decode IQ in bounded blocks",
    "glrt_batch": "Batch the full pilot correlation bank",
    "glrt_cascade": "Screen GLRT cells before the contrast calculation",
    "track_link": "Link native detections using bounded causal state",
    "track_reduce": "Compress track points before position search",
    "orbit_interp": "Reuse orbital states across region searches",
    "shape_score": "Screen below-horizon orbits before full interpolation",
    "v5_lean": "Compute original v5 coordinates without rendering evidence",
    "v5_core": "Run the reduced v5 branch selection, paired fits and cavity decision",
    "v5_one_seed": "Refine one neutral center assignment before the paired v5 cavity fit",
    "v5_first_ranked": "Refine only the first cold-ranked assignment in the v5 cavity fit",
    "v5_shared_search": "Reuse center projections and compact repeated v5 association work",
    "v5_two_refresh": "Limit early compact-v5 fits to two orbit phase refreshes",
    "v5_likelihood_reuse": "Reuse exact native likelihood terms at fitted v5 endpoints",
    "v5_secant_fit": "Use bounded secant steps in the compact v5 position solver",
    "interleaved_visits": "Skip one in four visits per RF channel before the compact fit (opt-in)",
    "v5_orbit_domain": "Extend causal orbit support for compact v5 corner projections",
    "v5_previous_orbit": "Isolate decayed previous elements in compact v5 priors (opt-in)",
    "v5_causal_orbit_fit": "Run compact v5 with three guarded numerical repairs (opt-in)",
    FAILED_ONLY: "Retry only three diagnosed failures after unchanged compact v5 (opt-in)",
    "v5_stable_phase": "Stop orbital updates once receiver position and satellite timings settle",
    "v5_secant_two_refresh": "Combine bounded secant fitting with two early orbit phase refreshes",
    "v5_screen_winner": "Screen initial compact-v5 assignments and finish the winner",
    "v5_screen_secant": "Screen initial compact-v5 assignments using bounded secant fitting",
    "v5_armijo_fit": "Use an Armijo search for compact v5 position fitting",
    "v5_armijo_tail": "Check a coarse Armijo stop with two symmetric linearizations",
    "v5_armijo_finish": "Run Armijo fitting through the final compact v5 selection",
    "v5_armijo_aligned_finish": "Align the ordered Armijo phase seed before final reassociation",
    "v5_pruned_finish": "Check residual-fold and family support before final compact v5 searches",
    "v5_stream_recovery": "Bound resident orbital geometry in late compact v5 recovery",
    "v5_screened_pruned_finish": "Screen the initial assignment and prune the aligned v5 finish",
    "v5_lazy_pair": "Defer paired fit work on rejected compact v5 proposals",
    "v5_discovery_memory": "Reuse the repeated discovery association before the secant cavity fit",
    "v5_sparse_discovery": "Keep sparse early nomination diagnostics through the compact v5 finish",
    "v5_compact_memory_combined": "Use sparse discovery and sampled family widths in compact v5",
    "v5_signed_context_memory": "Sample family and signed-context widths in compact v5",
    "v5_nomination_memory": "Bound compact v5 family-cavity nomination memory",
    "v5_recovery_cache_memory": "Bound dirty orbit scratch cache in the compact v5 finish",
    "v5_recovery_reads": "Read late compact v5 orbital scratch in row order (opt-in)",
    "projected_fit": "Fit position after profiling per-track offsets",
    "shared_doppler": "Fit position with shared receiver clocks and satellite time shifts",
    "anchor_receiver": "Replay 16 IQ windows with the optimized historical detector and refit v5",
    "glrt_odd_channels": "Use all visits to odd RF channels before tracking and v5 positioning",
    "glrt_even_channels": "Use all visits to even RF channels before tracking and v5 positioning",
    "orbit_projector": "Project Doppler and its phase derivative from orbit knots in one loop",
    "compact_finish": "Continue the compact cavity worker through frozen baseline adoption",
    "v5_recovery_bank_reuse": "Reuse immutable residual orbital geometry in final compact v5",
    "v5_batched_salvage": "Bound the Gaussian score batches in v5 conservative recovery",
    "v5_catalogue_memory": "Batch catalogue propagation and retain fresh residual orbit arrays",
    "v5_stream_prepare": "Read native GLRT records incrementally ahead of the compact v5 finish",
    "catalogue_checksum": "Validate causal orbital element checksums with a byte lookup in v5",
    "arc_validation": "Assign orbits on early track samples and verify them on later samples",
    "sweep_schedule": "Use alternate complete eight-channel sweeps before tracking and fitting",
    "iq_position": "Localize from newly computed GLRT detections in archived IQ",
    "point_votes_global": "Vote globally from GLRT point pairs and causal TLE",
    "point_votes_matched_tile": "Vote from GLRT point pairs within the original search tile",
    "rate_triplets_global": "Search globally from GLRT frequency triplets and causal TLE",
    "rate_triplets_matched_tile": "Search from GLRT frequency triplets within the original tile",
    "pass_geometry_global": "Infer two candidate sites per pass from measured Doppler curvature",
    "pass_geometry_matched_tile": "Fit pass geometry and receiver position on the original tile",
    "joint_pass_id_matched_tile": "Fit joint pass identities from GLRT on the original tile",
    "region_challenge_matched_tile": "Challenge the original tile against its neighbors from GLRT",
    "folded_doppler_global": "Search globally by folding GLRT Doppler and causal TLE predictions",
    "folded_doppler_matched_tile": "Fold GLRT Doppler predictions within the original tile",
    "contiguous_prefix_180": "Fit compact v5 on the first 180 seconds of capture-era GLRT",
    "raw_robust": "Rebuild tracks from complete capture-era GLRT and fit robust EM",
    "periodic_anchor": "Mix complete GLRT archives using one capture-era sweep every 64 sweeps",
    "robust_orbit_fit": "Refine fixed anonymous track assignments with orbital range rate",
    "robust_support": "Check a one-tile anonymous-track fit against held samples",
    "joint_orbits": "Fit joint orbit assignments from anonymous tracks on one supplied tile",
    "portable_native_joint": "Run the standalone joint receiver on complete native factors",
    "portable_native_clock": "Run the standalone smooth-clock receiver on complete native factors",
    **{
        variant: f"Run compact v5 with a smooth-clock fallback within {seconds} seconds (opt-in)"
        for variant, seconds in DEADLINE_VARIANTS.items()
    },
}
PANELS = (
    "smoke",
    "roof16",
    "ds26-common127",
    "ds26-all159",
    "ds26-excluded32",
    "transfer124",
    "transfer16",
)
DEFAULT_OUT = Path.home() / ".cache" / "leo" / "pipeline-eval"
THREAD_ENV = {
    k: "1"
    for k in (
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "BLIS_NUM_THREADS",
    )
}


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()


def local_output(path):
    path = Path(path).expanduser().resolve()
    if path.is_relative_to("/mnt/qnap01"):
        raise ValueError("the QNAP adapter is read-only; choose a local output directory")
    return path


def write(path, data):
    path = local_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        try:
            stream.write(data)
            stream.flush()
            os.replace(stream.name, path)
        finally:
            Path(stream.name).unlink(missing_ok=True)


def save_json(path, obj):
    write(path, json.dumps(obj, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n")


def references(panel, selected):
    from . import corpus

    source = "transfer124" if panel == "transfer16" else panel
    rows = list(corpus.references(source))
    if panel == "transfer16":
        # Pick whole acquisition pairs in each input family, independently of scores.
        keys = {(r["group"], r["recording"]) for r in rows}
        order = sorted(keys, key=lambda k: hashlib.sha256(encoded(["transfer16-v1", *k])).digest())
        pairs = {pair for g in {k[0] for k in keys} for pair in [k for k in order if k[0] == g][:2]}
        rows = [r for r in rows if (r["group"], r["recording"]) in pairs]
        if len(rows) != 16:
            raise ValueError("transfer16 requires paired queries in four groups")
    if selected:
        unknown = set(selected) - {r["id"] for r in rows}
        if unknown:
            raise ValueError(f"unknown case IDs in {panel}: {sorted(unknown)}")
        rows = [r for r in rows if r["id"] in selected]
    return source, rows


def public_cases(panel, refs, cache):
    from . import corpus

    ids = {r["id"] for r in refs}
    inputs = {case["id"]: case for case, _ in corpus.cases(panel, cache, only=ids)}
    if inputs.keys() != ids:
        raise ValueError("corpus adapter did not return the full selected roster")
    return [inputs[r["id"]] for r in refs]


def read_predictions(path):
    records = {}
    with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as stream:
        for number, line in enumerate(stream, 1):
            item = json.loads(line)
            case = item["id"]
            if case in records:
                raise ValueError(f"duplicate prediction at line {number}: {case}")
            validate_result(item["result"])
            encoded(item)
            records[case] = item
    return records


def module_name(variant):
    if variant == "v5_stable_phase":
        return "tools.pipeline_eval.variants.stable_phase"
    if variant in ("v5_one_seed", "v5_first_ranked"):
        return "tools.pipeline_eval.variants.v5_search_budget"
    if variant in ("glrt_odd_channels", "glrt_even_channels"):
        return "tools.pipeline_eval.variants.channel_schedule"
    if variant in SCREEN_MODES:
        return "tools.pipeline_eval.variants.v5_screen_winner"
    if variant == "original-grid":
        return "tools.pipeline_eval.qualification.regional"
    if variant.startswith("original-") and variant.removeprefix("original-") in ROLES:
        return "tools.pipeline_eval.qualification.original_v5"
    if variant in COLD_VARIANTS:
        return "tools.pipeline_eval.variants." + COLD_VARIANTS[variant][0]
    if variant in BOUND_CASE_VARIANTS:
        return BOUND_CASE_VARIANTS[variant]
    if variant in NATIVE_PUBLIC_VARIANTS:
        return "tools.pipeline_eval.variants.lean_receiver_cli_benchmark"
    if variant in DEADLINE_VARIANTS:
        return "tools.pipeline_eval.qualification.deadline_benchmark"
    if variant == FAILED_ONLY:
        return "tools.pipeline_eval.qualification.failed_only_benchmark"
    if variant == EXCEPTION_PROBE:
        return "tools.pipeline_eval.variants.v5_secant_fit"
    if variant == "v5_recovery_reads":
        return "tools.pipeline_eval.qualification.recovery_reads_benchmark"
    if variant == "joint_orbits":
        return "tools.pipeline_eval.variants.joint_orbits_benchmark"
    if variant not in VARIANTS:
        raise ValueError(f"unknown experiment {variant}")
    return "tools.pipeline_eval.variants." + variant


def implementation_digest(variant, module):
    digest = hashlib.sha256(module.read_bytes())
    if variant == FAILED_ONLY:
        digest.update(module.with_name("deadline_benchmark.py").read_bytes())
        candidate = module.parent.parent / "variants" / "v5_causal_orbit_fit.py"
        digest.update(implementation_digest("v5_causal_orbit_fit", candidate).encode())
        return digest.hexdigest()
    if variant in DEADLINE_VARIANTS:
        from inspect import getsource

        variants = module.parent.parent / "variants"
        digest.update(b"\0seconds=" + str(DEADLINE_VARIANTS[variant]).encode())
        digest.update(getsource(run_one).encode())
        for name in (
            "deadline_receiver.py",
            "v5_secant_fit.py",
            "orbit_projector.py",
            "orbit_projector.c",
            "v5_core.py",
            "v5_lean.py",
        ):
            digest.update((variants / name).read_bytes())
        digest.update(
            implementation_digest(
                "portable_native_clock", variants / "lean_receiver_cli_benchmark.py"
            ).encode()
        )
        return digest.hexdigest()
    if variant == "v5_recovery_reads":
        variants = module.parent.parent / "variants"
        for name in ("v5_recovery_reads.py", "v5_discovery_memory.py", "v5_secant_fit.py"):
            digest.update((variants / name).read_bytes())
        for name in (
            "recovery_reads_worker.py",
            "nomination_memory_worker.py",
            "signed_context_memory_worker.py",
            "compact_memory_combined_worker.py",
            "composed_memory_worker.py",
            "working_memory_worker.py",
            "secant_end_to_end_worker.py",
        ):
            digest.update(module.with_name(name).read_bytes())
        digest.update(
            implementation_digest(
                "v5_recovery_cache_memory", variants / "v5_recovery_cache_memory.py"
            ).encode()
        )
        return digest.hexdigest()
    if variant in NATIVE_PUBLIC_VARIANTS:
        from .variants.lean_receiver_cli import source_manifest

        digest.update(encoded(source_manifest(NATIVE_PUBLIC_VARIANTS[variant])))
    cold_module = COLD_VARIANTS[variant][0] if variant in COLD_VARIANTS else None
    if cold_module == "folded_doppler":
        digest.update(module.with_suffix(".c").read_bytes())
    if cold_module in ("pass_geometry", "joint_pass_id", "region_challenge"):
        digest.update(module.with_name("rate_triplets.py").read_bytes())
    if cold_module == "region_challenge":
        digest.update(module.with_name("joint_pass_id.py").read_bytes())
    if variant == "contiguous_prefix_180":
        digest.update(module.with_name("contiguous_prefix.py").read_bytes())
        trial = module.parent.parent / "qualification" / "contiguous_prefix_trial.py"
        digest.update(trial.read_bytes())
    if variant == "periodic_anchor":
        variants = module.parent.parent / "variants"
        for name in (
            "periodic_anchor.py",
            "orbit_projector.c",
            "orbit_projector.py",
            "v5_core.py",
            "v5_lean.py",
        ):
            digest.update((variants / name).read_bytes())
    if variant in ("robust_orbit_fit", "robust_support"):
        digest.update(module.with_name("robust_em.py").read_bytes())
        digest.update(module.with_name("projected_fit.py").read_bytes())
        digest.update((module.parent.parent / "reference" / "grid.py").read_bytes())
    if variant == "joint_orbits":
        for name in ("joint_orbits.py", "robust_orbit_fit.py", "robust_em.py", "projected_fit.py"):
            digest.update(module.with_name(name).read_bytes())
        digest.update((module.parent.parent / "reference" / "grid.py").read_bytes())
        sky = module.parents[3] / "src" / "leo" / "sky"
        for name in ("frames.py", "propagation.py", "sampling.py"):
            digest.update((sky / name).read_bytes())
    if variant == "v5_secant_two_refresh":
        for name in (
            "v5_secant_fit.py",
            "v5_two_refresh.py",
            "orbit_projector.py",
            "orbit_projector.c",
            "v5_core.py",
            "v5_lean.py",
        ):
            digest.update(module.with_name(name).read_bytes())
    if variant in SCREEN_MODES:
        mode = SCREEN_MODES[variant]
        digest.update(b"\0mode=" + mode.encode())
        for name in ("orbit_projector.py", "orbit_projector.c", "v5_core.py", "v5_lean.py"):
            digest.update(module.with_name(name).read_bytes())
        if mode == "secant":
            digest.update(module.with_name("v5_secant_fit.py").read_bytes())
    if variant == "v5_armijo_tail":
        digest.update(b"\0method=tail")
    armijo_finish = ("v5_armijo_fit.py", "compact_finish.py")
    aligned_finish = ("v5_armijo_finish.py", *armijo_finish)
    aligned_worker = ("v5_armijo_aligned_finish.py", *aligned_finish)
    composed_memory = (
        "v5_composed_memory.py",
        "v5_track_projection.py",
        "v5_stream_recovery.py",
        "v5_tiled_salvage.py",
        "history_stream_prep.py",
        "prep_stream_sky.py",
        "v5_catalogue_memory.py",
        *aligned_worker,
    )
    family_memory = ("v5_sparse_discovery.py", "v5_family_memory.py", *composed_memory)
    signed_memory = ("v5_compact_memory_combined.py", *family_memory)
    nomination_memory = ("v5_signed_context_memory.py", *signed_memory)
    memory_policies = {
        "v5_sparse_discovery": composed_memory,
        "v5_compact_memory_combined": family_memory,
        "v5_signed_context_memory": signed_memory,
        "v5_nomination_memory": nomination_memory,
        "v5_recovery_cache_memory": ("v5_nomination_memory.py", *nomination_memory),
    }
    compact_policies = {
        "interleaved_visits": ("v5_secant_fit.py",),
        "v5_stable_phase": ("v5_secant_fit.py",),
        "v5_armijo_fit": ("v5_secant_fit.py",),
        "v5_armijo_tail": ("v5_armijo_fit.py", "v5_secant_fit.py"),
        "v5_orbit_domain": ("v5_secant_fit.py",),
        "v5_previous_orbit": ("v5_secant_fit.py",),
        "v5_causal_orbit_fit": (
            "v5_orbit_domain.py",
            "v5_previous_orbit.py",
            "v5_cavity_isolation.py",
            "v5_optional_cavity.py",
            "v5_secant_fit.py",
        ),
        "v5_armijo_finish": armijo_finish,
        "v5_armijo_aligned_finish": aligned_finish,
        "v5_pruned_finish": aligned_worker,
        "v5_stream_recovery": aligned_worker,
        "v5_screened_pruned_finish": (
            "v5_pruned_finish.py",
            "v5_screen_winner.py",
            "v5_shared_search.py",
            *aligned_worker,
        ),
        "v5_discovery_memory": ("v5_secant_fit.py",),
        "v5_lazy_pair": ("compact_finish.py",),
        "v5_recovery_bank_reuse": ("compact_finish.py",),
        **memory_policies,
    }
    if variant in compact_policies:
        for name in (
            *compact_policies[variant],
            "orbit_projector.py",
            "orbit_projector.c",
            "v5_core.py",
            "v5_lean.py",
        ):
            digest.update(module.with_name(name).read_bytes())
    if variant in memory_policies or variant in (
        "v5_armijo_aligned_finish",
        "v5_pruned_finish",
        "v5_stream_recovery",
        "v5_screened_pruned_finish",
    ):
        phase_seed = module.parent.parent / "qualification" / "armijo_finish_phase_retry.py"
        digest.update(phase_seed.read_bytes())
    return digest.hexdigest()


def _input_receipt(binding):
    if binding is None:
        return dict(input_binding=None, input_sha256=None)
    return dict(
        input_binding=binding,
        input_sha256=binding.get("input_sha256") or hashlib.sha256(encoded(binding)).hexdigest(),
    )


def _run_cold(variant, case, entry, directory):
    from .qualification import cold_input

    if set(case) != {"id"}:
        raise ValueError("Cold workers accept only a recording ID")
    _, method, tile_format = COLD_VARIANTS[variant]
    tile = None
    try:
        capture = cold_input.load(case["id"])
        if tile_format is not None:
            offers = cold_input.matched_offers(case["id"])
            if len(offers) != 1:
                raise FileNotFoundError("Matched-tile search requires one frozen original offer")
            offer = offers[0]
            tile = dict(
                id=offer["id"], center=offer["center"], width_km=offer.get("width_km", 25.0)
            )
            if tile_format == "center" and tile["width_km"] != 25.0:
                raise FileNotFoundError("This matched-tile solver requires a 25 km original offer")
    except OSError as exc:
        return dict(
            status="unavailable",
            reason=str(exc),
            boundary="Frozen GLRT candidate probes and causal TLE to cold position",
            metrics={},
            arms={arm: {"latlon": None} for arm in ARMS},
        ), _input_receipt(None)

    binding = dict(
        case_id=capture.case_id,
        native_sha256=capture.native_sha256,
        catalog_sha256=capture.catalog_sha256,
        cutoff_utc_ns=capture.cutoff_utc_ns,
        catalog_timestamp_ns=capture.catalog_timestamp_ns,
    )
    if tile is not None:
        binding["matched_tile"] = tile
        if tile_format == "center":
            tile = tuple(tile["center"])
    receipt = _input_receipt(binding)
    save_json(directory / "cold-input.json", receipt)
    return getattr(entry, method)(capture, tile=tile), receipt


def child(variant, request, target, directory):
    if variant in DEADLINE_VARIANTS or variant == FAILED_ONLY:
        raise ValueError("routed policies must run in the benchmark supervisor")
    entry = importlib.import_module(module_name(variant))
    source_digest = implementation_digest(variant, Path(entry.__file__))
    case = json.loads(Path(request).read_bytes())
    directory = local_output(directory)
    local_output(target)
    start = time.perf_counter()
    input_receipt = {}
    if variant in COLD_VARIANTS:
        result, input_receipt = _run_cold(variant, case, entry, directory)
    elif variant in BOUND_CASE_VARIANTS:
        if set(case) != {"id"}:
            raise ValueError("Archive-bound workers accept only a recording ID")
        result = entry.run(case, directory)
        input_receipt = _input_receipt(result.pop("input_binding", None))
    elif variant == "joint_orbits":
        result = entry.run(case, directory)
        input_receipt = _input_receipt(result.pop("input_binding", None))
    elif variant in NATIVE_PUBLIC_VARIANTS:
        result = entry.run(case, NATIVE_PUBLIC_VARIANTS[variant])
        input_receipt = _input_receipt(result.pop("input_binding", None))
    elif variant in ("glrt_odd_channels", "glrt_even_channels", "v5_one_seed", "v5_first_ranked"):
        result = entry.run(case, directory, variant)
    elif variant in SCREEN_MODES:
        result = entry.run(case, directory, mode=SCREEN_MODES[variant])
    elif variant in ("v5_secant_fit", EXCEPTION_PROBE):
        result = entry.run(case, directory, mode="secant")
        if variant == EXCEPTION_PROBE and result.get("reason") == "AssertionError":
            from .qualification.failed_only_benchmark import previous_trace

            input_receipt["failure_trace"] = previous_trace(directory)
    elif variant == "v5_armijo_tail":
        result = entry.run(case, directory, method="tail")
    elif variant.startswith("original-") and variant != "original-grid":
        result = entry.run(case, directory, variant.removeprefix("original-"))
    else:
        result = entry.run(case, directory)
    validate_result(result)
    elapsed = time.perf_counter() - start
    artifacts = {}
    for name in ("waveform-comparison.json", "waveform-parity.json", "iq-replay.json"):
        path = Path(directory) / name
        if path.is_file():
            artifacts[name] = json.loads(path.read_bytes())
    save_json(
        Path(target),
        dict(
            id=case["id"],
            result=result,
            call_s=elapsed,
            implementation_sha256=source_digest,
            artifacts=artifacts,
            **input_receipt,
        ),
    )


def run_one(variant, case, base, seconds, affinity, output=None, *, supervised=False):
    # Each invocation owns a private directory; incomplete workers cannot publish an old result.
    if variant.startswith("original-") and variant != "original-grid":
        from .qualification.original_v5 import BULK, CACHE

        # The historical evidence writer accepts only these roots. Let the supervising
        # process own its scratch directory so an outer worker timeout also cleans it.
        scratch = Path(os.environ.get("LEO_PIPELINE_EVAL_V5_SCRATCH", BULK / "leo-dev")).resolve()
        if (
            not base.is_relative_to(BULK)
            and not base.is_relative_to(CACHE)
            and scratch.is_relative_to(BULK)
            and scratch.is_dir()
        ):
            base = scratch
    with tempfile.TemporaryDirectory(prefix=variant + "-", dir=base) as scratch:
        directory = Path(scratch)
        request, target = directory / "input.json", directory / "output.json"
        write(request, encoded(case))
        command = [
            sys.executable,
            "-B",
            "-m",
            "tools.pipeline_eval",
            "_worker",
            variant,
            str(request),
            str(target),
            str(directory),
        ]
        if affinity is not None:
            command = ["taskset", "-c", str(affinity), *command]
        if supervised:
            from .qualification.deadline_benchmark import watched_command

            command = watched_command(command, os.getpid())
        start = time.perf_counter()
        with (directory / "run.log").open("wb") as log:
            proc = subprocess.Popen(
                command,
                stdout=log,
                stderr=log,
                cwd=ROOT,
                env={**os.environ, **THREAD_ENV},
                start_new_session=True,
            )
            try:
                proc.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                status, reason = "timed_out", f"worker exceeded {seconds:g} seconds"
            else:
                status, reason = "failed", f"worker exited with status {proc.returncode}"
            finally:
                if supervised:
                    with suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
        elapsed = time.perf_counter() - start
        if proc.returncode == 0 and target.is_file():
            item = json.loads(target.read_bytes())
            if evidence := item["result"].get("evidence"):
                if evidence["file"] != "experimental-evidence.zip" or output is None:
                    raise ValueError("unexpected scientific evidence file")
                source = directory / evidence["file"]
                with source.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if digest != evidence["sha256"].removeprefix("sha256:"):
                    raise ValueError("scientific evidence digest differs from original worker")
                relative = Path("evidence") / case["id"] / source.name
                retained = local_output(output / relative)
                retained.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, retained)
                evidence["file"] = str(relative)
        else:
            with (directory / "run.log").open("rb") as log:
                log.seek(max(0, log.seek(0, 2) - 3000))
                detail = log.read().decode(errors="replace").strip()
            item = dict(
                id=case["id"],
                result=dict(status=status, reason=reason, boundary="worker", metrics={}),
                detail=detail,
            )
            cold_receipt = directory / "cold-input.json"
            if variant in COLD_VARIANTS and cold_receipt.is_file():
                item.update(json.loads(cold_receipt.read_bytes()))
        item["worker_wall_s"] = elapsed
        if variant in ID_ONLY_VARIANTS:
            item.setdefault("input_sha256", None)
        elif "input_sha256" not in item:
            item["input_sha256"] = hashlib.sha256(encoded(case)).hexdigest()
        return item


def scored_files(panel, method, refs, records, folder):
    summary, rows = score(refs, records)
    summary.update(schema_version=1, panel=panel, method=method, ids=[r["id"] for r in refs])
    with tempfile.TemporaryFile(mode="w+", newline="") as stream:
        out = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        out.writeheader()
        out.writerows(rows)
        stream.seek(0)
        write(folder / "errors.csv", stream.read().encode())
    if panel in ("transfer16", "transfer124"):
        from .qualification.transfer_figures import write_run_figures

        write_run_figures(refs, records, folder, method)
    elif all(
        r["group"] in ("DS26", "DS29") and all(k in r["reference"] for k in ROLES) for r in refs
    ):
        from .position_figure import write_run_figures

        write_run_figures(refs, records, folder, method)
    return summary


def number(value):
    return f"{value:.3f}" if value is not None else "-"


def show_baseline(rows):
    print("dataset\tcondition\tmethod\tarm\tfixes/attempts\twithin_5km\tmedian_km\tp95_km\tmax_km")
    for row in rows:
        e = row["error_km"]
        print(
            row["group"],
            row["condition"],
            row["method"],
            row["arm"],
            f"{e['n']}/{row['attempts']}",
            row["within_km"]["5"],
            *(number(e[k]) for k in ("p50", "p95", "max")),
            sep="\t",
        )


def show_result(summary):
    print(f"{summary['panel']}  {summary['method']}  {summary['statuses']}")
    ratios = summary["timing"]["paired_ratio_control_over_candidate"]
    if ratios["n"]:
        print(
            f"  Median paired control/candidate time ratio {ratios['p50']:.2f}× (n={ratios['n']})"
        )
    for row in summary["groups"]:
        if row["decision_counts"].get("stage_only") == row["attempts"]:
            if row["arm"] == "c0":
                print(
                    f"  {row['group']} {row['condition']} stage-only measurement "
                    f"(n={row['attempts']})"
                )
            continue
        e, checks = row["error_km"], row["checks"]
        gate = "-" if checks is None else ("pass" if all(checks.values()) else "fail")
        print(
            f"  {row['group']} {row['condition']} {row['arm']}: {e['n']}/{row['attempts']} fixes, "
            f"median {number(e['p50'])} km, P95 {number(e['p95'])} km, v5 panel {gate}"
        )


def meets_reference(summary):
    present = [g for g in summary["groups"] if g["condition"] == "present"]
    return (
        bool(present)
        and all(g["keeps_v5_panel"] is True for g in present)
        and not any(
            g["false_publications"] or g["decision_counts"].get("withheld", 0) != g["attempts"]
            for g in summary["groups"]
            if g["condition"] == "missing"
        )
    )


def compare_outputs(args):
    summaries = []
    for folder in sorted((args.out / args.panel).glob("*")):
        path = folder / "current" / "summary.json"
        if not path.is_file():
            path = folder / "summary.json"
        if path.is_file():
            summaries.append(json.loads(path.read_bytes()))
    if not summaries:
        raise ValueError(f"no complete run summaries in {args.out / args.panel}")
    rows = []
    for s in summaries:
        for g in s["groups"]:
            e, t = g["error_km"], s["timing"]["paired_ratio_control_over_candidate"]
            rows.append(
                dict(
                    method=s["method"],
                    group=g["group"],
                    condition=g["condition"],
                    arm=g["arm"],
                    attempts=g["attempts"],
                    fixes=e["n"],
                    within_5km=g["within_km"]["5"],
                    median_km=e["p50"],
                    p95_km=e["p95"],
                    worst_km=e["max"],
                    keeps_v5=g["keeps_v5_panel"],
                    decisions=json.dumps(g.get("decision_counts", {}), sort_keys=True),
                    panel_timing_pairs=t["n"],
                    panel_median_stage_time_ratio=t["p50"],
                )
            )
    with tempfile.TemporaryFile(mode="w+", newline="") as stream:
        out = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        out.writeheader()
        out.writerows(rows)
        stream.seek(0)
        table = stream.read()
    write(args.out / args.panel / "comparison.csv", table.encode())
    print(table, end="")


def run_folder(root, panel, method, refs, subset):
    path = root / panel / method
    if subset:
        digest = hashlib.sha256(encoded([r["id"] for r in refs])).hexdigest()
        path /= "subset-" + digest[:12]
    return local_output(path)


def new_generation(folder):
    generations = local_output(folder / "runs")
    generations.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=time.strftime("%Y%m%dT%H%M%S-"), dir=generations))


def publish_generation(folder, generation, report):
    """Switch complete run outputs while leaving the preceding run readable."""
    save_json(generation / "summary.json", report)
    with tempfile.TemporaryDirectory(dir=local_output(folder)) as tmp:
        tmp = Path(tmp)
        for name in (
            "summary.json",
            "predictions.jsonl",
            "errors.csv",
            "cases",
            "position-errors-fitted_c.png",
            "position-errors-c0.png",
        ):
            item = folder / name
            if (generation / name).exists() and not item.exists() and not item.is_symlink():
                (tmp / name).symlink_to(Path("current") / name)
                os.replace(tmp / name, item)
        (tmp / "current").symlink_to(generation.relative_to(folder))
        os.replace(tmp / "current", folder / "current")


def execute(args, source, refs):
    methods = list(dict.fromkeys(args.variant or ["all"]))
    if "all" in methods:
        methods = [
            method for method in VARIANTS if method not in OPT_IN_VARIANTS or method in methods
        ]
    if args.jobs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("jobs and timeout must be finite and positive")
    native_methods = set(methods) & NATIVE_PUBLIC_VARIANTS.keys()
    deadline_methods = set(methods) & DEADLINE_VARIANTS.keys()
    routed_methods = deadline_methods | ({FAILED_ONLY} & set(methods))
    inputs = (
        public_cases(source, refs, args.cache)
        if set(methods) - ID_ONLY_VARIANTS - native_methods - routed_methods
        else []
    )
    ids = [{"id": r["id"]} for r in refs]
    native_cases = []
    if native_methods:
        from .variants.lean_receiver_cli_benchmark import cases

        native_cases = cases(source, [r["id"] for r in refs])
    if deadline_methods:
        from .qualification import deadline_benchmark

        deadline_cases = deadline_benchmark.cases(source, [r["id"] for r in refs], args.cache)
    if FAILED_ONLY in routed_methods:
        from .qualification import failed_only_benchmark

        failed_only_cases = failed_only_benchmark.cases(source, [r["id"] for r in refs], args.cache)
    work = local_output(args.out / "work")
    work.mkdir(parents=True, exist_ok=True)
    available = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    folders = {m: run_folder(args.out, args.panel, m, refs, args.case) for m in methods}
    digest = hashlib.sha256(encoded([r["id"] for r in refs])).hexdigest()
    working = {m: new_generation(folder) for m, folder in folders.items()}
    todo = []
    for method in methods:
        selected = ids if method in ID_ONLY_VARIANTS else inputs
        if method in native_methods:
            selected = native_cases
        elif method in deadline_methods:
            selected = deadline_cases
        elif method == FAILED_ONLY:
            selected = failed_only_cases
        todo.extend((method, case) for case in selected)
    results = {m: {} for m in methods}
    failures = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        jobs = {
            pool.submit(
                deadline_benchmark.run
                if m in deadline_methods
                else (failed_only_benchmark.run if m == FAILED_ONLY else run_one),
                m,
                case,
                work,
                args.timeout,
                available[i % len(available)] if available and args.pin else None,
                working[m],
            ): m
            for i, (m, case) in enumerate(todo)
        }
        for job in as_completed(jobs):
            method, item = jobs[job], job.result()
            results[method][item["id"]] = item
            state = item["result"]["status"]
            if state in ("timed_out", "failed") or (args.require_inputs and state == "unavailable"):
                failures += 1
            save_json(working[method] / "cases" / (item["id"] + ".json"), item)
            print(
                f"{method} {item['id']} {item['result']['status']} {item['worker_wall_s']:.2f}s",
                flush=True,
            )
    for method, records in results.items():
        folder = working[method]
        write(
            folder / "predictions.jsonl", b"".join(encoded(records[r["id"]]) + b"\n" for r in refs)
        )
        report = scored_files(args.panel, method, refs, records, folder)
        module = ROOT / (module_name(method).replace(".", "/") + ".py")
        report["run"] = dict(
            jobs=args.jobs,
            timeout_s=args.timeout,
            pinned=args.pin,
            numerical_threads=1,
            reference_roster_sha256=digest,
            implementation_sha256=implementation_digest(method, module),
        )
        if method in deadline_methods:
            report["run"].update(
                deadline_total_s=DEADLINE_VARIANTS[method],
                deadline_reserve_s=deadline_benchmark.policy.RESERVE_S,
            )
        publish_generation(folders[method], folder, report)
        show_result(report)
        if args.require_v5 and not meets_reference(report):
            failures += 1
    return int(bool(failures))


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["baseline", "--panel", "roof16"]
    if argv and argv[0] == "_worker":
        child(*argv[1:])
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show available panels and receiver experiments")
    benchmark = sub.add_parser(
        "benchmark", help="regenerate receiver benchmark scores and charts from sealed evidence"
    )
    benchmark_source = benchmark.add_mutually_exclusive_group()
    benchmark_source.add_argument(
        "--receiver",
        choices=(
            "fixed",
            "staggered",
            "one-lane",
            "antenna-confirmation",
            "original-support",
            "receiver-deadline",
        ),
        default="fixed",
        help="select a named receiver benchmark and its comparison gallery",
    )
    benchmark_source.add_argument(
        "--study", type=Path, help="regenerate position scores and charts for a sealed study"
    )
    benchmark.add_argument(
        "--pack", action="store_true", help="package a study's position and sealed stage charts"
    )
    benchmark.add_argument("--out", type=Path, help="output directory (must be new with --pack)")
    full = sub.add_parser("full", help="replay a complete frozen roof recording from IQ through v5")
    full.add_argument("--case", required=True, help="frozen DS26 or DS29 roof recording ID")
    full.add_argument("--detector", choices=("ordinary", "single-rx0"), default="ordinary")
    full.add_argument("--out", type=Path, default=DEFAULT_OUT)
    full.add_argument("--cpus", type=int, nargs=2, help="two distinct available CPU indices")
    full.add_argument("--timeout", type=int, default=1200, help="complete recording deadline in s")
    full.add_argument("--require-v5", action="store_true")
    compare = sub.add_parser("compare", help="compare all completed receivers on the chosen panel")
    compare.add_argument("--panel", choices=PANELS, default="roof16")
    compare.add_argument("--out", type=Path, default=DEFAULT_OUT)
    coverage = sub.add_parser("coverage", help="report distance at fixed all-recording coverage")
    coverage.add_argument("--panel", choices=PANELS, required=True)
    coverage.add_argument("--case", action="append", help="explicit subset of offered recordings")
    coverage.add_argument("--predictions", type=Path, required=True)
    coverage.add_argument("--out", type=Path, help="also save the report as JSON")
    plot = sub.add_parser("plot", help="plot measured error distributions alongside the controls")
    plot.add_argument("--panel", choices=PANELS, default="roof16")
    plot.add_argument("--out", type=Path, default=DEFAULT_OUT)
    plot.add_argument("--arm", choices=("c0", "fitted_c"), default="fitted_c")
    plot.add_argument("--variant", action="append", help="include a saved positioning method")
    figures = sub.add_parser("figures", help="generate one matched v5 comparison per modification")
    figures.add_argument("--out", type=Path, default=DEFAULT_OUT / "figures")
    figures.add_argument("--arm", choices=("c0", "fitted_c", "both"), default="both")
    figures.add_argument("--variant", action="append", help="limit output to named modifications")
    figures.add_argument(
        "--runs", type=Path, help="read your completed runs instead of the published study"
    )
    figures.add_argument("--evidence", type=Path, help="use fresh matched roof replay JSONL files")
    figures.add_argument(
        "--panel",
        choices=(
            "published",
            "atlas",
            "short-receiver",
            "convergence",
            "screening",
            "matched135",
            "roof16",
            "smoke",
            "ds26-common127",
            "ds26-all159",
            "ds26-excluded32",
            "transfer124",
        ),
        help="default to the roof charts, or choose atlas for all roof and geographic studies",
    )
    figures.add_argument(
        "--additional",
        action="store_true",
        help="include the other roof cohort and two complete IQ recordings",
    )
    for name, help_text in [
        ("baseline", "show frozen v5 and regional receiver error distributions"),
        ("run", "execute receiver modules and score all selected recordings"),
        ("replay", "rerun original v5 science workers or the frozen regional receiver"),
        ("export", "export public case metadata for a separate receiver"),
        ("score", "score a receiver's JSONL predictions against the selected roster"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument(
            "--panel", choices=PANELS, default="smoke" if name in ("run", "replay") else "roof16"
        )
        p.add_argument("--case", action="append", help="select a case ID; repeat to select more")
        p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="results directory")
        if name in ("run", "export", "replay"):
            p.add_argument("--cache", type=Path, default=DEFAULT_OUT / "inputs")
        if name in ("run", "score", "replay"):
            p.add_argument(
                "--require-v5",
                action="store_true",
                help="exit nonzero if either arm fails or lacks a v5 comparison",
            )
        if name in ("run", "replay"):
            if name == "run":
                p.add_argument("--variant", action="append", choices=[*VARIANTS, "all"])
            else:
                p.add_argument(
                    "--role",
                    action="append",
                    choices=[*ROLES, "grid", "all"],
                    help="defaults to original no-repair v5; all selects four v5 roles",
                )
            p.add_argument(
                "--require-inputs",
                action="store_true",
                help="exit nonzero if a requested input is unavailable",
            )
            p.add_argument("--jobs", type=int, default=1, help="maximum concurrent recordings")
            p.add_argument("--timeout", type=float, default=1200, help="seconds per worker")
            p.add_argument("--pin", action="store_true", help="pin each worker to one CPU")
        if name == "score":
            p.add_argument("--predictions", required=True, type=Path)
            p.add_argument("--name", default="external")
    args = parser.parse_args(argv)
    if args.command == "coverage":
        from .coverage import evaluate

        _, refs = references(args.panel, args.case)
        values = evaluate(refs, read_predictions(args.predictions))
        if args.out:
            save_json(local_output(args.out), values)
        print(json.dumps(values, indent=2, allow_nan=False))
        return 0
    if args.command == "list":
        print("Panels: " + ", ".join(PANELS))
        for name, desc in VARIANTS.items():
            print(f"{name:16s} {desc}")
        return 0
    if args.command == "benchmark":
        if args.pack and args.study is None:
            benchmark.error("--pack requires --study")
        if args.study is not None:
            out = local_output(args.out or DEFAULT_OUT / f"{args.study.resolve().name}-benchmark")
            if args.pack:
                from .qualification import study_pack

                study_pack.run(args.study, out)
            else:
                from .qualification import study_benchmark

                study_benchmark.run(args.study, out)
            return 0
        if args.receiver == "antenna-confirmation":
            from .qualification import antenna_benchmark as study
            from .qualification import study_benchmark

            out = local_output(args.out or DEFAULT_OUT / "antenna-confirmation-benchmark")
            study.show(study.run(out), out)
            study_benchmark.render_indexed(out)
            return 0
        if args.receiver == "original-support":
            from .qualification import original_support_benchmark as study

            out = local_output(args.out or DEFAULT_OUT / "original-support-benchmark")
            study.run(out)
            return 0
        if args.receiver == "receiver-deadline":
            from .qualification import receiver_deadline_benchmark as study

            out = local_output(args.out or DEFAULT_OUT / "receiver-deadline-benchmark")
            study.run(out)
            return 0
        if args.receiver == "one-lane":
            from .qualification import one_lane_benchmark as study

            folder = "one-lane-benchmark"
        elif args.receiver == "staggered":
            from .qualification import staggered_benchmark as study

            folder = "staggered-benchmark"
        else:
            from .qualification import complete_detector_roster as study

            folder = "complete-detector-roster"
        out = local_output(args.out if args.out is not None else DEFAULT_OUT / folder)
        study.show(study.run(out), out)
        return 0
    args.out = local_output(args.out)
    if args.command == "figures":
        from .figure_books import generate

        arms = ("fitted_c", "c0") if args.arm == "both" else (args.arm,)
        generate(
            args.out, arms, args.variant, args.runs, args.panel, args.additional, args.evidence
        )
        return 0
    if args.command == "full":
        from .qualification.capture_release import UnsupportedCaptureRelease
        from .qualification.full_v5_check import PRODUCERS
        from .qualification.recording_to_v5 import NATIVE_LIBRARY, run_recording

        panel = (
            "smoke"
            if args.case in PRODUCERS
            else ("ds26-all159" if args.case.startswith("DS26-") else "roof16")
        )
        _, refs = references(panel, [args.case])
        name = "native-to-v5" if args.detector == "ordinary" else "single_rx0"
        base = run_folder(args.out, panel, name, refs, [args.case])
        generation = new_generation(base)
        cpus = args.cpus or sorted(os.sched_getaffinity(0))[:2]
        source = generation / "recording"
        native = os.environ.get("LEO_PIPELINE_EVAL_GLRT_LIBRARY", NATIVE_LIBRARY)
        try:
            kwargs = {} if args.detector == "ordinary" else {"detector": args.detector}
            run_recording(args.case, source, cpus, args.timeout, native, **kwargs)
        except (FileNotFoundError, UnsupportedCaptureRelease) as exc:
            detail = exc.filename if isinstance(exc, FileNotFoundError) else str(exc)
            missing = dict(
                status="unavailable",
                boundary="complete stored IQ to native GLRT and v5",
                reason=f"Required input or runtime is unavailable: {detail}",
                metrics={},
                arms={arm: {"latlon": None} for arm in ("c0", "fitted_c")},
            )
            write(source / "predictions.jsonl", encoded(dict(id=args.case, result=missing)) + b"\n")
        records = read_predictions(source / "predictions.jsonl")
        if set(records) != {args.case}:
            raise ValueError("whole-recording result differs from the selected case")
        write(generation / "predictions.jsonl", (source / "predictions.jsonl").read_bytes())
        report = scored_files(panel, name, refs, records, generation)
        publish_generation(base, generation, report)
        show_result(report)
        print(f"Full recording and scored result: {base / 'current'}")
        return int(
            any(k in report["statuses"] for k in ("failed", "timed_out", "unavailable"))
            or (args.require_v5 and not meets_reference(report))
        )
    if hasattr(args, "cache"):
        args.cache = local_output(args.cache)
    if args.command == "compare":
        compare_outputs(args)
        return 0
    if args.command == "plot":
        from .plot import make_plot

        _, refs = references(args.panel, None)
        directory = local_output(args.out / args.panel)
        target = local_output(directory / f"errors-{args.arm}.png")
        make_plot(refs, directory, args.arm, args.variant, target)
        print(target)
        return 0
    source, refs = references(args.panel, args.case)
    if not refs:
        raise ValueError("empty evaluation panel")
    if args.command == "baseline":
        rows = baseline_rows(refs)
        show_baseline(rows)
        folder = run_folder(args.out, args.panel, "", refs, args.case)
        save_json(folder / "baseline-distributions.json", rows)
    elif args.command == "score":
        if not args.name or Path(args.name).name != args.name or args.name in (".", ".."):
            raise ValueError("name must be a single directory name")
        records = read_predictions(args.predictions)
        folder = run_folder(args.out, args.panel, args.name, refs, args.case)
        generation = new_generation(folder)
        report = scored_files(args.panel, args.name, refs, records, generation)
        write(
            generation / "predictions.jsonl",
            b"".join(encoded(records[k]) + b"\n" for k in sorted(records)),
        )
        publish_generation(folder, generation, report)
        show_result(report)
        return int(args.require_v5 and not meets_reference(report))
    elif args.command == "export":
        cases = public_cases(source, refs, args.cache)
        path = run_folder(args.out, args.panel, "", refs, args.case) / "public-cases.jsonl"
        write(path, b"".join(encoded(case) + b"\n" for case in cases))
        print(f"{len(cases)} public cases written to {path}")
    else:
        if args.command == "replay":
            roles = args.role or ["baseline"]
            if "all" in roles:
                roles = [*ROLES, *(["grid"] if "grid" in roles else [])]
            args.variant = ["original-" + role for role in roles]
        return execute(args, source, refs)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        sys.exit(str(exc))
