"""Post-fit DSX01 root-cause report; evaluation GPS never flows into inference."""

# ruff: noqa: E501

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from investigate_dsx01_localization_failures import OUTPUT
from localize_merged_track_catalogue import distance_km
from report_dsx01_radial_restarts import REFERENCE, geographic_position, truth_position
from run_dsx01_joint_descent import ARMS, CASES

STAGES = ("core", "family", "track", "group", "variants", "hypotheses", "segments",
          "combinations", "coordinate", "prior_controls", "postfit_diagnostics",
          "calibration_policy", "bias_scale", "orbit_floors")
STAGES += ("regional_candidates", "numerical_checks")
COLORS = dict(c0="tab:blue", fitted_c="tab:orange")

INTERPRETATION = {
    "DSX01-S01": (
        "The phase tangent approximation is a confirmed source of bias: refreshing it reduces "
        "error from 1.117 to 0.557 km without changing a label, point or prior. The remaining "
        "offset is sensitive to several useful families, rather than dominated by the worst "
        "residual. Deleting 69433 reaches 0.198 km, but that choice uses GPS and does not "
        "authenticate an incorrect identity. Removing the larger 62811 family instead worsens "
        "error to 1.274 km. There are no archived multi-piece calibration joins here.",
        "Keep phase refresh and all original points. A one-scalar RF-selected fragment-offset "
        "prior of 200 Hz gives 0.477 / 0.435 km (c0 / fitted c). This is a parsimonious candidate "
        "for testing on unseen scans, not evidence for deleting a particular satellite. "
        "It also raises c0 unweighted all-point CFO RMS from 362 to 889 Hz: the robust "
        "frequency/prior bound can favor tighter constants while accommodating badly "
        "explained fragments through lower noise precision. This is not an improvement "
        "in explaining every point, and should not be promoted on position error alone."
    ),
    "DSX01-S02": (
        "Phase refresh removes part of the bias (1.548 to 1.117 km). A single-family deletion "
        "can reach 0.664 km by removing 66623, but that is a 40-point single-track constraint, "
        "and a GPS improvement is insufficient to prove its identity wrong. No archived "
        "multi-piece calibration join exists. Radio covariance and prior assumptions have "
        "greater demonstrated leverage: a 1 Hz/s receiver mean-drift prior reaches 0.252 km, "
        "and the fixed OU noise control reaches 0.103 km. These hypotheses remain unverified "
        "hardware/noise explanations; their success on this scan alone is not validation.",
        "The RF-selected 300 Hz independent track-offset scale reaches 0.424 / 0.560 km with "
        "no deletions or new per-track coefficients. Prefer this measured simple candidate "
        "over a GPS-based satellite blacklist. Independently validate noise correlation and "
        "receiver drift before adopting the more impressive OU result."
    ),
    "DSX01-S03": (
        "The original 5.500 km error was largely numerical: phase refresh reaches 1.571 km. "
        "The remaining displacement is not explained solely by any one tested satellite "
        "family: the best single-family deletion still has 1.051 km error. Removing the "
        "largest-influence pair/triple does not resolve it either. The only archived join, "
        "RX1 CH4 T002, can be separated into actively curved pieces, but the point-preserving "
        "refit worsens error to 1.649 km. Rechecking active curvature excludes one 19-point "
        "track and barely changes error (1.554 km). At GPS the weighted frequency-data cost "
        "is actually lower, while the total prior/Gamma/log-volume objective prefers the "
        "displaced endpoint. This directly implicates model regularization/calibration "
        "ambiguity in addition to the corrected phase approximation.",
        "A 20 Hz receiver-smooth prior reaches 0.438 km without adding coefficients, but "
        "worsens the RF objective by about 183; selecting it because of GPS would be oracle "
        "tuning. The RF-selected offset scale and a lower-loss alternate identity both "
        "worsen position. Keep the numerical correction; obtain independent receiver "
        "stability constraints before claiming a remaining sub-km solution."
    ),
    "DSX01-S04": (
        "This is the clearest unresolved case. Phase refresh leaves approximately the same "
        "1.85 km displacement. No single family deletion reaches 1 km, no archived multi-piece "
        "calibration join exists, and the most influential individual track moves the fit by "
        "less than 0.41 km. Removing the large 59540 family (415 points) worsens error to "
        "2.860 km. The full-box atlas contributes 23 distinct hypotheses; its own best "
        "candidate has 2.702 km error and worse RF loss than the retained incumbent. Thus "
        "expanding this finite pool is not a solution. These experiments cannot rule out an "
        "untested joint identity combination or actual causal-orbit error.",
        "A linear-only receiver calibration reaches 1.124 km, RF-gated calibrators reach "
        "1.376 km, and an RF-selected 300 Hz track-offset scale reaches 1.647 / 1.878 km. "
        "None is a demonstrated sub-km correction. Do not force a TLE adjustment or discard "
        "the strongest family to manufacture agreement. The next discriminating evidence "
        "is independently measured calibration stability or a better validated causal "
        "orbital covariance, followed by broader joint identity search."
    ),
    "DSX01-S05": (
        "Refreshing the inaccurate phase tangent worsens GPS error from 1.406 to 1.887 km "
        "while improving RF loss. The earlier apparent accuracy partly relied on cancellation "
        "with a numerical approximation error. No one-family deletion resolves the remaining "
        "bias (best 1.582 km), no archived multi-piece join exists, and hard RF-gate rejection "
        "worsens error to 3.118 km. Allowing more orbital flexibility also worsens position. "
        "The strongest demonstrated simple lever is the independent fragment-constant prior.",
        "Learning one common scale from RF evidence selects 100 Hz and reaches 0.998 / "
        "1.010 km while retaining all points and identities. Treat this as approximately "
        "1 km, not a robust pass of a sharp 1 km threshold. The same scale-learning policy "
        "fails to improve S03, so it is a promising candidate rather than a validated "
        "universal correction."
    ),
}


def rf_union(record):
    """Retain the incumbent when extending a candidate pool; never consult GPS."""
    choices = [("phase-refreshed incumbent", {
        a: record["core"]["arms"][a]["refreshed"] for a in ARMS})]
    for stage, key in (("hypotheses", "id"), ("regional_candidates", "node_id")):
        choices.extend((f"{stage}:{r[key]}", {a: r["arms"][a]["fit"] for a in ARMS})
                       for r in record[stage]["choices"])
    choices.append(("identity coordinate moves", {
        a: record["coordinate"]["arms"][a]["fit"] for a in ARMS}))
    return min(choices, key=lambda item: item[1]["c0"]["score"])


def error(fit):
    return distance_km(geographic_position(fit["parameters"]), REFERENCE)


def save(fig, path):
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def read_all():
    data, bindings = {}, {}
    for case in CASES:
        data[case] = {}
        for name in STAGES:
            path = OUTPUT / case / f"{name}.json"
            blob = path.read_bytes()
            record = json.loads(blob)
            if record["case"] != case:
                raise ValueError("scan receipt mismatch")
            if name != "postfit_diagnostics" and record.get("GPS_used") is not False:
                raise ValueError("inference artifact contains or lacks explicit GPS-use audit")
            bindings[str(path.relative_to(OUTPUT))] = hashlib.sha256(blob).hexdigest()
            data[case][name] = record
    return data, bindings


def models(record):
    result = {"zero phase expansion": {a: record["core"]["arms"][a]["baseline"] for a in ARMS}}
    for stage in ("variants", "prior_controls", "orbit_floors"):
        for row in record[stage]["interventions"]:
            name = "phase refresh" if row["control"] == "baseline" else row["control"]
            result.setdefault(name, {})[row["arm"]] = row["fit"]
    return result


