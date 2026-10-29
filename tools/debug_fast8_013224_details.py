"""Case-specific 013224 rejection/orphan diagnostics, with no position refit."""

import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import debug_fast_graph_unassociated as report


def main(args):
    out=args.output;out.mkdir(exist_ok=False)
    terminal,record,entries,scan,problems,replay=report.saved_context(args.run,args.release)
    from leo.analysis.research.retained_track_likelihood import PERIOD,profile
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from evaluate_ds23_phase_refreshed import FreshScan
    from investigate_dsx01_localization_failures import DiagnosticNormal
    root=args.run/"inference/SCAN"
    observations=report.read(root/"observations.json");raw={o["observation_id"]:o for o in observations}
    roles={r["observation_id"]:r["role_fitted_c"] for r in csv.DictReader((args.diagnostics/"all_GLRT_points.csv").open())}
    diagnostic=report.read(args.diagnostics/"track_diagnostics.json")
    # Each orphan remains unassociated. This only measures proximity to a
    # previously found polynomial, including at most eight seconds extrapolation.
    orphan=[]
    for o in observations:
        if roles[o["observation_id"]]!="unassociated_outside_graph":continue
        offers=[]
        for t in scan.tracks:
            if (t["receiver"],t["channel"])!=(o["receiver"],o["channel"]):continue
            for piece in t["pieces"]:
                if not piece["start_s"]-8<=o["time_s"]<=piece["end_s"]+8:continue
                y=np.polynomial.legendre.legval((o["time_s"]-piece["reference_time_s"])/piece["time_scale_s"],piece["coefficients_hz"])
                delta=(o["measured_cfo_hz"]-y+PERIOD/2)%PERIOD-PERIOD/2
                if abs(delta)<=450:
                    retained=any(not roles[oid].startswith("unassociated") for oid in t["observation_ids"])
                    offers.append((abs(delta),t["key"],retained,piece["start_s"]<=o["time_s"]<=piece["end_s"]))
        best=min(offers) if offers else None
        category=("near_retained_polynomial" if best and best[2] else "near_rejected_polynomial" if best else "no_nearby_polynomial")
        orphan.append(dict(o,proximity_category=category,nearest_component=best[1] if best else None,
                           absolute_frequency_distance_hz=best[0] if best else None,inside_piece_time_span=best[3] if best else None))
    report.table(out/"outside_graph_points.csv",orphan)
    categories={k:sum(r["proximity_category"]==k for r in orphan) for k in sorted({r["proximity_category"] for r in orphan})}
    # Replay the selected discovery endpoint; do not fit new parameters.
    discovery=report.read(root/"fit_radio_noise.json")
    branch=next(c for c in discovery["choices"] if c["hypothesis"]==discovery["selected_hypothesis"])
    discovery_scan=FreshScan(root,noise_mode="radio")
    saved=branch["arms"]["c0"]
    p=DiagnosticNormal(discovery_scan,branch["node"],discovery_scan.radio_sigma_hz,False,reference=np.asarray(saved["reference"]))
    x=np.asarray(saved["fit"]["parameters"]);residual=p.residual(x)
    score_delta=float(residual@residual-saved["fit"]["score"])
    if abs(score_delta)>1e-5:raise ValueError(f"Discovery stage failed exact replay {score_delta}")
    state=p.state(x);frequency,elevation=p.conditional_frequency(x);per_track=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        t=p.scan.tracks[i];q=t["rf_hz"]/11.5e9
        y=t["values"]-p.scan.hardware(t,state["beta"])-q*p.scan.rx_basis[i]@state["smooth"][t["receiver"]-1]
        terms=profile(y,q*frequency[sl],*p.scan.white[i]);noise=batch_noise_screen(terms["innovations"],t["times"])
        passed=bool(terms["rms"][0]<=450 and abs(terms["bias"][0])<=3000 and noise["noise_screen_pass"][0] and elevation[sl].min()>=0)
        per_track.append(dict(component=t["key"],norad=row["candidate_norad"],receiver=t["receiver"],channel=t["channel"],
            rms_hz=float(terms["rms"][0]),bias_hz=float(terms["bias"][0]),profile_pass_before_owner_cascade=passed,
            noise={k:float(v[0]) for k,v in noise.items()},minimum_elevation_deg=float(elevation[sl].min())))
    target="SCAN-RX1-CH1-T002-RF10940312500.000000"
    target_rows=[r for r in per_track if r["norad"]==58099]
    good_owners=sorted({(r["receiver"],r["channel"]) for r in target_rows if r["profile_pass_before_owner_cascade"]})
    target_index=int(np.flatnonzero(scan.norads==58099)[0])
    initial=report.read(root/"result.json");algo=report.read(root/"algo02_result.json")
    # The only post-salvage rejection was this component. Restore precisely its
    # saved selected support to reconstruct that input mask, without refitting.
    from propagate_ds23_arc_positions import PositionNormal
    initial_problem=PositionNormal(scan,initial["final_node"],scan.radio_sigma_hz,False)
    before=np.asarray(initial["final_mask"],bool).copy()
    for row,sl in zip(initial_problem.rows,initial_problem.slices,strict=True):
        if row["component"]==target:before[sl]=True
    owners_before=sorted({(scan.tracks[i]["receiver"],scan.tracks[i]["channel"])
                         for row,i,sl in zip(initial_problem.rows,initial_problem.members,initial_problem.slices,strict=True)
                         if row["candidate_index"]==target_index and before[sl].any()})
    if int(before.sum())!=initial["post_salvage_history"][0]["active_points"]:
        raise ValueError("Cannot reconstruct the saved pre-rejection mask")
    traces=dict(discovery_score_replay_difference=score_delta,selected_discovery_branch=discovery["selected_hypothesis"],
        discovery_58099_rows=target_rows,discovery_58099_in_physical_mode_supported_set=target_index in p.supported,
        profile_passing_receiver_channel_owners=good_owners,required_owners_for_fitted_physical_modes=2,
        initial_rejected=target in initial["initial_failed_components"],post_salvage_history=initial["post_salvage_history"],
        post_salvage_input_points=int(before.sum()),post_salvage_58099_passing_support_owners=owners_before,
        post_salvage_58099_physical_modes_allocated=target_index in initial_problem.supported,
        salvage_58099=[r for r in initial["trims"] if r["component"]==target],algo02_gate_history=algo["curved_gate_history"])
    report.write(out/"rejection_trace.json",traces)
    # Shared receiver/satellite residual pattern in CH7 and CH8: nearest-time
    # pairs only, one-to-one, within one second. No resampling creates points.
    shared=[next(r for r in diagnostic if r["component"].startswith(f"SCAN-RX1-CH{ch}-T000"))["active"] for ch in (7,8)]
    t1,t2=[np.asarray(r["times_s"]) for r in shared];r1,r2=[np.asarray(r["residual_hz"]) for r in shared]
    offers=sorted((abs(a-b),i,j) for i,a in enumerate(t1) for j,b in enumerate(t2) if abs(a-b)<=1.)
    used1=set();used2=set();pairs=[]
    for gap,i,j in offers:
        if i in used1 or j in used2:continue
        used1.add(i);used2.add(j);pairs.append((i,j,gap))
    correlation=float(np.corrcoef([r1[i] for i,j,gap in pairs],[r2[j] for i,j,gap in pairs])[0,1])
    report.write(out/"orphan_and_shared_summary.json",dict(outside_graph_counts=categories,
        proximity_gate_hz=450,max_extrapolation_s=8,proximity_is_not_association=True,
        shared_57701_CH7_CH8=dict(nearest_pairs=len(pairs),maximum_pair_time_gap_s=max(gap for i,j,gap in pairs),correlation=correlation),
        fractional_margin_medians={role:float(np.median([o["fractional_margin"] for o in observations if roles[o["observation_id"]]==role])) for role in sorted(set(roles.values()))}))
    by_id={oid:t["key"] for t in scan.tracks for oid in t["observation_ids"]}
    by_key={d["component"]:d for d in diagnostic};orphan_by_id={r["observation_id"]:r for r in orphan}
    inventory=list(csv.DictReader((args.diagnostics/"all_GLRT_points.csv").open()));explanations={}
    for row in inventory:
        oid=row["observation_id"];role=row["role_fitted_c"];key=by_id.get(oid);d=by_key.get(key)
        if not role.startswith("unassociated"):reason=role
        elif role=="unassociated_outside_graph":reason=orphan_by_id[oid]["proximity_category"]
        elif d["partially_retained"]:reason="masked_points_of_retained_curve"
        elif key==target:reason="two_owner_support_cascade_58099"
        elif key.startswith(("SCAN-RX1-CH7-T000","SCAN-RX1-CH8-T000")):reason="structured_shared_residual_57701"
        elif key.startswith("SCAN-RX1-CH3-T001"):reason="curved_track_joint_shape_mismatch"
        else:reason="short_track_diagnostic_candidate_only"
        row.update(graph_component=key or "",explanation_category_fitted_c=reason)
        explanations[reason]=explanations.get(reason,0)+1
    report.table(out/"all_GLRT_points.csv",inventory);report.write(out/"explanation_counts.json",explanations)
    fig,axes=plt.subplots(2,2,figsize=(15,9),layout="constrained")
    focus=next(r for r in diagnostic if r["component"]==target);t=next(t for t in scan.tracks if t["key"]==target);match=focus["catalogue"]
    native=np.array([raw[oid]["measured_cfo_hz"] for oid in t["observation_ids"]]);tt=np.asarray(t["times"])
    axes[0,0].scatter(tt,native/1000,c="crimson",s=18,label="Unassociated GLRT")
    axes[0,0].plot(tt,(native-np.asarray(match["residual_hz"]))/1000,c="tab:blue",label="58099 causal orbit + frozen receiver + diagnostic offset")
    axes[0,0].set(title="RX1 CH1 T002: 74 points remain unassociated",ylabel="Native CFO (kHz)",xlabel="Time (s)");axes[0,0].legend(fontsize=8)
    axes[1,0].plot(tt,match["residual_hz"],"o-",ms=3,c="tab:blue");axes[1,0].axhline(0,c=".4",lw=.8)
    axes[1,0].set(title=f"58099 diagnostic: RMS {match['rms_hz']:.1f} Hz; phase {match['phase_s']:.1f} s",ylabel="Residual (Hz)",xlabel="Time (s)")
    for ch,row,color in zip((7,8),shared,("tab:purple","tab:orange"),strict=True):
        axes[0,1].plot(row["times_s"],row["residual_hz"],".-",c=color,label=f"RX1 CH{ch}: RMS {row['rms_hz']:.0f} Hz; ACF {row['noise']['lag1_acf']:.2f}")
    axes[0,1].set(title="57701: correlated CH7/CH8 residuals, frozen phase",ylabel="Residual (Hz)",xlabel="Time (s)");axes[0,1].legend(fontsize=8)
    axes[1,1].scatter([r1[i] for i,j,gap in pairs],[r2[j] for i,j,gap in pairs],s=22)
    axes[1,1].set(title=f"One-to-one time pairs ≤1 s: n={len(pairs)}, r={correlation:.2f}",xlabel="CH7 residual (Hz)",ylabel="CH8 residual (Hz)")
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle("Two distinct causes: owner-support rejection versus structured residuals\nAll candidate overlays are diagnostic; production associations are unchanged")
    fig.savefig(out/"key_failures.png",dpi=170);fig.savefig(out/"key_failures.pdf");plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout="constrained")
    axes[0].bar(range(len(categories)),list(categories.values()),color=[".5","tab:purple","tab:blue"][:len(categories)])
    axes[0].set(xticks=range(len(categories)),xticklabels=[k.replace("_","\n") for k in categories],ylabel="Unassociated GLRT points",title="365 points outside every graph track")
    for role,color in [("curved_likelihood","tab:blue"),("unassociated_graph","crimson"),("unassociated_outside_graph","darkorange")]:
        values=[o["fractional_margin"] for o in observations if roles[o["observation_id"]]==role]
        axes[1].hist(values,bins=np.linspace(0,max(o["fractional_margin"] for o in observations),40),histtype="step",density=True,label=role.replace("_"," "),color=color)
    axes[1].set(title="Detection strength does not establish satellite identity",xlabel="Fractional GLRT margin",ylabel="Density");axes[1].legend(fontsize=8)
    fig.savefig(out/"outside_graph_accounting.png",dpi=170);plt.close(fig)
    report.figures(out,observations,scan.tracks,roles,diagnostic,args.title)
    print(json.dumps(dict(outside_graph_counts=categories,shared_residual_correlation=correlation,
                         good_58099_owners=good_owners,score_replay_difference=score_delta)),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True);parser.add_argument("--diagnostics",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--release",type=Path,required=True)
    parser.add_argument("--title",required=True);main(parser.parse_args())
