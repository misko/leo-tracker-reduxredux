"""Full sealed-membership DS22 coverage plus physical-model diagnostics."""
# ruff: noqa: E501

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from report_merged_catalogue_evaluation import table

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "reports/2026_10_17_ds22_merged_satellites"
REPORT = ROOT / "reports/2026_10_17_ds22_physical_model_revision"


def collect():
    entries = []
    for cohort, catalogue, consolidated, kind in (
        (OLD / "cohort", OLD / "catalogue", OLD / "consolidated", "fast"),
        (
            REPORT / "adaptive_tracks",
            REPORT / "adaptive_catalogue",
            REPORT / "adaptive_consolidated",
            "adaptive",
        ),
        (
            REPORT / "fast_sealed",
            REPORT / "fast_sealed_catalogue",
            REPORT / "fast_sealed_consolidated",
            "fast sealed prefix",
        ),
    ):
        folders = sorted(cohort.glob("DS22-*/receipt.json"))
        consolidation = json.loads((consolidated / "summary.json").read_text())
        for p in folders:
            row = json.loads(p.read_text())
            sid = row["source_id"]
            entries.append(
                dict(
                    source_id=sid,
                    kind=kind,
                    recording_path=str(p.parent.relative_to(ROOT)),
                    catalogue_path=str((catalogue / sid).relative_to(ROOT)),
                    consolidated_path=str((consolidated / sid).relative_to(ROOT)),
                    receipt_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                    counts={
                        k: row[k]
                        for k in ("winning_points", "graph_points", "graph_tracks", "merged_tracks")
                    },
                    consolidations=[x for x in consolidation if x["source_id"] == sid],
                )
            )
    entries.sort(key=lambda e: e["source_id"])
    if len(entries) != 137 or len({e["source_id"] for e in entries}) != 137:
        raise ValueError("full original 137-member denominator required")
    return entries


