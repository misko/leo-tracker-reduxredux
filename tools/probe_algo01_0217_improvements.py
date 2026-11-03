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


def shared_fast_basis(times, receivers, amplitude, spacing=4., width=2.):
    """Zero-mean Gaussian receiver error, with affine columns projected out."""
    t, rx=np.asarray(times), np.asarray(receivers)
    if t.shape!=rx.shape or amplitude<=0:
        raise ValueError("matching times/receiver IDs and positive fixed amplitude required")
    basis=projected_receiver_basis(t,spacing_s=spacing,width_s=width)
    return np.column_stack([amplitude*basis*(rx==r)[:,None] for r in (1,2)])


def make_problem(scan, node, arm, keep, reference, weights=None, fast=None):
    p = problem(scan, node, arm, keep, reference)
    if fast is not None:
        receivers=np.concatenate([np.full(sl.stop-sl.start,scan.tracks[i]["receiver"])
                                  for i,sl in zip(p.members,p.slices,strict=True)])
        p.fast=shared_fast_basis(p.flat_times,receivers,fast)
    if weights is not None or fast is not None:
        # Bind only this experimental instance; no runtime component changes.
        original = p.calculate

        def calculate(x):
            result = JointMarginal.calculate(p, x)
            features=result["features"]
            if fast is not None:
                stop=features.shape[1]-len(p.members)
                features=np.column_stack((features[:,:stop],p.fast,features[:,stop:]))
            raw = p.values - p.q * result["intercept"]
            present = np.unique(p.noise_groups[p.keep])
            power=np.ones(len(p.members)) if weights is None else np.asarray(weights)
            bound = hierarchical_bound(raw[p.keep], features[p.keep],
                                       p.point_noise[p.keep], p.noise_groups[p.keep],
                                       powers=power[present])
            precision = np.zeros(len(p.members))
            precision[present] = bound["noise_precision"]
            bound["noise_precision"] = precision
            bound["conditional_residual_hz"] = raw - features @ bound["coefficient"]
            volume = float(2*np.sum(power[p.noise_groups[p.keep]] *
                                    np.log(p.point_noise[p.keep]/40)))
            bound["residual"] = np.r_[bound["residual"], np.sqrt(volume)]
            result.update(bound,features=features)
            return result

        p.calculate = calculate
        p.unweighted_calculate = original
    if fast is not None:
        def conditional_frequency(x):
            result=p.calculate(x)
            start=p.hardware.shape[1]+p.smooth.shape[1]
            stop=result["features"].shape[1]-len(p.members)
            return (result["intercept"]+result["features"][:,start:stop]@
                    result["coefficient"][start:stop]/p.q,result["elevation"])
        p.conditional_frequency=conditional_frequency
    return p


def refit(scan, node, keep, arm, weights=None, rounds=5, iterations=48, start=(0, 0),fast=None):
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    reference, anchor, history = np.zeros(len(labels)), np.array(start, float), []
    for epoch in range(rounds):
        p = make_problem(scan, node, arm, keep, reference, weights,fast)
        fitted = fit(p, anchor, iterations=iterations)
        anchor = np.asarray(fitted["parameters"])
        phase = p.state(anchor)["phases"][p.labels]
        history.append(dict(epoch=epoch, fit=fitted, phase_change_s=float(np.max(abs(phase-reference)))))
        reference = np.clip(phase, -15, 15)
    result = diagnostics(p, anchor)
    result.update(history=history, gates=retained_metrics(p, anchor),
                  final_phase_change_s=history[-1]["phase_change_s"])
    if fast is not None:
        calculated=p.calculate(anchor)
        stop=calculated["features"].shape[1]-len(p.members)
        start=stop-p.fast.shape[1]
        coefficients=calculated["coefficient"][start:stop]
        result["shared_fast_correction_hz"]=p.fast@coefficients
        result["flat_times_s"]=p.flat_times
        result["prior_cost"]["fast_receiver"]=float(coefficients@coefficients)
        result["prior_cost"]["orbit"]-=float(coefficients@coefficients)
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