def phase_overview(data):
    fig, axes = plt.subplots(1, 3, figsize=(17, 5), layout="constrained")
    x = np.arange(5)
    before = [error(data[c]["core"]["arms"]["c0"]["baseline"]) for c in CASES]
    after = [error(data[c]["core"]["arms"]["c0"]["refreshed"]) for c in CASES]
    axes[0].bar(x - .18, before, .36, label="Fixed zero expansion")
    axes[0].bar(x + .18, after, .36, label="Updated expansion, same priors")
    axes[0].set(ylabel="GPS position error (km)", title="Numerical approximation alone")
    axes[0].legend(fontsize=8)
    for n, label in enumerate(("zero_expansion", "refreshed")):
        values = [data[c]["postfit_diagnostics"]["arms"]["c0"]["approximation"][label]["rms_hz"]
                  for c in CASES]
        axes[1].bar(x + (n - .5) * .36, values, .36, label=label)
    axes[1].set(yscale="log", ylabel="Exact − tangent conditional CFO RMS (Hz)",
                title="Exact SGP4 mean check at each fitted endpoint")
    fractions = [data[c]["postfit_diagnostics"]["arms"]["c0"]["information"][
        "information_trace_fraction"] for c in CASES]
    axes[2].bar(x, fractions, color="tab:purple")
    axes[2].set(yscale="log", ylabel="Position-information trace fraction",
                title="After integrating nuisance coefficients")
    for ax in axes:
        ax.set_xticks(x, [c[-3:] for c in CASES])
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("Causal, matched-data c=0 controls; GPS is post-fit evaluation only")
    save(fig, OUTPUT / "phase_and_identifiability.png")


def convergence_overview(data):
    fig, axes = plt.subplots(1, 3, figsize=(17, 5), layout="constrained")
    for arm in ARMS:
        rows = [next(r for r in data[c]["numerical_checks"]["checks"] if r["arm"] == arm)
                for c in CASES]
        x = np.arange(5)
        for ax, values in zip(axes, (
            [np.linalg.norm(r["profile_gradient"]) for r in rows],
            [r["final_phase_reference_change_s"] for r in rows],
            [r["default_precision_iterations"] for r in rows],
        ), strict=True):
            ax.plot(x, values, ".-", label=arm)
            ax.set_xticks(x, [c[-3:] for c in CASES])
            ax.grid(alpha=.2)
    axes[0].set(yscale="log", title="Final profiled-position gradient",
                ylabel="Norm (loss / km)")
    axes[1].set(yscale="log", title="Last phase-reference update", ylabel="Maximum change (s)")
    axes[2].set(title="Inner noise precision updates", ylabel="Iterations to tolerance")
    axes[0].legend()
    fig.suptitle("Refreshed endpoints: extending inner budget 256 → 1024 changes no objective or precision")
    save(fig, OUTPUT / "numerical_convergence.png")


def model_overview(data):
    names = list(models(data[CASES[0]]))
    fig, axes = plt.subplots(1, 2, figsize=(16, 12), layout="constrained")
    for ax, arm in zip(axes, ARMS, strict=True):
        values = np.array([[error(models(data[c])[name][arm]) for c in CASES] for name in names])
        image = ax.imshow(values, vmin=0, vmax=3, cmap="viridis_r", aspect="auto")
        for (i, j), value in np.ndenumerate(values):
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if value > 1.9 else "black")
        ax.set_xticks(range(5), [c[-3:] for c in CASES])
        ax.set_yticks(range(len(names)), names)
        ax.set_title(f"{arm}: position error (km)")
    fig.colorbar(image, ax=axes, label="km; color saturates at 3 km", shrink=.5)
    fig.suptitle("No point deletion or identity changes: common radio and causal orbit controls")
    save(fig, OUTPUT / "model_position_controls.png")
    fig, ax = plt.subplots(figsize=(11, 12), layout="constrained")
    differences = np.array([[models(data[c])[name]["c0"]["score"]
                              - models(data[c])["phase refresh"]["c0"]["score"]
                              for c in CASES] for name in names])
    image = ax.imshow(differences, vmin=-200, vmax=200, cmap="RdBu_r", aspect="auto")
    for (i, j), value in np.ndenumerate(differences):
        ax.text(j, i, f"{value:+.0f}", ha="center", va="center", fontsize=8,
                color="white" if abs(value) > 140 else "black")
    ax.set_xticks(range(5), [c[-3:] for c in CASES])
    ax.set_yticks(range(len(names)), names)
    ax.set_title("c=0 objective change versus phase-refreshed normal model\n"
                 "Same observations; lower is favored by the frequency/prior bound")
    fig.colorbar(image, ax=ax, label="Δ loss; not a position-accuracy measure", shrink=.5)
    save(fig, OUTPUT / "model_score_controls.png")


def bias_scale_overview(data):
    fig, axes = plt.subplots(3, 5, figsize=(19, 11), layout="constrained")
    for col, case in enumerate(CASES):
        r = data[case]["bias_scale"]
        scales = [v["sigma_hz"] for v in r["choices"]]
        for arm in ARMS:
            fits = [v["arms"][arm]["fit"] for v in r["choices"]]
            minimum = min(v["score"] for v in fits)
            axes[0, col].plot(scales, [v["score"] - minimum for v in fits], ".-",
                              color=COLORS[arm], label=arm)
            axes[1, col].plot(scales, [error(v) for v in fits], ".-", color=COLORS[arm])
            axes[2, col].plot(scales, [v["residual_rms_hz"] for v in fits], ".-",
                              color=COLORS[arm])
        for row in range(3):
            axes[row, col].axvline(r["selected_sigma_hz"], color="black", ls="--",
                                   label="c0 RF-selected scale")
            axes[row, col].set(xscale="log", xlabel="Independent track-offset prior σ (Hz)")
            axes[row, col].grid(alpha=.2)
        axes[0, col].set_title(case)
    axes[0, 0].set_ylabel("Loss above arm's grid minimum")
    axes[1, 0].set_ylabel("GPS error (km), evaluation only")
    axes[2, 0].set_ylabel("Unweighted all-point CFO RMS (Hz)")
    axes[0, 0].legend(fontsize=7)
    fig.suptitle("One scalar learned from RF evidence: improved fit need not improve position")
    save(fig, OUTPUT / "bias_scale_selection.png")


def calibration_overview(data):
    policies = ["remeasured_curvature", "endpoint_stable_curvature", "all_RF_association_gates",
                "stable_curvature_and_gates"]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5), layout="constrained")
    for ax, arm in zip(axes, ARMS, strict=True):
        values = []
        counts = []
        for name in policies:
            selected = [next(r for r in data[c]["calibration_policy"]["interventions"]
                             if r["policy"] == name and r["arm"] == arm) for c in CASES]
            values.append([error(r["fit"]) for r in selected])
            counts.append([r["active_points"] for r in selected])
        image = ax.imshow(values, vmin=0, vmax=3.5, cmap="viridis_r", aspect="auto")
        for (i, j), value in np.ndenumerate(values):
            ax.text(j, i, f"{value:.2f} km\n{counts[i][j]} pts", ha="center", va="center",
                    fontsize=8, color="white" if value > 2 else "black")
        ax.set_yticks(range(4), policies)
        ax.set_xticks(range(5), [c[-3:] for c in CASES])
        ax.set_title(arm)
    fig.colorbar(image, ax=axes, label="GPS error (km)", shrink=.7)
    fig.suptitle("RF-only calibration membership: removing doubtful tracks is not a universal fix")
    save(fig, OUTPUT / "calibration_membership.png")


