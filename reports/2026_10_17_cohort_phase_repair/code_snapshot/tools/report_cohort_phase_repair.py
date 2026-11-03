"""Report all-scan curved-family phase repairs and controlled model sensitivities."""

import hashlib
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from inventory_clipped_phase_cohort import ROOT

REPORT = ROOT / "reports/2026_10_17_cohort_phase_repair"
ACTIVE = REPORT / "curved_only"


def read(path):
    return json.loads(path.read_text())


def run():
    associations = read(ACTIVE / "association/summary.json")
    competitions = [read(p) for p in sorted((ACTIVE / "competition").glob("*/*/*/summary.json"))]
    rf = [read(p) for p in sorted((REPORT / "rf_reference").glob("*/*/*/summary.json"))]
    priors = [read(p) for p in sorted((REPORT / "phase_prior").glob("*/*/*/summary.json"))]
    if (len(associations), len(competitions), len(rf), len(priors)) != (10, 10, 12, 12):
        raise ValueError("bounded experiments are incomplete")
    for folder in ("rf_reference", "phase_prior"):
        for p in (REPORT / folder).glob("*/*/*/fit.json"):
            if (
                hashlib.sha256(p.read_bytes()).hexdigest()
                != read(p.with_name("evaluation.json"))["fit_sha256"]
            ):
                raise ValueError("position fit changed after saving its evaluation")
    totals = {}
    for arm in ("c0", "fitted_c"):
        rows = [r for r in associations if r["arm"] == arm]
        totals[arm] = dict(
            before=sum(r["before_points"] for r in rows),
            after=sum(r["after_points"] for r in rows),
            gained=sum(r["gained_points"] for r in rows),
            curved_gained=sum(r["gained_curved_points"] for r in rows),
            linear_gained=sum(r["gained_linear_points"] for r in rows),
            raw_points=sum(r["raw_glrt_points"] for r in rows),
            merged_tracks=sum(r["merged_tracks"] for r in rows),
            lost=sum(r["lost_points"] for r in rows),
        )
        if any(r["relabelled_points"] for r in rows):
            raise ValueError("conservative cohort repair changed an old admitted identity")
    write(
        REPORT / "summary.json",
        dict(
            association=associations,
            totals=totals,
            rf_sensitivity=rf,
            phase_prior_sensitivity=priors,
            active_phase_results="curved_only",
            parent_phase_outputs_superseded=True,
        ),
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True, layout="constrained")
    for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
        rows = [r for r in associations if r["arm"] == arm]
        x = np.arange(5)
        ax.bar(
            x - 0.18,
            [100 * r["before_points"] / r["raw_glrt_points"] for r in rows],
            width=0.35,
            color="#777777",
            label="Frozen baseline",
        )
        ax.bar(
            x + 0.18,
            [r["percent_raw_glrt"] for r in rows],
            width=0.35,
            color="#2878b5",
            label="Phase repair",
        )
        ax.set(xticks=x, xticklabels=[f"S{i}" for i in range(1, 6)], ylim=(0, 80), title=arm)
        ax.grid(axis="y", alpha=0.2)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("Associated / all raw GLRT points (%)")
    fig.suptitle("Known GPS: five uniquely passing curved families, unchanged hardware")
    fig.savefig(REPORT / "cohort_association.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(5, 2, figsize=(14, 16), layout="constrained")
    for i in range(5):
        case = f"DSX01-S{i + 1:02d}"
        tracks = load_tracks(
            ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter" / case
        )
        partition = read(
            ROOT / "reports/2026_10_17_robust_curve_reassociation/partition" / case / "curves.json"
        )
        partition_by_key = {t["key"]: t for t in partition}
        for ax, arm in zip(axes[i], ("c0", "fitted_c"), strict=True):
            old = read(ACTIVE / "inventory" / case / arm / "baseline_association.json")
            new = read(ACTIVE / "association" / case / arm / "association.json")
            oldids = {
                oid
                for r in old["rows"]
                if r["compatible"]
                for oid in partition_by_key[r["component"]]["observation_ids"]
            }
            admitted = set(new["associated_observation_ids"])
            for t in tracks:
                mask = np.array([oid in admitted for oid in t["observation_ids"]])
                was = np.array([oid in oldids for oid in t["observation_ids"]])
                ax.scatter(
                    t["times"][~mask], t["values"][~mask] / 1000, s=4, color="#c8c8c8", alpha=0.6
                )
                for selected, color in ((mask & was, "#2878b5"), (mask & ~was, "#d97027")):
                    ax.scatter(
                        t["times"][selected],
                        t["values"][selected] / 1000,
                        s=6,
                        color=color,
                    )
            ax.set(
                title=f"{case} / {arm}: {new['compatible_points']:,} points",
                xlabel="Time within scan (s)",
                ylabel="Native GLRT CFO (kHz)",
            )
            ax.grid(alpha=0.15)
    fig.suptitle(
        "Graph observations: previous associations blue, "
        "new phase matches orange, unassociated grey"
    )
    fig.savefig(REPORT / "cohort_glrt.png", dpi=140)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    for ax, case in zip(axes, ("DSX01-S01", "DS22-001"), strict=True):
        for fitted_c, color, label in ((False, "#2878b5", "c=0"), (True, "#dc7025", "Fitted-c")):
            rows = [
                next(
                    r
                    for r in rf
                    if r["case"] == case and r["fitted_c"] == fitted_c and r["hypothesis"] == h
                )
                for h in ("sampled_edge", "edge_midpoint", "double_edge_offset")
            ]
            ax.plot(
                range(3), [r["known_position_rms_hz"] for r in rows], "o-", color=color, label=label
            )
        ax.set(
            xticks=range(3),
            xticklabels=["Recorded edge", "Edge midpoint", "Double deviation"],
            ylabel="Known-GPS RMS on fixed curved cohort (Hz)",
            title=case,
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.suptitle("RF coefficient sensitivity: alternatives degrade the physical frequency fit")
    fig.savefig(REPORT / "rf_reference_sensitivity.png", dpi=150)
    plt.close(fig)

    assoc_table = "\n".join(
        f"| {r['case']} | {r['arm']} | {r['before_points']} → {r['after_points']} | "
        f"{r['percent_raw_glrt']:.2f}% | "
        f"{r['gained_curved_points']} / {r['gained_linear_points']} | "
        f"{r['merged_tracks']} | {r['points_per_merged_track']:.1f} |"
        for r in associations
    )
    family_table = "\n".join(
        f"| {r['case']} | {r['nomination_norad']} | {'fitted-c' if r['fitted_c'] else 'c=0'} | "
        f"{len(r['members'])} / {r['curved_points']} | {r['candidates']} | "
        f"{r['passing_candidates'][0]['phase_s']:.2f} | "
        f"{r['passing_candidates'][0]['passing_phase_min_s']:.2f}…"
        f"{r['passing_candidates'][0]['passing_phase_max_s']:.2f} |"
        for r in competitions
        if r["uniquely_passing_nomination"]
    )
    rf_table = "\n".join(
        f"| {r['case']} | {'fitted-c' if r['fitted_c'] else 'c=0'} | {r['hypothesis']} | "
        f"{r['position_error_km']:.3f} | {r['rms_hz']:.1f} | "
        f"{r['compatible_curved_points']} / {r['fixed_points']} |"
        for r in rf
    )
    prior_table = "\n".join(
        f"| {r['case']} | {'fitted-c' if r['fitted_c'] else 'c=0'} | "
        f"{r['phase_sigma_floor_s']:.0f} | {r['position_error_km']:.3f} | "
        f"{r['compatible_curved_points']} / {r['fixed_curved_points']} |"
        for r in priors
    )
    zero, fitted = totals["c0"], totals["fitted_c"]
    approved = {(r["case"], u["norad"]) for r in associations for u in r["updates"]}
    text = f"""# All-scan curved-family phase repair and input-model checks

The phase-clipping repair generalizes across DSX01: {len(approved)} jointly supported
families add **{zero["gained"]} / {fitted["gained"]} points** in c=0 / fitted-c,
including {zero["curved_gained"]} / {fitted["curved_gained"]} curved and
{zero["linear_gained"]} / {fitted["linear_gained"]} linear points. Old losses are
{zero["lost"]} / {fitted["lost"]}; no retained old point changes identity.
Totals are **{zero["after"]:,} / {zero["raw_points"]:,}
({100 * zero["after"] / zero["raw_points"]:.2f}%)** for c=0 and
**{fitted["after"]:,} / {fitted["raw_points"]:,}
({100 * fitted["after"] / fitted["raw_points"]:.2f}%)** for fitted-c.
All figures here distinguish known-position association from blind accuracy.
The authoritative phase outputs are in `curved_only/`. Parent-level phase
outputs are preserved as superseded: they incorrectly locked competing phases
with linear-only support. RF/prior sensitivity and input audits are separate
experiments and remain at the parent level.

## Conservative nominations and candidate competition

Every scan retains its own four receiver/band offsets and small linear drifts.
Hardware stays frozen. A satellite keeps its phase only if an admitted curved
fragment supports it in either c arm. Linear-only matches cannot lock or veto
a phase. A common c0 nomination pool uses only curved fragments unassociated
in both arms, each independently measured-curved, and requires at
least two fragments whose nominated phase hit its old bound. Linear fragments
cannot nominate, estimate, rank or lock a phase. Eight families qualify: four in S01,
three in S03, one in S04; S02/S05 have none under this rule.

A 601-state -15…+15 s profile retains the original Gaussian phase priors and
all raw CFOs, times, RFs and IDs. Every nominated curved member must pass the
visibility, bias, RMS and mean/slope/quadratic/step/lag-1 checks at one common
candidate/phase. Five families pass; three remain rejected (S01 62052 / 63474,
S03 59547). No fragment is discarded to manufacture an all-member pass.

For each passing family, every candidate in its prepared causal bank competes;
only candidates with admitted curved support retain their established phases. The nominated
satellite is the sole passing candidate on the tested grid in both c arms.
Gaussian bias/phase/conditional-volume penalties remain; one candidate model
pays its phase prior once, rather than once per fragment or competing satellite.

| Scan | NORAD | c arm | Curved fragments / points | Candidates | Phase s | Passing grid range s |
|---|---:|---|---:|---:|---:|---|
{family_table}

Ranges are gate-passing grid samples, not confidence intervals. Some selected
phases lie at a gate boundary because the retained prior is strong; this should
not be presented as precise orbit calibration. Uniqueness is conditional on the
prepared candidate bank, same-data nominations, frozen hardware and finite grid;
it is not external identity truth or a calibrated false-discovery guarantee.

## Association with old and jointly vetted labels preserved

The final evaluation binds old accepted identities and the newly vetted
curved-family identities, then evaluates every candidate for remaining tracks.
Fixed labels still require every physical/residual/support gate. Preserving a
family label does not allow a bad residual through. This avoids breaking an
overdetermined common-family result by selecting a different candidate for an
individual member. A new narrow association port supports these bindings;
default association is unchanged. Linear fragments associate only afterward.
Old linear matches are rechecked under the curved-learned phases and can fail;
their survival is never used to select or veto a phase.

| Scan | c arm | Before → after | % raw GLRT | New curved / linear | Merged tracks | Points/track |
|---|---|---:|---:|---:|---:|---:|
{assoc_table}

The denominator includes all 20,084 raw GLRT detections, including marks outside
the original 18,338-point Graph catalogue. The original T009 and S02 background
points remain explicit and unassociated. Baselines include the earlier robust
partition and candidate-after-gates ordering; S01 starts at 2,009 rather than
the older 2,001. Old curved-supported phases and retained accepted NORADs stay fixed.
Shared-constant joining retains all admitted IDs and identities and applies
member and pooled residual checks with a 30 s maximum gap.

![All-scan coverage](cohort_association.png)

![GLRT point associations](cohort_glrt.png)

## RF and timing input audit

All 18,338 original DSX01 Graph points exactly preserve frozen source RF and
counter-derived times; every unwrapped CFO differs from the original mark by
an integer native alias. Orbit-bank origins match the source/adapter UTC anchors.
Lower/upper source IDs agree with their different RF edge lattices. The 230.625
MHz difference between the S01 lower edge and DS22 upper edge is therefore not
an adapter unit error. This checks exported metadata, not physical LO metrology.

For DS22-001 the original 14.7 MB public source snapshot is hash-verified and
all 4,039 published winning marks reproduce exactly. All 3,510 Graph points
retain their original time/RF/alias binding. Its nominal rate is 2.5 MS/s,
20 ms probes; the adapter uses device-counter elapsed time plus a half-probe
midpoint, with a 0.124731 s UTC half-bracket. Source RF authority remains
`hypothesis`. Absolute RF calibration or unmodelled UTC latency is not proven.
DSX01's original live input files are locally unreadable; its sealed source and
context exports provide the audited authority. This did not block the analysis.

`input_audit/` preserves all checks and hashes. No RF, CFO, timestamp or original
contract was silently corrected.

## Explicit RF-reference sensitivities are rejected as repairs

Using fixed earlier blind c0 families and initial states in both c arms, three
predeclared Doppler coefficients were tested: sampled edge, the midpoint of the
paired recorded edge settings, and twice the deviation from that midpoint.
Only the Doppler coefficient changes; actual RF metadata and the hardware c
feature remain unchanged. Every hypothesis gets the same exact-geometry binary
search cap of 73 locations and the same priors, points, labels and initializers.
GPS is used only after saving each independent endpoint, then in a separate
fixed-position frequency diagnostic. These are exploratory coefficient tests,
not new RF calibration authority. Original phase boxes are used in this table.

| Dataset | c arm | Coefficient hypothesis | Error km | Endpoint RMS Hz | Passing curved / fitted |
|---|---|---|---:|---:|---:|
{rf_table}

The sampled-edge controls exactly reproduce the previous endpoints. Alternative
coefficients substantially worsen RMS and lose most residual-compatible curved
points. A midpoint DS22 estimate happens to be nearer GPS (~0.94 km), and the
double-deviation S01 estimate is also nearer, while their frequency fits fail.
Neither is adopted or counted as a localization improvement. A smaller error
alone cannot justify changing the physical model.

![RF-reference frequency-fit checks](rf_reference_sensitivity.png)

## Separate phase-prior sensitivity

These runs use the original sampled-edge RF, identical blind families, initial
states and budgets, and hold every phase box at +/-15 s. The original uncalibrated
successive-TLE-disagreement prior is compared with sigma floors of 1 and 3 s.
Thus prior strength changes separately from clipping. Gaussian volume terms
are retained. These floors are sensitivity assumptions, not calibrated orbital
covariances or adopted defaults. There is no linear calibration or point pruning.

| Dataset | c arm | Phase sigma floor s | Error km | Passing curved / fitted |
|---|---|---:|---:|---:|
{prior_table}

The location bias persists: S01 stays roughly 6 km away; DS22 stays roughly
2.1–2.4 km away. Some fitted members fail final screens. These fixed-family
Gaussian searches are exploratory; the earlier 1.895 km DS22 result remains
better under the accepted RF model. No <0.5 km result, whole-DS22 validation or
new independent position result for S02–S05 is established by this report.

## Validation and next evidence

65 focused tests pass for nominations, linear exclusion, fixed-label gates,
independent dense fits, RF-reference/hardware-feature separation and original
point binding. Default RF statistics are bitwise unchanged in the synthetic
oracle and reproduced real-data control endpoints exactly. All handwritten
current sources pass Ruff. Source snapshots, numerical matrices, evaluations,
point IDs, source hashes and unchanged earlier seals accompany the report.
No new RF collection or QNAP mutation occurred.

The next useful position experiment is a nuisance-projected information audit
and then a common-position multi-scan fit with scan-local hardware. This should
test how much accuracy is lost to orbital phase, receiver drift and component
constants, before adding parameters or tuning on GPS. The three rejected phase
families can separately be examined for coherent curved subsets with explicit
clutter costs; their all-member failure is not permission to force them together.
"""
    (REPORT / "README.md").write_text(text)
    print(json.dumps(totals), flush=True)


if __name__ == "__main__":
    run()