def replicated_weights():
    scan,node,keep,_=context()
    prep=read(OUT/"preparation.json")
    p=problem(scan,node,"c0",keep)
    owners={j:{(scan.tracks[i]["receiver"],scan.tracks[i]["channel"])
               for row,i in zip(p.rows,p.members,strict=True) if row["candidate_index"]==j}
            for j in p.labels}
    confidence={r["component"]:r["confidence"] for r in prep["confidence"]}
    replicated=np.array([len(owners[r["candidate_index"]])>=2 and confidence[r["component"]]>=.95
                         for r in p.rows])
    cross_rx=np.array([len({rx for rx,ch in owners[r["candidate_index"]]})>=2 for r in p.rows])
    selected=keep.copy()
    for good,sl in zip(replicated,p.slices,strict=True):
        if not good:
            selected[sl]=False
    variants={"replicated_family_soft":(np.where(replicated,1.,.2),keep),
              "replicated_family_only":(None,selected),
              "cross_receiver_family_soft":(np.where(cross_rx,1.,np.where(replicated,.6,.2)),keep)}
    for name,(weights,mask) in variants.items():
        pair={arm:refit(scan,node,mask,arm,weights) for arm in ARMS}
        write(OUT/f"weight_{name}.json",dict(name=name,weights=weights,mask=mask,arms=pair,
             owners={str(int(scan.norads[j])):sorted(v) for j,v in owners.items()},
             calibration_only_uses_curved_tracks=True,GPS_used=False,
             same_weights_mask_labels_and_budget_in_c_pair=True))
        print(name,{a:pair[a]["endpoint_east_north_km"].tolist() for a in ARMS},flush=True)


def gated_weight():
    scan,node,keep,_=context()
    source=read(OUT/"weight_cross_receiver_family_soft.json")
    weights=np.asarray(source["weights"])
    p=problem(scan,node,"c0",keep)
    pair=source["arms"]; history=[]
    for epoch in range(4):
        failed={r["component"] for arm in ARMS for r in pair[arm]["gates"]["tracks"] if not r["compatible"]}
        history.append(dict(epoch=epoch,failed_components=sorted(failed),points=int(keep.sum())))
        if not failed:
            break
        for row,sl in zip(p.rows,p.slices,strict=True):
            if row["component"] in failed:
                keep[sl]=False
        pair={arm:refit(scan,node,keep,arm,weights) for arm in ARMS}
    write(OUT/"weight_cross_receiver_family_soft_gated.json",dict(
        name="cross_receiver_family_soft_gated",arms=pair,weights=weights,mask=keep,
        gate_history=history,GPS_used=False,matched_c_pair_mask=True,
        original_noise_and_support_gates_unchanged=True,
        masked_nuisance_design_preserved=True))
    controls={arm:refit(scan,node,keep,arm) for arm in ARMS}
    write(OUT/"weight_gated_matched_mask_unweighted.json",dict(
        name="gated_matched_mask_unweighted",arms=controls,weights=np.ones(len(p.rows)),mask=keep,
        GPS_used=False,mask_frozen_from_paired_RF_gates=True))
    print("gated weighting retained",int(keep.sum()),"points",flush=True)


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


def unique_probe_members(indices, probes, residual, margins):
    """One peak from each physical probe; choose on residual and RF margin."""
    selected=[]
    for group in np.unique(probes[indices]):
        choices=indices[probes[indices]==group]
        cost=(residual[choices]/150)**2-2*np.log(np.maximum(margins[choices],.01))
        selected.append(int(choices[np.argmin(cost)]))
    return np.array(sorted(selected),int)


