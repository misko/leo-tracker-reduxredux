"""Bounded DS23-0217 confidence, identity, residual-transfer and multi-peak experiments.

Inference stages never read the evaluation coordinate. Reporting is separate.
Existing ALGO01 inputs and outputs are immutable in this experiment.
"""

import argparse
import copy
import itertools
import json
import time
from pathlib import Path

import numpy as np

from audit_ds23_algo01_coverage import retained_metrics
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from investigate_algo01_ds23_0217 import SOURCE, CASE, context, diagnostics, problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from localize_merged_track_catalogue import raw_curvature
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, sha, write
from run_dsx01_clean_region import zero_state

from leo.analysis.polynomial_tracklets import TrackConfig, _predict, _refine, _diagnose
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency, prepare_phase_geometry
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD, projected_receiver_basis
from leo.analysis.research.visible_arc_variants import deduplicate, wrap

OUT = ROOT / "reports/2026_10_18_algo01_0217_improvements"
ARMS = ("c0", "fitted_c")


def powers_from_confidence(confidence, floor=.2):
    c = np.asarray(confidence, float)
    if c.ndim != 1 or not np.isfinite(c).all() or np.any((c < 0) | (c > 1)) or not 0 < floor <= 1:
        raise ValueError("finite confidence in [0,1] and floor in (0,1] required")
    return floor + (1 - floor) * c


def competitor_confidence(costs, incumbent):
    """Conditional identity weight, never advertised as calibrated probability."""
    costs = np.asarray(costs, float)
    delta = np.clip((costs - np.nanmin(costs)) / 2, 0, 700)
    probabilities = np.exp(-delta)
    probabilities /= probabilities.sum()
    others = costs.copy()
    others[incumbent] = np.inf
    return float(probabilities[incumbent]), float(np.min(others) - costs[incumbent])


def candidate_profile(y, f, derivative, elevation, sigma, widths):
    """All-bank phase/constant screening under causal zero-centered priors.

    Radio calibration is frozen; orbital modes are omitted in this proposal
    approximation. Every final identity is scored with the full physical model.
    """
    y, f, d = np.asarray(y), np.asarray(f), np.asarray(derivative)
    n, variance = len(y), sigma**2
    alias = np.rint((f.mean(axis=1) - y.mean()) / PERIOD).astype(int)
    raw = y[None] + alias[:, None] * PERIOD - f
    bden = n + variance / 1000**2
    sy, sd = raw.sum(axis=1), d.sum(axis=1)
    information = np.maximum(0, (d*d).sum(axis=1) - sd**2 / bden)
    phi = ((raw*d).sum(axis=1) - sd*sy/bden) / (information + variance / widths**2)
    phi = np.clip(phi, -15, 15)
    bias = (sy - sd*phi) / bden
    residual = raw - phi[:, None]*d - bias[:, None]
    # Determinant of I + whitened two-column design Gram.
    a = 1 + n*1000**2/variance
    b = 1000*widths*sd/variance
    c = 1 + widths**2*(d*d).sum(axis=1)/variance
    cost = (residual**2).sum(axis=1)/variance + (bias/1000)**2 + (phi/widths)**2
    cost += np.log(np.maximum(1, a*c-b*b))
    cost[np.min(elevation, axis=1) < 0] = np.inf
    return dict(cost=cost, aliases=alias, phase_s=phi, bias_hz=bias,
                rms_hz=np.sqrt(np.mean(residual**2, axis=1)))


def make_problem(scan, node, arm, keep, reference, weights=None):
    p = problem(scan, node, arm, keep, reference)
    if weights is not None:
        # Bind only this experimental instance; no runtime component changes.
        original = p.calculate

        def calculate(x):
            result = JointMarginal.calculate(p, x)
            raw = p.values - p.q * result["intercept"]
            present = np.unique(p.noise_groups[p.keep])
            bound = hierarchical_bound(raw[p.keep], result["features"][p.keep],
                                       p.point_noise[p.keep], p.noise_groups[p.keep],
                                       powers=np.asarray(weights)[present])
            precision = np.zeros(len(p.members))
            precision[present] = bound["noise_precision"]
            bound["noise_precision"] = precision
            bound["conditional_residual_hz"] = raw - result["features"] @ bound["coefficient"]
            volume = float(2*np.sum(np.asarray(weights)[p.noise_groups[p.keep]] *
                                    np.log(p.point_noise[p.keep]/40)))
            bound["residual"] = np.r_[bound["residual"], np.sqrt(volume)]
            result.update(bound)
            return result

        p.calculate = calculate
        p.unweighted_calculate = original
    return p