def ablation_plots(case, record):
    baseline = record["core"]["arms"]["c0"]["refreshed"]
    origin, truth = np.array(baseline["parameters"]), truth_position()
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), layout="constrained")
    for ax, kind in zip(axes, ("family", "track", "group"), strict=True):
        rows = [r for r in record[kind]["interventions"]
                if r["arm"] == "c0" and r["phase"] == "refreshed"]
        for r in rows:
            point = np.array(r["fit"]["parameters"])
            ax.plot(*np.array([origin, point]).T, color="tab:blue", alpha=.45, lw=.8)
            ax.scatter(*point, s=15, color="tab:blue")
        for r in sorted(rows, key=lambda a: a["shift_km"], reverse=True)[:5]:
            label = r["target"].replace(case[-3:] + "-", "")
            ax.annotate(label, r["fit"]["parameters"], fontsize=6,
                        xytext=(3, 4), textcoords="offset points")
        ax.scatter(*origin, marker="X", color="red", s=90, label="Full fit")
        ax.scatter(*truth, marker="*", color="gold", edgecolors="black", s=140,
                   label="GPS, evaluation only")
        ax.set(title=f"Delete one {kind}: {len(rows)} refits", xlabel="East (km)",
               ylabel="North (km)", aspect="equal")
        ax.grid(alpha=.2)
    axes[0].legend(fontsize=7)
    fig.suptitle(f"{case}: influence diagnostics with original nuisance prior support preserved\n"
                 "A large deletion shift does not establish a bad satellite or track")
    save(fig, OUTPUT / case / "ablation_positions.png")
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), layout="constrained")
    families = [r for r in record["family"]["interventions"]
                if r["arm"] == "c0" and r["phase"] == "refreshed"]
    top = sorted(families, key=lambda r: r["shift_km"], reverse=True)[:12][::-1]
    axes[0].barh(range(len(top)), [r["shift_km"] for r in top], color="tab:blue", alpha=.7)
    axes[0].set_yticks(range(len(top)), [f"{r['target']} ({r['deleted_points']} pts)" for r in top])
    axes[0].set(xlabel="Position movement after deletion (km)", title="Largest family influence")
    tracks = {r["component"]: r for r in record["core"]["track_audits"]["c0"]}
    rows = [r for r in record["track"]["interventions"] if r["arm"] == "c0"]
    rms = [tracks[r["target"]]["rms_hz"] for r in rows]
    shifts = [r["shift_km"] for r in rows]
    precision = [tracks[r["target"]]["noise_precision"] for r in rows]
    image = axes[1].scatter(rms, shifts, c=np.log10(np.maximum(precision, 1e-8)),
                            cmap="viridis", s=[r["deleted_points"] for r in rows], alpha=.8)
    for r in sorted(rows, key=lambda r: r["shift_km"], reverse=True)[:3]:
        axes[1].annotate(r["target"].replace(case[-3:] + "-", ""),
                         (tracks[r["target"]]["rms_hz"], r["shift_km"]),
                         xytext=(3, 4), textcoords="offset points", fontsize=7)
    axes[1].set(xscale="log", xlabel="Full-model conditional track RMS (Hz)",
                ylabel="Position movement after track deletion (km)",
                title="Bad residuals versus actual position influence")
    fig.colorbar(image, ax=axes[1], label="log10 noise precision; size = point count")
    for ax in axes:
        ax.grid(alpha=.2)
    save(fig, OUTPUT / case / "family_and_track_influence.png")


def loss_plots(case, record):
    r = record["postfit_diagnostics"]["arms"]["c0"]["evaluated"]
    blind, truth = r["blind"]["parts"], r["GPS_diagnostic_only"]["parts"]
    keys = [k for k in blind if k != "diagonal_noise_volume"]
    difference = np.array([truth[k] - blind[k] for k in keys])
    fig, axes = plt.subplots(1, 2, figsize=(16, 6), layout="constrained")
    axes[0].barh(range(len(keys)), difference,
                 color=["firebrick" if d > 0 else "tab:blue" for d in difference])
    axes[0].set_yticks(range(len(keys)), [k.replace("_", " ") for k in keys])
    axes[0].set(title="Why the model favors its displaced endpoint",
                xlabel="Cost at GPS − cost at blind minimum")
    a = {v["norad"]: v for v in r["blind"]["families"]}
    b = {v["norad"]: v for v in r["GPS_diagnostic_only"]["families"]}
    delta = {j: sum(b[j][k] - v[k] for k in ("weighted_frequency_cost", "phase_prior",
                                             "orbit_prior", "track_constant_prior"))
             for j, v in a.items()}
    selected = sorted(delta, key=lambda j: abs(delta[j]), reverse=True)[:10][::-1]
    axes[1].barh(range(len(selected)), [delta[j] for j in selected], color="tab:purple")
    axes[1].set_yticks(range(len(selected)), [str(j) for j in selected])
    axes[1].set(title="Leading satellite contributions (partial decomposition)",
                xlabel="Δ weighted data + phase/orbit/track priors\n"
                       "Shared calibration, Gamma terms and log-volume excluded")
    for ax in axes:
        ax.axvline(0, color="black", lw=.6)
        ax.grid(axis="x", alpha=.2)
    fig.suptitle(f"{case}: GPS is an oracle diagnostic here, never a fit input")
    save(fig, OUTPUT / case / "objective_pressure.png")


def association_plot(case, record):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), layout="constrained")
    base = record["core"]["arms"]["c0"]["refreshed"]
    for name, marker, color, choices, selected_key, id_key in (
        ("13-start RF bank", "o", "tab:blue", record["hypotheses"]["choices"],
         record["hypotheses"]["selected_id"], "id"),
        ("Full 25 km box RF atlas", "s", "tab:green", record["regional_candidates"]["choices"],
         record["regional_candidates"]["selected_id"], "node_id"),
    ):
        scores = [r["arms"]["c0"]["fit"]["score"] - base["score"] for r in choices]
        errors = [error(r["arms"]["c0"]["fit"]) for r in choices]
        axes[0].scatter(scores, errors, marker=marker, color=color, label=name, s=35, alpha=.7)
        selected = next(r for r in choices if r[id_key] == selected_key)
        axes[0].scatter(selected["arms"]["c0"]["fit"]["score"] - base["score"],
                         error(selected["arms"]["c0"]["fit"]), marker="*", color=color,
                         s=160, edgecolors="black")
    value = record["coordinate"]["arms"]["c0"]["fit"]
    axes[0].scatter(value["score"] - base["score"], error(value), marker="D", s=65,
                     color="tab:purple", label="Family/track identity recombination")
    axes[0].axhline(error(base), color="red", ls="--", lw=.8)
    axes[0].axvline(0, color="black", ls=":", lw=.8)
    axes[0].set(xlabel="Δ same-data model loss versus refreshed incumbent",
                ylabel="GPS position error (km)", title="Do different identities explain the failure?")
    axes[0].legend(fontsize=7)
    family = [r for r in record["family"]["interventions"]
              if r["arm"] == "c0" and r["phase"] == "refreshed"]
    axes[1].scatter([r["deleted_points"] for r in family], [error(r["fit"]) for r in family],
                     color="tab:blue", s=25, label="Delete one satellite family")
    axes[1].axhline(error(base), color="red", ls="--", label="All-family fit")
    axes[1].axhline(1, color="black", ls=":", label="1 km")
    best = min(family, key=lambda r: error(r["fit"]))
    axes[1].annotate(f"Best GPS deletion: {best['target']}\nORACLE diagnostic only",
                      (best["deleted_points"], error(best["fit"])), xytext=(5, 15),
                      textcoords="offset points", fontsize=7)
    axes[1].set(xlabel="Deleted curved GLRT points", ylabel="GPS error after refit (km)",
                title="Can any single family explain the displacement?")
    axes[1].legend(fontsize=7)
    for ax in axes:
        ax.grid(alpha=.2)
    fig.suptitle(f"{case}: stars select by RF loss, never GPS; deletion minimum is explicitly oracle")
    save(fig, OUTPUT / case / "association_hypotheses.png")


