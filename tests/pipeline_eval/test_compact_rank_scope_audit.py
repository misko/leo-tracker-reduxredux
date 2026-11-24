"""Rank work, memory and phase-clock attribution for sealed successor receipts."""

from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
from compact_rank_scope_audit import exactly, partition, rank_scope


def test_two_count_ratio_is_explained_by_one_centre_and_four_corner_geometries():
    rank = dict(cpu_ns=800, inputs=dict(centre_projection_bytes=672, centre_projections_reused=4,
                                       nominal_projections=5, other_projections=4,
                                       centre_track_cells_reused=144, centre_track_terms_reused=8,
                                       geometry_track_terms_built=10, fused_passes=9,
                                       nominal_projection_cells=140, peak_centre_track_bytes=776,
                                       statistics_cpu_ns=127))
    seeds = dict(catalogue_rows=4, original_curved=2, paid_centres=2)
    blocks = dict(calls=20, compact_calls=20, index_builds=10, original_rows=80, rows_saved=55,
                  rows_retained=25, padded_cells=360)
    graph = dict(tracks=3, assigned=11)
    scoped = rank_scope(rank, seeds, blocks, graph)
    assert scoped["projection_axis_epochs"] == 7
    assert scoped["curved_points"] == 9
    assert scoped["rank_only_omittable_epochs_upper_bound"] == 2
    assert scoped["possible_bytes_removed_from_one_projection_upper_bound"] == 192
    assert scoped["generations"] == dict(unique_nominal_views=5, centres=2, corners=4,
                                         unique_associations=10, same_state_explore_returns_reused=8)
    assert scoped["centre_terms_peak_bytes"] == 776
    assert scoped["concurrent_centre_payload_bytes"] == 1448
    assert scoped["cumulative_padded_matrix_bytes"] == 2880
    assert scoped["other_inclusive_rank_cpu_ns"] == 673
    with pytest.raises(ValueError, match="different branch"):
        rank_scope(rank, seeds, dict(blocks, calls=22), graph)
    with pytest.raises(ValueError, match="different branch"):
        rank_scope(rank, dict(seeds, ordinary_retry={}), blocks, graph)
    with pytest.raises(ValueError, match="not divisible"):
        exactly(5, 3)


def test_nonoverlap_reducer_subtracts_rank_and_grid_from_their_parents():
    attempt = {key: {"cpu_s": value} for key, value in (
        ("cold_clocks", 4.5), ("candidate_pre_evidence_clocks", 7.5),
        ("signed_total_clocks", 1.5), ("standard_evidence_clocks", 5.2), ("exterior_clocks", .01)
    )}
    parts = partition(dict(cpu_s=17), 3_000_000_000, dict(cpu_ns=2_500_000_000), attempt,
                      dict(clock=dict(cpu_ns=4_740_000_000)))["disjoint_cpu_ns"]
    assert parts["rank"] == 3_000_000_000
    assert parts["cold_after_rank"] == 1_500_000_000
    assert parts["proposal_after_cold"] == 3_000_000_000
    assert parts["grid"] == 4_740_000_000
    assert parts["evidence_outside_grid"] == 460_000_000
    assert parts["remaining_solve"] == 290_000_000
    assert sum(parts.values()) == 17_000_000_000
    with pytest.raises(ValueError, match="partitioned"):
        partition(dict(cpu_s=16), 3_000_000_000, dict(cpu_ns=2_500_000_000), attempt,
                  dict(clock=dict(cpu_ns=4_740_000_000)))
