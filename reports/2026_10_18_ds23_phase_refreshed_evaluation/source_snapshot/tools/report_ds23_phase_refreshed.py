"""Post-fit DS23 reporting. The reference position is used only in this file."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/2026_10_18_ds23_phase_refreshed_evaluation"
DATASET = ROOT / "reports/2026_10_18_ds23_post_ds22"
REFERENCE = (37.849061591561885, -122.48574968092912)
CENTER = (37.906, -122.545)
MODES = {"fixed150": "fit.json", "radio": "fit_radio_noise.json"}
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coordinates(x):
    return (CENTER[0] + x[1] / 111.0,
            CENTER[1] + x[0] / (111.32 * np.cos(np.deg2rad(CENTER[0]))))


def error(x):
    lat, lon = coordinates(x)
    a, b = np.deg2rad([lat, REFERENCE[0]])
    h = np.sin((a - b) / 2)**2 + np.cos(a) * np.cos(b) * np.sin(
        np.deg2rad(lon - REFERENCE[1]) / 2)**2
    return float(12742. * np.arcsin(np.sqrt(h)))


def selected(document):
    return next(v for v in document["choices"]
                if v["hypothesis"] == document["selected_hypothesis"])


def polynomial(ax, track, raw, color):
    times = np.array(track["times"])
    values = np.array(track["values"])
    observed = np.array([raw[k]["measured_cfo_hz"] for k in track["observation_ids"]])
    for piece in track["pieces"]:
        m = (times >= piece["start_s"]) & (times <= piece["end_s"])
        xx = (times[m] - piece["reference_time_s"]) / piece["time_scale_s"]
        curve = np.polynomial.legendre.legval(xx, piece["coefficients_hz"])
        curve -= values[m] - observed[m]
        curve[np.r_[False, np.abs(np.diff(curve)) > 100000]] = np.nan
        ax.plot(times[m], curve / 1000, color=color, lw=1.15)


def plots(directory, observations, tracks, arms):
    raw = {v["observation_id"]: v for v in observations}
    associations = arms["c0"]["all_graph_associations"]["tracks"]
    accepted = {r["component"]: r["norad"] for r in associations if r["compatible"]}
    sats = sorted(set(accepted.values()))
    colors = {s: plt.colormaps["turbo"]((i + .5) / len(sats)) for i, s in enumerate(sats)}
    accepted_ids = {oid for t in tracks if t["key"] in accepted for oid in t["observation_ids"]}
    channels = sorted({v["channel"] for v in observations})
    blocks = (len(channels) + 3) // 4
    for kind in ("associated", "unassociated"):
        fig, axes = plt.subplots(2 * blocks, 4, figsize=(17, 8 * blocks), sharex=True)
        for rx in (1, 2):
            for j, ch in enumerate(channels):
                ax = axes[(rx - 1) * blocks + j // 4, j % 4]
                lane = [v for v in observations if v["receiver"] == rx and v["channel"] == ch]
                ax.scatter([v["time_s"] for v in lane],
                           [v["measured_cfo_hz"] / 1000 for v in lane],
                           s=4, c=".85", rasterized=True)
                for i, t in enumerate(tracks):
                    if t["receiver"] != rx or t["channel"] != ch:
                        continue
                    is_accepted = t["key"] in accepted
                    if is_accepted != (kind == "associated"):
                        continue
                    color = (colors[accepted[t["key"]]] if is_accepted
                             else plt.colormaps["tab20"](i % 20))
                    pts = [raw[k] for k in t["observation_ids"]]
                    if is_accepted:
                        ax.scatter([v["time_s"] for v in pts],
                                   [v["measured_cfo_hz"] / 1000 for v in pts], s=7, c=[color])
                    polynomial(ax, t, raw, color)
                if kind == "unassociated":
                    pts = [v for v in lane if v["observation_id"] not in accepted_ids]
                    ax.scatter([v["time_s"] for v in pts],
                               [v["measured_cfo_hz"] / 1000 for v in pts],
                               s=7, c="crimson", alpha=.65)
                ax.set_title(f"RX{rx} CH{ch}")
                ax.grid(alpha=.2)
                ax.set(xlabel="Time (s)", ylabel="Native CFO (kHz)")
        fig.suptitle(f"{directory.name}: {kind} GLRT points and graph polynomials\n"
                     "Radio-only noise, c=0; grey = all points; "
                     + ("color = satellite" if kind == "associated"
                        else "red = unassociated points, lines colored by track"))
        fig.tight_layout()
        fig.savefig(directory / f"{kind}_GLRT.png", dpi=135)
        plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
    by_key = {t["key"]: t for t in tracks}
    for ax, arm in zip(axes, ARMS, strict=True):
        rows = arms[arm]["metrics"]["tracks"]
        for row in rows:
            t = by_key[row["component"]]
            ax.scatter(t["end_s"] - t["start_s"], row["native_rms_hz"],
                       s=max(12, row["points"]),
                       c="tab:blue" if row["compatible"] else "crimson", alpha=.65)
        ax.axhline(450, ls="--", c=".4", label="450 Hz RMS gate")
        ax.set(title=arm, xlabel="Curved track duration (s)", ylabel="Conditional RMS (Hz)")
        ax.set_yscale("symlog", linthresh=50)
        ax.grid(alpha=.2)
        ax.legend()
    fig.suptitle(f"{directory.name}: curved calibration candidates; red fails any association gate")
    fig.tight_layout()
    fig.savefig(directory / "track_residuals.png", dpi=140)
    plt.close(fig)


def table(rows):
    header = ("| Scan | Noise | c | Associated / GLRT | % | Tracks | Points/track "
              "| Error km | RMS Hz |\n"
              "|---|---|---|---:|---:|---:|---:|---:|---:|\n")
    return header + "".join(
        f"| {r['case']} | {r['mode']} | {r['arm']} "
        f"| {r['associated_points']:,} / {r['GLRT_points']:,} "
        f"| {r['associated_percent']:.2f} | {r['associated_tracks']} "
        f"| {r['points_per_track']:.1f} | {r['error_km']:.3f} | {r['RMS_hz']:.1f} |\n"
        for r in rows)


def main():
    sample = read(DATASET / "random_sample_10.json")
    rows, validation, members = [], [], []
    for member in sample["selected"]:
        case = member["dataset_label"]
        d = OUT / case
        prepared, receipt = read(d / "prepared.json"), read(d / "receipt.json")
        tracks, observations = read(d / "tracks.json"), read(d / "observations.json")
        noise = read(d / "radio_noise.json")
        assert sha(d / "tracking.json") == prepared["tracking_sha256"]
        assert receipt["latest_max_epoch_utc_ns"] <= receipt["cutoff_utc_ns"]
        assert receipt["latest_max_collection_utc_ns"] <= receipt["cutoff_utc_ns"]
        previous = read(d / "previous_receipt.json")
        assert sha(d / "previous.tle") == previous["catalogue_sha256"]
        assert all(r["epoch_utc_ns"] <= receipt["cutoff_utc_ns"]
                   and r["collected_utc_ns"] <= receipt["cutoff_utc_ns"]
                   for r in previous["sources"].values())
        local_rows, documents = [], {}
        for mode, filename in MODES.items():
            doc = read(d / filename)
            assert doc["status"] == "complete" and doc["GPS_used"] is False
            assert doc["same_observations_candidates_priors_bounds_and_budgets_in_c_pair"]
            old = read(d / filename.replace(".json", "_first_pass.json"))
            assert old["selected_hypothesis"] == doc["selected_hypothesis"]
            choice = selected(doc)
            for arm in ARMS:
                a = choice["arms"][arm]
                old_a = selected(old)["arms"][arm]
                assert np.allclose(a["fit"]["parameters"], old_a["fit"]["parameters"],
                                   atol=1e-8, rtol=0)
                assert abs(a["fit"]["score"] - old_a["fit"]["score"]) < 1e-6
                assoc = a["all_graph_associations"]
                assert assoc == old_a["all_graph_associations"]
                keys = {r["component"] for r in assoc["tracks"] if r["compatible"]}
                ids = [oid for t in tracks if t["key"] in keys for oid in t["observation_ids"]]
                assert len(ids) == len(set(ids)) == assoc["accepted_points"]
                fit = a["fit"]
                last = a["phase_rounds"][-1]
                lat, lon = coordinates(fit["parameters"])
                r = dict(case=case, mode=mode, arm=arm, format=member["recording_format"],
                         GLRT_points=len(observations), graph_points=prepared["graph_points"],
                         graph_tracks=len(tracks), associated_points=len(ids),
                         associated_percent=100 * len(ids) / len(observations),
                         associated_tracks=len(keys), points_per_track=len(ids) / max(1, len(keys)),
                         satellites=assoc["accepted_satellites"],
                         curved_gate_points=a["metrics"]["accepted_points"],
                         RMS_hz=fit["residual_rms_hz"], score=fit["score"],
                         error_km=error(fit["parameters"]), latitude=lat, longitude=lon,
                         zero_phase_error_km=error(doc["zero_phase_control"][arm]["parameters"]),
                         zero_phase_score=doc["zero_phase_control"][arm]["score"],
                         constant_noise_sigma_hz=doc["noise_sigma_hz"],
                         last_phase_change_s=last["max_reference_change_s"],
                         max_posterior_phase_s=max(map(abs, last["posterior_phase_s"])),
                         inner_stop=fit["stopped"], paired_scan_seconds=doc["seconds"])
                rows.append(r)
                local_rows.append(r)
            documents[mode] = doc
        plots(d, observations, tracks, selected(documents["radio"])["arms"])
        compact_noise = {k: v for k, v in noise.items() if k != "per_observation_noise_sigma_hz"}
        write(d / "summary.json", dict(prepared=prepared, receipt=receipt, noise=compact_noise,
                                       results=local_rows,
                                       associations={a: selected(documents["radio"])["arms"][a]
                                                     ["all_graph_associations"] for a in ARMS}))
        text = f"# {case}\n\nRecording `{member['recording_id']}`.\n\n" + table(local_rows)
        text += ("\nRMS covers all nominated curved calibration points before acceptance gates; "
                 "association totals additionally include tracks accepted with calibration frozen. "
                 "GPS errors are post-fit evaluations against the stated rooftop reference.\n\n"
                 "![Associated](associated_GLRT.png)\n\n![Unassociated](unassociated_GLRT.png)\n\n"
                 "![Curved residual RMS](track_residuals.png)\n\n"
                 "[Numerical summary](summary.json) · [Protocol and limitations](../README.md)\n")
        (d / "README.md").write_text(text)
        validation.append(dict(case=case, all_four_arms_complete=True, causal_times_pass=True,
                               input_hash_pass=True, duplicate_associated_points=0,
                               exact_replay_associations=True, endpoint_replay_tolerance_km=1e-8))
        members.append({k: member[k] for k in ("dataset_label", "recording_id", "recording_format",
                                             "captured_utc_ns", "recording_state")})
    with (DATASET / "sample_members.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(members[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(members)
    with (OUT / "results.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    aggregates = []
    for mode in MODES:
        for arm in ARMS:
            group = [r for r in rows if r["mode"] == mode and r["arm"] == arm]
            errors = [r["error_km"] for r in group]
            aggregates.append(dict(mode=mode, arm=arm, scans=len(group),
                                   median_error_km=float(np.median(errors)),
                                   mean_error_km=float(np.mean(errors)), max_error_km=max(errors),
                                   scans_under_1km=sum(e < 1 for e in errors),
                                   associated_points=sum(r["associated_points"] for r in group),
                                   GLRT_points=sum(r["GLRT_points"] for r in group),
                                   associated_tracks=sum(r["associated_tracks"] for r in group)))
    write(OUT / "summary.json", dict(seed=sample["seed"], sampled_scans=10, substitutions=0,
                                     GPS_evaluation_only=True, reference_position=REFERENCE,
                                     results=aggregates))
    sources = read(OUT / "run_sources.json")
    assert all(sha(ROOT / k) == v for k, v in sources.items())
    write(OUT / "validation.json", dict(cases=validation, frozen_run_sources_match=True,
                                        sampled_cases=10, complete_cases=10, substitutions=0))
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fields = (("error_km", "Position error (km)"), ("associated_percent", "Associated GLRT (%)"),
              ("RMS_hz", "All nominated curved RMS (Hz)"), ("associated_tracks", "Accepted tracks"))
    names = [m["dataset_label"].split("-")[-1] for m in members]
    for ax, (field, label) in zip(axes.flat, fields, strict=True):
        for mode in MODES:
            for arm, color in zip(ARMS, ("tab:blue", "tab:orange"), strict=True):
                group = [r for r in rows if r["mode"] == mode and r["arm"] == arm]
                ax.plot(names, [r[field] for r in group], marker="o", ms=4, c=color,
                        ls="--" if mode == "fixed150" else "-", label=f"{mode} / {arm}")
        ax.set(ylabel=label, xlabel="DS23 sample label")
        if field == "RMS_hz":
            ax.set_yscale("log")
        ax.grid(alpha=.2)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Random DS23 transfer pilot: fit and association are separate from localization")
    fig.tight_layout()
    fig.savefig(OUT / "comparison.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for ax, mode in zip(axes, MODES, strict=True):
        group = [r for r in rows if r["mode"] == mode and r["arm"] == "c0"]
        ax.plot(names, [r["zero_phase_error_km"] for r in group], "o--",
                label="Expansion fixed at zero")
        ax.plot(names, [r["error_km"] for r in group], "o-", label="Phase refreshed")
        ax.set(title=mode, xlabel="DS23 label", ylabel="Position error (km)")
        ax.grid(alpha=.2)
        ax.legend()
    fig.suptitle("Same selected identities/aliases: phase expansion control, c=0")
    fig.tight_layout()
    fig.savefig(OUT / "phase_control.png", dpi=150)
    plt.close(fig)
    primary = [r for r in rows if r["mode"] == "radio"]
    report = ("# DS23 random ten-scan phase-refreshed transfer pilot\n\n"
              "All **10 presealed random scans** completed, with no replacements: eight fast and "
              "two adaptive recordings from the 413-member post-DS22 dataset. Seed **2026101801**. "
              "The sample was selected before localization or association results.\n\n"
              "**Coverage transfers better than localization:** radio-only noise, c=0 accepts "
              "21,686 of 30,586 GLRT points (70.90%) in 678 tracks, but median position error "
              "is 2.949 km, maximum 5.000 km, and none of these ten runs is below 1 km. "
              "Fitted c gives almost the same coverage and a 2.955 km median error. "
              "The fixed-noise control has a 2.835 km c=0 median error. These results do not "
              "yet reproduce DSX01's tighter localization.\n\n"
              "![Comparison](comparison.png)\n\n" + table(primary))
    report += "\n| Noise | c | Median error km | Mean km | Max km | Below 1 km | Associated % |\n"
    report += "|---|---|---:|---:|---:|---:|---:|\n"
    for r in aggregates:
        report += (f"| {r['mode']} | {r['arm']} | {r['median_error_km']:.3f} "
                   f"| {r['mean_error_km']:.3f} | {r['max_error_km']:.3f} "
                   f"| {r['scans_under_1km']}/10 "
                   f"| {100*r['associated_points']/r['GLRT_points']:.2f} |\n")
    report += """