def polynomial_proposals(candidates, cfg, trials=1800, seed=217):
    """Radio-only quadratic/cubic proposal seeds, followed by frozen fit gates."""
    t=np.array([c["time_s"] for c in candidates])
    y=np.array([c["cfo_hz"] for c in candidates])
    probes=np.array([c["probe"] for c in candidates])
    margins=np.array([c["margin"] for c in candidates])
    if len(candidates)<12:
        return []
    rng=np.random.default_rng(seed)
    models={}
    for trial in range(trials):
        degree=2 if trial%3 else 3
        first=int(rng.integers(len(t)))
        eligible=np.flatnonzero((t>=t[first]) & (t<=t[first]+65))
        if len(eligible)<degree+1:
            continue
        seed_ix=np.sort(rng.choice(eligible,degree+1,replace=False))
        if np.unique(probes[seed_ix]).size!=degree+1 or np.ptp(t[seed_ix])<10:
            continue
        ts,ys=t[seed_ix],y[seed_ix]
        # Resolve interior alias integers relative to the endpoint secant.
        slope=float(wrap(ys[-1]-ys[0])/(ts[-1]-ts[0]))
        if abs(slope)>cfg.max_slope_hz_s:
            continue
        line=ys[0]+slope*(ts-ts[0])
        lifted=line+wrap(ys-line)
        ref=float(ts.mean());scale=max(float(np.ptp(ts)),1.)
        coefficient=np.polynomial.polynomial.polyfit((ts-ref)/scale,lifted,degree)
        prediction=np.polynomial.polynomial.polyval((t-ref)/scale,coefficient)
        rr=wrap(y-prediction)
        ix=np.flatnonzero((abs(rr)<450)&(t>=ts.min()-10)&(t<=ts.max()+10))
        ix=unique_probe_members(ix,probes,rr,margins)
        if len(ix)<12 or np.ptp(t[ix])<20:
            continue
        for _ in range(3):
            model=_refine(t,y,ix,prediction[ix],cfg,grow=False)
            if model is None:
                break
            prediction=_predict(model,t)
            rr=wrap(y-prediction)
            eligible=np.flatnonzero((abs(rr)<450)&(t>=t[model["indices"]].min()-10)&
                                   (t<=t[model["indices"]].max()+10))
            new=unique_probe_members(eligible,probes,rr,margins)
            if not len(new):
                model=None;break
            chunks=np.split(new,np.flatnonzero(np.diff(t[new])>cfg.max_gap_s)+1)
            new=max(chunks,key=lambda c:len(np.intersect1d(c,ix)))
            if np.array_equal(new,ix):
                break
            ix=new
        if model is None:
            continue
        # Final refit after ownership changes, with no stale coefficients.
        model=_refine(t,y,ix,prediction[ix],cfg,grow=False)
        if model is None:
            continue
        ix=np.array(model["indices"],int)
        lifted=_predict(model,t[ix])+wrap(y[ix]-_predict(model,t[ix]))
        if len(ix)<12 or not raw_curvature(dict(times=t[ix],values=lifted)):
            continue
        diag=_diagnose(model,t,y,cfg)
        if diag["quality_flags"]:
            continue
        rr=wrap(y[ix]-_predict(model,t[ix]))
        gain=9*len(ix)-np.sum((rr/cfg.noise_sigma_hz)**2)-cfg.track_penalty
        gain-=(model["degree"]+1)*np.log(len(ix))+2*np.log(trials)
        if gain<=0 or np.unique(probes[ix]).size!=len(ix) or np.max(abs(rr))>=450:
            continue
        signature=tuple(ix)
        if signature not in models:
            models[signature]=dict(indices=ix,piece=model,diagnostics=diag,
                                  gain=float(gain),values=lifted,
                                  curvature_rms_hz=float(np.sqrt(np.mean((lifted-
                                      np.column_stack((np.ones(len(ix)),t[ix]-t[ix].mean()))@
                                      np.linalg.lstsq(np.column_stack((np.ones(len(ix)),t[ix]-t[ix].mean())),lifted,rcond=None)[0])**2))))
    return sorted(models.values(),key=lambda m:-m["gain"])


