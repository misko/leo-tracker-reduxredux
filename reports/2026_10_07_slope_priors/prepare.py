"""Freeze shared numerical inputs through public readers, without fitting.

The published method-specific winning basin union is the only candidate pool.
Reference coordinates are copied into evaluation-only metadata, never seeds.
Run with the deployed regional worker on PYTHONPATH and the API interpreter.
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CASES = (
    ("1939", "scan-fw-6a376b600fc2f542", "2026_10_07_recent_filter_review"),
    ("2139", "scan-fw-e3bebc228093a125", "2026_10_07_adaptive_drift_8h"),
    ("2252", "scan-fw-ffe5accf2d020263", "2026_10_07_adaptive_drift_8h"),
    ("2322", "scan-fw-7503dce5ad59cac2", "2026_10_07_adaptive_drift_8h"),
    ("guard2109", "scan-fw-e634af901bed5cd3", "2026_10_07_adaptive_drift_8h"),
    ("guard0223", "scan-fw-037100c3a1aa6ca8", "2026_10_07_adaptive_drift_8h"),
)
OBSERVATION_FIELDS = ("window_ids", "times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin")
BANK_FIELDS = ("numbers", "nodes_s", "position_km", "velocity_km_s")


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def encode(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def reference_point(prior, latitude_deg, longitude_deg):
    lat0, lon0, lat, lon = np.radians([prior.latitude_deg, prior.longitude_deg,
                                      latitude_deg, longitude_deg])
    dlon = lon - lon0
    y = np.sin(dlon) * np.cos(lat)
    x = np.cos(lat0) * np.sin(lat) - np.sin(lat0) * np.cos(lat) * np.cos(dlon)
    angle = np.arctan2(np.hypot(x, y), np.sin(lat0) * np.sin(lat)
                      + np.cos(lat0) * np.cos(lat) * np.cos(dlon))
    return 6371.0088 * angle * np.array([np.sin(np.arctan2(y, x)), np.cos(np.arctan2(y, x))])


def prepare_case(case, session_id, report):
    import leo
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import PositionObjective, coordinates
    from leo.contracts.regional_position import RegionalPrior, PositionScore
    from leo.contracts.digests import canonical_digest
    from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

    snapshot_path = HERE.parent / report / "snapshot.json"
    snapshot_raw = snapshot_path.read_bytes()
    capture = next(c for c in json.loads(snapshot_raw)["captures"] if c["session_id"] == session_id)
    doc = capture["regional_document"]
    assert canonical_digest(doc) == capture["regional_document_sha256"]
    assert canonical_digest(doc["configuration"]) == doc["configuration_sha256"]
    for path, expected in doc["configuration"]["source_digests"].items():
        assert digest((Path(leo.__file__).parent / path).read_bytes()) == expected, path
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = store.load(session_id)
    finally:
        store.close()
    assert source.input_manifest_sha256 == doc["input_manifest_sha256"]
    assert source.analysis_manifest_sha256 == doc["analysis_manifest_sha256"]
    prepared = prepare_position_windows(source)
    obs = prepared.observations
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    saved = doc["diagnostics"]
    tle = next(s for s in archive.list_snapshots() if s.digest == saved["snapshot_sha256"]
               and s.collected_utc_ns == saved["snapshot_collected_utc_ns"])
    payload, exclusions = exclude_labelled_starlink_debris(archive.read(tle))
    catalogue = parse_element_sets(payload)
    indices = np.array([i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")])
    candidate_numbers = [int(catalogue.satellite_numbers[i]) for i in indices]
    assert canonical_digest({"windows": prepared.evidence_sha256, "tle": tle.digest,
                             "candidates": candidate_numbers}) == doc["evidence_sha256"]
    prior = RegionalPrior(**doc["configuration"]["prior"])
    bank, receipt = build_regional_bank(catalogue, indices, prepared.start_utc_ns,
                                       obs, prior, maximum_seconds=60)
    assert list(receipt.retained_numbers) == saved["bank"]["retained_numbers"]
    checkpoint = RegionalCheckpointStore(Path("/srv/bulk/leo"), session_id, saved["checkpoint_binding"])
    prefix = canonical_digest(doc["configuration"]["run"])
    methods = {method["name"]: sorted({arm["selected"]["source_basin"] for arm in method["arms"]
                                      if arm["selected"]}) for method in doc["methods"]}
    point = reference_point(prior, doc["reference_latitude_deg"], doc["reference_longitude_deg"])
    np.testing.assert_allclose(coordinates(prior, point), [doc["reference_latitude_deg"], doc["reference_longitude_deg"]], atol=1e-9, rtol=0)
    result = dict(case=case, session_id=session_id, source_snapshot=str(snapshot_path.relative_to(HERE.parent)),
                  source_snapshot_sha256=digest(snapshot_raw), regional_document_sha256=capture["regional_document_sha256"],
                  configuration_sha256=doc["configuration_sha256"], evidence_sha256=doc["evidence_sha256"],
                  input_manifest_sha256=source.input_manifest_sha256, analysis_manifest_sha256=source.analysis_manifest_sha256,
                  observation_evidence_sha256=prepared.evidence_sha256, observation_count=len(obs.window_ids),
                  start_utc_ns=prepared.start_utc_ns, capture_start_utc=capture.get("capture_start_utc"),
                  prior=asdict(prior), scores=doc["configuration"]["scores"], methods=methods,
                  source_digests=doc["configuration"]["source_digests"],
                  tle_snapshot_sha256=tle.digest, tle_snapshot_collected_utc_ns=tle.collected_utc_ns,
                  candidate_numbers=candidate_numbers, bank_receipt=asdict(receipt), basins={},
                  evaluation_reference=dict(latitude_deg=doc["reference_latitude_deg"], longitude_deg=doc["reference_longitude_deg"],
                                            point_km=point.tolist()), published_selected={}, repricing=[])
    for method in doc["methods"]:
        result["published_selected"][method["name"]] = {arm["name"]: arm["selected"] for arm in method["arms"]}
    for basin_index, basin in enumerate(sorted({b for group in methods.values() for b in group})):
        association_value = checkpoint.get(prefix + ":" + basin + ":association")
        calibration_value = checkpoint.get(prefix + ":" + basin + ":calibration")
        assert association_value and association_value["result"]
        assert calibration_value and calibration_value["result"]
        association, calibration = association_value["result"], calibration_value["result"]
        subset = bank.select(association["selected_indices"])
        baseline = np.asarray(calibration["receiver_baseline_hz"])
        initial = np.asarray(association["initial_vector"])
        correction = calibration["correction"]
        post = calibration["postfit"]["vector"]
        knots = np.asarray(correction["knots_hz"])
        penalty = float(.5 * (np.sum(knots**2) / 50**2 + np.sum(np.diff(knots, n=2, axis=1)**2) / 25**2))
        arrays = {"obs_" + field: np.asarray(getattr(obs, field)) for field in OBSERVATION_FIELDS}
        arrays.update({"bank_" + field: np.asarray(getattr(subset, field)) for field in BANK_FIELDS})
        arrays.update(receiver_baseline_hz=baseline, correction_nodes_s=np.asarray(correction["nodes_s"]),
                      correction_knots_hz=knots, correction_values_hz=np.asarray(correction["values_hz"]))
        target = HERE / "inputs" / f"{case}_basin{basin_index}.npz"
        if target.exists():
            with np.load(target, allow_pickle=False) as existing:
                assert set(existing.files) == set(arrays)
                for key, value in arrays.items():
                    np.testing.assert_array_equal(existing[key], value)
        else:
            np.savez_compressed(target, **arrays)
        result["basins"][basin] = dict(file=str(target.relative_to(HERE)), sha256=digest(target.read_bytes()),
            initial_vector=initial.tolist(), center_km=initial[:2].tolist(), local_radius_km=25.,
            calibration_penalty=penalty, calibration_vector=post,
            calibration_fields=dict(b0_hz_s=post[3], b1_hz_s=post[5], differential_hz_s=post[5] - post[3],
                                    nonlinear_correction_min_hz=float(np.min(arrays["correction_values_hz"])),
                                    nonlinear_correction_max_hz=float(np.max(arrays["correction_values_hz"])),
                                    nonlinear_correction_rms_hz=float(np.sqrt(np.mean(arrays["correction_values_hz"]**2)))),
            association_checkpoint_sha256=canonical_digest(association_value),
            calibration_checkpoint_sha256=canonical_digest(calibration_value), selected_numbers=subset.numbers.tolist())
        for row in saved["final_starts"]:
            if row["basin"] != basin or not row["fit"]:
                continue
            if "satellites" in row:
                np.testing.assert_array_equal(row["satellites"], subset.numbers)
            np.testing.assert_allclose(row["calibration_penalty"], penalty, atol=1e-10, rtol=0)
            objective = PositionObjective(obs, subset, prior, PositionScore(**result["scores"][row["method"]]),
                                          receiver_baseline_hz=baseline)
            fit = row["fit"]
            value, _, terms = objective.evaluate(np.asarray(fit["vector"]))
            mass = float(terms.responsibilities.sum())
            rms = float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass))
            np.testing.assert_allclose(value, fit["objective"], rtol=0, atol=1e-7)
            np.testing.assert_allclose(rms, fit["posterior_rms_hz"], rtol=0, atol=1e-7)
            result["repricing"].append(dict(basin=basin, method=row["method"], arm=row["arm"], start=row["start"],
                                            objective=value, published_objective=fit["objective"],
                                            objective_difference=value-fit["objective"], data_nll=terms.nll,
                                            posterior_rms_hz=rms, published_posterior_rms_hz=fit["posterior_rms_hz"]))
        print(case, basin, len(subset.numbers), "frozen/repriced", flush=True)
    return result


def main():
    destination = HERE / "inputs" / "manifest.json"
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(exist_ok=True)
    result = dict(protocol_sha256=digest(Path(__file__).read_bytes()),
                  definition="Original observations, frozen TLE/candidates, method-specific winning-basin union, calibration/association checkpoints; no fits during preparation.",
                  seeds=["association initial_vector", "association initial_vector with vector[7:]=0"],
                  local_radius_km=25., reference_usage="evaluation-only", cases=[])
    for case in CASES:
        result["cases"].append(prepare_case(*case))
    with destination.open("x") as output:
        json.dump(result, output, indent=2, default=encode, allow_nan=False)
        output.write("\n")
    print("Wrote", destination, flush=True)


if __name__ == "__main__":
    main()
