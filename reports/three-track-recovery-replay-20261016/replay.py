"""Replay pinned cold checkpoints without refitting or reading /tmp artifacts."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import importlib.metadata
import leo

import numpy as np

from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.application.shared_orbit_replay import selected_model
from leo.application.channel_group_refinement import objective
from leo.analysis.shared_scan_model import SharedScanObjective, donor_state
from leo.analysis.channel_group_calibration import project_calibration_seed
from leo.analysis.sequential_group_calibration import (
    SequentialShift, fixed_shift_objective, freeze_sequential_calibration,
)
from leo.analysis.regional_position_score import circular, zero_sum_basis
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.hard60_bounded_fit import _Problem
from leo.contracts.regional_position import PositionObservations, RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

HERE = Path(__file__).resolve().parent


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def verified_json(path, expected=None):
    payload = path.read_bytes()
    if expected is not None and digest(payload) != expected:
        raise ValueError(f"Digest mismatch: {path.name}")
    return json.loads(payload)


def verify_capsule():
    manifest = verified_json(HERE / "manifest.json")
    for entry in manifest["files"]:
        if digest((HERE / entry["path"]).read_bytes()) != entry["sha256"]:
            raise ValueError(f"Capsule digest mismatch: {entry['path']}")
    package_root = Path(leo.__file__).resolve().parent
    for entry in manifest["runtime_modules"]:
        if digest((package_root / entry["path"]).read_bytes()) != entry["sha256"]:
            raise ValueError(f"Analysis package source differs: {entry['path']}")
    for name, version in manifest["runtime_versions"].items():
        if importlib.metadata.version(name) != version:
            raise ValueError(f"Scientific dependency version differs: {name}")
    return manifest


def replay(args, *, return_context=False):
    verify_capsule()
    folder = HERE / "checkpoints" / args.fold
    derivation = verified_json(folder / "derivation.json")
    document = verified_json(args.input, derivation["parent_input_sha256"])
    source = load_input(document)
    origin = source.timing.first_sample_estimate_utc_ns
    winners = {}
    for point in project_scanner_candidates(source):
        previous = winners.get(point.source_group_id)
        key = lambda p: (-p.margin, p.candidate_rank, p.candidate_id)
        if previous is None or key(point) < key(previous):
            winners[point.source_group_id] = point
    points = sorted(winners.values(), key=lambda p: (p.support_center_utc_ns, p.source_group_id))
    if len(points) != derivation["original_observations"]:
        raise ValueError("Original observation count changed")
    held = derivation["withheld_original_rows"]
    keys = {(points[i].visit_index, points[i].receiver_id, points[i].probe_index) for i in held}
    derived = {k: v for k, v in document.items() if k in
               ("source", "clock_anchor", "delivery_clocks", "last_sample_counter")}
    derived["source"]["probes"] = [p for p in derived["source"]["probes"] if
        (p["visit_index"], p["receiver_id"], p["probe_index"]) not in keys]
    payload = (json.dumps(derived, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if digest(payload) != derivation["derived_input_sha256"]:
        raise ValueError("Training-input reconstruction differs")
    prepared, nodes = prepare_views(load_input(derived))
    cold_obs = prepared["all"].observations
    obs = PositionObservations(
        tuple(p.source_group_id for p in points),
        np.array([(p.support_center_utc_ns - origin) / 1e9 for p in points]),
        np.array([p.measured_cfo_hz for p in points]),
        np.array([p.actual_rf_hz for p in points]),
        np.array([p.receiver_id for p in points]),
        np.array([p.channel for p in points]), np.array([p.margin for p in points]),
    )
    if set(obs.window_ids) - set(cold_obs.window_ids) != {points[i].source_group_id for i in held}:
        raise ValueError("Withheld source groups differ")
    terminal = verified_json(folder / "terminal.json")
    stages = {p.stem: verified_json(p) for p in (folder / "stages").glob("*.json")}
    bindings = {Path(r["path"]).stem: r["sha256"] for r in terminal["stage_receipts"]}
    for path in (folder / "stages").glob("*.json"):
        if "sha256:" + digest(path.read_bytes()) != bindings[path.stem]:
            raise ValueError("Saved stage differs from original terminal receipt")
    prior = RegionalPrior(**terminal["provenance"]["prior"])
    archive = TleArchiveReader(args.tle_root)
    snapshot = next(s for s in archive.list_snapshots()
                    if s.digest == terminal["provenance"]["tle_sha256"])
    catalogue = parse_element_sets(archive.read(snapshot))
    lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
    numbers = terminal["candidate_numbers"]
    bank, _ = build_regional_bank(catalogue, [lookup[n] for n in numbers], origin, cold_obs, prior)
    order = {int(n): i for i, n in enumerate(bank.numbers)}
    bank = bank.select([order[n] for n in numbers])
    cold_model, fit, audit = selected_model(
        {"all": SimpleNamespace(observations=cold_obs)}, bank, prior,
        np.array(terminal["provenance"]["clock_nodes_s"]), terminal, stages,
    )
    if not audit["accepted"]:
        raise ValueError("Cold training checkpoint fails strict replay audit")
    source_name = terminal["selection"]["source"]
    if source_name == "B-all":
        training_joint = objective(SimpleNamespace(observations=cold_obs), bank, prior, nodes)
        _, shift, _, _, _ = donor_state(training_joint,
            stages[f"B-{stages['source-selection']['B_index']}"]["result"]["fit"])
    else:
        high = stages[source_name + "-high"]["result"]["fit"]
        shift = SequentialShift(tuple(high["group_receivers"]), np.array(high["group_offsets_hz"]))
    if return_context:
        return SimpleNamespace(observations=obs, training_observations=cold_obs,
            bank=bank, prior=prior, clock_nodes=nodes, training_fit=fit,
            training_audit=audit, shift=shift, derivation=derivation,
            stages=stages, catalogue=catalogue, catalogue_lookup=lookup,
            origin_utc_ns=origin, candidate_numbers=numbers,
            regional_candidate_numbers=terminal['provenance']['full_candidate_numbers'])
    vector, nuisance = (np.array(fit[k]) for k in ("vector", "nuisance"))
    calibration = freeze_sequential_calibration(cold_model.original,
        dict(vector=vector, nuisance=nuisance[:cold_model.clock_count]), shift)
    target = calibration.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5)
    joint = objective(SimpleNamespace(observations=obs), bank, prior, nodes)
    raw = fixed_shift_objective(joint.base, shift)
    projection = project_calibration_seed(raw, target - raw.baseline)
    vector[2:7] = projection["coefficients"][:5]
    nuisance = np.r_[projection["coefficients"][5:], nuisance[cold_model.clock_count:]]
    base = SharedScanObjective(raw, shift)
    transport_error = float(np.max(abs(raw.correction(vector, nuisance[:base.clock_count]) - target)))
    if transport_error >= 1e-6:
        raise ValueError("Calibration transport differs")
    output = dict(fold=args.fold, training_observations=len(cold_obs.times_s),
                  withheld_observations=len(held), cold_audit=audit,
                  calibration_transport_error_hz=transport_error, tracks=[])
    if args.variant == "cold":
        reference = verified_json(folder / "cold_candidate_temporal_transfer.json")
        full, _ = build_regional_bank(catalogue,
            [lookup[n] for n in terminal["provenance"]["full_candidate_numbers"]], origin, obs, prior)
        correction = raw.correction(vector, nuisance[:base.clock_count])
        for target_rows in derivation["targets"]:
            selected = next(r for r in reference["results"] if r["track"] == target_rows["track"])["ranked"][0]
            rows = np.array(target_rows["test_rows"])
            k = list(full.numbers).index(selected["satellite"])
            prediction = predict_orbits(full.select([k]), observation_subset(obs, rows), prior,
                vector[:2], np.array([selected["timing_s"]]), derivatives=False)[0][:, 0]
            rms = float(np.sqrt(np.mean(circular(obs.measured_hz[rows] - correction[rows] - prediction)**2)))
            if abs(rms - selected["test_rms_hz"]) > 1e-6:
                raise ValueError("Cold withheld replay differs")
            output["tracks"].append(dict(track=target_rows["track"], satellite=selected["satellite"], rms_hz=rms))
    else:
        from frozen_band_bias_joint import FrozenBandBiasJoint
        checkpoint = verified_json(folder / (args.variant + ".json"))
        if not checkpoint["audit"]["accepted"]:
            raise ValueError("Joint checkpoint was not accepted")
        mask = np.ones(len(points), bool); mask[held] = False
        base = SharedScanObjective(raw, shift, mask=mask)
        base.score = replace(base.score, relative_sigma_s=.5)
        indices = []; columns = []
        if checkpoint["variant"] == "band_bias":
            _, _, _, derivative = predict_orbits(bank, obs, prior, vector[:2],
                vector[7] + zero_sum_basis(len(numbers)) @ vector[8:])
            for hypothesis in checkpoint["hypotheses"]:
                if hypothesis["mode"] == "lower_band_frequency_basis":
                    k = numbers.index(hypothesis["satellite"])
                    indices.append(k); columns.append(derivative[:, k] * (obs.channel <= 4))
        basis = np.column_stack(columns) if columns else np.zeros((len(points), 0))
        model = FrozenBandBiasJoint(base, basis, indices)
        v, n = (np.array(checkpoint["fit"][k]) for k in ("vector", "nuisance"))
        evaluation = model.evaluate_joint(v, n)
        problem = _Problem(model, v, rf_arm=checkpoint["arm"],
            local_center=vector[:2], local_radius_km=25., slope_half_width_hz_s=60)
        limits = np.r_[np.full(model.clock_count, 2000.), model.group_limits]
        scales = np.r_[np.full(model.clock_count, 50.), model.group_scales]
        projected = scales * evaluation[2]
        projected[(n <= -limits + 1e-7) & (projected >= 0)] = 0
        projected[(n >= limits - 1e-7) & (projected <= 0)] = 0
        kkt = max(problem.stationarity(v, evaluation[1]), float(np.max(abs(projected), initial=0)))
        if not problem.feasible(v) or np.any(abs(n) > limits + 1e-7) or kkt > .001:
            raise ValueError("Joint endpoint fails independent feasibility/stationarity audit")
        if abs(evaluation[0] - checkpoint["fit"]["objective"]) > 1e-7:
            raise ValueError("Joint training objective replay differs")
        changed = object.__new__(type(raw)); changed.__dict__.update(raw.__dict__)
        changed.observations = replace(obs, measured_hz=obs.measured_hz + np.where(mask, 0., 1234567.))
        altered_base = SharedScanObjective(changed, shift, mask=mask); altered_base.score = base.score
        altered = FrozenBandBiasJoint(altered_base, basis, indices)
        difference = max(float(np.max(abs(np.asarray(a)-np.asarray(b)), initial=0))
                         for a, b in zip(evaluation[:3], altered.evaluate_joint(v, n)[:3]))
        if difference != 0:
            raise ValueError("Withheld measurements influence training objective or gradients")
        output.update(joint_stationarity=kkt, withheld_perturbation_error=difference)
        full_base = SharedScanObjective(raw, shift); full_base.score = base.score
        terms = FrozenBandBiasJoint(full_base, basis, indices).evaluate_joint(v, n)[3]
        best = terms.responsibilities.argmax(axis=1)
        associated = terms.responsibilities[np.arange(len(points)), best] > terms.clutter_probability
        for previous, target_rows in zip(checkpoint["after"]["tracks"], derivation["targets"]):
            rows = np.array(target_rows["test_rows"]); k = numbers.index(previous["satellite"])
            rms = float(np.sqrt(np.mean(terms.residual_hz[rows, k]**2)))
            matches = int(np.sum(associated[rows] & (best[rows] == k)))
            if abs(rms - previous["test_rms_hz"]) > 1e-6 or matches != previous["test_intended_matches"]:
                raise ValueError("Joint withheld predictions or assignments differ")
            output["tracks"].append(dict(track=target_rows["track"], satellite=previous["satellite"],
                                        rms_hz=rms, intended_matches=matches, test_count=len(rows)))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--tle-root", required=True, type=Path)
    parser.add_argument("--fold", choices=("early_to_late", "late_to_early"), required=True)
    parser.add_argument("--variant", default="cold", choices=("cold", "band_bias", "no_bias_from_band"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = replay(args)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload)
    print(payload)