The `c=0` and fitted-`c` treatments use the same observations, candidate catalogue, identities,
aliases, other priors and search budgets. The branch is selected by the final c=0 frequency/prior
objective, and reused for fitted c. A lower RF loss or larger accepted fraction is not evidence
of better position accuracy or independently verified satellite identities. `RMS` above includes
all nominated curved calibration points, including failures; accepted counts also include eligible
frozen-calibration extensions. Per-track RMS and raw CFO plots are provided for every scan below.

## Protocol

This applies the [DSX01 model](../2026_10_19_dsx01_phase_refreshed_algorithm/README.md)
to new frozen inputs,
with the finite pilot search and observation-noise adaptations described here.

1. Read the sealed existing tracking contracts. Keep one winning gate-passing fractional GLRT
   CFO per probe; withhold no points. This is existing CFO reanalysis, not a new RF collection
   or DSX01's GLRT300 remeasurement. All ten exports succeeded, including both adaptive scans.
2. Use the frozen graph settings, in lanes defined by RX, channel and actual RF. Fit piecewise
   polynomials with alias handling and residual structure checks. Only tracks spanning at least
   20 seconds with at least 250 Hz RMS departure from their best affine fit can calibrate position,
   receiver/band offsets, drifts or satellite corrections. Linear tracks cannot vote for
   calibration.
