#!/usr/bin/env python3
"""Run matched tau-zero causal point/rate fits on two six-scan TRAIN views."""

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from leo.analysis.research.doppler_error_budget import profile
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records, parse_element_sets

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
EPOCHS = Path("/tmp/leo-train-orbit-epochs.json")
METADATA = Path("/tmp/leo-train-rx-metadata.json")
PRIOR = HERE / "results/frozen-prior.json"
INVENTORY = ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json"
HELPER = ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/fit.py"
SINGLE = ROOT / "reports/2026_09_23_long_training_search/search.py"
PARENTS = (
    ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/results/inference.json",
    ROOT / "reports/2026_09_23_second_train_epoch_replication/results/inference.json",
)
CACHES = (
    Path("/tmp/leo-long-training-cache-full8h"),
    Path("/tmp/leo-long-training-cache-second8h"),
)
NS_HOUR = 3_600_000_000_000


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def disk_point(raw, radius):
    norm = np.linalg.norm(raw)
    return radius * raw / np.sqrt(1 + norm**2)


def target_point_phase(study, current_text, records, cutoff_ns, capture_ns, model):
    eligible = [
        row
        for row in records
        if row["epoch_utc_ns"] < cutoff_ns and row["first_collected_utc_ns"] < cutoff_ns
    ]
    current_key = study.tle_key(current_text)
    current = next((row for row in eligible if study.tle_key(row["text"]) == current_key), None)
    if current is None:
        raise ValueError("current causal element absent from cutoff history")
    previous = [row for row in eligible if row["epoch_utc_ns"] < current["epoch_utc_ns"]]
    if not previous:
        return 0.0, None
    previous = max(previous, key=lambda row: (row["epoch_utc_ns"], row["first_collected_utc_ns"]))
    gap_h = (current["epoch_utc_ns"] - previous["epoch_utc_ns"]) / NS_HOUR
    if not 1 <= gap_h <= 72:
        return 0.0, None
    recent_phase = study.phase_seconds(previous["text"], current["text"], current["epoch_utc_ns"])
    recent_rate = recent_phase / gap_h
    old_sat = parse_element_sets(previous["text"]).satellites[0]
    new_sat = parse_element_sets(current["text"]).satellites[0]
    feature = [
        recent_rate,
        float(new_sat.bstar),
        float(new_sat.no_kozai),
        float(new_sat.ecco),
        float((new_sat.bstar - old_sat.bstar) / gap_h),
        float((new_sat.no_kozai - old_sat.no_kozai) / gap_h),
        float((new_sat.ecco - old_sat.ecco) / gap_h),
        gap_h,
    ]
    predicted_rate = study.predict_rate(model, recent_rate, feature)
    age_h = (capture_ns - current["epoch_utc_ns"]) / NS_HOUR
    return predicted_rate * age_h, {
        "previous_epoch_utc_ns": previous["epoch_utc_ns"],
        "previous_first_collected_utc_ns": previous["first_collected_utc_ns"],
        "current_first_collected_utc_ns": current["first_collected_utc_ns"],
        "gap_h": gap_h,
        "recent_rate_s_h": recent_rate,
        "predicted_rate_s_h": predicted_rate,
        "causal_age_h": age_h,
    }