def refit(scan, node, keep, arm, weights=None, rounds=5, iterations=48, start=(0, 0)):
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    reference, anchor, history = np.zeros(len(labels)), np.array(start, float), []
    for epoch in range(rounds):
        p = make_problem(scan, node, arm, keep, reference, weights)
        fitted = fit(p, anchor, iterations=iterations)
        anchor = np.asarray(fitted["parameters"])
        phase = p.state(anchor)["phases"][p.labels]
        history.append(dict(epoch=epoch, fit=fitted, phase_change_s=float(np.max(abs(phase-reference)))))
        reference = np.clip(phase, -15, 15)
    result = diagnostics(p, anchor)
    result.update(history=history, gates=retained_metrics(p, anchor),
                  final_phase_change_s=history[-1]["phase_change_s"])
    return result


def prepare():
    scan, node, keep, baseline = context()
    saved = baseline["arms"]["c0"]["record"]
    point = np.asarray(saved["endpoint_east_north_km"])
    p = problem(scan, node, "c0", keep, np.array(saved["phase_reference"]))
    state = p.state(point)
    widths, prior_receipt = phase_widths(scan, list(range(len(scan.norads))))
    widths = np.asarray(widths)
    positions = [point, np.zeros(2)] + [np.clip(point+d, -12.5, 12.5)
                                       for d in (np.array([2, 0]), np.array([-2, 0]),
                                                 np.array([0, 2]), np.array([0, -2]))]
    summaries, proposals = {}, {}
    for number, xy in enumerate(positions):
        f, elevation, derivative = phase_linear_frequency(scan.geometry, *latlon(xy))
        for k, (row, member, sl) in enumerate(zip(p.rows, p.members, p.slices, strict=True)):
            tr, ix = scan.tracks[member], scan.index[member]
            q = tr["rf_hz"] / 11.5e9
            y = tr["values"] - scan.hardware(tr, state["beta"])
            y -= q * scan.rx_basis[member] @ state["smooth"][tr["receiver"]-1]
            screen = candidate_profile(y, q*f[:, ix], q*derivative[:, ix], elevation[:, ix],
                                       scan.radio_sigma_hz, widths)
            incumbent = row["candidate_index"]
            confidence, gap = competitor_confidence(screen["cost"], incumbent)
            ordered = np.argsort(screen["cost"])[:5]
            entries = [dict(candidate_index=int(j), norad=int(scan.norads[j]),
                            **{name: float(screen[name][j]) for name in
                               ("cost", "phase_s", "bias_hz", "rms_hz")},
                            alias=int(screen["aliases"][j])) for j in ordered]
            summaries.setdefault(row["component"], []).append(dict(position_index=number,
                incumbent_conditional_weight=confidence, gap_to_best_other=gap, alternatives=entries))
            # Alternative proposals include all five best all-bank candidates at
            # each RF-defined anchor. No truth-selected candidate or location.
            for e in entries:
                if e["candidate_index"] != incumbent:
                    proposals.setdefault((k, e["candidate_index"]), []).append(dict(e, position_index=number))
    confidences = []
    for k, row in enumerate(p.rows):
        records = summaries[row["component"]]
        # Endpoint and ±2 km stability; regional-center entry is a search anchor.
        local = [r for r in records if r["position_index"] != 1]
        confidence = min(r["incumbent_conditional_weight"] for r in local)
        track = scan.tracks[p.members[k]]
        confidences.append(dict(component=row["component"], norad=int(scan.norads[row["candidate_index"]]),
            confidence=confidence, endpoint_weight=records[0]["incumbent_conditional_weight"],
            minimum_gap=min(r["gap_to_best_other"] for r in local), points=len(track["times"]),
            receiver=track["receiver"], channel=track["channel"], candidate_index=row["candidate_index"]))
    # Rank near alternatives first; retain two for every original component.
    proposal_rows = []
    for (k, j), records in proposals.items():
        best = min(records, key=lambda r: r["cost"])
        proposal_rows.append(dict(row_index=k, incumbent_index=p.rows[k]["candidate_index"], **best))
    proposal_rows = [e for k in range(len(p.rows))
                     for e in sorted([r for r in proposal_rows if r["row_index"] == k],
                                     key=lambda r: r["cost"])[:2]]
    write(OUT / "preparation.json", dict(confidence=confidences, screens=summaries,
          positions=positions, proposals=proposal_rows, causal_phase_priors=prior_receipt,
          candidate_count=len(scan.norads), original_rows=p.rows,
          GPS_used=False, confidence_is_conditional_uncalibrated_proxy=True,
          proposal_approximation="fixed RF-calibration phase+constant; full physical model for final scoring",
          source_sha256=sha(Path(__file__)),
          inputs={str(SOURCE / CASE / n): sha(SOURCE / CASE / n)
                  for n in ("observations.json", "tracks.json", "result.json", "tracking.json", "bank.npz")}))
    print("prepared", len(p.rows), "curves", len(scan.norads), "candidates", len(proposal_rows), "alternatives", flush=True)