def recovery():
    from evaluate_ds22_merged_tracks import CONFIG
    from propagate_ds23_arc_positions import install_tracks
    from leo.analysis.research.public_tracking_points import public_tracking_points

    scan,node,keep,baseline=context()
    document=read(SOURCE/CASE/"tracking.json")
    observations,_=public_tracking_points(document)
    by_support={(o["native_receiver_id"],o["valid_start_counter"]):o for o in observations}
    p=problem(scan,node,"c0",keep)
    owned={oid for member,sl in zip(p.members,p.slices,strict=True)
           for oid,active in zip(scan.tracks[member]["observation_ids"],keep[sl],strict=True) if active}
    cfg=TrackConfig(**read(CONFIG)["config"])
    fs,origin=document["sample_rate_hz"],document["timing"]["session_start_device_sample_counter"]
    receivers=sorted({p["receiver_id"] for p in document["probes"]})
    lanes={}
    for pi,probe in enumerate(document["probes"]):
        start=probe["valid_start_counter"]+round(probe["probe_start_ms"]*fs/1000)
        obs=by_support.get((probe["receiver_id"],start))
        if obs is None or obs["observation_id"] in owned:
            continue
        eligible=[c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]
        winner=max(eligible,key=lambda c:(c["fractional_margin"],-c["candidate_rank"]))
        for c in eligible:
            key=(receivers.index(probe["receiver_id"])+1,probe["channel"],probe["actual_rf_hz"])
            lanes.setdefault(key,[]).append(dict(time_s=(start-origin)/fs+document["probe_ms"]/2000,
                probe=pi,cfo_hz=c["fractional_tracking_cfo_hz"],margin=c["fractional_margin"],
                rank=c["candidate_rank"],winner=c is winner,observation_id=obs["observation_id"]))
    proposals=[];receipts=[]
    for li,(lane,candidates) in enumerate(sorted(lanes.items())):
        reps,_=deduplicate([c["cfo_hz"] for c in candidates],[c["margin"] for c in candidates],
                           [c["probe"] for c in candidates])
        candidates=sorted([candidates[i] for i in reps],key=lambda c:(c["time_s"],c["cfo_hz"]))
        models=polynomial_proposals(candidates,cfg,seed=217+li)
        # Exclusive physical-probe ownership across all added tracks.
        reserved=set()
        accepted=[]
        for m in models:
            ids={candidates[i]["probe"] for i in m["indices"]}
            if reserved & ids:
                continue
            reserved|=ids;accepted.append(m)
        receipts.append(dict(lane=lane,candidate_entries=len(candidates),physical_probes=len({c["probe"] for c in candidates}),
                             radio_proposals=len(models),exclusive_proposals=len(accepted)))
        for m in accepted:
            proposals.append(dict(lane=lane,candidates=[candidates[i] for i in m["indices"]],
                                  model=m))
        print("recovery lane",lane,"candidates",len(candidates),"curved",len(accepted),flush=True)
    write(OUT/"recovery_proposals.json",dict(proposals=proposals,receipts=receipts,
          excluded_original_calibration_observations=len(owned),seed=217,trials_per_lane=1800,
          one_peak_per_physical_probe_globally=True,GPS_or_orbits_used_for_polynomial_discovery=False))
    # Screen each genuinely new radio curve against the entire same causal bank
    # using the frozen RF-selected calibration. Refit only after gate acceptance.
    saved=baseline["arms"]["c0"]["record"]
    point=np.array(saved["endpoint_east_north_km"])
    baseproblem=problem(scan,node,"c0",keep,np.array(saved["phase_reference"]))
    state=baseproblem.state(point)
    widths,_=phase_widths(scan,list(range(len(scan.norads))))
    tracks,rows,aliases=copy.deepcopy(scan.tracks),copy.deepcopy(node["seed"]["rows"]),list(node["aliases"])
    fits=[]
    for number,proposal in enumerate(proposals):
        rx,ch,rf=proposal["lane"]
        candidates=proposal["candidates"]
        times=np.array([c["time_s"] for c in candidates])
        values=np.array(proposal["model"]["values"])
        dummy=dict(receiver=rx,channel=ch,times=times,rf_hz=rf)
        radio=scan.hardware(dummy,state["beta"])+rf/11.5e9*projected_receiver_basis(times)@state["smooth"][rx-1]
        geometry=prepare_phase_geometry(scan.sky,times)
        f,e,d=phase_linear_frequency(geometry,*latlon(point),rf_hz=rf)
        screen=candidate_profile(values-radio,f,d,e,scan.radio_sigma_hz,widths)
        best=np.argsort(screen["cost"])[:5]
        attempts=[];chosen=None
        for j in best:
            single=dict(time_s=scan.sky["time_s"],position_km=scan.sky["position_km"][[j]],
                        velocity_km_s=scan.sky["velocity_km_s"][[j]])
            phi=screen["phase_s"][j]
            freq,elev=paired_phase_frequency(single,times,np.zeros(len(times),int),np.array([phi]),*latlon(point))
            raw=values-radio+screen["aliases"][j]*PERIOD-rf/11.5e9*freq
            bias=float(raw.mean());rr=raw-bias
            gate=batch_noise_screen(rr[None],times)
            passed=bool(np.sqrt(np.mean(rr**2))<=450 and max(abs(rr))<450 and
                        abs(bias)<=3000 and elev.min()>=0 and gate["noise_screen_pass"][0])
            attempts.append(dict(norad=int(scan.norads[j]),candidate_index=int(j),phase_s=float(phi),
                cost=float(screen["cost"][j]),rms_hz=float(np.sqrt(np.mean(rr**2))),bias_hz=bias,passed=passed))
            if passed and chosen is None:
                chosen=int(j)
        fits.append(dict(proposal=number,attempts=attempts,chosen=chosen))
        if chosen is None:
            continue
        # Raw CFO changes only by integer alias periods. Probe observation ID
        # remains the same even when its selected frequency peak changes.
        track=dict(key=f"{CASE}-RECOVERED-{number:03}",receiver=rx,channel=ch,rf_hz=rf,
            bank="CH1-4" if ch<=4 else "CH5-8",times=times,values=values,
            observation_ids=[c["observation_id"] for c in candidates],pieces=[],
            start_s=float(times.min()),end_s=float(times.max()),quality_status="no_structure_detected")
        assert np.allclose((values-np.array([c["cfo_hz"] for c in candidates]))/PERIOD,
                           np.rint((values-np.array([c["cfo_hz"] for c in candidates]))/PERIOD),atol=1e-8)
        tracks.append(track)
        rows.append(dict(component=track["key"],candidate_index=chosen,candidate_norad=int(scan.norads[chosen]),
                         active_curvature=True,points=len(times),compatible=True))
        aliases.append(int(screen["aliases"][chosen]))
    accepted_new=len(rows)-len(node["seed"]["rows"])
    pair={}
    independent_controls=[]
    if accepted_new:
        install_tracks(scan,tracks,rows)
        newnode=dict(seed=dict(rows=rows,state=zero_state(scan)),aliases=aliases)
        extra=len(np.concatenate([t["times"] for t in tracks[-accepted_new:]]))
        newkeep=np.r_[keep,np.ones(extra,bool)]
        ids=[oid for member in scan.curved for oid in scan.tracks[member]["observation_ids"]]
        assert len(ids)==len(set(ids))
        pair={arm:refit(scan,newnode,newkeep,arm) for arm in ARMS}
        for new_index in range(accepted_new):
            single_scan,original_node,original_keep,_=context()
            selected_track=tracks[-accepted_new+new_index]
            single_rows=copy.deepcopy(original_node["seed"]["rows"])+[rows[-accepted_new+new_index]]
            install_tracks(single_scan,single_scan.tracks+[selected_track],single_rows)
            single_node=dict(seed=dict(rows=single_rows,state=zero_state(single_scan)),
                aliases=list(original_node["aliases"])+[aliases[-accepted_new+new_index]])
            selected=np.r_[original_keep,np.ones(len(selected_track["times"]),bool)]
            independent_controls.append(dict(new_track=selected_track["key"],
                arms={arm:refit(single_scan,single_node,selected,arm) for arm in ARMS},
                absent_new_tracks_do_not_create_artificial_orbital_support_requirements=True))
    write(OUT/"recovery_result.json",dict(new_curved_proposals=len(proposals),
        accepted_new_tracks=accepted_new,attempts=fits,arms=pair,
        independent_controls=independent_controls,
        tracks=[t for t in tracks if "-RECOVERED-" in t["key"]],
        same_new_tracks_labels_aliases_and_priors_in_c_pair=True,GPS_used=False,
        candidate_search_count=len(scan.norads),
        baseline_polynomial_and_satellite_gates_preserved=True,
        caveat="bounded random polynomial proposals; no claim that remaining evidence contains no tracks"))


