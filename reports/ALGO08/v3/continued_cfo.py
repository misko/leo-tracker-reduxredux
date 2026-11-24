"""Pay fixed-epoch CFO remeasurement only on causal continuation positives."""

from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from held_cycle_refined import FACTOR_FIELDS, FrequencyChanges, select_refined


def lane_key(probe):
    return probe["visit_index"], probe["receiver_id"]


class ContinuedChanges(FrequencyChanges):
    """Bind original detector order, continuation decisions, and only paid amendments."""

    def __init__(self):
        super().__init__()
        from tools.pipeline_eval.variants import carrier_continuation
        import empty_bootstrap as staged

        pin = staged.EXTRA_SOURCES[staged.CONTINUATION]
        staged.checked(Path(carrier_continuation.__file__), pin)
        self.history = carrier_continuation.Continuation()
        self.lanes = []
        self.paid = []

    def consider(self, probe, short):
        if len(probe["candidates"]) > 1:
            raise ValueError("The original mixed receiver must emit one selected row per lane")
        _, keep, _ = self.history.select(probe)
        key = lane_key(probe)
        self.lanes.append((key, keep))
        if short and keep is not None:
            self.paid.append(key)
            return True
        return False

    @contextmanager
    def capture(self, policy):
        with super().capture(policy), patch.object(policy, "continued_changes", self, create=True):
            yield

    def bind_attempts(self, document):
        from anchor_exposure import enroll

        rows = document["source"]["probes"]
        tracked = tuple(zip(rows, self.lanes, enroll(document), strict=True))
        if (self.attempted != len(self.paid) or len(set(self.paid)) != len(self.paid)
                or any(lane_key(row) != key for row, (key, _), _ in tracked)):
            raise ValueError("The signed chronology differs from the original continuation decisions")
        paid_rows = [row for row, (_, keep), event in tracked if keep is not None and event[4] == "short"]
        if [lane_key(row) for row in paid_rows] != self.paid:
            raise ValueError("The observed refinement order differs from the paid short lanes")
        for n, (before, after) in self.by_attempt.items():
            row = paid_rows[n]
            (factor,) = row["candidates"]
            if tuple(factor[key] for key in FACTOR_FIELDS) != after:
                raise ValueError("Refinement changed a different signed lane")
            self.changed[lane_key(row)] = before, after[3]

    def projected_history(self, probes):
        rows = []
        for row, (key, keep) in zip(probes, self.lanes, strict=True):
            if lane_key(row) != key:
                raise ValueError("Continuation decisions belong to a different signed chronology")
            rows.append(dict(row, candidates=[] if keep is None else [row["candidates"][keep]]))
        return rows


def recipe(original):
    import empty_bootstrap as staged

    return dict(original, continued_cfo=dict(
        wrapper_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        continuation_sha256=staged.EXTRA_SOURCES[staged.CONTINUATION],
        admission="original short-lane factor retained by chronological carrier continuation",
        chronology="advance every original pre-refinement probe, including full anchors and empty lanes",
        finish="frozen held full-anchor cycle selector on original factors"))


def select_paid(native, detector_recipe, changes, session, inventory, receipt_file):
    import anchor_holds
    from anchor_cycle_route import select_route  # load the unchanged held-mask replay before the scoped override

    if select_route.__globals__["history_rows"] is not anchor_holds.history_rows:
        raise ValueError("The held-cycle score must use the original training replay")
    with patch.object(anchor_holds, "history_rows", changes.projected_history):
        return select_refined(native, detector_recipe, changes, session, inventory, receipt_file)


def raw_entry(library, argv, *, guarded_pack=None):
    """Run the same continuation gate with the exact or guarded native receiver."""
    import numpy as np
    import held_cycle_refined as selection
    import short_cfo_raw as exact

    if (library is None) == (guarded_pack is None):
        raise ValueError("Choose exactly one native CFO library or verified guarded pack")
    mixed = exact.mixed.MixedApertureDetector

    @contextmanager
    def detector(self, method, edge, *, binary=None, pilot=None):
        full = None
        with mixed.detector(self, method, edge, binary=binary, pilot=pilot) as receive, ExitStack() as close:
            def refined(window):
                nonlocal full
                old = self.visits["short_primary"]
                probes = receive(window)
                short = self.visits["short_primary"] != old
                paid = [self.policy.continued_changes.consider(row, short) for row in probes]
                if not any(paid):
                    return probes
                target, scope = window.target, window.acquisition
                center = target["rf_center_hz"]-target["lnb_lo_hz"]-scope["actual_if_center_hz"]
                for n, (probe, allowed) in enumerate(zip(probes, paid, strict=True)):
                    if not allowed:
                        continue
                    cpu, wall = process_time_ns(), perf_counter_ns()
                    if full is None:
                        asset = np.frombuffer(exact.mixed.verified(pilot, exact.mixed.PILOT_SHA[edge]), dtype="<f4")
                        full = exact.mixed.NativePath(binary, asset, "full")
                        close.callback(full.close)
                    probes[n], reason, changed = exact.refined_probe(probe, window.samples, full, self.policy, center)
                    self.lanes.setdefault((edge, probe["receiver_id"]), Counter()).update(
                        {"attempted": 1, "changed": int(changed), reason: 1})
                    self.cpu_ns += process_time_ns()-cpu
                    self.wall_ns += perf_counter_ns()-wall
                return probes

            yield refined

    args = [*argv, "--select-before-cfo"]
    with (patch.object(exact.RefinedShortDetector, "detector", detector),
          patch.object(selection, "FrequencyChanges", ContinuedChanges),
          patch.object(selection, "select_refined", select_paid)):
        if guarded_pack is None:
            before = exact.recipe
            with patch.object(exact, "recipe", lambda *args: recipe(before(*args))):
                return exact.run_cli(library, args)

        import anchored_cfo_raw as guarded

        before = guarded.recipe
        with patch.object(guarded, "recipe", lambda *args: recipe(before(*args))):
            return guarded.run_cli(guarded_pack, args)


if __name__ == "__main__":
    import argparse

    cli = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    native = cli.add_mutually_exclusive_group(required=True)
    native.add_argument("--cfo-refinement-library", type=Path)
    native.add_argument("--anchored-cfo-pack", type=Path)
    args, inherited = cli.parse_known_args()
    raw_entry(args.cfo_refinement_library, inherited, guarded_pack=args.anchored_cfo_pack)
