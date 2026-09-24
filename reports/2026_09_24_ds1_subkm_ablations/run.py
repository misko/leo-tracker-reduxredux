#!/usr/bin/env python3
# ruff: noqa: E501
"""Frozen-trace DS1 ablations for transferable sub-kilometre techniques.

The source DS1 arm supplies the complete, already-sealed local point/tau trace.
This runner never expands that trace.  Candidate choices and all nuisance fits
use the original randomized TRAIN mask; reference position and held rows are
only read after each arm has selected its TRAIN minimum.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear

HERE = Path(__file__).resolve().parent
DS1 = HERE.parent / "2026_09_24_ds1"
CAP = 800.0
RATE_SIGMA = 0.09176615913014215
RATE_BOUND = 0.25
REFERENCE = (37.84903264307456, -122.4856541910174)  # evaluation only


def sha(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sealed(path):
    if sha(path).split(":", 1)[1] != path.with_suffix(".sha256").read_text().split()[0]:
        raise ValueError("seal mismatch: " + str(path))
    return json.loads(path.read_text())


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def archive_ages(requests):
    """Read only causal TLE epochs for already-selected cache candidate IDs."""
    if not requests:
        return {}
    code = (
        "import hashlib,json,sys\n"
        "from pathlib import Path\n"
        "from leo.operations.tle_archive import TleArchiveReader\n"
        "from leo.sky.propagation import parse_element_sets\n"
        "a=TleArchiveReader(Path('/var/lib/leo/tle')); out=[]\n"
        "for q in json.load(sys.stdin):\n"
        " s=next(x for x in a.list_snapshots() if x.digest==q['digest'] and x.collected_utc_ns==q['collected'])\n"
        " payload=a.read(s); assert 'sha256:'+hashlib.sha256(payload.encode()).hexdigest()==q['digest']; c=parse_element_sets(payload); d=dict(zip(map(int,c.satellite_numbers),map(int,c.element_epoch_utc_ns()),strict=True))\n"
        " out.append({'key':q['key'],'age':{str(n):(q['start']-d[n])/3.6e12 for n in q['ids'] if n in d}})\n"
        "print(json.dumps(out))\n"
    )
    result = subprocess.run(
        ["sudo", "-n", "-u", "leo", sys.executable, "-c", code],
        input=json.dumps(requests),
        text=True,
        capture_output=True,
        check=True,
    )
    return {
        item["key"]: {int(k): float(v) for k, v in item["age"].items()}
        for item in json.loads(result.stdout)
    }


def state(engine, session, index, times, tau):
    part = {
        **session,
        "position": session["position"][index : index + 1],
        "velocity": session["velocity"][index : index + 1],
    }
    p, v = engine.interpolate(part, times, np.asarray([tau]))
    return p[0, :, 0], v[0, :, 0]


def prediction(engine, receiver, p, v):
    delta = p - receiver
    return (
        -engine.search.REFERENCE_RF_HZ
        / engine.search.LIGHT_KM_S
        * np.sum(delta * v, axis=1)
        / np.linalg.norm(delta, axis=1)
    )


def pair_tracks(engine, lat, lon, tau, assignments, fixed=None):
    receiver, up = engine.search.receiver_ecef(lat, lon)
    choice = {(a["session_id"], a["track_id"]): a["candidate_id"] for a in assignments}
    if fixed is not None:
        choice = fixed
    out = []
    for session in engine.sessions:
        ids = {str(value): i for i, value in enumerate(session["candidate_ids"])}
        for raw in session["tracks"]:
            cid = choice.get((session["session_id"], raw["track_id"]))
            index = ids.get(str(cid)) if cid is not None else None
            pred = derivative = None
            if index is not None:
                p, v = state(engine, session, index, raw["times"], tau)
                delta = p - receiver
                if np.max(np.sum(delta * up, axis=1) / np.linalg.norm(delta, axis=1)) >= 0:
                    pred = prediction(engine, receiver, p, v)
                    eps = 0.05
                    # Cached authority ends at the declared +/-5 s support.
                    # Use the corresponding one-sided derivative at a bound;
                    # the model records bound diagnostics rather than probing
                    # unrepresented state.
                    if tau >= 5.0 - eps:
                        pm, vm = state(engine, session, index, raw["times"], tau - eps)
                        derivative = (pred - prediction(engine, receiver, pm, vm)) / eps
                    elif tau <= -5.0 + eps:
                        pp, vp = state(engine, session, index, raw["times"], tau + eps)
                        derivative = (prediction(engine, receiver, pp, vp) - pred) / eps
                    else:
                        pp, vp = state(engine, session, index, raw["times"], tau + eps)
                        pm, vm = state(engine, session, index, raw["times"], tau - eps)
                        derivative = (
                            prediction(engine, receiver, pp, vp)
                            - prediction(engine, receiver, pm, vm)
                        ) / (2 * eps)
            out.append(
                {
                    "session_id": session["session_id"],
                    "track_id": raw["track_id"],
                    "candidate_id": cid,
                    "measured": raw["measured"],
                    "train": raw["train"],
                    "weight": raw["weight"],
                    "prediction": pred,
                    "derivative": derivative,
                }
            )
    return out


def fit(tracks, kind, ages, robust=False):
    labels = []
    occurrences = defaultdict(int)
    for t in tracks:
        if t["prediction"] is None:
            continue
        if kind == "scan":
            label = "scan:" + t["session_id"]
        else:
            age = (
                ages.get((t["session_id"], int(t["candidate_id"])))
                if t["candidate_id"] is not None
                else None
            )
            if age is None:
                continue
            label = "norad:" + str(t["candidate_id"])
        occurrences[label] += 1
        if label not in labels:
            labels.append(label)
    # A per-NORAD correction is identifiable as a shared nuisance only when
    # that NORAD recurs.  Leaving singleton IDs at zero prevents a large set
    # of locally flexible one-track timing corrections from masquerading as
    # the historical shared-orbit model.
    if kind == "norad":
        labels = [label for label in labels if occurrences[label] >= 2]
    index = {x: i for i, x in enumerate(labels)}
    xs, ys, ws = [], [], []
    for t in tracks:
        if t["prediction"] is None:
            continue
        if kind == "scan":
            label, multiplier = "scan:" + t["session_id"], 1.0
        else:
            age = (
                ages.get((t["session_id"], int(t["candidate_id"])))
                if t["candidate_id"] is not None
                else None
            )
            if age is None:
                continue
            label, multiplier = "norad:" + str(t["candidate_id"]), age
        if label not in index:
            continue
        mask = t["train"]
        y = t["measured"][mask] - t["prediction"][mask]
        y -= y.mean()
        x = t["derivative"][mask] * multiplier
        x -= x.mean()
        block = np.zeros((len(y), len(labels)))
        block[:, index[label]] = x
        xs.append(block)
        ys.append(y)
        ws.append(np.full(len(y), t["weight"] / len(y)))
    if not labels:
        return {}, {"parameter_count": 0, "at_bound": 0, "missing_age_track_count": 0}
    x, y, weight = np.concatenate(xs), np.concatenate(ys), np.concatenate(ws)
    sigma = 1.0 if kind == "scan" else RATE_SIGMA
    root_w = np.sqrt(weight)
    base_x = np.vstack((x * root_w[:, None], np.eye(len(labels)) / sigma))
    lo = np.full(len(labels), -RATE_BOUND if kind == "norad" else -np.inf)
    hi = np.full(len(labels), RATE_BOUND if kind == "norad" else np.inf)
    beta = np.zeros(len(labels))
    for _ in range(12 if robust else 1):
        scale = np.sqrt(5.0 / (4.0 + ((y - x @ beta) / 250.0) ** 2)) if robust else np.ones(len(y))
        answer = lsq_linear(
            np.vstack((base_x[: len(y)] * scale[:, None], base_x[len(y) :])),
            np.r_[y * root_w * scale, np.zeros(len(labels))],
            bounds=(lo, hi),
            tol=1e-10,
            lsmr_tol="auto",
        )
        if np.max(np.abs(answer.x - beta)) < 1e-7:
            beta = answer.x
            break
        beta = answer.x
    return dict(zip(labels, map(float, beta), strict=True)), {
        "parameter_count": len(labels),
        "at_bound": int(np.sum(np.abs(beta) >= RATE_BOUND - 1e-6)) if kind == "norad" else 0,
        "prior_sigma": sigma,
        "recurrent_norad_only": kind == "norad",
        "robust_fixed_scale_hz": 250.0 if robust else None,
    }


def score(tracks, kind, params, ages):
    train_total = held_total = held_square = supported = 0.0
    for t in tracks:
        if t["prediction"] is None:
            train_total += t["weight"]
            held_total += t["weight"]
            continue
        shift = 0.0
        if kind == "scan":
            shift = params.get("scan:" + t["session_id"], 0.0)
        elif kind == "norad" and t["candidate_id"] is not None:
            shift = params.get("norad:" + str(t["candidate_id"]), 0.0) * ages.get(
                (t["session_id"], int(t["candidate_id"])), 0.0
            )
        err = t["measured"] - t["prediction"] - shift * t["derivative"]
        err -= err[t["train"]].mean()
        a = float(np.mean(err[t["train"]] ** 2))
        b = float(np.mean(err[~t["train"]] ** 2))
        train_total += t["weight"] * min(a / CAP**2, 1.0)
        held_total += t["weight"] * min(b / CAP**2, 1.0)
        held_square += t["weight"] * b
        supported += t["weight"]
    denominator = sum(t["weight"] for t in tracks)
    penalty = (
        sum(v * v for v in params.values())
        if kind == "scan"
        else sum((v / RATE_SIGMA) ** 2 for v in params.values())
        if kind == "norad"
        else 0.0
    )
    return {
        "training_capped_loss": train_total / denominator,
        "penalized_training_capped_loss": (train_total + penalty) / denominator,
        "held_capped_loss": held_total / denominator,
        "held_uncapped_supported_rms_hz": math.sqrt(held_square / supported) if supported else None,
        "supported_occupied_second_weight": supported,
    }


def receipts(case, runner):
    out = {}
    root = runner.CACHE_ROOTS[case["group_id"]]
    for sid in case["session_ids"]:
        e = json.loads((root / sid / "cache_receipt.json").read_text())["prepared_evidence"]
        out[sid] = (
            e["snapshot_digest"],
            int(e["snapshot_collected_utc_ns"]),
            int(e["start_utc_ns"]),
        )
    return out


def run_arm(case, prior, arm, runner, evaluation):
    names = (
        "tau_zero",
        "shared_tau",
        "fixed_identity_shared_tau",
        "linearized_scan_epoch_scale1_sensitivity",
        "linearized_norad_rate",
        "fixed_scale_robust_rate_sensitivity",
        "fractional_track_time",
        "dual_rx_beam_geometry",
    )
    base = {
        (r["model"] == "baseline" and "tau_zero" or "shared_tau"): r
        for r in evaluation
        if r["case_id"] == case["case_id"] and r["prior"] == prior
    }
    if "failure" in arm:
        return [
            {
                "case_id": case["case_id"],
                "partition": case["partition"],
                "group_id": case["group_id"],
                "view": case["view"],
                "scan_count": case["scan_count"],
                "prior": prior,
                "model": n,
                "status": "input_failure" if n in ("tau_zero", "shared_tau") else "not_applicable",
                "reason": arm.get("failure", {}).get("reason")
                if n in ("tau_zero", "shared_tau")
                else "no eligible DS1 TEST64 input; no substitution",
                "truth_used_for_fit": False,
                "held_used_for_fit": False,
            }
            for n in names
        ]
    _, engine = runner.make_engine(case)
    rec = receipts(case, runner)
    # This control freezes IDs selected at the original tau-zero DS1 winner,
    # not IDs from the shared-time arm.  Thus it isolates pointwise
    # reassignment from the one common tau extension.
    winner = arm["models"]["baseline"]
    _, _, chosen = engine.profile(
        winner["latitude_deg"], winner["longitude_deg"], np.asarray([winner["tau_s"]]), False, True
    )
    fixed = {(x["session_id"], x["track_id"]): x["candidate_id"] for x in chosen[0]}
    pairs = {
        n: []
        for n in (
            "fixed_identity_shared_tau",
            "linearized_scan_epoch_scale1_sensitivity",
            "linearized_norad_rate",
            "fixed_scale_robust_rate_sensitivity",
        )
    }
    pending = []
    for pair in arm["visited_pairs"]:
        _, _, assignments = engine.profile(
            pair["latitude_deg"], pair["longitude_deg"], np.asarray([pair["tau_s"]]), False, True
        )
        dynamic = pair_tracks(
            engine, pair["latitude_deg"], pair["longitude_deg"], pair["tau_s"], assignments[0]
        )
        frozen = pair_tracks(
            engine,
            pair["latitude_deg"],
            pair["longitude_deg"],
            pair["tau_s"],
            assignments[0],
            fixed,
        )
        pairs["fixed_identity_shared_tau"].append((pair, frozen, None, {}, {}))
        pending.extend(dynamic)
        pairs["linearized_scan_epoch_scale1_sensitivity"].append(
            (pair, dynamic, "scan", None, None)
        )
        pairs["linearized_norad_rate"].append((pair, dynamic, "norad", None, None))
        pairs["fixed_scale_robust_rate_sensitivity"].append((pair, dynamic, "norad", None, None))
    request = defaultdict(lambda: {"ids": set()})
    for t in pending:
        if t["candidate_id"] is not None:
            digest_value, collected, start = rec[t["session_id"]]
            key = digest_value + "@" + str(collected)
            request[key].update(
                {"key": key, "digest": digest_value, "collected": collected, "start": start}
            )
            request[key]["ids"].add(int(t["candidate_id"]))
    fetched = archive_ages([{**v, "ids": sorted(v["ids"])} for v in request.values()])
    ages = {
        (sid, n): fetched.get(d + "@" + str(c), {}).get(n)
        for sid, (d, c, _s) in rec.items()
        for n in []
    }
    for sid, (d, c, _s) in rec.items():
        for n, age in fetched.get(d + "@" + str(c), {}).items():
            ages[sid, n] = age
    rows = []
    for name, values in pairs.items():
        choices = []
        for pair, tracks, kind, _params, _diag in values:
            if name == "fixed_identity_shared_tau":
                params, diag, actual_kind = {}, {"parameter_count": 0, "at_bound": 0}, None
            else:
                actual_kind = kind
                params, diag = fit(
                    tracks, kind, ages, name == "fixed_scale_robust_rate_sensitivity"
                )
            result = score(tracks, actual_kind, params, ages)
            choices.append({**pair, **result, "diagnostics": diag, "parameter_values": params})
        selected = min(
            choices,
            key=lambda x: (
                x["penalized_training_capped_loss"],
                abs(x["tau_s"]),
                x["tau_s"],
                x["latitude_deg"],
                x["longitude_deg"],
            ),
        )
        rows.append(
            {
                "case_id": case["case_id"],
                "partition": case["partition"],
                "group_id": case["group_id"],
                "view": case["view"],
                "scan_count": case["scan_count"],
                "prior": prior,
                "model": name,
                "status": "completed",
                "reference_error_km": engine.search.haversine_km(
                    (selected["latitude_deg"], selected["longitude_deg"]), REFERENCE
                ),
                "selected": selected,
                "pair_count": len(choices),
                "truth_used_for_fit": False,
                "held_used_for_fit": False,
            }
        )
    for name in ("tau_zero", "shared_tau"):
        r = base[name]
        rows.append(
            {
                "case_id": case["case_id"],
                "partition": case["partition"],
                "group_id": case["group_id"],
                "view": case["view"],
                "scan_count": case["scan_count"],
                "prior": prior,
                "model": name,
                "status": r["status"],
                "reference_error_km": r.get("reference_error_km"),
                "selected": {
                    "tau_s": r.get("tau_s"),
                    "training_capped_loss": r.get("training_capped_loss"),
                    "held_capped_loss": r.get("held_capped_loss"),
                    "held_uncapped_supported_rms_hz": r.get("held_uncapped_supported_rms_hz"),
                    "diagnostics": {
                        "parameter_count": 0,
                        "at_bound": int(r.get("global_tau_boundary", False)),
                    },
                },
                "pair_count": r.get("pair_count"),
                "truth_used_for_fit": False,
                "held_used_for_fit": False,
            }
        )
    for name, reason in (
        (
            "fractional_track_time",
            "not transferred: historical ±5 s per-track timing exceeds device timing authority and failed another group",
        ),
        (
            "dual_rx_beam_geometry",
            "not transferred: DS1 scalar cache has no calibrated dual-RX/beam visibility evidence; prior proxy lost to shuffled control",
        ),
    ):
        rows.append(
            {
                "case_id": case["case_id"],
                "partition": case["partition"],
                "group_id": case["group_id"],
                "view": case["view"],
                "scan_count": case["scan_count"],
                "prior": prior,
                "model": name,
                "status": "not_applicable",
                "reason": reason,
                "truth_used_for_fit": False,
                "held_used_for_fit": False,
            }
        )
    return rows


def render(rows, output):
    output.mkdir(parents=True, exist_ok=True)
    flat = []
    for r in rows:
        s = r.get("selected", {})
        d = s.get("diagnostics", {})
        flat.append(
            {
                "case_id": r["case_id"],
                "partition": r["partition"],
                "group_id": r["group_id"],
                "view": r["view"],
                "scan_count": r["scan_count"],
                "prior": r["prior"],
                "model": r["model"],
                "status": r["status"],
                "reason": r.get("reason"),
                "reference_error_km": r.get("reference_error_km"),
                "tau_s": s.get("tau_s"),
                "training_capped_loss": s.get("training_capped_loss"),
                "held_capped_rms_hz": CAP * math.sqrt(s["held_capped_loss"])
                if s.get("held_capped_loss") is not None
                else None,
                "held_uncapped_supported_rms_hz": s.get("held_uncapped_supported_rms_hz"),
                "parameter_count": d.get("parameter_count"),
                "at_bound": d.get("at_bound"),
                "pair_count": r.get("pair_count"),
            }
        )
    fields = list(flat[0])
    with (output / "rows.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(flat)
    groups = defaultdict(list)
    for r in flat:
        if r["status"] == "completed":
            groups[r["partition"], r["view"], r["model"]].append(r)
    summary = []
    for (partition, view, model), values in sorted(groups.items()):
        error = np.array([v["reference_error_km"] for v in values])
        held = np.array([v["held_capped_rms_hz"] for v in values])
        summary.append(
            {
                "partition": partition,
                "view": view,
                "model": model,
                "arms": len(values),
                "median_error_km": float(np.median(error)),
                "mean_error_km": float(np.mean(error)),
                "subkm_arms": int(np.sum(error < 1)),
                "median_held_capped_rms_hz": float(np.median(held)),
            }
        )
    (output / "summary.json").write_text(
        json.dumps({"rows": rows, "summary": summary}, indent=2, sort_keys=True) + "\n"
    )
    import matplotlib.pyplot as plt

    completed = [r for r in flat if r["status"] == "completed"]
    order = sorted({r["model"] for r in completed})
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for model in order:
        x = [i for i, r in enumerate(completed) if r["model"] == model]
        y = [r["reference_error_km"] for r in completed if r["model"] == model]
        axes[0].scatter(x, y, s=18, label=model)
        h = [r["held_capped_rms_hz"] for r in completed if r["model"] == model]
        axes[1].scatter(h, y, s=18, label=model)
    axes[0].axhline(1, color="black", linestyle="--")
    axes[0].set_yscale("log")
    axes[0].set_ylabel("post-seal error (km)")
    axes[0].set_xlabel("model-local DS1 arm index")
    axes[0].set_title("Frozen-trace DS1 case comparison")
    axes[1].axhline(1, color="black", linestyle="--")
    axes[1].set_yscale("log")
    axes[1].set_xlabel("held capped RMS (Hz)")
    axes[1].set_title("Held RMS versus location error")
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(output / "case_comparison_and_held_error.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append")
    parser.add_argument("--prior", action="append")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    data, _, evaluation = (
        sealed(DS1 / "dataset.json"),
        sealed(DS1 / "inference_index.json"),
        sealed(DS1 / "evaluation.json")["rows"],
    )
    runner = load(DS1 / "run.py", "ds1_ablation_runner")
    rows = []
    for case in data["cases"]:
        if args.case and case["case_id"] not in args.case:
            continue
        for prior in data["priors"]:
            if args.prior and prior not in args.prior:
                continue
            print("running", case["case_id"], prior, flush=True)
            arm = sealed(DS1 / "inference" / (case["case_id"] + "__" + prior + ".json"))
            rows.extend(run_arm(case, prior, arm, runner, evaluation))
    render(rows, args.output)
    (args.output / "metadata.json").write_text(
        json.dumps(
            {
                "schema": "ds1-subkm-frozen-trace-ablations/v1",
                "complete": True,
                "dataset": sha(DS1 / "dataset.json"),
                "inference": sha(DS1 / "inference_index.json"),
                "source": sha(Path(__file__)),
                "truth_used_for_fit": False,
                "held_used_for_fit": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
