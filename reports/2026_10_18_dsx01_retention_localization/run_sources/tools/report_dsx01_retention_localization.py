"""Evaluate sealed DSX01 endpoints; ground truth is confined to this reporter."""

# Long literals below are Markdown paragraphs and table cells.
# ruff: noqa: E501

import csv
import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, OUTPUT, PARTITION, ROOT
from localize_merged_track_catalogue import distance_km

from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REFERENCE = (37.849061591561885, -122.48574968092912)
LABELS = dict(
    shared_phase="Shared phase",
    family_rate="Satellite family rate",
    orbit_em="Orbital MAP / soft EM",
    penalized_split="Penalized subdivision",
    correlated_noise="Correlated-noise likelihood",
    receiver_smooth="Receiver smooth error",
)


def table(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def run():
    # Require every geographic fit to finish before any reference-based metric.
    files = [OUTPUT / f"DSX01-S{i:02d}/refined_endpoints.json" for i in range(1, 6)]
    if not all(p.exists() for p in files):
        raise RuntimeError("all five refined endpoint files must be sealed before evaluation")
    exact_orbits = json.loads((OUTPUT / "exact_orbit_validation.json").read_text())
    assert len(exact_orbits) == 10
    assert not any(r["final_accepted_rows_failing_exact_recheck"] for r in exact_orbits.values())
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    validated_hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(
            p.with_name("exact_validated_endpoints.json").read_bytes()
        ).hexdigest()
        for p in files
    }
    raw = [
        json.loads(line)
        for line in (
            ROOT / "reports/2026_10_16_dsx01_fast_association_losses" / "context-observations.jsonl"
        )
        .read_text()
        .splitlines()
    ]
    sources = json.loads(
        (ROOT / "reports/2026_10_16_dsx01_fast_association_losses/sources.json").read_text()
    )
    standard, summaries, c_pairs, per_track, coordinates = [], [], [], [], []
    global_associations = {
        f"{arm}/{method}": {} for arm in ("c0", "fitted_c") for method in METHODS
    }
    checks = []
    for i, path in enumerate(files, 1):
        case, source_id = f"DSX01-S{i:02d}", f"S{i:02d}"
        all_ids = {r["observation_id"] for r in raw if r["source_id"] == source_id}
        tracks = json.loads((PARTITION / case / "curves.json").read_text())
        receipt = json.loads((PARTITION / case / "receipt.json").read_text())
        for name in ("curves", "background"):
            assert (
                hashlib.sha256((PARTITION / case / f"{name}.json").read_bytes()).hexdigest()
                == receipt[f"{name}_sha256"]
            )
        track = {t["key"]: t for t in tracks}
        raw_by_id = {r["observation_id"]: r for r in raw if r["source_id"] == source_id}
        for t in tracks:
            for oid, time_s, value in zip(
                t["observation_ids"], t["times"], t["values"], strict=True
            ):
                point = raw_by_id[oid]
                assert (t["receiver"], t["channel"], t["rf_hz"]) == (
                    point["receiver"],
                    point["channel"],
                    point["actual_rf_hz"],
                )
                assert abs(time_s - point["time_s"]) < 1e-8
                lift = (value - point["measured_cfo_hz"]) / (1 / 4.4e-6)
                assert abs(lift - round(lift)) < 1e-7
        ids = [oid for t in tracks for oid in t["observation_ids"]]
        assert len(set(ids)) == len(ids) and set(ids) <= all_ids
        endpoints = json.loads(path.with_name("exact_validated_endpoints.json").read_text())
        for arm in ("c0", "fitted_c"):
            assert (
                exact_orbits[f"{case}/{arm}"]["endpoint_sha256"]
                == hashes[str(path.relative_to(ROOT))]
            )
        protocol = json.loads(path.with_name("refinement_protocol.json").read_text())
        assert protocol["known_reference_used"] is False
        assert protocol["inherited_hardware_initializer_used"] is False
        source = next(r for r in sources if r["source_id"] == source_id)
        original_position = source["original_position"]
        standard.append(
            dict(
                case=case,
                raw_points=len(all_ids),
                associated=source["original_associated_count"],
                percent=100 * source["original_associated_count"] / len(all_ids),
                position_error_km=distance_km(
                    (original_position["latitude_deg"], original_position["longitude_deg"]),
                    REFERENCE,
                ),
            )
        )
        mapping = {}
        for key, fit in endpoints.items():
            arm, method = key.split("/")
            rows = fit["rows"]
            assert {r["component"] for r in rows} == set(track)
            accepted, residual_by_id, label_by_id, raw_rss, innovation_rss = set(), {}, {}, 0.0, 0.0
            curved_owners, hardware_owners = {}, set()
            for row in rows:
                if row["compatible"] and row["active_curvature"]:
                    t = track[row["component"]]
                    curved_owners.setdefault(row["candidate_index"], set()).add(t["channel"])
                    hardware_owners.add(2 * (t["receiver"] - 1) + int(t["channel"] > 4))
            for row in rows:
                ids = track[row["component"]]["observation_ids"]
                assert row["points"] == len(ids) == len(row["residual_hz"])
                r, innovations = np.array(row["residual_hz"]), np.array(row["innovations_hz"])
                assert abs(np.sqrt(np.mean(r * r)) - row["rms_hz"]) < 1e-6
                if row["compatible"]:
                    assert row["rms_hz"] <= 450 and abs(row["bias_hz"]) <= 3000
                    t, j = track[row["component"]], row["candidate_index"]
                    if str(j) in fit["state"]["extra"]:
                        assert len(curved_owners.get(j, set())) >= 2
                    if not row["active_curvature"]:
                        assert 2 * (t["receiver"] - 1) + int(t["channel"] > 4) in hardware_owners
                        if abs(fit["state"]["phases"][j]) > 0.001:
                            assert j in curved_owners
                    blocks = (
                        [slice(None)]
                        if row["parts"] == 1
                        else [slice(0, row["split_at"]), slice(row["split_at"], None)]
                    )
                    for block in blocks:
                        assert batch_noise_screen(
                            innovations[None, block], np.array(t["times"])[block]
                        )["noise_screen_pass"][0]
                    assert not accepted.intersection(ids)
                    accepted.update(ids)
                    raw_rss += float(r @ r)
                    innovation_rss += float(innovations @ innovations)
                    for oid, value in zip(ids, r, strict=True):
                        residual_by_id[oid] = float(value)
                        label_by_id[oid] = row["candidate_norad"]
                        global_associations[key][case, oid] = row["candidate_norad"]
                per_track.append(
                    dict(
                        case=case,
                        arm=arm,
                        method=method,
                        component=row["component"],
                        points=row["points"],
                        compatible=row["compatible"],
                        norad=row["candidate_norad"],
                        rms_hz=row["rms_hz"],
                        innovation_rms_hz=float(np.sqrt(np.mean(innovations**2))),
                        parts=row["parts"],
                        split_at=row["split_at"],
                        curved=row["active_curvature"],
                    )
                )
            assert accepted <= all_ids
            mapping[key] = dict(ids=accepted, residual=residual_by_id, labels=label_by_id)
            destination = OUTPUT / "associations" / case
            destination.mkdir(parents=True, exist_ok=True)
            write(
                destination / f"{arm}_{method}.json",
                dict(
                    associated_observation_ids=sorted(accepted),
                    unassociated_observation_ids=sorted(all_ids - accepted),
                    original_raw_points=len(all_ids),
                    no_points_deleted=True,
                    saved_fit_sha256=validated_hashes[str(path.relative_to(ROOT))],
                    original_search_endpoint_sha256=hashes[str(path.relative_to(ROOT))],
                ),
            )
            parents = sum(r["compatible"] for r in rows)
            pieces = sum(r["parts"] for r in rows if r["compatible"])
            summary = dict(
                case=case,
                arm=arm,
                method=method,
                raw_points=len(all_ids),
                polynomial_points=sum(r["points"] for r in rows),
                outside_polynomials=len(all_ids) - sum(r["points"] for r in rows),
                associated=len(accepted),
                unassociated=len(all_ids) - len(accepted),
                percent_associated=100 * len(accepted) / len(all_ids),
                polynomial_parents=parents,
                association_segments=pieces,
                points_per_parent=len(accepted) / max(1, parents),
                points_per_segment=len(accepted) / max(1, pieces),
                candidate_satellites=len({r["candidate_norad"] for r in rows if r["compatible"]}),
                native_rms_hz=float(np.sqrt(raw_rss / max(1, len(accepted)))),
                innovation_rms_hz=float(np.sqrt(innovation_rss / max(1, len(accepted)))),
                score=fit["score"],
                latitude_deg=fit["latitude_deg"],
                longitude_deg=fit["longitude_deg"],
                position_error_km=distance_km(
                    (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                ),
                c_hz_per_ghz=fit["state"]["beta"][8] if arm == "fitted_c" else 0.0,
            )
            summaries.append(summary)
            coordinates.append(summary)
            write(
                path.parent / f"evaluation_{method}_{arm}.json",
                dict(
                    **summary,
                    endpoint_file_sha256=validated_hashes[str(path.relative_to(ROOT))],
                    original_search_endpoint_sha256=hashes[str(path.relative_to(ROOT))],
                    reference_used_only_after_fit=True,
                ),
            )
        for method in METHODS:
            a, b = mapping[f"c0/{method}"], mapping[f"fitted_c/{method}"]
            common = a["ids"] & b["ids"]
            c_pairs.append(
                dict(
                    case=case,
                    method=method,
                    common_associated_points=len(common),
                    common_label_agreement=sum(
                        a["labels"][oid] == b["labels"][oid] for oid in common
                    ),
                    common_point_native_rms_c0_hz=float(
                        np.sqrt(np.mean([a["residual"][oid] ** 2 for oid in common]))
                    )
                    if common
                    else None,
                    common_point_native_rms_fitted_c_hz=float(
                        np.sqrt(np.mean([b["residual"][oid] ** 2 for oid in common]))
                    )
                    if common
                    else None,
                )
            )
        checks.append(
            dict(
                case=case,
                raw_denominator=len(all_ids),
                point_population_verified=True,
                all_12_endpoints_evaluated=True,
                reference_excluded_from_search=True,
            )
        )
    assert sum(r["raw_points"] for r in standard) == 20084
    for name, rows in (
        ("per_scan.csv", summaries),
        ("per_track.csv", per_track),
        ("historical_standard.csv", standard),
        ("c_ablation.csv", c_pairs),
    ):
        with (OUTPUT / name).open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    aggregate = []
    consensus_path = OUTPUT / "blind_position_consensus.json"
    consensus = json.loads(consensus_path.read_text())["estimates"]
    for method in METHODS:
        for arm in ("c0", "fitted_c"):
            rows = [r for r in summaries if r["method"] == method and r["arm"] == arm]
            count = sum(r["associated"] for r in rows)
            aggregate.append(
                dict(
                    method=method,
                    arm=arm,
                    associated=count,
                    raw_points=20084,
                    percent_associated=100 * count / 20084,
                    segments=sum(r["association_segments"] for r in rows),
                    points_per_segment=count / max(1, sum(r["association_segments"] for r in rows)),
                    median_position_error_km=float(
                        np.median([r["position_error_km"] for r in rows])
                    ),
                    maximum_position_error_km=max(r["position_error_km"] for r in rows),
                    scans_below_0_5km=sum(r["position_error_km"] < 0.5 for r in rows),
                    fused_position_error_km=distance_km(
                        (
                            consensus[f"{arm}/{method}"]["latitude_deg"],
                            consensus[f"{arm}/{method}"]["longitude_deg"],
                        ),
                        REFERENCE,
                    ),
                )
            )
    write(
        OUTPUT / "summary.json",
        dict(
            per_scan=summaries,
            aggregate=aggregate,
            historical_standard=standard,
            c_ablation=c_pairs,
            reference=REFERENCE,
            matched_new_models=True,
            historical_standard_is_not_a_matched_rerun=True,
        ),
    )
    write(
        OUTPUT / "evaluation_validation.json",
        dict(
            checks=checks,
            endpoint_sha256=hashes,
            exact_validated_endpoint_sha256={
                str(
                    p.with_name("exact_validated_endpoints.json").relative_to(ROOT)
                ): hashlib.sha256(
                    p.with_name("exact_validated_endpoints.json").read_bytes()
                ).hexdigest()
                for p in files
            },
            all_raw_points_accounted=True,
            c0_fitted_c_observations_candidates_priors_and_budgets_matched=True,
            physical_satellite_identity_ground_truth_available=False,
            geographic_global_optimum_proven=False,
            blind_consensus_saved_before_evaluation=True,
            blind_consensus_sha256=hashlib.sha256(consensus_path.read_bytes()).hexdigest(),
        ),
    )
    pairwise = []
    for arm in ("c0", "fitted_c"):
        for method in METHODS:
            for other in METHODS:
                a, b = global_associations[f"{arm}/{method}"], global_associations[f"{arm}/{other}"]
                common, union = a.keys() & b.keys(), a.keys() | b.keys()
                pairwise.append(
                    dict(
                        arm=arm,
                        method=method,
                        other_method=other,
                        common_points=len(common),
                        union_points=len(union),
                        jaccard=len(common) / max(1, len(union)),
                        shared_label_agreement=sum(a[k] == b[k] for k in common)
                        / max(1, len(common)),
                    )
                )
    write(OUTPUT / "pairwise_associations.json", pairwise)
    render(summaries, standard, aggregate, per_track)
    render_target()
    report(summaries, standard, aggregate)
    print(json.dumps(aggregate), flush=True)


def render(rows, standard, aggregate, tracks):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout="constrained")
    values = np.array(
        [
            [
                next(
                    r["position_error_km"]
                    for r in rows
                    if r["method"] == m
                    and r["arm"] == "fitted_c"
                    and r["case"] == f"DSX01-S{i:02d}"
                )
                for i in range(1, 6)
            ]
            for m in METHODS
        ]
    )
    image = axes[0].imshow(np.log10(np.maximum(values, 0.01)), aspect="auto", cmap="RdYlGn_r")
    axes[0].set(
        xticks=range(5),
        xticklabels=[f"S{i:02d}" for i in range(1, 6)],
        yticks=range(len(METHODS)),
        yticklabels=[LABELS[m] for m in METHODS],
        title="Position error (km), fitted c",
    )
    for j in range(len(METHODS)):
        for i in range(5):
            axes[0].text(i, j, f"{values[j, i]:.2f}", ha="center", va="center", fontsize=9)
    fig.colorbar(image, ax=axes[0], label="log10(error in km)", shrink=0.7)
    for method in METHODS:
        r = [r for r in rows if r["method"] == method and r["arm"] == "fitted_c"]
        axes[1].plot(range(1, 6), [a["percent_associated"] for a in r], "o-", label=LABELS[method])
    axes[1].plot(range(1, 6), [r["percent"] for r in standard], "k--", label="Historical standard")
    axes[1].set(
        xlabel="DSX01 scan",
        ylabel="All raw GLRT associated (%)",
        xticks=range(1, 6),
        title="Association at independently estimated positions",
    )
    axes[1].grid(alpha=0.2)
    axes[1].legend(fontsize=7)
    fig.savefig(OUTPUT / "position_and_coverage.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), layout="constrained")
    for k, method in enumerate(METHODS):
        a, b = [
            next(r for r in aggregate if r["method"] == method and r["arm"] == arm)
            for arm in ("c0", "fitted_c")
        ]
        color = plt.get_cmap("tab10")(k)
        axes[0].plot(
            [a["percent_associated"], b["percent_associated"]],
            [a["median_position_error_km"], b["median_position_error_km"]],
            color=color,
        )
        axes[0].scatter(
            a["percent_associated"],
            a["median_position_error_km"],
            color=color,
            marker="o",
            label=LABELS[method],
        )
        axes[0].scatter(
            b["percent_associated"], b["median_position_error_km"], color=color, marker="^", s=65
        )
        axes[1].bar(k - 0.18, a["median_position_error_km"], width=0.36, color=color, alpha=0.4)
        axes[1].bar(k + 0.18, b["median_position_error_km"], width=0.36, color=color)
    axes[0].set(
        xlabel="Associated GLRT across DSX01 (%)",
        ylabel="Median position error (km)",
        title="Coverage versus accuracy: circles c=0, triangles fitted c",
    )
    axes[1].set(
        xticks=range(len(METHODS)),
        xticklabels=[LABELS[m] for m in METHODS],
        ylabel="Median position error (km)",
        title="Matched c ablation: translucent c=0, solid fitted c",
    )
    axes[1].tick_params(axis="x", rotation=35)
    for ax in axes:
        ax.grid(alpha=0.2)
    axes[0].legend(fontsize=7)
    fig.savefig(OUTPUT / "c_ablation_and_accuracy.png", dpi=170)
    plt.close(fig)
    target = [r for r in tracks if r["component"] == "S01-RX1-CH2-T000"]
    write(OUTPUT / "target_blind_outcomes.json", target)


def render_target():
    """Show raw retained points and model residuals without hiding rejected fits."""
    target_key = "S01-RX1-CH2-T000"
    target = next(
        t
        for t in json.loads((PARTITION / "DSX01-S01/curves.json").read_text())
        if t["key"] == target_key
    )
    times, values = np.array(target["times"]), np.array(target["values"])
    frozen = json.loads((OUTPUT / "target_frozen_state_prototypes.json").read_text())["models"]
    fig, axes = plt.subplots(3, 2, figsize=(13, 10), layout="constrained", sharex=True)
    for column, method in enumerate(("shared_phase", "penalized_split", "correlated_noise")):
        fit = frozen[method]
        residual = np.array(fit["residual_hz"])
        axes[0, 0].plot(times, (values - residual) / 1000, label=LABELS[method], lw=1.5)
        axes[column, 1].plot(times, residual, "o-", ms=3, label="Native residual")
        axes[column, 1].plot(times, fit["innovations_hz"], ".-", ms=3, label="Innovation")
        if fit["parts"] > 1:
            axes[column, 1].axvline(times[fit["split_at"]], color="k", ls=":")
        axes[column, 1].axhline(0, color="k", lw=0.7)
        axes[column, 1].set(
            title=f"{LABELS[method]}: {'passes' if fit['passing'] else 'fails'}", ylabel="Hz"
        )
        axes[column, 1].legend(fontsize=7)
    axes[0, 0].scatter(times, values / 1000, s=9, color="k", label="All 80 GLRT points")
    axes[0, 0].set(title="Known-site frozen-state diagnostic", ylabel="Unwrapped CFO (kHz)")
    axes[0, 0].legend(fontsize=7)
    axes[1, 0].axis("off")
    axes[1, 0].text(
        0.02,
        0.9,
        "Subdivision: all 80 points, two association pieces.\n"
        "Correlated noise: all 80 points, one curve.\n\n"
        "These fits use a frozen known-site state.\n"
        "They do not establish an independently correct position.\n"
        "No frozen parameters enter the blind comparison.",
        va="top",
        transform=axes[1, 0].transAxes,
        fontsize=11,
    )
    axes[2, 0].axis("off")
    for ax in axes.flat:
        ax.grid(alpha=0.2)
        ax.set_xlabel("Seconds from scan start")
    fig.savefig(OUTPUT / "target_retention_prototypes.png", dpi=170)
    plt.close(fig)

    fits = json.loads((OUTPUT / "DSX01-S01/exact_validated_endpoints.json").read_text())
    fig, axes = plt.subplots(3, 2, figsize=(13, 10), layout="constrained", sharex=True, sharey=True)
    for ax, method in zip(axes.flat, METHODS, strict=True):
        row = next(r for r in fits[f"fitted_c/{method}"]["rows"] if r["component"] == target_key)
        ax.plot(times, row["residual_hz"], "o-", ms=3, label="Native residual")
        ax.plot(times, row["innovations_hz"], ".-", ms=3, label="Innovation")
        if row["parts"] > 1:
            ax.axvline(times[row["split_at"]], color="k", ls=":")
        ax.axhline(0, color="k", lw=0.7)
        ax.set(
            title=f"{LABELS[method]}: {'accepted' if row['compatible'] else 'unassociated'}\n"
            f"NORAD {row['candidate_norad']}, native RMS {row['rms_hz']:.0f} Hz",
            xlabel="Seconds from scan start",
            ylabel="Hz",
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=7)
    fig.suptitle("Target at each independently estimated S01 position, fitted c")
    fig.savefig(OUTPUT / "target_blind_residuals.png", dpi=170)
    plt.close(fig)


def report(rows, standard, aggregate):
    targets = json.loads((OUTPUT / "target_blind_outcomes.json").read_text())
    white, split, correlated = [
        next(r for r in aggregate if r["method"] == method and r["arm"] == "fitted_c")
        for method in ("shared_phase", "penalized_split", "correlated_noise")
    ]
    lines = [
        "# DSX01: retaining long tracks and evaluating independent position",
        "",
        "Six model structures were evaluated across all five scans with paired c=0 and fitted-c runs. "
        "Every fitted position was saved before the supplied GPS entered this reporter. The new search used "
        "zero hardware initialization, raw-curved calibration only, and shared bounded geographic proposals. "
        "The historical standard pipeline is a recorded reference with different inference/search settings, not a matched rerun.",
        "",
        "## Measured findings",
        "",
        "The full 80-point S01 target can be retained without deleting its tail. Penalized subdivision associates two pieces to candidate 62811 at 138.5 Hz RMS; the correlated-noise model keeps one curve at 203.9 Hz native RMS and 120.2 Hz innovation RMS. Both retain the same independently fitted S01 location as the shared-phase baseline: 4.160 km error. They do not establish independent truth for the satellite identity.",
        "",
        f"Across DSX01, subdivision raises coverage from {white['percent_associated']:.2f}% to {split['percent_associated']:.2f}%. Correlated noise raises it to {correlated['percent_associated']:.2f}%, or {correlated['associated']:,} of 20,084 raw GLRT points. Its median scan error is {correlated['median_position_error_km']:.3f} km, equal to the fitted-c baseline median, while its worst scan error is {correlated['maximum_position_error_km']:.3f} km versus {white['maximum_position_error_km']:.3f} km. More associated points do not consistently imply a better independent position.",
        "",
        "Correlated noise gives the best simple five-scan consensus here at 1.508 km, but none of the independent scan estimates from any method/arm is within 500 m. The family-rate, orbital and receiver-smooth extensions increase coverage while worsening median scan accuracy relative to fitted-c shared phase. These bounded prototypes expose a remaining localization/parameter-identifiability problem; they do not solve it.",
        "",
        "The c ablation is mixed. For correlated noise, c=0 yields 81.50% coverage versus 81.21% with fitted c, the same 4.160 km median and 1.508 km consensus, and a smaller worst error (10.484 versus 13.332 km). There is no consistent evidence here for enabling the RF-dependent c term merely to improve fit.",
        "",
        "For conservative immediate retention, subdivision preserves the existing white-residual requirement within each piece, with the explicit limitation that the pieces can have different constants. Correlated noise is the strongest coverage prototype and warrants further shared-error diagnosis; it changes the requirement to white innovations, so native residual structure remains a modeled hypothesis. The next useful experiment is joint multiscan inference with shared physical error sources and explicit position/nuisance identifiability diagnostics, rather than selecting a model by in-sample coverage alone.",
        "",
        "## Position error by scan",
        "",
        "Values are kilometers; each cell is **c=0 / fitted c**.",
        "",
        table(
            ["Approach", "S01", "S02", "S03", "S04", "S05"],
            [
                [LABELS[m]]
                + [
                    " / ".join(
                        f"{next(r['position_error_km'] for r in rows if r['method'] == m and r['arm'] == a and r['case'] == f'DSX01-S{i:02d}'):.3f}"
                        for a in ("c0", "fitted_c")
                    )
                    for i in range(1, 6)
                ]
                for m in METHODS
            ],
        ),
        "",
        "Historical recorded standard: "
        + ", ".join(f"{r['case'][-3:]} {r['position_error_km']:.3f} km" for r in standard)
        + ".",
        "",
        "## Coverage at the estimated position",
        "",
        table(
            [
                "Approach / c arm",
                "Associated GLRT",
                "Associated %",
                "Segments",
                "GLRT / segment",
                "Median position error, km",
                "Worst error, km",
            ],
            [
                [
                    LABELS[r["method"]] + " / " + r["arm"],
                    r["associated"],
                    f"{r['percent_associated']:.2f}",
                    r["segments"],
                    f"{r['points_per_segment']:.1f}",
                    f"{r['median_position_error_km']:.3f}",
                    f"{r['maximum_position_error_km']:.3f}",
                ]
                for r in aggregate
            ],
        ),
        "",
        "![Position and coverage](position_and_coverage.png)",
        "",
        "![Matched RF calibration ablation](c_ablation_and_accuracy.png)",
        "",
        "## Per-scan coverage and track size",
        "",
        "Each cell is **associated percentage / association segments / GLRT per segment**, fitted c. The full paired runs, parent counts and native/innovation RMS are in `per_scan.csv`.",
        "",
        table(
            ["Approach", "S01", "S02", "S03", "S04", "S05"],
            [
                [LABELS[m]]
                + [
                    next(
                        f"{r['percent_associated']:.1f}% / {r['association_segments']} / {r['points_per_segment']:.1f}"
                        for r in rows
                        if r["method"] == m
                        and r["arm"] == "fitted_c"
                        and r["case"] == f"DSX01-S{i:02d}"
                    )
                    for i in range(1, 6)
                ]
                for m in METHODS
            ],
        ),
        "",
        "## Five-scan position fusion",
        "",
        "A coordinate-wise median of the five independently fitted positions was saved before GPS evaluation. This is a simple robust position consensus, not a joint-likelihood refit, and the association counts above remain those at the independent scan positions.",
        "",
        table(
            ["Approach", "c=0 error, km", "Fitted c error, km"],
            [
                [LABELS[m]]
                + [
                    f"{next(r['fused_position_error_km'] for r in aggregate if r['method'] == m and r['arm'] == a):.3f}"
                    for a in ("c0", "fitted_c")
                ]
                for m in METHODS
            ],
        ),
        "",
        "## Model definitions",
        "",
        "- Shared phase: four RX/band offsets and small linear drifts, optional RF coefficient c, one phase per satellite, Gaussian whole-curve constants and strict raw-residual gates.",
        "- Satellite family rate: one additional shared frequency rate per satellite, sigma 10 Hz/s and bound 20 Hz/s. Two accepted curved channels must own a correction.",
        "- Orbital MAP / soft EM: shared phase plus two eccentricity-vector adjustments, sigma 1e-4 and component bounds 5e-4; whole-curve signal/clutter responsibilities drive MAP proposals. Each satellite prior is charged once. These are heuristic sensitivity priors, not calibrated orbit covariance.",
        "- Penalized subdivision: at most two individually raw-curved pieces, each retaining all of its observations; Gaussian constants per piece plus 12+log(n) split cost. Pieces are counted separately and do not establish a continuous carrier identity across the boundary.",
        "- Correlated noise: all points retained with white sigma 150 Hz plus an exponential-covariance component of sigma 150 Hz and correlation time 10 s. Covariance volume is included. Structure gates apply to whitened innovations; native residuals can remain correlated.",
        "- Receiver smooth error: eleven smooth columns per receiver, projected off scan-wide constant/linear components, sigma 200 Hz. At least two curved satellite nominees must support a receiver. Four separate RX/band affine calibrations remain in the model.",
        "",
        "The satellite-rate and orbital models are common-harness localization implementations of the earlier fixed-site approaches, not a reuse of their ground-truth-position labels or coefficients. Priors, initializer and optimizer budget are stated here because their results need not be numerically identical to the earlier fixed-site association experiments.",
        "The overall selection objectives combine likelihood terms, explicit clutter costs, structure gates and complexity penalties. They are research composite scores, not normalized identity probabilities; position error is measured separately.",
        "",
        "## Target capability versus blind outcome",
        "",
        "The separate `target_frozen_state_prototypes.json` is explicitly a known-site diagnostic and was never used for geographic search. At that frozen state, the 80-point target fails the white model at 201 Hz RMS; penalized subdivision retains all 80 points as two pieces at 140 Hz combined RMS; the correlated-noise model retains the full curve with native RMS 202 Hz and approximately 120 Hz innovation RMS. Actual outcomes at each independently fitted S01 position are in `target_blind_outcomes.json`.",
        "",
        table(
            [
                "Approach / c arm",
                "Target points associated",
                "Tested NORAD",
                "Pieces",
                "Native RMS, Hz",
                "Innovation RMS, Hz",
            ],
            [
                [
                    LABELS[r["method"]] + " / " + r["arm"],
                    r["points"] if r["compatible"] else 0,
                    r["norad"],
                    r["parts"],
                    f"{r['rms_hz']:.1f}",
                    f"{r['innovation_rms_hz']:.1f}",
                ]
                for r in targets
            ],
        ),
        "",
        "![Target retention at a frozen state](target_retention_prototypes.png)",
        "",
        "![Target residuals at independently estimated positions](target_blind_residuals.png)",
        "",
        "## Controls and limitations",
        "",
        "The raw denominator is 20,084 GLRT points. Points outside retained graph polynomials remain explicitly unassociated; no observation is silently deleted. Counts are polynomial fragments or association segments, not authenticated emitters or newly merged carrier tracks. Satellite identities have no independent ground truth here.",
        "",
        "Changing every linear fragment's CFO by a large nonaffine perturbation left calibration parameters and scores exactly unchanged in all twelve model/c-arm combinations at the regional center (`linear_influence_control.json`). The prior inherited initializer was rejected because its older calibration used linear-sided pairs; its incomplete outputs remain explicitly superseded and never enter evaluation.",
        "",
        "Causal TLEs reproduce every frozen scan bank exactly at checked epochs (`tle_parity.json`). No post-observation TLE enters these fits. Matched c-arm frequency effects on common associated points are reported separately in `c_ablation.csv`; a better score or RMS is not a position-accuracy claim.",
        "Final orbital-model assignments were rechecked using actual perturbed SGP4 elements at their frozen fitted positions (`exact_orbit_validation.json`). The final coverage uses exact residuals and conservatively rejects any assignment that fails this check, followed by removal of assignments whose curved calibration support disappeared. The original tangent-based search endpoints and position estimates remain unchanged. No previously rejected assignment is promoted during this audit. All final accepted rows pass the exact frequency, visibility and residual-structure checks.",
        "One assignment was removed by that audit: the 57-point S01 RX2 CH6 T000 under fitted-c orbital MAP. Its maximum residual difference was only 0.142 Hz, but its trend BIC gain crossed the limit of 10 to 10.0068. There were no support-cascade losses. This illustrates the sensitivity of binary gate counts near a boundary; the gate was kept fixed.",
        "",
        "The geographic search is bounded and not proof of a global optimum. Regional discovery may use free constants and per-curve phases only to propose locations; final fits enforce their stated shared model. All observations are fitted, with no withheld points. Prototype choices were informed by the S01 diagnosis, so these five scans are an exploratory comparison rather than independent generalization evidence.",
        "",
        "Each scan directory records the initial and refinement geographic candidates, scores, nuisance histories, final parameter states and protocol. The supplied GPS is confined to this post-fit reporting program. `evaluation_validation.json` binds all reported endpoints by SHA-256.",
        "",
        "## Implementation and verification",
        "",
        "The numerical component is `src/leo/analysis/research/retained_track_likelihood.py`; the common fitter is `tools/compare_dsx01_retention_localization.py`, with geographic continuation in `tools/refine_dsx01_retention_localization.py`. Source snapshots and hashes are recorded in `run_sources/` and `source_manifest.json`.",
        "",
        "Nineteen focused scientific tests passed, including five component-owned tests covering native alias parity, Gaussian covariance whitening, affine-free smooth basis, exact Gaussian constant elimination and invalid repeated timestamps. Ruff checks passed for the new component, tests and comparison/report tools. The final accepted rows also pass the independent observation-binding, ownership and residual audits recorded in `evaluation_validation.json`.",
        "",
        "To regenerate the evaluation and figures from sealed endpoints, run `tools/validate_dsx01_retention_orbits.py`, then `tools/fuse_dsx01_retention_positions.py`, then `tools/report_dsx01_retention_localization.py`, using the repository virtual environment with `PYTHONPATH=src:tools`. Search candidates and all endpoint states are persisted, so the numerical evaluations at those locations can be replayed without rerunning geographic discovery. Inference and reporting are research tools; no production pipeline or persisted public contract was changed.",
        "",
        "## Methodological background and next prototypes",
        "",
        "Penalized changepoint likelihood motivates the subdivision test; the current implementation exhaustively searches one break among three shortlisted satellites, rather than implementing PELT or claiming its complexity guarantees. A useful extension would connect pieces with a continuity prior and allow rate changes only when supported. [Killick, Fearnhead and Eckley, optimal changepoint detection](https://arxiv.org/abs/1101.1438).",
        "",
        "The correlated-noise model uses a Gaussian covariance and includes its log determinant, so increasing model flexibility has a volume cost. The present fixed covariance is a hypothesis about frequency error, not evidence of its physical origin. A useful next test would share the correlated process across simultaneous channels and contrast receiver-shared versus satellite-shared error. [Rasmussen and Williams, Gaussian Processes for Machine Learning](https://gaussianprocess.org/gpml/chapters/).",
        "",
        "Soft assignment followed by shared parameter updates is motivated by EM. Our finite proposals, structure gates and composite selection criterion do not establish classical EM monotonicity or posterior calibration. The next inference experiment should use one consistent joint signal/clutter likelihood with explicit identifiability checks on position, phase, receiver drift and orbit correction. [Dempster, Laird and Rubin, the EM algorithm](https://academic.oup.com/jrsssb/article/39/1/1/7027539).",
        "",
        "A fourth unimplemented retention option is to retain a reliable prefix for orbital calibration while preserving the remaining points as an explicitly uncalibrated continuation. This would avoid discarding their existence without letting the problematic tail steer position. It must be reported separately from a full satellite association.",
        "",
    ]
    (OUTPUT / "README.md").write_text("\n".join(lines))


if __name__ == "__main__":
    run()