def detail_tracks(case, record):
    tracks = record["core"]["tracks"]
    audit = {r["component"]: r for r in record["core"]["track_audits"]["c0"]}
    rows = [r for r in record["track"]["interventions"] if r["arm"] == "c0"]
    selected = [r["target"] for r in sorted(rows, key=lambda r: r["shift_km"], reverse=True)[:2]]
    structured = max(audit.values(), key=lambda r: (r["strongest_residual_step"]["bic_gain"]
                                                   if r["strongest_residual_step"] else -1))
    selected.append(structured["component"])
    selected.extend(r["component"] for r in audit.values() if r["pieces"] > 1)
    selected = list(dict.fromkeys(selected))
    lengths = [len(t["times"]) for t in tracks]
    offsets = np.r_[0, np.cumsum(lengths)]
    post = record["postfit_diagnostics"]["arms"]["c0"]
    paths = []
    for key in selected:
        k = next(i for i, t in enumerate(tracks) if t["key"] == key)
        t = tracks[k]
        sl = slice(offsets[k], offsets[k + 1])
        times = np.array(t["times"])
        y = np.array(post["alias_lifted_values_hz"])[sl]
        noise = np.array(post["point_noise_hz"])[sl]
        center = float(np.median(y))
        predictions = {label: np.array(r["total_prediction_hz"])[sl]
                       for label, r in post["evaluated"].items()}
        nominal = np.array(post["evaluated"]["blind"][
            "nominal_orbit_plus_conditional_calibration_hz"])[sl]
        z = (times - times.mean()) / max(float(np.ptp(times)), 1)
        degree = audit[key]["polynomial"]["degree"]
        coefficients = np.polynomial.polynomial.polyfit(z, y, degree, w=1 / noise)
        poly = np.polynomial.polynomial.polyval(z, coefficients)
        fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True, layout="constrained")
        axes[0].scatter(times, y - center, color="black", s=12, label="Original GLRT CFO")
        for label, prediction in predictions.items():
            axes[0].plot(times, prediction - center, lw=1, label=label)
        axes[0].plot(times, nominal - center, ls="--", color="gray", lw=.8,
                     label="Nominal causal orbit + conditional RX/track calibration")
        axes[0].set(ylabel="Alias-lifted CFO − median (Hz)")
        axes[0].legend(fontsize=7)
        axes[1].plot(times, y - poly, ".-", markersize=4, lw=.6, color="black")
        axes[1].fill_between(times, -noise, noise, color="gray", alpha=.2, label="Radio ±1σ")
        axes[1].set(ylabel=f"Raw degree-{degree} polynomial residual (Hz)")
        for label, prediction in predictions.items():
            axes[2].plot(times, y - prediction, ".-", markersize=3, lw=.7, label=label)
        axes[2].fill_between(times, -noise, noise, color="gray", alpha=.2)
        axes[2].set(ylabel="Orbit + calibration residual (Hz)", xlabel="Scan time (s)")
        for ax in axes:
            ax.axhline(0, color="black", lw=.5)
            for piece in t["pieces"][:-1]:
                ax.axvline(piece["end_s"], color="green", lw=1, label="Archived join")
            cut = audit[key]["strongest_residual_step"]
            if cut:
                ax.axvline(cut["time_s"], color="red", ls=":", lw=.8)
            ax.grid(alpha=.2)
        influence = next(r["shift_km"] for r in rows if r["target"] == key)
        fig.suptitle(f"{case}: {key}; nominated {audit[key]['norad']}; "
                     f"{len(times)} points; {len(t['pieces'])} archived polynomial piece(s)\n"
                     f"Deleting this track moves position {influence:.3f} km; "
                     f"noise precision {audit[key]['noise_precision']:.4g}\n"
                     "Red dotted line: strongest residual-step probe, not proof of a join")
        stem = key.replace("/", "_")
        save(fig, OUTPUT / case / f"track_{stem}.png")
        starts = np.arange(np.floor(times.min() / 20) * 20, times.max() + .01, 20)
        ncols, nrows = min(3, len(starts)), int(np.ceil(len(starts) / 3))
        fig, panels = plt.subplots(nrows, ncols, figsize=(5 * ncols, 3.2 * nrows),
                                    squeeze=False, layout="constrained")
        for ax, start in zip(panels.ravel(), starts, strict=False):
            mask = (times >= start) & (times < start + 20)
            ax.scatter(times[mask], y[mask] - center, s=14, color="black")
            for label, prediction in predictions.items():
                ax.plot(times[mask], prediction[mask] - center, ".-", lw=.7, ms=2, label=label)
            ax.set(title=f"{start:g}–{start + 20:g} s", xlim=(start, start + 20),
                   xlabel="Scan time (s)", ylabel="CFO − full-track median (Hz)")
            ax.grid(alpha=.2)
        for ax in panels.ravel()[len(starts):]:
            ax.axis("off")
        panels.ravel()[0].legend(fontsize=6)
        fig.suptitle(f"{key}: original GLRT CFO in 20-second segments")
        save(fig, OUTPUT / case / f"zoom20_{stem}.png")
        paths.append(dict(component=key, detail=f"track_{stem}.png", zoom=f"zoom20_{stem}.png"))
    return paths


def pair_errors(pair):
    return " / ".join(f"{error(pair[a]):.3f}" for a in ARMS)


