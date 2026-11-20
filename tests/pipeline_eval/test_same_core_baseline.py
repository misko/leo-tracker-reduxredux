from tools.pipeline_eval.qualification import same_core_baseline as trial
from tools.pipeline_eval.qualification import same_core_baseline_results as report


def test_selection_is_hash_stable_with_two_strata_in_each_dataset():
    refs, stock = {}, {}
    for ds in ("DS26", "DS29"):
        for index, old in enumerate((101, 140, 180, 250, 280, 310, 339, 350)):
            ident = f"{ds}-{index}"
            refs[ident] = dict(
                group=ds,
                reference=dict(
                    baseline={a: dict(wall_s=old, latlon=[1, 1]) for a in ("c0", "fitted_c")}
                ),
            )
            stock[ident] = dict(source="fresh_full_panel", worker_wall_s=80)
    ids, strata = trial.selection(refs, stock)
    assert trial.selection(dict(reversed(list(refs.items()))), stock) == (ids, strata)
    assert [(r["dataset"], r["half"]) for r in strata] == [
        ("DS26", "low"),
        ("DS26", "high"),
        ("DS29", "low"),
        ("DS29", "high"),
    ]
    assert all(r["historical_original_s"] <= 340 for r in strata)


def fixture(original=True, state="ok"):
    groups = (*report.SHARED, *report.LATE, *report.RENDER)
    base = dict(
        id="DS26-0026",
        cpu=20,
        order=0,
        resources=dict(
            wall_s=120,
            cpu_s=55,
            child_user_s=45,
            child_system_s=5,
            child_peak_rss_kib=250000,
        ),
    )
    if original:
        metric = dict(candidate_s=119, stages=groups, stage_s=[2] * len(groups))
    else:
        metric = dict(candidate_s=100, stage_s=dict.fromkeys(report.SHARED, 1))
    return dict(
        base,
        method=report.ORIGINAL if original else report.COMPACT,
        result=dict(status=state, metrics=metric),
    )


def test_original_late_and_render_are_disjoint_from_common_stages():
    row = report.timing(fixture())
    assert row["common_through_cavity_s"] == 12
    assert row["original_full_late_s"] == 24
    assert row["numerical_published_boundary_s"] == 36
    assert row["original_render_s"] == 4
    assert row["worker_other_s"] == 79
    assert row["child_cpu_s"] == 50
    assert report.timing(fixture(original=False))["numerical_published_boundary_s"] == 6


def test_timeout_has_no_speed_ratio_and_survives_the_paired_roster():
    incomplete = report.timing(fixture(state="timed_out"))
    assert incomplete["numerical_published_boundary_s"] is None
    result = report.summarize([incomplete, report.timing(fixture(original=False))])
    assert result["planned_pairs"] == 1
    assert result["completed_pairs"] == 0
    assert result["pairs"][0]["launcher_wall_s"] is None
