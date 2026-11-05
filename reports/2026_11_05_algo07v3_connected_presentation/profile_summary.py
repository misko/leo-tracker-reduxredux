"""Summarize the separately instrumented fresh run only after exact parity."""

import json
import pstats

from render import OUT, RUN, checked, digest


def main():
    from compare_algo07v3_inclusion import first_difference
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    baseline, baseline_receipt = checked(RUN / "fresh-candidate.json")
    profiled, receipt = checked(RUN / "profile-candidate.json")
    difference = first_difference(baseline, profiled)
    assert difference is None, difference
    for name, sha in profiled["presentation"]["products"].items():
        assert digest(RUN / "profile-artifacts" / (name + ".png")) == sha
        assert digest(RUN / "fresh-artifacts" / (name + ".png")) == sha
    profile = RUN / "fresh-profile.pstats"
    stats = pstats.Stats(str(profile))

    def total(suffix, function, *, missing_direct_caller=False):
        found = [
            (key, row)
            for key, row in stats.stats.items()
            if key[0].endswith(suffix) and key[2] == function
        ]
        assert len(found) == 1, (suffix, function, len(found))
        key, row = found[0]
        if not missing_direct_caller:
            return row[3]
        # Exactly two controller calls: the source's direct predictive call and
        # the captured numerical replay call. The harness frame is absent here.
        callers = row[4]
        assert row[1] == 2 and len(callers) == 1
        caller, values = next(iter(callers.items()))
        assert caller[0].endswith("localization_v3/numerical_recovery.py")
        assert caller[2] == "replay_recovery" and values[1] == 1
        return row[3] - values[3]

    stages = {}
    entries = [
        ("Initial regional search", "localization_v3/initial_search.py", "initial_search"),
        (
            "Conservative recovery",
            "localization_v3/conservative_recovery.py",
            "conservative_recovery",
        ),
        ("Family/history policy", "localization_v3/history_policy.py", "history_policy"),
        ("Signed-prior context", "localization_v3/signed_context.py", "signed_context"),
        ("Cavity nominations", "localization_v3/family_cavity.py", "nominate_families"),
        ("Cavity fitting", "localization_v3/family_cavity.py", "cavity_policy"),
        ("Recovery inventory", "localization_v3/recovery_inventory.py", "prepare_recovery"),
        ("Numerical recovery", "application/localization_v3.py", "recover_numerical_checkpoint"),
        ("Gap recovery", "application/localization_v3.py", "recover_gap_checkpoint"),
        ("Residual preparation", "application/localization_v3.py", "prepare_additional_checkpoint"),
        ("Residual screening", "application/localization_v3.py", "screen_additional_recovery"),
        ("Additional-family fitting", "application/localization_v3.py", "fit_additional_recovery"),
        ("Final incumbent preparation", "application/localization_v3.py", "prepare_reassociation"),
        ("Final family ranking", "application/localization_v3.py", "rank_reassociation_families"),
        (
            "Final association screening",
            "application/localization_v3.py",
            "screen_reassociation_candidates",
        ),
        ("Final guarded fitting", "application/localization_v3.py", "fit_reassociation"),
        ("Plot evidence and grid", "presentation/localization_v3.py", "prepare_packet"),
    ]
    for label, filename, function in entries:
        stages[label] = total(filename, function)
    stages["Predictive recovery"] = total(
        "localization_v3/recovery_controller.py",
        "recover_tracks",
        missing_direct_caller=True,
    )
    overall = stats.total_tt
    other = overall - sum(stages.values())
    assert other >= 0, "Nested stage accounting must not be added twice"
    stages["Unattributed, rendering, imports and serialization"] = other
    top = sorted(stats.stats.items(), key=lambda item: item[1][2], reverse=True)[:25]
    rows = [
        dict(
            file=k[0],
            line=k[1],
            function=k[2],
            primitive_calls=v[0],
            calls=v[1],
            own_seconds=v[2],
            cumulative_seconds=v[3],
        )
        for k, v in top
    ]
    gaussian = total("localization_v3/marginal.py", "integrated_gaussian")
    summary = dict(
        case="DS26-0002",
        profile_sha256=digest(profile),
        exact_profile_outputs=True,
        observed_unprofiled_seconds=baseline_receipt["seconds"],
        observed_profiled_seconds=receipt["seconds"],
        profiler_total_self_seconds=overall,
        missing_profiler_frames=["harness run", "present_owned_result", "render"],
        stage_attribution_complete=False,
        stage_seconds=stages,
        top_own_time_functions=rows,
        integrated_gaussian_inclusive_seconds=gaussian,
        integrated_gaussian_fraction_of_run=gaussian / overall,
        performance_ratio=None,
        complete_path_speedup=None,
        scope=(
            "Prepared inputs through numerical policies, complete grid and eight PNGs; "
            "no publication"
        ),
    )
    (OUT / "profile.json").write_text(json.dumps(summary, indent=2) + "\n")
    files = [
        profile,
        RUN / "fresh-candidate.json",
        RUN / "fresh-candidate.receipt.json",
        RUN / "profile-candidate.json",
        RUN / "profile-candidate.receipt.json",
    ]
    (OUT / "profile-bindings.json").write_text(
        json.dumps(
            {path.name: dict(path=str(path), sha256=digest(path)) for path in files}, indent=2
        )
        + "\n"
    )
    table = "| Stage | Profiled seconds | Share of profiled run |\n|---|---:|---:|\n"
    for name, seconds in sorted(stages.items(), key=lambda row: -row[1]):
        table += f"| {name} | {seconds:.3f} | {100 * seconds / overall:.1f}% |\n"
    (OUT / "profile-stages.md").write_text(table)
    selected = sorted(stages.items(), key=lambda row: -row[1])[:9]
    figure = Figure(figsize=(11, 6), layout="constrained")
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    labels, seconds = zip(*selected, strict=True)
    bars = axis.barh(
        labels,
        seconds,
        color=["#888888" if name.startswith("Unattributed") else "#3076a8" for name in labels],
    )
    axis.invert_yaxis()
    axis.bar_label(bars, fmt="%.1f s", padding=4)
    axis.set_xlim(0, max(seconds) * 1.15)
    axis.set_xlabel("Seconds in separately instrumented execution")
    axis.set_title("DS26-0002: ALGO07v3 profile\nPartial stage attribution; exact output parity")
    figure.savefig(OUT / "profile-stages.png", dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