def case_report(case, record, details):
    full = {a: record["core"]["arms"][a]["refreshed"] for a in ARMS}
    family = [r for r in record["family"]["interventions"]
              if r["arm"] == "c0" and r["phase"] == "refreshed"]
    track = [r for r in record["track"]["interventions"] if r["arm"] == "c0"]
    best_family = min(family, key=lambda r: error(r["fit"]))
    best_track = min(track, key=lambda r: error(r["fit"]))
    regional = record["regional_candidates"]
    selected_name, selected_pair = rf_union(record)
    bias = record["bias_scale"]
    chosen_bias = next(r for r in bias["choices"] if r["sigma_hz"] == bias["selected_sigma_hz"])
    text = [f"# {case}: localization root cause", "", "[All-scan report](../README.md)", "",
            "## Finding and smallest defensible correction", "",
            *[paragraph for item in INTERPRETATION[case] for paragraph in (item, "")],
            "## Controlled position results", "",
            "Errors below are **c0 / fitted c**, km. GPS is evaluation only.", "",
            "| Intervention | Position error (km) | Interpretation |",
            "|---|---:|---|",
            f"| Fixed zero phase expansion | {pair_errors({a: record['core']['arms'][a]['baseline'] for a in ARMS})} | Earlier joint-descent model |",
            f"| Phase refresh, same labels and priors | {pair_errors(full)} | Numerical correction only |",
            f"| Best single-family deletion by GPS | {error(best_family['fit']):.3f} (c0) | ORACLE diagnostic: delete {best_family['target']}, {best_family['deleted_points']} points |",
            f"| Best single-track deletion by GPS | {error(best_track['fit']):.3f} (c0) | ORACLE diagnostic: delete {best_track['target']} |",
            f"| Expanded RF pool, retaining incumbent | {pair_errors(selected_pair)} | RF-selected {selected_name}; atlas adds {len(regional['choices'])} hypotheses |",
            f"| RF-learned independent offset σ={bias['selected_sigma_hz']:g} Hz | {pair_errors({a: chosen_bias['arms'][a]['fit'] for a in ARMS})} | One learned scalar; no GPS selection |", "",
            "Deletion experiments preserve the original nuisance prior support for all "
            "remaining observations. Their losses cannot be compared across different "
            "observation masks. A deletion improving GPS error is evidence of influence, "
            "not authentication that a satellite identity is wrong.", "",
            "## Satellite and track evidence", "",
            "![Satellite identity and deletion controls](association_hypotheses.png)", "",
            "![Leave-family/track/receiver-band/time-block positions](ablation_positions.png)", "",
            "![Influence and residual reliability](family_and_track_influence.png)", "",
            "Largest family movements are listed below, selected without GPS. "
            "Several influential constraints can pull toward the correct position.", "",
            "| Deleted family | Points | Position movement (km) | GPS error after deletion (km) |",
            "|---|---:|---:|---:|"]
    for r in sorted(family, key=lambda r: r["shift_km"], reverse=True)[:8]:
        text.append(f"| {r['target']} | {r['deleted_points']} | {r['shift_km']:.3f} | {error(r['fit']):.3f} |")
    text += ["", "## Why frequency fit prefers the displaced endpoint", "",
             "![Objective pressure at GPS versus blind endpoint](objective_pressure.png)", "",
             "Positive bars mean a term penalizes the GPS coordinate more than the blind "
             "minimum after re-profiling nuisance coefficients at both positions. The "
             "right-hand plot omits shared calibration, Gamma penalties and log-volume; "
             "it is a partial family decomposition, not a satellite probability.", "",
             "![Fitted receiver calibration and satellite prior pulls](nuisance_calibration.png)", "",
             "These are conditional fitted coefficients under engineering priors. Their size "
             "does not establish actual hardware drift or actual orbit error. Each receiver "
             "has a mean linear drift and band contrast; offsets are separate for the four "
             "receiver/band groups. Smooth terms can absorb position-dependent Doppler. "
             "A large prior pull identifies model pressure, not an authenticated bad identity.", "",
             "## General model controls", "",
             "All rows below preserve the same points, candidate identities and aliases. "
             "Only the declared nuisance model or prior changes. The score change is c0 "
             "relative to phase refresh; smaller loss does not establish better position.", "",
             "| Model | Error c0 / fitted c (km) | RMS c0 / fitted c (Hz) | c0 Δ loss | fitted-c Δ loss |",
             "|---|---:|---:|---:|---:|"]
    for name, pair in models(record).items():
        rms = " / ".join(f"{pair[a]['residual_rms_hz']:.2f}" for a in ARMS)
        text.append(f"| {name} | {pair_errors(pair)} | {rms} | "
                    f"{pair['c0']['score'] - full['c0']['score']:+.3f} | "
                    f"{pair['fitted_c']['score'] - full['fitted_c']['score']:+.3f} |")
    text += ["", "The RF-selected common fragment-offset scale is an additional one-scalar "
             "empirical-Bayes experiment, shown in the all-scan scale figure. All physical "
             "orbit-floor experiments leave the nominal causal TLE unchanged and add no "
             "coefficients. The expanded eccentricity control does add two supported-satellite "
             "physical modes; its Gaussian integration includes a volume penalty.", "",
             "## Multiple-family and receiver/time controls", "",
             "The three most influential families were selected by position movement, not "
             "GPS improvement. All three pairs and their triple were then removed. This is "
             "a bounded influence probe, not exhaustive multi-satellite subset search.", "",
             "| Deleted families | Points removed | Error c0 / fitted c (km) |",
             "|---|---:|---:|"]
    combinations = record["combinations"]["interventions"]
    for ids in dict.fromkeys(tuple(r["deleted_satellites"]) for r in combinations):
        rows = {a: next(r for r in combinations if tuple(r["deleted_satellites"]) == ids
                        and r["arm"] == a) for a in ARMS}
        text.append(f"| {', '.join(ids)} | {rows['c0']['deleted_points']} | {pair_errors({a: rows[a]['fit'] for a in ARMS})} |")
    text += ["", "| Deleted receiver/band or time group | Points removed | Error c0 / fitted c (km) |",
             "|---|---:|---:|"]
    groups = record["group"]["interventions"]
    for target in dict.fromkeys(r["target"] for r in groups):
        rows = {a: next(r for r in groups if r["target"] == target and r["arm"] == a) for a in ARMS}
        text.append(f"| {target} | {rows['c0']['deleted_points']} | {pair_errors({a: rows[a]['fit'] for a in ARMS})} |")
    text += ["", "## Calibration membership and joins", "",
             "| RF-only calibration policy | Calibrating points | Error c0 / fitted c (km) |",
             "|---|---:|---:|"]
    policies = record["calibration_policy"]["interventions"]
    for name in dict.fromkeys(r["policy"] for r in policies):
        rows = {a: next(r for r in policies if r["policy"] == name and r["arm"] == a) for a in ARMS}
        text.append(f"| {name} | {rows['c0']['active_points']} | {pair_errors({a: rows[a]['fit'] for a in ARMS})} |")
    joined = [r for r in record["core"]["track_audits"]["c0"] if r["pieces"] > 1]
    text += ["", f"There are **{len(joined)} archived multi-piece calibration tracks** in this scan. "
             "A single polynomial can still contain a misclustered point; zero archived "
             "joins does not prove every original point assignment correct. Split probes "
             "test the three strongest residual-step candidates and every archived join. "
             "A residual step can also indicate orbit mismatch. Each new calibration "
             "piece must retain at least 20 s and 250 Hz RMS departure from an affine "
             "line, so a split cannot introduce linear-only offset calibrators.", "",
             "| Split target | Cut | Result |", "|---|---:|---|"]
    for row in record["segments"]["choices"]:
        if "arms" not in row:
            text.append(f"| {row['component']} | point {row['cut']} | Ineligible: {row['reason']} |")
        else:
            f = row["arms"]["c0"]
            change = f["penalized_score"] - full["c0"]["negative_twice_elbo"]
            text.append(f"| {row['component']} | {row['cut_time_s']:.2f} s | "
                        f"{pair_errors({a: row['arms'][a]['fit'] for a in ARMS})} km; "
                        f"Δ full bound + cut penalty {change:+.3f} |")
    text += ["", "The split comparison uses the full normalized variational bound and "
             "an additional `3 log(n)` cut-search penalty because splitting changes "
             "the noise-group normalization. No original point is dropped or duplicated.", "",
             "## Original GLRT evidence and 20-second views", "",
             "Tracks below were chosen by largest deletion influence, largest residual-step "
             "evidence, and archived join membership—not by GPS improvement. The blue/orange "
             "model curves include orbit and fitted calibration; the nominal causal-orbit "
             "curve uses the same conditional calibration for display. GPS curves are "
             "post-fit diagnostics. A polynomial and an orbital model test different things.", ""]
    for item in details:
        text += [f"### {item['component']}", "", f"![Track evidence]({item['detail']})", "",
                 f"[Original CFO in 20-second segments]({item['zoom']})", ""]
    (OUTPUT / case / "README.md").write_text("\n".join(text))


def nuisance_plot(case, record):
    r = record["core"]["arms"]["c0"]
    tracks = record["core"]["tracks"]
    features, coefficient = np.array(r["features"]), np.array(r["coefficient"])
    ns = sum(map(len, r["state"]["smooth"]))
    times = np.concatenate([t["times"] for t in tracks])
    rx = np.concatenate([np.full(len(t["times"]), t["receiver"]) for t in tracks])
    band = np.concatenate([np.full(len(t["times"]), int(t["channel"] > 4)) for t in tracks])
    linear = features[:, 4:8] @ coefficient[4:8]
    smooth = features[:, 8:8 + ns] @ coefficient[8:8 + ns]
    fig, axes = plt.subplots(1, 3, figsize=(18, 5), layout="constrained")
    for receiver in (1, 2):
        for b in (0, 1):
            mask = (rx == receiver) & (band == b)
            order = np.argsort(times[mask])
            name = f"RX{receiver} {'high' if b else 'low'}"
            for ax, values in zip(axes[:2], (linear, smooth), strict=True):
                ax.plot(times[mask][order], values[mask][order], ".", ms=2, label=name)
    axes[0].set(title="Conditional receiver linear drift", ylabel="Native CFO contribution (Hz)")
    axes[1].set(title="Conditional receiver smooth term", ylabel="Native CFO contribution (Hz)")
    families = r["families"]
    supported = [f for f in families if len(f["owners"]) >= 2]
    prior = np.array(r["prior_penalty"])
    start = 8 + ns + len(families)
    pulls = {f["norad"]: float(np.sqrt(prior[start + 3 * k:start + 3 * k + 3].sum()))
             for k, f in enumerate(supported)}
    for f in families:
        x, y = abs(f["phase_s"]) / f["phase_sigma_s"], pulls.get(f["norad"], 0)
        axes[2].scatter(x, y, s=f["points"] / 2, alpha=.6, color="tab:purple")
        if x > 2.5 or y > 2:
            axes[2].annotate(str(f["norad"]), (x, y), fontsize=7, xytext=(3, 3),
                             textcoords="offset points")
    axes[2].set(xlabel="Absolute phase posterior mean / prior σ",
                ylabel="Norm of standardized physical orbit mean",
                title="Prior pressure; marker size = point count")
    axes[0].legend(fontsize=7)
    for ax in axes[:2]:
        ax.set_xlabel("Scan time (s)")
    for ax in axes:
        ax.grid(alpha=.2)
    fig.suptitle(f"{case}: full-data c=0 phase-refreshed model; conditional, not external calibration")
    save(fig, OUTPUT / case / "nuisance_calibration.png")