def fit_model(data, single, prior, sensitivity, sigma, rates, initial_xy):
    radius = prior[2]
    initial_norm = np.linalg.norm(initial_xy)
    raw = initial_xy / np.sqrt(max(radius**2 - initial_norm**2, 1e-12))
    labels = sorted(set(data["source"])) if rates else []
    label_index = {value: index for index, value in enumerate(labels)}

    def unpack(value):
        xy = disk_point(value[:2], radius)
        rate = {label: 0.25 * np.tanh(value[2 + index]) for label, index in label_index.items()}
        return xy, rate

    def residual(value, y=None):
        xy, rate = unpack(value)
        point = single.offset_coordinate(prior[:2], *xy)
        receiver, _ = single.receiver_ecef(*point)
        phase = np.asarray([rate.get(label, 0.0) for label in data["source"]]) * data["age_h"]
        p = sensitivity["p0"] + 0.5 * (sensitivity["p1"] - sensitivity["pm1"]) * phase[:, None]
        p += (
            0.5
            * (sensitivity["p1"] + sensitivity["pm1"] - 2 * sensitivity["p0"])
            * phase[:, None] ** 2
        )
        v = sensitivity["v0"] + 0.5 * (sensitivity["v1"] - sensitivity["vm1"]) * phase[:, None]
        v += (
            0.5
            * (sensitivity["v1"] + sensitivity["vm1"] - 2 * sensitivity["v0"])
            * phase[:, None] ** 2
        )
        delta = p - receiver
        prediction = (
            -single.REFERENCE_RF_HZ
            / single.LIGHT_KM_S
            * np.sum(delta * v, axis=1)
            / np.linalg.norm(delta, axis=1)
        )
        radio = profile(
            (data["y"] if y is None else y) - prediction, data["segment"], data["training"]
        )
        robust = radio[data["training"]] * np.sqrt(
            2 / (np.sqrt(1 + (radio[data["training"]] / 250) ** 2) + 1)
        )
        penalty = 100 * np.asarray(list(rate.values())) / sigma
        return np.concatenate([robust, penalty]), radio, point, rate

    initial = np.r_[raw, np.zeros(len(labels))]
    answer = least_squares(lambda value: residual(value)[0], initial, max_nfev=60)
    _, radio, point, rate = residual(answer.x)
    altered = data["y"].copy()
    altered[~data["training"]] += 1_000_000
    check = least_squares(lambda value: residual(value, altered)[0], initial, max_nfev=60)
    check_xy, check_rate = unpack(check.x)
    final_xy, _ = unpack(answer.x)
    return {
        "latitude_deg": point[0],
        "longitude_deg": point[1],
        "x_km": final_xy.tolist(),
        "training_rms_hz": float(np.sqrt(np.mean(radio[data["training"]] ** 2))),
        "evaluation_rms_hz": float(np.sqrt(np.mean(radio[~data["training"]] ** 2))),
        "converged": bool(answer.success),
        "nfev": answer.nfev,
        "rate_corrections_s_h": {str(k): float(v) for k, v in rate.items()},
        "rate_at_bound_count": int(sum(abs(v) > 0.249 for v in rate.values())),
        "held_1mhz_parameter_invariance": bool(
            np.max(abs(check_xy - final_xy)) < 1e-8
            and all(abs(check_rate[k] - rate[k]) < 1e-10 for k in rate)
        ),
    }


