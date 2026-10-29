"""Bounded CH7/8 recovery trials using sealed causal inference and paired c fits."""

import argparse
import copy
from functools import partial
from pathlib import Path
import time

import numpy as np

import debug_fast_graph_unassociated as report


ARMS = ("c0", "fitted_c")


def context(args):
    _, saved, entries, scan, original, replay = report.saved_context(args.run, args.source_root)
    from ds23_frequency_events import make_event_problem, attach_event_predictive
    from probe_ds23_history_calibrated_phase import make_problem
    from probe_ds23_frequency_events import cached
    previous = report.read(args.ch1/"results.json")
    assert previous["prototype_selected"] == "restore_active_support"
    node = copy.deepcopy(saved["selected"]["node"] if saved["accepted"] else saved["baseline_node"])
    means = np.asarray(saved["selected"]["means"] if saved["accepted"] else saved["baseline_means"])
    keep = np.asarray(saved["original_mask"], bool).copy()
    base = original["c0"]
    k = next(k for k, row in enumerate(base.rows) if row["component"] == previous["proposal"]["component"])
    keep[base.slices[k]] = True
    powers, model = np.asarray(saved["powers"]), saved["model"]
    problems = {}
    for arm in ARMS:
        r = previous["results"]["restore_active_support"]["arms"][arm]
        x = np.asarray(r["endpoint_east_north_km"])
        p = make_event_problem(scan, node, keep, arm, np.asarray(r["phase_reference"]), powers,
            means, model, [], base_problem_factory=partial(make_problem, support_policy="active"))
        attach_event_predictive(p, entries, powers); cached(p)
        delta = p.calculate(x)["negative_twice_elbo"]-r["negative_twice_elbo"]
        if abs(delta)>1e-5: raise ValueError(f"CH1 baseline objective did not replay: {delta}")
        problems[arm] = (p, x)
    return dict(scan=scan, node=node, keep=keep, powers=powers, means=means, model=model,
                entries=entries, problems=problems, previous=previous, original=original,
                original_replay=replay)


def select_targets(d):
    p, _ = d["problems"]["c0"]
    selected = []
    for ch in (7, 8):
        eligible = [k for k, (i, sl) in enumerate(zip(p.members, p.slices, strict=True))
                    if not p.keep[sl].any() and d["scan"].tracks[i]["receiver"] == 1
                    and d["scan"].tracks[i]["channel"] == ch]
        selected.append(max(eligible, key=lambda k: len(d["scan"].tracks[p.members[k]]["times"])))
    return selected


def inventory(d, targets):
    from investigate_ds23_0268_remaining_tracks import family_frequency, corrected_observation
    from leo.analysis.research.retained_track_likelihood import profile
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    p, x = d["problems"]["fitted_c"]
    scan = d["scan"]
    screens = []
    for k in targets:
        t = scan.tracks[p.members[k]]
        screens.append(dict(component=t["key"], track_index=p.members[k], row=k,
            previous_nominee=p.rows[k]["candidate_norad"],
            active=report.screen(p, x, t, np.arange(len(t["times"])), False)))
    candidates = sorted({s["active"]["norad"] for s in screens} | {s["previous_nominee"] for s in screens})
    families = []
    for k, (r, i, sl) in enumerate(zip(p.rows, p.members, p.slices, strict=True)):
        t = scan.tracks[i]
        if not p.keep[sl].any(): continue
        q = t["rf_hz"]/11.5e9
        f, e = family_frequency(p, x, r["candidate_index"], times=t["times"])
        raw = corrected_observation(p, x, i)
        terms = profile(raw, q*f, *scan.white[i])
        noise = batch_noise_screen(terms["innovations"], t["times"])
        families.append(dict(component=t["key"], norad=r["candidate_norad"],
            receiver=t["receiver"], channel=t["channel"], times_s=t["times"],
            residual_hz=terms["residual"][0], RMS_hz=float(terms["rms"][0]),
            active_mask=p.keep[sl], noise={k:float(v[0]) for k,v in noise.items()},
            minimum_elevation_deg=float(e.min())))
    return dict(screens=screens, candidates=candidates, retained=families)