def receiver_models():
    from ds23_radio_noise import estimate
    observations=read(SOURCE/CASE/"observations.json")
    for name in ("radio_rx_noise","shared_fast","radio_rx_noise_shared_fast"):
        scan,node,keep,_=context()
        metadata={}
        if "radio_rx_noise" in name:
            for rx in (1,2):
                local=[t for t in scan.tracks if t["receiver"]==rx]
                noise=estimate(local,[o for o in observations if o["receiver"]==rx])
                metadata[str(rx)]=noise
                for track in local:
                    for oid in track["observation_ids"]:
                        scan.fixed_window_noise["per_observation_noise_sigma_hz"][oid]=(
                            noise["per_observation_noise_sigma_hz"][oid] if noise["extra_parameter_BIC_gain"]>0
                            else noise["constant_radio_sigma_hz"])
            # WindowNoise reads the supplied per-observation map with this switch.
            scan.fixed_window_noise["extra_parameter_BIC_gain"]=1.
        fast=scan.radio_sigma_hz/np.sqrt(2) if "shared_fast" in name else None
        pair={arm:refit(scan,node,keep,arm,fast=fast) for arm in ARMS}
        write(OUT/f"receiver_model_{name}.json",dict(name=name,arms=pair,
            radio_only_noise_metadata=metadata,fast_amplitude_hz=fast,
            fast_spacing_s=4 if fast else None,fast_width_s=2 if fast else None,
            fixed_before_reading_any_position_errors=True,GPS_used=False,
            same_observations_candidates_priors_and_budgets_in_c_pair=True,
            correction_is_receiver_shared_not_per_satellite=True))
        print("receiver model",name,{a:pair[a]["endpoint_east_north_km"].tolist() for a in ARMS},flush=True)


