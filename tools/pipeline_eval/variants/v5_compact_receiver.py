"""Run the qualified row-major compact v5 decision without qualification wrappers."""

import sys
from collections import Counter
from contextlib import ExitStack, contextmanager
from functools import partial
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output
from tools.pipeline_eval.variants import (
    compact_finish,
    history_stream_prep,
    orbit_projector,
    prep_stream_sky,
    v5_armijo_fit,
    v5_core,
    v5_family_memory,
    v5_lean,
    v5_nomination_memory,
    v5_recovery_cache_memory,
    v5_recovery_reads,
    v5_signed_context_memory,
    v5_sparse_discovery,
    v5_stream_recovery,
    v5_tiled_salvage,
    v5_track_projection,
)

METHOD = "v5_compact_receiver"
BOUNDARY = "Complete row-major compact v5 position from stored native GLRT"


class ScratchRows(v5_stream_recovery.OrbitRows):
    """Keep the qualified float64 scratch row ABI and omit its diagnostic digests."""

    def __init__(self, file, knots):
        self.file, self.knots = file, knots
        self.count, self.finite = 0, True

    def append(self, values):
        array = np.ascontiguousarray(values, dtype=np.float64)
        if array.ndim != 3 or array.shape[1:] != self.shape[1:]:
            raise ValueError("invalid orbit state block shape")
        if len(array):
            self.finite &= bool(np.isfinite(array).all())
            raw = memoryview(array).cast("B")
            if self.file.write(raw) != raw.nbytes:
                raise OSError("short orbit scratch write")
            self.count += len(array)


def scratch_size(position, velocity, usable=None):
    return dict(
        rows=position.count, knots=position.knots, scratch_bytes=position.nbytes + velocity.nbytes
    )


@contextmanager
def row_major_screens():
    from leo.analysis.localization_v3 import (
        reassociation_admission,
        reassociation_screen,
        residual_screen,
    )

    # The request has authenticated the immutable donor source. Only replace its
    # two coarse sweeps. Their fine fits and ordered publication stay in the donor.
    residual = v5_recovery_reads.overlay(
        residual_screen.screen_candidates,
        "        # Stream one phase at a time",
        "        for arm in ARMS:\n            for policy,",
        """        _row_major(
            _nomination_grids, profile_rate, bank, phases, t, query, positions,
            ARMS, {a: np.asarray(target["corrected_hz"][a]) for a in ARMS},
            folds, columns, q, best,
        )
""",
    )
    reassociate = v5_recovery_reads.overlay(
        reassociation_screen.screen,
        "        for phi in np.arange(-30, 31, 2):",
        "        for a in ARMS:\n            finalists =",
        """        _row_major(
            phase_frequency_grids, profile_rate, bank, np.arange(-30, 31, 2),
            ts[ii], positions, ARMS, {a: values[a][ii] for a in ARMS}, q[ii], best,
        )
""",
    )
    with ExitStack() as stack:
        for module, kernel in (
            (residual_screen, v5_recovery_reads.residual_blocks),
            (reassociation_screen, v5_recovery_reads.reassociation_blocks),
        ):
            stack.enter_context(patch.object(module, "_row_major", kernel, create=True))
        stack.enter_context(patch.object(residual_screen, "screen_candidates", residual))
        stack.enter_context(patch.object(reassociation_admission, "screen", reassociate))
        yield


def align_phase_seed(context, before, added):
    """Carry the checked zero initializer for an appended catalogue slot."""
    catalogue = tuple(map(int, context["scan"].norads))
    node, seed = context["node"], context["node"]["seed"]
    state = seed["state"]
    phases = np.asarray(state["phases"])
    if phases.shape == (len(catalogue),):
        return context
    if (
        before is None
        or added in before
        or catalogue != (*before, added)
        or phases.shape != (len(before),)
        or not np.isfinite(phases).all()
        or len(before) != len(set(before))
        or any(
            not 0 <= row["candidate_index"] < len(before)
            or before[row["candidate_index"]] != row["candidate_norad"]
            for row in seed["rows"]
        )
    ):
        raise ValueError("short phase initializer has no exact adopted catalogue-slot authority")
    return dict(
        context, node=dict(node, seed=dict(seed, state=dict(state, phases=np.r_[phases, 0.0])))
    )


@contextmanager
def ordered_phases():
    from leo.analysis.localization_v3 import reassociation_context, reassociation_recovery

    add, remap = reassociation_context.add_target, reassociation_recovery.remap
    before, added = None, None

    def remember(context, *args, **kwargs):
        nonlocal before, added
        previous = tuple(map(int, context["scan"].norads))
        entry = add(context, *args, **kwargs)
        current = tuple(map(int, context["scan"].norads))
        if current != previous:
            number = int(entry["norad"])
            if current != (*previous, number) or entry["candidate_index"] != len(previous):
                raise ValueError("residual addition changed the ordered sky identities")
            before, added = previous, number
        return entry

    def aligned(context, hypothesis, ledger):
        return remap(align_phase_seed(context, before, added), hypothesis, ledger)

    with (
        patch.object(reassociation_context, "add_target", remember),
        patch.object(reassociation_recovery, "remap", aligned),
    ):
        yield


