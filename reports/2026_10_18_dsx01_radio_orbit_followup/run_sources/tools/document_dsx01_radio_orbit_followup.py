"""Render the completed matched followup comparison from saved numerical evidence."""

import json
import re

from compare_dsx01_retention_localization import ROOT
from report_dsx01_radio_orbit_followup import CASES, OUTPUT


def run():
    rows = json.loads((OUTPUT / "evaluation_summary.json").read_text())
    details = json.loads((OUTPUT / "frequency_details.json").read_text())
    ablations = json.loads((OUTPUT / "c_ablation.json").read_text())
    final = [r for r in rows if r["final"]]
    variants = list(dict.fromkeys(r["variant"] for r in final))
    table = [
        "| Model | S01 | S02 | S03 | S04 | S05 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    coverage = [
        "| Model, fitted `c` | Accepted curved points | % of curved | Curves | Points/curve | "
        "Common-point RMS, c0 / fitted c (Hz) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in variants:
        pairs = [
            [
                next(
                    r for r in final if r["case"] == c and r["variant"] == variant and r["arm"] == a
                )
                for a in ("c0", "fitted_c")
            ]
            for c in CASES
        ]
        table.append(
            "| "
            + variant
            + " | "
            + " | ".join(
                f"{a['position_error_km']:.3f} / {b['position_error_km']:.3f}" for a, b in pairs
            )
            + " |"
        )
        points = sum(b["white_gate_points"] for a, b in pairs)
        curves = sum(b["white_gate_curves"] for a, b in pairs)
        control = [r for r in ablations if r["variant"] == variant]
        count = sum(r["common_points"] for r in control)
        rms = [
            (
                sum(r[f"native_rms_{a}_hz"] ** 2 * r["common_points"] for r in control)
                / max(1, count)
            )
            ** 0.5
            for a in ("c0", "fitted_c")
        ]
        coverage.append(
            f"| {variant} | {points:,} | {100 * points / 12724:.2f}% | {curves} | "
            f"{points / max(1, curves):.2f} | {rms[0]:.3f} / {rms[1]:.3f} |"
        )
    # Equal three-phase-round budget. The tighter solver replaces, rather than
    # competes against, its otherwise identical 24-precision-iteration version.
    choices = [
        v
        for v in variants
        if v not in ("fixed_3", "fixed_5", "relinearized_3", "relinearized_5", "window_noise")
    ]
    selection = []
    for case in CASES:
        candidates = [
            r for r in final if r["case"] == case and r["arm"] == "c0" and r["variant"] in choices
        ]
        selected = min(candidates, key=lambda r: r["normalized_total"])
        partner = next(
            r
            for r in final
            if r["case"] == case and r["arm"] == "fitted_c" and r["variant"] == selected["variant"]
        )
        selection.append(
            dict(
                case=case,
                variant=selected["variant"],
                error_c0_km=selected["position_error_km"],
                error_fitted_c_km=partner["position_error_km"],
            )
        )
    (OUTPUT / "c0_model_selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    selected_text = "; ".join(
        f"{r['case'][-3:]} {r['variant']} ({r['error_fitted_c_km']:.3f} km)" for r in selection
    )
    driver = details["DSX01-S03/baseline/c0"]["GPS_minus_endpoint_cost"]
    info = json.loads((OUTPUT / "local_information.json").read_text())
    info_table = [
        "| Scan | Baseline local principal scales (km) | Noise-weighted scales (km) |",
        "| --- | ---: | ---: |",
    ]
    for case in CASES:
        cells = []
        for variant in ("baseline", "window_precise"):
            entry = next(
                r
                for r in info
                if r["case"] == case and r["variant"] == variant and r["arm"] == "c0"
            )
            scales = entry["formal_principal_sigma_km"]
            cells.append("undefined" if scales is None else " / ".join(f"{x:.3f}" for x in scales))
        info_table.append(f"| {case[-3:]} | " + " | ".join(cells) + " |")
    text = f"""# DSX01: independent band drifts, exact-orbit references and measured point noise

**The independent all-scan sub-1 km goal remains unmet.** This iteration tests
three remedies and two followups on the original curved population. Noise
weighting helps several scans, and combining it with independent band drifts
brings S02 below 1 km, but S03 and S05 remain unresolved. Better numerical
orbit accuracy does not materially change their positions.

This follows the [published joint analysis](../2026_10_18_dsx01_joint_analysis/README.md).
All **12,724 curved observations** remain in every likelihood. No points are
withheld, labels or integer aliases are changed, future TLEs are used, or RF is
collected. GLRT-300 means **300 pilot symbols per frame at 2.5 MS/s**, measured
in archived 20 ms windows.

## Implemented tests and controls

1. **Independent receiver/band drifts:** replace the RX mean/contrast prior
   (10 and 0.5 Hz/s, implying 0.995 low/high prior correlation) with four
   independent Gaussian rates at either 2 or 10 Hz/s. This changes a declared
   hardware hypothesis; neither scale was selected using GPS error.
2. **Exact physical relinearization:** update mean-motion, inclination, RAAN
   and optional two eccentricity directions around exact combined SGP4
   states. Absolute priors remain centered on the original causal orbit.
   Fixed-reference controls have the same four outer rounds. Mean motion
   preserves scan-midpoint mean longitude.
3. **Measured per-observation noise:** estimate a frame-scatter feature after
   removing an intercept and linear within-window chirp. Calibrate it using
   radio-only polynomial residuals before geography. Enable it only if the
   extra parameter improves radio-only BIC. Retain every observation, with
   fallback scales for unsupported features. All five radio BIC gains are
   positive; this is not evidence of improved localization.

The combination uses the same fixed noise vectors with independent band
drifts. A further all-candidate covariance control gives causal physical
uncertainty to single-owner satellite hypotheses too. The usual requirement
for two RX/channel owners still governs acceptance of orbital corrections;
giving a candidate uncertainty does not authenticate it.

All searches use the **25 × 25 km** Mill Valley box centered at
**37.906°, −122.545°**, 25 grid nodes, three shared `c=0`-selected starts and
24 geographic iterations per start and arm. Radio/covariance alternatives use
three phase-reference rounds; the fixed/relinearized physical pair uses four.
Each **`c=0` / fitted-`c`** pair keeps observations, candidates, aliases, other
priors, starts and budgets matched. The known coordinate
**37.849061591561885°, −122.48574968092912°** enters postfit evaluation only.
Scans are fitted independently. This is exploratory work on the same corpus,
not an independent validation set.

## Position results

Errors are km, **`c=0` / fitted `c`**. `window_precise` is a numerical control
for the same point-noise model, not another physical algorithm.

{chr(10).join(table)}

![Independent errors for both c arms](position_errors.png)

For an equal three-round comparison, a single lowest normalized `c=0` bound
rule selects: **{selected_text}**. Fixed/relinearized four-round experiments
are excluded from this selection, and the precise noise solver replaces its
less converged version. The omitted fixed white-noise volume is restored
before comparing noise models. This is a heuristic score rule, not calibrated
model probability; noise features were developed on this same corpus.
Choosing each scan's lowest GPS error would be an oracle.

## Why does the wrong position still win?

On S03, the baseline weighted frequency residual cost is **{-driver["weighted_data"]:.3f}
units lower at the true position**, yet its shared prior costs increase by
**{driver["shared_prior"]:.3f}** and its per-fragment constant prior by
**{driver["curve_constant_prior"]:.3f}**. The total bound favors the displaced
endpoint by **{driver["normalized_total"]:.3f}** units. This is a regularization
and model-identification tradeoff, not evidence that the data require the
wrong coordinate. All nuisance means are refitted at both diagnostic sites
using the same numerical phase/orbit reference; GPS is absent from inference.

![Frequency, prior and latent-noise contributions](wrong_position_cost_drivers.png)

Exact physical relinearization greatly reduces conditional-mean approximation
error while barely moving the final positions. Thus the measured tangent
error is not the main cause of the current kilometre-scale displacements.
This validates a local conditional mean, not exact nonlinear marginalization.

![Exact-mean accuracy versus location](relinearization_controls.png)

An orbit-free radio diagnostic projects out RF-scaled family polynomials and
measures hardware information. Common RX mean drift has nominal uncertainty
about 12–16 Hz/s; relative RX drift and band contrasts are much better
constrained. Its standardized residual RMS exceeds one, especially on S01
and S04, so these are optimistic, model-conditional information estimates.
They are not fed back as new independent priors on the same measurements.

![Radio-only common and relative drift information](radio_drift_information.png)

Local curvature of the nuisance-integrated bound gives the following formal
principal scales for `c=0`, with covariance twice the inverse Hessian. These are
conditional on labels and model assumptions and are **not calibrated position
confidence**. The complete matched-c diagnostics are in
[local information](local_information.json).

{chr(10).join(info_table)}

## Coverage and frequency accuracy

Acceptance uses the original white-residual gates. The denominator is 12,724
curved points, not all raw GLRT detections. Counts can fall when a candidate's
uncertainty now activates the existing two-owner gate. Those observations
remain in the inference likelihood. Linear-track transfer was not rerun.
RMS comparisons use common accepted observations within each matched pair.

{chr(10).join(coverage)}

## Numerical controls and reproducibility

The grouped Student bound matches the observation-space implementation on all
five saved noise-model endpoints, with score differences below 1e-5 and native
prediction differences below 1e-4 Hz. Measured kernel timings improve by about
sixfold; these are host numerical timings, not embedded-device benchmarks.
The 24-iteration latent solver had not converged on S05. `window_precise`
allows 256 updates with the same tolerance, observations and physical model.
See [backend/convergence controls](precision_backend_checks.json).

[Evaluation CSV](evaluation_summary.csv), [matched c controls](c_ablation.csv),
[full gate and objective details](frequency_details.json), and
[input bindings](evaluation_bindings.json) preserve frequency fit separately
from position error. There are **{len(rows)} evaluated fit records /
{len(rows) // 2} matched pairs**, including reused controls and all outer rounds.

The next hypotheses should target the remaining source of bias: robust
satellite-level orbital priors, geometry consensus across independently
supported satellite families, and further carrier-frequency evidence from
the existing recordings. These are proposed next tests, not claimed fixes.
Production contracts and golden fixtures are unchanged. No new RF collection
is needed for the next bounded analysis.
"""
    checkpoint = ROOT / "reports/2026_10_18_dsx01_radio_orbit_followup"
    metadata = [
        checkpoint / name
        for name in ("source_manifest.json", "input_manifest.json", "frozen_tests.json")
    ]
    if all(path.exists() for path in metadata):
        sources, inputs, tests = [json.loads(path.read_text()) for path in metadata]
        passed = re.search(r"(\d+) passed", tests["stdout"])
        text += (
            "\nThe [frozen test receipt](frozen_tests.json) records "
            f"**{passed[1]} passing tests**. "
            f"[Source hashes](source_manifest.json) pin **{sources['count']} source snapshots**; "
            "[input hashes](input_manifest.json) pin "
            f"**{inputs['count']} numerical/protocol inputs**. "
            "See the [completed-checkpoint validation](validation.json) and "
            "[frozen product replay](frozen_endpoint_replay.json).\n"
        )
    (OUTPUT / "README.md").write_text(text)


if __name__ == "__main__":
    run()
