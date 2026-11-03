"""Render fixed-family transport, clipping evidence and independent local fits."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from associate_merged_track_catalogue import load_tracks, write

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_17_fixed_family_transfer"


def read(path):
    return json.loads(path.read_text())


def run():
    diagnostic = [
        row
        for p in sorted((REPORT / "diagnostics").glob("*/*/summary.json"))
        for row in read(p)["rows"]
    ]
    sensitivity = [
        dict(row, setting=p.parent.parent.name)
        for p in sorted((REPORT / "bound_sensitivity").glob("*/*/summary.json"))
        for row in read(p)["rows"]
    ]
    searches = [read(p) for p in sorted((REPORT / "search").glob("*/*/summary.json"))]
    if len(diagnostic) != 16 or len(sensitivity) != 12 or len(searches) != 8:
        raise ValueError("bounded experiments are not all complete")
    for p in (REPORT / "search").glob("*/*/fit.json"):
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest != read(p.with_name("evaluation.json"))["fit_sha256"]:
            raise ValueError("blind fit changed after evaluation")
        fit = read(p)["endpoint"]
        if not fit["no_points_rejected"] or not fit["no_labels_changed"]:
            raise ValueError("fixed-family scientific invariant failed")
    phases = {
        arm: read(REPORT / "clipped_family_phase" / arm / "summary.json")
        for arm in ("c0", "fitted_c")
    }
    competitions = {
        arm: read(REPORT / "all_candidate_audit" / arm / "summary.json")
        for arm in ("c0", "fitted_c")
    }
    write(
        REPORT / "summary.json",
        dict(
            diagnostics=diagnostic,
            bound_sensitivity=sensitivity,
            searches=searches,
            phase_overlay=phases,
            all_candidate_competition=competitions,
        ),
    )

    # All-candidate vector scores must reproduce the independent scalar audit.
    for arm in phases:
        scalar = read(REPORT / "clipped_family_phase" / arm / "phase_grid.json")
        with np.load(REPORT / "all_candidate_audit" / arm / "candidate_phase_grid.npz") as grid:
            j = grid["norad"].tolist().index(100320)
            np.testing.assert_allclose(
                grid["scores"][:, j], [r["score"] for r in scalar], rtol=1e-10, atol=0.01
            )
            np.testing.assert_array_equal(
                grid["all_members_pass"][:, j], [r["all_members_pass"] for r in scalar]
            )
    scalar = read(REPORT / "clipped_family_phase/c0/phase_grid.json")
    x, y = np.array([r["phase_s"] for r in scalar]), np.array([r["score"] for r in scalar])
    passing = np.array([r["all_members_pass"] for r in scalar])
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    axes[0].plot(x, (y - y.min()) / 1e6, color="#2878b5")
    axes[0].set(
        xlim=(-4.5, -2.5),
        ylim=(0, 12),
        ylabel="Excess Gaussian score (millions)",
        xlabel="Shared orbital phase correction (s)",
        title="Fixed GPS and hardware",
    )
    for i in range(3):
        axes[1].plot(
            x,
            [r["members"][i]["rms_hz"] for r in scalar],
            label=scalar[0]["members"][i]["key"].replace("S01-", ""),
        )
    axes[1].set(
        xlim=(-4.5, -2.5),
        ylim=(0, 450),
        ylabel="Member RMS (Hz)",
        xlabel="Shared orbital phase correction (s)",
        title="Every member uses all points",
    )
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.axvline(-3, color="#bb2222", ls="--", label="Old bound")
        ax.axvline(phases["c0"]["best_phase_s"], color="#222222", ls=":")
        ax.axvspan(x[passing].min(), x[passing].max(), color="#45a16b", alpha=0.15)
        ax.grid(alpha=0.2)
    fig.suptitle("NORAD 100320: the old phase limit excludes the compatible region")
    fig.savefig(REPORT / "clipped_family_phase.png", dpi=160)
    plt.close(fig)

    tracks = load_tracks(ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter/DSX01-S01")
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.7), sharey=True, layout="constrained")
    for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
        folder = REPORT / "clipped_family_phase" / arm
        before = set(read(folder / "before_association.json")["associated_observation_ids"])
        after = set(read(folder / "after_association.json")["associated_observation_ids"])
        for t in tracks:
            old = np.array([oid in before for oid in t["observation_ids"]])
            new = np.array([oid in after - before for oid in t["observation_ids"]])
            for mask, color, label in (
                (~(old | new), "#c5c5c5", "Unassociated"),
                (old, "#2878b5", "Existing"),
                (new, "#dc7025", "New"),
            ):
                ax.scatter(
                    t["times"][mask],
                    t["values"][mask] / 1000,
                    s=7,
                    color=color,
                    label=label if t is tracks[0] else None,
                    rasterized=True,
                )
        ax.set(
            title=f"{arm}: {len(before):,} → {len(after):,}, +{len(after - before)} points",
            xlabel="Time within scan (s)",
            ylabel="Native unwrapped GLRT CFO (kHz)",
        )
        ax.grid(alpha=0.15)
        ax.legend(fontsize=8)
    fig.suptitle("Known-GPS association: only one satellite phase changes; hardware stays frozen")
    fig.savefig(REPORT / "known_position_gain.png", dpi=150)
    plt.close(fig)

    transfer_table = "\n".join(
        f"| {r['case']} | {'fitted-c' if r['fitted_c'] else 'c=0'} | "
        f"{'Shared' if r['merged'] else 'Separate'} | {r['site']} | "
        f"{r['rms_hz']:.1f} | {r['member_compatible_points']} / {r['total_points']} | "
        f"{r['family_compatible_points']} |"
        for r in diagnostic
    )
    bounds_table = "\n".join(
        f"| {r['setting']} | {'fitted-c' if r['fitted_c'] else 'c=0'} | {r['rms_hz']:.1f} | "
        f"{r['member_compatible_points']} |"
        for r in sensitivity
        if r["site"] == "supplied_gps"
    )
    search_table = "\n".join(
        f"| {r['case']} | {'fitted-c' if r['fitted_c'] else 'c=0'} | "
        f"{'Shared' if r['merged'] else 'Separate'} | {r['phase_bound_floor_s']:.0f} | "
        f"{r['position_error_km']:.3f} | {r['fixed_member_compatible_points']} / "
        f"{r['fixed_curved_points']} | {r['extended_associated_points']} | {r['merged_tracks']} |"
        for r in searches
    )
    competition_table = "\n".join(
        f"| {arm} | {r['candidates']} | {r['phases']} | {r['passing_candidates']} | "
        f"{', '.join(str(x['norad']) for x in r['ranked_passing_candidates'])} |"
        for arm, r in competitions.items()
    )
    phase_table = "\n".join(
        f"| {arm} | {r['best_phase_s']:.2f} | {r['before_points']} | {r['after_points']} | "
        f"{100 * r['after_points'] / 4797:.2f}% | {r['gained_points']} | "
        f"{r['lost_points']} / {r['relabelled_points']} | {r['merged_tracks']} |"
        for arm, r in phases.items()
    )
    track_map = {t["key"]: t for t in tracks}
    before = read(REPORT / "clipped_family_phase/c0/before_association.json")
    after = read(REPORT / "clipped_family_phase/c0/after_association.json")
    existing_keys = {r["component"] for r in before["association"]["rows"] if r["compatible"]}
    new_members = [
        r
        for r in after["association"]["rows"]
        if r["compatible"] and r["component"] not in existing_keys
    ]
    fragment_table = "\n".join(
        f"| {r['component'].replace('S01-', '')} | {r['points']} | "
        f"{track_map[r['component']]['times'][0]:.2f}–"
        f"{track_map[r['component']]['times'][-1]:.2f} | {r['rms_hz']:.1f} | "
        f"{'Yes' if r['active_curvature'] else 'No'} |"
        for r in new_members
    )
    write(REPORT / "new_phase_family_members.json", new_members)
    text = f"""# Fixed satellite families: phase clipping and the remaining position bias

