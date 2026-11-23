"""Shadow repeated-row sufficient statistics at one original dense grid objective."""

import argparse
import gzip
import json
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from aperture_trial import write
from dense_full_short_crossover import HERE, file_sha
from dense_geographic_trial import host
from grid_cross_arm_posterior import PINNED_BOUND, PINNED_HANDOFF, same_bits
from grid_neighbor_gamma_trial import reconstruct


PINNED_C = "40888d6143f385c2146e5e2cb28ea99a96b2f1bb791fab4c22b5afaaa2b3a23b"
PINNED_MARGINAL = "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609"
PINNED_POSITION = "c3507e6ecaba0adf6d3677f56d8056afcccbcf90d6a561bca7a42b06b0daef9d"
POINT = (0., 0.)
ARM = "c0"
STATIC_COLUMNS = (0, 1, 2, 3, 5, 7)


def common_rows(design):
    """Group equal normalized binary64 operands including their zero signs."""
    rows = {}
    for i, row in enumerate(design):
        rows.setdefault(row.tobytes(), []).append(i)
    return rows.values()


def group_statistics(design, values, gram, rhs):
    """Build real-valued equivalent statistics with a distinct-row exact fallback."""
    members = common_rows(design)
    if len(members) == len(values):
        return gram, rhs, len(members)
    small_gram = np.zeros_like(gram)
    small_rhs = np.zeros_like(rhs)
    for indices in members:
        row = design[indices[0]]
        small_gram += len(indices) * np.outer(row, row)
        small_rhs += row * sum(values[i] for i in indices)
    return small_gram, small_rhs, len(members)


def original_statistics(design, values):
    """Scalar-order group accumulation with the installed ascending active indices."""
    width = design.shape[1]
    gram, rhs = np.zeros((width, width)), np.zeros(width)
    for row, value in zip(design, values, strict=True):
        gram += np.outer(row, row)
        rhs += row * value
    return gram, rhs


def audit(data, prefix=None):
    y, u, sigma, groups = (data[key] for key in ("y", "u", "s", "g"))
    profiles = []
    for group in np.unique(groups):
        mask = groups == group
        matrix = u[mask]
        scale = sigma[mask]
        design = matrix[:, np.any(matrix != 0., axis=0)] / scale[:, None]
        response = y[mask] / scale
        gram, rhs = original_statistics(design, response)
        candidate_gram, candidate_rhs, unique = group_statistics(design, response, gram, rhs)
        profiles.append(dict(group=int(group), rows=len(design), unique=unique, active=design.shape[1],
                             prefix_unique=None if prefix is None else len(common_rows(prefix[mask] / scale[:, None])),
                             gram_linf=float(np.max(np.abs(gram-candidate_gram), initial=0.)),
                             rhs_linf=float(np.max(np.abs(rhs-candidate_rhs), initial=0.)),
                             bitwise_exact=bool(same_bits(gram, candidate_gram).all() and same_bits(rhs, candidate_rhs).all())))
    return dict(rows=len(y), width=u.shape[1], groups=len(profiles),
                distinct=sum(row["unique"] for row in profiles),
                distinct_static_prefix=None if prefix is None else sum(row["prefix_unique"] for row in profiles),
                products={name: dict(original=sum(row["rows"]*row["active"]**power for row in profiles),
                                     removable=sum((row["rows"]-row["unique"])*row["active"]**power for row in profiles))
                          for name, power in (("gram", 2), ("rhs", 1))},
                bitwise_exact=all(row["bitwise_exact"] for row in profiles),
                gram_linf=max(row["gram_linf"] for row in profiles), rhs_linf=max(row["rhs_linf"] for row in profiles),
                original_residual_rows=len(y), per_group=profiles)


