"""Paired-c, cold-start test of retaining a rejected curved satellite owner.

No reference position, new satellite identity, post-scan elements or relaxed
residual gate is supplied. The largest wholly rejected nominated curve whose
family has unsupported orbital coordinates is a proposal, never a forced match.
"""

import argparse
from functools import partial
import hashlib
from pathlib import Path
import time

import numpy as np

import debug_fast_graph_unassociated as report


ARMS = ("c0", "fitted_c")


def run(args):
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    terminal, saved, entries, scan, baseline_problems, replay = report.saved_context(
        args.run, args.source_root
    )
    from algo02_scan import pair_passes
    from ds23_frequency_events import make_event_problem, attach_event_predictive
    from investigate_dsx01_localization_failures import fit
    from probe_ds23_frequency_events import cached, summary
    from probe_ds23_history_calibrated_phase import make_problem
    from leo.analysis.research.retained_track_likelihood import PERIOD

    node = saved["selected"]["node"] if saved["accepted"] else saved["baseline_node"]
    means = np.asarray(saved["selected"]["means"] if saved["accepted"] else saved["baseline_means"])
    keep = np.asarray(saved["original_mask"], bool)
    powers, model = np.asarray(saved["powers"]), saved["model"]
    base = baseline_problems["c0"]
    owners = {}
    for row, i, sl in zip(base.rows, base.members, base.slices, strict=True):
        if keep[sl].any():
            t = scan.tracks[i]
            owners.setdefault(row["candidate_index"], set()).add((t["receiver"], t["channel"]))
    eligible = []
    for k, (row, i, sl) in enumerate(zip(base.rows, base.members, base.slices, strict=True)):
        j = row["candidate_index"]
        if (not keep[sl].any() and i in scan.curved and j in base.supported
                and len(owners.get(j, ())) < 2 and len(scan.tracks[i]["times"]) >= 12
                and np.ptp(scan.tracks[i]["times"]) >= 10):
            eligible.append((len(scan.tracks[i]["times"]), float(np.ptp(scan.tracks[i]["times"])), k))
    if not eligible:
        raise ValueError("No rejected curved owner with unsupported physical corrections")
    _, _, chosen = max(eligible)
    target_row, target_i, target_slice = base.rows[chosen], base.members[chosen], base.slices[chosen]
    target = scan.tracks[target_i]
    offered = keep.copy()
    offered[target_slice] = True
    original_ids = {o["observation_id"] for o in report.read(args.run/"inference/SCAN/observations.json")}
    proposal = dict(component=target["key"], norad=target_row["candidate_norad"],
                    points=len(target["times"]), duration_s=float(np.ptp(target["times"])),
                    selection="largest wholly rejected curved nomination with fewer than two active owners",
                    satellite_identity_from_original_causal_RF_nomination=True)
    report.write(out/"protocol.json", dict(proposal=proposal, eligible=eligible,
        original_points=int(keep.sum()), offered_points=int(offered.sum()),
        predictive_points=sum(e["points"] for e in entries),
        regional_start_km=[0, 0], regional_box_width_km=25,
        phase_rounds=5, position_steps_per_round=48, original_aliases_unchanged=True,
        no_GPS_or_future_TLE=True, no_original_observation_deleted=True,
        null_objective_replay_differences=replay,
        controls=["baseline", "restore_nominal_orbits", "restore_active_support"],
        covariance_modes_removed_not_merely_ignored_by_acceptance=True,
        source_sha256={name: hashlib.sha256((args.source_root/name).read_bytes()).hexdigest() for name in (
            "tools/probe_graph_orbital_support_backoff.py",
            "tools/probe_ds23_history_calibrated_phase.py",
            "src/leo/analysis/research/orbital_support.py")}))
    print("Proposal", proposal, flush=True)
    results = {}
    fitted_problems = {}
    for control in ("baseline", "restore_nominal_orbits", "restore_active_support"):
        active = keep if control == "baseline" else offered
        policy = "active" if control == "restore_active_support" else "nominal"
        pair = {}
        for arm in ARMS:
            reference, x, history = np.zeros(len(means)), np.zeros(2), []
            began = time.monotonic()
            for epoch in range(5):
                factory = partial(make_problem, support_policy=policy)
                p = make_event_problem(scan, node, active, arm, reference, powers,
                                       means, model, [], base_problem_factory=factory)
                attach_event_predictive(p, entries, powers)
                cached(p)
                fitted = fit(p, x, iterations=48)
                x = np.asarray(fitted["parameters"])
                phase = np.clip(p.state(x)["phases"][p.labels], -15, 15)
                history.append(dict(fit=fitted, phase_change_s=float(np.max(abs(phase-reference)))))
                reference = phase
            row = summary(p, x, entries)
            row.update(history=history, final_phase_change_s=history[-1]["phase_change_s"],
                       seconds=time.monotonic()-began,
                       orbital_support_backoff=getattr(p, "orbital_support_backoff", None),
                       physical_orbit_norads=[int(scan.norads[j]) for j in p.supported],
                       retained_original_ids=sorted(oid for i, sl in zip(p.members, p.slices, strict=True)
                           for oid, use in zip(scan.tracks[i]["observation_ids"], active[sl], strict=True) if use))
            curved, predictive, accepted, _ = report.memberships(p, x, entries)
            row.update(associated_original_points=len(accepted & original_ids),
                       associated_original_percent=100*len(accepted & original_ids)/len(original_ids),
                       associated_original_ids=sorted(accepted & original_ids),
                       curved_likelihood_points=len(curved), predictive_likelihood_points=len(predictive),
                       postfit_only_points=len(accepted-curved-predictive),
                       target_gate=next(r for r in row["gates"]["tracks"] if r["component"] == target["key"]) if control != "baseline" else None)
            if not set(base.scan.tracks[i]["observation_ids"][n]
                       for i, sl in zip(base.members, base.slices, strict=True)
                       for n, use in enumerate(keep[sl]) if use) <= set(row["retained_original_ids"]):
                raise ValueError("Original likelihood evidence was removed")
            pair[arm] = row
            fitted_problems[control, arm] = (p, x)
            report.write(out/f"{control}_{arm}.json", row)
            print(control, arm, "raw offered membership", row["associated_original_points"],
                  "RMS", row["RMS_hz"], "target passes", row["target_gate"]["compatible"] if row["target_gate"] else None,
                  "phase delta", row["final_phase_change_s"], flush=True)
        results[control] = dict(arms=pair, paired_valid=pair_passes(pair, include_linear=True))
    # Compact scientific summary; unlike normalized same-mask model comparison,
    # raw baseline-v-restored objective differences are not adoption scores.
    proposal_valid = results["restore_active_support"]["paired_valid"] and all(
        set(results["baseline"]["arms"][arm]["associated_original_ids"]) <=
        set(results["restore_active_support"]["arms"][arm]["associated_original_ids"]) for arm in ARMS)
    report.write(out/"results.json", dict(proposal=proposal, results=results,
        prototype_selected="restore_active_support" if proposal_valid else "baseline",
        source_revision=terminal.get("source_revision"), null_replay=replay,
        matched_c_observations_nominations_aliases_priors_and_search_budgets=True,
        production_memberships_not_modified=True, seconds=time.monotonic()-started))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharex="col")
    for col, arm in enumerate(ARMS):
        axes[0, col].scatter(target["times"], target["values"], s=14, c="black", label="original CH1 GLRT")
        for control, color, label in (("restore_nominal_orbits", "#b45309", "Three orbital corrections: fails support"),
                                      ("restore_active_support", "#2563eb", "Phase only: passes all gates")):
            p, x = fitted_problems[control, arm]
            c = p.calculate(x)
            # Full conditional posterior uses the existing 300 Hz constant prior.
            observed = p.values[target_slice]
            residual = c["conditional_residual_hz"][target_slice]
            axes[0, col].plot(target["times"], observed-residual-p.alias[chosen]*PERIOD,
                              color=color, label=label)
            axes[1, col].plot(target["times"], residual, ".-", ms=3, color=color,
                              label=f"{label}: {np.sqrt(np.mean(residual**2)):.1f} Hz RMS")
        axes[0, col].set_title(arm)
        axes[0, col].set_ylabel("Unwrapped graph CFO (Hz)")
        axes[1, col].set_ylabel("Conditional residual (Hz)")
        axes[1, col].set_xlabel("Time in scan (s)")
        axes[1, col].axhline(0, color="gray", lw=1)
        for ax in axes[:, col]:
            ax.grid(alpha=.25)
            ax.legend()
    fig.suptitle(f"{target['key']} — unchanged data and residual gates; simpler orbital model")
    fig.tight_layout()
    fig.savefig(out/"target_backoff.png", dpi=160)
    fig.savefig(out/"target_backoff.pdf")
    plt.close(fig)
    print("Done", {k: r["paired_valid"] for k, r in results.items()}, flush=True)