def csv_rows(data):
    rows, ablations = [], []
    for case, record in data.items():
        choices = list(models(record).items())
        choices.extend((f"offset_sigma_{r['sigma_hz']:g}", {
            a: r["arms"][a]["fit"] for a in ARMS}) for r in record["bias_scale"]["choices"])
        choices.extend((f"regional_hypothesis_{r['node_id']}", {
            a: r["arms"][a]["fit"] for a in ARMS}) for r in record["regional_candidates"]["choices"])
        for name, pair in choices:
            for arm, f in pair.items():
                point = geographic_position(f["parameters"])
                rows.append(dict(case=case, model=name, arm=arm, error_km=error(f),
                                 latitude=point[0], longitude=point[1], score=f["score"],
                                 residual_rms_hz=f["residual_rms_hz"], points=f["active_points"]))
        for stage in ("family", "track", "group"):
            for r in record[stage]["interventions"]:
                ablations.append(dict(case=case, stage=stage, arm=r["arm"], phase=r["phase"],
                                      target=r["target"], deleted_points=r["deleted_points"],
                                      error_km=error(r["fit"]), movement_km=r["shift_km"]))
    for name, records in (("models_and_candidates.csv", rows), ("deletion_ablations.csv", ablations)):
        with (OUTPUT / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)


