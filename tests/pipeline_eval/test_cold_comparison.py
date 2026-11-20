from tools.pipeline_eval.qualification import cold_comparison


def test_global_guess_and_given_tile_center_do_not_count_as_published_fixes():
    truth = [0.0, 0.0]
    case = dict(id="example", regions=[dict(id="prior", center=truth)])
    ref = dict(
        truth=truth, group="DS26", reference={"baseline": {"c0": dict(latlon=truth, error_km=0)}}
    )
    row = dict(
        worker_wall_s=1.2,
        result=dict(status="withheld", arms={"c0": dict(latlon=None, forced_latlon=[0, 1])}),
    )
    v5 = dict(worker_wall_s=8, result=dict(arms={"c0": dict(latlon=truth)}))
    rows = [
        cold_comparison.comparison_row(case, ref, row, v5, "score", mode, "c0")
        for mode in ("global", "matched-tile")
    ]
    global_row, assisted = cold_comparison.summarize(rows)
    assert global_row["attempts"] == assisted["attempts"] == 1
    assert global_row["returned_count"] == assisted["returned_count"] == 0
    assert global_row["forced_count"] == 1 and global_row["forced_median_km"] > 100
    assert global_row["prior_center_median_km"] is None
    assert assisted["prior_center_count"] == assisted["prior_center_within_5_km"] == 1
    assert assisted["median_v5_worker_wall_s"] == 8
