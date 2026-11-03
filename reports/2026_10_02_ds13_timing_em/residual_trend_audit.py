"""Bounded, frozen-membership residual audit; does not update associations or fits."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT.parent / "2026_10_02_multiscan_localization"))
from prediction_jacobian import paired_prediction_jacobian
from plot_all_glrt_doppler_overlay import SESSIONS, file_digest, load_archived_session, serializable
from plot_final_glrt_orbit_tracks import final_tracks, read_membership_rows
from plot_62953_stage_comparison import map_raw_seed_rows_to_family_rows

CARRIER = 11.085e9
OUTPUT = ROOT / "residual-trend-audit"
COLORS = ("#0072B2", "#E69F00", "#009E73", "#CC79A7")


def rms(values):
    return float(np.sqrt(np.mean(np.asarray(values, float) ** 2)))


def regress(design, values, train=None, robust=False):
    design, values = np.asarray(design, float), np.asarray(values, float)
    train = np.ones(len(values), bool) if train is None else np.asarray(train, bool)
    a, y = design[train], values[train]
    weights = np.ones(len(y))
    for _ in range(30 if robust else 1):
        coef, _, rank, _ = np.linalg.lstsq(a * np.sqrt(weights[:, None]), y * np.sqrt(weights), rcond=None)
        error = y - a @ coef
        scale = max(1.0, float(1.4826 * np.median(np.abs(error - np.median(error)))))
        weights = np.minimum(1.0, 1.345 * scale / np.maximum(np.abs(error), 1e-12))
    return coef, design @ coef, int(rank)


def polynomial(times, order=1):
    times = np.asarray(times, float)
    return np.vander((times - np.mean(times)) / 30.0, order + 1, increasing=True)


def stats(times, values):
    if len(values) < 4 or np.ptp(times) < 1:
        return {"count": len(values), "available": False}
    line, pl, _ = regress(polynomial(times, 1), values)
    quad, pq, _ = regress(polynomial(times, 2), values)
    robust, _, _ = regress(polynomial(times, 1), values, robust=True)
    return {
        "count": len(values), "available": True, "start_s": float(min(times)),
        "end_s": float(max(times)), "rms_hz": rms(values), "mean_hz": float(np.mean(values)),
        "centered_rms_hz": rms(values - np.mean(values)), "slope_hz_s": float(line[1] / 30),
        "huber_slope_hz_s": float(robust[1] / 30), "quadratic_hz_s2": float(quad[2] / 900),
        "line_rms_hz": rms(values - pl), "quadratic_rms_hz": rms(values - pq),
        "outside_150_count": int(np.sum(np.abs(values) > 150)),
    }


def time_folds(times, count=5, guard_s=1.0):
    """Contiguous equal-duration validation blocks with purged training neighbors."""
    times = np.asarray(times, float)
    edges = np.linspace(times.min(), times.max(), count + 1)
    labels = np.minimum(np.searchsorted(edges, times, side="right") - 1, count - 1)
    result = []
    for k in range(count):
        test = labels == k
        if not np.any(test):
            continue
        lo, hi = times[test].min(), times[test].max()
        train = (times < lo - guard_s) | (times > hi + guard_s)
        if np.sum(train) >= 10:
            result.append((train, test))
    return result


def cross_validate(design, values, folds):
    errors, fold_results, predictions = [], [], np.full(len(values), np.nan)
    for train, test in folds:
        _, prediction, rank = regress(design, values, train)
        if rank != design.shape[1]:
            return {"available": False, "reason": "rank-deficient training design"}
        e = values[test] - prediction[test]
        errors.extend(e)
        predictions[test] = prediction[test]
        fold_results.append(rms(e))
    if len(errors) != len(values):
        return {"available": False, "reason": "incomplete held-out coverage"}
    return {"available": True, "rms_hz": rms(errors), "fold_rms_hz": fold_results}


def bootstrap_coefficients(times, values, design, seed, replicates=600):
    """Five-second time-cluster resampling; descriptive stability, not an IID CI."""
    clusters = np.floor((times - min(times)) / 5.0).astype(int)
    levels = np.unique(clusters)
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(replicates):
        sample = np.concatenate([np.flatnonzero(clusters == c) for c in rng.choice(levels, len(levels))])
        a = design[sample]
        if np.linalg.matrix_rank(a) == a.shape[1]:
            estimates.append(np.linalg.lstsq(a, values[sample], rcond=None)[0])
    if not estimates:
        return {"available": False}
    return {"available": True, "cluster_count": len(levels), "replicates": len(estimates),
            "percentiles_2_5_97_5": np.quantile(estimates, [.025, .975], axis=0)}


def profile_minimum(objective, bound=1.0):
    """Global grid screen, then refine every sampled minimum inside +/-bound seconds."""
    grid = np.linspace(-bound, bound, 81)
    costs = np.array([objective(v) for v in grid])
    best = (float(costs.min()), float(grid[np.argmin(costs)]))
    candidates = np.flatnonzero((costs[1:-1] <= costs[:-2]) & (costs[1:-1] <= costs[2:])) + 1
    for index in candidates:
        lo, hi = grid[index - 1], grid[index + 1]
        ratio = (5 ** .5 - 1) / 2
        c, d = hi - ratio * (hi - lo), lo + ratio * (hi - lo)
        fc, fd = objective(c), objective(d)
        for _ in range(35):
            if fc < fd:
                hi, d, fd = d, c, fc
                c = hi - ratio * (hi - lo)
                fc = objective(c)
            else:
                lo, c, fc = c, d, fd
                d = lo + ratio * (hi - lo)
                fd = objective(d)
        delta = float((lo + hi) / 2)
        best = min(best, (float(objective(delta)), delta))
    return best[1]


class ExactOrbit:
    def __init__(self, arrays, bank, column, rows):
        satellite = int(arrays["satellite_indices"][column])
        self.times = np.asarray(arrays["times_s"])[rows]
        self.parameters = np.r_[arrays["parameters"][:2], np.zeros(4), arrays["parameters"][6 + satellite]]
        self.data = SimpleNamespace(
            times=self.times, rf=np.full(len(rows), CARRIER), receiver=np.zeros(len(rows), int),
            reference_time_s=150.0, numbers=bank["numbers"][[satellite]], nodes=bank["nodes"],
            position=bank["position"][[satellite]], velocity=bank["velocity"][[satellite]],
        )
        if self.data.numbers[0] != arrays["catalog_numbers"][column]:
            raise ValueError("orbit-bank satellite mapping changed")
        self.rows = np.arange(len(rows))
        self.satellites = np.zeros(len(rows), int)
        self.cache = {}
        self.baseline = self.predict(0.0)

    def predict(self, delta):
        delta = float(delta)
        if delta not in self.cache:
            p = self.parameters.copy()
            p[6] += delta
            self.cache[delta] = paired_prediction_jacobian(self.data, p, self.rows, self.satellites)[0]
        return self.cache[delta]

    def change(self, delta):
        return self.predict(delta) - self.baseline


def timing_fit(orbit, values, bias_feature=None, train=None):
    train = np.ones(len(values), bool) if train is None else train

    def evaluate(delta, detail=False):
        remaining = values - orbit.change(delta)
        bias = (float(bias_feature[train] @ remaining[train] / (bias_feature[train] @ bias_feature[train]))
                if bias_feature is not None else 0.0)
        correction = orbit.change(delta) + (bias * bias_feature if bias_feature is not None else 0.0)
        return (correction, bias) if detail else float(np.mean((values[train] - correction[train]) ** 2))

    delta = profile_minimum(evaluate)
    prediction, bias = evaluate(delta, True)
    return {"extra_timing_s": delta, "total_timing_s": float(orbit.parameters[6] + delta),
            "bias_hz": bias, "boundary_hit": abs(delta) >= .9999,
            "rms_hz": rms(values[train] - prediction[train])}, prediction


def channel_design(times, channels, order=0):
    levels = np.unique(channels)
    return np.column_stack([channels == c for c in levels] +
                           [((times - times.mean()) / 30) ** k for k in range(1, order + 1)])


def ungated_groups(arrays, column, receiver, start, end, threshold=.9):
    """One target-MAP peak per group; no residual or initial-ownership gate."""
    mask = ((arrays["receiver"] == receiver) & (arrays["times_s"] >= start) & (arrays["times_s"] <= end))
    rows = np.flatnonzero(mask)
    selected = []
    for group in np.unique(arrays["group"][rows]):
        rr = rows[arrays["group"][rows] == group]
        if np.sum(arrays["posterior"][rr, column]) >= threshold:
            selected.append(int(rr[np.argmax(arrays["posterior"][rr, column])]))
    return np.array(sorted(selected, key=lambda r: arrays["times_s"][r]), dtype=int)


def audit_track(arrays, track, bank, original_rows, memberships, label):
    rows, column = track["rows"], track["column"]
    times = np.asarray(arrays["times_s"])[rows]
    values = np.asarray(arrays["residual_hz"])[rows, column]
    channels = np.asarray(arrays["channel"])[rows]
    rf = np.asarray(arrays["rf_hz"])[rows]
    folds = time_folds(times)
    designs = {"constant": polynomial(times, 0), "line": polynomial(times, 1),
               "quadratic": polynomial(times, 2), "channel_offsets": channel_design(times, channels),
               "channel_line": channel_design(times, channels, 1),
               "channel_quadratic": channel_design(times, channels, 2)}
    models, predictions = {}, {}
    for name, design in designs.items():
        coef, prediction, rank = regress(design, values)
        predictions[name] = prediction
        models[name] = {"coefficients": coef, "rank": rank, "rms_hz": rms(values - prediction),
                        "cv": cross_validate(design, values, folds)}
    boot = bootstrap_coefficients(times, values, designs["channel_quadratic"], track["catalog_number"] + track["receiver"])
    # Timing is evaluated against the identical archived physical predictor.
    orbit = ExactOrbit(arrays, bank, column, rows)
    parity = float(np.max(np.abs(orbit.baseline - arrays["modeled_doppler_hz"][rows, column])))
    if parity > 1e-7:
        raise ValueError(f"physical predictor parity failed: {parity}")
    for name, feature in (("timing", None), ("timing_bias", np.ones(len(rows))),
                           ("timing_native_bias", CARRIER / rf)):
        model, prediction = timing_fit(orbit, values, feature)
        predictions[name] = prediction
        errors, fold_records = [], []
        for train, test in folds:
            fitted, predicted = timing_fit(orbit, values, feature, train)
            errors.extend(values[test] - predicted[test])
            fold_records.append({**fitted, "test_rms_hz": rms(values[test] - predicted[test])})
        model["cv"] = {"available": len(errors) == len(values), "rms_hz": rms(errors), "folds": fold_records}
        model["remaining_slope_hz_s"] = stats(times, values - prediction)["slope_hz_s"]
        models[name] = model
    # Carrier/Doppler scale is a diagnostic of effective RF or velocity-scale mismatch.
    doppler = orbit.baseline
    scale_design = np.c_[np.ones(len(rows)), (doppler - doppler.mean()) / 1e5]
    coef, prediction, rank = regress(scale_design, values)
    models["doppler_scale_bias"] = {"fractional_scale": float(coef[1] / 1e5),
        "equivalent_carrier_error_mhz": float(CARRIER * coef[1] / 1e5 / 1e6),
        "rms_hz": rms(values - prediction), "cv": cross_validate(scale_design, values, folds)}
    derivative = (orbit.predict(.001) - orbit.predict(-.001)) / .002
    models["timing_bias"]["timing_bias_column_cosine"] = float(abs(np.mean(derivative)) / rms(derivative))

    subsets = {}
    for name, rr in (("seed_owned", rows[track["seed_owned"]]), ("unallocated", rows[~track["seed_owned"]]),
                      ("original_proposals", original_rows)):
        subsets[name] = stats(arrays["times_s"][rr], arrays["residual_hz"][rr, column])
    independent_lookup = {(int(r["group"]), int(r["catalog_number"]), int(r["receiver"])): int(r["independent_row"])
                          for r in memberships if r["scan_label"] == label}
    independent = np.array([independent_lookup[(int(arrays["group"][r]), track["catalog_number"], track["receiver"])] for r in rows])
    subsets["independent_peaks"] = stats(arrays["times_s"][independent], arrays["residual_hz"][independent, column])
    relaxed = ungated_groups(arrays, column, track["receiver"], times.min() - 10, times.max() + 10)
    subsets["expanded_window_no_residual_gate"] = stats(arrays["times_s"][relaxed], arrays["residual_hz"][relaxed, column])
    inside = relaxed[(arrays["times_s"][relaxed] >= times.min()) & (arrays["times_s"][relaxed] <= times.max())]
    subsets["same_window_no_residual_gate"] = stats(arrays["times_s"][inside], arrays["residual_hz"][inside, column])
    holdouts = {}
    for name, train in (("early_half", times < (times.min() + times.max()) / 2),
                         ("late_half", times >= (times.min() + times.max()) / 2),
                         ("seed_owned", track["seed_owned"]), ("unallocated", ~track["seed_owned"])):
        if sum(train) < 12 or sum(~train) < 8:
            continue
        holdouts[name] = {}
        for model_name in ("line", "quadratic"):
            coef, predicted, _ = regress(designs[model_name], values, train)
            holdouts[name][model_name] = {"rms_hz": rms(values[~train] - predicted[~train]), "coefficients": coef}
        fit, predicted = timing_fit(orbit, values, np.ones(len(rows)), train)
        holdouts[name]["timing_bias"] = {**fit, "test_rms_hz": rms(values[~train] - predicted[~train])}
        holdouts[name]["baseline_rms_hz"] = rms(values[~train])

    channel_results = []
    for channel in np.unique(channels):
        mask = channels == channel
        channel_results.append({"channel": int(channel), "rf_hz": float(rf[mask][0]),
                                **stats(times[mask], values[mask])})
    # Two-second bin medians damp unequal burst density and isolated outliers.
    bins = np.floor((times - times.min()) / 2).astype(int)
    bx = np.array([np.median(times[bins == b]) for b in np.unique(bins)])
    by = np.array([np.median(values[bins == b]) for b in np.unique(bins)])
    binned = stats(bx, by)
    record = {"scan": label, "catalog_number": track["catalog_number"], "receiver": track["receiver"],
        "final": stats(times, values), "models": models, "channels": channel_results,
        "channel_adjusted_bootstrap": boot, "binned_medians": binned, "subsets": subsets,
        "half_and_provenance_holdouts": holdouts, "physical_parity_max_hz": parity,
        "sealed_timing_s": float(orbit.parameters[6]), "viterbi_changes": int(track["changed"].sum())}
    panel = {"record": record, "times": times, "residual": values, "channels": channels,
             "predictions": predictions, "relaxed_times": arrays["times_s"][relaxed],
             "relaxed_residual": arrays["residual_hz"][relaxed, column], "rows": rows}
    return record, panel


def peer_audit(arrays, tracks):
    """Compare distinct satellite peaks at identical time, channel, receiver, group."""
    output = []
    group_rows = {int(g): np.flatnonzero(arrays["group"] == g) for g in np.unique(arrays["group"])}
    for track in tracks:
        target = track["column"]
        for other, number in enumerate(arrays["catalog_numbers"]):
            if other == target:
                continue
            matches = []
            for row in track["rows"]:
                rr = group_rows[int(arrays["group"][row])]
                rr = rr[arrays["receiver"][rr] == track["receiver"]]
                if np.sum(arrays["posterior"][rr, other]) < .9:
                    continue
                peer = rr[np.argmax(arrays["posterior"][rr, other])]
                if peer == row:
                    continue
                if arrays["rf_hz"][row] != arrays["rf_hz"][peer] or arrays["times_s"][row] != arrays["times_s"][peer]:
                    raise ValueError("peer pair is not simultaneous on the same RF")
                factor = arrays["rf_hz"][row] / CARRIER
                matches.append((float(arrays["times_s"][row]), int(arrays["channel"][row]),
                                arrays["residual_hz"][row, target] * factor,
                                arrays["residual_hz"][peer, other] * factor))
            if len(matches) < 15:
                continue
            pairs = np.asarray(matches)
            x, channels, y, z = pairs.T
            if np.ptp(x) < 10:
                continue
            design = channel_design(x, channels, 1)
            coefficients, _, _ = regress(design, y - z, robust=True)
            output.append({"target": track["catalog_number"], "receiver": track["receiver"],
                "peer": int(number), "groups": len(matches), "start_s": float(min(x)), "end_s": float(max(x)),
                "target_native": stats(x, y), "peer_native": stats(x, z),
                "difference_native": stats(x, y - z),
                "channel_adjusted_robust_difference_slope_hz_s": float(coefficients[-1] / 30)})
    return output


def plot_scan(panels, label, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    fig = plt.figure(figsize=(17, 21))
    grid = fig.add_gridspec(6, 2, left=.06, right=.99, bottom=.055, top=.93, hspace=.5, wspace=.2)
    for index, p in enumerate(panels):
        ax = fig.add_subplot(grid[index // 2, index % 2])
        r = p["record"]
        x, y, ch = p["times"], p["residual"], p["channels"]
        ax.scatter(p["relaxed_times"], p["relaxed_residual"], s=10, color=".7", alpha=.38, zorder=1)
        for channel in np.unique(ch):
            mask = ch == channel
            ax.scatter(x[mask], y[mask], s=13, color=COLORS[(channel-1) % 4], zorder=3)
        for name, color, style in (("line", "#222222", "--"), ("quadratic", "#CC3311", "-"), ("timing_bias", "#882255", ":")):
            ax.plot(x, p["predictions"][name], color=color, linestyle=style, linewidth=1.7, zorder=4)
        for v in (-150, 150):
            ax.axhline(v, color=".55", linestyle=":", linewidth=.7)
        ax.axhline(0, color=".5", linewidth=.7)
        ax.set_ylim(-350, 350)
        ax.set_xlim(max(0, x.min()-10), min(300, x.max()+10))
        f, m = r["final"], r["models"]
        ax.set_title(f"{r['catalog_number']} / RX{r['receiver']} · {f['count']} groups · slope {f['slope_hz_s']:+.2f} Hz/s\n"
                     f"RMS current/line/quad: {f['rms_hz']:.1f}/{m['line']['rms_hz']:.1f}/{m['quadratic']['rms_hz']:.1f} Hz", fontsize=10)
        ax.set_ylabel("GLRT − sealed orbit (Hz)")
        ax.set_xlabel("Receive time (s)")
        ax.grid(alpha=.17)
    fig.suptitle(f"DS13 Scan {label} · residual trend audit\nCurves show fitted residual components; all original orbit fits remain frozen", y=.987, fontsize=15)
    handles = [Line2D([], [], color=COLORS[i], marker="o", linestyle="", label=f"CH{i+1}") for i in range(4)]
    handles += [Line2D([], [], color=".7", marker="o", linestyle="", label="No residual/ownership gate"),
                Line2D([], [], color="#222222", linestyle="--", label="Linear"),
                Line2D([], [], color="#CC3311", label="Quadratic"),
                Line2D([], [], color="#882255", linestyle=":", label="Timing + constant bias")]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5,.965), ncol=8, fontsize=8)
    fig.text(.5,.017,"RMS labels are in-sample diagnostics. See report for purged time-block validation and channel controls.\n"
             "Grey points: target group posterior ≥0.90, ±10 s window, no residual or ownership gate. Display clips beyond ±350 Hz.\n"
             "All Hz normalized to 11.085 GHz; dotted horizontal lines mark the original ±150 Hz selection gate.",ha="center",fontsize=9)
    outputs=[]
    for suffix in ("png","svg"):
        path=output/f"scan-{label.lower()}-residual-audit.{suffix}"
        fig.savefig(path,dpi=165);outputs.append(path)
    plt.close(fig)
    return outputs


def write_csv(path, rows):
    with path.open("x", newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def run(output=OUTPUT):
    output=Path(output)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    membership_path=ROOT/"orbit-backfill-prototype/group-summed-orbit-backfill-memberships.csv"
    backfill_receipt=ROOT/"orbit-backfill-prototype/group-summed-orbit-backfill-receipt.json"
    sealed=json.loads(backfill_receipt.read_text())
    if file_digest(membership_path)!=sealed["outputs"][str(membership_path.resolve())]:
        raise ValueError("membership digest mismatch")
    memberships=read_membership_rows(membership_path)
    sources={str(p):file_digest(p) for p in (Path(__file__), membership_path,backfill_receipt)}
    records, panels_all, peers, artifacts, csv_rows=[],[],[],[],[]
    for session,label in zip(SESSIONS,"AB",strict=True):
        archive,metadata,path,receipt=load_archived_session(session)
        arrays={k:archive[k].copy() for k in archive.files};archive.close()
        bank_path=ROOT/"all-visible-bank"/session/"expanded.npz"
        bank_receipt_path=bank_path.parent/"receipt.json"
        bank_receipt=json.loads(bank_receipt_path.read_text())
        digest=file_digest(bank_path)
        if digest!=bank_receipt["artifacts"]["expanded_npz_sha256"] or digest!=metadata["source_hashes"][str(bank_path)]:
            raise ValueError("archived physical bank hash changed")
        with np.load(bank_path) as b:
            bank={k:b[k] for k in ("numbers","nodes","position","velocity")}
        manifest_path=ROOT/"scans"/session/"bundle.json"
        seed_path=ROOT/"scans"/session/"seed.json"
        manifest=json.loads(manifest_path.read_text());seed=json.loads(seed_path.read_text())
        for p in (path,receipt,bank_path,bank_receipt_path,manifest_path,seed_path):
            sources[str(p)]=file_digest(p)
        tracks=final_tracks(memberships,arrays,label)
        panels=[]
        for track in tracks:
            assignments=[a for a in seed["rough"]["assignments"] if a["accepted"] and int(a["catalog_number"])==track["catalog_number"] and int(a["receiver"])==track["receiver"]]
            mapped=map_raw_seed_rows_to_family_rows(manifest,assignments)
            orig=np.unique(np.concatenate([a["rows"] for a in mapped]))
            record,panel=audit_track(arrays,track,bank,orig,memberships,label)
            records.append(record);panels.append(panel);panels_all.append(panel)
            print(label,track["catalog_number"],track["receiver"],"RMS",record["final"]["rms_hz"],flush=True)
            for i,row in enumerate(track["rows"]):
                csv_rows.append({"scan":label,"catalog_number":track["catalog_number"],"receiver":track["receiver"],
                    "row":int(row),"group":int(arrays["group"][row]),"time_s":float(panel["times"][i]),
                    "channel":int(panel["channels"][i]),"rf_hz":float(arrays["rf_hz"][row]),
                    "residual_hz":float(panel["residual"][i]),
                    **{name+"_correction_hz":float(pred[i]) for name,pred in panel["predictions"].items()}})
        peers.extend([{ "scan":label,**p} for p in peer_audit(arrays,tracks)])
        artifacts.extend(plot_scan(panels,label,output))
    points_path=output/"points-and-diagnostic-corrections.csv";write_csv(points_path,csv_rows);artifacts.append(points_path)
    summary_rows=[]
    for r in records:
        m,f=r["models"],r["final"]
        summary_rows.append({"scan":r["scan"],"catalog_number":r["catalog_number"],"receiver":r["receiver"],
            **f,"channel_slope_hz_s":float(m["channel_line"]["coefficients"][-1]/30),
            **{name+"_cv_rms_hz":v["cv"].get("rms_hz") for name,v in m.items()},
            "timing_bias_extra_s":m["timing_bias"]["extra_timing_s"],"timing_bias_hz":m["timing_bias"]["bias_hz"],
            "timing_bias_rms_hz":m["timing_bias"]["rms_hz"]})
    summary_path=output/"all-tracks.csv";write_csv(summary_path,summary_rows);artifacts.append(summary_path)
    result={"schema":"ds13-residual-trend-audit/v1","created_utc":datetime.now(UTC).isoformat(),
        "source_hashes":sources,"tracks":records,"simultaneous_peer_comparisons":peers,
        "method": {"time_cv":"five equal-duration contiguous blocks, 1 s purge; conditional on frozen selected memberships",
            "bootstrap":"600 resamples of non-overlapping 5 s time clusters; descriptive, not formal multiple-tested significance",
            "timing":"exact archived ephemeris predictor; extra tau in [-1,+1] s, 81-point screen + local refinement",
            "bias":"timing_bias uses normalized 11.085 GHz Hz; timing_native_bias fits a common native-RF Hz offset scaled per row",
            "polynomial":"t centered on each cohort mean, u=(t-mean)/30; quadratic coefficient u² /900 has units Hz/s²",
            "source_verification":"local ephemeris NPZ verified against both archived bank receipt and sealed overlay receipt; full historical /opt runtime provenance not revalidated"},
        "limitations":["All corrections are diagnostics at the reference position, never applied to the original fit or membership.",
            "Final cohorts were selected using the baseline posterior and ±150 Hz residual gate; CV is not independent association or instrument validation.",
            "No new RF or IQ reprocessing. Same orbit, transmitter, receiver or estimator errors can be confounded.",
            "Ungated comparison still conditions on archived group posterior and a time window; it is not unselected raw evidence."],
        "outputs":{str(p):file_digest(p) for p in artifacts}}
    for p,digest in sources.items():
        if file_digest(p)!=digest:raise ValueError(f"source changed during audit: {p}")
    (output/"receipt.json").write_text(json.dumps(serializable(result),indent=2,allow_nan=False)+"\n")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=OUTPUT)
    run(parser.parse_args().output_dir)