3. Build a broad regional Starlink catalogue from Space-Track snapshots collected during the
   48 hours preceding the scan. Both collection times and element epochs must be causal. Latest
   elements define the mean; previous distinct causal elements set physical uncertainty directions.
   No satellite whitelist, later TLE or reference GPS is used. The coarse visibility screen uses
   37.5, -122 with a broad elevation guard, not the evaluation position.
4. Search a fixed **25 × 25 km box centered at 37.906, -122.545**, beginning from fresh radio
   state. Use four radio discovery seeds and RF proposals at the center and four corners.
   Rank distinct identity/alias branches using their c=0 center objective, then fully fit the best
   three. Rebuild nuisance and phase states from zero. This pilot does not repeat the earlier
   large radial restart campaign or establish a global optimum.
5. Within each branch use five phase refresh rounds, with up to 48 damped position steps per round.
   Re-expand the orbital frequency curve around the current posterior phase while preserving its
   absolute zero-centered prior. Labels remain fixed inside this continuous solve; alternative
   labels are represented by the finite proposal branches. Keep receiver/band offsets and small
   drifts, physical per-satellite uncertainty modes and regularized per-fragment constants.
   Fit paired c=0 and fitted-c arms.
6. Compare fixed 150 Hz observation noise with a radio-only estimate. The estimate uses
   leverage-corrected residuals from actively curved graph polynomial pieces. A floor-plus-inverse-
   GLRT-margin variance is enabled only when its extra parameter wins BIC. This is an uncertainty
   proxy, not a certified sensor error bar. It uses no GPS, TLE or satellite-fit residuals. Changing
   this covariance can change RF proposals; this is not a fixed-label covariance-only
   ablation, nor a fully marginalized noise-evidence comparison.
