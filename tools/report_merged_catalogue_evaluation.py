"""Summarize complete DS22 fast-input comparisons and unsuccessful position pilots."""
# ruff: noqa: E501

import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_17_ds22_merged_satellites"


def table(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def render():
    aggregates, per_case, consolidations = [], [], []
    actual = {}
    for dataset, folder, denominator in (
        ("DS22 fast", "catalogue", 243085),
        ("DSX01", "dsx01_catalogue", 20084),
    ):
        total = defaultdict(Counter)
        for path in sorted((REPORT / folder).glob("*/bias_*/summary.json")):
            for row in json.loads(path.read_text()):
                key = (row["grouped"], row["fitted_c"], row["component_bias_sigma_hz"])
                for name in (
                    "components",
                    "graph_points",
                    "compatible_components",
                    "compatible_points",
                ):
                    total[key][name] += row[name]
                total[key]["cases"] += 1
                per_case.append(dict(dataset=dataset, **row))
        for key, counts in sorted(total.items()):
            grouped, c, sigma = key
            aggregates.append(
                [
                    dataset,
                    "hard merged" if grouped else "Graph fragments",
                    "fitted c" if c else "c=0",
                    int(sigma),
                    counts["cases"],
                    counts["components"],
                    counts["compatible_components"],
                    counts["compatible_points"],
                    f"{100 * counts['compatible_points'] / denominator:.2f}%",
                    f"{counts['compatible_points'] / max(1, counts['compatible_components']):.2f}",
                ]
            )
        actual[dataset] = total
    for dataset, folder in (("DS22 fast", "consolidated"), ("DSX01", "dsx01_consolidated")):
        rows = json.loads((REPORT / folder / "summary.json").read_text())
        for fitted_c in (False, True):
            selected = [r for r in rows if r["fitted_c"] == fitted_c]
            counts = {
                k: sum(r[k] for r in selected)
                for k in ("input_tracks", "output_tracks", "points", "points_dropped")
            }
            assert counts["points_dropped"] == 0
            consolidations.append(
                [
                    dataset,
                    "fitted c" if fitted_c else "c=0",
                    counts["input_tracks"],
                    counts["output_tracks"],
                    counts["points"],
                    0,
                    f"{counts['points'] / max(counts['output_tracks'], 1):.2f}",
                ]
            )
    coverage = json.loads((REPORT / "cohort/coverage.json").read_text())
    assert len(coverage) == 137
    statuses = Counter(r["status"] for r in coverage)
    evaluated = [r for r in coverage if r["status"] == "tracks_evaluated"]
    assert len(evaluated) == 68
    assert sum(r["winning_points"] for r in evaluated) == 243085
    assert sum(r["graph_points"] for r in evaluated) == 216039
    with (REPORT / "per-case-association.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=sorted(set().union(*(r.keys() for r in per_case))),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(per_case)
    with (REPORT / "aggregate-association.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerows(aggregates)
    position_rows = []
    for folder, sigma in (("position_hardware_only", 0), ("position_pilot", 1000)):
        for arm in ("c0", "fitted_c"):
            p = REPORT / folder / arm
            fit = json.loads((p / "fit.json").read_text())
            evaluation = json.loads((p / "evaluation.json").read_text())
            assert (
                hashlib.sha256((p / "fit.json").read_bytes()).hexdigest()
                == evaluation["fit_sha256"]
            )
            assert fit["geometry_uses_fixed_site_associations"] is False
            position_rows.append(
                [
                    sigma,
                    arm,
                    fit["evaluations"],
                    fit["full_data_location_evaluations"],
                    f"{fit['endpoint']['latitude_deg']:.6f}",
                    f"{fit['endpoint']['longitude_deg']:.6f}",
                    f"{evaluation['position_error_km']:.3f}",
                    evaluation["within_0_5km"],
                ]
            )
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), constrained_layout=True)
    fraction = np.array([r["graph_points"] / r["winning_points"] for r in evaluated])
    axes[0].hist(100 * fraction, bins=16, color="#267d9c")
    axes[0].set(
        xlabel="Graph-associated / gated winners (%)",
        ylabel="Recordings",
        title="DS22: all 68 available fast inputs",
    )
    x = np.arange(len(evaluated))
    axes[1].plot(x, [r["graph_tracks"] for r in evaluated], label="Graph fragments")
    axes[1].plot(x, [r["merged_tracks"] for r in evaluated], label="Hard polynomial components")
    axes[1].set(
        xlabel="Recording in acquisition order",
        ylabel="Track count",
        title="Track construction uses no satellite or position",
    )
    axes[1].legend()
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.savefig(REPORT / "track-coverage.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.7), constrained_layout=True)
    for axis, c in zip(axes, (False, True), strict=True):
        for grouped, sigma, label in (
            (False, 0, "Fragments, bias=0"),
            (True, 0, "Hard merged, bias=0"),
            (False, 1000, "Fragments, bias sigma=1 kHz"),
            (True, 1000, "Hard merged, bias sigma=1 kHz"),
        ):
            selected = sorted(
                [
                    r
                    for r in per_case
                    if r["dataset"] == "DS22 fast"
                    and r["fitted_c"] == c
                    and r["grouped"] == grouped
                    and r["component_bias_sigma_hz"] == sigma
                ],
                key=lambda r: r["source_id"],
            )
            denominator = {r["source_id"]: r["winning_points"] for r in evaluated}
            axis.plot(
                np.arange(len(selected)),
                [100 * r["compatible_points"] / denominator[r["source_id"]] for r in selected],
                label=label,
                lw=1,
            )
        axis.set(
            title="Fitted c" if c else "c = 0",
            xlabel="Recording in acquisition order",
            ylabel="Frequency-compatible / gated winners (%)",
        )
        axis.grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    fig.savefig(REPORT / "association-coverage.png", dpi=160)
    plt.close(fig)
    fig, axis = plt.subplots(figsize=(8, 4.6), constrained_layout=True)
    labels = [f"bias={r[0]} Hz\n{r[1]}" for r in position_rows]
    errors = [float(r[6]) for r in position_rows]
    axis.bar(labels, errors, color=["#267d9c", "#ca7e24"] * 2)
    axis.axhline(0.5, color="red", ls="--", label="0.5 km target")
    axis.set(ylabel="Horizontal error (km)", title="DS22-001 cold regional pilot: target not met")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)
    fig.savefig(REPORT / "position-error.png", dpi=160)
    plt.close(fig)
    maxima = []
    for p in (REPORT / "catalogue").glob("*/bias_0/orbit-receipt.json"):
        receipt = json.loads(p.read_text())
        assert all(
            r["element_epoch_utc_ns"] <= receipt["cutoff_utc_ns"]
            and r["collected_utc_ns"] <= receipt["cutoff_utc_ns"]
            for r in receipt["provenance"]
        )
        maxima.extend(r["maximum_error_hz"] for r in receipt["interpolation_checks"])
    report = f"""# Merged-track satellite association: DS22 transfer and position failure

The active goal remains **unachieved**: implement satellite association over the new track approaches, evaluate DS22 and DSX01, and verify horizontal position error below 0.5 km. The current cold position pilot is about146–148km from the supplied reference. Increased fixed-site association counts are not localization success.

This iteration evaluates every one of the **68 DS22 fast recordings with a sealed tracking input**, and all five frozen DSX01 scans. DS22 still has68 adaptive recordings without an implemented observation adapter here, plus one fast recording without a pinned tracking export. Every one of137 DS22 members remains in the coverage ledger. No unavailable recording is silently excluded or counted as successful. No new RF was collected.

## Track construction and merging

DS22 contains243,085 gate-passing maximum-margin GLRT winners in these68 fast exports. One physical probe contributes at most one winner. Their sealed snapshot digests and UTC-bracket/device-counter timing are checked. The frozen S01-selected Graph policy is transferred without retuning: degree≤4,150Hz noise scale,450Hz residual gate,8,000Hz/s physical slope cap,4 points per coefficient and6-second minimum span. This is the primary Graph policy; DSX01 reuses its earlier frozen recovered Graph memberships, which had an additional recovery pass. Cross-dataset differences therefore are not a controlled effect of the tracker policy.

Graph assigns216,039/243,085 points (**88.87%**) into7,120 fragments. Curved-only trimmed calibration and polynomial fusion reduce this to6,123 components, without dropping their points. The remaining27,046 gated winners stay in the evaluation denominator. Calibration uses only pairs with measured active curvature, not linear fragments; native drift is capped at5Hz/s. These are exploratory curve correspondences, not physical emitter truth.

![Track coverage](track-coverage.png)

The full137-member accounting is in [cohort/coverage.csv](cohort/coverage.csv). Its statuses are {dict(statuses)}. All68 fast exports name the same radio identifier; transferring the supplied station position to DS22 assumes a static installation. Radio identity alone does not independently prove absence of movement.

## Association model and controlled RF ablation

For each scan, retain four receiver×band constants and four small linear drifts: RX1-low, RX1-high, RX2-low and RX2-high. Drifts have a zero-centered2Hz/s Gaussian preference and a hard±5Hz/s limit. There is no one-offset-for-all-DSX01 assumption. Only individually curved fragments vote on hardware calibration, including when a linear member shares a merged component with a curved member.

The hardware-only arm has no component bias. The new arm adds **one native-Hz constant per whole component**, with a zero-centered1,000Hz Gaussian prior. A shared component bias cannot remove slope, curvature, or a discrepancy between member receivers/channels. Its branch-profiled score includes the Gaussian quadratic penalty and the log-determinant term log(1+n*tau²/sigma²). Native integer aliases are profiled per original fragment. The result is a bounded robust research score, not a normalized wrapped joint likelihood or identity posterior.

Actual RF scales the physical Doppler prediction. An optional scan-shared RF coefficient c is evaluated as a matched c=0/fitted-c ablation. Within each grouping/bias arm, observations, candidates, priors, classification checks and maximum160 discovery-seed budget are identical. The bias0 case algebraically nests the hardware-only score. Fewer seeds may satisfy the physical eligibility gates. The Gaussian prior supplies a centering assumption; these fitted offsets are not independent physical clock measurements.

Satellite candidates come from the newest eligible past Space-Track element per NORAD, with both collection and element epoch before the scan UTC bracket, within48hours. Preparation uses the broad regional center(37.5,-122.0), radius250km, and a conservative horizon guard; it does not select candidates using the supplied evaluation GPS. SGP4 is sampled every second and interpolated. The maximum checked interpolation discrepancy across these68 banks is **{max(maxima):.3f}Hz at11.5GHz**, over96 metadata-selected times and five declared regional sites per recording; this is a sampled qualification, not a uniform analytic error bound. UTC approximates UT1; polar motion is omitted.

Fixed-site association is evaluated at the supplied **37.849061591561885,-122.48574968092912**, assumed0m WGS84 ellipsoidal height. Recorded RF/LNB assignments remain hypotheses; nominal tuner correction is assumed zero in this portable replay. Above-horizon membership is required at every component observation. Compatibility requires≤450Hz RMS, a bias within3 prior sigmas, and the existing per-fragment residual mean/slope/quadratic/step/autocorrelation screen. No independent satellite IDs are available. These are **frequency-compatible candidates**, not verified satellite associations.

## Complete available-input association results

DS22 percentages below use all243,085 available fast gated winners, including Graph-unresolved points. DSX01 percentages use all20,084 original winning points; its frozen Graph population contains18,338. Counts are not percentages of unknown/unavailable adaptive observations.

{table(["Dataset", "Matching unit", "RF arm", "Bias sigma Hz", "Cases", "Input units", "Compatible units", "Compatible points", "% gated winners", "Points / compatible unit"], aggregates)}

![Association coverage](association-coverage.png)

The additional constant-bias model substantially increases admitted point counts. Hard polynomial pre-merging still loses coverage relative to fragment matching. This comparison includes different fitted nuisance optima, so it does not uniquely establish that every lost component was a wrong polynomial join. It does establish that hard pre-merging is not a safe replacement in the current pipeline. This iteration has not yet qualified a physical identity false-discovery rate or shown that larger counts are correct.

## Safer identity-guided consolidation

The alternative freezes the unmerged fit's calibration and identity proposals, then considers only equal-NORAD fragments that overlap or are within10seconds. A join must improve the integrated Gaussian constant-bias score and pass all original-fragment residual checks with one shared bias. Different identities, incompatible biases, discontinuous residuals and long gaps remain separate. Failed joins retain both inputs; the component asserts exact observation ownership and zero points dropped. No linear track recalibrates a hardware offset or drift in this step.

{table(["Dataset", "RF arm", "Input candidate fragments", "Consolidated groups", "Retained candidate points", "Points dropped", "Points / group"], consolidations)}

Thus the fitted-c DS22 candidate population retains25,371 points while reducing1,251 candidate fragments to1,132 groups. DSX01 retains3,621 points while reducing194 fragments to166 groups. This is a useful complexity reduction with a coverage-preservation invariant; it does not independently confirm those candidate labels. Identity-guided consolidation is downstream of fragment matching, while hard polynomial pre-merging was upstream. Their compute budgets and resulting units are not identical.

## Actual position error: four unsuccessful cold pilots

The predeclared pilot is DS22-001, the first available recording by capture time. Search starts from nine fixed regional grid points, independent of the supplied GPS. It reassigns satellites and refits scan hardware at every geography; it does not reuse fixed-site satellite identities. Discovery uses at most eight actual time-spread observations per original fragment, retaining measured curvature eligibility from all raw points. It is a discovery subset, not a held-data validation split. The best four discovered locations are reranked with predictions and component statistics recomputed on all3,510 original Graph points and the full160-seed calibration allocation. The geographic score uses the fixed actively-curved component subset; linear fragments do not calibrate hardware.

Both c arms share the same65-geography maximum, same discovery subset, four-seed discovery allocation, component-bias setting, priors and candidate bank. Up to two axial moves per refinement scale are allowed. This bounded surrogate search is neither globally certified nor a proven local optimum. The endpoint is written before the evaluation coordinate is consumed. Coordinate error is in kilometres; it is not inferred from the frequency score.

{table(["Bias sigma Hz", "RF arm", "Discovery geographies", "Full-data finalists", "Estimated latitude", "Estimated longitude", "Error km", "Below0.5km"], position_rows)}

![Position error](position-error.png)

All four endpoints fail the0.5km target by a large margin. The component-bias model's fixed-site frequency-coverage gain does not translate into geographic accuracy. No position error has yet been evaluated for the other67 available DS22 fast recordings or the69 unavailable members in this iteration. The first full-row search exceeded its180-second compute cap in fitted-c; its paired c0 attempt was terminated after that cost failure. Those unsuccessful attempts are preserved in [position_full_row_attempt](position_full_row_attempt), not relabeled as valid endpoints. The compressed-discovery search above is a changed algorithm, followed by full-data scoring.

## What changes next

The goal remains active. Priorities are to move the geographic objective onto the coverage-preserving association/merge path, test physically RF-proportional versus native component biases with explicit gauge assumptions, and check competing identity modes before expanding more position fits. A common unknown site across independently supported static scans could constrain false single-scan modes, while keeping each scan's hardware and timing separate. Neither option is established by the present results. Causal orbital-timing uncertainty and the nominal RF correction also need qualification before claiming sub-kilometre accuracy.

The68 adaptive members and missing fast export remain actual scope gaps. They need an existing-data observation adapter or an explicit evaluation failure, not removal from DS22. The new orbit-state port supports geographic evaluation without recollecting RF or importing either reference repository. Subsequent c-dependent analyses must continue to retain matched c=0 controls and report position errors separately.

## Evidence and reproduction

- [All per-record association summaries](per-case-association.csv), [aggregate table](aggregate-association.csv), [DS22 execution](catalogue/execution.json), [DSX01 execution](dsx01_catalogue/execution.json).
- [DS22 consolidation](consolidated/summary.json), [DSX01 consolidation](dsx01_consolidated/summary.json), and their original-fragment membership files retain every point.
- [Hardware-only position pilots](position_hardware_only), [component-bias position pilots](position_pilot), their fit hashes, full-data finalists and complete search traces remain available.
- `tools/evaluate_ds22_merged_tracks.py` transfers the track policy; `tools/associate_merged_track_catalogue.py` prepares orbits and runs matched associations; `tools/run_merged_catalogue_cohort.py` bounds each recording stage; `tools/consolidate_catalogue_matches.py` performs lossless candidate consolidation; `tools/localize_merged_track_catalogue.py` performs the cold regional pilot.

The component tests cover probe ownership, native aliases, no extrapolation, Doppler sign/carrier scaling, bias0 nesting, shared-bias penalties, retained slope errors, incompatible members, fixed grouping/c populations, lossless consolidation, failed/unavailable member accounting, response-blind time subsets and regional search/error units. No golden fixture changed. The final targeted suite contains41 passing cases including the existing Graph and DSX01 fixed-site guards. Static checks pass on the new sources.

Source snapshots are provenance copies under `code_snapshot`; runtime imports remain the current repository. Frozen TLE exports are copied under `orbit_elements`; matrix caches remain outside the report and are hash-bound by their preparation receipts. Input tracking exports remain the sealed DS22 snapshots. [artifact_manifest.json](artifact_manifest.json) binds this report's files. No production model is promoted and the goal is not marked complete.
"""
    (REPORT / "README.md").write_text(report)
    source_names = [
        "tools/evaluate_ds22_merged_tracks.py",
        "tools/associate_merged_track_catalogue.py",
        "tools/run_merged_catalogue_cohort.py",
        "tools/localize_merged_track_catalogue.py",
        "tools/consolidate_catalogue_matches.py",
        "tools/report_merged_catalogue_evaluation.py",
        "tools/analyze_dsx01_fixed_site.py",
        "tools/evaluate_dsx01_consensus_calibration.py",
        "src/leo/analysis/research/track_catalogue_geometry.py",
        "src/leo/analysis/research/component_frequency_bias.py",
        "src/leo/analysis/research/identified_track_merging.py",
        "tests/analysis/test_ds22_merged_tracks.py",
        "tests/analysis/test_merged_track_catalogue_tool.py",
        "tests/analysis/test_track_catalogue_geometry.py",
        "tests/analysis/test_component_frequency_bias.py",
        "tests/analysis/test_identified_track_merging.py",
        "tests/analysis/test_localize_merged_track_catalogue.py",
        "tests/analysis/test_run_merged_catalogue_cohort.py",
        "tests/analysis/test_graph_tracklets.py",
        "tests/analysis/test_dsx01_fixed_site.py",
    ]
    for name in source_names:
        target = REPORT / "code_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    elements = REPORT / "orbit_elements"
    elements.mkdir(exist_ok=True)
    for folder in ("catalogue", "dsx01_catalogue"):
        execution = json.loads((REPORT / folder / "execution.json").read_text())
        for row in execution:
            if row["status"] == "association_evaluated":
                source = Path(row["bank"]) / "selected.tle"
                shutil.copyfile(source, elements / (row["source_id"] + ".tle"))
    files = {
        str(p.relative_to(REPORT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(REPORT.rglob("*"))
        if p.is_file() and p.name != "artifact_manifest.json"
    }
    (REPORT / "artifact_manifest.json").write_text(json.dumps(files, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                files=len(files),
                association_arms=len(aggregates),
                position_pilots=len(position_rows),
            )
        )
    )


if __name__ == "__main__":
    render()
