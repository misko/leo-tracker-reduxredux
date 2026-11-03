"""Bounded, fixed-site diagnosis of the largest remaining S01 GLRT fragment."""

import json
from types import SimpleNamespace

import analyze_dsx01_fixed_site as matching
import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from inventory_clipped_phase_cohort import ROOT, load_study
from run_s01_shared_satellite_prototypes import Prototype
from sgp4.api import Satrec

from leo.analysis.research.robust_polynomial_order import polynomial_orders
from leo.analysis.research.shared_satellite_correction import profile_curve, ridge_shared_fit

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT = ROOT / "reports/2026_10_18_s01_ch2_t000_diagnosis"
PROTOTYPES = ROOT / "reports/2026_10_17_s01_shared_satellite_prototypes"
BRACKET = ROOT / "reports/2026_10_17_s01_ch4_t001_diagnosis"
TARGET = "S01-RX1-CH2-T000"
NORAD = 62811


def hardware(track, beta):
    g = matching.group(track)
    value = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
    if len(beta) == 9:
        value += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
    return value


def evaluate(tracks, values, times, frequency, elevation):
    rows = []
    for t, y in zip(tracks, values, strict=True):
        ix = np.searchsorted(times, t["times"])
        terms = profile_curve(y, t["rf_hz"] / 11.5e9 * frequency[ix])
        residual = terms["residual"][0]
        noise = matching.noise_screen(residual, t["times"])
        x = t["times"] - np.mean(t["times"])
        rows.append(
            dict(
                component=t["key"],
                points=len(y),
                rms_hz=float(terms["rms"][0]),
                bias_hz=float(terms["bias"][0]),
                alias=int(terms["aliases"][0]),
                residual_hz=residual,
                times_s=t["times"],
                diagnostics=noise,
                slope_hz_s=float(x @ residual / (x @ x)),
                passing=bool(
                    np.min(elevation[ix]) >= 0
                    and terms["rms"][0] <= 450
                    and abs(terms["bias"][0]) <= 3000
                    and noise["noise_screen_pass"]
                ),
            )
        )
    return rows


def fitted_rate(tracks, values, times, frequency, members, reference):
    features, residuals = [], []
    for i in members:
        t = tracks[i]
        q = t["rf_hz"] / 11.5e9
        r = values[i] - q * frequency[np.searchsorted(times, t["times"])]
        r += round(-float(r.mean()) / matching.PERIOD) * matching.PERIOD
        features.append((q * (t["times"] - reference))[:, None])
        residuals.append(r)
    rate, _, _ = ridge_shared_fit(
        features, residuals, np.ones(len(members)), np.array([[1e12]]), np.ones(len(members), bool)
    )
    return float(np.clip(rate[0], -20, 20))


