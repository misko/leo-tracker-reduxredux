"""Render the bounded fixed-site study and bind its scientific inputs."""
# ruff: noqa: E501

import csv
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import analyze_dsx01_fixed_site as experiment
import matplotlib.pyplot as plt
import numpy as np

ROOT = experiment.ROOT
REPORT = ROOT / "reports/2026_10_17_dsx01_satellite_association"
INPUTS = Path("/tmp/dsx01-fixed-site-20261017-inputs")


def table(headers, rows):
    return "\n".join(
        [
            "| " + " | ".join(map(str, headers)) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        + ["| " + " | ".join(map(str, r)) + " |" for r in rows]
    )


def render():
    tracks, hashes = experiment.load_tracks()
    arms = {
        arm: json.loads((REPORT / arm / "summary.json").read_text()) for arm in ("c0", "fitted_c")
    }
    metrics, calibration, coverage, ages, candidate_rows = [], [], [], [], []
    scores, deletions = [], []
    for sid in ("S01", "S02", "S03", "S04", "S05"):
        receipt = json.loads((INPUTS / sid / "receipt.json").read_text())
        dest = REPORT / "inputs" / sid
        dest.mkdir(parents=True, exist_ok=True)
        for name in ("receipt.json", "selected.tle"):
            shutil.copyfile(INPUTS / sid / name, dest / name)
        provenance = receipt["provenance"]
        assert all(
            p["element_epoch_utc_ns"] <= receipt["origin_utc_ns"]
            and p["collected_utc_ns"] <= receipt["origin_utc_ns"]
            for p in provenance
        )
        age = np.percentile([p["age_s"] / 3600 for p in provenance], [0, 50, 95, 100])
        ages.append(
            [sid, receipt["catalogue_count"], receipt["selected_count"], *[f"{v:.2f}" for v in age]]
        )
        with np.load(INPUTS / sid / "bank.npz") as archive:
            bank = {key: archive[key] for key in archive.files}
        groups, _ = experiment.components(sid, tracks)
        stats = experiment.statistics(groups, bank, receipt["nominal_corrections_hz"])
        shape = np.min(np.where(stats["component_visible"], stats["shape_rms"], np.inf), axis=1)
        coverage.append([sid, len(groups), int(sum(shape < 200)), f"{np.median(shape):.1f}"])
        for arm in arms:
            d = next(d for d in arms[arm] if d["source_id"] == sid)
            beta = np.array(d["beta_native_hz_and_hz_per_150s"])
            best, rms, lifts, _ = experiment.evaluate(stats, beta)
            active = stats["active"]
            weights = np.minimum(stats["count"][active], 50)
            raw = float(sum(weights * np.minimum(rms[active] ** 2, 900.0**2)) / 150.0**2)
            prior = float(sum((beta[4:8] / (150 * d["drift_prior_sigma_hz_s"])) ** 2))
            complexity = len(beta) * np.log(max(float(sum(weights)), 2.0))
            scores.append(
                [
                    sid,
                    arm,
                    f"{raw:.1f}",
                    f"{prior:.1f}",
                    f"{complexity:.1f}",
                    f"{raw + prior + complexity:.1f}",
                ]
            )
            metrics.append(
                [
                    sid,
                    arm,
                    d["components"],
                    d["points"],
                    d["compatible_components"],
                    d["compatible_points"],
                    f"{100 * d['compatible_points'] / d['points']:.2f}%",
                    d["noise_screened_components"],
                    d["noise_screened_points"],
                    d["evidence_screened_components"],
                ]
            )
            ranks = d["calibration_group_ranks"]
            names = ("RX1-low", "RX1-high", "RX2-low", "RX2-high")
            for g, name in enumerate(names):
                support = d["calibration_support"][g]
                calibration.append(
                    [
                        sid,
                        arm,
                        name,
                        f"{beta[g]:.1f}",
                        f"{beta[g + 4] / 150:.3f}",
                        ranks[g],
                        support["qualified_curved_components"],
                        support["drift_bound_active"],
                        support["calibration_screen_pass"],
                    ]
                )
            result = json.loads((REPORT / arm / f"{sid}_results.json").read_text())
            rows = result["components"]
            stronger = [ci for ci, row in enumerate(rows) if row["evidence_screen_pass"]]
            for removed in stronger:
                audit = dict(stats)
                audit["active"] = stats["active"].copy()
                audit["fragment_active"] = stats["fragment_active"].copy()
                audit["active"][removed] = False
                audit["fragment_active"][stats["ci"] == removed] = False
                _, initial = experiment.components(sid, tracks)
                if arm == "fitted_c":
                    initial = np.r_[initial, 0.0]
                alternative, _ = experiment.solve(audit, initial, 160)
                other_best, other_rms, _, _ = experiment.evaluate(stats, alternative)
                for ci in stronger:
                    involved = {experiment.group(t) for t in groups[ci][1]}
                    change = max(
                        abs(
                            float(
                                experiment.PERIOD / 2
                                + alternative[g]
                                - beta[g]
                                + endpoint * (alternative[g + 4] - beta[g + 4])
                            )
                            % experiment.PERIOD
                            - experiment.PERIOD / 2
                        )
                        for g in involved
                        for endpoint in (-1, 1)
                    )
                    deletions.append(
                        [
                            sid,
                            arm,
                            groups[removed][0],
                            groups[ci][0],
                            int(bank["norad"][best[ci]]),
                            int(bank["norad"][other_best[ci]]),
                            bool(best[ci] == other_best[ci]),
                            f"{other_rms[ci]:.1f}",
                            f"{change:.1f}",
                        ]
                    )
            # Export every real native point, including failed components.
            point_rows = []
            for fi, track in enumerate(stats["fragments"]):
                ci = int(stats["ci"][fi])
                sat = int(best[ci])
                g = experiment.group(track)
                t = track["times"]
                q = track["rf_hz"] / experiment.REFERENCE_RF
                indexes = np.searchsorted(bank["time_s"], t)
                alias = int(lifts[fi, sat])
                cal = beta[g] + beta[g + 4] * (t - 150) / 150
                if len(beta) == 9:
                    cal += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
                predicted = q * bank["doppler_0"][sat, indexes]
                residual = track["values"] + alias * experiment.PERIOD - cal - predicted
                residual -= receipt["nominal_corrections_hz"][str(track["channel"])]
                for j in range(len(t)):
                    point_rows.append(
                        dict(
                            source_id=sid,
                            observation_id=track["observation_ids"][j],
                            component=groups[ci][0],
                            original_track=track["key"],
                            receiver=track["receiver"],
                            channel=track["channel"],
                            time_s=float(t[j]),
                            actual_rf_hz=track["rf_hz"],
                            graph_unwrapped_native_hz=float(track["values"][j]),
                            additional_alias=alias,
                            candidate_norad=int(bank["norad"][sat]),
                            calibration_hz=float(cal[j]),
                            predicted_doppler_hz=float(predicted[j]),
                            residual_hz=float(residual[j]),
                            elevation_deg=float(bank["elevation_deg"][sat, indexes[j]]),
                            status=rows[ci]["status"],
                            noise_screen_pass=rows[ci]["noise_screen_pass"],
                            evidence_screen_pass=rows[ci]["evidence_screen_pass"],
                        )
                    )
            assert len(point_rows) == d["points"]
            with (REPORT / arm / f"{sid}_observations.csv").open("w") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(point_rows[0]))
                writer.writeheader()
                writer.writerows(point_rows)
            for row in rows:
                if row["status"] != "unexplained" and row["noise_screen_pass"]:
                    candidate_rows.append(
                        [
                            sid,
                            arm,
                            row["component"],
                            row["candidate_norad"],
                            row["points"],
                            f"{row['rms_hz']:.1f}",
                            row["active_curvature"],
                            row["evidence_screen_pass"],
                        ]
                    )
    controls = []
    for arm in arms:
        for seed in (11, 29, 47):
            ds = json.loads((REPORT / "controls" / f"{arm}_{seed}" / "summary.json").read_text())
            controls.append(
                [
                    arm,
                    seed,
                    *[
                        sum(d[k] for d in ds)
                        for k in (
                            "compatible_components",
                            "compatible_points",
                            "noise_screened_components",
                            "noise_screened_points",
                            "evidence_screened_components",
                        )
                    ],
                ]
            )
    totals = {
        arm: {
            key: sum(d[key] for d in ds)
            for key in (
                "compatible_components",
                "compatible_points",
                "noise_screened_components",
                "noise_screened_points",
                "evidence_screened_components",
            )
        }
        for arm, ds in arms.items()
    }
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    for ax, key, title in zip(
        axes,
        ("compatible_points", "noise_screened_points"),
        (
            "Points passing loose compatibility checks",
            "Points also passing residual structure screen",
        ),
        strict=True,
    ):
        maximum = 0
        for x, arm in enumerate(arms):
            ax.bar(x, totals[arm][key], width=0.45, color=("#267d9c", "#ca7e24")[x], alpha=0.75)
            null = []
            for seed in (11, 29, 47):
                ds = json.loads(
                    (REPORT / "controls" / f"{arm}_{seed}" / "summary.json").read_text()
                )
                null.append(sum(d[key] for d in ds))
            ax.scatter(
                x + np.linspace(-0.13, 0.13, 3),
                null,
                color="black",
                marker="x",
                s=55,
                label="Refitted offset-randomized controls" if x == 0 else None,
            )
            maximum = max(maximum, totals[arm][key], *null)
            ax.text(x, totals[arm][key] + 10, str(totals[arm][key]), ha="center")
        ax.set_xticks([0, 1], ["c = 0", "Fitted c"])
        ax.set_ylim(0, maximum * 1.2 + 10)
        ax.set(title=title, ylabel="GLRT points (18,338 input points)")
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    fig.savefig(REPORT / "real_vs_controls.png", dpi=160)
    plt.close(fig)
    calibration_headers = [
        "Scan",
        "Arm",
        "Path",
        "Offset at 150 s (Hz)",
        "Drift (Hz/s)",
        "Data rank",
        "Qualified curved components",
        "At drift bound",
        "Calibration screen",
    ]
    with (REPORT / "calibration_paths.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(calibration_headers)
        writer.writerows(calibration)
    source_bindings = dict(hashes)
    for path in [
        ROOT / "tools/analyze_dsx01_fixed_site.py",
        ROOT / "tools/render_dsx01_satellite_report.py",
        ROOT / "tests/analysis/test_dsx01_fixed_site.py",
        experiment.SOURCES,
        *sorted(experiment.BASE.glob("S*/trimmed/results.json")),
    ]:
        source_bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    experiment.write_json(
        REPORT / "analysis_receipt.json",
        dict(
            source_sha256=source_bindings,
            totals=totals,
            controlled_ablation="same points, candidates, priors and seed budget",
            scope="fixed supplied GPS; no position estimate or localization accuracy comparison",
            numpy_version=np.__version__,
            learned_c_comparison=True,
            observations_withheld=0,
        ),
    )
    report = f"""# DSX01: fixed-site satellite association investigation

Fixed ground truth: **37.849061591561885, -122.48574968092912**. Latitude and longitude are never fitted. WGS84 ellipsoidal height is assumed 0 m because measured altitude is unavailable. This is a bounded existing-recording experiment, with no new RF collection.

The previous [four-variant report is published on main](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_17_dsx01_consensus_calibration/README.md), commit `329e8a0c7276d112641d610937ec363e83ebfeb8`.

**Result: the present shared-calibration prototype does not establish confident satellite identities.** Its candidate counts are small, residual structure removes more matches, and independent component frequency translations also produce apparent matches. No claim of physical satellite identification or improved localization follows from these fits. A bounded local search is not a certificate that a better joint assignment does not exist.

The inputs are all **456 trimmed least-squares components**, containing **676 original Graph fragments / 18,338 GLRT points**, from 20,084 total GLRT detections. The 1,746 points outside the Graph components are outside this experiment. Component membership is fixed. A component receives one candidate NORAD; failed components are not silently split. The trimmed-LS calibration initializes the search; its coefficients are reestimated rather than imposed as hard constraints. All points are fitted; none are withheld in the primary fit.

## Hardware model: separate paths, small drifts, and per-scan shifts

For observation i in original fragment j, component h, scan s, receiver r and band b:

```text
y_i + k_j * P = Doppler(NORAD_h, true_position, exact_UTC_i, actual_RF_i)
                + a[s,r,b] + d[s,r,b] * (time_i - 150 seconds)
                + c[s] * (actual_RF_i - 11.5 GHz)
                + known_nominal_tuner_correction_i + residual_i
P = 227272.7272727 Hz, k_j integer in native Hz
```

Each scan has four offset parameters and four drift parameters: **RX1-low, RX1-high, RX2-low, RX2-high**. Consequently the model includes both cross-band offsets and cross-receiver offsets, and allows the band difference to differ between receivers. The main arm uses a zero-centered Gaussian drift preference with sigma **2 Hz/s**, and a hard limit **±5 Hz/s**. These are declared small-drift hypotheses, not measured hardware specifications. The offsets are constant within each scan; they are not shared across DSX01. All recorded nominal tuner corrections were zero. The recorded RF/LNB mapping remains a hypothesis.

The ninth parameter is an optional shared RF-dependent coefficient c, with c=0 versus fitted-c arms. It is dimensionless when RF is in Hz. This is a frequency-fit ablation at a fixed known position; it is not a localization experiment. Candidate sets, observations, drift priors, gates and maximum discovery-seed budget are matched. No per-track continuous offset or slope is available in the physical fit. Aliases are profiled separately for each original fragment, before RF scaling.

Only fragments with **measured active curvature** calibrate hardware: at least 20 seconds span and at least 250 Hz RMS departure from their best affine fit. Linear fragments cannot calibrate even when another fragment in their merged component is curved. This is a heuristic curvature screen, not a proof of distinct identity. Linear fragments can be evaluated with the resulting calibration.

The four offset contrasts obey a cycle: RX2-low minus RX1-low; RX2-high minus RX1-high; RX1-high minus RX1-low; RX2-high minus RX2-low. Only three contrasts are independent. Their native-Hz differences have integer-alias alternatives; wrapped differences alone are not unique physical LO measurements. Full path coefficients and support flags are in [calibration_paths.csv](calibration_paths.csv). Unsupported paths must not be interpreted as measured calibration.

## Causal Space-Track orbit evidence

For each NORAD we select the newest eligible element epoch, using only Space-Track archive snapshots collected by scan start, with both epoch and collection in the preceding 48 hours. Repeated identical payloads are deduplicated with the latest eligible collection tie-break. No future collection, nearest-future snapshot, or previous association labels enter the candidate selection. Requiring a past element epoch is an additional conservative rule: availability and epoch are distinct quantities. [Space-Track documents GP and historical GP separately](https://www.space-track.org/documentation).

SGP4 is evaluated at the actual GLRT timestamps. TEME to ECEF uses UTC as an approximation to UT1 and neglects polar motion; the observer is stationary. Doppler sign is positive for an approaching satellite. [Vallado et al.](https://celestrak.org/publications/AIAA/2006-6753/) provide the SGP4 reference and verification work. A broad coarse horizon guard selects candidates; final component membership requires the candidate above the geometric horizon at every observation. Antenna beam poses are not sufficiently measured to impose a narrow angular gate.

{table(["Scan", "Causal Starlinks", "Broad sky bank", "Min TLE age (h)", "Median (h)", "95th percentile (h)", "Max (h)"], ages)}

Selected element sets and per-NORAD epoch/collection/digest provenance are frozen under [inputs](inputs). Orbit matrices are local reproducible caches at `/tmp/dsx01-fixed-site-20261017-inputs`; they are not the primary orbit authority. Across these banks, ±100 m height changes reference-frequency Doppler by at most about 37.3 Hz. This is a geometric sensitivity calculation with fixed labels and calibration, not a complete refit or an altitude estimate.

## Results and interpretation

Loose compatibility requires per-fragment RMS ≤450 Hz, absolute mean ≤150 Hz, fitted trend excursion ≤300 Hz, half-to-half mean difference ≤300 Hz, and maximum absolute residual ≤1500 Hz. A separated candidate additionally has runner-up RMS at least max(600 Hz, twice the best RMS), conditional on the chosen calibration.

The stricter residual screen checks zero mean and slope at a 3-sigma heuristic threshold; a quadratic alternative must not improve BIC by more than 10; maximum split-mean z must be ≤4; lag-one correlation must be ≤4/sqrt(n) in magnitude. A 75-Hz noise floor avoids overstating precision. These diagnostics do not prove white noise, and their joint false-positive rate is not calibrated.

A further calibration evidence screen requires each participating hardware path to have at least three separated, noise-screened curved components, at least two candidate NORADs, ≥30 s time coverage, and no active drift bound. Even passing this screen would still require stability and independent validation before claiming identity.

{table(["Scan", "Arm", "Components", "Input points", "Compatible components", "Compatible points", "% of input points", "Also noise-screened components", "Also noise-screened points", "Full evidence-screened components"], metrics)}

![Real data versus refitted controls](real_vs_controls.png)

For denominator clarity, compatible points are measured against the 18,338 input component points in the table; dividing by 20,084 instead includes the unresolved Graph detections. These candidate counts are not confirmed satellite associations.

**Curvature alone is permissive.** The following diagnostic removes a separate continuous affine term from each fragment, solely to measure a shape-fit lower bound. It is explicitly not the accepted association model:

{table(["Scan", "Components", "Best shape-only RMS <200 Hz", "Median best shape-only RMS (Hz)"], coverage)}

Thus many curves look satellite-like when arbitrary affine freedom is allowed. Their failure under the shared hardware model can reflect incorrect component joins, unmodeled signal bias, or a missed joint optimum. It does not establish that their emitters are absent from the catalogue.

## Controlled c ablation and calibration diagnostics

The research score below is a capped squared frequency error over curved components, with each component capped at 50 point-votes, divided by 150-Hz noise variance; a drift-prior penalty and k log(N) parameter penalty are shown separately. Capping residual RMS at 900 Hz creates a clutter option. This is a descriptive penalized score, not a likelihood-calibrated posterior or formal BIC for a mixture. N is the capped curved-component vote count; k is 8 or 9. A better value is a better in-sample frequency fit only.

{table(["Scan", "Arm", "Capped frequency score", "Drift prior", "Parameter penalty", "Total"], scores)}

{table(calibration_headers, calibration)}

Many paths either hit their drift bound or lack qualified curved support. The numerical offsets above are candidate-mode coefficients, not trustworthy independent LNB calibration measurements. In particular, apparent regression rank does not establish that the participating tracks have the correct satellite identities.

## Refitted frequency-coherence controls

Each control adds an independent uniform reference-frequency offset in [-P/2,P/2] to every component, scaling by actual_RF/11.5GHz in each member fragment. Times, measured curvature, membership, RF, sky candidates and noise are retained. Both satellite assignment and hardware calibration are rerun with the same budget. This specifically tests shared frequency-calibration coherence conditional on the upstream components. Because real Doppler curvature survives the transformation, it is not a satellite-absent null and cannot estimate physical identity FDR. Three replay seeds are insufficient for a calibrated probability in any event.

{table(["Arm", "Seed", "Compatible components", "Compatible points", "Also noise-screened components", "Also noise-screened points", "Full evidence-screened components"], controls)}

Loose candidate point totals overlap the controls. The stricter residual and calibration screens are more informative: compare those counts directly in the tables. A real-data advantage on only three conditional replays is exploratory evidence, not a calibrated identity probability. A small residual and a distant runner-up within one selected calibration mode are insufficient to authorize identities.

## Whole-component deletion stability

For components passing the full evidence screen, remove each such component from hardware calibration in turn and rerun the complete bounded candidate/calibration search. All other components, candidates, priors and budgets remain fixed; every original point remains available for subsequent evaluation. Removing an already-linear component is a negative control because it had no calibration vote. These are post-fit sensitivity audits; the primary fit above uses all observations.

{table(["Scan", "Arm", "Removed from calibration", "Evaluated component", "Primary NORAD", "Refitted NORAD", "Same NORAD", "Refitted RMS (Hz)", "Max path calibration change at scan endpoints (Hz)"], deletions)}

This audit tests reliance on individual anchors and competing calibration modes. Even a stable candidate is not independently authenticated. Failure should prevent promotion of a candidate despite its primary-fit residual score.

## Proposed next analysis

The strongest next model is a **joint, alias-aware factor graph with shared hardware calibration and a penalized satellite/channel bias hierarchy**. Keep GPS fixed and preserve an unmatched/clutter state. Use curved tracks to discover candidate identities and constrain hardware; then admit linear tracks only against independently supported calibration. Score whole components from the native measurements, including every member RX/channel.

1. Build candidate lists with curvature and physically possible Doppler slopes, retaining alternatives. Improve initialization using consensus votes over shared offset/drift modes rather than relying on one curved component at a time. The current bounded multistart fit is a prototype, not an exhaustive combinatorial search.
2. Keep four receiver/band offsets and four small drifts per scan, with explicit priors and alias branches. Carry forward independently supported trimmed-LS relative-calibration contrasts and their uncertainty, retaining alternative alias modes rather than imposing one absolute calibration. Contrast priors are a proposed next arm; the present prototype uses initialization only. Fit a common scan timing correction only within the recorded clock uncertainty, if tested. Do not give individual tracks a free time shift or geographic position.
3. Compare the present hardware-only model with a sparse, shrinkage-regularized constant bias for an independently supported satellite/channel family, shared across RX observations. Charge a parameter/group penalty, fix the global hardware/transmitter gauge, and require rank and deletion stability. A new bias per short component would restore the original ambiguity and should not count as identification. Add slopes or change points only when their cost is supported by repeatable evidence.
4. Compare c=0 and fitted-c with identical observations, candidate sets, priors and budgets in every new bias arm. Report raw residual changes, complexity penalties and identifiable parameter combinations separately. Do not infer position accuracy at a position fixed to truth.
5. Require separation from competing NORADs across credible shared-calibration modes, stability when curved anchors are removed, residual mean/trend/step/curvature checks, and refitted controls. Audit a failed merged component by its original fragments without silently changing the primary population. Report compatible, ambiguous and unconfirmed results separately.

There is a physical reason to test a signal-bias hierarchy: Saroufim, Hayek and Kassas report channel-dependent CFO behavior, including bias and sawtooth corrections and synchronized channel groups, in their peer-reviewed [Mind the Beam (ION GNSS+ 2026) abstract](https://www.ion.org/publications/abstract.cfm?articleID=20898). This supports an extension hypothesis; it does not establish that such corrections cause the DSX01 failures. The full paper was not available in this review.

## Candidate audit and visualizations

The following candidates pass the loose and residual screens. They still need the calibration evidence screen and independent identity validation:

{table(["Scan", "Arm", "Component", "Candidate NORAD", "Points", "RMS (Hz)", "Component has active curvature", "Full evidence screen"], candidate_rows)}

Each per-scan figure shows corrected measured GLRT points with candidate SGP4 curves, unexplained points under the same selected calibration, and native-Hz residuals. Colors can repeat; candidate NORAD labels and all residual diagnostics are authoritative in the adjacent CSV/JSON. All native observations, including unexplained components, are exported as `Sxx_observations.csv` in each real arm. IDs in those files are hypotheses, including for unexplained rows.

"""
    for sid in ("S01", "S02", "S03", "S04", "S05"):
        for arm in arms:
            report += f"\n**{sid}, {arm}** — [components]({arm}/{sid}_components.csv), [native observations]({arm}/{sid}_observations.csv), [receipt and results]({arm}/{sid}_results.json)\n\n![{sid} {arm}]({arm}/{sid}_candidates.png)\n"
    report += """
## Reproduction and checks

The implementation is `tools/analyze_dsx01_fixed_site.py`; report generation is `tools/render_dsx01_satellite_report.py`. Preparation uses public read-only archive/storage ports, not reference repositories or private storage-path construction. A locally readable frozen bank can be used without privileged storage access.

```bash
sudo -n -u leo .venv/bin/python tools/analyze_dsx01_fixed_site.py prepare --output /tmp/dsx01-fixed-site-20261017-inputs-NEW
OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/analyze_dsx01_fixed_site.py run --inputs /tmp/dsx01-fixed-site-20261017-inputs-NEW --output /tmp/dsx01-c0-NEW --seed-budget 160
OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/analyze_dsx01_fixed_site.py run --inputs /tmp/dsx01-fixed-site-20261017-inputs-NEW --output /tmp/dsx01-c-NEW --seed-budget 160 --fit-rf-c
.venv/bin/python -m pytest -q tests/analysis/test_dsx01_fixed_site.py tests/operations/test_causal_tle_catalogue.py
```

Controls add `--null-seed 11`, `29` or `47`. The small-drift hypotheses can be changed explicitly with `--drift-bound-hz-s` and `--drift-sigma-hz-s`. All present cases use a maximum budget of 160 generated discovery seeds plus the initial calibration; fewer seeds can pass the physical eligibility gates. Current numerical tests cover native alias scaling, shared RF-coefficient identifiability, zero free track intercepts, linear-fragment exclusion even within curved components, drift prior/bound enforcement, component-level NORAD consistency, visibility and structured-residual rejection. Causal-catalogue tests exclude future collection and future element epochs. No golden fixtures were changed.

[analysis_receipt.json](analysis_receipt.json) binds source inputs and implementation. [artifact_manifest.json](artifact_manifest.json) binds the report artifacts. The large orbit-bank arrays are caches outside the report, with hashes in each preparation receipt. The selected TLE and original point timestamps suffice to regenerate the geometry; preparation can also be replayed against the read-only local archive.
"""
    (REPORT / "README.md").write_text(report)
    files = {
        str(p.relative_to(REPORT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(REPORT.rglob("*"))
        if p.is_file() and p.name != "artifact_manifest.json"
    }
    experiment.write_json(REPORT / "artifact_manifest.json", files)
    print(json.dumps(dict(totals=totals, artifacts=len(files))))


if __name__ == "__main__":
    render()
