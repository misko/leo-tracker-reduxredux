"""Compare later archived TLEs with sealed fits; never replace original evidence.

Run with the pinned deployed Python for identical propagation and fitting code.
The final displayed memberships/aliases stay fixed; the original full finite-set
likelihood, priors, RF term, and reference position are used for nuisance refits.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import inspect
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT.parent / "2026_10_02_multiscan_localization"),
               str(ROOT.parent / "2026_10_02_localization_benchmark")]
from plot_all_glrt_doppler_overlay import SESSIONS, load_archived_session, file_digest, serializable
from plot_final_glrt_orbit_tracks import final_tracks, read_membership_rows
from residual_trend_audit import COLORS, CARRIER, stats, polynomial, regress
from plot_residual_audit_summary import SELECTED

OUTPUT = ROOT / "later-tle-comparison"


def element_records(payload):
    """Retain exact element lines; decode numeric and Alpha-5 catalogue IDs."""
    from sgp4.alpha5 import from_alpha5
    lines = payload.splitlines()
    records = {}
    for i, line in enumerate(lines):
        if not line.startswith("1 "):
            continue
        second = lines[i + 1]
        if not second.startswith("2 ") or second[2:7] != line[2:7]:
            raise ValueError("invalid paired TLE")
        number = from_alpha5(line[2:7])
        yy = int(line[18:20])
        epoch = datetime(1900 + yy if yy >= 57 else 2000 + yy, 1, 1, tzinfo=UTC)
        epoch += timedelta(days=float(line[20:32]) - 1)
        records[number] = {"epoch_utc_ns": round(epoch.timestamp() * 1e9),
                           "epoch_utc": epoch.isoformat(), "line1": line, "line2": second}
    return records


def epoch_status(epoch_ns, origin_ns, end_s=300.0):
    if epoch_ns > origin_ns + round(end_s * 1e9):
        return "after scan: backward propagation"
    if epoch_ns < origin_ns:
        return "before scan: forward propagation"
    return "epoch within scan"


def fixed_alias_residual(old_residual, old_prediction, new_prediction, rf):
    """No re-gating, peak changes, or nearest-alias reassignment in comparisons."""
    return old_residual + (old_prediction - new_prediction) * CARRIER / rf[:, None]


def save_json(path, value):
    with path.open("x") as stream:
        json.dump(serializable(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


def predict(data, parameters, satellites, rf_coefficient):
    from compact_satellite_selection import _predict_matrix
    from rf_calibration_diagnostic import rf_features
    prediction, _ = _predict_matrix(data, np.asarray(parameters), satellites)
    _, features = rf_features(data.rf, data.receiver, False)
    return prediction + (features @ np.asarray(rf_coefficient))[:, None]


def refit(data, profile, sealed, initial_vector=None):
    from position_profile_grid import run_profile
    vector = np.asarray(sealed["vector"] if initial_vector is None else initial_vector)
    attempts = []
    for _ in range(10):
        result = run_profile(data, sealed["parameters"], profile["satellite_indices"],
                             sealed["rf_coefficient_hz_per_ghz"],
                             np.asarray(sealed["parameters"])[:2],
                             probability_override=profile["detection_probability"],
                             start_vector=vector, budget_s=8.0)
        attempts.append(result)
        vector = result["vector"]
        if result["success"]:
            break
    best = min(attempts, key=lambda r: r["objective"])
    return best, [{k: r[k] for k in ("objective", "status", "success", "elapsed_s",
                                    "projected_nuisance_gradient_inf_norm")}
                  for r in attempts]


def plots(tracks):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    by_key = {(r["scan"], r["catalog_number"], r["receiver"]): r for r in tracks}
    handles = [Line2D([], [], color=COLORS[i], marker="o", linestyle="", label=f"CH{i+1}")
               for i in range(4)]
    handles += [Line2D([], [], color="#222222", linestyle="--", label="Fitted line"),
                Line2D([], [], color="#CC3311", label="Fitted quadratic")]

    def panel(ax, r, variant, limits):
        t, ch = np.asarray(r["time_s"]), np.asarray(r["channel"])
        y = np.asarray(r[variant + "_residual_hz"])
        for c in np.unique(ch):
            mask = ch == c
            ax.scatter(t[mask], y[mask], s=15, alpha=.85, color=COLORS[c-1], zorder=4)
        key = (r["scan"], r["catalog_number"], r["receiver"])
        if key == ("A", 58622, 1):
            for c in np.unique(ch):
                m = ch == c
                ax.plot([t[m].min(), t[m].max()], [y[m].mean()] * 2,
                        color=COLORS[c-1], linewidth=2)
        else:
            for order, color, style in ((1, "#222222", "--"), (2, "#CC3311", "-")):
                _, fit, _ = regress(polynomial(t, order), y)
                ax.plot(t, fit, color=color, linestyle=style, linewidth=1.8, zorder=5)
        ax.axhline(0, color=".6", linewidth=.7)
        for v in (-150, 150):
            ax.axhline(v, color=".6", linestyle=":", linewidth=.7)
        ax.set_ylim(*limits)
        ax.set_xlim(t.min()-2, t.max()+2)
        ax.grid(alpha=.15)
        s = r[variant + "_stats"]
        ax.set_title(f"Scan {r['scan']} · {r['catalog_number']} / RX{r['receiver']} · "
                     f"RMS {s['rms_hz']:.1f} Hz\n"
                     f"slope {s['slope_hz_s']:+.2f} Hz/s; q {s['quadratic_hz_s2']:+.4f} Hz/s²",
                     fontsize=10)
        ax.set_xlabel("Receive time (s)")
        ax.set_ylabel("GLRT − fitted orbit (Hz)")

    def finish(fig, name, title, footer):
        fig.suptitle(title, y=.992, fontsize=15)
        fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5,.975), ncol=6)
        fig.text(.5,.012,footer,ha="center",fontsize=9)
        fig.tight_layout(rect=(.01,.05,.99,.946),h_pad=2.0)
        for ext in ("png", "svg"):
            fig.savefig(OUTPUT/f"{name}.{ext}",dpi=170)
        plt.close(fig)

    # Matched scales for before and after, never hide points outside old gate.
    selected = [by_key[key] for key in SELECTED]
    limits = {}
    for key, r in zip(SELECTED, selected, strict=True):
        values = np.r_[r["old_residual_hz"], r["later_residual_hz"]]
        bound = max(180., np.ceil(np.max(np.abs(values))/25)*25 + 10)
        limits[key] = (-bound, bound)
    for variant, label in (("old", "Original pinned TLEs"), ("later", "Later archived TLEs · same-model refit")):
        fig, axes = plt.subplots(4,2,figsize=(15,14.5))
        for ax, key, r in zip(axes.flat, SELECTED, selected, strict=True):
            panel(ax,r,variant,limits[key])
            if variant == "later":
                ax.text(.01,.025,r["tle_status"],transform=ax.transAxes,fontsize=8,
                        bbox={"facecolor":"white","alpha":.8,"edgecolor":"none"})
        finish(fig,f"{variant}-key-findings",f"DS13 residual comparison · {label}",
               "Identical displayed GLRT rows and aliases; same per-panel scales; normalized to 11.085 GHz.\n"
               "Latest snapshot collected after both scans; only epochs after a scan constitute backward propagation.\n"
               "Line/quadratic overlays describe residuals, not additional orbit-fit parameters. No new residual gate.")
    fig, axes = plt.subplots(8,2,figsize=(15,24))
    for row,key in enumerate(SELECTED):
        for col,variant in enumerate(("old","later")):
            panel(axes[row,col],by_key[key],variant,limits[key])
            axes[row,col].text(.01,.025,"Original" if col==0 else by_key[key]["tle_status"],
                              transform=axes[row,col].transAxes,fontsize=8)
    finish(fig,"before-after", "Original pinned TLEs (left) versus later TLEs refitted (right)",
           "Same GLRT rows, aliases, nuisance model, reference site and matched scales.\n"
           "Later collection is not necessarily a later-than-scan element epoch. No polynomial subtraction.")


def run():
    from all_visible_bank import load_expanded_scan
    from finite_set_fit import snapshot_files
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    started = time.monotonic()
    OUTPUT.mkdir(exist_ok=True)
    if any(OUTPUT.iterdir()):
        raise FileExistsError(f"refusing to overwrite existing evidence: {OUTPUT}")
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    latest = max(archive.list_snapshots("space-track"), key=lambda s:s.collected_utc_ns)
    payload = archive.read(latest)
    records = element_records(payload)
    catalogue = parse_element_sets(payload)
    lookup = {int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    membership = ROOT/"orbit-backfill-prototype/group-summed-orbit-backfill-memberships.csv"
    membership_rows = read_membership_rows(membership)
    inputs = [Path(__file__),membership,latest.path,Path(inspect.getfile(propagate_candidate_states)),
              ROOT/"position_profile_grid.py",ROOT/"rf_calibration_diagnostic.py",
              ROOT/"timing_model.py",ROOT/"truth_start_diagnostic.py"]
    tracks, scans = [], []
    for label,session in zip(("A","B"),SESSIONS,strict=True):
        print(f"{label}: loading verified sealed bank",flush=True)
        data = load_expanded_scan(session)
        arrays,_,_,_ = load_archived_session(session)
        profile_path = ROOT/"pruned-position-profile-grid"/f"{session}.json"
        profile = json.loads(profile_path.read_text())
        sealed = next(p["best"] for p in profile["positions"] if p["label"]=="truth")
        satellites = np.asarray(profile["satellite_indices"],int)
        origin = data.bank_receipt["ephemeris"]["origin_utc_ns"]
        if latest.collected_utc_ns <= origin + 300_000_000_000:
            raise ValueError("selected snapshot was not collected after scan")
        numbers = data.numbers[satellites]
        indices = [lookup[int(n)] for n in numbers]
        position,velocity,valid = propagate_candidate_states(catalogue,indices,origin,data.nodes,np.array([0.]))
        if list(valid) != indices:
            raise ValueError("later TLE propagation missing selected satellite")
        newer = copy.copy(data)
        newer.position = data.position.copy()
        newer.velocity = data.velocity.copy()
        newer.position[satellites] = position[:,0]
        newer.velocity[satellites] = velocity[:,0]
        old_prediction = predict(data,sealed["parameters"],satellites,sealed["rf_coefficient_hz_per_ghz"])
        frozen_prediction = predict(newer,sealed["parameters"],satellites,sealed["rf_coefficient_hz_per_ghz"])
        # Verify the sealed residual through its original wrapped residual definition.
        from finite_set_likelihood import circular_residual, prepare_finite_set_likelihood
        alias_hz = prepare_finite_set_likelihood(data.measured,data.group).alias_hz
        replay = circular_residual(data.measured[:,None],old_prediction,alias_hz) * CARRIER/data.rf[:,None]
        error = float(np.max(np.abs(replay-arrays["residual_hz"])))
        if error > 1e-6:
            raise ValueError(f"sealed residual replay failed: {error}")
        print(f"{label}: baseline replay {error:.3g} Hz; refitting original control",flush=True)
        control,control_attempts = refit(data,profile,sealed)
        if abs(control["objective"]-sealed["objective"]) > .001:
            raise ValueError("original fit control did not reproduce objective")
        print(f"{label}: refitting later TLE timing/RX/RF nuisance",flush=True)
        fitted,attempts = refit(newer,profile,sealed)
        print(f"{label}: {fitted['status']}, gradient {fitted['projected_nuisance_gradient_inf_norm']:.6g}",flush=True)
        new_prediction = predict(newer,fitted["parameters"],satellites,fitted["rf_coefficient_hz_per_ghz"])
        after = fixed_alias_residual(arrays["residual_hz"],old_prediction,new_prediction,data.rf)
        frozen = fixed_alias_residual(arrays["residual_hz"],old_prediction,frozen_prediction,data.rf)
        old_payload = archive.read(next(s for s in archive.list_snapshots(data.bank_receipt["tle"]["provider"])
                                       if s.digest==data.bank_receipt["tle"]["digest"]
                                       and s.collected_utc_ns==data.bank_receipt["tle"]["collected_utc_ns"]))
        old_records = element_records(old_payload)
        tle_rows=[]
        for n in numbers:
            old,new = old_records[int(n)],records[int(n)]
            tle_rows.append({"catalog_number":int(n),"original":old,"later":new,
                             "epoch_relative_to_scan_hours":(new["epoch_utc_ns"]-origin)/3.6e12,
                             "status":epoch_status(new["epoch_utc_ns"],origin),
                             "element_changed":(old["line1"],old["line2"])!=(new["line1"],new["line2"])})
        for track in final_tracks(membership_rows,arrays,label):
            rows,col = track["rows"],track["column"]
            n = track["catalog_number"]
            t = data.times[rows]
            entry = {"scan":label,"session":session,"catalog_number":n,"receiver":track["receiver"],
                     "rows":rows,"time_s":t,"channel":data.channel[rows],
                     "tle_status":epoch_status(records[n]["epoch_utc_ns"],origin)}
            for name,values in (("old",arrays["residual_hz"]),("frozen",frozen),("later",after)):
                entry[name+"_residual_hz"]=values[rows,col]
                entry[name+"_stats"]=stats(t,values[rows,col])
            tracks.append(entry)
        scans.append({"scan":label,"session":session,"origin_utc_ns":origin,
                      "original_tle_snapshot":data.bank_receipt["tle"],"elements":tle_rows,
                      "sealed_replay_max_error_hz":error,"sealed_objective":sealed["objective"],
                      "original_refit_control":control,"original_control_attempts":control_attempts,
                      "later_fit":fitted,"later_attempts":attempts})
        inputs += [profile_path,ROOT/"all-visible-bank"/session/"receipt.json",
                   ROOT/"all-visible-bank"/session/"expanded.npz",
                   ROOT/"tle-doppler-overlay"/f"{session}-plot-data.npz"]
        save_json(OUTPUT/f"scan-{label.lower()}-fit.json",scans[-1])
    plots(tracks)
    fields=["scan","catalog_number","receiver","tle_status","count","old_rms_hz","later_rms_hz",
            "old_slope_hz_s","later_slope_hz_s","old_q_hz_s2","later_q_hz_s2"]
    with (OUTPUT/"comparison.csv").open("x",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for t in tracks:
            old,new=t["old_stats"],t["later_stats"]
            writer.writerow({**{k:t[k] for k in fields[:4]},"count":old["count"],
                "old_rms_hz":old["rms_hz"],"later_rms_hz":new["rms_hz"],
                "old_slope_hz_s":old["slope_hz_s"],"later_slope_hz_s":new["slope_hz_s"],
                "old_q_hz_s2":old["quadratic_hz_s2"],"later_q_hz_s2":new["quadratic_hz_s2"]})
    save_json(OUTPUT/"receipt.json",{
        "schema":"ds13-later-tle-comparison/v1","elapsed_s":time.monotonic()-started,
        "latest_snapshot":{"provider":latest.provider,"collected_utc_ns":latest.collected_utc_ns,
                           "digest":latest.digest,"path":str(latest.path)},
        "scope":"Retrospective diagnostic, not causal/real-time orbit availability. Same original full "
                "finite-set likelihood, candidate set, priors, sigma, detection probability, fixed position, "
                "RX offset+slope and common RF coefficient; timing nuisance refitted. Final displayed rows "
                "and aliases are frozen, no new gate. Line/quadratic overlays are diagnostic only. "
                "Epochs before scan do not constitute backward propagation. No new held-out validation.",
        "all_fits_converged":all(s["later_fit"]["success"] for s in scans),
        "scans":scans,"tracks":tracks,"source_hashes":snapshot_files(inputs),
        "outputs":{str(p):file_digest(p) for p in OUTPUT.iterdir() if p.is_file()}})
    # Root is needed only for the protected archive/deployed runtime. Return new
    # report artifacts to the workspace owner; never touch original evidence.
    owner=ROOT.stat()
    if os.geteuid()==0:
        for p in [*OUTPUT.iterdir(),OUTPUT]:os.chown(p,owner.st_uid,owner.st_gid)
    print(json.dumps({"output":str(OUTPUT),"converged":all(s["later_fit"]["success"] for s in scans)}),flush=True)


if __name__=="__main__":
    run()