def family_combinations():
    scan,node,keep,baseline=context()
    singles=read(OUT/"identity_singles.json")
    combinations=read(OUT/"identity_combinations.json")
    counts={j:sum(r["candidate_index"]==j for r in node["seed"]["rows"])
            for j in {r["candidate_index"] for r in node["seed"]["rows"]}}
    # Every operation changes every fragment bearing an original family label.
    operations=[r for r in singles+combinations
        if len({c["incumbent_index"] for c in r["changes"]})==1 and
        len(r["changes"])==counts[r["changes"][0]["incumbent_index"]]]
    pool=[];seen=set()
    for r in sorted(operations,key=lambda r:r["score"]):
        source=r["changes"][0]["incumbent_index"]
        if source not in seen:
            pool.append(r["changes"]);seen.add(source)
        if len(pool)==6:
            break
    results=[]
    start=baseline["arms"]["c0"]["record"]["endpoint_east_north_km"]
    for number,ops in enumerate([c for n in (2,3) for c in itertools.combinations(pool,n)]):
        changes=[c for op in ops for c in op]
        trialnode=changed_node(scan,node,changes)
        fitted=refit(scan,trialnode,keep,"c0",rounds=3,iterations=20,start=start)
        results.append(dict(changes=changes,whole_families=len(ops),score=fitted["score"],
                            endpoint=fitted["endpoint_east_north_km"],
                            passing_points=fitted["gates"]["accepted_points"]))
        if number%10==0:
            print("whole family pairs/triples",number,flush=True)
    finalist=min(results,key=lambda r:r["score"])
    finalist["arms"]={arm:refit(scan,changed_node(scan,node,finalist["changes"]),keep,arm) for arm in ARMS}
    write(OUT/"identity_whole_family_combinations.json",dict(pool=pool,results=results,
         best=finalist,GPS_used=False,selection="c0 RF loss",all_original_curved_points_retained=True,
         whole_family_means_all_original_fragments_changed_together=True))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage",choices=("prepare","weighted","replicated_weights","gated_weight","identities","residuals","recovery","receiver_models","family_combinations"),required=True)
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    globals()[args.stage]()
    print(args.stage,"seconds",time.monotonic()-start,flush=True)


if __name__=="__main__":
    main()
