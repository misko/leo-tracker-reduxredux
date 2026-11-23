"""Reuse fixed scan layout preparation across fresh ALGO08v3 likelihoods."""

from collections import Counter
from contextlib import ExitStack, contextmanager
from functools import wraps
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from pickle import dumps
from textwrap import dedent
from time import process_time_ns
from unittest.mock import patch

import numpy as np


POSITION_SOURCE = "c3507e6ecaba0adf6d3677f56d8056afcccbcf90d6a561bca7a42b06b0daef9d"
MARGINAL_SOURCE = "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609"
SCAN_LAYOUT = ("tracks", "curved", "sky", "elements", "previous_sources", "rx_basis",
               "fixed_window_noise", "search_region", "previous_tle", "norads")


def constructor_parts(position):
    """Split the pinned constructor at the observation-mask boundary."""
    original = position.NormalPosition.__init__
    source = dedent(getsource(original))
    header, body = source.split("point_noise=None):\n", 1)
    fixed, current = body.split("    self.keep = ", 1)
    fixed = fixed.replace("super().__init__(", "JointMarginal.__init__(self, ", 1)
    namespace = dict(original.__globals__)
    exec(compile(header + "point_noise=None):\n" + fixed
                 + "\ndef apply_mask(self, keep):\n    self.keep = " + current,
                 position.__file__, "exec"), namespace)
    return namespace["__init__"], namespace["apply_mask"]


def copy_fields(fields):
    """Preserve independent arrays and lists in each fresh problem instance."""
    result = {}
    for name, value in fields.items():
        if type(value) is np.ndarray:
            value = value.copy(order="K")
        elif type(value) is list:
            value = value.copy()
        elif name == "sky":
            value = dict(value, position_km=value["position_km"].copy(),
                         velocity_km_s=value["velocity_km_s"].copy())
        result[name] = value
    return result


class Layouts:
    """Hold only the most recent constructor layout for each calibration arm."""

    def __init__(self, fixed, apply_mask, original, classes, scan_class, counts, *, reuse, audit):
        self.fixed, self.apply_mask, self.original = fixed, apply_mask, original
        self.classes, self.scan_class = classes, scan_class
        self.counts, self.reuse, self.audit = counts, reuse, audit
        self.scan = None
        self.ports = ()
        self.provenance = None
        self.recent = {}
        self.last = None

    def prepare(self, problem, scan, node, sigma, fitted_c, *, reference=None, keep=None,
                point_noise=None):
        if (type(problem) not in self.classes or type(scan) is not self.scan_class
                or type(reference) is not np.ndarray
                or type(fitted_c) is not bool or point_noise is not None):
            self.counts["unexamined_constructions"] += 1
            return self.original(problem, scan, node, sigma, fitted_c, reference=reference,
                                 keep=keep, point_noise=point_noise)
        start = process_time_ns()
        # ScanLikelihood owns these fixed inputs. The frozen solve constructs a
        # new scan for another bank/noise pass and does not edit the arrays in
        # place during the enrolled NormalPosition and PositionNormal fits.
        ports = tuple(getattr(scan, name) for name in SCAN_LAYOUT) + tuple(
            scan.sky[name] for name in ("time_s", "position_km", "velocity_km_s", "phase_sigma_s")
        )
        provenance = (scan.origin_utc_ns, scan.previous_tle_sha256,
                      scan.fixed_window_noise_sha256, vars(scan).get("hardware"))
        if (scan is not self.scan or provenance != self.provenance
                or any(a is not b for a, b in zip(ports, self.ports, strict=True))):
            self.scan, self.ports = scan, ports
            self.provenance = provenance
            self.recent.clear()
            self.last = None
        # The seed state reaches the stock constructor's initial alias probe,
        # even with explicit aliases. Snapshot it along with the ordered rows.
        key = dumps((node["seed"], node["aliases"], sigma), protocol=5)
        previous = self.recent.get(fitted_c)
        matched = previous is not None and previous[0] == key
        self.counts["lookup_cpu_ns"] += process_time_ns() - start
        start = process_time_ns()
        if matched and self.reuse:
            vars(problem).update(copy_fields(previous[1]))
            problem.rows = [row for row in node["seed"]["rows"] if row["active_curvature"]]
            problem.reference = np.asarray(reference)
            self.counts["reused_fixed_constructions"] += 1
            self.counts["reused_fixed_rows"] += len(problem.values)
            self.counts["reuse_cpu_ns"] += process_time_ns() - start
        else:
            self.fixed(problem, scan, node, sigma, fitted_c, reference=reference)
            self.counts["fixed_constructions"] += 1
            self.counts["rebuilt_fixed_rows"] += len(problem.values)
            self.counts["fixed_cpu_ns"] += process_time_ns() - start
            if matched:
                self.counts["eligible_fixed_cpu_ns"] += process_time_ns() - start
            if self.reuse:
                start = process_time_ns()
                state = {k: v for k, v in vars(problem).items() if k not in ("rows", "reference")}
                state = copy_fields(state)
                self.counts["snapshot_cpu_ns"] += process_time_ns() - start
            else:
                state = None
        start = process_time_ns()
        self.apply_mask(problem, keep)
        self.counts["mask_cpu_ns"] += process_time_ns() - start
        self.counts["mask_calls"] += 1
        if matched:
            self.counts["same_arm_layout_matches"] += 1
            state = previous[1]
        changes = ()
        if self.audit:
            changes = reference.tobytes(), problem.keep.tobytes()
            self.counts["active_mask_rows"] += int(problem.keep.sum())
            if matched:
                self.counts["matches_with_phase_change"] += previous[2] != changes[0]
                self.counts["matches_with_mask_change"] += previous[3] != changes[1]
            self.observe(problem, fitted_c)
        self.recent[fitted_c] = key, state, *changes

    def observe(self, problem, fitted_c):
        owners = {row["component"]: (row["candidate_index"], alias, sl.stop - sl.start)
                  for row, alias, sl in zip(problem.rows, problem.alias, problem.slices, strict=True)}
        if self.last is not None:
            old_arm, old_owners = self.last
            same = owners == old_owners
            self.counts["arm_transitions"] += old_arm != fitted_c
            self.counts["owner_or_alias_transitions"] += not same
            if not same:
                self.counts["rows_in_owner_or_alias_transitions"] += len(problem.values)
                self.counts["rows_with_same_owner_and_alias"] += sum(
                    value[2] for track, value in owners.items() if old_owners.get(track) == value
                )
                self.counts["rows_with_same_track"] += sum(
                    value[2] for track, value in owners.items()
                    if track in old_owners and old_owners[track][2] == value[2]
                )
        self.last = fitted_c, owners


