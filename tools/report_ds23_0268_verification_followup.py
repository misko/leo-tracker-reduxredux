"""Report-only synthesis of the retained fit and independent identity controls."""

import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from debug_ds23_0268_visibility_reentry import OUT
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import read, write, sha, ROOT
from probe_algo03_frame_peak_recovery import SOURCE
from plot_ds23_0268_remaining_tracks import alias_lines
from report_ds23_0268_visibility_reentry import graph_piece_prediction
from audit_ds23_0268_sky_visibility import render


def association_figure(coverage):
    proposal = "selected_split_all_RX1_with_CH2_constrained"
    current = coverage[proposal]["c0"]
    previous = next(r for r in read(OUT / "trial_coverage.json")["rows"] if r["name"] == "interior_add_66797")["arms"]["c0"]
    observations = read(SOURCE / "DS23-0268/observations.json")
    tracks = read(SOURCE / "DS23-0268/tracks.json")
    by_key = {t["key"]: t for t in tracks}
    def owners(record):
        return {oid: r["norad"] for r in record["accepted_rows"]
                for oid in r.get("observation_ids", by_key[r["component"]]["observation_ids"])}
    before, after = owners(previous), owners(current)
    accepted = {r["component"] for r in current["accepted_rows"]}
    figure, panels = plt.subplots(4, 4, figsize=(22, 14))
    counts = dict(unchanged=0, reassigned=0, added=0, unknown=0)
    for rx in (1, 2):
        for ch in range(1, 9):
            ax = panels[(rx-1)*2 + (ch-1)//4, (ch-1)%4]
            points = [o for o in observations if o["receiver"] == rx and o["channel"] == ch]
            times = np.array([o["time_s"] for o in points])
            values = np.array([o["measured_cfo_hz"] for o in points])
            lo, hi = values.min()-8000, values.max()+8000
            for t in tracks:
                if (t["receiver"], t["channel"]) != (rx, ch):
                    continue
                for piece in t["pieces"]:
                    grid = np.linspace(piece["start_s"], piece["end_s"], 150)
                    for line in alias_lines(graph_piece_prediction(piece, grid), lo, hi):
                        ax.plot(grid, line/1000, color="#99aaa0" if t["key"] in accepted else "#c08591", lw=.7, alpha=.6)
            labels = []
            for o in points:
                oid = o["observation_id"]
                label = ("unknown" if oid not in after else "added" if oid not in before else
                         "reassigned" if before[oid] != after[oid] else "unchanged")
                labels.append(label)
                counts[label] += 1
            for kind, color, label in (("unchanged", "#267b44", "Retained identity"),
                    ("reassigned", "#9659ad", "Reassigned 53923 → 67953"),
                    ("added", "#277cce", "Newly associated CH2"), ("unknown", "#e04e68", "Unassociated")):
                use = np.array(labels) == kind
                ax.scatter(times[use], values[use]/1000, color=color, s=10, alpha=.8, label=label)
            ax.set_title(f"RX{rx} CH{ch}")
            ax.set_xlim(0, 300)
            ax.set_ylim(lo/1000, hi/1000)
            ax.set_ylabel("Native CFO (kHz)")
            ax.set_xlabel("Scan time (s)")
            ax.grid(alpha=.12)
    handles, labels = panels[0, 0].get_legend_handles_labels()
    figure.legend(handles, labels, ncol=4, loc="lower center")
    figure.suptitle("DS23-0268 · accepted receiver split + CH2 · 2,316 / 3,165 = 73.18%\n"
        "All previous 2,254 associated observations retained · original graph polynomials and acceptance gates", fontsize=16)
    figure.tight_layout(rect=(0, .045, 1, .94))
    figure.savefig(OUT / "accepted_split_73percent_GLRT.png", dpi=170)
    plt.close(figure)
    return counts


def main():
    audit = read(OUT / "independent_replay_audit.json")
    identity = read(OUT / "identity_family_excluded_screen.json")
    selected = read(OUT / "trials/interior_add_66797.json")
    accepted_coverage = read(OUT / "accepted_identity_split_coverage.json")
    point_counts = association_figure(accepted_coverage)
    if point_counts != dict(unchanged=2154, reassigned=100, added=62, unknown=849):
        raise ValueError("association figure counts changed")
    latest_name = "selected_split_all_RX1_with_CH2_constrained"
    latest_sky = read(OUT / (latest_name + "_independent_replay_audit.json"))
    names = ("selected_split_RX1", "selected_split_RX1_with_CH2",
             "selected_split_all_RX1", "selected_split_all_RX1_with_CH2")
    names += tuple(name + "_constrained" for name in names)
    proposals = [read(OUT / (name + ".json")) for name in names]
    figure, axes = plt.subplots(2, 3, figsize=(16, 9))
    identity_table = []
    for row, arm in enumerate(("c0", "fitted_c")):
        for col, group in enumerate(("RX1", "RX2", "all_six")):
            candidates = identity["arms"][arm][group]
            pair = [next(r for r in candidates if r["norad"] == n) for n in (53923, 67953)]
            ax = axes[row, col]
            ax.bar(["53923", "67953"], [r["curve_score"] for r in pair], color=["#267b44", "#9659ad"])
            for i, r in enumerate(pair):
                ax.text(i, r["curve_score"], f"{r['curve_score']:.1f}\nrank {r['rank']}", ha="center", va="bottom")
            ax.set_ylim(0, max(r["curve_score"] for r in pair) * 1.22)
            ax.set_title(f"{arm} · {group}")
            ax.set_ylabel("Conditional shared-phase curve score")
            ax.grid(axis="y", alpha=.15)
            identity_table.append(f"| {arm} | {group} | {pair[0]['curve_score']:.1f} | {pair[1]['curve_score']:.1f} |")
    figure.suptitle("DS23-0268 · all 53923 evidence excluded from calibration and position\n"
        "1,402 causal candidates · one phase per group · compare within each panel only\n"
        "Diagnostic fit fails other retained gates; scores are proposals, not identity probabilities")
    figure.tight_layout(rect=(0, 0, 1, .88))
    figure.savefig(OUT / "identity_family_excluded_comparison.png", dpi=170)
    plt.close(figure)
    points = [r for r in csv.DictReader((OUT / (latest_name + "_direct_nominal_sky_points.csv")).open())
              if r["arm"] == "c0" and r["geometry"] == "RF_estimate"]
    polar_rows = []
    for component in dict.fromkeys(r["component"] for r in points):
        group = [r for r in points if r["component"] == component]
        polar_rows.append(dict(receiver=int(group[0]["receiver"]), norad=int(group[0]["norad"]),
            azimuth_deg=[float(r["azimuth_deg"]) for r in group],
            elevation_deg=[float(r["elevation_deg"]) for r in group]))
    render(polar_rows, "split_73percent_c0_nominal")
    lines = ["# DS23-0268: 73.18% association and receiver-dependent satellite identity repair", "",
        f"Audit time: {audit['audited_at_UTC']}. This follow-up replays saved scientific fits, adds a "
        "direct nominal-SGP4 sky check, and tests family-excluded calibration and identity proposals. "
        "It does not replace the default algorithm or demonstrate generalization to other scans.", "",
        "**The new accepted RX1/RX2 split reaches 2,316/3,165 original GLRT points (73.175%), "
        "64 tracks and 17 satellite labels in both c arms.** It retains all 2,254 previously "
        "accepted observations, relabels 100 RX1 points from 53923 to 67953, adds the "
        "62-point CH2 curve to 67953, and leaves 849 points unassociated. "
        "No original graph track is rebuilt or split. The unchanged residual, alias, horizon, "
        "support and predictive gates all pass after constrained optimization.", "",
        "![Latest GLRT association and identity changes](accepted_split_73percent_GLRT.png)", "",
        "The earlier retained candidate has **2,254/3,165 original winning GLRT points (71.216%)**, "
        "63 tracks and 16 satellite labels in each matched c arm. All 2,111 earlier associated "
        "points are retained: 143 added, zero lost, zero additional peaks counted in the numerator. "
        "Fresh replay reproduces the full RF objective, retained curved gates, predictive gates "
        "and extension membership. The 911 remaining points remain unassociated.", "",
        "| Earlier accepted candidate | c = 0 | fitted c |", "|---|---:|---:|",
        f"| Position error, km | {position_error(selected['arms']['c0']['endpoint_latlon']):.3f} | "
        f"{position_error(selected['arms']['fitted_c']['endpoint_latlon']):.3f} |", "",
        "Higher coverage is not accurate localization. GPS is used only by this reporter, never "
        "for fitting, candidate nomination or acceptance. No future TLE or new RF collection is used.", "",
        "## Recovery mechanism", "",
        "The receiver-step/family-reentry baseline reaches 66.70%. A finer receiver basis with "
        "matched average pointwise prior variance recovers the intact 60-point CH7 curve as 64333, "
        "reaching 68.59%. Restoring both 66797 curves adds 67 curved points; a frozen-calibration "
        "extension adds 16 more. The unconstrained c0 solution narrowly fails a retained slope "
        "gate (3.021 versus 3). The retained candidate minimizes the same RF objective subject "
        "to the original gates, with a stricter 0.01 normalized interior slack. This changes "
        "optimization, not the acceptance thresholds. Original observations and graph pieces are retained.", "",
        "## 53923 identity: what is and is not established", "",
        "The original whole-catalogue screen favors 53923 for all six curved tracks, but its "
        "receiver calibration was jointly learned with those tracks. As a control, remove every "
        "53923 curved and predictive factor and refit position and calibration from the same "
        "regional cold start and unchanged remaining priors. The disputed measurements are used "
        "only after this fit to screen all 1,402 causal candidates across shared phases from "
        "-15 to +15 seconds, spaced by 0.25 seconds. Nominal candidate orbits are compared; no "
        "candidate-specific orbit modes or phase prior enter these proposal scores.", "",
        "| c arm | Disputed group | 53923 score | 67953 score |", "|---|---|---:|---:|",
        *identity_table, "",
        "The RX1 pair favors 67953 in both c arms; RX2 favors 53923. The all-six winner changes "
        "between c arms. This exposes calibration/identity coupling and supports keeping the "
        "split as a hypothesis. It does not prove either identity: the family-excluded fit itself "
        "fails retained 63901 gates, and these conditional proposal scores omit "
        "calibration uncertainty. Neither all-six nominal candidate passes every local gate. "
        "All ten currently accepted 53923 graph tracks have a single polynomial piece, so a "
        "multi-piece graph join is not demonstrated as the explanation.", "",
        "![Family-excluded candidate comparison](identity_family_excluded_comparison.png)", "",
        "## Joint test of the receiver split", "",
        "Next, starting from the accepted 71.216% observation mask, change the two RX1 curved "
        "nominations to 67953 while retaining the RX2 quartet as 53923. Test both with and "
        "without the additional 62-point CH2 curve proposed for 67953. Keep all earlier "
        "calibration and predictive observations, priors, gates, c-arm matching and cold "
        "5-by-48 search budget. The all_RX1 variants also change the retained RX1 CH4 and CH6 "
        "predictive fragments to 67953: four earlier tracks containing 100 points change identity. "
        "The constrained variants refine each cold proposal "
        "for five phase rounds with at most 40 position steps per round, requiring a 0.01 "
        "interior margin on the unchanged gates. Geographic errors below are diagnostics, not trial selectors.", "",
        "| Proposal | Paired gates | Failed curved c0 / fitted c | Failed predictive c0 / fitted c | Position error c0 / fitted c, km |",
        "|---|---|---:|---:|---:|"]
    failure_notes = []
    for proposal in proposals:
        counts = [sum(not r["compatible"] for r in proposal["arms"][a]["gates"]["tracks"])
                  for a in ("c0", "fitted_c")]
        linear_counts = [sum(not r["compatible"] for r in proposal["arms"][a]["linear_gates"])
                         for a in ("c0", "fitted_c")]
        errors = [position_error(proposal["arms"][a]["endpoint_latlon"]) for a in ("c0", "fitted_c")]
        lines.append(f"| {proposal['name']} | {'PASS' if proposal['paired_valid'] else 'FAIL'} | "
                     f"{counts[0]} / {counts[1]} | {linear_counts[0]} / {linear_counts[1]} | {errors[0]:.3f} / {errors[1]:.3f} |")
        for arm in ("c0", "fitted_c"):
            failed = [r["component"] for r in proposal["arms"][arm]["gates"]["tracks"] if not r["compatible"]]
            failure_notes += ["", f"{proposal['name']} {arm} failed curves: " + (", ".join(failed) or "none") + "."]
    lines += failure_notes
    lines += ["", "The whole-RX1 constrained alternatives pass both c arms. On the matched "
        "original observation mask, the split's negative-twice RF bound is 19519.402 / "
        "19530.978, versus 19560.662 / 19571.100 before: gains of 41.260 / 40.122 with "
        "unchanged observations, powers and search constraints. Its position error is "
        "1.240 / 0.943 km, versus 3.867 / 3.636 km. This supports the split independently "
        "of GPS scoring. It does not establish a unique physical transmitter identity.", "",
        "Adding CH2 raises association to 73.175% with 1.577 / 1.343 km error. Its raw bound "
        "must not be compared to a different observation mask. Coverage favors this branch; "
        "the higher-coverage branch does not yield the smallest position error. The successful "
        "repair needed the RX1 predictive fragments to change family as well as the curved "
        "pair, followed by gate-constrained refinement; changing the curved pair alone "
        "leaves inconsistent predictive evidence. The receiver-specific identity split is "
        "a better-supported explanation than blaming a graph join or declaring all 53923 "
        "evidence incorrect. RX2 retains its 53923 assignment.", "",
        "## Direct sky verification", "",
        "Every associated observation is propagated directly from its nominal causal TLE at "
        "its original measurement time using SGP4, with **zero fitted phase/orbit correction**. "
        "Every catalogue element's epoch and collection timestamp precedes the scan cutoff. "
        "The station authority matches the recorded radio and is valid at the scan time. Its "
        "receiver-ID mapping supplies RX1 west / RX2 east; for a level mount, the nominal "
        "20-degree outward tilt implies 70-degree elevation. Connector mapping remains "
        "provisional; installed elevation, beam width and obstructions are unmeasured. "
        "The sky calculation assumes zero-metre observer altitude; actual altitude is unavailable.", "",
        "For the latest 73.175% model at the c0 RF estimate all 2,316 associated points are "
        "above the horizon; minimum elevation is 34.060 degrees, maximum nominal off-axis "
        "angle 48.062 degrees, and none "
        "is behind the nominal feed axis. The fitted-c audit gives the same conclusion. "
        "An evaluation-only check at the supplied coordinate gives 34.092 degrees minimum "
        "elevation and 47.995 degrees maximum off-axis angle. This coordinate never feeds back into inference.", "",
        "Eight nominal-TLE points exceed 45 degrees off-axis in c0 (seven in fitted-c). "
        "The earlier adjusted-orbit audit's four-point count uses fitted "
        "phase/orbit corrections, so it is a different sensitivity calculation. Neither "
        "45 degrees nor any other unmeasured beam width is used as a selection threshold.", "",
        "| Satellite | Points RX1 / RX2 | Nominal minimum elevation | Nominal maximum off-axis |",
        "|---|---:|---:|---:|"]
    for n in sorted({int(r["norad"]) for r in points}):
        group = [r for r in points if int(r["norad"]) == n]
        counts = [sum(int(r["receiver"]) == rx for r in group) for rx in (1, 2)]
        lines.append(f"| {n} | {counts[0]} / {counts[1]} | "
            f"{min(float(r['elevation_deg']) for r in group):.2f}° | "
            f"{max(float(r['nominal_off_axis_deg']) for r in group):.2f}° |")
    lines += ["", "![Direct nominal sky directions through time](" + latest_name + "_direct_nominal_sky_time_audit.png)", "",
        "![All 17 nominal satellite directions by receiver](sky_split_73percent_c0_nominal.png)", "",
        "Horizon visibility is verified. Reception within a measured antenna beam cannot be "
        "certified from the available pose and pattern records. The near-zenith overlap of "
        "the two axes makes seeing the same satellite on both receivers plausible.", "",
        "## Evidence and reproduction", "",
        "Run the repository venv with `PYTHONPATH=/tmp/algo03-feasible-deps:src:tools` and "
        "single-thread BLAS. Scripts: `tools/verify_ds23_0268_selected_result.py`, "
        "`tools/probe_ds23_0268_identity_holdout.py`, `tools/probe_ds23_0268_selected_identity_split.py`, "
        "and this reporter. Completed identity trials refuse to overwrite prior results. "
        "The first nominal screen attempt was interrupted after noticing it omitted the "
        "event-aware hardware wrapper; its fit was retained and the corrected screen rerun. "
        "No output of that interrupted screen was accepted. The event-aware subtraction has "
        "a regression test. Seventeen focused tests pass, including family exclusion, native "
        "polynomial plotting, membership and receiver geometry checks.", "",
        "[Latest independent replay receipt](" + latest_name + "_independent_replay_audit.json) · "
        "[Latest per-point nominal angles](" + latest_name + "_direct_nominal_sky_points.csv) · "
        "[Family-excluded fit](identity_family_excluded_fit.json) · "
        "[Family-excluded catalogue ranks](identity_family_excluded_screen.json) · "
        "[Accepted 71% split](selected_split_all_RX1_constrained.json) · "
        "[Accepted 73% split](selected_split_all_RX1_with_CH2_constrained.json) · "
        "[Coverage and ownership](accepted_identity_split_coverage.json) · "
        "[Earlier recovery report](README.md)"]
    (OUT / "verification_followup.md").write_text("\n".join(lines) + "\n")
    write(OUT / "verification_followup_provenance.json", dict(
        sources={str(p.relative_to(ROOT)): sha(p) for p in [
            ROOT / "tools/verify_ds23_0268_selected_result.py",
            ROOT / "tools/probe_ds23_0268_identity_holdout.py",
            ROOT / "tools/probe_ds23_0268_selected_identity_split.py",
            ROOT / "tools/report_ds23_0268_verification_followup.py",
            ROOT / "tests/analysis/test_ds23_0268_identity_holdout.py"]},
        plot_point_counts=point_counts,
        latest_sky_audit=latest_sky,
        artifacts={p.name: sha(p) for p in [OUT / "independent_replay_audit.json",
            OUT / "identity_family_excluded_fit.json", OUT / "identity_family_excluded_screen.json",
            *[OUT / (name + ".json") for name in names]]}))


if __name__ == "__main__":
    main()
