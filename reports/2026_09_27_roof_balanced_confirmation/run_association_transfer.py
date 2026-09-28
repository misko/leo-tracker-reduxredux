"""Calibration-only RX-to-reserved-Doppler association-transfer shards."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
import json
import math
from pathlib import Path
import pickle
import time

import numpy as np

import association_transfer_core as transfer
from association_transfer_split import temporal_association_split
import detection_random_intercept_refined as detection_core
import mixture_calibration_inputs as adapter
import mixture_reception_core as mixture_core
import ratio_random_intercept as ratio_core
import run_mixture_calibration as calibration_runner
import run_ratio_random_intercept as ratio_runner
import run_track_random_intercept as detection_runner

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DIRECTION = ROOT / "reports/2026_09_27_roof_direction_subset"
LOCATION = ROOT / "reports/2026_09_27_roof_location_geometry"
FIRST = ROOT / "reports/2026_09_27_roof_geometry_confirmation"

import sys
sys.path[:0] = [str(DIRECTION), str(LOCATION), str(FIRST)]
import calibrate_frequency_fixedpoint as frequency_helpers
from pairing import provenance_key
from source_links import resolve
from source_topology import filter_prepared
from robust_core import student_t_logpdf, train_shortlist
from leo.analysis.adaptive_tle_prediction import RegionalTrackPredictionEvaluator, build_prediction_banks
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig, reconstruct_persistent_hop_trajectories,
    persistent_hop_tracklet_graph,
)
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader

FIT_ORDER = 64
VERIFY_ORDER = 128
QUADRATURE_TOLERANCE = .001
EXPECTED_TRACKS = 344
EXPECTED_ROWS = 6378


def digest(payload: bytes) -> str:
    return calibration_runner.digest(payload)


def json_value(value):
    if isinstance(value, dict): return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [json_value(v) for v in value]
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    return value


def source_hashes():
    names = ("run_association_transfer.py", "association_transfer_core.py",
             "association_transfer_split.py", "mixture_calibration_inputs.py",
             "detection_random_intercept_refined.py", "ratio_random_intercept.py",
             "robust_core.py", "source_links.py", "source_topology.py",
             "calibrate_frequency_fixedpoint.py")
    paths = {name: (HERE / name if (HERE / name).exists() else
                    DIRECTION / name if (DIRECTION / name).exists() else
                    FIRST / name if (FIRST / name).exists() else LOCATION / name)
             for name in names}
    return {name: digest(path.read_bytes()) for name, path in paths.items()}


def provenance_rows(raw):
    """Public graph observation provenance keyed by track and observation."""
    projected = project_scanner_candidates(raw)
    source = {candidate.candidate_id: candidate for candidate in projected}
    if len(source) != len(projected): raise ValueError("duplicate projected candidate ID")
    trajectory = reconstruct_persistent_hop_trajectories(
        projected, config=PersistentHopTrajectoryConfig(minimum_span_s=3., minimum_support=6))
    points = defaultdict(set)
    for tracklet in trajectory.tracklets:
        for point in tracklet.points:
            candidate = source[point.candidate_id]
            key = (tracklet.tracklet_id, *provenance_key(candidate),
                   f"rx-{candidate.receiver_id}", point.normalized_dealiased_cfo_hz)
            points[key].add(candidate.candidate_id)
    result = {}
    for hypothesis in trajectory.hypotheses:
        for tracklet_id in hypothesis.tracklet_ids:
            graph = persistent_hop_tracklet_graph(hypothesis, tracklet_id)
            for observation in graph.observations:
                key = (tracklet_id, observation.source_group_id,
                       observation.source_sample_start, observation.source_sample_end,
                       observation.support_center_utc_ns, observation.stream_id,
                       observation.measured_cfo_hz)
                ids = points.get(key, set())
                if len(ids) != 1: raise ValueError("graph observation source is not unique")
                candidate = source[next(iter(ids))]
                probe = next((p for p in raw.probes if p.visit_index == candidate.visit_index and
                              p.probe_index == candidate.probe_index and
                              p.receiver_id == candidate.receiver_id), None)
                if probe is None: raise ValueError("source probe missing")
                siblings = [p for p in raw.probes if p.visit_index == candidate.visit_index and
                            p.probe_index == candidate.probe_index]
                if len(siblings) != 2 or {p.receiver_id for p in siblings} != {0, 1} or any(
                        (p.probe_start_ms, p.channel, p.edge, p.valid_start_counter) !=
                        (probe.probe_start_ms, probe.channel, probe.edge, probe.valid_start_counter)
                        for p in siblings):
                    raise ValueError("RX opportunity lanes are not simultaneous")
                value = {
                    "source_group_id": observation.source_group_id,
                    "sample_start": int(observation.source_sample_start),
                    "sample_end": int(observation.source_sample_end),
                    "utc_ns": int(observation.support_center_utc_ns),
                    # Session is implicit in this one-session shard.  Receiver,
                    # rank and RX-specific counters must not split an opportunity.
                    "opportunity_key": (raw.session_id, int(probe.visit_index),
                                        int(probe.probe_index)),
                }
                join = (tracklet_id, observation.observation_id)
                if join in result and result[join] != value:
                    raise ValueError("conflicting graph observation provenance")
                result[join] = value
    return result


def directional_design(track, tensor, schema, mode):
    """Return frozen mixture design, changing only the direction coordinate."""
    if mode not in {"normal", "reversed", "null"}: raise ValueError("unknown direction mode")
    detection = np.asarray(tensor.detection_design, float).copy()
    ratio = np.asarray(tensor.ratio_design, float).copy()
    weights = np.exp(np.asarray(track.log_weights, float))
    for n, row in enumerate(track.rows):
        east = np.asarray(row.east, float)
        if mode == "reversed": east = -east
        elif mode == "null": east = np.repeat(weights @ east, len(east))
        signed = east if row.receiver_id == "rx0" else -east
        detection[:, n, -1] = ((signed - schema.detection_east_mean) /
                               schema.detection_east_scale)
        ratio[:, n, -1] = ((east - schema.ratio_east_mean) / schema.ratio_east_scale)
    return detection, ratio


def reception_loglik(track, tensor, schema, theta, layout, indices, sigma, tau, mode):
    detection, ratio = directional_design(track, tensor, schema, mode)
    idx = np.asarray(indices, int); matched = np.asarray(tensor.matched, bool)[idx]
    pd, pr = layout.detection_size, layout.ratio_size
    logits = np.einsum("knp,p->kn", detection[:, idx], theta[:pd])
    low = detection_core.candidate_detection_loglik(logits, matched, sigma,
                                                     quadrature_order=FIT_ORDER)
    high = detection_core.candidate_detection_loglik(logits, matched, sigma,
                                                      quadrature_order=VERIFY_ORDER)
    delta = float(np.max(np.abs(low-high)))
    if (not np.all(np.isfinite(low)) or not np.all(np.isfinite(high)) or
            not math.isfinite(delta) or delta < 0 or delta > QUADRATURE_TOLERANCE):
        raise ValueError("detection quadrature check failed")
    means = np.einsum("knp,p->kn", ratio[:, idx], theta[pd:pd+pr])
    observed = np.asarray(tensor.log_ratio, float)[idx]
    residual = observed[None, matched] - means[:, matched]
    ratio_ll = ratio_core.candidate_ratio_loglik(
        residual, math.exp(2*float(theta[-1])), tau)
    # The preregistered estimator is the 64-point value; 128 points are an
    # acceptance check only and must not silently change the scored model.
    result = low + ratio_ll
    if not np.all(np.isfinite(result)): raise ValueError("reception likelihood is nonfinite")
    return result, {"fit_order": FIT_ORDER, "verification_order": VERIFY_ORDER,
                             "maximum_candidate_loglik_absolute_difference": delta,
                             "tolerance": QUADRATURE_TOLERANCE, "passed": True}


def summarize(rows, weight_key="weight_seconds"):
    if not rows: return {"tracks": 0}
    output = {"tracks": len(rows), "held_observations": sum(r["held_count"] for r in rows)}
    for control in ("normal", "reversed", "null"):
        for metric in ("baseline_mean_nll", "reception_mean_nll",
                       "improvement_baseline_minus_reception"):
            values = np.asarray([r[control][metric] for r in rows], float)
            weights = np.asarray([r[weight_key] for r in rows], float)
            output[f"{control}_{metric}_equal_track"] = float(values.mean())
            output[f"{control}_{metric}_occupied_second_weighted"] = float(weights@values/weights.sum())
    return output


def _accepted_sources(sessions):
    tracks, receipt, calibration, calibration_sha, detection, detection_sha = \
        ratio_runner.load_sources()
    ratio_path = HERE / "ratio_random_intercept.json"
    ratio_bytes = ratio_path.read_bytes(); ratio = json.loads(ratio_bytes)
    expected_checks = {"all_fits_valid_and_interior", "mixture_pooled_gain",
                       "mixture_at_least_four_folds_improve",
                       "mixture_positive_without_largest_gain"}
    if (receipt["sessions"] != sessions or not ratio.get("advance") or
            set(ratio.get("advancement_checks", {})) != expected_checks or
            not all(ratio["advancement_checks"].values()) or
            ratio.get("calibration_sha256") != calibration_sha or
            ratio.get("detection_random_effect_sha256") != detection_sha or
            ratio.get("protocol_sha256") != digest(
                (HERE / "RATIO_RANDOM_INTERCEPT_PROTOCOL.md").read_bytes()) or
            ratio.get("code_sha256") != ratio_runner.source_hashes()):
        raise ValueError("accepted reception calibration chain changed")
    for name, expected in ratio.get("shard_sha256", {}).items():
        if digest((HERE / name).read_bytes()) != expected:
            raise ValueError("ratio shard changed: " + name)
    if len(ratio.get("shard_sha256", {})) != 7:
        raise ValueError("ratio shard inventory changed")
    return tracks, receipt, calibration, calibration_sha, detection, detection_sha, ratio, digest(ratio_bytes)


def _fold_models(sid, sessions, calibration, detection, ratio):
    coefficients = next(row for row in calibration["conditional_loso_shards"]
                        if row["held_session"] == sid)
    detection_name = f"track-random-intercept-refined-fold-{sid}.json"
    ratio_name = f"ratio-random-intercept-fold-{sid}.json"
    detection_fold = json.loads((HERE / detection_name).read_text())
    ratio_fold = json.loads((HERE / ratio_name).read_text())
    if (detection["shard_sha256"].get(detection_name) != digest((HERE / detection_name).read_bytes()) or
            ratio["shard_sha256"].get(ratio_name) != digest((HERE / ratio_name).read_bytes()) or
            detection_fold.get("held_session") != sid or ratio_fold.get("held_session") != sid or
            detection_fold.get("training_sessions") != [x for x in sessions if x != sid] or
            ratio_fold.get("training_sessions") != [x for x in sessions if x != sid]):
        raise ValueError("LOSO shard binding changed")
    dm = detection_fold["models"]["mixture"]
    rm = ratio_fold["models"]["mixture"]
    sigma = float(dm["sigma_selection"]["sigma"]); tau = float(rm["tau_selection"]["tau"])
    if (not dm.get("numerically_accepted") or not rm.get("numerically_accepted") or
            not 0 <= sigma < 8 or not 0 <= tau < 4 or
            float(rm["detection_sigma"]) != sigma):
        raise ValueError("LOSO shared effects are not accepted")
    return coefficients, detection_fold, ratio_fold, sigma, tau


def _atomic(path, value):
    if path.exists(): raise FileExistsError(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(json_value(value), indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def run(session_index: int):
    started = time.monotonic()
    fixed_path = LOCATION / "topology_frequency_fixedpoint.json"
    fixed_bytes = fixed_path.read_bytes(); fixed = json.loads(fixed_bytes)
    sessions = sorted(fixed["final_tracks"])
    if not 0 <= session_index < len(sessions): raise IndexError("session index must be 0..5")
    sid = sessions[session_index]
    target = HERE / f"association-transfer-{sid}.json"
    if target.exists(): raise FileExistsError(target)
    parameters = fixed["frozen_final_parameters"]
    if parameters != {"scale_hz": 130.0352477522671,
                      "degrees_of_freedom": 1.5307006392659719}:
        raise ValueError("frozen frequency hyperparameters changed")

    joined, receipt, calibration, calibration_sha, detection, detection_sha, ratio, ratio_sha = \
        _accepted_sources(sessions)
    held = tuple(track for track in joined if track.session_id == sid)
    training = tuple(track for track in joined if track.session_id != sid)
    coefficients, detection_fold, ratio_fold, sigma, tau = _fold_models(
        sid, sessions, calibration, detection, ratio)
    schema = adapter.fit_schema(training)
    if coefficients["feature_schema"] != json_value(asdict(schema)):
        raise ValueError("LOSO feature schema changed")
    tensors, layout, names = adapter.build_arm(held, schema, "mixture", mixture_core)
    model = coefficients["models"]["mixture"]
    theta = detection_runner.frozen_theta(model, layout)
    joined_by_track = {track.track_id: (track, tensor)
                       for track, tensor in zip(held, tensors, strict=True)}

    inventory_path = DIRECTION / "evaluation_inventory.json"
    inventory_bytes = inventory_path.read_bytes()
    inventory = {row["session_id"]: row for row in json.loads(inventory_bytes)}
    entry = inventory[sid]; payload = Path(entry["cache_file"]).read_bytes()
    if (not entry["ready"] or entry["split"] != "calibration" or
            digest(payload) != entry["cache_sha256"]):
        raise ValueError("calibration cache changed")
    raw = pickle.loads(payload)
    prepared = prepare_adaptive_tle_position_inputs(
        sid, inputs=frequency_helpers.CachedInput(raw),
        archive=TleArchiveReader(Path("/var/lib/leo/tle")))
    source = fixed["source_digests"][sid]
    for key in ("input_manifest_sha256", "analysis_manifest_sha256",
                "evidence_sha256", "snapshot_digest"):
        if getattr(prepared, key) != source[key]: raise ValueError("prepared binding changed: " + key)
    links = resolve(raw)
    canonical_links = json.dumps(links, sort_keys=True, separators=(",", ":"),
                                 allow_nan=False).encode()
    if digest(canonical_links) != source["source_links_sha256"]:
        raise ValueError("source links changed")
    prepared, topology = filter_prepared(prepared, links)
    if (topology["removed_track_ids"] != source["removed_track_ids"] or
            len(prepared.tracks) != len(held)):
        raise ValueError("topology-filtered track inventory changed")

    manifest_path = DIRECTION / "evaluation_manifest.json"
    manifest_bytes = manifest_path.read_bytes(); manifest = json.loads(manifest_bytes)
    directions = json.loads((HERE / "calibration_directions_data.json").read_text())
    if (directions["source_hashes"].get("evaluation_inventory") != digest(inventory_bytes) or
            directions["source_hashes"].get("evaluation_manifest") != digest(manifest_bytes) or
            directions["source_hashes"].get("topology_frequency_fixedpoint") != digest(fixed_bytes)):
        raise ValueError("known-site direction input binding changed")
    pose = next(row["pose"]["pose_authority"] for row in manifest["sessions"]
                if row["pose"]["session_id"] == sid)
    banks, bank_receipt = build_prediction_banks(
        prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns,
        prepared.tracks, taus_s=np.array([0.]))
    blocks = defaultdict(list)
    evaluator = RegionalTrackPredictionEvaluator(
        banks, lambda _e, _n: frequency_helpers.point(
            pose["latitude_deg"], pose["longitude_deg"]), taus_s=np.array([0.]))
    for block in evaluator(0, 0): blocks[block.track_id].append(block)
    bank_by_track = {bank.source.track_id: bank for bank in banks}
    provenance = provenance_rows(raw)
    model_rows = json.loads((DIRECTION / "model_rows.json").read_text())
    pair_by_observation = {(row["track_id"], row["observation_id"]): row.get("physical_pair_key")
                           for row in model_rows if row["session_id"] == sid and row["split"] == "cal"}
    frozen_by_track = {row["track_id"]: row for row in fixed["final_tracks"][sid]}
    results = []; unsupported = []
    for prepared_track in prepared.tracks:
        tid = prepared_track.track_id
        if tid not in joined_by_track or tid not in frozen_by_track:
            raise ValueError("prepared/frozen/reception track membership changed")
        joined_track, tensor = joined_by_track[tid]
        chunks = blocks[tid]
        predicted = np.concatenate([block.predictions_hz[:, 0, :] for block in chunks])
        candidate_ids = np.concatenate([block.candidate_ids for block in chunks])
        visible = np.concatenate([np.asarray(block.visible).reshape(-1) for block in chunks])
        shortlist = train_shortlist(
            predicted, prepared_track.measured_hz, prepared_track.training_mask, visible,
            scale_hz=parameters["scale_hz"], df=parameters["degrees_of_freedom"])
        chosen = np.asarray(shortlist["candidate_indices"], int)
        ids = candidate_ids[chosen].astype(int).tolist(); frozen_track = frozen_by_track[tid]
        if (ids != frozen_track["candidate_ids"] or
                not np.allclose(shortlist["profiled_cfo_hz"], frozen_track["profiled_cfo_hz"], rtol=0, atol=1e-9) or
                not np.allclose(shortlist["log_weights"], frozen_track["log_weights"], rtol=0, atol=1e-10)):
            raise ValueError("frequency shortlist does not reproduce frozen extraction")
        observation_lookup = {oid: n for n, oid in enumerate(prepared_track.observation_ids)}
        joined_lookup = {row.observation_id: n for n, row in enumerate(joined_track.rows)}
        if set(joined_lookup) != {oid for oid, train in zip(prepared_track.observation_ids,
                                                            prepared_track.training_mask) if not train}:
            raise ValueError("reserve reception/frequency observation membership differs")
        split_input = []
        for n, (oid, train) in enumerate(zip(prepared_track.observation_ids,
                                             prepared_track.training_mask, strict=True)):
            prov = provenance.get((tid, oid))
            if prov is None: raise ValueError("observation lacks public provenance")
            split_input.append({"observation_index": n, "observation_id": oid,
                                "training": bool(train), **prov,
                                "physical_pair_key": pair_by_observation.get((tid, oid))})
        split = temporal_association_split(split_input)
        if not split["supported"]:
            unsupported.append({"track_id": tid, "split": split}); continue
        weight_seconds = len(np.unique(np.floor(prepared_track.times_s)))
        residual = (np.asarray(prepared_track.measured_hz)[None, :] - predicted[chosen] -
                    np.asarray(shortlist["profiled_cfo_hz"])[:, None])
        reserve_mask = ~np.asarray(prepared_track.training_mask, bool)
        if not np.allclose(residual[:, reserve_mask],
                           np.asarray(frozen_track["reserve_residual_hz"], float),
                           rtol=0, atol=1e-8):
            raise ValueError("reserve residuals do not reproduce frozen extraction")
        frequency_ll = student_t_logpdf(
            residual, scale_hz=parameters["scale_hz"],
            degrees_of_freedom=parameters["degrees_of_freedom"])
        directions = {}
        for label, conditioning_indices, held_indices in (
                ("A_to_B", split["A_observation_indices"], split["B_observation_indices"]),
                ("B_to_A", split["B_observation_indices"], split["A_observation_indices"])):
            reception_indices = [joined_lookup[prepared_track.observation_ids[n]]
                                 for n in conditioning_indices]
            f_a = frequency_ll[:, conditioning_indices].sum(axis=1)
            f_b = frequency_ll[:, held_indices].sum(axis=1)
            controls = {}; quadrature = {}
            for mode in ("normal", "reversed", "null"):
                r_a, check = reception_loglik(joined_track, tensor, schema, theta, layout,
                                               reception_indices, sigma, tau, mode)
                controls[mode] = transfer.association_transfer_score(
                    ids, shortlist["log_weights"], f_a, r_a, f_b, len(held_indices))
                quadrature[mode] = check
                controls[mode]["conditioning_reception_log_likelihood"] = r_a.tolist()
            directions[label] = {"conditioning_observation_indices": conditioning_indices,
                                 "held_observation_indices": held_indices,
                                 "conditioning_frequency_log_likelihood": f_a.tolist(),
                                 "held_frequency_log_likelihood": f_b.tolist(),
                                 "reception": controls, "quadrature": quadrature}
        results.append({"track_id": tid, "candidate_ids": ids,
                        "training_log_weights": shortlist["log_weights"],
                        "profiled_cfo_hz": shortlist["profiled_cfo_hz"],
                        "weight_seconds": weight_seconds, "split": split,
                        "directions": directions})

    def direction_rows(label):
        return [{"session_id": sid, "track_id": row["track_id"], "direction": label,
                 "candidate_ids": row["candidate_ids"],
                 "weight_seconds": row["weight_seconds"],
                 "conditioning_count": len(row["directions"][label]["conditioning_observation_indices"]),
                 "held_count": row["directions"][label]["reception"]["normal"]["held_count"],
                 "conditioning_frequency_log_likelihood": row["directions"][label]["conditioning_frequency_log_likelihood"],
                 "held_frequency_log_likelihood": row["directions"][label]["held_frequency_log_likelihood"],
                 **{mode: row["directions"][label]["reception"][mode]
                    for mode in ("normal", "reversed", "null")}} for row in results]
    result_records = [record for label in ("A_to_B", "B_to_A")
                      for record in direction_rows(label)]
    protocol_path = HERE / "ASSOCIATION_TRANSFER_PROTOCOL.md"
    split_totals = {key: sum(row["split"]["counts"][key] for row in results) +
                         sum(row["split"]["counts"][key] for row in unsupported)
                    for key in ("rows", "components", "training_components",
                                "reserve_dropped_with_training", "guard_components",
                                "guard_excluded", "A", "B")}
    output = {
        "kind": "calibration_only_conditional_association_transfer", "session_index": session_index,
        "held_session": sid, "finished": True, "tracks": results,
        "result_records": result_records, "unsupported_tracks": unsupported,
        "accounting": {"expected_all_sessions_tracks": EXPECTED_TRACKS,
                       "expected_all_sessions_reserve_rows": EXPECTED_ROWS,
                       "session_tracks": len(held), "session_reserve_rows": sum(len(t.rows) for t in held),
                       "supported_tracks": len(results), "unsupported_tracks": len(unsupported),
                       "split_totals": split_totals,
                       "A_counts": sorted(row["split"]["counts"]["A"] for row in results),
                       "B_counts": sorted(row["split"]["counts"]["B"] for row in results)},
        "summaries": {label: summarize(direction_rows(label)) for label in ("A_to_B", "B_to_A")},
        "frequency_parameters": parameters, "feature_schema": asdict(schema),
        "mixture_feature_names": names, "detection_sigma": sigma, "ratio_tau": tau,
        "calibration_sha256": calibration_sha, "detection_aggregate_sha256": detection_sha,
        "ratio_aggregate_sha256": ratio_sha,
        "coefficient_shard_sha256": digest((HERE / f"mixture-calibration-polished-fold-{sid}.json").read_bytes()),
        "detection_shard_sha256": detection["shard_sha256"][f"track-random-intercept-refined-fold-{sid}.json"],
        "ratio_shard_sha256": ratio["shard_sha256"][f"ratio-random-intercept-fold-{sid}.json"],
        "input_source_hashes": receipt["source_hashes"], "cache_sha256": entry["cache_sha256"],
        "evaluation_inventory_sha256": digest(inventory_bytes),
        "evaluation_manifest_sha256": digest(manifest_bytes),
        "calibration_directions_data_sha256": digest(
            (HERE / "calibration_directions_data.json").read_bytes()),
        "input_manifest_sha256": prepared.input_manifest_sha256,
        "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
        "evidence_sha256": prepared.evidence_sha256, "snapshot_digest": prepared.snapshot_digest,
        "source_links_sha256": source["source_links_sha256"],
        "prediction_receipt": asdict(bank_receipt), "topology_receipt": topology,
        "protocol_sha256": digest(protocol_path.read_bytes()), "code_sha256": source_hashes(),
        "elapsed_s": time.monotonic()-started,
        "scope": "Known calibration site; held-session LOSO RX model; conditional identity diagnostic, not satellite truth or geographic evidence.",
    }
    _atomic(target, output)
    print("ASSOCIATION_TRANSFER_DONE", sid, len(results), len(unsupported), flush=True)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--session-index", type=int, required=True)
    run(parser.parse_args().session_index)


if __name__ == "__main__": main()