Holding the blind candidate families fixed identifies a concrete S01 failure:
the three measured-curved arcs nominated as NORAD 100320 need about -3.7 s of
shared orbital phase at GPS, outside the old -3 s limit. With hardware and all
other satellite phases frozen, this adds 173 compatible points, 141 curved and
32 on linear tracks, without losing or relabelling existing assignments. A
1,707-candidate grid audit finds only 100320 passing all three arcs in each c arm.
This remains conditional frequency compatibility, not authenticated identity.

Independent fixed-family position searches improve S01 to 6.36 km. DS22's fixed
families give 2.14 km, worse than the earlier 1.89 km fitted-c result. No new
sub-0.5 km result or full-corpus validation is established.

## Immutable-family transport

The common population and labels come only from the earlier blind **c=0** result
in each dataset. Both c arms use identical source observations, original IDs,
candidate labels, hardware/phase initializers, causal banks, priors and budgets.
S01 has 1,519 points on 43 individually measured-curved fragments; DS22 has
1,123 points on 29. Linear fragments are excluded even from component constants
and all calibration/state ranking. Gaussian fitting includes every selected
observation and never drops a failing member or switches NORAD. Native aliases
remain discrete whole-fragment profile branches; no extra track slope is fitted.

We compare separate fragment constants with the existing blind merged-family
shared constants, after removing all linear members from calibration. S01
reduces 43 constants to 36; DS22 stays at 29 because its selected curved members
were not joined. All fits use exact nonlinear phase geometry, two initial phase
states, up to six relinearizations and monotonic tangent/nonlinear steps.
Receiver/band offsets remain scan-local; drift prior sigma is 0.5 Hz/s, default
bound 1 Hz/s. Original per-satellite Gaussian phase priors are retained.