7. Apply conditional RMS (450 Hz), regularized fragment-bias (3,000 Hz), residual structure,
   visibility and alias gates. With accepted curved families and calibration frozen, test other
   graph tracks against those satellites, including linear tracks. These extensions do not update
   calibration or position. Untracked isolated GLRT points remain unassociated. Counts are unique
   original observation IDs, not polynomial interpolants.

## Phase control

![Phase control](phase_control.png)

For each selected branch the control holds the phase expansion reference at zero, using the same
labels and priors. The refreshed endpoint may improve or worsen GPS error. Scores at different phase
tangent expansions are approximation-dependent and should not be interpreted as an exact common
nonlinear likelihood. The final inner stopping reason and last outer phase-reference change are
retained in the CSV; five outer rounds are a budget, not proof of exact joint convergence.

## Evaluation limits

Position errors are computed **after fitting** against the user-provided rooftop coordinate
**37.849061591561885, -122.48574968092912**. That coordinate was not independently surveyed or
verified for each recording, so errors are conditional on all recordings sharing that reference.
Receiver altitude is zero. This tests transfer to additional recordings and two input formats,
not certified performance at a new geographic location. The recording period overlaps previous DSX01
development; membership is disjoint from DS22, but may overlap other research datasets. There was
no per-scan GPS-driven tuning, point replacement, future TLE selection or satellite preselection.