def root_report(data):
    text = ["# DSX01: why the graph localization endpoints remain displaced", "",
            "**18 October 2026 · all five scans · causal TLEs · matched c=0 / fitted-c controls**", "",
            "The major confirmed numerical error source is a phase tangent expansion held at "
            "zero while fitting phases of several seconds. Updating the expansion without "
            "moving the absolute prior reduces S03's error from 5.500 to 1.571 km and S01's "
            "from 1.117 to 0.557 km. The remaining failures are model-sensitive. The tests do "
            "not support attributing every scan to one bad satellite or an incorrect track "
            "join, and do not establish a universal sub-km correction.", "",
            "A simple RF-selected common fragment-offset scale helps S01, S02 and S05, but "
            "worsens S03. S04 remains unresolved. More flexible orbital or receiver models "
            "can improve frequency fit while worsening position. The per-scan diagnoses "
            "below distinguish measured numerical causes, model sensitivity and unverified "
            "physical explanations.", "", "## Main controlled results", "",
            "Each cell is **position error c0 / fitted c**, in km. All fits here use the same "
            "original curved GLRT observations and baseline satellite labels. The last "
            "column learns one common offset scale using only the c0 RF bound; both c arms "
            "then use that same scale. It is a separate prototype, not a GPS-selected winner.", "",
            "| Scan | Previous zero expansion | Phase refresh | RF-selected offset σ | Phase refresh + selected σ |",
            "|---|---:|---:|---:|---:|"]
    summary = []
    for case, r in data.items():
        zero = {a: r["core"]["arms"][a]["baseline"] for a in ARMS}
        phase = {a: r["core"]["arms"][a]["refreshed"] for a in ARMS}
        scale = r["bias_scale"]["selected_sigma_hz"]
        selected = next(v for v in r["bias_scale"]["choices"] if v["sigma_hz"] == scale)
        learned = {a: selected["arms"][a]["fit"] for a in ARMS}
        text.append(f"| [{case[-3:]}]({case}/README.md) | {pair_errors(zero)} | {pair_errors(phase)} | {scale:g} Hz | {pair_errors(learned)} |")
        summary.append(dict(case=case, zero_error_km={a: error(zero[a]) for a in ARMS},
                            phase_refreshed_error_km={a: error(phase[a]) for a in ARMS},
                            RF_selected_offset_sigma_hz=scale,
                            selected_scale_error_km={a: error(learned[a]) for a in ARMS}))
    text += ["", "## c ablation: frequency score and position are separate", "",
             "Both arms share points, labels, aliases, other priors and search budgets. "
             "The loss includes the nuisance integration penalty, so an extra fitted "
             "coefficient can improve residuals while increasing loss. RMS includes "
             "all original curved points, including strongly downweighted fragments. "
             "The offset-scale rows use the common scale selected by c0 RF evidence.", "",
             "| Scan | Model | Δ loss (fitted c − c0) | RMS c0 / fitted c (Hz) | Error c0 / fitted c (km) |",
             "|---|---|---:|---:|---:|"]
    for case, r in data.items():
        scale = r["bias_scale"]["selected_sigma_hz"]
        selected = next(v for v in r["bias_scale"]["choices"] if v["sigma_hz"] == scale)
        for name, pair in (
            ("Phase refresh", {a: r["core"]["arms"][a]["refreshed"] for a in ARMS}),
            (f"Offset σ={scale:g} Hz", {a: selected["arms"][a]["fit"] for a in ARMS}),
        ):
            rms = " / ".join(f"{pair[a]['residual_rms_hz']:.2f}" for a in ARMS)
            text.append(f"| {case[-3:]} | {name} | {pair['fitted_c']['score'] - pair['c0']['score']:+.3f} | {rms} | {pair_errors(pair)} |")
    text += ["", "## Phase approximation and nuisance confounding", "",
             "![Numerical phase approximation and nuisance confounding](phase_and_identifiability.png)", "",
             "The exact-minus-tangent check uses the same fitted physical orbit correction "
             "and evaluates its conditional SGP4 mean. CFO discrepancy falls from 49.9–98.3 Hz "
             "to 0.030–0.342 Hz. This establishes numerical agreement, not truth of the causal "
             "TLE. S05 becomes less accurate after the numerical correction, exposing a bias "
             "that had partly cancelled the old approximation error. The right panel is a "
             "local Schur-complement information diagnostic: nuisance integration retains "
             "only 2.1–5.3 × 10⁻⁵ of the known-nuisance trace. This shows strong local confounding; "
             "it is not a calibrated confidence interval or a proof that accurate localization "
             "is impossible.", "", "## Did descent actually converge?", "",
             "The [preceding stepwise-reassociation experiment](../2026_10_18_dsx01_joint_descent/README.md) "
             "ran 81 starts per scan and c arm inside the 10 km disk (810 paths total). "
             "Within each scan/arm the endpoints agreed within 0.08 m; none reached the "
             "outer step cap. It converged tightly to a displaced solution under that "
             "finite-hypothesis objective. Restart agreement does not establish geographic accuracy.", "",
             "![Refreshed endpoint numerical convergence](numerical_convergence.png)", "",
             "For the refreshed model, all ten endpoints also have small profiled-position "
             "gradients and small final phase-reference changes. Increasing the inner "
             "precision-update budget from 256 to 1024 changes neither objective nor "
             "noise precision: the updates already stop at their tolerance. These checks "
             "support focusing on approximation/model bias rather than simply spending "
             "more iterations at the same endpoints. They do not certify a global optimum "
             "over all possible satellite combinations.", "", "## Scan-by-scan diagnosis", ""]
    for case in CASES:
        text += [f"### [{case}]({case}/README.md)", "", *[p for item in INTERPRETATION[case] for p in (item, "")],
                 f"![{case}: deletion and receiver/time influence]({case}/ablation_positions.png)", "",
                 f"![{case}: frequency versus regularization pressure]({case}/objective_pressure.png)", ""]
    text += ["## Association and track-join ablations", "",
             "Every original nominated satellite family and every original curved track "
             "was removed once, in both c arms. Family deletions were tested both before and "
             "after phase refresh. The refreshed phase reference is held fixed within each "
             "deletion series; every deletion independently refits position and reintegrates "
             "all remaining nuisance coefficients from the regional center. Keeping the "
             "original nuisance design prevents deletion from also removing the multi-owner "
             "physical-orbit prior support. Four receiver/band groups and three 100-second "
             "time blocks were independently removed. Three top-influence families supply "
             "all three pair deletions plus their triple; this is not an exhaustive subset "
             "search. Scores for different observation masks are not comparable.", "",
             "| Scan | Curved points | Tracks | Nominated families | Best one-family deletion, km (ORACLE) | Archived multi-piece calibration tracks |",
             "|---|---:|---:|---:|---:|---:|"]
    for case, r in data.items():
        family = [v for v in r["family"]["interventions"] if v["arm"] == "c0" and v["phase"] == "refreshed"]
        best = min(family, key=lambda v: error(v["fit"]))
        joined = sum(t["pieces"] > 1 for t in r["core"]["track_audits"]["c0"])
        text.append(f"| {case[-3:]} | {r['core']['arms']['c0']['refreshed']['active_points']} | {len(r['core']['tracks'])} | {len(family)} | {error(best['fit']):.3f}, remove {best['target']} | {joined} |")
    text += ["", "GPS-selected deletion minima above are deliberately labeled ORACLE. "
             "Improved GPS error after deletion does not identify a false satellite. "
             "There is no external authentication of the satellite labels in this study. "
             "No single-family deletion reaches 1 km in S03–S05; that rejects one tested "
             "family as the sole removable source of each displacement, but does not prove "
             "multiple identities are wrong. Several valid families can pull in competing "
             "directions under an imperfect shared calibration model.", "",
             "Residual structure was examined independently: best degree 1–4 polynomial "
             "with BIC penalty, conditional orbital residual means/slopes/steps, noise "
             "precisions, and each original archived boundary. We tested the strongest "
             "three residual-step cuts plus every archived join per scan. Most cuts would "
             "create a piece without active curvature and are ineligible to calibrate. "
             "The only eligible archived unjoin is S03; it does not improve position. "
             "Large residuals often cause downweighting, so the largest-RMS track is not "
             "necessarily the most influential. Each per-scan report includes the most "
             "influential tracks, strongest residual-step track, every archived joined "
             "track, and original GLRT CFO views in 20-second panels. A point assignment "
             "error within a single archived polynomial remains possible.", "",
             "![RF-only calibration eligibility controls](calibration_membership.png)", "",
             "Rechecking active curvature, endpoint-stable curvature, all conditional "
             "association gates, or both gates and endpoint stability does not fix all "
             "scans. These masks change calibration membership only; excluded points "
             "remain available for later satellite explanation. Losing curvature after "
             "removing an endpoint can also be a duration-threshold effect and is not "
             "proof that the endpoint is an outlier.", "",
             "## Wider RF-only satellite search", "",
             "We refit every distinct hypothesis from the previous 13-start bank, made a "
             "broader causal full-catalogue proposal (`topk=12`, maximum 256), and tried "
             "coherent family and individual-fragment moves between donor hypotheses. "
             "Coordinate search screens all local proposals and fully refits the best "
             "12 per pass for at most two passes. We additionally refit **80 distinct "
             "hypotheses** from 25 cold RF discovery positions spanning the full 25 × 25 km "
             "box (15/10/14/23/18 by scan). Saved atlas positions and nuisance states are "
             "discarded. Every refit starts at the regional center with zero nuisance "
             "and phase-reference initialization. Selection uses c0 loss, and fitted-c "
             "is the matched control. The expanded pool always retains the incumbent.", "",
             "| Scan | RF-selected source from union | Error c0 / fitted c (km) | c0 Δ loss versus refreshed incumbent |",
             "|---|---|---:|---:|"]
    for case, r in data.items():
        source, pair = rf_union(r)
        text.append(f"| {case[-3:]} | {source} | {pair_errors(pair)} | {pair['c0']['score'] - r['core']['arms']['c0']['refreshed']['score']:+.3f} |")
    text += ["", "This search is finite and does not enumerate all joint satellite/alias "
             "assignments. In S03 the RF-preferred alternate identity improves loss while "
             "worsening GPS error. In S04 the atlas-only winner has worse loss than the "
             "incumbent, so it is retained only as a diagnostic alternative, not forced "
             "into the selected solution. Per-scan association plots show both pools.", "",
             "## Nuisance and physical-orbit controls", "",
             "![Position accuracy under model controls](model_position_controls.png)", "",
             "![Same-data RF objective changes](model_score_controls.png)", "",
             "Both figures are needed: better in-sample frequency/prior loss does not "
             "establish better localization. All full-data controls retain identical "
             "observations, labels, aliases, candidate sets, position bounds, five phase "
             "refresh rounds and paired c budgets. Baseline engineering scales include "
             "four RX/band offsets, a 10 Hz/s mean linear drift per RX and 1 Hz/s band "
             "contrast, RX smooth coefficients at 200 Hz, per-satellite absolute phase "
             "σ≥1 s, causal physical orbit modes for satellites observed by at least two "
             "RX/channel owners, and independent fragment constants at 1000 Hz. There "
             "is no free linear Doppler term per satellite in this model.", "",
             "Controls include tighter receiver drift, a 3× phase prior, 3× track constants, "
             "3× orbit modes, two extra eccentricity modes, native-band smooth terms, "
             "a diagonal-plus-OU covariance (150 Hz amplitude, 10 s correlation), 300 Hz "
             "fragment constants, 20 Hz or zero receiver smooth terms, independent "
             "2 Hz/s drifts in each RX/band, combined controls, and a shared satellite "
             "clock hierarchy. Radial/normal physical covariance floors of "
             "(0.1,0.05), (0.5,0.25), and (1,0.5) km alter prior uncertainty without "
             "adding physical parameters or changing nominal TLEs. Mean-motion, "
             "inclination and RAAN corrections are evaluated consistently through SGP4; "
             "exact conditional means were checked for the orbit-floor controls. None "
             "of these floors uniformly improves position.", "",
             "![RF-learned independent fragment-offset scale](bias_scale_selection.png)", "",
             "The offset-scale prototype tries 50, 100, 200, 300, 600 and 1000 Hz and "
             "selects by the same-data c0 variational frequency/prior bound. Both c arms "
             "use the same chosen scale. One hyperparameter costs an additional `log(n)` "
             "BIC penalty relative to the fixed-scale model (recorded in JSON); this "
             "constant does not change which grid value wins. This is finite-grid "
             "empirical Bayes, not a fully marginalized hyperparameter posterior. The "
             "policy is RF-only but developed on DSX01; unseen-location validation "
             "is still needed. Retaining every observation row does not guarantee that "
             "every point is well explained: noise precisions are re-estimated. S01's "
             "selected scale improves position modestly while increasing unweighted RMS "
             "from 362 to 889 Hz. The third row exposes this tradeoff. Do not call a lower "
             "frequency/prior bound a reduction in raw frequency residuals, or promote "
             "a scale based only on its GPS error.", "",
             "## Reproducible scope and leakage controls", "",
             "The input is the existing graph catalogue with archived GLRT300 CFO "
             "remeasurements, not a new RF acquisition. Across five scans it contains "
             "20,084 raw GLRT detections; this investigation preserves 12,724 originally "
             "selected actively curved calibration detections. It does not claim those "
             "are all associated GLRT points or rerun acquisition/GLRT/track construction "
             "for every ablation. Linear tracks can later be associated or overlapped, "
             "but never calibrate offsets or drifts here. Active curvature requires at "
             "least 20 s duration and 250 Hz RMS departure from an affine fit.", "",
             "The regional box remains **25 × 25 km**, centered at **37.906°, −122.545°** "
             "with east/north bounds ±12.5 km. The broader causal visibility catalogue "
             "uses a 250 km radius centered at 37.5°, −122.0° and no identity whitelist. "
             "The evaluation coordinate **37.849061591561885°, −122.48574968092912°** "
             "appears only in the reporting and separate forbidden-as-inference "
             "post-fit diagnostic tool. No GPS value chooses a fit, identity, nuisance "
             "coefficient or RF-selected scale. GPS-best deletions and promising "
             "GPS-error model rows are explicitly retrospective oracle diagnostics. "
             "These controlled ablations optimize position from the box center after "
             "RF discovery; they are not complete pipeline reruns at every map pixel.", "",
             "Receiver altitude remains fixed at 0 m in these controls. The supplied "
             "ground truth contains latitude/longitude only; physical site height was "
             "not inferred or ablated here. This and untested timing/frame effects "
             "remain possible model limitations, alongside unexplored joint identities.", "",
             "Only causal elements are used: both collection time and TLE byte epoch "
             "must precede each scan cutoff. Previous causal elements inform engineering "
             "orbit uncertainty; no following TLE or later observation is read. Candidate "
             "counts are 1707/1479/1422/1427/1424. The read guard rejects future-element, "
             "evaluation-site and unrelated report inputs during inference. The original "
             "joint-descent receipt contributes the identity of its RF-selected mode, "
             "not its saved position or nuisance solution; the baseline fit is replayed "
             "numerically. Source hashes and temporal receipts are saved in each core "
             "artifact. Post-fit GPS loss decomposition is written by a separate tool "
             "and is never read by any fitting/selection tool.", "",
             "The objective integrates Gaussian nuisance coefficients and iterates "
             "Gamma fragment noise precisions. The optimized residual vector includes "
             "weighted frequency innovations, standardized nuisance means, integration "
             "log-volume, Gamma cost, fixed diagonal-noise volume, and visibility cost. "
             "Each position step uses bounded damped Gauss–Newton, at most 48 iterations "
             "per phase round. Refreshed fits use five rounds from zero phase reference; "
             "the phase prior stays centered at absolute zero. Conditional means need "
             "not have exactly zero residual on each short fragment under finite priors; "
             "gates and residual plots diagnose resulting structure. Split comparisons "
             "restore full normalization and add a `3 log(n)` cut penalty. The Gaussian "
             "noise model and engineering prior scales are hypotheses, not calibrated "
             "ground truth.", "", "## What generalizes and what needs more evidence", "",
             "- Phase refresh is a numerical consistency correction that applies at any "
             "location and uses no external GPS or later scan.",
             "- Curvature eligibility, RF-only scale learning, causal candidate discovery "
             "and paired c ablations can run on a single scan. Their form is general, "
             "but the tested scales and model family were developed on DSX01.",
             "- Physical orbit uncertainty uses the latest and previous **causal** "
             "element records. It therefore depends on pre-scan history, not solely "
             "on the current scan. It cannot establish actual TLE accuracy without "
             "independent orbit truth.",
             "- Choosing a satellite deletion, a smoothness scale, or a different model "
             "for each scan because it gives the smallest GPS error is not deployable "
             "evidence. No such GPS-chosen policy is promoted here.", "",
             "The lean next step is to retain phase refresh, compare the RF-only "
             "offset-scale policy on unseen archived scans/locations, and constrain "
             "receiver drift/smoothness using independent calibration evidence. Only "
             "then expand satellite orbit freedom with causal calibrated covariances. "
             "S04 remains the priority unresolved case; no experiment here justifies "
             "claiming its physical cause is known.", "", "## Relation to primary literature", "",
             "TLE mean elements and their propagator must be treated consistently; "
             "a numerically precise fit is not validation of true satellite position. "
             "This distinction follows the [CelesTrak SGP4 tutorial](https://celestrak.org/software/tutorials/sgp4.php) "
             "and motivates the exact conditional-mean checks here.", "",
             "Clock and ephemeris uncertainties are recognized LEO Doppler positioning "
             "limitations. [A Double-Difference Doppler Shift-Based Positioning Framework "
             "with Ephemeris Error Correction of LEO Satellites](https://arxiv.org/abs/2409.05026) "
             "examines corrections with differential/reference information; that reference "
             "infrastructure is not present in these single-scan tests. "
             "[Orbital Errors in LEO Satellite Positioning: Modeling, Analysis, and Bayesian "
             "Calibration](https://arxiv.org/abs/2511.06060) studies Bayesian orbital-error "
             "calibration. These works motivate physical uncertainty models; they do "
             "not authenticate any satellite label or engineering prior used here.", "",
             "## Artifacts and reproduction", "",
             "- [Model scores, residual RMS and coordinates](models_and_candidates.csv).",
             "- [Every family, track and group deletion](deletion_ablations.csv).",
             "- [Machine-readable summary](summary.json) and [artifact validation](validation.json).",
             "- [Component tests and lint verification](verification.json).",
             "- Every scan directory contains all intervention JSON, original point IDs, "
             "source hashes, loss decompositions and linked diagnostic figures.", "",
             "Inference tools: `investigate_dsx01_localization_failures.py`, "
             "`dsx01_failure_followups.py`, `dsx01_failure_prior_controls.py`, "
             "`dsx01_failure_bias_scale.py`, `dsx01_failure_orbit_floors.py`, "
             "`dsx01_failure_regional_candidates.py`. Post-fit-only tools: "
             "`probe_dsx01_failure_postfit.py`, `report_dsx01_failure_investigation.py`.", "",
             "```bash", "OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src:tools \\",
             "  .venv/bin/python tools/report_dsx01_failure_investigation.py", "```", ""]
    (OUTPUT / "README.md").write_text("\n".join(text))
    (OUTPUT / "summary.json").write_text(json.dumps(dict(
        scans=summary, GPS_evaluation_only=True, universal_sub_km_solution_established=False,
        unresolved_case="DSX01-S04"), indent=2))


