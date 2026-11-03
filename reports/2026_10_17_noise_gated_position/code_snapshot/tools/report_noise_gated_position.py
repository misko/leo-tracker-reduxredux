"""Report matched legacy/new objective searches, accuracy and frozen-state nulls."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from associate_merged_track_catalogue import load_tracks, write

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_17_noise_gated_position"
CASES = ("DSX01-S01", "DS22-001")
ARMS = ("c0", "fitted_c")
METHODS = ("legacy_control", "search")
RAW = {"DSX01-S01": 4797, "DS22-001": 4039}


def read(path):
    return json.loads(path.read_text())


def run():
    rows, bindings, associations, null_rows = [], {}, {}, []
    for case in CASES:
        for arm in ARMS:
            for method in METHODS:
                folder = REPORT / method / case / arm
                row = read(folder / "summary.json")
                evaluation = read(folder / "evaluation.json")
                digest = hashlib.sha256((folder / "fit.json").read_bytes()).hexdigest()
                if digest != evaluation["fit_sha256"]:
                    raise ValueError("endpoint is not bound to its evaluation")
                if not read(folder / "fit.json")["endpoint"]["exact_phase_geometry"]:
                    raise ValueError("final state lacks exact phase geometry")
                association = read(folder / "association.json")
                if not association["all_original_points_accounted_for"]:
                    raise ValueError("original point accounting failed")
                ids = association["associated_observation_ids"]
                if len(ids) != len(set(ids)) or len(ids) != row["associated_points"]:
                    raise ValueError("associated IDs disagree with summary")
                rows.append(
                    dict(
                        row,
                        method=method,
                        arm=arm,
                        associated_percent_raw=100 * len(ids) / RAW[case],
                        points_per_track=len(ids) / max(1, row["merged_tracks"]),
                    )
                )
                associations[case, arm, method] = association
                bindings[str((folder / "fit.json").relative_to(REPORT))] = digest
                if method == "search":
                    null = read(folder / "conditional_nulls.json")
                    counts = [r["compatible_curved_points"] for r in null["nulls"]]
                    null_rows.append(
                        dict(
                            case=case,
                            arm=arm,
                            actual_curved_points=null["actual"]["compatible_curved_points"],
                            null_min=min(counts),
                            null_median=float(np.median(counts)),
                            null_max=max(counts),
                            repetitions=len(counts),
                        )
                    )
    write(REPORT / "summary.json", rows)
    write(REPORT / "null_summary.json", null_rows)

    point_labels, support, comparisons = {}, [], []
    for case in CASES:
        recording = (
            ROOT
            / "reports/2026_10_17_ds22_merged_satellites"
            / ("dsx01_adapter" if case.startswith("DSX") else "cohort")
            / case
        )
        source = {t["key"]: t for t in load_tracks(recording)}
        for arm in ARMS:
            for method in METHODS:
                assoc = associations[case, arm, method]
                admitted = [r for r in assoc["association"]["rows"] if r["compatible"]]
                accepted = set(assoc["associated_observation_ids"])
                point_labels[case, arm, method] = {
                    oid: r["candidate_norad"]
                    for r in admitted
                    for oid in source[r["component"]]["observation_ids"]
                    if oid in accepted
                }
                by_sat = {}
                for r in admitted:
                    if r["active_curvature"]:
                        by_sat.setdefault(r["candidate_norad"], []).append(r)
                support.append(
                    dict(
                        case=case,
                        arm=arm,
                        method=method,
                        curved_satellites=len(by_sat),
                        satellites_with_one_curved_fragment=sum(
                            len(v) == 1 for v in by_sat.values()
                        ),
                        single_curved_fragment_points=sum(
                            v[0]["points"] for v in by_sat.values() if len(v) == 1
                        ),
                        curved_points=sum(r["points"] for v in by_sat.values() for r in v),
                    )
                )
        pairs = [
            ("c0", "legacy_control", "c0", "search"),
            ("fitted_c", "legacy_control", "fitted_c", "search"),
            ("c0", "search", "fitted_c", "search"),
        ]
        for arm1, method1, arm2, method2 in pairs:
            a, b = point_labels[case, arm1, method1], point_labels[case, arm2, method2]
            common = a.keys() & b.keys()
            comparisons.append(
                dict(
                    case=case,
                    first=f"{method1}/{arm1}",
                    second=f"{method2}/{arm2}",
                    common_associated_points=len(common),
                    same_norad_points=sum(a[oid] == b[oid] for oid in common),
                    changed_norad_points=sum(a[oid] != b[oid] for oid in common),
                    gained_points=len(b.keys() - a.keys()),
                    lost_points=len(a.keys() - b.keys()),
                )
            )
    write(REPORT / "pairwise_labels.json", comparisons)
    write(REPORT / "curved_satellite_support.json", support)

    rms_rows = []
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    for index, (case, arm) in enumerate((c, a) for c in CASES for a in ARMS):
        ax = axes.flat[index]
        for method, color in (("legacy_control", "#777777"), ("search", "#2878b5")):
            values = []
            for group in associations[case, arm, method]["consolidated"]["groups"]:
                n, b = group["points"], group["bias_hz"]
                # Invert the saved Gaussian contrast, including its two prior terms.
                sse = 150**2 * (group["cost"] - b**2 / 1000**2 - np.log1p(n * 1000**2 / 150**2))
                rms = float(np.sqrt(max(0, sse) / n))
                rms_rows.append(dict(case=case, arm=arm, method=method, rms_hz=rms, **group))
                values.append(rms)
            ax.plot(
                np.arange(1, len(values) + 1),
                sorted(values),
                ".-",
                color=color,
                markersize=3,
                label="Legacy" if method == "legacy_control" else "Noise-gated",
            )
        ax.set(
            title=f"{case} / {arm}",
            xlabel="Merged-track rank, sorted within method",
            ylabel="RMS (Hz)",
            ylim=(0, 450),
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.suptitle("RMS under each merged track's shared constant; every admitted point retained")
    fig.savefig(REPORT / "merged_track_rms.png", dpi=150)
    plt.close(fig)
    write(REPORT / "merged_track_rms.json", rms_rows)

    labels = [f"{c}\n{a}" for c in CASES for a in ARMS]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), layout="constrained")
    for ax, field, title in zip(
        axes,
        ("position_error_km", "associated_percent_raw", "points_per_track"),
        ("Position error (km)", "Associated / all raw GLRT (%)", "GLRT points per merged track"),
        strict=True,
    ):
        for shift, method, color, name in (
            (-0.2, "legacy_control", "#777777", "Legacy objective"),
            (0.2, "search", "#2878b5", "Noise-gated objective"),
        ):
            selected = [r for r in rows if r["method"] == method]
            ax.bar(
                np.arange(4) + shift,
                [r[field] for r in selected],
                width=0.38,
                label=name,
                color=color,
            )
        ax.set(xticks=np.arange(4), xticklabels=labels, title=title)
        ax.tick_params(axis="x", labelsize=8)
        ax.grid(axis="y", alpha=0.2)
    axes[0].axhline(0.5, color="#bb2222", ls="--", label="0.5 km target")
    axes[0].legend(fontsize=8)
    fig.suptitle("Matched resumed blind searches: fit coverage and accuracy are separate")
    fig.savefig(REPORT / "comparison.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 2, figsize=(15, 14), layout="constrained")
    all_norads = sorted(
        {
            r["candidate_norad"]
            for a in associations.values()
            for r in a["association"]["rows"]
            if r["compatible"]
        }
    )
    colors = {
        n: plt.get_cmap("turbo")(i / max(1, len(all_norads) - 1)) for i, n in enumerate(all_norads)
    }
    for index, (case, arm) in enumerate((c, a) for c in CASES for a in ARMS):
        recording = (
            ROOT
            / "reports/2026_10_17_ds22_merged_satellites"
            / ("dsx01_adapter" if case.startswith("DSX") else "cohort")
            / case
        )
        tracks = load_tracks(recording)
        for col, method in enumerate(METHODS):
            ax, assoc = axes[index, col], associations[case, arm, method]
            accepted = set(assoc["associated_observation_ids"])
            mapping = {r["component"]: r for r in assoc["association"]["rows"]}
            for t in tracks:
                mask = np.array([oid in accepted for oid in t["observation_ids"]])
                ax.scatter(
                    t["times"][~mask],
                    t["values"][~mask] / 1000,
                    s=5,
                    color="#bdbdbd",
                    alpha=0.55,
                    rasterized=True,
                )
                if mask.any():
                    ax.scatter(
                        t["times"][mask],
                        t["values"][mask] / 1000,
                        s=7,
                        color=colors[mapping[t["key"]]["candidate_norad"]],
                        rasterized=True,
                    )
            name = "Legacy" if method == "legacy_control" else "Noise-gated"
            ax.set(
                title=f"{case} / {arm} / {name}: {len(accepted):,} points",
                xlabel="Time within scan (s)",
                ylabel="Native unwrapped GLRT CFO (kHz)",
            )
            ax.grid(alpha=0.15)
    fig.suptitle(
        "Original Graph observations: satellite colors, unassociated points in grey\n"
        "Colors identify candidate NORAD consistently across panels; no curve resampling"
    )
    fig.savefig(REPORT / "track_associations.png", dpi=140)
    plt.close(fig)

    table = "\n".join(
        f"| {r['case']} | {r['arm']} | "
        f"{'Legacy' if r['method'] == 'legacy_control' else 'Noise-gated'} "
        f"| {r['position_error_km']:.3f} | {r['associated_points']:,} | "
        f"{r['associated_percent_raw']:.2f}% | {r['merged_tracks']} | {r['points_per_track']:.1f} |"
        for r in rows
    )
    null_table = "\n".join(
        f"| {r['case']} | {r['arm']} | {r['actual_curved_points']} | "
        f"{r['null_min']} / {r['null_median']:.0f} / {r['null_max']} |"
        for r in null_rows
    )
    diagnoses = [
        read(REPORT / "known_position_diagnostic" / c / a / "summary.json")
        for c in CASES
        for a in ARMS
    ]
    diagnostic_table = "\n".join(
        f"| {r['case']} | {'fitted_c' if r['fitted_c'] else 'c0'} | "
        f"{r['blind_score'] / 1e6:.2f} | "
        f"{r['known_position_same_blind_initializer_score'] / 1e6:.2f} | "
        f"{r['known_position_historical_initializer_score'] / 1e6:.2f} |"
        for r in diagnoses
    )
    pairwise_table = "\n".join(
        f"| {r['case']} | {r['first']} -> {r['second']} | {r['common_associated_points']} | "
        f"{r['changed_norad_points']} | {r['gained_points']} / {r['lost_points']} |"
        for r in comparisons
    )
    support_table = "\n".join(
        f"| {r['case']} | {r['arm']} | {r['satellites_with_one_curved_fragment']} / "
        f"{r['curved_satellites']} | {r['single_curved_fragment_points']} / {r['curved_points']} |"
        for r in support
        if r["method"] == "search"
    )
    text = f"""# Whole-track noise evidence inside satellite/position fitting

