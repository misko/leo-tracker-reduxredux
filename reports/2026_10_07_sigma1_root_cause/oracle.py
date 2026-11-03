"""Diagnostic fixed-position profiles; truth is never an inference candidate.

Compare the known receiver location with the prior sigma=1 selected location,
using identical satellite evidence, receiver baseline, seeds and fit caps.
These are conditional, finite-start profiles, not global likelihood optima.
"""
import hashlib
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import time

import numpy as np

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "2026_10_07_bad_sample_options"
SPEC = importlib.util.spec_from_file_location("controls", OLD / "experiment.py")
CONTROLS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROLS)


def reference_point(prior, latitude_deg, longitude_deg):
    lat0, lon0, lat, lon = np.radians([prior.latitude_deg, prior.longitude_deg,
                                      latitude_deg, longitude_deg])
    dlon = lon - lon0
    y = np.sin(dlon) * np.cos(lat)
    x = np.cos(lat0) * np.sin(lat) - np.sin(lat0) * np.cos(lat) * np.cos(dlon)
    angle = np.arctan2(np.hypot(x, y), np.sin(lat0) * np.sin(lat)
                      + np.cos(lat0) * np.cos(lat) * np.cos(dlon))
    bearing = np.arctan2(y, x)
    return 6371.0088 * angle * np.array([np.sin(bearing), np.cos(bearing)])


def load(case):
    import leo
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.contracts.regional_position import RegionalPrior
    from leo.contracts.digests import canonical_digest
    from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
    receipt = json.loads((OLD / case / "results.json").read_text())
    snapshot = json.loads(CONTROLS.SOURCE.read_text())
    capture = next(c for c in snapshot["captures"] if c["session_id"] == receipt["session_id"])
    doc = capture["regional_document"]
    for path, digest in doc["configuration"]["source_digests"].items():
        assert CONTROLS.digest_bytes((Path(leo.__file__).parent / path).read_bytes()) == digest
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = store.load(receipt["session_id"])
    finally:
        store.close()
    assert source.input_manifest_sha256 == doc["input_manifest_sha256"]
    assert source.analysis_manifest_sha256 == doc["analysis_manifest_sha256"]
    prepared = prepare_position_windows(source)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    saved = doc["diagnostics"]
    tle = next(s for s in archive.list_snapshots() if s.digest == saved["snapshot_sha256"]
               and s.collected_utc_ns == saved["snapshot_collected_utc_ns"])
    payload, _ = exclude_labelled_starlink_debris(archive.read(tle))
    catalogue = parse_element_sets(payload)
    indices = np.array([i for i, n in enumerate(catalogue.names) if n.upper().startswith("STARLINK")])
    assert canonical_digest({"windows": prepared.evidence_sha256, "tle": tle.digest,
                             "candidates": [int(catalogue.satellite_numbers[i]) for i in indices]}) == doc["evidence_sha256"]
    prior = RegionalPrior(**doc["configuration"]["prior"])
    bank, bank_receipt = build_regional_bank(catalogue, indices, prepared.start_utc_ns,
                                           prepared.observations, prior, maximum_seconds=60)
    assert list(bank_receipt.retained_numbers) == saved["bank"]["retained_numbers"]
    checkpoint = RegionalCheckpointStore(Path("/srv/bulk/leo"), receipt["session_id"], saved["checkpoint_binding"])
    return doc, receipt, prepared.observations, prior, bank, checkpoint, canonical_digest(doc["configuration"]["run"])


def fixed_audit(objective, vector, arm):
    value, gradient, terms = objective.evaluate(vector)
    gradient = gradient.copy()
    gradient[:2] = 0  # Equality-constrained position has no free gradient component.
    obs, bank = objective.observations, objective.bank
    audit = CONTROLS.audit(vector, gradient, objective.basis, arm, objective.prior.radius_km,
                           np.zeros(2), objective.prior.radius_km,
                           max(-20., bank.nodes_s[0] - obs.times_s.min()),
                           min(20., bank.nodes_s[-1] - obs.times_s.max()))
    mass = float(terms.responsibilities.sum())
    return dict(objective=float(value), data_nll=float(terms.nll),
                timing_penalty=float(value - terms.nll),
                posterior_rms_hz=float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)),
                signal_fraction=mass / len(obs.window_ids), vector=vector.tolist(), **audit)