def render():
    entries = collect()
    (REPORT / "cohort.json").write_text(json.dumps(entries, indent=2) + "\n")
    totals, per_case = defaultdict(Counter), []
    for entry in entries:
        for sigma in (0, 1000):
            document = json.loads(
                (ROOT / entry["catalogue_path"] / f"bias_{sigma}/summary.json").read_text()
            )
            if len(document) != 4:
                raise ValueError("every member needs all eight controlled arms")
            for row in document:
                if row["graph_points"] != entry["counts"]["graph_points"]:
                    raise ValueError("changed association point population")
                key = (entry["kind"].split()[0], sigma, row["grouped"], row["fitted_c"])
                for bucket in (key, ("all", *key[1:])):
                    totals[bucket].update(
                        {
                            k: row[k]
                            for k in (
                                "components",
                                "compatible_components",
                                "compatible_points",
                                "graph_points",
                            )
                        }
                    )
                    totals[bucket]["cases"] += 1
                per_case.append(dict(row, kind=entry["kind"]))
    denominator = sum(e["counts"]["winning_points"] for e in entries)
    track_table = []
    for kind in ("fast", "adaptive", "all"):
        selected = [e for e in entries if kind == "all" or e["kind"].startswith(kind)]
        count = {k: sum(e["counts"][k] for e in selected) for k in entries[0]["counts"]}
        track_table.append(
            [
                kind,
                len(selected),
                count["winning_points"],
                count["graph_points"],
                f"{100 * count['graph_points'] / count['winning_points']:.2f}%",
                count["graph_tracks"],
                count["merged_tracks"],
                f"{count['graph_points'] / count['graph_tracks']:.2f}",
            ]
        )
    association_table = []
    for (kind, sigma, merged, c), count in sorted(totals.items()):
        selected_denominator = sum(
            e["counts"]["winning_points"]
            for e in entries
            if kind == "all" or e["kind"].startswith(kind)
        )
        association_table.append(
            [
                kind,
                sigma,
                "hard merged" if merged else "fragments",
                "fitted c" if c else "c=0",
                count["cases"],
                count["compatible_components"],
                count["compatible_points"],
                f"{100 * count['compatible_points'] / selected_denominator:.2f}%",
                f"{count['compatible_points'] / max(1, count['compatible_components']):.2f}",
            ]
        )
    with (REPORT / "association.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "dataset",
                "bias_sigma_hz",
                "grouping",
                "rf_arm",
                "cases",
                "components",
                "points",
                "winning_point_percent",
                "points_per_component",
            ]
        )
        writer.writerows(association_table)
    with (REPORT / "per-case-association.csv").open("w") as stream:
        fields = sorted(set().union(*(row.keys() for row in per_case)))
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(per_case)
    consolidated_table = []
    for c in (False, True):
        rows = [r for e in entries for r in e["consolidations"] if r["fitted_c"] == c]
        if len(rows) != 137 or sum(r["points_dropped"] for r in rows):
            raise ValueError("incomplete or lossy consolidation")
        counts = {k: sum(r[k] for r in rows) for k in ("input_tracks", "output_tracks", "points")}
        expected = totals["all", 1000, False, c]["compatible_points"]
        if counts["points"] != expected:
            raise ValueError("consolidation changed admitted points")
        consolidated_table.append(
            [
                "fitted c" if c else "c=0",
                counts["input_tracks"],
                counts["output_tracks"],
                counts["points"],
                f"{100 * counts['points'] / denominator:.2f}%",
                f"{counts['points'] / max(1, counts['output_tracks']):.2f}",
            ]
        )
    plt.rcParams.update({"font.size": 10})
    fig, axes = plt.subplots(2, 1, figsize=(15, 7), sharex=True)
    index = np.arange(1, 138)
    fast = [e["kind"].startswith("fast") for e in entries]
    axes[0].scatter(
        index,
        [100 * e["counts"]["graph_points"] / e["counts"]["winning_points"] for e in entries],
        c=["#2878b5" if f else "#8a4cb5" for f in fast],
        s=16,
    )
    axes[0].set_ylabel("Graph / gated GLRT points (%)")
    axes[0].scatter([], [], c="#2878b5", s=16, label="Fast")
    axes[0].scatter([], [], c="#8a4cb5", s=16, label="Adaptive")
    axes[0].legend()
    for c, color in ((False, "#2878b5"), (True, "#d95319")):
        values = []
        for e in entries:
            value = next(r for r in e["consolidations"] if r["fitted_c"] == c)["points"]
            values.append(100 * value / e["counts"]["winning_points"])
        axes[1].plot(index, values, ".", color=color, label="fitted c" if c else "c=0")
    axes[1].set_ylabel("Satellite-compatible / gated GLRT (%)")
    axes[1].set_xlabel(
        "Original DS22 member ordinal; final fast entry uses its sealed 2,048 windows"
    )
    axes[1].legend()
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle(
        "All 137 original DS22 entries · original fast products plus newly frozen adaptive analysis"
    )
    fig.tight_layout()
    fig.savefig(REPORT / "full-corpus-coverage.png", dpi=150)
    plt.close(fig)
    diagnostic_rows = []
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for number, path in enumerate(sorted((REPORT / "diagnosis").glob("*/results.json"))):
        data = json.loads(path.read_text())
        if len(data) != 24:
            raise ValueError("incomplete physical-model experiment")
        for j, family in enumerate(("native", "rf_scaled")):
            ax = axes[number, j]
            for site, color in (
                ("supplied_evaluation_site", "#2878b5"),
                ("previous_blind_endpoint", "#d95319"),
            ):
                for c in (False, True):
                    rows = sorted(
                        [
                            r
                            for r in data
                            if r["family"] == family and r["site"] == site and r["fitted_c"] == c
                        ],
                        key=lambda r: r["utc_shift_s"],
                    )
                    ax.plot(
                        [r["utc_shift_s"] for r in rows],
                        [r["score"] / 1e6 for r in rows],
                        "o--" if c else "o-",
                        color=color,
                        label=("supplied site" if site.startswith("supplied") else "blind endpoint")
                        + (" fitted c" if c else " c=0"),
                    )
                    best = min(rows, key=lambda r: r["score"])
                    diagnostic_rows.append(
                        [
                            path.parent.name,
                            family,
                            "fitted c" if c else "c=0",
                            site,
                            f"{best['utc_shift_s']:.6f}",
                            f"{best['score']:.0f}",
                        ]
                    )
            ax.set_title(path.parent.name + " · " + family)
            ax.set_xlabel("Common UTC shift within declared bracket (s)")
            ax.set_ylabel("Penalized frequency score / 1e6")
            ax.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle(
        "Diagnostic only · improved fit does not remove preference for the wrong geographic endpoint"
    )
    fig.tight_layout()
    fig.savefig(REPORT / "physical-model-diagnosis.png", dpi=150)
    plt.close(fig)
    position_rows = []
    for path in sorted((REPORT / "position_pilots").glob("*/*/evaluation.json")):
        evaluation = json.loads(path.read_text())
        fit = json.loads(path.with_name("fit.json").read_text())
        if (
            hashlib.sha256(path.with_name("fit.json").read_bytes()).hexdigest()
            != evaluation["fit_sha256"]
        ):
            raise ValueError("frozen position fit changed")
        position_rows.append(
            [
                path.parent.parent.name,
                "fitted c" if fit["fitted_c"] else "c=0",
                f"{evaluation['position_error_km']:.3f}",
                fit["points"],
                fit["evaluations"],
            ]
        )
    if len(position_rows) != 4:
        raise ValueError("both preselected adaptive pilots require both c arms")
    orbit_rows = []
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for path in sorted((REPORT / "orbit_disagreement").glob("*/results.json")):
        case = path.parent.name
        data = [r for r in json.loads(path.read_text()) if r["status"] == "compared"]
        catalogue_folder = "dsx01_catalogue" if case.startswith("DSX") else "catalogue"
        matches = json.loads(
            (OLD / catalogue_folder / case / "bias_1000/fragments_c0.json").read_text()
        )
        admitted = {r["candidate_norad"] for r in matches["components"] if r["compatible"]}
        for label, selected in (
            ("all compared candidates", data),
            ("admitted candidate NORADs", [r for r in data if r["norad"] in admitted]),
        ):
            position = [r["median_position_difference_km"] for r in selected]
            shape = [r["frequency_difference_affine_removed_rms_hz"] for r in selected]
            orbit_rows.append(
                [
                    case,
                    label,
                    len(selected),
                    f"{np.median(position):.3f}",
                    f"{np.percentile(position, 90):.3f}",
                    f"{np.median(shape):.1f}",
                    f"{np.percentile(shape, 90):.1f}",
                ]
            )
            if label.startswith("all"):
                for ax, values in zip(axes, (position, shape), strict=True):
                    values = np.sort(values)
                    ax.plot(values, np.arange(1, len(values) + 1) / len(values), label=case)
    for ax in axes:
        ax.set_xscale("log")
        ax.set_ylabel("Fraction of compared causal candidates")
        ax.grid(alpha=0.2)
        ax.legend()
    axes[0].set_xlabel("Median latest-vs-previous position difference (km)")
    axes[1].set_xlabel("Doppler difference after affine removal (Hz RMS)")
    fig.suptitle("Successive causal TLE prediction disagreement · neither TLE is independent truth")
    fig.tight_layout()
    fig.savefig(REPORT / "causal-orbit-disagreement.png", dpi=150)
    plt.close(fig)
    text = """# DS22 full-membership association and physical-model investigation

All 137 original DS22 entries now have Graph tracks and eight matched fixed-site
association arms. The former gap of 68 adaptive inputs has been closed using
existing public-port products, with no RF collection or GLRT re-analysis.
Satellite identities remain frequency-compatible candidates, not verified IDs.
The sub-0.5-km geographic requirement remains unachieved.

## Membership and timing authority

The 68 adaptive exports bind the exact raw-capture manifest digests in the
original sealed DS22 dataset, with identical UTC origins. Their device sample
counters retain gaps and within-visit probe offsets. Their actual sample rate
is 10 MS/s; no rate was inferred from the older fast-scan format. Graph fitting
separates receiver/channel/actual RF lanes. One maximum-margin gate-passing
fractional peak is retained per physical probe; no observations are held out.

DS22-137 was only four completed raw segments (2,048 windows) in the original
seal. The later finished capture has fourteen segments. The four original
segment digests match its prefix exactly; all 32 original index chunks were
hash-verified. Only probes within those exact original device-counter windows
enter the main comparison. The resulting 2,094 processed receiver probes yield
948 gated winners and 861 Graph points. The longer completed capture remains
under `fast_recovered*` as an explicitly excluded extension; its points do not
enter any full-corpus total below. Earlier sealed reports remain unchanged.

## Track construction

The same frozen Graph/trimmed policy is used across capture formats. Detector
rate, RF/channel coverage and available probe density differ, so these totals
are not a controlled detector or cross-format performance comparison.

"""
    text += table(
        [
            "Format",
            "Entries",
            "Gated winners",
            "Graph points",
            "Graph %",
            "Graph tracks",
            "Hard merged",
            "GLRT points/Graph track",
        ],
        track_table,
    )
    text += "\n\n![Full-corpus coverage](full-corpus-coverage.png)\n\n## Fixed-site satellite compatibility\n\nThe supplied site is 37.849061591561885, -122.48574968092912 (assumed ellipsoidal height 0 m). Latest eligible causal Space-Track elements are chosen before each scan; neither future epochs nor future collection times enter. Candidates use the same broad regional prior in each arm. Every scan retains four receiver/band offsets and four small linear drifts (sigma 2 Hz/s, bounds ±5 Hz/s here). Only measured-curved fragments calibrate; linear tracks can be associated afterward. Groups absent from a capture are not measured calibration.\n\n"
    text += "Each c=0/fitted-c pair holds original points, candidates, priors and budgets matched. A 1,000-Hz component-bias prior is a carrier-offset hypothesis; no free component slope is fitted. Admission still requires RMS ≤450 Hz, residual-structure checks and bounded bias. Percentages use all gated original winning GLRT points, not just Graph points. No independent identity accuracy is available.\n\n"
    text += table(
        [
            "Format",
            "Bias sigma Hz",
            "Grouping",
            "RF arm",
            "Entries",
            "Compatible groups",
            "Points",
            "GLRT %",
            "Points/group",
        ],
        association_table,
    )
    text += "\n\n## Lossless candidate-guided consolidation\n\nHard pre-merging can lose compatible points. This alternative begins from admitted original fragments and only joins compatible same-NORAD candidates with shared calibration, one constant component bias and residual checks. Failed joins retain both fragments. Every admitted point and candidate identity is preserved.\n\n"
    text += table(
        ["RF arm", "Input fragments", "Output groups", "Points retained", "GLRT %", "Points/group"],
        consolidated_table,
    )
    text += "\n\n## Carrier-bias and UTC diagnostics\n\nA new RF-proportional carrier-bias hypothesis contributes `(RF/11.5 GHz)*b` with a zero-mean Gaussian prior of 1,000 Hz at the reference. This prior imposes a hardware/carrier gauge; it is not independent calibration evidence. Unit tests compare its marginal Gaussian quadratic and determinant against a dense covariance calculation. Native alias spacing and the zero-bias nested model are preserved.\n\n"
    text += "Both bias families were scored at the supplied site and previously sealed blind endpoints, with UTC shifts at the midpoint and the two declared bracket ends. Both c arms use identical observations, candidates, priors and budgets. These are diagnosis locations only and cannot seed the next blind search. Across both cases, improved frequency fit still leaves the wrong endpoint preferable. Merely changing native bias to RF-proportional bias, or profiling the allowed UTC bracket, does not solve the geographic error. An additional frozen-calibration saturation diagnostic from 150 to 900 Hz also retains the wrong-site preference.\n\n![Physical-model diagnostic](physical-model-diagnosis.png)\n\n"
    text += table(
        [
            "Case",
            "Carrier-bias model",
            "RF arm",
            "Fixed scoring site",
            "Best sampled UTC shift s",
            "Penalized frequency score",
        ],
        diagnostic_rows,
    )
    text += "\n\nA recent experimental study reports channel-dependent Doppler biases and CFO correction behavior, including synchronized channel clusters: [Saroufim, Hayek and Kassas, Mind the Beam (ION GNSS+ 2026)](https://www.ion.org/publications/abstract.cfm?articleID=20898). This motivates checking transmitter behavior; it does not establish which mechanism affects our recordings.\n\n## Blind adaptive position pilots\n\nThe pilots were preselected without geographic error: DS22-002 is the first adaptive entry; DS22-058 has the most points in individually measured-curved Graph fragments (ranking retained). The unchanged uniform 81-point regional grid, three basins and eight full-budget finalists use all original Graph points. The evaluation GPS is supplied only after each fit is frozen. These are bounded pilot searches, not a complete 137-recording position evaluation or proven global optima.\n\n"
    text += table(
        [
            "Recording",
            "RF arm",
            "Position error km",
            "Original Graph points",
            "Geographic evaluations",
        ],
        position_rows,
    )
    text += "\n\n## Causal orbital sensitivity\n\nThe latest selected TLE was compared with the newest available **distinct older epoch** collected before the same causal cutoff, within the same 48-hour archive window. No future element, observation or candidate set was introduced. Both predictions were propagated at 13 times over 300 seconds. Doppler disagreement is evaluated at the original broad regional center (37.5, -122), with the best affine difference removed to expose shape changes.\n\n"
    text += table(
        [
            "Case",
            "Subset",
            "NORADs",
            "Position median km",
            "Position p90 km",
            "Shape median Hz",
            "Shape p90 Hz",
        ],
        orbit_rows,
    )
    text += "\n\n![Causal orbit disagreement](causal-orbit-disagreement.png)\n\nThese differences are substantial, including for NORADs admitted by the fixed-site frequency model. They demonstrate sensitivity to the orbital input, not the true error of the latest TLE or proof of an association. Objects without a previous distinct causal epoch are absent only from this diagnostic; they remain in association candidate sets. The earlier candidate IDs are not independent identity labels. The current experiments still use the latest causal TLE without orbital correction.\n\n"
    text += "A new pure geometry port separates satellite orbital-phase perturbations from receiver UTC shifts: states at `t+delta` are rotated back to Earth orientation at observation time `t`. The zero-phase model exactly nests existing geometry. This is preparation for a physically constrained, per-NORAD shared correction experiment; no corrected position solution is claimed here. Future corrections must be shared across all assigned tracks of a satellite, retain priors and complexity costs, and be evaluated with matched c arms and blind geographic initialization.\n\n"
    text += "No pilot meets 0.5 km. Improved frequency fit, merged-group counts and a completed corpus pass are not evidence of geographic success. `cohort.json` maps every original entry to its frozen observations, association artifacts and consolidation; machine-readable comparisons, all controlled failures/extensions and the active checkpoint accompany this report.\n"
    (REPORT / "README.md").write_text(text)
    summary = dict(
        members=137,
        association_arms=137 * 8,
        independent_identity_truth=False,
        points={k: sum(e["counts"][k] for e in entries) for k in entries[0]["counts"]},
        consolidated=consolidated_table,
        position_pilots=position_rows,
        goal_complete=False,
    )
    (REPORT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    render()