This experiment implements the residual-aware criterion inside parameter
updates and geographic ranking, then evaluates actual position error. Both
DSX01 scan 1 and DS22 scan 001 have paired c=0/fitted-c runs and matching
legacy-objective controls. The results below are resumed blind local searches,
not global convergence or independent satellite identity validation.

## Controlled search and association

All methods use the same causal candidate banks, radio-only robust partitions,
original measured CFOs / times / RF / IDs, and scan-specific receiver/band
offsets and small drifts (sigma 0.5 Hz/s, bound 1 Hz/s). Each c pair starts from
the same earlier **blind c=0** position and eight hardware coefficients; fitted-c
adds a zero initial c. The new method also receives the same blind phase vector
in both c arms. No known-position phases or hardware enter a blind search.

Only individually measured-curved fragments can rank geographic states or
calibrate hardware/phase. The score applies all candidates' visibility, RMS
450 Hz, component-constant 3,000 Hz, member mean/slope/quadratic/step/lag-1 gates
before choosing a winner. Failed components pay the declared capped-count
900 Hz squared cost. Bias, drift, phase, conditional phase-volume and hardware
dimension penalties remain. The same original measurements contribute; there
is no point holdout or smoothing. Gates are finite-sample diagnostics, not a
guarantee of white noise or correct identity.

