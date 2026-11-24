"""Verify unchanged signed readouts and summarize already-paid duplicate work."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from survivor_sensitivity_score import PAIR, read, receipt


HERE = Path(__file__).resolve().parent
TRIAL = Path("/dev/shm/leo-v3-signed-state-ceiling-01")
ARCHIVED_GRID_SHA = "b7a496144bfba021c55aa9b7c56bd865360b738d08f7e7ebd5406327d690eb75"
ARMS = ("c0", "fitted_c")
PROJECTIONS = ("curved_derivative_interpolation", "curved_nominal_and_modes_interpolation",
               "predictive_frequency_modes", "predictive_phase_frequency")
FRAMES = ("receiver_ecef", "receiver_enu")
REPEATS = ("across_arms", "later_refresh", "same_refresh")


def duplicate_cpu(census, names, scopes=REPEATS):
    return sum(census[name].get(scope, {}).get("cpu_ns", 0) for name in names for scope in scopes)


def score(root=TRIAL):
    seal = read(root / "feature-seal.json")
    sources = read(root / "binding.json")
    reference = read(HERE / "measurements/grid-feature-projection.json.gz", ARCHIVED_GRID_SHA)
    grid = reference["stock-map"]["receipt"]["timing"]["arms"]
    prior_ns = sum(grid[arm]["curved"]["phase_ns"] for arm in ARMS)
    prior_count = sum(grid[arm]["curved"]["phase_calls"] for arm in ARMS)
    results = {}
    for case in ("0008", "0402"):
        port = read(root / case / "probe.json", seal[case])
        clocks = read(root / f"{case}-clock.json")
        full = receipt(*PAIR[case][2:])
        detail = full["route_details"]
        if (port["case"] != case or port["waveform_calls"] != 0 or port["handoff"][0] != 1 or clocks["exit_code"]
                or port["readout"] != detail["signed"]["finish"] or not port["original_gate"]
                or any(port["roster"] != sorted(full["selected_rows"][arm]) for arm in ARMS)
                or len(port["roster"]) != port["row_count"] or full["receipt"]["decision"] != "complete"):
            raise ValueError("Observed pair does not reproduce the authenticated original fit")
        views = port["phase_views"]
        if [(row["arm"], row["epoch"]) for row in views] != [(arm, epoch) for arm in ARMS for epoch in range(5)]:
            raise ValueError("The observed solver did not follow the original paired five-refresh route")
        invariant = {key: views[0][key] for key in ("members", "aliases", "keep", "phase_width")}
        if any({key: row[key] for key in invariant} != invariant for row in views):
            raise ValueError("Original roster, alias or nuisance width changed between refreshes")
        census = port["census"]
        common = port["common_operands"]
        curved = census.get("curved_phase_projection")
        if curved is None:
            representation = "nominal/modes interpolation keys and exact initial coordinate peers"
            # Only one pair of views reused the actual curved interpolation inputs.
            # The stock map provides a scale estimate for the remaining curved geometry.
            nominal = census["curved_nominal_and_modes_interpolation"]
            if len({tuple(row["reference"][1]) + (row["reference"][-1],) for row in views}) != 9 or any(
                nominal.get(scope, {}).get("calls", 0) != int(scope == "across_arms") for scope in REPEATS
            ):
                raise ValueError("Cannot restrict shared curved geometry to the common initial references")
            estimated_projection = round(prior_ns / prior_count * common["common_coordinate_count"])
        else:
            representation = "direct installed curved geometry timing"
            estimated_projection = None
        covered = tuple(name for name in (*PROJECTIONS, *FRAMES, "paid_full_objective", "curved_posterior",
                                         "predictive_covariance", "curved_phase_projection") if name in census)
        results[case] = dict(
            exact_original_readouts=True, exact_owner_role_count=port["row_count"], pin=seal[case],
            archived_publication_sha256=PAIR[case][-1], request_sha256=port["request_sha256"],
            observed_pair_cpu_ns=port["clocks_cpu_ns"], archived_signed_refit=detail["signed_refit_clocks"],
            phase_views=[dict(arm=row["arm"], epoch=row["epoch"], phase_reference=row["reference"]) for row in views],
            common_layout=dict(nominal_curved_points=invariant["keep"][1][0], tracks=len(invariant["members"]),
                               phase_width=invariant["phase_width"], keep=invariant["keep"]),
            handoff=port["handoff"], stages=census, cumulative_clock=clocks,
            diagnostic_validation_cpu_ns=port["diagnostic_validation_cpu_ns"], common_operands=common,
            measured_duplicate_cpu_ns_with_overlaps=duplicate_cpu(census, covered),
            measured_duplicate_cpu_ns_cross_or_later_with_overlaps=duplicate_cpu(census, covered, REPEATS[:2]),
            curved_projection_evidence=representation,
            projected_missing_curved_cpu_ns_from_grid_mean=estimated_projection,
            diagnostic_key_cpu_ns=sum(row["key_cpu_ns"] + row["extra_common_key_cpu_ns"] for row in census.values()),
            exact_readout=port["readout"])
    return dict(protocol_sha256=sources["source_sha256"]["signed-state-ceiling-protocol.md"],
                source=sources, results=results, measured_solver_replays=2, new_publications=0, waveform_reads=0,
                separate_projection_reference=dict(sha256=ARCHIVED_GRID_SHA, curved_cpu_ns=prior_ns,
                                                   curved_calls=prior_count))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=TRIAL)
    args = parser.parse_args()
    print(json.dumps(score(args.root), indent=2, sort_keys=True, allow_nan=False))
