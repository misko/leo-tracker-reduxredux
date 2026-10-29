"""Replay a sealed production model and account for every original GLRT winner.

Position, calibration, identities and production memberships are never refit.
Candidate screens are diagnostic compatibility tests, not accepted identities.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import time
import importlib.util

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

helper_path=Path(__file__).resolve().parents[1]/"src/leo/analysis/research/graph_position_membership.py"
helper_spec=importlib.util.spec_from_file_location("diagnostic_membership",helper_path)
helpers=importlib.util.module_from_spec(helper_spec)
helper_spec.loader.exec_module(helpers)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    def encode(x):
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        raise TypeError(type(x).__name__)
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, allow_nan=False, default=encode)
        f.write("\n")


def table(path, rows):
    if not rows: return
    with Path(path).open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def saved_context(run, release):
    sys.path[:0] = [str(release/"src"), str(release/"tools")]
    import algo02_scan as algo
    from ds23_frequency_events import make_event_problem, attach_event_predictive
    from ds23_family_cavity import legacy_phase_reference
    from probe_ds23_frequency_events import cached
    root = run/"inference"; case = "SCAN"
    terminal = read(run/"terminal.json")
    if terminal["state"] != "complete": raise ValueError("A qualified terminal is required")
    record = read(root/"family_cavity/position/SCAN.json")
    selected = record["selected"] if record["accepted"] else None
    algo.bind_run_directory(root)
    scan = algo.load_scan(root, case)
    node = selected["node"] if selected else record["baseline_node"]
    entries = selected["entries"] if selected else record["baseline_entries"]
    means = np.asarray(selected["means"] if selected else record["baseline_means"])
    keep, powers = np.asarray(record["original_mask"], bool), np.asarray(record["powers"])
    def build(arm, reference):
        p = make_event_problem(scan,node,keep,arm,np.asarray(reference),powers,means,record["model"],[])
        attach_event_predictive(p,entries,powers)
        return p
    problems, replay = {}, {}
    for arm in ("c0", "fitted_c"):
        saved = record["policy_arms"][arm];x = np.asarray(saved["endpoint_east_north_km"])
        p = build(arm, saved["phase_reference"])
        delta = p.calculate(x)["negative_twice_elbo"] - saved["negative_twice_elbo"]
        if abs(delta) > 1e-5:
            def posterior(reference, parameters):
                probe = build(arm,reference)
                return probe.state(parameters)["phases"][probe.labels]
            reference = legacy_phase_reference(saved["history"],np.zeros(len(means)),posterior)
            p = build(arm,reference)
            delta = p.calculate(x)["negative_twice_elbo"]-saved["negative_twice_elbo"]
        if abs(delta) > 1e-5: raise ValueError(f"Saved objective did not replay: {arm} {delta}")
        problems[arm] = cached(p); replay[arm] = float(delta)
    return terminal, record, entries, scan, problems, replay


def memberships(p, x, entries):
    from audit_ds23_algo01_coverage import retained_metrics
    from evaluate_ds23_phase_refreshed import extend_associations
    metrics = retained_metrics(p,x)
    curved = {oid for i,sl in zip(p.members,p.slices,strict=True)
              for oid,use in zip(p.scan.tracks[i]["observation_ids"],p.keep[sl],strict=True) if use}
    predictive = {oid for e in entries for oid in e["observation_ids"]}
    extension = extend_associations(p,x,metrics)
    lookup = {t["key"]:t for t in p.scan.tracks}
    accepted = set(curved)|predictive
    owners = {}
    for row in extension["tracks"]:
        if not row["compatible"]: continue
        ids = row.get("observation_ids",lookup[row["component"]]["observation_ids"])
        if set(ids)&predictive: continue
        accepted.update(ids)
        for oid in ids: owners[oid] = row["norad"]
    for e in entries:
        for oid in e["observation_ids"]: owners[oid] = e["norad"]
    return curved,predictive,accepted,owners


def screen(p, x, track, indices, full_catalogue=False):
    from leo.analysis.research.retained_track_likelihood import profile, whitening
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
    from prototype_dsx01_continuous_position import latlon
    state = p.state(x); times = np.asarray(track["times"])[indices]; q = track["rf_hz"]/11.5e9
    raw = np.asarray(track["values"]) - p.scan.hardware(track,state["beta"])
    i = next(i for i,t in enumerate(p.scan.tracks) if t["key"] == track["key"])
    raw -= q * p.scan.rx_basis[i] @ state["smooth"][track["receiver"]-1]
    y = raw[indices]; inv,volume = whitening(times)
    active = sorted({r["candidate_index"] for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()})
    guesses = []
    if full_catalogue:
        subset = np.unique(np.linspace(0,len(times)-1,min(12,len(times))).astype(int))
        candidates=[]
        for phase in np.arange(-15.,15.001,1.):
            f,e = phase_frequency_grid(p.scan.sky,times[subset],*latlon(x),phase_seconds=phase)
            terms = profile(y[subset],q*f,*whitening(times[subset]))
            score = np.where(e.min(axis=1)>=0,terms["cost"],np.inf)
            for j in np.argsort(score)[:12]:
                if np.isfinite(score[j]): candidates.append((float(score[j]),int(j),float(phase)))
        candidates.sort();seen=set()
        for cost,j,phase in candidates:
            if j in seen: continue
            seen.add(j)
            for phi in np.linspace(max(-15,phase-1),min(15,phase+1),21): guesses.append((j,float(phi)))
            if len(seen)>=12: break
    else:
        guesses = [(j,float(state["phases"][j])) for j in active if abs(state["phases"][j])<=15]
    if not guesses:return dict(status="no_eligible_candidate")
    prediction=[];elevation=[]
    calc=p.calculate(x);begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
    for j,phase in guesses:
        bank={k:p.scan.sky[k][[j]] for k in ("position_km","velocity_km_s")};bank["time_s"]=p.scan.sky["time_s"]
        f,e=paired_phase_frequency(bank,times,np.zeros(len(times),int),np.array([phase]),*latlon(x))
        if not full_catalogue and j in p.supported:
            local=p.labels.index(j);slot=p.supported.index(j)
            modes={k:p.mode_bank[k][3*local:3*local+3] for k in ("position_km","velocity_km_s")};modes["time_s"]=p.mode_bank["time_s"]
            d=paired_frequency_modes(bank,modes,times,np.zeros(len(times),int),np.array([phase]),*latlon(x))
            f+=d@calc["coefficient"][begin+3*slot:begin+3*slot+3]
        prediction.append(q*f);elevation.append(e)
    terms=profile(y,np.asarray(prediction),inv,volume);noise=batch_noise_screen(terms["innovations"],times)
    visible=np.min(elevation,axis=1)>=0
    rms_ok=terms["rms"]<=450;bias_ok=abs(terms["bias"])<=3000
    passed=visible&rms_ok&bias_ok&noise["noise_screen_pass"]
    ranking=np.where(passed,terms["cost"],np.inf)
    # When none pass, choose the least-cost visible candidate to explain its gates.
    best=int(np.argmin(ranking)) if passed.any() else int(np.argmin(np.where(visible,terms["cost"],np.inf)))
    if not visible.any():best=int(np.argmin(terms["cost"]))
    j,phase=guesses[best]
    fails=[]
    if not rms_ok[best]:fails.append("RMS")
    if not bias_ok[best]:fails.append("offset")
    if not visible[best]:fails.append("visibility")
    if not noise["noise_screen_pass"][best]:fails.append("residual_structure")
    return dict(status="screened",norad=int(p.scan.norads[j]),phase_s=phase,rms_hz=float(terms["rms"][best]),
        offset_hz=float(terms["bias"][best]),minimum_elevation_deg=float(np.min(elevation[best])),
        passes_all=bool(passed[best]),passing_hypotheses=int(passed.sum()),failed_gates=fails,
        passing_satellites=sorted({int(p.scan.norads[guesses[k][0]]) for k in np.flatnonzero(passed)}),
        noise={k:float(v[best]) for k,v in noise.items()},alias=int(terms["alias"][best]),
        times_s=times,corrected_observation_hz=y,prediction_hz=np.asarray(prediction)[best],
        residual_hz=terms["residual"][best],diagnostic_only=True,
        physical_modes_included=not full_catalogue,independent_per_track_phase_search=full_catalogue)


def figures(out, observations, tracks, roles, diagnostics, title):
    native_polynomial=helpers.native_polynomial
    raw={o["observation_id"]:o for o in observations};colors=plt.colormaps["tab20"]
    for rx in (1,2):
        fig,axes=plt.subplots(4,2,figsize=(16,13),sharex=True,layout="constrained")
        for ch,ax in enumerate(axes.flat,1):
            lane=[o for o in observations if o["receiver"]==rx and o["channel"]==ch]
            for kind,color,marker,size,label in [("associated",".78",".",10,"Satellite associated"),
                ("unassociated_graph","crimson","o",17,"Unassociated, in graph"),
                ("unassociated_outside_graph","darkorange","x",24,"Unassociated, no graph track")]:
                selected=[o for o in lane if (not roles[o["observation_id"]].startswith("unassociated"))] if kind=="associated" else [o for o in lane if roles[o["observation_id"]]==kind]
                ax.scatter([o["time_s"] for o in selected],[o["measured_cfo_hz"]/1000 for o in selected],c=color,marker=marker,s=size,alpha=.8,label=label)
            for k,t in enumerate(tracks):
                if (t["receiver"],t["channel"])!=(rx,ch):continue
                remaining=np.array([roles[o]=="unassociated_graph" for o in t["observation_ids"]])
                if not remaining.any():continue
                for yy in native_polynomial(t,raw):
                    yy=yy.copy();yy[~remaining]=np.nan;ax.plot(t["times"],yy/1000,lw=1.4,color=colors(k%20))
                if remaining.sum()>=8:
                    pick=np.flatnonzero(remaining)[len(np.flatnonzero(remaining))//2]
                    ax.annotate(t["key"].split("-CH")[1].split("-RF")[0],(t["times"][pick],raw[t["observation_ids"][pick]]["measured_cfo_hz"]/1000),fontsize=7,xytext=(3,5),textcoords="offset points")
            n=sum(roles[o["observation_id"]].startswith("unassociated") for o in lane)
            ax.set(title=f"RX{rx} CH{ch}: {n}/{len(lane)} unassociated",ylabel="Native GLRT CFO (kHz)",xlabel="Device time (s)")
            ax.grid(alpha=.2)
        handles,labels=axes.flat[0].get_legend_handles_labels();fig.legend(handles,labels,loc="outside lower center",ncol=3)
        fig.suptitle(title+f" · RX{rx}\nColored lines = remaining portions of graph polynomials; gray points are ASSOCIATED",fontsize=13)
        fig.savefig(out/f"unassociated_RX{rx}.png",dpi=160);fig.savefig(out/f"unassociated_RX{rx}.pdf");plt.close(fig)
    counts=[]
    for rx in (1,2):
        for ch in range(1,9):
            lane=[o for o in observations if (o["receiver"],o["channel"])==(rx,ch)]
            counts.append(dict(receiver=rx,channel=ch,total=len(lane),**{role:sum(roles[o["observation_id"]]==role for o in lane) for role in sorted(set(roles.values()))}))
    table(out/"per_channel.csv",counts)
    fig,axes=plt.subplots(1,2,figsize=(16,5),layout="constrained")
    palette={"curved_likelihood":"tab:blue","predictive_likelihood":"tab:cyan","postfit_only":"tab:green","unassociated_graph":"crimson","unassociated_outside_graph":"darkorange"}
    for rx,ax in enumerate(axes,1):
        selected=[r for r in counts if r["receiver"]==rx];bottom=np.zeros(8)
        for role,color in palette.items():
            values=[r.get(role,0) for r in selected];ax.bar(range(1,9),values,bottom=bottom,color=color,label=role.replace("_"," "));bottom+=values
        ax.set(title=f"RX{rx}",xlabel="Channel",ylabel="Original winning GLRT points",xticks=range(1,9))
    fig.legend(*axes[0].get_legend_handles_labels(),loc="outside upper center",ncol=3);fig.savefig(out/"point_accounting.png",dpi=170);plt.close(fig)
    candidates=sorted(diagnostics,key=lambda r:(-r["unassociated_duration_s"],-r["unassociated_points"]))[:6]
    fig,axes=plt.subplots(len(candidates),2,figsize=(16,3.0*len(candidates)),squeeze=False,layout="constrained")
    for row,axesrow in zip(candidates,axes,strict=True):
        t=next(t for t in tracks if t["key"]==row["component"]);ax,resax=axesrow
        lane=[o for o in observations if (o["receiver"],o["channel"])==(t["receiver"],t["channel"]) and row["start_s"]-5<=o["time_s"]<=row["end_s"]+5]
        focus=set(t["observation_ids"])
        ax.scatter([o["time_s"] for o in lane],[o["measured_cfo_hz"]/1000 for o in lane],s=15,c=".78")
        other=[o for o in lane if roles[o["observation_id"]].startswith("unassociated") and o["observation_id"] not in focus]
        ax.scatter([o["time_s"] for o in other],[o["measured_cfo_hz"]/1000 for o in other],s=20,c="darkorange",marker="x")
        z=[raw[oid] for oid in t["observation_ids"] if roles[oid]=="unassociated_graph"]
        ax.scatter([o["time_s"] for o in z],[o["measured_cfo_hz"]/1000 for o in z],s=20,c="crimson")
        for yy in native_polynomial(t,raw):ax.plot(t["times"],yy/1000,color="tab:blue",lw=1)
        ax.set(title=f"RX{t['receiver']} CH{t['channel']} {t['key'].split('-T')[1].split('-RF')[0]} · {row['unassociated_points']} remaining points",ylabel="Native CFO (kHz)",xlabel="Time (s)");ax.grid(alpha=.2)
        for label,key,color in [("Frozen active family","active","tab:blue"),("Causal catalogue diagnostic","catalogue","tab:orange")]:
            d=row.get(key,{})
            if d.get("status")!="screened":continue
            resax.plot(d["times_s"],d["residual_hz"],".-",color=color,label=f"{label}: {d['norad']}, RMS {d['rms_hz']:.0f} Hz")
        resax.axhline(0,c=".5",lw=.8);resax.set(title="Residual after permitted alias + constant profile",ylabel="CFO residual (Hz)",xlabel="Time (s)");resax.grid(alpha=.2);resax.legend(fontsize=8)
    fig.savefig(out/"longest_unassociated_details.png",dpi=155);fig.savefig(out/"longest_unassociated_details.pdf");plt.close(fig)


def main(args):
    began=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False)
    terminal,record,entries,scan,problems,replay=saved_context(args.run,args.release)
    point_roles=helpers.point_roles
    observations=read(args.run/"inference/SCAN/observations.json")
    snapshots={};roles_by_arm={}
    for arm,p in problems.items():
        x=np.asarray(record["policy_arms"][arm]["endpoint_east_north_km"])
        curved,predictive,accepted,owners=memberships(p,x,entries)
        roles=point_roles(observations,scan.tracks,curved,predictive,accepted);roles_by_arm[arm]=roles
        snapshots[arm]=dict(total=len(observations),curved=len(curved),predictive=len(predictive),postfit_only=len(accepted-curved-predictive),
            associated=len(accepted),associated_percent=100*len(accepted)/len(observations),unassociated=len(observations)-len(accepted),
            role_counts={role:list(roles.values()).count(role) for role in sorted(set(roles.values()))},owners=owners)
    roles=roles_by_arm["fitted_c"];p=problems["fitted_c"];x=np.asarray(record["policy_arms"]["fitted_c"]["endpoint_east_north_km"])
    diagnostic=[]
    for track_index,track in enumerate(scan.tracks):
        ix=np.array([i for i,oid in enumerate(track["observation_ids"]) if roles[oid]=="unassociated_graph"],int)
        if not len(ix):continue
        times=np.asarray(track["times"])[ix]
        row=dict(component=track["key"],receiver=track["receiver"],channel=track["channel"],total_points=len(track["times"]),
            unassociated_points=len(ix),start_s=float(times.min()),end_s=float(times.max()),unassociated_duration_s=float(np.ptp(times)),
            graph_quality=track["quality_status"],active_curvature=track_index in scan.curved,
            partially_retained=len(ix)<len(track["times"]))
        if len(ix)>=4 and np.ptp(times)>0:
            row["active"]=screen(p,x,track,ix)
            row["catalogue"]=screen(p,x,track,ix,True)
        else:row.update(active=dict(status="insufficient_remaining_samples"),catalogue=dict(status="insufficient_remaining_samples"))
        diagnostic.append(row)
        print(track["key"],len(ix),row["active"].get("failed_gates"),row["catalogue"].get("norad"),flush=True)
    pointrows=[dict(o,role_fitted_c=roles[o["observation_id"]],role_c0=roles_by_arm["c0"][o["observation_id"]]) for o in observations]
    table(out/"all_GLRT_points.csv",pointrows)
    write(out/"track_diagnostics.json",diagnostic)
    table(out/"unassociated_tracks.csv",[{k:v for k,v in row.items() if k not in ("active","catalogue")} | {prefix+"_"+k: d.get(k) if k!="failed_gates" else ",".join(d.get(k,[])) for prefix in ("active","catalogue") for d in [row[prefix]] for k in ("norad","rms_hz","phase_s","offset_hz","passes_all","failed_gates")} for row in diagnostic])
    figures(out,observations,scan.tracks,roles,diagnostic,args.title)
    summary=dict(recording=args.title,model_version=terminal["model_version"],position=terminal["position"],arms=snapshots,objective_replay_differences=replay,
        no_position_or_calibration_refits=True,no_diagnostic_match_adopted=True,causal_catalogue_candidates=len(scan.norads),
        independent_catalogue_phase_diagnostic_grid="-15..15s, 1s coarse; 12 unique candidates, ±1s/21-point refinement; no new physical-mode fit",
        source_release=str(args.release),fresh_run=str(args.run),seconds=time.monotonic()-began)
    write(out/"summary.json",summary)
    print(json.dumps({a:{k:v for k,v in d.items() if k!="owners"} for a,d in snapshots.items()}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--release",type=Path,required=True);parser.add_argument("--title",required=True)
    main(parser.parse_args())