The new solver generates two proposals at each location (previous blind state
and legacy fit), takes up to two feasible-component joint updates per tangent,
and accepts only new-score improvements. Linear / failing tracks cannot update
parameters. Three finalists are checked under exact nonlinear phase geometry,
with up to four relinearizations for each proposal. An exact score, rather than
a tangent score, chooses the reported endpoint.

Both algorithms search a fixed 3x3 grid of +/-16 km around their common blind
start, followed by up to two axial sweeps at 8, 2, 0.5 and 0.125 km. The cap is
41 discovery locations with 4 generated legacy seeds; three exact finalists use
8 generated seeds. Actual visited locations can differ because rankings differ.
The new method spends additional feasible-update work, so this comparison
matches declared geographic / seed budgets, not CPU instructions. Final
association uses the same candidate-after-gates logic for both algorithms, then
requires curved hardware/phase support before admitting linear fragments.
Lossless shared-constant merging checks every member and pooled residual with
a maximum 30 s gap; it does not itself refit the position.

## Blind endpoints

On these matched local searches, the new method reduces error from 11.968 km
to 8.367 / 8.501 km on DSX01-S01 (c=0 / fitted-c), and from 12.924 km to
3.241 / 1.895 km on DS22-001. No endpoint meets the 0.5 km target. Fitted-c
helps DS22 accuracy here, but on DSX01 associates more points while giving a
slightly larger position error. These two scans cannot establish a general
accuracy advantage for fitted-c.