@contextmanager
def projected_orbits(library):
    from leo.analysis.localization_v3 import (
        conservative_recovery,
        discovery,
        family_weighting,
        scan,
    )

    from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

    projector = orbit_projector.Projector(library)

    def evaluate(grid, *args, **kwargs):
        operation = (
            projector.evaluate
            if isinstance(grid, orbit_projector.Stencil)
            else phase_linear_frequency
        )
        return operation(grid, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.object(scan, "prepare_phase_geometry", orbit_projector.prepare))
        for module in (scan, discovery, family_weighting, conservative_recovery):
            stack.enter_context(patch.object(module, "phase_linear_frequency", evaluate))
        yield projector


def infer(prepared, region, backend, stages, archive, identities):
    from leo.analysis.localization_v3 import family_cavity

    nominate, fit = family_cavity.nominate_families, family_cavity.cavity_policy
    cavity = {}

    def keep_nomination(signed):
        cavity["signed"] = signed
        cavity["nominations"] = nominate(signed)
        return cavity["nominations"]

    def keep_fit(signed, nominations):
        cavity["fit"] = fit(signed, nominations)
        return cavity["fit"]

    with (
        patch.object(family_cavity, "nominate_families", keep_nomination),
        patch.object(family_cavity, "cavity_policy", keep_fit),
    ):
        core = v5_core.infer(prepared, region, backend, stages)
        if core["status"] != "ok":
            return core
        if "fit" not in cavity:
            start = perf_counter()
            keep_fit(cavity["signed"], cavity["nominations"])
            stages["cavity"] += perf_counter() - start
        selected = cavity["fit"]
        if selected["status"] != "complete":
            raise ValueError(f"Cavity fit failed: {selected.get('error')}")
        result = compact_finish.finish(
            archive, identities, prepared, cavity["signed"]["scan"], selected, stages
        )
    result["metrics"] = dict(core["metrics"], **result["metrics"])
    return result


class DiscardShortlists:
    def append(self, shortlist):
        pass


def worker(request_file, output, library):
    original, request, job = v5_lean.bound_request(request_file)
    engine = original.ev.owned_import("leo.application.localization_v3_engine", request["source"])
    from leo.analysis.localization_v3 import conservative_recovery, position
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v4.backend import ProcessBound
    from leo.operations.localization_v3_job import read_bound

    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.operations.tle_archive import TleArchiveReader

    backend = ProcessBound(request["native_manifest"], Path(job["output_root"]) / "receipts/native")
    document = read_bound(job["native_input"])
    if document["source"]["session_id"] != job["identity"]["session_id"]:
        raise ValueError("native observations belong to a different session")
    archive = TleArchiveReader(Path(job["tle_root"]))
    counts, stops, salvage_counts = Counter(), Counter(), Counter()

    def optimize(*args, **kwargs):
        result = v5_armijo_fit.bounded_armijo(*args, **kwargs)
        counts["calls"] += 1
        for key in ("evaluations", "jacobian_refreshes", "rejected_trials"):
            counts[key] += result[key]
        stops[result["stopped"]] += 1
        return result

    salvage = partial(
        v5_tiled_salvage.salvage, conservative_recovery, salvage_counts, DiscardShortlists()
    )
    with ExitStack() as stack:
        for context in (
            row_major_screens(),
            patch.object(v5_stream_recovery, "OrbitRows", ScratchRows),
            patch.object(v5_stream_recovery, "receipt", scratch_size),
            v5_recovery_cache_memory.bounded_scratch_cache(),
            v5_nomination_memory.nomination_memory(),
            v5_signed_context_memory.signed_widths(),
            v5_family_memory.family_widths_context(),
            v5_sparse_discovery.discovery_diagnostics(),
            v5_track_projection.track_projection(),
            v5_stream_recovery.streamed_recovery(Path(output).parent),
            patch.object(conservative_recovery, "salvage", salvage),
            prep_stream_sky.prepared_sky(),
            history_stream_prep.history_cache(),
            ordered_phases(),
            patch.object(position, "bounded_gauss_newton", optimize),
        ):
            stack.enter_context(context)
        projector = stack.enter_context(projected_orbits(library))
        start = perf_counter()
        center = job["screen_center"]
        prepared = engine._prepared_values(
            engine.policy.prepare_native_scan(
                document,
                archive,
                TrackConfig(**read_bound(job["track_config"])["config"]),
                screen_latitude_deg=center[0],
                screen_longitude_deg=center[1],
            )
        )
        result = infer(
            prepared,
            SearchRegion(tuple(job["search_center"])),
            backend,
            {"native_preparation": perf_counter() - start},
            archive,
            job["scan_identities"],
        )
    original.check_scientific_inputs(request)
    if original.ev.source_binding(v5_lean.SOURCE) != request["source"]:
        raise ValueError("frozen source changed during inference")
    result["boundary"] = BOUNDARY
    result["metrics"].update(
        compact_projections=projector.calls,
        position_optimizer=dict(counts),
        optimizer_stops=dict(stops),
        salvage_work=dict(salvage_counts),
    )
    original.write(output, result)


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
