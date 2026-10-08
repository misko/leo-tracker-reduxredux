"""Audit published estimates with the original Python likelihood and KKT oracle."""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026_10_07_hard60_default"))
from audit_publication import audit  # noqa: E402

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris  # noqa: E402
from leo.analysis.regional_position_bank import build_regional_bank  # noqa: E402
from leo.analysis.regional_position_score import PositionObjective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402
from leo.application.regional_position_inputs import prepare_position_windows  # noqa: E402
from leo.cli.regional_position import configuration  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.contracts.regional_position import RegionalPrior  # noqa: E402
from leo.operations.tle_archive import TleArchiveReader  # noqa: E402
from leo.sky.propagation import parse_element_sets  # noqa: E402
from leo.storage.regional_position_v2 import Hard60Store  # noqa: E402
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore  # noqa: E402


def main(product_root, session, destination):
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=True)
    store = Hard60Store(Path(product_root))
    doc = store.status(session).manifest.document
    assert doc.configuration_sha256 == canonical_digest(configuration())
    assert doc.diagnostics["recovery"]["policy"] == "failed-coarse-box-v1"
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = inputs.load(session)
    finally:
        inputs.close()
    assert source.input_manifest_sha256 == doc.input_manifest_sha256
    assert source.analysis_manifest_sha256 == doc.analysis_manifest_sha256
    prepared = prepare_position_windows(source)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
    assert snapshot.digest == doc.diagnostics["snapshot_sha256"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = np.array(
        [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
    )
    bank, _ = build_regional_bank(
        catalogue,
        indices,
        prepared.start_utc_ns,
        prepared.observations,
        RegionalPrior(),
        maximum_seconds=180,
    )
    lookup = {int(number): i for i, number in enumerate(bank.numbers)}
    rows = []
    for arm in doc.methods[0].arms:
        selected = arm.selected
        assert selected and selected.converged
        fitted = next(
            row["fit"]
            for row in doc.diagnostics["final_starts"]
            if row["arm"] == arm.name
            and row["basin"] == selected.source_basin
            and row["fit"]
            and row["fit"]["converged"]
            and abs(row["fit"]["objective"] - selected.objective) < 1e-9
        )
        calibration = doc.diagnostics["calibrations"][selected.source_basin]
        objective = PositionObjective(
            prepared.observations,
            bank.select([lookup[n] for n in selected.satellites]),
            RegionalPrior(),
            HARD60_SCORE,
            receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
        )
        vector = np.asarray(fitted["vector"])
        value, gradient, terms = objective.evaluate(vector)
        np.testing.assert_allclose(value, fitted["objective"], rtol=0, atol=1e-6)
        candidates = (
            doc.diagnostics["retained_basins"] + doc.diagnostics["recovery"]["retained_basins"]
        )
        basin = next(
            b
            for b in candidates
            if f"point:{b['east_km']:g}:{b['north_km']:g}"
            == selected.source_basin.removeprefix("recovery:")
        )
        stationarity = audit(
            objective,
            vector,
            gradient,
            arm.name,
            [basin["east_km"], basin["north_km"]],
            max(25, basin["spacing_km"] / np.sqrt(2)),
        )
        rms = float(
            np.sqrt(
                np.sum(terms.responsibilities * terms.residual_hz**2) / terms.responsibilities.sum()
            )
        )
        np.testing.assert_allclose(rms, selected.posterior_rms_hz, rtol=0, atol=1e-6)
        rows.append(
            {
                "arm": arm.name,
                "objective_delta": value - selected.objective,
                "original_oracle_kkt": stationarity,
                "frequency_rms_hz": rms,
                "position_error_m": selected.horizontal_error_m,
                "final_added_slopes_hz_s": vector[[3, 5]].tolist(),
                "source_basin": selected.source_basin,
            }
        )
    receipt = {
        "session_id": session,
        "configuration_sha256": doc.configuration_sha256,
        "capture_start_utc_ns": prepared.start_utc_ns,
        "arms": rows,
        "recovery_attempted": doc.diagnostics["recovery"]["attempted_points"],
        "recovery_converged": doc.diagnostics["recovery"]["converged_points"],
    }
    (output / "audit.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (output / "document.json").write_text(doc.model_dump_json(indent=2) + "\n")
    (output / "V16.png").write_bytes(store.artifact(session, "V16"))
    print(json.dumps(receipt))


if __name__ == "__main__":
    main(*sys.argv[1:])
