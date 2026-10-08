"""Read frozen newer recordings and existing baselines through public ports."""

import json
from pathlib import Path

import numpy as np
from inputs import Case

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.regional_position_bank import build_regional_bank
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

HERE = Path(__file__).resolve().parent


def load_newer(label):
    frozen = json.loads(
        (HERE.parent / "2026_10_08_position_error_iter05/newer-recordings.json").read_text()
    )
    index = int(label.removeprefix("NEW-")) - 1
    assert label == f"NEW-{index + 1:03d}" and 0 <= index < len(frozen["captures"])
    member = frozen["captures"][index]
    root = Path("/srv/bulk/leo")
    manifest = Hard60Store(root).status(member["session_id"]).manifest
    if manifest is None:
        raise ValueError("Frozen newer baseline not published yet")
    doc = manifest.document.model_dump(mode="json")
    assert doc["configuration"]["run"]["recovery_policy"] == "failed-coarse-box-v1"
    assert doc["configuration"]["run"]["basin_separation_km"] == 12.5
    assert doc["input_manifest_sha256"] == member["recording_manifest_sha256"]
    inputs = ScannerTrackingInputStore(root)
    try:
        source = inputs.load(doc["session_id"])
    finally:
        inputs.close()
    assert source.input_manifest_sha256 == doc["input_manifest_sha256"]
    assert source.analysis_manifest_sha256 == doc["analysis_manifest_sha256"]
    prepared = prepare_position_windows(source)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
    assert snapshot.digest == doc["diagnostics"]["snapshot_sha256"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = np.array(
        [i for i, n in enumerate(catalogue.names) if n.upper().startswith("STARLINK")]
    )
    prior = RegionalPrior()
    bank, receipt = build_regional_bank(
        catalogue, indices, prepared.start_utc_ns, prepared.observations, prior, maximum_seconds=180
    )
    assert list(receipt.retained_numbers) == doc["diagnostics"]["bank"]["retained_numbers"]
    return Case(
        doc,
        prepared,
        bank,
        prior,
        RegionalCheckpointStore(root, doc["session_id"], doc["diagnostics"]["checkpoint_binding"]),
        canonical_digest(doc["configuration"]["run"]),
    )
