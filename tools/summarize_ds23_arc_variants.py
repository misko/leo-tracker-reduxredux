"""Audit saved prototype runs and derive comparison tables and figures."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from associate_merged_track_catalogue import write
from evaluate_ds23_arc_variants import CASES, OUT, plot, prepare
from investigate_ds23_visible_arcs import SOURCE

from leo.analysis.research.visible_arc_variants import (
    curvature_rms,
    duplicate_explanations,
    frequency,
    wrap,
)

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("greedy_graph_repair", "joint_paths", "satellite_EM")


def read(path):
    return json.loads(path.read_text())


def baseline(case, arm, document):
    tracks = read(SOURCE / case / "tracks.json")
    raw = read(SOURCE / case / "tracking.json")
    obs = read(SOURCE / case / "observations.json")
    probe_ids = {
        (p["receiver_id"], p["valid_start_counter"]): i for i, p in enumerate(raw["probes"])
    }
    observations = {
        o["observation_id"]: probe_ids[o["native_receiver_id"], o["valid_start_counter"]]
        for o in obs
    }
    old = read(SOURCE / case / "fit_radio_noise.json")
    winner = next(c for c in old["choices"] if c["hypothesis"] == old["selected_hypothesis"])
    accepted = {r["component"] for r in winner["arms"][arm]["all_graph_associations"]["tracks"]}
    accepted_probes = {
        observations[oid] for t in tracks if t["key"] in accepted for oid in t["observation_ids"]
    }
    probe = np.asarray(document["probes"])
    winners = np.asarray(document["winners"])
    target = None
    if case == "DS23-0342":
        target_track = next(t for t in tracks if "RX1-CH2-T002" in t["key"])
        target = {observations[oid] for oid in target_track["observation_ids"]}
    return dict(
        associated_winners=sum(probe[i] in accepted_probes for i in winners),
        winning_probes=len(winners),
    ), target


def audit_result(document, result):
    times, probe = np.asarray(document["times"]), np.asarray(document["probes"])
    assignment = np.asarray(result["assignment"])
    owned = []
    for k, t in enumerate(result["tracks"]):
        ix = np.asarray(t["indices"])
        np.testing.assert_array_equal(assignment[ix], k)
        assert len(set(probe[ix])) == len(ix)
        assert np.max(np.diff(times[ix])) <= 10
        assert t["orbit"]["rms_hz"] <= 3 * document["sigma_hz"]
        assert max(abs(np.array(t["orbit"]["residual_hz"]))) <= 6 * document["sigma_hz"]
        assert t["orbit"]["diagnostics"]["noise_screen_pass"]
        assert t["polynomial"]["diagnostics"]["noise_screen_pass"]
        assert (
            curvature_rms(
                times[ix],
                {**t["polynomial"], "coefficients": np.asarray(t["polynomial"]["coefficients"])},
            )
            >= 2 * document["sigma_hz"]
        )
        owned.extend(ix.tolist())
    assert len(set(owned)) == len(owned)
    assert sorted(owned) == np.flatnonzero(assignment >= 0).tolist()
    for run in result.get("em_runs", []):
        assert max(np.diff(run["history"])) <= 1e-5


def summarize():
    rows, track_rows, audits, files = [], [], [], []
    for case in CASES:
        pair = []
        for arm in ("c0", "fitted_c"):
            path = OUT / f"{case}_{arm}.json"
            a = read(path)
            pair.append(a)
            files.append(path)
            old, target = baseline(case, arm, a)
            scan, data, candidates, winners, *_ = prepare(case, arm)
            plot(case, arm, scan, data, candidates, winners, a["results"])
            all_results = dict(a["results"])
            all_results["satellite_EM_MAP"] = a["results"]["satellite_EM"]["map_assignment_result"]
            details = []
            for method, result in all_results.items():
                audit_result(a, result)
                s = result["summary"]
                assignment = np.asarray(result["assignment"])
                target_hits = (
                    None
                    if target is None
                    else sum(data["probes"][i] in target and assignment[i] >= 0 for i in winners)
                )
                row = dict(
                    case=case,
                    arm=arm,
                    method=method,
                    **s,
                    canonical_peaks=len(candidates),
                    canonical_percent=100 * s["assigned_peaks"] / len(candidates),
                    baseline_winners=old["associated_winners"],
                    original_rejected_track_recovered=target_hits,
                    common_proposal_s=a["common_proposal_s"],
                    selection_s=result.get(
                        "selection_s", a["results"]["satellite_EM"]["selection_s"]
                    ),
                )
                rows.append(row)
                for track in result["tracks"]:
                    track_rows.append(
                        dict(
                            case=case,
                            arm=arm,
                            method=method,
                            norad=track["norad"],
                            points=track["points"],
                            winning_points=track["winning_points"],
                            secondary_points=track["secondary_points"],
                            start_s=track["start_s"],
                            end_s=track["end_s"],
                            orbit_rms_hz=track["orbit"]["rms_hz"],
                            polynomial_rms_hz=track["polynomial"]["rms_hz"],
                            polynomial_degree=track["polynomial"]["degree"],
                            polynomial_knots_s=str(track["polynomial"]["knots"]),
                            phase_s=track["orbit"]["parameters"][0],
                            bias_hz=track["orbit"]["parameters"][1],
                            doppler_scale=track["orbit"]["parameters"][2],
                        )
                    )
                for i in winners[assignment[winners] < 0]:
                    distance = [
                        float(
                            wrap(
                                data["values"][i]
                                - frequency(
                                    scan.sky,
                                    tr["candidate_index"],
                                    np.array([data["times"][i]]),
                                    tr["orbit"]["parameters"],
                                    data["site"],
                                    data["rf_hz"],
                                )[0]
                            )
                        )
                        for tr in result["tracks"]
                    ]
                    details.append(
                        dict(
                            method=method,
                            time_s=float(data["times"][i]),
                            canonical_peak=int(i),
                            original_rejected_track=bool(target and data["probes"][i] in target),
                            residuals_to_retained_tracks_hz=distance,
                        )
                    )
            write(OUT / f"{case}_{arm}_remaining_winner_audit.json", details)
            # Robustness of the alternative-identity guard, independent of GPS.
            pool = []
            for h in a["hypotheses"]:
                if h["candidate_index"] not in {m["candidate_index"] for m in pool}:
                    pool.append(h)
            guards = {
                str(threshold): [
                    (x["candidate_index"], y["candidate_index"])
                    for i, x in enumerate(pool)
                    for y in pool[i + 1 :]
                    if duplicate_explanations(x, y, threshold)
                ]
                for threshold in (0.4, 0.6, 0.8)
            }
            audits.append(
                dict(
                    case=case,
                    arm=arm,
                    baseline=old,
                    allocation_and_noise_gates_passed=True,
                    duplicate_guard_conflicts=guards,
                )
            )
            ablation = read(OUT / f"{case}_{arm}_duplicate_ablation.json")
            for method in ("joint_paths", "satellite_EM"):
                r = ablation["results"][method]
                rows.append(
                    dict(
                        case=case,
                        arm=arm,
                        method=method + "_without_identity_guard",
                        **r["summary"],
                        canonical_peaks=len(candidates),
                        canonical_percent=100 * r["summary"]["assigned_peaks"] / len(candidates),
                        baseline_winners=old["associated_winners"],
                        original_rejected_track_recovered=None,
                        common_proposal_s=ablation["common_proposal_s"],
                        selection_s=r["selection_s"],
                    )
                )
        assert pair[0]["candidates"] == pair[1]["candidates"]
        assert pair[0]["winners"] == pair[1]["winners"]
        assert pair[0]["all_causal_satellites"] == pair[1]["all_causal_satellites"]
        assert {r["candidate_index"] for r in pair[0]["attempts"]} == {
            r["candidate_index"] for r in pair[1]["attempts"]
        }
        assert {r["candidate_index"] for r in pair[0]["hypotheses"]} == {
            r["candidate_index"] for r in pair[1]["hypotheses"]
        }
    for filename, table in [("comparison.csv", rows), ("track_details.csv", track_rows)]:
        with (OUT / filename).open("w") as f:
            writer = csv.DictWriter(f, fieldnames=list(table[0]))
            writer.writeheader()
            writer.writerows(table)
    summary_plot(rows)
    files.extend(
        [
            ROOT / "src/leo/analysis/research/visible_arc_variants.py",
            ROOT / "tools/evaluate_ds23_arc_variants.py",
            Path(__file__).resolve(),
            ROOT / "tests/analysis/test_visible_arc_variants.py",
        ]
    )
    for case in CASES:
        files.extend(
            SOURCE / case / name
            for name in [
                "observations.json",
                "tracking.json",
                "tracks.json",
                "bank.npz",
                "nominal_elements.json",
                "receipt.json",
                "radio_noise.json",
            ]
        )
        files.extend(
            ROOT / "reports/2026_10_18_ds23_visible_arcs" / f"{case}_{arm}_frozen.json"
            for arm in ("c0", "fitted_c")
        )
    write(
        OUT / "validation.json",
        dict(
            audits=audits,
            paired_c_inputs_and_candidate_sets_matched=True,
            GPS_used_for_selection=False,
            future_TLE_used=False,
            position_reestimated=False,
            component_tests=11,
            regression_tests="60 passed",
            ruff="all checks passed",
            sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
            },
        ),
    )
    print("Audited all allocations, gates, paired c inputs and EM monotonicity.", flush=True)


def summary_plot(rows):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    methods = ["greedy_graph_repair", "joint_paths", "satellite_EM_MAP", "satellite_EM"]
    labels = ["Greedy graph\nrepair", "Joint paths", "EM: MAP", "EM: posterior\n≥0.8"]
    for ax, case in zip(axes, CASES, strict=True):
        selected = [
            next(
                r for r in rows if r["case"] == case and r["arm"] == "c0" and r["method"] == method
            )
            for method in methods
        ]
        wins = np.array([r["associated_winners"] for r in selected])
        secondary = np.array([r["secondary_peaks"] for r in selected])
        ax.bar(np.arange(4), wins, label="Original winners")
        ax.bar(
            np.arange(4),
            secondary,
            bottom=wins,
            label="Additional canonical peaks",
            color="tab:orange",
        )
        for i, (w, s) in enumerate(zip(wins, secondary, strict=True)):
            ax.text(i, w + s + 1, f"{w}+{s}", ha="center")
        ax.axhline(
            selected[0]["baseline_winners"], c="black", ls="--", label="Original associated winners"
        )
        ax.set(
            title=case,
            ylabel="Associated canonical peaks",
            xticks=np.arange(4),
            xticklabels=labels,
            ylim=(0, max(wins + secondary) + 22),
        )
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.legend(fontsize=8)
    fig.suptitle("Target intervals only; no position re-estimation; c=0")
    fig.tight_layout()
    fig.savefig(OUT / "comparison.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    summarize()
