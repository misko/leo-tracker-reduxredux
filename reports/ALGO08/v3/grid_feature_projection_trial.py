"""Price exact projection and design scopes in the authenticated dense map."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
from inspect import getclosurevars
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from aperture_trial import write
from dense_full_short_crossover import file_sha
from dense_geographic_trial import elapsed, host, now
from grid_feature_projection import Design, Native, build, exact
from grid_neighbor_gamma import clear_grid_cache
from grid_neighbor_gamma_trial import reconstruct
from grid_phase_state_reuse import checked_geometry, identical, prepared_features, sample_with_cached_features


class Packing:
    """Route just the handoff's final stack through the census timer."""

    def __init__(self, module, measure):
        self.module = module
        self.column_stack = measure(module.column_stack)

    def __getattr__(self, name):
        return getattr(self.module, name)


class Census:
    def __init__(self, archive, native=None, *, edge_sample=False):
        self.archive = archive
        self.context = None
        self.native = native
        self.edge_sample = edge_sample
        self.arm = None
        self.view = None
        self.work = defaultdict(Counter)
        self.rows = []
        self.output = None

    def exercise_edges(self, score, endpoints, **_kwargs):
        candidates = self.archive["points"]
        chosen = [candidates[2], candidates[-1]]
        chosen += [min(candidates, key=lambda r: east*r["east_km"] + north*r["north_km"])
                   for east in (-1, 1) for north in (-1, 1)]
        rows = []
        for row in chosen:
            point = row["east_km"], row["north_km"]
            results = {}
            for arm in endpoints:
                clear_grid_cache(self.context["problems"][arm][0])
                results[arm] = score(arm, point)
            rows.append(dict(east_km=point[0], north_km=point[1], scores=results, failures={}))
        return dict(points=rows, complete=True, evaluated_points=len(rows))

    def candidate(self, stack, calculate, stock_phase, original, history, direct):
        layout = Design(direct)
        assembly = calculate["_assemble"]
        select_globals = history.make_problem.__globals__
        select = select_globals["_select"]
        phase = self.native.phase(stock_phase, verify=self.edge_sample)

        def design(problem, frequency, derivative, modes, scales, geometry_only):
            if not geometry_only or problem.variant != "radio_noise":
                layout.counts["design_fallback"] += 1
                return assembly(problem, frequency, derivative, modes, scales, geometry_only)
            value = layout.assemble(problem, derivative, modes, scales)
            if self.edge_sample and not exact(value, assembly(problem, frequency, derivative, modes, scales, geometry_only)):
                raise ValueError("Expected bit-identical curved features")
            return value

        def select_rows(features, scale, keep):
            value = self.native.selected_design(features, scale, keep, select)
            if self.edge_sample and not exact(value, select(features, scale, keep)):
                raise ValueError("Expected bit-identical selected rows")
            return value

        curved, linear = self.phase("curved", phase), self.phase("predictive", phase)
        released_linear = prepared_features(original, linear)
        check_linear = prepared_features(original, stock_phase) if self.edge_sample else None
        timed_design = self.observe(lambda: (self.arm, "curved"), "candidate_design", design)
        timed_selection = self.observe(lambda: (self.arm, "curved"), "candidate_selection", select_rows)
        stack.enter_context(patch.dict(calculate, _phase_geometry=curved, _assemble=timed_design))
        stack.enter_context(patch.dict(select_globals, _select=timed_selection))

        def predictive(view, position, altitude):
            if view.variant != "radio_noise" or altitude != 0.:
                return released_linear(view, position, altitude)
            frequency, elevation, derivative, modes = linear(view, np.asarray(position)[:2])
            intercept = frequency - derivative * view.reference[view.flat_labels]
            scales = np.ones(3)
            result = dict(features=layout.assemble(view, derivative, modes, scales), elevation=elevation,
                          scales=scales, frequency=frequency, intercept=intercept, derivative=derivative)
            if check_linear is not None:
                expected = check_linear(view, position, altitude)
                if not identical(result, expected):
                    raise ValueError("Expected bit-identical predictive features")
            return result

        return predictive, layout.counts

    def observe(self, bucket, name, operation):
        def measured(*args, **kwargs):
            key = bucket()
            if None in key:
                return operation(*args, **kwargs)
            work = self.work[key]
            start = process_time_ns()
            result = operation(*args, **kwargs)
            work[name + "_ns"] += process_time_ns() - start
            work[name + "_calls"] += 1
            return result

        return measured

    def phase(self, view, operation):
        phase = self.observe(self.group, "phase", operation)

        def measured(*args, **kwargs):
            self.view = view
            try:
                return phase(*args, **kwargs)
            finally:
                self.view = None

        return measured

    def group(self):
        return self.arm, self.view

    def point(self, score):
        def measured(arm, position):
            self.arm = arm
            try:
                return score(arm, position)
            finally:
                self.arm = None

        return measured

    def sample(self, score, endpoints, **kwargs):
        from leo.analysis.localization_v3 import history_position, marginal
        from leo.analysis.position_grid import sample_position_grid
        from leo.analysis.research import prepared_phase_geometry as geometry
        from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff, algo08_curved_design

        event, original, _, _ = checked_geometry()
        calculate = marginal.JointMarginal.calculate.__globals__
        assembly = getclosurevars(calculate["_assemble"]).nonlocals["counts"]
        previous = assembly.copy()
        stock_phase = calculate["_phase_geometry"]
        if stock_phase is not marginal._phase_geometry or kwargs.get("map_batches") is not None:
            raise ValueError("Expected the current single-core curved and predictive stage")
        counters = Counter()
        with ExitStack() as stack:
            for module, name, key in (
                (geometry, "phase_frequency_from_states", "nominal"),
                (geometry, "frequency_modes_from_states", "physical_modes"),
                (marginal, "phase_frequency_from_states", "offset_projection"),
                (geometry, "paired_phase_states", "interpolate"),
                (marginal, "paired_phase_states", "interpolate"),
            ):
                stack.enter_context(patch.object(module, name, self.observe(self.group, key, getattr(module, name))))
            stack.enter_context(patch.object(
                handoff.Capture, "run", self.observe(lambda: (self.arm, "curved"), "checked_export", handoff.Capture.run),
            ))
            stack.enter_context(patch.object(
                handoff, "np", Packing(handoff.np, lambda operation: self.observe(
                    lambda: (self.arm, "predictive"), "pack", operation)),
            ))
            layout = {}
            if self.native is None:
                stack.enter_context(patch.dict(calculate, _phase_geometry=self.phase("curved", stock_phase)))
                predictive = prepared_features(original, self.phase("predictive", stock_phase))
            else:
                predictive, layout = self.candidate(
                    stack, calculate, stock_phase, original, history_position, algo08_curved_design.direct_features,
                )
            grid = sample_with_cached_features(
                self.exercise_edges if self.edge_sample else sample_position_grid, event, original,
                self.observe(lambda: (self.arm, "predictive"), "geometry", predictive), counters,
            )
            start = now()
            result = grid(self.point(score), endpoints, **kwargs)
            clocks = elapsed(start)
        self.rows = result["points"]
        self.output = dict(clocks=clocks, complete=result["complete"], prepared=dict(counters),
                           assembly=dict(assembly - previous), template=dict(layout),
                           native={} if self.native is None else dict(self.native.counts))
        return result

    def report(self):
        stage = self.output
        if stage is None:
            raise ValueError("The reconstructed solve had no map")
        stage["arms"] = {}
        by_view = dict(curved=Counter(), predictive=Counter())
        for (arm, view), values in sorted(self.work.items()):
            counters = values.copy()
            counters["phase_other_ns"] = values["phase_ns"] - sum(
                values[name + "_ns"] for name in ("nominal", "offset_projection", "physical_modes", "interpolate")
            )
            if view == "predictive":
                counters["geometry_design_ns"] = values["geometry_ns"] - values["phase_ns"]
            stage["arms"].setdefault(arm, {})[view] = dict(counters)
            by_view[view].update(counters)
        assembly = stage["assembly"]
        stage["disjoint_ns"] = {
            name: sum(view[name + "_ns"] for view in by_view.values())
            for name in ("nominal", "offset_projection", "physical_modes", "phase_other")
        }
        stage["disjoint_ns"].update(
            curved_design=assembly.get("direct_assembly_ns", 0) + assembly.get("released_assembly_ns", 0)
            if self.native is None else by_view["curved"]["candidate_design_ns"],
            curved_selection=sum(assembly.get(name + "_selection_ns", 0) for name in ("history", "normal"))
            if self.native is None else by_view["curved"]["candidate_selection_ns"],
            predictive_design=by_view["predictive"]["geometry_design_ns"],
            predictive_packing=by_view["predictive"]["pack_ns"],
        )
        stage["disjoint_scope_ns"] = sum(stage["disjoint_ns"].values())
        return stage

    def scores_exact(self):
        if not self.edge_sample:
            return self.rows == self.archive["points"]
        expected = {(row["east_km"], row["north_km"]): row for row in self.archive["points"]}
        return all(row == expected[row["east_km"], row["north_km"]] for row in self.rows)


