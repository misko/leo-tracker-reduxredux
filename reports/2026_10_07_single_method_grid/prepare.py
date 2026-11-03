"""Freeze original full-bank ports for a new discovery experiment."""
import json
from pathlib import Path
from dataclasses import asdict
import numpy as np
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.regional_position_inputs import prepare_position_windows
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.regional_position_bank import build_regional_bank
from leo.contracts.regional_position import RegionalPrior
from leo.contracts.digests import canonical_digest

HERE = Path(__file__).resolve().parent
SID = "scan-fw-e3bebc228093a125"

def main():
    snapshot = HERE.parent / "2026_10_07_recent_filter_review/snapshot.json"
    capture = next(c for c in json.loads(snapshot.read_text())["captures"] if c["session_id"] == SID)
    doc = capture["regional_document"]
    assert canonical_digest(doc) == capture["regional_document_sha256"]
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = store.load(SID)
    finally:
        store.close()
    assert source.input_manifest_sha256 == doc["input_manifest_sha256"]
    assert source.analysis_manifest_sha256 == doc["analysis_manifest_sha256"]
    prepared = prepare_position_windows(source)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    saved = doc["diagnostics"]
    tle = next(r for r in archive.list_snapshots() if r.digest == saved["snapshot_sha256"]
               and r.collected_utc_ns == saved["snapshot_collected_utc_ns"])
    payload, _ = exclude_labelled_starlink_debris(archive.read(tle))
    catalogue = parse_element_sets(payload)
    indices = np.array([i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")])
    assert canonical_digest(dict(windows=prepared.evidence_sha256, tle=tle.digest,
        candidates=[int(catalogue.satellite_numbers[i]) for i in indices])) == doc["evidence_sha256"]
    prior = RegionalPrior(**doc["configuration"]["prior"])
    bank, receipt = build_regional_bank(catalogue, indices, prepared.start_utc_ns,
                                       prepared.observations, prior, maximum_seconds=60)
    assert list(receipt.retained_numbers) == saved["bank"]["retained_numbers"]
    arrays = {"obs_" + name: np.asarray(getattr(prepared.observations, name)) for name in
        ("window_ids", "times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin")}
    arrays.update({"bank_" + name: getattr(bank, name) for name in
        ("numbers", "nodes_s", "position_km", "velocity_km_s")})
    destination = HERE / "inputs.npz"
    if destination.exists():
        raise FileExistsError(destination)
    np.savez_compressed(destination, **arrays)
    import hashlib
    result = dict(session_id=SID, prior=asdict(prior), scores=doc["configuration"]["scores"],
        bootstrap_tracks=prepared.bootstrap_tracks, observation_count=len(prepared.observations.window_ids),
        bank_count=len(bank.numbers), input_manifest_sha256=source.input_manifest_sha256,
        analysis_manifest_sha256=source.analysis_manifest_sha256, evidence_sha256=doc["evidence_sha256"],
        observation_evidence_sha256=prepared.evidence_sha256, tle_sha256=tle.digest,
        inputs_sha256="sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest(),
        checkpoint_binding=saved["checkpoint_binding"], checkpoint_prefix=canonical_digest(doc["configuration"]["run"]),
        source_digests=doc["configuration"]["source_digests"])
    (HERE / "inputs.json").write_text(json.dumps(result, indent=2) + "\n")
    # The inference input file contains no reference location or saved finalist.
    (HERE / "evaluation.json").write_text(json.dumps(dict(
        latitude_deg=doc["reference_latitude_deg"], longitude_deg=doc["reference_longitude_deg"]), indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("session_id", "observation_count", "bank_count", "inputs_sha256")}))

if __name__ == "__main__":
    main()