def receiver_basis(scan, node, basis):
    """Optional covariance change, normalized on a fixed scan-time grid."""
    from investigate_ds23_0268_remaining_tracks import fine_receiver_basis
    from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
    scan, node = copy.copy(scan), copy.deepcopy(node)
    if basis == "original": return scan, node
    resolution = basis.removeprefix("band_") if basis.startswith("band_") else basis
    if resolution == "original":
        basis_function = projected_receiver_basis
    elif resolution == "fine":
        basis_function = fine_receiver_basis
    elif resolution == "fast":
        grid = np.linspace(0, 300, 301)
        scale = np.linalg.norm(projected_receiver_basis(grid))/np.linalg.norm(projected_receiver_basis(grid, spacing_s=5, width_s=5))
        basis_function = lambda t: scale*projected_receiver_basis(t, spacing_s=5, width_s=5)
    else:
        raise ValueError("Unknown receiver basis")
    scan.rx_basis = []
    for track in scan.tracks:
        b = basis_function(track["times"])
        if basis.startswith("band_"):
            zero = np.zeros_like(b)
            b = np.column_stack((b, zero) if track["channel"] <= 4 else (zero, b))
        scan.rx_basis.append(b)
    node["seed"]["state"]["smooth"] = np.zeros((2, scan.rx_basis[0].shape[1]))
    return scan, node


def trial(d, targets, norad, basis="original", events=()):
    from ds23_frequency_events import make_event_problem, attach_event_predictive
    from investigate_dsx01_localization_failures import fit
    from probe_ds23_frequency_events import cached, summary
    from probe_ds23_history_calibrated_phase import make_problem
    from algo02_scan import pair_passes
    from leo.analysis.research.retained_track_likelihood import profile
    from investigate_ds23_0268_remaining_tracks import family_frequency, corrected_observation
    scan = copy.copy(d["scan"])
    p0, x0 = d["problems"]["c0"]
    node, keep = copy.deepcopy(d["node"]), d["keep"].copy()
    candidate = int(np.flatnonzero(scan.norads == norad)[0])
    for k in targets:
        i, sl = p0.members[k], p0.slices[k]
        t = scan.tracks[i]
        # Explicit whole-curve candidate change. Receiver gauge comes from
        # existing qualified curves; no target point is discarded.
        f, _ = family_frequency(p0, x0, candidate, times=t["times"])
        terms = profile(corrected_observation(p0, x0, i), t["rf_hz"]/11.5e9*f, *scan.white[i])
        node["seed"]["rows"][k].update(candidate_index=candidate, candidate_norad=norad)
        node["aliases"][k] = int(terms["alias"][0])
        keep[sl] = True
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    old_mean = dict(zip(p0.labels, d["means"], strict=True))
    means = np.array([old_mean[j] for j in labels])
    scan, node = receiver_basis(scan, node, basis)
    pair, problems = {}, {}
    for arm in ARMS:
        reference, x, history = np.zeros(len(means)), np.zeros(2), []
        for epoch in range(5):
            p = make_event_problem(scan, node, keep, arm, reference, d["powers"], means,
                d["model"], list(events), base_problem_factory=partial(make_problem, support_policy="active"))
            attach_event_predictive(p, d["entries"], d["powers"]); cached(p)
            fitted = fit(p, x, iterations=48); x = np.asarray(fitted["parameters"])
            phase = np.clip(p.state(x)["phases"][p.labels], -15, 15)
            history.append(dict(fit=fitted, phase_change_s=float(np.max(abs(phase-reference)))))
            reference = phase
        r = summary(p, x, d["entries"])
        curved, predictive, associated, owners = report.memberships(p, x, d["entries"])
        c = p.calculate(x)
        r.update(history=history, final_phase_change_s=history[-1]["phase_change_s"],
            curved_points=len(curved), predictive_points=len(predictive),
            raw_associated_points=len(associated), raw_associated_ids=sorted(associated),
            postfit_only_points=len(associated-curved-predictive),
            targets=[dict(gate=next(g for g in r["gates"]["tracks"] if g["component"]==p.rows[k]["component"]),
                times_s=scan.tracks[p.members[k]]["times"],
                values_hz=scan.tracks[p.members[k]]["values"],
                conditional_residual_hz=c["conditional_residual_hz"][p.slices[k]]) for k in targets])
        pair[arm] = r; problems[arm] = (p, x)
    return dict(norad=norad, basis=basis, events=list(events), node=node, mask=keep, means=means,
                arms=pair, paired_valid=pair_passes(pair, include_linear=True)), problems


