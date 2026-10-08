"""Evaluate frozen newer whole-scan groups through public input/checkpoint ports."""

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

# Bootstrap the frozen report module paths before importing their modules.
# isort: off
from pipeline import REPORTS, run_pipeline

import numpy as np
from inputs import Case, ExperimentCheckpoints, json_value, write_json
from regions import ReplayCheckpoints

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.regional_position_bank import build_regional_bank
from leo.application.hard60_runner import Hard60Configuration, run_hard60
from leo.application.regional_position_inputs import prepare_position_windows
from leo.application.regional_position_report import regional_position_document
from leo.application.regional_position_runner import RegionalSliceExpired
from leo.cli.regional_position import configuration
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
# isort: on

HERE = Path(__file__).resolve().parent


def load_member(member):
    root = Path("/srv/bulk/leo")
    manifest = Hard60Store(root).status(member["session_id"]).manifest
    if manifest is None:
        raise ValueError("Frozen member has no published baseline; retain as unavailable")
    document = manifest.document.model_dump(mode="json")
    assert document["configuration"]["run"] == json_value(Hard60Configuration())
    assert document["input_manifest_sha256"] == member["recording_manifest_sha256"]
    inputs = ScannerTrackingInputStore(root)
    try:
        source = inputs.load(document["session_id"])
    finally:
        inputs.close()
    assert source.input_manifest_sha256 == document["input_manifest_sha256"]
    assert source.analysis_manifest_sha256 == document["analysis_manifest_sha256"]
    prepared = prepare_position_windows(source)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
    assert snapshot.digest == document["diagnostics"]["snapshot_sha256"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = np.array(
        [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
    )
    prior = RegionalPrior()
    bank, receipt = build_regional_bank(
        catalogue, indices, prepared.start_utc_ns, prepared.observations, prior, maximum_seconds=180
    )
    assert list(receipt.retained_numbers) == document["diagnostics"]["bank"]["retained_numbers"]
    return Case(
        document,
        prepared,
        bank,
        prior,
        RegionalCheckpointStore(
            root, document["session_id"], document["diagnostics"]["checkpoint_binding"]
        ),
        canonical_digest(document["configuration"]["run"]),
    )


def additional_region(case, label):
    original = case.document
    config = replace(Hard60Configuration(), basin_separation_km=25)
    prefix = canonical_digest(json_value(config)) + ":"
    cache = ExperimentCheckpoints(
        HERE / "checkpoints" / label,
        dict(original=canonical_digest(original), config=json_value(config)),
    )
    borrowed = set()
    result = None
    for _ in range(4):
        try:
            result = run_hard60(
                case.prepared.observations,
                case.bank,
                case.prior,
                case.prepared.bootstrap_tracks,
                ReplayCheckpoints(case, cache, prefix, borrowed),
                configuration=config,
                maximum_seconds=500,
            )
            break
        except RegionalSliceExpired as error:
            print(label, "checkpointed slice", str(error), flush=True)
    if result is None:
        raise TimeoutError("Four bounded offline regional slices exhausted")
    doc_config = configuration()
    doc_config["run"] = json_value(config)
    document = regional_position_document(
        result,
        session_id=original["session_id"],
        input_digest=original["input_manifest_sha256"],
        analysis_digest=original["analysis_manifest_sha256"],
        evidence_digest=original["evidence_sha256"],
        configuration=doc_config,
        windows=original["windows"],
        reference=(original["reference_latitude_deg"], original["reference_longitude_deg"]),
        reference_evidence="Existing reference applied after inference only",
        diagnostics={k: original["diagnostics"][k] for k in ("bank", "snapshot_sha256")},
    ).model_dump(mode="json")

    def coordinates(doc):
        return [
            (p["east_km"], p["north_km"], p["spacing_km"])
            for p in doc["methods"][0]["points"]
        ]

    assert coordinates(document) == coordinates(original)
    receipt = dict(
        identical_grid=True,
        point_count=len(coordinates(document)),
        borrowed_stages=sorted(borrowed),
        source_document_sha256=canonical_digest(original),
        candidate_document_sha256=canonical_digest(document),
    )
    return document, receipt


def run(label):
    protocol = json.loads((HERE / "validation-protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    member = next(row for row in protocol["members"] if row["label"] == label)
    if member["evaluation_group"] != "development":
        # Require both implementation-qualification cases, without selecting by their errors.
        for development in protocol["development_labels"]:
            row = json.loads((HERE / "results" / f"{development}.json").read_text())
            assert row["status"] == "complete", "Resolve development execution before holdout"
    path = HERE / "results" / f"{label}.json"
    if path.exists():
        raise FileExistsError(f"Preserve immutable first result: {path}")
    try:
        case = load_member(member)
        write_json(HERE / "baselines" / f"{label}.json", case.document)
        additional, receipt = additional_region(case, label)
        write_json(HERE / "regions" / f"{label}.json", additional)
        result = run_pipeline(case, case.document, additional)
        # A strict RF ablation must not restore the RF interaction under another name.
        for rows in result["stages"].values():
            zero = rows["zero-c"]
            assert zero["vector"][6] == 0.0
            assert all(value == 0 for value in zero.get("rf_drift_coefficients", []))
        output = dict(
            status="complete", member=member, result=result, regional_receipt=receipt,
            protocol_sha256=hashlib.sha256(
                (HERE / "validation-protocol.json").read_bytes()
            ).hexdigest(),
        )
    except Exception as error:
        write_json(path, dict(status="failed", member=member, error=repr(error)))
        raise
    write_json(path, output)
    errors = {arm: row["error_km"] for arm, row in result["operational"].items()}
    print(label, json.dumps(errors), flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