@contextmanager
def incremental_layout(*, reuse=True, audit=False):
    """Scope reuse to a single solve and optionally count unchanged likelihood work."""
    from leo.analysis.localization_v3 import marginal, position, retained_position, scan

    for module, expected in ((position, POSITION_SOURCE), (marginal, MARGINAL_SOURCE)):
        if sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Expected the frozen ALGO08v3 constructor: {module.__file__}")
    original = position.NormalPosition.__init__
    counts = Counter()
    layouts = Layouts(*constructor_parts(position), original,
                      (position.NormalPosition, retained_position.PositionNormal),
                      scan.ScanLikelihood, counts, reuse=reuse, audit=audit)

    def initialize(problem, *args, **kwargs):
        return layouts.prepare(problem, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.object(position.NormalPosition, "__init__", initialize))
        if audit:
            from leo.analysis.localization_v4.native_bound import NativeBound

            bound = NativeBound.__call__
            project = marginal._phase_geometry
            last_problem = last_point = last_reference = None

            @wraps(bound)
            def measure(instance, response, design, *args, **kwargs):
                result = bound(instance, response, design, *args, **kwargs)
                updates = int(result["precision_iterations"])
                counts["bound_calls"] += 1
                counts["bound_rows"] += len(response)
                counts["bound_precision_updates"] += updates
                counts["bound_weighted_row_updates"] += len(response) * updates
                return result

            @wraps(project)
            def geometry(problem, point):
                nonlocal last_problem, last_point, last_reference
                reference = np.asarray(problem.reference).tobytes()
                location = np.asarray(point).tobytes()
                same = problem is last_problem
                counts["phase_projections"] += 1
                counts["phase_projection_rows"] += len(problem.flat_times)
                counts["position_moves_same_model"] += same and location != last_point
                counts["position_moves_same_model_rows"] += (
                    len(problem.flat_times) if same and location != last_point else 0
                )
                counts["reference_changes_same_model"] += same and reference != last_reference
                # Keep only one recent model and no likelihood arrays.
                last_problem, last_point, last_reference = problem, location, reference
                return project(problem, point)

            stack.enter_context(patch.object(NativeBound, "__call__", measure))
            stack.enter_context(patch.object(marginal, "_phase_geometry", geometry))
        yield counts


@contextmanager
def install(publication, specification, args, *, reuse=True, audit=False):
    """Bind to the installed publication after its lazy startup, for one solve."""
    if specification.get("curved_design") is not True:
        raise ValueError("Expected installed ALGO08v3 curved likelihood stage")
    wrap = publication._with_curved_design
    counts = {}

    def binding(solve, measure, released_counts):
        original = wrap(solve, measure, released_counts)

        @wraps(original)
        def candidate(*args, **kwargs):
            with incremental_layout(reuse=reuse, audit=audit) as measured:
                result = original(*args, **kwargs)
            counts.update(measured)
            return result

        return candidate

    with patch.object(publication, "_with_curved_design", binding):
        yield counts