def figures(out, inv, trials):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True)
    colors = ("#b91c1c", "#2563eb")
    candidate = inv["screens"][0]["active"]["norad"]
    for s, color in zip(inv["screens"], colors, strict=True):
        r = s["active"]
        axes[0].plot(r["times_s"], r["residual_hz"], ".-", color=color, label=s["component"].split("-RF")[0])
    for r in inv["retained"]:
        t = np.asarray(r["times_s"]); mask = (t>=65)&(t<=150)&np.asarray(r["active_mask"])
        if mask.sum()<4: continue
        if r["norad"] == candidate:
            axes[1].plot(t[mask], np.asarray(r["residual_hz"])[mask], ".-", label=f"RX{r['receiver']} CH{r['channel']} ({mask.sum()} points)")
        elif r["receiver"] == 1:
            axes[2].plot(t[mask], np.asarray(r["residual_hz"])[mask], ".-", label=f"{r['norad']} CH{r['channel']}")
    for ax, title in zip(axes, ("Unassociated CH7/CH8: same residual pattern", f"Other retained tracks of satellite {candidate}", "Other satellites on RX1 during the same interval"), strict=True):
        ax.set_title(title); ax.set_ylabel("Profile residual (Hz)"); ax.axhline(0, color="gray", lw=.8)
        ax.grid(alpha=.2); ax.legend(loc="upper left", bbox_to_anchor=(1.01,1), fontsize=8)
    axes[-1].set_xlabel("Time in scan (s)")
    fig.suptitle("Frozen CH1-recovered baseline: receiver-versus-family discrepancy audit")
    fig.tight_layout(); fig.savefig(out/"residual_context.png", dpi=150); plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharex=True)
    for col, arm in enumerate(ARMS):
        for name, result in trials.items():
            if result["norad"] != candidate: continue
            for row, target in enumerate(result["arms"][arm]["targets"]):
                gate = target["gate"]
                axes[row,col].plot(target["times_s"], target["conditional_residual_hz"], ".-", ms=3,
                    label=f"{name}: {gate['conditional_residual_gate']['rms_hz']:.1f} Hz, {'pass' if gate['compatible'] else 'fail'}")
        for row, ch in enumerate((7,8)):
            axes[row,col].set_title(f"RX1 CH{ch}, {arm}"); axes[row,col].axhline(0, color="gray", lw=.8)
            axes[row,col].grid(alpha=.2); axes[row,col].legend(fontsize=8)
            axes[row,col].set_ylabel("Conditional residual (Hz)")
            axes[row,col].set_xlabel("Time in scan (s)")
    fig.suptitle("Whole-curve recovery trials: all original target points retained")
    fig.tight_layout(); fig.savefig(out/"recovery_residuals.png", dpi=150); plt.close(fig)


def main(args):
    out = args.output; out.mkdir(parents=True, exist_ok=False)
    d = context(args); targets = select_targets(d); inv = inventory(d, targets)
    report.write(out/"inventory.json", inv)
    print("Targets", [(s["component"], s["previous_nominee"], s["active"]["norad"]) for s in inv["screens"]], flush=True)
    trials = {}
    for candidate in inv["candidates"]:
        for basis in ("original", "fine"):
            name = f"{candidate}_{basis}"
            began = time.monotonic()
            result, _ = trial(d, targets, candidate, basis)
            result["seconds"] = time.monotonic()-began
            trials[name] = result
            report.write(out/(name+".json"), result)
            print(name, "valid", result["paired_valid"],
                [(a, r["raw_associated_points"], [(t["gate"]["compatible"],t["gate"]["conditional_residual_gate"]["rms_hz"]) for t in r["targets"]],
                  [g["component"] for g in r["gates"]["tracks"] if not g["compatible"]]) for a,r in result["arms"].items()], flush=True)
    report.write(out/"summary.json", dict(trials={k:dict(paired_valid=r["paired_valid"],seconds=r["seconds"]) for k,r in trials.items()},
        original_points_not_removed=True, no_GPS_or_future_TLE=True, paired_c_data_and_budget=True,
        start_east_north_km=[0,0], box_width_km=25, phase_rounds=5, position_steps=48,
        note="Raw membership counts are not accepted if any existing gate fails"))
    figures(out, inv, trials)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--ch1", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    main(parser.parse_args())
