"""Run or resume automatic Hard60 analysis from saved GLRT products."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.regional_position_bank import build_regional_bank
from leo.application.hard60_runner import HARD60_SCORE, Hard60Configuration, run_hard60
from leo.application.regional_position_inputs import (
    PositionInputUnavailable,
    prepare_position_windows,
)
from leo.application.regional_position_report import regional_position_document
from leo.application.regional_position_runner import (
    RegionalSliceExpired,
    json_value,
)
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.regional_position import render_regional_position
from leo.sky.propagation import parse_element_sets
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

REFERENCE = (37.84903264307456, -122.4856541910174)


def configuration():
    package = Path(__file__).resolve().parents[1]
    paths = sorted(package.glob("analysis/regional_position*.py"))
    paths += sorted(package.glob("analysis/t1_at*.py"))
    paths += sorted(package.glob("application/regional_position*.py"))
    paths += [package / "contracts/regional_position.py"]
    paths += sorted(package.glob("analysis/hard60*.py"))
    paths += [
        package / "analysis/_regional_orbits.cpp",
        package / "application/hard60_runner.py",
        package / "contracts/regional_position_v2.py",
    ]
    return {
        "protocol": "sacramento-hard60-v1",
        "run": json_value(Hard60Configuration()),
        "scores": {"V16": json_value(HARD60_SCORE)},
        "slope_scope": "each-stage-added-affine-slope-not-total-receiver-drift",
        "selection": "stationary-only-model-score-no-reference",
        "prior": json_value(RegionalPrior()),
        "refinement": "off",
        "rf_ablation_scope": "final-score-shared-fitted-c-calibration-and-association",
        "source_digests": {
            str(path.relative_to(package)): sha256_digest(path.read_bytes()) for path in paths
        },
    }


def regional_position_complete(root, session_id, *, expected_input=None, expected_analysis=None):
    store = Hard60Store(root)
    status = store.status(session_id)
    if status.manifest is None:
        return False
    doc = status.manifest.document
    return (
        doc.configuration_sha256 == canonical_digest(configuration())
        and (expected_input is None or doc.input_manifest_sha256 == expected_input)
        and (expected_analysis is None or doc.analysis_manifest_sha256 == expected_analysis)
        and store.artifact(session_id, "V16") is not None
    )


def run_regional_position_analysis(
    root, tle_root, session_id, *, output_root=None, maximum_seconds=500.0
):
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800:
        raise ValueError("invalid regional worker time budget")
    begun = time.monotonic()
    destination = output_root or root
    store = Hard60Store(destination, read_only=False)
    inputs = ScannerTrackingInputStore(root)
    try:
        source = inputs.load(session_id)
    finally:
        inputs.close()
    config = configuration()
    if regional_position_complete(
        destination,
        session_id,
        expected_input=source.input_manifest_sha256,
        expected_analysis=source.analysis_manifest_sha256,
    ):
        return {"session_id": session_id, "state": "complete"}
    if store.status(session_id).manifest is not None:
        raise ValueError("regional position publication has different configuration or inputs")
    diagnostics = {}
    try:
        prepared = prepare_position_windows(source)
    except PositionInputUnavailable as error:
        windows = 0
        evidence = canonical_digest(
            {
                "input": source.input_manifest_sha256,
                "analysis": source.analysis_manifest_sha256,
                "reason": str(error),
            }
        )
        result = {
            "searches": {
                name: {"evaluations": [], "deferred_cells": 0, "stop_reason": "insufficient-input"}
                for name in ("V16",)
            },
            "points": {},
            "finals": [],
            "failures": [{"reason": str(error)}],
        }
    else:
        windows = len(prepared.observations.window_ids)
        archive = TleArchiveReader(tle_root)
        cutoff = prepared.start_utc_ns - 505_000_000_000
        snapshot = archive.select_latest_before(cutoff)
        if snapshot.collected_utc_ns >= cutoff:
            raise ValueError("regional TLE snapshot is not strictly causal")
        payload, exclusions = exclude_labelled_starlink_debris(archive.read(snapshot))
        catalogue = parse_element_sets(payload)
        indices = np.array(
            [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")],
            dtype=int,
        )
        evidence = canonical_digest(
            {
                "windows": prepared.evidence_sha256,
                "tle": snapshot.digest,
                "candidates": [int(catalogue.satellite_numbers[i]) for i in indices],
            }
        )
        binding = canonical_digest(
            {
                "input": source.input_manifest_sha256,
                "analysis": source.analysis_manifest_sha256,
                "evidence": evidence,
                "configuration": config,
            }
        )
        remaining = maximum_seconds - (time.monotonic() - begun)
        if remaining <= 30:
            return {"session_id": session_id, "state": "pending", "phase": "bank"}
        bank, receipt = build_regional_bank(
            catalogue,
            indices,
            prepared.start_utc_ns,
            prepared.observations,
            RegionalPrior(),
            maximum_seconds=min(180, remaining - 15),
        )
        diagnostics = {
            "bank": json_value(receipt),
            "snapshot_sha256": snapshot.digest,
            "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
            "catalogue_exclusions": json_value(exclusions),
            "checkpoint_binding": binding,
        }
        checkpoints = RegionalCheckpointStore(destination, session_id, binding)
        try:
            with checkpoints.writer():
                result = run_hard60(
                    prepared.observations,
                    bank,
                    RegionalPrior(),
                    prepared.bootstrap_tracks,
                    checkpoints,
                    maximum_seconds=max(0.001, maximum_seconds - (time.monotonic() - begun) - 5),
                )
        except RegionalSliceExpired as error:
            return {"session_id": session_id, "state": "pending", "phase": str(error)}
    document = regional_position_document(
        result,
        session_id=session_id,
        input_digest=source.input_manifest_sha256,
        analysis_digest=source.analysis_manifest_sha256,
        evidence_digest=evidence,
        configuration=config,
        windows=windows,
        reference=REFERENCE,
        reference_evidence="Configured baseline receiver reference; evaluation only",
        diagnostics=diagnostics,
    )
    store.publish(document, {"V16": render_regional_position(document, "V16")})
    return {"session_id": session_id, "state": "complete"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--maximum-seconds", type=float, default=500)
    parser.add_argument("session_id")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run_regional_position_analysis(
                args.bulk_root,
                args.tle_root,
                args.session_id,
                output_root=args.output_root,
                maximum_seconds=args.maximum_seconds,
            )
        )
    )


if __name__ == "__main__":
    main()