The cap of 50 points per component changes weights after merging. Accordingly,
scores across shared/separate models are not directly comparable; raw RMS,
residual compatibility and actual position error are reported separately.

| Dataset | c arm | Constants | Position | RMS Hz | Member points / all | Family points |
|---|---|---|---|---:|---:|---:|
{transfer_table}

The fixed blind position is the same earlier c=0 coordinate for both c arms.
The GPS diagnostic uses 37.849061591561885, -122.48574968092912, height 0 m.
Compatibility uses the unchanged 450 Hz RMS, 3,000 Hz constant and member
mean/slope/quadratic/step/lag-1 screens; shared families additionally need the
pooled residual screen. Failed observations remain fully costed in these
diagnostic fits and cannot be called newly qualified calibration evidence.

## Bound sensitivity separates two effects

At GPS, NORAD 100320 hits its -3 s phase limit and two S01 receiver drifts hit
+1 Hz/s. We independently release the phase box to at least +/-15 s, the drift
box to +/-5 Hz/s, or both. **Gaussian priors do not change.** These are diagnostic
stress tests, not evidence that physical drifts should have larger priors.

| Released bound | c arm | GPS raw RMS Hz | Passing member points / 1519 |
|---|---|---:|---:|
{bounds_table}

The phase release restores all three 100320 curved members: 25, 43 and 73
points. Their shared phase is -3.717 s in the joint transfer fit. Drift release
alone barely helps and leaves that satellite clipped. Releasing both gives
about 132 Hz pooled RMS versus 148 Hz under default boxes, but other families
still fail. Clipping is a demonstrated local association failure, not a full
explanation of the geographic bias.

## Frozen-hardware phase repair and candidate competition

For the actual association update we freeze the earlier known-GPS hardware and
all other satellite phases. Only the reviewed satellite phase is profiled, with
its original sigma=1 s Gaussian prior, on 601 exact phase states from -15 to
+15 s in 0.05 s steps. Every one of the same 141 curved observations contributes.
No linear track calibrates this phase. The passing grid interval is -3.90 to
-3.60 s in both c arms; this is a residual-gate interval, not a confidence level.

![Clipped phase profile](clipped_family_phase.png)

The full causal bank competition forces one common candidate and phase to
explain all three arcs. Already-supported satellite phases stay fixed; other
candidates receive the same 601-state grid and their own unchanged Gaussian
phase prior. Each candidate model pays that phase prior once. Ranking occurs
after every member's visibility, constant, RMS and residual checks.