def run(output, candidate, edge_sample):
    machine = host()
    observers = []
    native = None
    if candidate:
        library = output.with_suffix(".so")
        build(library)
        native = Native(library)

    def observer(grid):
        audit = Census(grid, native, edge_sample=edge_sample)
        observers.append(audit)
        return audit

    reconstruction, _ = reconstruct(observer)
    audit, = observers
    timing = audit.report()
    checks = reconstruction["checks"]
    points, fresh = (6, 6) if edge_sample else (179, 178)
    checks.update(
        points=timing["complete"] and len(audit.rows) == points and audit.scores_exact(),
        prepared=timing["prepared"] == {"grids": 1, "prepared_views": 2, "prepared_calls": 2 * fresh},
        work=all(
            arms["curved"]["phase_calls"] == arms["curved"]["checked_export_calls"] == fresh
            and arms["predictive"]["phase_calls"] == arms["predictive"]["pack_calls"] == fresh
            for arms in timing["arms"].values()
        ),
    )
    if native is not None:
        checks["candidate"] = (native.counts["exact_projection_checks"] == (4 * fresh if edge_sample else 4)
                               and native.counts["native_selection"] == 2 * fresh
                               and native.counts["projection_fallback"] == native.counts["selection_fallback"] == 0
                               and timing["template"] == {"design_views": 4, "template_design": 4 * fresh})
    write(output, dict(**reconstruction, machine=machine, timing=timing, points=audit.rows,
                       source_sha256=file_sha(Path(__file__))))
    if not all(checks.values()):
        raise ValueError(f"The measured exact grid did not match the saved replay: {checks}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--edge-sample", action="store_true")
    args = parser.parse_args()
    run(args.output, args.candidate, args.edge_sample)