The sample is deliberately small and mixes input formats. Large errors must not be hidden by pooling
favorable fit scores. This prototype's finite identity search, possible graph mistakes, covariance
approximation and flexible nuisance variables remain possible error sources. The results do not
establish every accepted association is correct. The next useful experiment is an identity/track
ablation of the largest failures with a fixed causal candidate set and matched c controls, rather
than tuning toward these reference coordinates.

## Per-scan evidence

"""
    for m in members:
        case = m["dataset_label"]
        report += (f"- [{case}]({case}/README.md): `{m['recording_id']}` "
                   f"({m['recording_format']}).\n")
    report += """

[Results CSV](results.csv) · [Aggregate JSON](summary.json) · [Validation](validation.json) ·
[Source bindings](run_sources.json) · [DS23 membership](../2026_10_18_ds23_post_ds22/README.md) ·
[All dataset authorities](../2026_10_18_dataset_manifest_archive/README.md) ·
[Final fits](fit_archive_catalogue.json) · [Source snapshot](source_snapshot/README.md) ·
[Verification](verification.json)

The published compact evidence includes native observations, polynomial tracks, causal elements and
receipts, numerical summaries, source snapshots and 32 figures. Large local tracking contracts,
propagated banks and full exploratory histories are retained locally with checksum bindings;
they are not runtime dependencies of the report. Research source snapshots document the experiment
and are not a supported production API.
"""
    (OUT / "README.md").write_text(report)
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