def weighted():
    scan, node, keep, _ = context()
    confidence = np.array([r["confidence"] for r in read(OUT / "preparation.json")["confidence"]])
    variants = {"baseline_replay": (np.ones(len(confidence)), keep),
                "confidence_soft": (powers_from_confidence(confidence), keep),
                "confidence_strong": (powers_from_confidence(confidence, .05), keep)}
    p = problem(scan, node, "c0", keep)
    selected = keep.copy()
    for c, sl in zip(confidence, p.slices, strict=True):
        if c < .95:
            selected[sl] = False
    if selected.any():
        variants["confident_only_095"] = (np.ones(len(confidence)), selected)
    for name, (weights, mask) in variants.items():
        start = time.monotonic()
        pair = {arm: refit(scan, node, mask, arm, None if name in
                          ("baseline_replay", "confident_only_095") else weights) for arm in ARMS}
        write(OUT / f"weight_{name}.json", dict(name=name, weights=weights, mask=mask, arms=pair,
              same_weights_and_mask_in_c_pair=True, GPS_used=False,
              score_is_generalized_evidence=name.startswith("confidence_"), seconds=time.monotonic()-start))
        print(name, {a: pair[a]["endpoint_east_north_km"].tolist() for a in ARMS}, flush=True)


def changed_node(scan, original, changes):
    node = copy.deepcopy(original)
    for change in changes:
        k, j = change["row_index"], change["candidate_index"]
        node["seed"]["rows"][k].update(candidate_index=j, candidate_norad=int(scan.norads[j]))
        node["aliases"][k] = change["alias"]
    node["seed"]["state"] = zero_state(scan)
    return node


def identities():
    scan, original, keep, baseline = context()
    prep = read(OUT / "preparation.json")
    endpoint = baseline["arms"]["c0"]["record"]["endpoint_east_north_km"]
    trials = []
    # Screen every proposed single replacement with the full nuisance model.
    for i, change in enumerate(prep["proposals"]):
        node = changed_node(scan, original, [change])
        fitted = refit(scan, node, keep, "c0", rounds=3, iterations=20, start=endpoint)
        trials.append(dict(changes=[change], score=fitted["score"],
                           endpoint=fitted["endpoint_east_north_km"],
                           passing_points=fitted["gates"]["accepted_points"]))
        if i % 10 == 0:
            print("identity singles", i, len(prep["proposals"]), flush=True)
    write(OUT / "identity_singles.json", trials)
    # Best six distinct component changes, selected by RF loss alone.
    pool, rows = [], set()
    for tr in sorted(trials, key=lambda r: r["score"]):
        change = tr["changes"][0]
        if change["row_index"] not in rows:
            pool.append(change)
            rows.add(change["row_index"])
        if len(pool) == 6:
            break
    combinations = [list(c) for n in (2, 3) for c in itertools.combinations(pool, n)]
    # Also test coherent whole-family replacements proposed for every member.
    family_trials = []
    for incumbent in sorted({r["candidate_index"] for r in original["seed"]["rows"]}):
        members = [k for k, row in enumerate(original["seed"]["rows"]) if row["candidate_index"] == incumbent]
        if len(members) < 2:
            continue
        candidates = set(c["candidate_index"] for c in prep["proposals"] if c["row_index"] in members)
        for j in candidates:
            changes = [next((c for c in prep["proposals"] if c["row_index"] == k and c["candidate_index"] == j), None)
                       for k in members]
            if all(c is not None for c in changes):
                family_trials.append(changes)
    combinations.extend(family_trials)
    combo_results = []
    for i, changes in enumerate(combinations):
        node = changed_node(scan, original, changes)
        fitted = refit(scan, node, keep, "c0", rounds=3, iterations=20, start=endpoint)
        combo_results.append(dict(changes=changes, score=fitted["score"],
                                 endpoint=fitted["endpoint_east_north_km"],
                                 passing_points=fitted["gates"]["accepted_points"]))
        if i % 10 == 0:
            print("identity combinations", i, len(combinations), flush=True)
    write(OUT / "identity_combinations.json", combo_results)
    # Pair the incumbent and best single / joint alternatives with equal cold
    # regional-center budgets. Selection is by c0 RF objective, never GPS.
    finalists = [dict(changes=[], name="incumbent")]
    if trials:
        finalists.append(dict(min(trials, key=lambda r: r["score"]), name="best_single"))
    if combo_results:
        finalists.append(dict(min(combo_results, key=lambda r: r["score"]), name="best_joint"))
    for trial in finalists:
        node = changed_node(scan, original, trial["changes"])
        trial["arms"] = {arm: refit(scan, node, keep, arm) for arm in ARMS}
    write(OUT / "identity_finalists.json", dict(finalists=finalists,
          singles=len(trials), joint_proposals=len(combo_results), pool=pool,
          no_exhaustiveness_claim=True, GPS_used=False,
          same_observations_priors_budget_and_identities_in_c_pairs=True,
          selected_by="c0 RF loss, not position error; final gates reported separately"))