class OnePosterior:
    def __init__(self, grid):
        self.grid = grid
        self.context = None
        self.record = None

    def sample(self, score, endpoints, **_kwargs):
        from leo.analysis.localization_v3 import marginal, position
        from leo.analysis.localization_v4 import native_bound
        from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

        original_validate, original_run = native_bound._VALIDATE, handoff.Capture.run
        pins = {Path(native_bound.__file__): PINNED_BOUND, Path(handoff.__file__): PINNED_HANDOFF,
                Path(native_bound.__file__).with_suffix(".c"): PINNED_C,
                Path(marginal.__file__): PINNED_MARGINAL, Path(position.__file__): PINNED_POSITION}
        if any(file_sha(path) != digest for path, digest in pins.items()):
            raise ValueError("Installed posterior operands or assembly source changed")
        if {arm: list(point) for arm, point in endpoints.items()} != self.grid["endpoints"]:
            raise ValueError("The selected evidence does not reproduce the archived final coordinates")
        data, exports = [], []

        def validate(*args, **kwargs):
            value = original_validate(*args, **kwargs)
            data.append(value)
            return value

        def run(capture, owner, operation, args):
            start = process_time_ns()
            status = original_run(capture, owner, operation, args)
            exports.append((status, capture.exported.value, process_time_ns()-start))
            return status

        expected, = (row["scores"][ARM] for row in self.grid["points"] if (row["east_km"], row["north_km"]) == POINT)
        with patch.object(native_bound, "_VALIDATE", validate), patch.object(handoff.Capture, "run", run):
            observed = score(ARM, POINT)
        source, = data
        status, exported, native_ns = exports[0]
        if observed != expected or len(exports) != 1 or status != 0 or exported != 1:
            raise ValueError("Expected one checked posterior and the exact archived objective")
        problem, _ = self.context["problems"][ARM]
        prefix = problem.hardware[problem.keep][:, STATIC_COLUMNS]
        _, groups = np.unique(problem.noise_groups[problem.keep], return_inverse=True)
        operands = dict(hardware=bool(same_bits(prefix, source["u"][:, STATIC_COLUMNS]).all()),
                        noise=bool(same_bits(problem.point_noise[problem.keep], source["s"]).all()),
                        groups=bool(np.array_equal(groups, source["g"])))
        start = process_time_ns()
        rep = audit(source, prefix=prefix if all(operands.values()) else None)
        self.record = dict(point=POINT, arm=ARM, objective=observed, archived_objective=expected, exported=exported,
                           native_cpu_ns=native_ns, audit_cpu_ns=process_time_ns()-start,
                           static_columns=STATIC_COLUMNS, static_operands_match=operands,
                           installed_sha256={p.name: pin for p, pin in pins.items()}, **rep)
        return dict(points=[], complete=False, evaluated_points=1)


def budget():
    latest = HERE / "measurements/regional-dense-pair.json"
    panel = HERE / "measurements/regional-dense-budget.json"
    grid = HERE / "measurements/grid-cross-arm-posterior.json.gz"
    paired = json.loads(latest.read_bytes())
    caps = json.loads(panel.read_bytes())
    posterior = json.loads(gzip.decompress(grid.read_bytes()))
    return archived_budget(paired, caps, posterior) | dict(sha256={p.name: file_sha(p) for p in (latest, panel, grid)})


def archived_budget(paired, caps, posterior):
    current = paired["runs"]["native"]
    full = current["solve_cpu_s"]
    if full != caps["solve_cpu_s"]:
        raise ValueError("The roster model does not use this dense solve")
    need = full - caps["panels"]["4"]["scenarios"]["fastest_prefix"]["dense_solve_budget_s"]
    native = posterior["ceiling"]["native"]["both_arms_cpu_s"]
    cold_and_evidence = current["cold_cpu_s"] + current["grid_cpu_s"]
    return dict(current_full_solve_cpu_s=full, needed_saving_cpu_s=need, observed_grid_native_cpu_s=native,
                hypothetical_shortfall_with_free_native_grid_s=need-native,
                current_cold_and_grid_evidence_cpu_s=cold_and_evidence,
                hypothetical_shortfall_with_free_cold_and_evidence_s=need-cold_and_evidence)


def run(output):
    machine = host()
    output.mkdir(exist_ok=False)
    observer = []

    def make(grid):
        captured = OnePosterior(grid)
        observer.append(captured)
        return captured

    reconstruction, _ = reconstruct(make)
    observed, = observer
    code = (Path(__file__), HERE / "grid_neighbor_gamma_trial.py", HERE / "dense-row-repetition-protocol.md")
    write(output / "result.json", dict(**reconstruction, host=machine, posterior=observed.record, budget=budget(),
                                      source_sha256={path.name: file_sha(path) for path in code}))
    if not all(reconstruction["checks"].values()):
        raise ValueError(f"The selected context differs from the dense control: {reconstruction['checks']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
