"""Reconcile frozen raw successor rank and solve counters without another solver."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


CASES = ("DS30-0274", "DS30-0019", "DS30-0178")
ARMS = ("c0", "fitted_c")
CORNERS = 4
FLOAT_BYTES = 8
PLANES = 3


def exactly(dividend, divisor):
    quotient, remainder = divmod(dividend, divisor)
    if remainder:
        raise ValueError("Observed work is not divisible at the reviewed scope")
    return quotient


def rank_scope(rank, seed, blocks, graph):
    rows = seed["catalogue_rows"]
    curves = seed["original_curved"]
    centres = seed["paid_centres"]
    inputs = rank["inputs"]
    centre_uses = 2*centres
    association_calls = centres + centre_uses + CORNERS
    nominal_views = 1+CORNERS
    slots = exactly(inputs["centre_projection_bytes"], FLOAT_BYTES*PLANES)
    all_epochs = exactly(slots, rows)
    curved_points = exactly(inputs["centre_track_cells_reused"], centre_uses*rows)
    if (centres != 2 or "ordinary_retry" in seed
            or inputs["centre_projections_reused"] != centre_uses
            or inputs["nominal_projections"] != nominal_views or inputs["other_projections"] != CORNERS
            or inputs["centre_track_terms_reused"] != centre_uses*curves
            or inputs["geometry_track_terms_built"] != nominal_views*curves
            or inputs["fused_passes"] != nominal_views+centre_uses
            or inputs["nominal_projection_cells"] != nominal_views*slots
            or (blocks["calls"], blocks["compact_calls"], blocks["index_builds"])
            != (association_calls*curves, association_calls*curves, nominal_views*curves)
            or blocks["original_rows"] != blocks["calls"]*rows
            or blocks["padded_cells"] != association_calls*rows*curved_points
            or blocks["rows_saved"]+blocks["rows_retained"] != blocks["original_rows"]):
        raise ValueError("Rank followed a different branch or allocation/storage path")
    tracked = inputs["peak_centre_track_bytes"]
    # Two double matrices, three double per-orbit terms and one boolean mask.
    if tracked != 2*FLOAT_BYTES*curved_points*rows+(3*FLOAT_BYTES+1)*rows*curves:
        raise ValueError("The retained centre terms are not the complete reviewed layout")
    if not 0 < curves <= graph["tracks"] or not 0 < curved_points <= graph["assigned"]:
        raise ValueError("The original Graph count cannot bound discarded epochs")
    axis_bound = min(all_epochs, graph["assigned"]-curved_points)
    return dict(catalogue_rows=rows, curved_tracks=curves, graph_tracks=graph["tracks"],
                graph_points=graph["assigned"], curved_points=curved_points,
                projection_axis_epochs=all_epochs, rank_only_omittable_epochs_upper_bound=axis_bound,
                possible_bytes_removed_from_one_projection_upper_bound=FLOAT_BYTES*PLANES*rows*axis_bound,
                centre_projection_bytes=inputs["centre_projection_bytes"], centre_terms_peak_bytes=tracked,
                concurrent_centre_payload_bytes=inputs["centre_projection_bytes"]+tracked,
                generations=dict(unique_nominal_views=nominal_views, centres=centres, corners=CORNERS,
                                 unique_associations=association_calls, same_state_explore_returns_reused=centre_uses+CORNERS),
                block=blocks, cumulative_padded_matrix_bytes=blocks["padded_cells"]*FLOAT_BYTES,
                rank_cpu_ns=rank["cpu_ns"], fused_statistics_cpu_ns=inputs["statistics_cpu_ns"],
                other_inclusive_rank_cpu_ns=rank["cpu_ns"]-inputs["statistics_cpu_ns"])


def partition(solve, rank, preparation, attempt, grid):
    solve_ns = int(round(solve["cpu_s"]*1e9))
    prep_cpu = preparation["cpu_ns"]
    cold_cpu = int(round(attempt["cold_clocks"]["cpu_s"]*1e9))
    envelope = int(round(attempt["candidate_pre_evidence_clocks"]["cpu_s"]*1e9))
    signed_cpu = int(round(attempt["signed_total_clocks"]["cpu_s"]*1e9))
    evidence_cpu = int(round(attempt["standard_evidence_clocks"]["cpu_s"]*1e9))
    grid_cpu = grid["clock"]["cpu_ns"]
    guard_cpu = int(round(attempt["exterior_clocks"]["cpu_s"]*1e9))
    parts = dict(preparation=prep_cpu, rank=rank, cold_after_rank=cold_cpu-rank,
                 proposal_after_cold=envelope-cold_cpu, signed_update=signed_cpu, terminal_guard=guard_cpu, grid=grid_cpu,
                 evidence_outside_grid=evidence_cpu-grid_cpu,
                 remaining_solve=solve_ns-prep_cpu-envelope-signed_cpu-evidence_cpu-guard_cpu)
    if min(parts.values()) < 0 or sum(parts.values()) != solve_ns:
        raise ValueError("The clock envelopes cannot be partitioned at this observed boundary")
    return dict(solve_cpu_ns=solve_ns, disjoint_cpu_ns=parts)


def load(path):
    body = path.read_bytes()
    return json.loads(body), sha256(body).hexdigest()


def summarize(attempt_root):
    publication = attempt_root/"publication"
    result, result_sha = load(attempt_root/"result.json")
    witness, witness_sha = load(publication/"exact-named-raw-witness.json")
    acquisition, acquisition_sha = load(publication/"legacy-original-acquisition.json")
    marker, marker_sha = load(publication/"algo08v3-successor-release.json")
    detail = witness["evidence"]["detail"]
    ports = witness["ports"]
    risk = ports["history_risk"]
    rank, = ports["rank"]
    attempt, = risk["lean_attempts"]
    solve, = witness["timing"]["solve"]
    prep, = ports["history"]["prepare"]
    grid = acquisition["acceleration"]["solver"]["grid"]
    if (result["algorithm"] != "successor" or result["outcome"] != "complete" or result["generation"] != 1
            or result["process"]["exit_code"] != 0 or risk["choice"]["route"] != "lean"
            or result["native_sha256"] != detail["input_sha256"]
            or result["evidence"]["receipt"]["terminal_sha256"] != detail["terminal_sha256"]
            or marker["terminal_sha256"] != detail["terminal_sha256"]
            or acquisition["finished_raw_authority"] != result["raw_identity"]["raw_authority_sha256"]
            or not grid["complete"] or grid["points"] != result["grid_points"] or grid["points"] != 179
            or ports["grid"]["prepared_views"] != 2 or ports["grid"]["prepared_calls"] != 356
            or grid["projection"]["native_projection"] != 708
            or grid["projection"]["exact_projection_checks"] != 4
            or grid["projection"]["native_selection"] != 356 or grid["assembly"]["assembly_calls"] != 356):
        raise ValueError("The sealed pair's original successor science or live grid scope changed")
    owners = witness["evidence"]["owner_rows"]
    counts = {}
    for arm in ARMS:
        row = detail["arms"][arm]
        labels = {observation: norad for observation, norad, _role in owners[arm]}
        key = "sha256:"+sha256(json.dumps(labels, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
        if (len(labels) != len(owners[arm]) or key != result["evidence"]["owners"][arm]
                or row["endpoint_latlon"] != result["evidence"]["arms"][arm]["latlon"]):
            raise ValueError("Owner rows or arm endpoints differ from original qualification")
        counts[arm] = len(labels)
    report = rank_scope(rank, risk["two_centre_rank"], ports["blocks"], ports["graph"]["graph"])
    report.update(partition(solve, rank["cpu_ns"], prep, attempt, grid))
    done = attempt["cold"]["completed"]
    loser_clocks = [item["cpu_ns"] for item in done if item["branch"] != attempt["cold"]["branch"]]
    return dict(report, receipt_sha256=dict(result=result_sha, witness=witness_sha, acquisition=acquisition_sha,
                                            marker=marker_sha),
                wall_through_verified_s=result["elapsed_s"], owner_count=counts,
                owners_and_roles_same_across_arms=owners["c0"] == owners["fitted_c"],
                grid_ports=grid, prepared_grid_views=ports["grid"], portable=ports["portable"],
                finalist_prefix_cpu_ns=sum(item["cpu_ns"] for item in attempt["cold"]["prefix"]),
                completed_finalists=len(done), hindsight_losing_completions_cpu_ns=sum(loser_clocks))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("campaign", type=Path)
    args = cli.parse_args()
    result = {case: summarize(args.campaign/"cases"/case/"successor/attempt-000001") for case in CASES}
    print(json.dumps(dict(schema_version=1, cases=result, numerical_runs=0, waveform_reads=0),
                     sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