def audit(args):
    """Recheck sealed prototype outputs without rerunning localization."""
    terminal, saved, entries, scan, baseline_problems, _ = report.saved_context(args.run, args.source_root)
    from ds23_frequency_events import make_event_problem, attach_event_predictive
    from probe_ds23_frequency_events import cached
    from probe_ds23_history_calibrated_phase import make_problem
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.analysis.research.retained_track_likelihood import PERIOD, profile, whitening
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from prototype_dsx01_continuous_position import latlon
    d = report.read(args.output/"results.json")
    node = saved["selected"]["node"] if saved["accepted"] else saved["baseline_node"]
    means = np.asarray(saved["selected"]["means"] if saved["accepted"] else saved["baseline_means"])
    keep = np.asarray(saved["original_mask"], bool).copy()
    base = baseline_problems["c0"]
    chosen = next(k for k, r in enumerate(base.rows) if r["component"] == d["proposal"]["component"])
    keep[base.slices[chosen]] = True
    target = scan.tracks[base.members[chosen]]
    track_by_id = {oid: t["key"] for t in scan.tracks for oid in t["observation_ids"]}
    result = {}
    for arm in ARMS:
        old, new = [d["results"][control]["arms"][arm] for control in ("baseline", "restore_active_support")]
        x = np.asarray(new["endpoint_east_north_km"])
        p = make_event_problem(scan, node, keep, arm, np.asarray(new["phase_reference"]),
            np.asarray(saved["powers"]), means, saved["model"], [],
            base_problem_factory=partial(make_problem, support_policy="active"))
        attach_event_predictive(p, entries, np.asarray(saved["powers"]))
        cached(p)
        delta = p.calculate(x)["negative_twice_elbo"]-new["negative_twice_elbo"]
        if abs(delta)>1e-5:
            raise ValueError("Prototype endpoint objective does not replay")
        old_ids, new_ids = set(old["associated_original_ids"]), set(new["associated_original_ids"])
        added = new_ids-old_ids
        by_track = {key: sum(track_by_id[oid] == key for oid in added) for key in sorted({track_by_id[oid] for oid in added})}
        # Randomized four-second block test. Receiver/site stay fixed to the
        # ORIGINAL fit, which excluded every target observation. Only phase and
        # its Gaussian curve constant are estimated on training blocks.
        baseline = baseline_problems[arm]
        baseline_x = np.asarray(saved["policy_arms"][arm]["endpoint_east_north_km"])
        state = baseline.state(baseline_x)
        times = target["times"]
        q = target["rf_hz"]/11.5e9
        raw = target["values"]-scan.hardware(target, state["beta"])
        raw -= q*scan.rx_basis[base.members[chosen]]@state["smooth"][target["receiver"]-1]
        label = base.rows[chosen]["candidate_index"]
        bank = {k: scan.sky[k][[label]] for k in ("position_km", "velocity_km_s")}
        bank["time_s"] = scan.sky["time_s"]
        phases = np.arange(-15., 15.0001, .05)
        predictions = np.asarray([q*paired_phase_frequency(bank, times, np.zeros(len(times), int),
            np.array([phase]), *latlon(baseline_x))[0] for phase in phases])
        blocks = np.floor((times-times.min())/4).astype(int)
        unique = np.unique(blocks)
        rng = np.random.default_rng(20261029)
        test_blocks = sorted(rng.choice(unique, max(1, int(np.ceil(.3*len(unique)))), replace=False).tolist())
        held = np.isin(blocks, test_blocks)
        terms = profile(raw[~held], predictions[:, ~held], *whitening(times[~held]), bias_sigma=300.)
        sigma = baseline.phase_sigma[baseline.labels.index(label)]
        mu = means[baseline.labels.index(label)]
        # Student prior uses the same causal location/scale/nu as production.
        nu = saved["model"]["nu"]
        z = (phases-mu)/sigma
        prior = z*z if nu is None else (nu+1)*np.log1p(z*z/nu)
        best = int(np.argmin(terms["cost"]+prior))
        residual = raw+terms["alias"][best]*PERIOD-predictions[best]-terms["bias"][best]
        curved, predictive, accepted, associated_owners = report.memberships(p, x, entries)
        result[arm] = dict(objective_replay_difference=delta, added_by_track=by_track,
            added_identities={key: sorted({associated_owners[oid] for oid in added if track_by_id[oid] == key}) for key in by_track},
            curved_likelihood_points=len(curved), predictive_likelihood_points=len(predictive),
            postfit_only_points=len(accepted-curved-predictive),
            disabled_orbit_norads=[int(scan.norads[j]) for j in p.orbital_support_backoff["disabled_families"]],
            lost_original_associated_ids=sorted(old_ids-new_ids),
            endpoint_shift_km=float(np.linalg.norm(x-np.asarray(old["endpoint_east_north_km"]))),
            new_phase_s=float(p.state(x)["phases"][label]),
            target_orbital_coordinates=3*int(label in p.supported),
            randomized_block_check=dict(seed=20261029, block_seconds=4, test_blocks=test_blocks,
                training_points=int((~held).sum()), test_points=int(held.sum()),
                block_assignments=blocks, held_mask=held, phase_s=float(phases[best]),
                bias_hz=float(terms["bias"][best]), alias=int(terms["alias"][best]),
                training_RMS_hz=float(np.sqrt(np.mean(residual[~held]**2))),
                test_RMS_hz=float(np.sqrt(np.mean(residual[held]**2))),
                test_mean_hz=float(np.mean(residual[held])),
                test_noise_screen={k: float(v[0]) for k, v in batch_noise_screen(residual[held][None,:], times[held]).items()},
                receiver_and_position_frozen_from_original_fit_excluding_target=True,
                catalogue_identity_proposed_using_full_track_not_blind_identity_validation=True))
    report.write(args.output/"validation.json", result)
    print({arm: {k:v for k,v in r.items() if k != "randomized_block_check"} for arm,r in result.items()}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    if args.audit_only:
        audit(args)
    else:
        run(args)