def cost(rows, members):
    return sum(min(rows[i]["points"], 50) * rows[i]["rms_hz"] ** 2 for i in members)


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source = json.loads((BRACKET / "bracketing_tles.json").read_text())
    all_results = {}
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        folder = OUTPUT / arm
        folder.mkdir(exist_ok=True)
        study, *_ = load_study("DSX01-S01", fc)
        current = json.loads(
            (PROTOTYPES / "family_extension" / arm / "association.json").read_text()
        )
        old = {r["component"]: r for r in current["rows"]}
        parameters = json.loads(
            (PROTOTYPES / "family_extension" / arm / "parameters.json").read_text()
        )
        fit = json.loads(
            (
                PROTOTYPES.parent / "2026_10_17_s01_phase_sensitivity" / arm / "fit_cap_2.7.json"
            ).read_text()
        )
        beta = np.array(fit["beta"])
        tracks = [t for t in study.tracks if old[t["key"]]["candidate_norad"] == NORAD]
        target = next(i for i, t in enumerate(tracks) if t["key"] == TARGET)
        curved = [i for i, t in enumerate(tracks) if t["key"] in study.curved_keys]
        accepted = [i for i in curved if old[tracks[i]["key"]]["compatible"]]
        times = np.unique(np.concatenate([t["times"] for t in tracks]))
        reference = parameters[str(NORAD)]["reference_time_s"]
        values = [t["values"] - hardware(t, beta) for t in tracks]
        if not fc:
            write(OUTPUT / "target.json", tracks[target])
            write(
                OUTPUT / "polynomial_orders.json",
                polynomial_orders(tracks[target]["times"], tracks[target]["values"]),
            )
            write(
                OUTPUT / "tle_provenance.json",
                {
                    k: source[k][str(NORAD)]
                    for k in ("past", "first_post_collection", "first_future_epoch")
                },
            )
        modes = dict(
            target_phase=[target],
            family_phase=curved,
            target_phase_rate=[target],
            family_phase_rate=curved,
            accepted_curved_phase_rate=accepted,
            omit_target_phase_rate=[i for i in curved if i != target],
        )
        results = {}
        for kind in ("past", "first_future_epoch"):
            proxy = SimpleNamespace(
                method="family_extension",
                origin=source["anchor_utc_ns"],
                satellites={NORAD: Satrec.twoline2rv(*source[kind][str(NORAD)]["lines"])},
                tref={NORAD: reference},
            )
            best = {mode: None for mode in modes}
            grid = np.unique(np.r_[np.linspace(-15, 15, 601), parameters[str(NORAD)]["theta"][0]])
            target_profile = []
            current_rows = None
            for phase in grid:
                f, e = Prototype.forward(proxy, NORAD, np.array([phase, 0.0]), times)
                plain = evaluate(tracks, values, times, f, e)
                target_profile.append(dict(phase_s=float(phase), **plain[target]))
                if phase == parameters[str(NORAD)]["theta"][0]:
                    current_rows = plain
                for mode, members in modes.items():
                    rate = (
                        fitted_rate(tracks, values, times, f, members, reference)
                        if mode.endswith("rate")
                        else 0.0
                    )
                    rows = (
                        evaluate(tracks, values, times, f + rate * (times - reference), e)
                        if rate
                        else plain
                    )
                    score = cost(rows, members)
                    if best[mode] is None or score < best[mode]["cost"]:
                        best[mode] = dict(
                            phase_s=float(phase),
                            rate_hz_s=rate,
                            cost=score,
                            rows=rows,
                            calibration_members=[tracks[i]["key"] for i in members],
                        )
            results[kind] = dict(
                best=best, current_rows=current_rows, target_phase_profile=target_profile
            )
            write(folder / f"{kind}_profiles.json", results[kind])
            print(
                json.dumps(
                    dict(
                        arm=arm,
                        tle=kind,
                        best={
                            mode: dict(
                                phase_s=r["phase_s"],
                                rate_hz_s=r["rate_hz_s"],
                                target_rms=r["rows"][target]["rms_hz"],
                                target_pass=r["rows"][target]["passing"],
                                passing_points=sum(x["points"] for x in r["rows"] if x["passing"]),
                            )
                            for mode, r in best.items()
                        },
                    )
                ),
                flush=True,
            )
        all_results[arm] = results
        write(
            folder / "summary.json",
            {
                kind: {
                    mode: {
                        **{k: v for k, v in result.items() if k != "rows"},
                        "target": result["rows"][target],
                        "passing_points": sum(r["points"] for r in result["rows"] if r["passing"]),
                        "passing_fragments": sum(r["passing"] for r in result["rows"]),
                    }
                    for mode, result in payload["best"].items()
                }
                for kind, payload in results.items()
            },
        )
        render(arm, tracks, values, target, results)
    write(
        OUTPUT / "protocol.json",
        dict(
            target=TARGET,
            baseline="family_extension",
            norad_hypothesis=NORAD,
            position=[matching.LATITUDE, matching.LONGITUDE],
            hardware_frozen=True,
            matched_c0_fitted_c=True,
            phases_s=[-15, 15],
            phase_grid_count=601,
            rate_box_hz_s=[-20, 20],
            all_family_labels_frozen=True,
            linear_calibration=False,
            future_selection="first epoch after S01, chosen before radio fitting",
            conditional_omission_not_independent_of_previously_fitted_hardware=True,
            target_only_models_diagnostic_not_accepted_calibration=True,
            no_production_association_modified=True,
        ),
    )


def render(arm, tracks, values, target, results):
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), layout="constrained")
    t = tracks[target]
    reference = results["past"]["best"]["target_phase"]["rows"][target]
    aligned = values[target] + reference["alias"] * matching.PERIOD - reference["bias_hz"]
    for kind, label in (("past", "Causal TLE"), ("first_future_epoch", "First later-epoch TLE")):
        for mode, style in (("target_phase", "-"), ("target_phase_rate", "--")):
            result = results[kind]["best"][mode]
            row = result["rows"][target]
            residual = np.array(row["residual_hz"])
            axes[0].plot(
                t["times"],
                (aligned - residual) / 1000,
                style,
                label=f"{label}, {mode}: {row['rms_hz']:.1f} Hz",
            )
            axes[1].plot(t["times"], residual, style, label=f"{label}, {mode}")
    axes[0].scatter(
        t["times"], aligned / 1000, s=12, c="black", label="Target GLRT (constant aligned)"
    )
    for i, tr in enumerate(tracks):
        r = results["past"]["current_rows"][i]
        if tr["key"].split("-")[1] == "RX1":
            axes[2].plot(
                tr["times"],
                r["residual_hz"],
                ".-",
                ms=3,
                alpha=0.8,
                label=f"{tr['key'].replace('S01-', '')} ({'pass' if r['passing'] else 'fail'})",
            )
    axes[0].set(
        title="Largest remaining S01 fragment: RX1 CH2 T000, 80 GLRT points",
        ylabel="Aligned CFO (kHz)",
    )
    axes[1].set(
        title="Best target-only shape fits — diagnostic, not accepted associations",
        ylabel="Residual (Hz)",
    )
    axes[2].set(
        title="62811 candidate family at the existing shared phase (causal TLE)",
        ylabel="Residual (Hz)",
    )
    for ax in axes:
        ax.set(xlabel="Seconds from S01 start")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=7, ncol=2)
    for ax in axes[1:]:
        ax.axhline(0, color="black", lw=0.6)
    fig.savefig(OUTPUT / arm / "target_and_family.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    run()
