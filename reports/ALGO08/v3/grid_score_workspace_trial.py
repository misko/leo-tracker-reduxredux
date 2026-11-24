"""Compare one full standard-grid pair using the retained DS30-0169 likelihood."""

from collections import Counter
from contextlib import contextmanager, nullcontext
from functools import partial
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import struct
import sys
from tempfile import TemporaryDirectory
from time import process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJECTION = Path("/dev/shm/leo-grid-feature-projection-02/native-map.so")
TEMPLATE = Path("/dev/shm/leo-v3-exact-grid-0138-active01/template.so")
TEMPLATE_SHA = "d55bb5bbcd33de7a610221558c3727d86e827279c56b09d9142524afd4e4aa0b"


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def child_cpu():
    use = getrusage(RUSAGE_CHILDREN)
    return round(1e9 * (use.ru_utime + use.ru_stime))


def timing_fill(designs):
    operation = designs.fill

    def fill(*args):
        start = process_time_ns()
        operation(*args)
        designs.counts["fill_cpu_ns"] += process_time_ns() - start

    return fill


def compare(prepared, region, bound, original, archived, target, _original_curved, *, binaries, phase_port):
    import numpy as np
    import grid_fixed_context_trial as fixed
    from grid_design_template import Designs, bind_projected_design
    from grid_feature_projection import Native
    from grid_score_workspace import Workspace, released_cache, scalar_grid_score
    from leo.analysis import position_grid
    from leo.analysis.localization_v3 import event_position, reassociation_context
    from leo.contracts.digests import canonical_digest
    from leo.presentation import localization_v3 as presentation
    from mixture_finish import digest as noise_digest
    from tools.pipeline_eval.variants import v5_core

    args = dict(box_width_km=region.width_km, maximum_seconds=30.)
    built = fixed.clock()
    scan = v5_core.scan_context(prepared, region, noise_digest(prepared["noise"]), bound, "genuine_previous")
    witness = archived["lean_final_fit"]
    order = archived["lean_attempts"][0]["support"]["predictive_labels"]
    endpoints = original["endpoints"]
    arms = witness["arms"]
    for arm, row in arms.items():
        if (scan.fixed_window_noise_sha256 != row["original_noise"]
                or scan.previous_tle_sha256 != row["original_previous_tle"]
                or scan.origin_utc_ns != row["timing_origin_ns"]
                or endpoints[arm] != row["fit"]["position"]):
            raise ValueError("The reconstructed selected likelihood changed")
    expected = [{k: v for k, v in row.items() if k != "latlon"} for row in original["points"]]
    if not original["complete"] or len(expected) != 179:
        raise ValueError("The original retained grid must be complete")

    def context_for(mode):
        start = fixed.clock()
        problems = {}
        for arm, row in arms.items():
            problem, verify = fixed.selected(scan, row, arm, order, witness["model"], None)
            verify()
            problems[arm] = event_position.cached(problem), endpoints[arm]
        context = dict(problems=problems, families=[])
        construction = fixed.elapsed(start)
        start = fixed.clock()
        for arm, (problem, coordinate) in context["problems"].items():
            first = reassociation_context.objective(problem, context, np.asarray(coordinate))
            original_score = next(row["scores"][arm] for row in expected
                                  if [row["east_km"], row["north_km"]] == coordinate)
            if struct.pack("d", first) != struct.pack("d", original_score):
                raise ValueError(f"Endpoint objective differs before {mode} grid")
        return context, dict(build=construction, endpoint_prefill=fixed.elapsed(start))

    common = fixed.elapsed(built)
    contexts = {mode: context_for(mode) for mode in ("ordinary", "workspace")}
    stock_sampler = position_grid.sample_position_grid

    def sweep(mode):
        context, separate = contexts[mode]
        problems = context["problems"]
        caches = {a: released_cache(p, event_position) for a, (p, _) in problems.items()}
        if any(cache is None for cache in caches.values()):
            raise ValueError("Missing original endpoint calculation cache")
        start = fixed.clock()
        native = Native(PROJECTION)
        designs = Designs(TEMPLATE) if mode == "ordinary" else Workspace(binaries["workspace"])
        setup = fixed.elapsed(start)
        start = fixed.clock()
        with (patch.object(presentation, "sample_position_grid", stock_sampler),
              patch.object(designs, "fill", timing_fill(designs)),
              phase_port(bind=partial(bind_projected_design, native, designs)) as phase):
            if mode == "ordinary":
                def objective(arm, xy):
                    return reassociation_context.objective(problems[arm][0], context, np.asarray(xy))

                route = nullcontext((objective, {}, {}))
            else:
                route = scalar_grid_score(stock_sampler, context, endpoints, designs)
            with route as (score, by_arm, dispatch):
                result = presentation.sample_position_grid(score, endpoints, **args)
        clocks = fixed.elapsed(start)
        if result["points"] != expected or result["evaluated_points"] != 179 or not result["complete"]:
            raise ValueError(f"{mode} did not reproduce both arms at every standard node")
        if designs.counts["assembly_calls"] != 356 or native.counts["native_selection"] != 356:
            raise ValueError("Expected both integrated native grid ports on every fresh call")
        return dict(**separate, setup=setup, grid=clocks, template=dict(designs.counts), projection=dict(native.counts),
                    phase=dict(phase), score_dispatch=dict(dispatch), score_by_arm={a: dict(v) for a, v in by_arm.items()},
                    cache={a: dict(cache.cache_info()._asdict()) for a, cache in caches.items()},
                    science=canonical_digest(result["points"]))

    def sample(*_args, **_kwargs):
        target.update(scan_context=common, grid_points=len(expected), checked_scores=2*len(expected),
                      comparison={mode: sweep(mode) for mode in ("ordinary", "workspace")})
        reused = target["comparison"]["workspace"]
        if (reused["score_dispatch"] != {"admitted": 1} or reused["template"]["borrowed_designs"] != 354
                or any(row["scalar_only"] != 177 for row in reused["score_by_arm"].values())):
            raise ValueError("The private workspace did not serve the exact off-endpoint scope")
        return {}

    target["_sample"] = sample


