"""Bounded, orbit-free native-Hz comparison of tightly epoch-matched receivers.

This is a diagnostic, not an association/oscillator calibration. Candidate
selection uses only visit, probe, RF, native-zero bin, epoch and GLRT margin;
no satellite model, CFO difference or fitted curve selects observations.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "2026_10_02_multiscan_localization"
ALIAS_HZ = 1 / 4.4e-6
SCANS = [
    ("DS10-S01", "scan-fw-df44e74320bd2718"),
    ("DS10-S05", "scan-fw-fec8aa45d347c322"),
    ("DS10-S10", "scan-fw-f2e13c014c6d8141"),
    ("DS11-S04", "scan-fw-6363650720d37f1e"),
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def circular(values):
    return (np.asarray(values) + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def select_pairs(metadata, representatives, arrays, sample_rate, tolerance_s):
    """At most one pair per visit/probe; maximize weaker receiver margin."""
    groups = {}
    for item, row in zip(metadata, representatives, strict=True):
        if item["native_residual_bin"] != 0:
            continue
        visit, receiver, probe = item["local_probe_key"]
        groups.setdefault((visit, probe), [[], []])[receiver].append((item, row))
    selected = []
    for (visit, probe), (left, right) in sorted(groups.items()):
        possibilities = []
        for item0, row0 in left:
            for item1, row1 in right:
                if arrays["rf"][row0] != arrays["rf"][row1]:
                    continue
                dt = (
                    item1["integer_session_sample"] - item0["integer_session_sample"]
                    + item1["fractional_epoch_offset_samples"]
                    - item0["fractional_epoch_offset_samples"]
                ) / sample_rate
                if abs(dt) > tolerance_s:
                    continue
                possibilities.append((
                    -min(item0["fractional_margin"], item1["fractional_margin"]),
                    abs(dt), row0, row1, dt,
                ))
        if not possibilities:
            continue
        _, _, row0, row1, dt = min(possibilities)
        raw = float(arrays["measured"][row1] - arrays["measured"][row0])
        selected.append({
            "visit": visit, "probe": probe, "row0": int(row0), "row1": int(row1),
            "time_s": float((arrays["times"][row0] + arrays["times"][row1]) / 2),
            "epoch_difference_s": float(dt),
            "channel": int(arrays["channel"][row0]), "rf_hz": float(arrays["rf"][row0]),
            "margin0": float(arrays["margin"][row0]),
            "margin1": float(arrays["margin"][row1]),
            "rx1_minus_rx0_raw_hz": raw,
            "rx1_minus_rx0_modulo_alias_hz": float(circular(raw)),
        })
    return selected


def design(times, channels, order, channel_values):
    x = (np.asarray(times) - 150) / 150
    return np.column_stack([
        *[(np.asarray(channels) == c).astype(float) for c in channel_values],
        *[x ** power for power in range(1, order + 1)],
    ])


def huber_fit(matrix, values, delta=100.0):
    """Fixed 100-Hz Huber loss; no iterative observation rejection."""
    values = np.asarray(values)
    coefficients = np.linalg.lstsq(matrix, np.full(len(values), np.median(values)), rcond=None)[0]
    for _ in range(100):
        residual = values - matrix @ coefficients
        weight = np.minimum(1.0, delta / np.maximum(abs(residual), 1e-12))
        updated = np.linalg.lstsq(matrix * np.sqrt(weight[:, None]), values * np.sqrt(weight), rcond=None)[0]
        if np.max(abs(updated - coefficients)) < 1e-8:
            coefficients = updated
            break
        coefficients = updated
    return coefficients


def models(times, channels, values):
    times, channels, values = map(np.asarray, (times, channels, values))
    channel_values = np.unique(channels)
    result = {}
    folds = np.minimum(((times - times.min()) / np.ptp(times) * 5).astype(int), 4)
    for order in (0, 1, 2):
        matrix = design(times, channels, order, channel_values)
        fitted = huber_fit(matrix, values)
        residual = values - matrix @ fitted
        held = np.full(len(times), np.nan)
        for fold in range(5):
            test = folds == fold
            train = (~test) & ((times < times[test].min() - 1) | (times > times[test].max() + 1))
            if np.linalg.matrix_rank(matrix[train]) == matrix.shape[1]:
                held[test] = values[test] - matrix[test] @ huber_fit(matrix[train], values[train])
        result[str(order)] = {
            "channel_intercepts_hz_at_150s": dict(zip(map(str, channel_values), map(float, fitted[:len(channel_values)]))),
            "slope_hz_s_at_150s": float(fitted[len(channel_values)] / 150) if order else 0.0,
            "quadratic_coefficient_hz_s2": float(fitted[-1] / 150**2) if order == 2 else 0.0,
            "descriptive_median_absolute_error_hz": float(np.median(abs(residual))),
            "descriptive_p90_absolute_error_hz": float(np.quantile(abs(residual), .9)),
            "all_selected_rms_hz": float(np.sqrt(np.mean(residual**2))),
            "fraction_within_300_hz": float(np.mean(abs(residual) <= 300)),
            "held_count": int(np.isfinite(held).sum()),
            "five_time_block_held_median_absolute_error_hz": float(np.nanmedian(abs(held))),
            "five_time_block_held_p90_absolute_error_hz": float(np.nanquantile(abs(held), .9)),
        }
    return result


def summarize_pairs(pairs):
    a = {key: np.asarray([p[key] for p in pairs]) for key in pairs[0]}
    t, ch, y = a["time_s"], a["channel"], a["rx1_minus_rx0_modulo_alias_hz"]
    result = {
        "pair_count": len(pairs), "time_range_s": [float(t.min()), float(t.max())],
        "absolute_epoch_difference_ns_quantiles": dict(zip(["minimum", "median", "p90", "maximum"], map(float, np.quantile(abs(a["epoch_difference_s"])*1e9, [0,.5,.9,1])))),
        "median_margin_rx0": float(np.median(a["margin0"])),
        "median_margin_rx1": float(np.median(a["margin1"])),
        "native_direct_difference_equals_wrapped_fraction": float(np.mean(abs(y-a["rx1_minus_rx0_raw_hz"]) < 1e-6)),
        "channel_offset_controlled_models": models(t,ch,y),
        "per_channel": {},
    }
    bins=[]
    for start in range(0,300,30):
        mask=(t>=start)&(t<start+30)
        bins.append({"start_s":start,"end_s":start+30,"pair_count":int(mask.sum()),"median_rx_difference_hz":float(np.median(y[mask]))})
    result["thirty_second_bin_medians"] = bins
    result["thirty_second_bin_median_range_hz"] = float(np.ptp([b["median_rx_difference_hz"] for b in bins]))
    for channel in np.unique(ch):
        mask = ch == channel
        result["per_channel"][str(channel)] = {
            "pair_count": int(mask.sum()), "time_range_s": [float(t[mask].min()),float(t[mask].max())],
            "models": models(t[mask],ch[mask],y[mask]),
        }
    strong = np.minimum(a["margin0"],a["margin1"]) >= .4
    result["strong_margin_at_least_0p4_both"] = {
        "pair_count": int(strong.sum()),
        "models": models(t[strong],ch[strong],y[strong]),
    }
    return result


def archived_pilot_crosscheck():
    path = SOURCE / "pilot-cfo-precision-diagnostic.json"
    receipt = json.loads(path.read_text())
    groups = {}
    for probe in receipt["progress"]["probes"]:
        groups.setdefault((probe["visit_index"],probe["probe_index"]),{})[probe["receiver_axis"]] = probe
    rows = []
    for (visit,probe), receivers in groups.items():
        if set(receivers) != {0,1}:
            continue
        left,right = receivers[0],receivers[1]
        dt = (right["integer_session_sample"] - left["integer_session_sample"] + right["fractional_epoch_offset_samples"] - left["fractional_epoch_offset_samples"]) / 1e7
        if left["native_residual_bin"] or right["native_residual_bin"] or abs(dt)>1e-7:
            continue
        frames0={f["frame_index"]:f for f in left["frames"] if f["measurement_supported"]}
        frames1={f["frame_index"]:f for f in right["frames"] if f["measurement_supported"]}
        common=sorted(frames0.keys() & frames1.keys())
        if not common:
            continue
        corrections=[frames1[k]["circular_difference_from_persisted_cfo_hz"] - frames0[k]["circular_difference_from_persisted_cfo_hz"] for k in common]
        raw=right["persisted_tracking_cfo_hz"]-left["persisted_tracking_cfo_hz"]
        rows.append({"visit":visit,"probe":probe,"time_session_counter_s":left["integer_session_sample"]/1e7,"epoch_difference_ns":dt*1e9,"supported_matched_frame_indices":common,"median_refinement_of_rx_difference_hz":float(np.median(corrections)),"persisted_wrapped_rx_difference_hz":float(circular(raw)),"refined_wrapped_rx_difference_hz":float(circular(raw+np.median(corrections)))})
    absolute=np.abs([r["median_refinement_of_rx_difference_hz"] for r in rows])
    return {"source":str(path),"source_sha256":digest(path),"session_id":receipt["session_id"],"selection":"Both native bins zero, same visit/probe, epoch separation <=100ns, common frame index with measurement_supported on both receivers. No CFO-agreement filtering.","matched_visit_count":len(rows),"matched_frame_count":sum(len(r["supported_matched_frame_indices"]) for r in rows),"absolute_rx_difference_refinement_hz_quantiles":dict(zip(["median","p90","maximum"],map(float,np.quantile(absolute,[.5,.9,1])))),"rows":rows,"limitation":"Independent estimator uses the same original IQ and acquisition-bound pilot timing; sparse existing selection, not a fresh blind audit or decoded identity."}


def main():
    grouped_receipt_path = SOURCE / "paired-rx-grouped-width-v1.json"
    grouped = json.loads(grouped_receipt_path.read_text())
    source_digests = {str(grouped_receipt_path): digest(grouped_receipt_path)}
    cases, all_pairs = [], []
    for unit, session in SCANS:
        prior = next(c for c in grouped["cases"] if c["unit_id"] == unit)
        for path, expected in prior["input_sha256_pre"].items():
            actual = digest(path)
            if actual != expected:
                raise ValueError(f"input digest mismatch: {path}")
            source_digests[path] = actual
        prefix = unit.replace("-S", "-")
        export = json.loads((SOURCE / f"runs/alias-family-cohort-v1/{prefix}-{session}.json").read_text())
        with np.load(SOURCE / f"scans/{session}/bundle.npz", allow_pickle=False) as archive:
            arrays = {k: archive[k] for k in ["times","measured","rf","receiver","channel","group","margin"]}
        # Bind the numerical observations back to their acquisition metadata.
        indices=np.asarray(export["representative_original_indices"])
        representatives=export["grouping"]["representative_rows"]
        if not np.array_equal(arrays["measured"][indices],[r["tracking_cfo_hz"] for r in representatives]):
            raise ValueError("metadata CFO differs from native-Hz numerical observation")
        if not np.array_equal(arrays["receiver"][indices],[r["local_probe_key"][1] for r in representatives]):
            raise ValueError("receiver axis mismatch")
        manifest=json.loads((SOURCE/f"scans/{session}/bundle.json").read_text())
        case = {"unit_id":unit,"session_id":session,"origin_utc_ns":manifest["origin_utc_ns"],"cohorts":{}}
        for label, tolerance in [("epoch_within_1us",1e-6),("epoch_within_100ns",1e-7)]:
            pairs = select_pairs(export["grouping"]["representative_rows"],export["representative_original_indices"],arrays,export["sample_rate_hz"],tolerance)
            case["cohorts"][label] = summarize_pairs(pairs)
            all_pairs.extend(dict(unit_id=unit,session_id=session,cohort=label,**p) for p in pairs)
        cases.append(case)
        print(unit, json.dumps(case["cohorts"]["epoch_within_100ns"]["channel_offset_controlled_models"]),flush=True)
    receipt = {
        "schema":"cross-scan-native-rx-drift-diagnostic/v1",
        "selection":"Four contrasting archived scans selected diagnostically, not representative population sampling; no DS13 A/B reused.",
        "pairing":"Same visit, probe and exact RF; both native residual bin zero; epoch threshold fixed at 1us and tighter 100ns sensitivity. At most one pair per visit/probe, maximizing weaker GLRT margin, independent of frequency difference and model fit.",
        "fit":"Native RX1−RX0 CFO modulo full 227272.727Hz ambiguity. Separate constant per channel and shared polynomial time terms; fixed 100Hz Huber loss; no observation rejection. Five contiguous time folds, 1s purge, training-only coefficients. No satellite/ephemeris or separately fitted receiver correction used.",
        "limitations":["Epoch alignment is strong evidence of common signal but does not prove identical decoded frame/satellite identity.","GLRT margin is a quality proxy, not calibrated SNR.","Differences isolate differential chain/estimator effects only if common emission; they cannot measure common transmitter drift or common receiver drift.","Smooth fits are diagnostics, not corrections; selected scans and temporal dependence prevent population/generalized causal claims.","Historical source metadata differs from frozen dataset-admission analysis; local bundle and export digests are verified against published grouped-width receipt.","No IQ reread, RF collection, orbit fitting or production modification performed."],
        "source_sha256":source_digests,"diagnostic_code_sha256":digest(__file__),"cases":cases,
        "independent_archived_pilot_crosscheck":archived_pilot_crosscheck(),
    }
    (ROOT/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    with (ROOT/"native-paired-points.csv").open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(all_pairs[0]));writer.writeheader();writer.writerows(all_pairs)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure,axes=plt.subplots(2,2,figsize=(14,9),sharex=True)
    for ax,case in zip(axes.ravel(),cases,strict=True):
        p=[r for r in all_pairs if r["unit_id"]==case["unit_id"] and r["cohort"]=="epoch_within_100ns"]
        y=np.array([r["rx1_minus_rx0_modulo_alias_hz"] for r in p]);t=np.array([r["time_s"] for r in p]);ch=np.array([r["channel"] for r in p])
        center=float(np.median(y))
        for channel in np.unique(ch):
            mask=ch==channel
            ax.scatter(t[mask],(y[mask]-center),s=4,alpha=.45,label=f"CH{channel}")
        lo,hi=np.quantile(y-center,[.005,.995]);ax.set_ylim(lo-100,hi+100)
        ax.set_title(f'{case["unit_id"]} · {len(p)} pairs · center {center:+.0f} Hz')
        ax.grid(alpha=.2);ax.set_xlim(0,300);ax.set_ylabel("Native RX1−RX0 CFO minus panel median (Hz)")
        ax.set_xlabel("Receive time since capture start (s)");ax.legend(markerscale=2)
    figure.suptitle("Other scans: tightly epoch-matched dual-receiver frequency differences\nSame visit/probe/RF; epoch separation ≤100 ns; CFO modulo 227.273 kHz; no orbit or RX trend removed",fontsize=13)
    figure.text(.5,.005,"Zero native residual bins only; pairs chosen by epoch/margin, not CFO proximity. Plot uses 0.5–99.5% quantile limits + 100 Hz padding; CSV retains all pairs. Identity not decoded.",ha="center",fontsize=8)
    figure.tight_layout(rect=(0,.025,1,.94))
    figure.savefig(ROOT/"native-rx-difference-other-scans.png",dpi=170)
    plt.close(figure)


if __name__ == "__main__":
    main()