def exact_verification(data, sensitivity, contexts, result, single, prior, replay):
    point = result["latitude_deg"], result["longitude_deg"]
    receiver, _ = single.receiver_ecef(*point)
    rates = {int(key): value for key, value in result["rate_corrections_s_h"].items()}
    prediction = np.empty(len(data["y"]))
    for context in contexts:
        phase = (
            context["point_phase_s"] + rates.get(context["candidate_id"], 0.0) * context["age_h"]
        )
        p, v, valid = replay.state_arrays(
            context["catalogue"],
            [0],
            context["anchor_utc_ns"],
            context["times_s"],
            orbit_time_s=phase,
            clock_s=0,
        )
        if len(valid) != 1:
            raise ValueError("final exact propagation failure")
        delta = p[0] - receiver
        prediction[context["slice"]] = (
            -single.REFERENCE_RF_HZ
            / single.LIGHT_KM_S
            * np.sum(delta * v[0], axis=1)
            / np.linalg.norm(delta, axis=1)
        )
    radio = profile(data["y"] - prediction, data["segment"], data["training"])
    phase = np.asarray([rates.get(label, 0.0) for label in data["source"]]) * data["age_h"]
    qp = sensitivity["p0"] + 0.5 * (sensitivity["p1"] - sensitivity["pm1"]) * phase[:, None]
    qp += (
        0.5 * (sensitivity["p1"] + sensitivity["pm1"] - 2 * sensitivity["p0"]) * phase[:, None] ** 2
    )
    qv = sensitivity["v0"] + 0.5 * (sensitivity["v1"] - sensitivity["vm1"]) * phase[:, None]
    qv += (
        0.5 * (sensitivity["v1"] + sensitivity["vm1"] - 2 * sensitivity["v0"]) * phase[:, None] ** 2
    )
    qdelta = qp - receiver
    qprediction = (
        -single.REFERENCE_RF_HZ
        / single.LIGHT_KM_S
        * np.sum(qdelta * qv, axis=1)
        / np.linalg.norm(qdelta, axis=1)
    )
    qradio = profile(data["y"] - qprediction, data["segment"], data["training"])
    per_track = []
    for segment in np.unique(data["segment"]):
        mask = (data["segment"] == segment) & data["training"]
        per_track.append(float(np.sqrt(np.mean((qradio[mask] - radio[mask]) ** 2))))
    return {
        "training_rms_hz": float(np.sqrt(np.mean(radio[data["training"]] ** 2))),
        "evaluation_rms_hz": float(np.sqrt(np.mean(radio[~data["training"]] ** 2))),
        "quadratic_minus_exact_training_rms_hz": float(
            result["training_rms_hz"] - np.sqrt(np.mean(radio[data["training"]] ** 2))
        ),
        "quadratic_minus_exact_evaluation_rms_hz": float(
            result["evaluation_rms_hz"] - np.sqrt(np.mean(radio[~data["training"]] ** 2))
        ),
        "profiled_residual_difference_per_track_rms_hz": {
            "median": float(np.median(per_track)),
            "maximum": float(np.max(per_track)),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh output required")
    prior_result = json.loads(PRIOR.read_text())
    if prior_result["bindings"]["fixed_epoch_export"] != digest(EPOCHS):
        raise ValueError("prior/epoch export binding differs")
    if prior_result["bindings"]["strict_metadata"] != digest(METADATA):
        raise ValueError("prior/strict metadata binding differs")
    sigma = min(
        prior_result["frozen_model"]["candidates"],
        key=lambda row: row["validation_median_absolute_rate_error_s_h"],
    )["validation_rms_rate_error_s_h"]
    epochs = json.loads(EPOCHS.read_text())
    if epochs["bindings"]["strict_metadata"] != digest(METADATA):
        raise ValueError("epoch/strict metadata binding differs")
    metadata = {row["session_id"]: row for row in json.loads(METADATA.read_text())["sessions"]}
    helper = load(HELPER, "phase_helper")
    single = load(SINGLE, "phase_single")
    view_inputs = load(HERE / "view_inputs.py", "phase_view_inputs")
    arms = view_inputs.load_view_arms()
    reader = TleArchiveReader(args.tle_root)
    refs = reader.list_snapshots()
    refmap = {(r.digest, r.collected_utc_ns): r for r in refs}
    archive_cache = {}
    tools = str(ROOT / "tools")
    sys.path.insert(0, tools)
    study = load(ROOT / "tools/study_causal_orbit_phase_prior.py", "phase_study")
    replay = load(ROOT / "tools/replay_regional_doppler.py", "phase_replay")
    results = []
    for arm in arms:
        print(f"preparing {arm['group']} {arm['prior']}", flush=True)
        session_ids = arm["session_ids"]
        tracks, cache_bindings = helper.prepare(
            single, Path(arm["cache_root"]), session_ids, arm["scans"]
        )
        wanted = {int(t["candidate_id"]) for t in tracks}
        max_cutoff = (
            max(metadata[t["session_id"]]["tle_snapshot_collected_utc_ns"] for t in tracks) + 1
        )
        histories = defaultdict(dict)
        for ref in refs:
            if ref.collected_utc_ns >= max_cutoff:
                continue
            text = reader.read(ref)
            for rec in parse_element_set_records(text):
                if rec.satellite_number in wanted:
                    candidate = {
                        "text": rec.text,
                        "epoch_utc_ns": parse_element_sets(rec.text).element_epoch_utc_ns()[0],
                        "first_collected_utc_ns": ref.collected_utc_ns,
                    }
                    previous = histories[rec.satellite_number].get(rec.text)
                    if (
                        previous is None
                        or candidate["first_collected_utc_ns"] < previous["first_collected_utc_ns"]
                    ):
                        histories[rec.satellite_number][rec.text] = candidate
        arrays = {
            k: []
            for k in (
                "y",
                "training",
                "segment",
                "source",
                "age_h",
                "p0",
                "v0",
                "pm1",
                "vm1",
                "p1",
                "v1",
                "pn",
                "vn",
            )
        }
        contexts = []
        cursor = 0
        for segment, track in enumerate(tracks):
            m = metadata[track["session_id"]]
            identity = (m["tle_snapshot_digest"], m["tle_snapshot_collected_utc_ns"])
            if identity not in archive_cache:
                archive_cache[identity] = reader.read(refmap[identity])
            rec = next(
                r
                for r in parse_element_set_records(archive_cache[identity])
                if r.satellite_number == int(track["candidate_id"])
            )
            mr = next(x for x in m["tracks"] if x["track_id"] == track["track_id"])
            receipt_track = (
                next(x for x in mr["observation_ids"] if x) if mr["observation_ids"] else None
            )
            if receipt_track is None or len(mr["support_center_utc_ns"]) != len(track["times_s"]):
                raise ValueError("metadata/receipt track support differs")
            anchor = mr["support_center_utc_ns"][0] - round(track["times_s"][0] * 1e9)
            recovered_times = np.asarray(mr["support_center_utc_ns"], dtype=np.int64)
            derived_times = anchor + np.rint(track["times_s"] * 1e9).astype(np.int64)
            if np.max(np.abs(recovered_times - derived_times)) > 256:
                raise ValueError("relative/UTC support join differs")
            cutoff = anchor - 505_000_000_000
            if not m["tle_snapshot_collected_utc_ns"] < cutoff:
                raise ValueError("current snapshot is not causal at frozen cutoff")
            phase, detail = target_point_phase(
                study,
                rec.text,
                list(histories[int(track["candidate_id"])].values()),
                cutoff,
                anchor,
                prior_result["frozen_model"]["winner"],
            )
            cat = parse_element_sets(rec.text)
            element_epoch = cat.element_epoch_utc_ns()[0]
            age_h = (anchor - element_epoch) / 3.6e12
            states = {}
            p, v, valid = replay.state_arrays(
                cat, [0], anchor, track["times_s"], orbit_time_s=0.0, clock_s=0
            )
            if len(valid) != 1:
                raise ValueError("nominal exact propagation failure")
            states["pn"], states["vn"] = p[0], v[0]
            for suffix, shift in [("m1", -1), ("0", 0), ("1", 1)]:
                p, v, valid = replay.state_arrays(
                    cat, [0], anchor, track["times_s"], orbit_time_s=phase + shift, clock_s=0
                )
                if len(valid) != 1:
                    raise ValueError("exact propagation failure")
                states["p" + suffix] = p[0]
                states["v" + suffix] = v[0]
            n = len(track["times_s"])
            contexts.append(
                {
                    "slice": slice(cursor, cursor + n),
                    "candidate_id": int(track["candidate_id"]),
                    "catalogue": cat,
                    "anchor_utc_ns": anchor,
                    "times_s": track["times_s"],
                    "point_phase_s": phase,
                    "age_h": age_h,
                }
            )
            cursor += n
            arrays["y"].extend(track["measured_hz"])
            arrays["training"].extend(track["training_mask"])
            arrays["segment"].extend([segment] * n)
            arrays["source"].extend([int(track["candidate_id"])] * n)
            arrays["age_h"].extend([age_h] * n)
            for key in ("p0", "v0", "pm1", "vm1", "p1", "v1", "pn", "vn"):
                arrays[key].extend(states[key])
        data = {k: np.asarray(arrays[k]) for k in ("y", "training", "segment", "source", "age_h")}
        sensitivity = {
            k: np.asarray(arrays[k]) for k in ("p0", "v0", "pm1", "vm1", "p1", "v1", "pn", "vn")
        }
        prior_name = arm["prior"]
        pr = single.PRIORS[prior_name]
        initial_xy = [arm["initial_xy_km"]["east"], arm["initial_xy_km"]["north"]]
        if True:
            print(f"fitting {arm['group']} {arm['prior']}: {len(tracks)} tracks", flush=True)
            tau_zero = fit_model(
                data,
                single,
                pr,
                {
                    "p0": sensitivity["pn"],
                    "v0": sensitivity["vn"],
                    "pm1": sensitivity["pn"],
                    "vm1": sensitivity["vn"],
                    "p1": sensitivity["pn"],
                    "v1": sensitivity["vn"],
                },
                sigma,
                False,
                initial_xy,
            )
            point = fit_model(data, single, pr, sensitivity, sigma, False, tau_zero["x_km"])
            rate = fit_model(data, single, pr, sensitivity, sigma, True, point["x_km"])
            rate["exact_final_state_verification"] = exact_verification(
                data, sensitivity, contexts, rate, single, pr, replay
            )
            results.append(
                {
                    "view": arm["group"],
                    "session_ids": session_ids,
                    "prior": prior_name,
                    "tau_zero_uncorrected": tau_zero,
                    "point_mean_zero_rate": point,
                    "all_identity_rate": rate,
                    "track_count": len(tracks),
                    "candidate_count": len(wanted),
                    "view_bindings": arm["bindings"],
                    "cache_bindings": cache_bindings,
                }
            )
            checkpoint = args.output.with_suffix(".partial.json")
            checkpoint.write_text(json.dumps({"complete": False, "results": results,
                "executed_source": digest(Path(__file__))}, indent=2) + "\n")
            print(f"checkpoint {len(results)}/{len(arms)}: {checkpoint}", flush=True)
    output = {
        "schema": "leo.train_causal_phase_rate_pilot.v1",
        "prior_sigma_s_h": sigma,
        "results": results,
        "bindings": {
            "tool": digest(Path(__file__)),
            "prior": digest(PRIOR),
            "epochs": digest(EPOCHS),
        },
        "validation_or_test_used": False,
        "reference_position_used_for_fit": False,
        "scan_tau_s": 0.0,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