def main():
    from leo.analysis.regional_position_score import PositionObjective, coordinates, predict_orbits, singleton_likelihood
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import PositionScore
    output_path = HERE / "oracle_results.json"
    if output_path.exists():
        raise FileExistsError(output_path)
    output = dict(protocol_sha256=CONTROLS.digest_bytes(Path(__file__).read_bytes()),
                  sigma_s=1., seconds_per_fit=8., iterations=300, rows=[], selections=[], cases={}, status="running")

    def save():
        output_path.write_text(json.dumps(output, indent=2, default=CONTROLS.encode) + "\n")

    for case in ("1939", "2139"):
        doc, receipt, obs, prior, bank, checkpoint, prefix = load(case)
        truth = reference_point(prior, doc["reference_latitude_deg"], doc["reference_longitude_deg"])
        np.testing.assert_allclose(coordinates(prior, truth), [doc["reference_latitude_deg"], doc["reference_longitude_deg"]], atol=1e-9, rtol=0)
        original = [r for r in doc["diagnostics"]["final_starts"] if r["method"] == "V16" and r["fit"]]
        basins = {r["basin"] for r in receipt["selections"] if r["option"] == "sigma100"}
        if case == "2139":
            # Include the original T1AT winning bank, selected by that method's score.
            t1 = [r for r in doc["diagnostics"]["final_starts"] if r["method"] == "T1AT" and r["arm"] == "fitted-c" and r["fit"]]
            basins.add(min(t1, key=lambda r: r["fit"]["objective"] + r["calibration_penalty"])["basin"])
        output["cases"][case] = dict(session_id=receipt["session_id"], evidence_sha256=doc["evidence_sha256"],
                                     reference_point_km=truth.tolist(), basins=sorted(basins))
        for basin in sorted(basins):
            association = checkpoint.get(prefix + ":" + basin + ":association")["result"]
            calibration = checkpoint.get(prefix + ":" + basin + ":calibration")["result"]
            objective = PositionObjective(obs, bank.select(association["selected_indices"]), prior,
                                          replace(PositionScore(**doc["configuration"]["scores"]["V16"]), relative_sigma_s=1.),
                                          receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]))
            midpoint = (obs.times_s.min() + obs.times_s.max()) / 2
            masks = {"early": obs.times_s <= midpoint, "late": obs.times_s > midpoint,
                     **{f"rx{rx}": obs.receiver == rx for rx in np.unique(obs.receiver)},
                     **{f"channel{channel}": obs.channel == channel for channel in np.unique(obs.channel)}}
            for arm in CONTROLS.ARMS:
                previous = min((r for r in receipt["candidates"] if r["option"] == "sigma100" and r["arm"] == arm and r["basin"] == basin), key=lambda r:r["selection_score"])
                starts = [r for r in original if r["basin"] == basin and r["arm"] == arm]
                assert len(starts) == 2
                for location, point in (("prior_sigma1_fit", np.asarray(previous["vector"][:2])), ("known_reference", truth)):
                    candidates = []
                    for source in starts:
                        vector = np.asarray(source["fit"]["vector"]).copy()
                        vector[:2] = point
                        before = fixed_audit(objective, vector, arm)
                        fit = fit_position(objective, vector, rf_arm=arm, fixed_position=True,
                                           maximum_seconds=8, maximum_iterations=300)
                        row = fixed_audit(objective, fit.vector, arm)
                        assert abs(row["stationarity"] - fit.stationarity) < 1e-5
                        np.testing.assert_array_equal(fit.vector[:2], point)
                        if arm == "zero-c":
                            assert fit.vector[6] == 0
                        row.update(case=case, basin=basin, arm=arm, location=location, seed=source["start"],
                                   elapsed_s=fit.elapsed_s, stop_reason=fit.stop_reason,
                                   initial_objective=before["objective"], original_seed_sha256=CONTROLS.vector_digest(source["fit"]["vector"]))
                        output["rows"].append(row)
                        candidates.append(row)
                        print(case, basin, arm, location, source["start"], round(row["objective"], 3), row["converged"], flush=True)
                        save()
                    best = min(candidates, key=lambda r:r["objective"]).copy()
                    vector = np.asarray(best["vector"])
                    prediction, visible, _, _ = predict_orbits(objective.bank, obs, prior, vector[:2], vector[7] + objective.basis @ vector[8:])
                    prediction += (objective.design @ vector[2:7] + objective.baseline)[:, None]
                    best["block_data_nll"] = {label: float(singleton_likelihood(obs.measured_hz[mask], prediction[mask], visible[mask], objective.score).nll)
                                              for label, mask in masks.items()}
                    output["selections"].append(best)
                    save()
    output["status"] = "complete"
    save()


if __name__ == "__main__":
    main()