| Dataset | c arm | Method | Error km | Associated | % raw GLRT | Merged tracks | Points/track |
|---|---|---|---:|---:|---:|---:|---:|
{table}

Percentages use 4,797 raw GLRT points for DSX01-S01 and 4,039 for DS22-001,
including points outside the 4,487 / 3,510-point Graph populations. One S01
measurement remains explicit background; DS22 membership is unchanged. GPS
37.849061591561885, -122.48574968092912 is used only after saving each blind
endpoint. Observer height is fixed at 0 m in all models. Endpoint hashes bind
the evaluations. Better fit or association
coverage must not be read as better position accuracy.

![Accuracy and association comparison](comparison.png)

![GLRT association panels](track_associations.png)

![Merged-track RMS distributions](merged_track_rms.png)

`merged_track_rms.json` records RMS, members, candidate and point count for every
merged track. RMS is recovered from the saved Gaussian contrast after removing
its constant-prior and volume terms (150 Hz noise, 1,000 Hz bias prior). The plot
sorts each method independently; equal ranks do not imply matching identities.

## Label stability and independent-arc support

The comparison below uses original observation IDs, not curve resampling or
time-nearest matching. Changed NORAD means both methods associate the same
measurement but nominate different objects. Stability is not identity truth.

| Dataset | Comparison | Common points | Changed NORAD | Gained / lost |
|---|---|---:|---:|---:|
{pairwise_table}

The two new c arms agree on NORAD for all 2,334 common S01 points and all 1,567
common DS22 points. Against the old control, 61 common S01 points change NORAD
in each c arm and no common DS22 points do. Much of the gain is a change in
which fragments pass, rather than a wholesale relabelling of shared points.
Agreement across these variants still does not supply external identity truth.