| c arm | Candidates | Phase grid size | Passing candidates | NORADs |
|---|---:|---:|---:|---|
{competition_table}

The finite grid does not prove uniqueness over every continuous phase or model.
The three arcs and frozen hardware were selected using the same dataset; the
audit is not external identity truth or a calibrated false-discovery rate.
All 601 scalar phase costs and passing flags for 100320 agree with the full
candidate-vector computation, checked numerically in both c arms.

| c arm | Phase s | Before | After | % all raw GLRT | Gained | Lost / relabelled | Merged tracks |
|---|---:|---:|---:|---:|---:|---:|---:|
{phase_table}

The denominator is all 4,797 S01 GLRT detections, including observations outside
the original 4,487-point Graph catalogue. The 2,009-point baseline already uses
candidate-after-gates ranking, which adds eight points to the earlier 2,001-point
repaired baseline. The **additional 173** are attributable to this one phase
change. All new points nominate 100320, including two 16-point linear fragments
on RX2 CH7 and CH8. All original IDs and the T009 background endpoint remain
accounted for. Re-evaluation has zero losses and zero relabels in both arms.

| Fragment | Points | Time span s | RMS Hz, c=0 | Curved phase calibration |
|---|---:|---|---:|---|
{fragment_table}

![Known-position association gain](known_position_gain.png)

## Independent local position searches

Separate searches read only the prior blind c=0 family labels and initial state;
they never read GPS transport/phase-repair outputs. The Gaussian criterion keeps
all selected curved observations in the fit. Both c arms use the same 3x3
+/-16 km grid and binary scales 8, 4, 2, 1, 0.5, 0.25, 0.125, 0.0625 km,
two axial sweeps per scale, at most 73 unique locations. Every location gets
exact nonlinear phase fitting. A synthetic two-axis minimum test checks that
the schedule can actually reach fine resolution; dropping scale by four with
only two sweeps can stop early even on a smooth quadratic surface.

Each endpoint is saved and hash-bound before GPS is used for error evaluation.
Full-bank association is then a post-fit extension with hardware/position fixed,
unestimated satellite phases set to zero, and the usual curved-support and
lossless member/pooled merge checks. It has no feedback into fixed-family
position fitting. No source curved fragment changes NORAD in those extensions.

| Dataset | c arm | Constants | Box floor s | Error km | Curved / fitted | Associated | Tracks |
|---|---|---|---:|---:|---:|---:|---:|
{search_table}

S01's optimum is unchanged by widening the phase box alone. Merging slightly
changes its endpoint rather than resolving the remaining error. DS22's shared
curved groups are identical to the separate groups, so duplicated merged
searches were not run. Some fitted curved members fail the final screens; these
are exploratory, not fully qualified location results. The earlier 1.895 km
DS22 result remains better than this fixed-family variant. More associated
points, lower Gaussian cost and improved geographic accuracy remain distinct.

## Validation and next work

Forty-four focused tests pass, including an independent dense point solve,
immutable labels and point costs, linear-member exclusion, per-candidate phase
prior accounting and bounded two-axis geographic refinement. Final handwritten
sources pass Ruff. The exact audit-run source is archived separately; its later
lint-only change explicitly binds synchronous loop callback variables and has
no numerical effect. Default-bound source snapshots and protocol hashes retain
the versions used for the early transport fits. Earlier sealed reports are intact.

The demonstrated phase-clipping pattern can now be audited on other scans,
requiring shared support from multiple measured-curved arcs and preserving old
assignments. The remaining position discrepancy needs investigation of the
physical frequency inputs and shared residual structure, not an inference that
noise screens alone authenticate a satellite. Independently verify RF/timing
metadata before adding per-track nuisance terms that could erase localization
information. No new RF was collected, and no QNAP path was modified.
"""
    (REPORT / "README.md").write_text(text)
    print(
        json.dumps(
            dict(
                diagnostic_fits=len(diagnostic) + len(sensitivity),
                blind_searches=len(searches),
                phase_gains=phases,
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    run()
