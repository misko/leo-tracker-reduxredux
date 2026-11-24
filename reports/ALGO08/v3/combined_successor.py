"""Compose guarded lean nomination and the exact native standard grid."""

from contextlib import contextmanager
from functools import partial
from inspect import getsource
from hashlib import sha256
from unittest.mock import patch

from nomination_handoff import NominationHandoff, routed_binding
from two_centre_seeds import elapsed, now, two_seeds


class SuccessorHandoff(NominationHandoff):
    def __init__(self, core, screens, exact_rank, audit):
        super().__init__(core, screens, exact_rank, audit)
        self.scout = audit.setdefault("two_centre_rank", {})
        self.original_screen = screens.screen_nodes
        self.speculative = False

    def rank(self, scan):
        from leo.analysis.localization_v3.discovery import signature

        if scan is not self.scan or self.scout:
            return self.exact_rank(scan)
        started = now()
        with two_seeds(self.scout):
            nodes = self.exact_rank(scan)
        signatures = [signature(node) for node in nodes[:3]]
        self.scout.update(paid=elapsed(started), ranked_nodes=len(nodes),
                          distinct_finalists=len(set(signatures)), finalist_signatures=signatures)
        if (self.scout.get("paid_centres") != 2 or self.scout.get("fallback")
                or self.scout["distinct_finalists"] != 3):
            # Re-enter the unmodified producer only after restoring discovery.
            # An unsupported candidate cannot certify a paid prefix.
            self.scout.setdefault("fallback", "insufficient_distinct_ranked_assignments")
            started = now()
            ordinary = super().rank(scan)
            self.scout["ordinary_retry"] = elapsed(started)
            return ordinary
        self.speculative = True
        self.source = self.scan = self.nodes = self.checkpoint = None
        self.counts["speculative_ranks_excluded"] += 1
        return nodes

    def capture(self, scan, nodes, outcomes):
        if self.speculative:
            self.counts["speculative_prefix_sets_excluded"] += 1
            return
        super().capture(scan, nodes, outcomes)

    @contextmanager
    def fallback(self):
        if not self.speculative:
            with super().fallback():
                yield
            return
        self.counts["ordinary_fallbacks"] += 1
        with (patch.object(self.core, "scan_context", self.scan_context),
              patch.object(self.core, "ranked_initial_nodes", self.exact_rank),
              patch.object(self.screens, "screen_nodes", self.original_screen)):
            yield


@contextmanager
def successor_binding(reader, cutoff, audit, original_rank):
    import nomination_handoff

    with (patch.object(nomination_handoff, "NominationHandoff", SuccessorHandoff),
          routed_binding(reader, cutoff, audit, original_rank)):
        yield


@contextmanager
def exact_grid(projection, template_path, audit):
    import grid_phase_state_reuse as phase
    from grid_design_template import Designs, bind_projected_design
    from grid_feature_projection import Native, PHASE_SHA, supported_cpu
    from leo.analysis.localization_v3 import marginal

    if not supported_cpu() or sha256(getsource(marginal._phase_geometry).encode()).hexdigest() != PHASE_SHA:
        audit["fallback"] = "unsupported_native_grid_binding"
        yield
        return
    try:
        native, template = Native(projection), Designs(template_path)
    except (OSError, AttributeError):
        audit["fallback"] = "unavailable_native_grid_library"
        yield
        return

    def bind(sample, geometry, prepared):
        operation, features = bind_projected_design(native, template, sample, geometry, prepared)

        def measure(*args, **kwargs):
            start = now()
            result = operation(*args, **kwargs)
            audit.update(clock=elapsed(start), complete=result["complete"], points=result["evaluated_points"])
            return result

        return measure, features

    original = phase.cached_predictive_grid
    try:
        with patch.object(phase, "cached_predictive_grid", partial(original, bind=bind)):
            yield
    finally:
        audit.update(projection=dict(native.counts), assembly=dict(template.counts))