For each new fit, count satellites supported by only one measured-curved
fragment. Multiple fragments do not necessarily mean independent passes or
independent calibration; this is a descriptive support inventory.

| Dataset | c arm | Single-curved-fragment satellites / all | Their points / curved points |
|---|---|---:|---:|
{support_table}

## Conditional random-intercept diagnostics

For each new final state, 16 deterministic randomizations add an independent
uniform native-period intercept to each curved fragment. Times, centered curve
shape, noise and RF remain fixed; parameters, phases and position remain frozen.
Both c arms use identical random draws. Candidates and gates remain unchanged.
The table reports only curved points, which are the observations allowed to
calibrate; these counts differ from total associated Graph points above.

| Dataset | c arm | Actual curved points | Null min / median / max |
|---|---|---:|---:|
{null_table}

This is a conditional frequency-coincidence check, not an end-to-end null search,
an authenticated label test, or a calibrated false discovery rate. It does not
measure how often reoptimizing hardware, phases and position on null data would
recover apparent tracks. That stronger test remains outstanding.

## Separate post-search known-position diagnostics

Only after completed blind endpoints and nulls are saved, a separate tool fixes
the supplied GPS and runs the new fit with the same blind initializer/budget.
It also refines an earlier known-position fit as a distinct initialization
sensitivity check. Neither diagnostic is fed into the reported searches.
Scores below are new composite scores in millions; lower is better. Historical
known-position initialization has information unavailable to a blind search.

| Dataset | c arm | Blind endpoint | GPS / blind start | GPS / historical GPS start |
|---|---|---:|---:|---:|
{diagnostic_table}

All four new blind endpoints score better than both tested GPS initializations.
Thus integrating residual gates improves this experiment but does not make
noise-like residuals sufficient for correct positioning or identity. More
search alone has no guarantee of fixing that remaining discrepancy. These
finite proposals do not prove a globally worse optimum at GPS.

If GPS scores better, the saved wrong endpoint does not establish a globally
preferred wrong position: geographic or parameter proposal search still misses
a better state. If a wrong endpoint beats tested GPS states, that is evidence
of a model/criterion mismatch within the tested proposals, not proof that all
GPS states are worse. The larger <0.5 km objective remains unachieved unless
independent, representative results meet it; these two scans alone cannot
establish performance on the full DS22 and DSX01 corpora.

The next diagnostic should transfer each saved blind candidate family to GPS
with identities fixed, then refit only allowed shared hardware/phase parameters
on measured-curved fragments. That separates a failure to propose good
parameters at GPS from incompatible candidate families or a frequency-model
error. It must remain separate from blind search and must not promote a
GPS-derived parameter state into a localization result. Shared-constant merged
families and independently curved members can then supply stronger joint
constraints without recruiting linear fragments for calibration.

## Validation and reproducibility

Thirty-five focused tests passed for robust membership, preserved original IDs,
provided-population consolidation, phase profiling, candidate-after-gates
association, linear association without calibration, and monotonic new-score
updates. Independent dense point residuals agree with tangent sufficient
statistics for c=0 and fitted-c, including nonzero phase anchors. All changed
scientific sources pass Ruff. Code snapshots bind the run versions; bank and
partition receipts bind the same durable inputs as the previous repair report.
All runs use existing on-disk observations; no RF collection was performed.

The result directories preserve every endpoint, trace, exact finalist,
association, original observation ID, merged component, null draw summary and
GPS-only diagnostic. `validation.json` binds endpoint hashes. This is a research
prototype; published contracts and baseline reports are unchanged.
"""
    (REPORT / "README.md").write_text(text)
    write(
        REPORT / "validation.json",
        dict(
            endpoint_sha256=bindings,
            focused_tests_passed=35,
            original_ids_verified=True,
            exact_phase_finalists_verified=True,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    print(json.dumps(rows), flush=True)


if __name__ == "__main__":
    run()