def residuals():
    scan, node, keep, baseline = context()
    records, pairwise = [], []
    for arm in ARMS:
        saved = baseline["arms"][arm]["record"]
        p = problem(scan, node, arm, keep, np.array(saved["phase_reference"]))
        x = np.asarray(saved["endpoint_east_north_km"])
        c = p.calculate(x)
        residual = c["conditional_residual_hz"]
        for row, member, sl in zip(p.rows, p.members, p.slices, strict=True):
            tr, mask = scan.tracks[member], keep[sl]
            t, r = tr["times"][mask], residual[sl][mask]
            centered = t-t.mean()
            slope = float(centered@r/(centered@centered))
            screen = batch_noise_screen(r[None], t)
            records.append(dict(arm=arm, component=row["component"], norad=int(scan.norads[row["candidate_index"]]),
                receiver=tr["receiver"], channel=tr["channel"], band="CH1-4" if tr["channel"]<=4 else "CH5-8",
                time_s=t, residual_hz=r, noise_hz=p.point_noise[sl][mask],
                mean_hz=float(r.mean()), slope_hz_s=slope, rms_hz=float(np.sqrt(np.mean(r*r))),
                noise_precision=float(c["noise_precision"][len(records)%len(p.rows)]),
                screens={k: np.asarray(v)[0] for k,v in screen.items()}))
        local = [r for r in records if r["arm"]==arm]
        for a,b in itertools.combinations(local,2):
            ta,tb=np.asarray(a["time_s"]), np.asarray(b["time_s"])
            ra,rb=np.asarray(a["residual_hz"]),np.asarray(b["residual_hz"])
            # Independent nearest time pairs, no synthetic interpolation votes.
            used, ia, ib = set(), [], []
            for k in np.argsort(ta):
                order=np.argsort(abs(tb-ta[k]))
                j=next((int(v) for v in order if int(v) not in used and abs(tb[v]-ta[k])<=.5),None)
                if j is not None:
                    ia.append(k);ib.append(j);used.add(j)
            if len(ia)<6:
                continue
            aa,bb=ra[ia],rb[ib]
            corr=float(np.corrcoef(aa,bb)[0,1])
            pairwise.append(dict(arm=arm,left=a["component"],right=b["component"],pairs=len(ia),
                same_family=a["norad"]==b["norad"],same_receiver=a["receiver"]==b["receiver"],
                same_channel=a["channel"]==b["channel"],correlation=corr,
                difference_rms_hz=float(np.sqrt(np.mean((aa-bb)**2)))))
    # Receiver/channel deletions test whether one hardware grouping drives bias.
    controls=[]
    p=problem(scan,node,"c0",keep)
    for kind, values in (("receiver",(1,2)),("channel",(1,2,3,4))):
        for value in values:
            mask=keep.copy()
            for member,sl in zip(p.members,p.slices,strict=True):
                if scan.tracks[member][kind]==value:
                    mask[sl]=False
            arms={arm:refit(scan,node,mask,arm) for arm in ARMS}
            controls.append(dict(kind=kind,removed=value,arms=arms))
            print("residual group deletion",kind,value,flush=True)
    write(OUT/"residuals.json",dict(tracks=records,pairs=pairwise,group_controls=controls,
        available_bands=sorted({r["band"] for r in records}),
        only_conditioned_postfit_residuals=True,
        correlation_is_descriptive_not_identity_or_causation_test=True,GPS_used=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage",choices=("prepare","weighted","identities","residuals","recovery"),required=True)
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    globals()[args.stage]()
    print(args.stage,"seconds",time.monotonic()-start,flush=True)


if __name__=="__main__":
    main()