def validate(data, bindings):
    import re

    audits = []
    for case, r in data.items():
        audit = r["core"]["input_audit"]
        if max(audit["latest_max_epoch_utc_ns"], audit["latest_max_collection_utc_ns"]) >= audit["cutoff_utc_ns"]:
            raise ValueError("noncausal catalogue")
        ids = [i for t in r["core"]["tracks"] for i in t["observation_ids"]]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate original GLRT point")
        for pair in models(r).values():
            if set(pair) != set(ARMS):
                raise ValueError("missing matched c arm")
            for f in pair.values():
                if not np.isfinite(f["score"]) or max(abs(np.array(f["parameters"]))) > 12.5:
                    raise ValueError("invalid full-data fit")
                if f["active_points"] != len(ids):
                    raise ValueError("full-data control changed point support")
        for name in STAGES:
            path = OUTPUT / case / f"{name}.json"
            if hashlib.sha256(path.read_bytes()).hexdigest() != bindings[str(path.relative_to(OUTPUT))]:
                raise ValueError("input artifact changed during rendering")
        audits.append(dict(case=case, points=len(ids), unique_point_ids=True,
                           causal_epoch_and_collection_valid=True,
                           model_count=len(models(r)), matched_c_arms=True))
    missing = []
    for path in OUTPUT.rglob("*.md"):
        for link in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if link.startswith(("http:", "https:", "#")):
                continue
            target = (path.parent / link.split("#")[0]).resolve()
            if not target.exists():
                missing.append(str(target))
    # This file is created immediately below, so its forward README link is valid.
    missing = [p for p in missing if p != str(OUTPUT / "validation.json")]
    if missing:
        raise ValueError(f"broken report links: {missing}")
    artifacts = {str(p.relative_to(OUTPUT)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in OUTPUT.rglob("*") if p.suffix in (".md", ".png", ".csv")}
    receipt = dict(status="complete", scans=audits, inference_artifact_sha256=bindings,
                   report_artifact_sha256=artifacts, broken_local_links=[],
                   generated_figure_count=len(list(OUTPUT.rglob("*.png"))),
                   scientific_limits="Engineering priors, finite identities, no independently verified satellite labels",
                   report_generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUTPUT / "validation.json").write_text(json.dumps(receipt, indent=2))


def main():
    data, bindings = read_all()
    for function in (phase_overview, convergence_overview, model_overview, bias_scale_overview,
                     calibration_overview):
        function(data)
        print(function.__name__, "complete", flush=True)
    for case, record in data.items():
        for function in (ablation_plots, loss_plots, association_plot, nuisance_plot):
            function(case, record)
        details = detail_tracks(case, record)
        case_report(case, record, details)
        print(case, "report complete", flush=True)
    csv_rows(data)
    root_report(data)
    validate(data, bindings)
    print(OUTPUT / "README.md", flush=True)


if __name__ == "__main__":
    main()