def run(result):
    import grid_fixed_context_trial as fixed
    import grid_phase_state_reuse as phase
    from exact_grid_0138 import deny_backing
    from grid_feature_projection import LIBRARY_SHA, supported_cpu
    from grid_score_workspace import build, check

    sys.addaudithook(deny_backing)
    check(TEMPLATE, TEMPLATE_SHA)
    check(PROJECTION, LIBRARY_SHA)
    if not supported_cpu():
        raise ValueError("The benchmark requires the same checked native x86 projection")

    @contextmanager
    def use_inner_sampler():
        yield Counter()

    with TemporaryDirectory(prefix="leo-v3-grid-workspace-", dir="/tmp") as scratch:
        library = Path(scratch)/"workspace.so"
        start, child = fixed.clock(), child_cpu()
        build(library)
        compile_cost = fixed.elapsed(start) | {"compiler_cpu_ns": child_cpu()-child}
        trial = partial(compare, binaries={"workspace": library}, phase_port=phase.cached_predictive_grid)

        def observed(*args, **kwargs):
            target = args[5]
            target.update(candidate_binary=digest(library), build_clock=compile_cost,
                          protocol=digest(HERE/"grid-score-workspace-protocol.md"),
                          setup_sources={name: digest(HERE/name) for name in (
                              "grid_score_workspace.py", Path(__file__).name)},
                          projection_sha256=LIBRARY_SHA, stock_template_sha256=TEMPLATE_SHA)
            return trial(*args, **kwargs)

        with (patch.object(fixed, "strip", observed),
              patch.object(phase, "cached_predictive_grid", use_inner_sampler)):
            fixed.run(result)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Use one new receipt directly under /dev/shm")
    run(Path(sys.argv[1]))
