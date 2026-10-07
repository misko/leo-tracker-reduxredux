"""Verify all experiment inputs against published receipts; no orbit fitting."""

import hashlib
import inspect
import json
import time
from pathlib import Path

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.application.regional_position_inputs import prepare_position_windows
from leo.storage.regional_position import RegionalPositionStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

HERE = Path(__file__).resolve().parent
SESSIONS = ("scan-fw-6bf407cfe8158445", "scan-fw-559a822227a6a71b", "scan-fw-ffe5accf2d020263")


def main():
    begun = time.monotonic()
    root = Path("/srv/bulk/leo")
    store = RegionalPositionStore(root)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = archive.list_snapshots()
    rows = []
    for session in SESSIONS:
        doc = store.status(session).manifest.document.model_dump(mode="json")
        source_store = ScannerTrackingInputStore(root)
        try:
            source = source_store.load(session)
        finally:
            source_store.close()
        assert source.input_manifest_sha256 == doc["input_manifest_sha256"], session
        assert source.analysis_manifest_sha256 == doc["analysis_manifest_sha256"], session
        prepared = prepare_position_windows(source)
        assert len(prepared.observations.window_ids) == doc["windows"], session
        snapshot = next(s for s in snapshots if s.digest == doc["diagnostics"]["snapshot_sha256"])
        assert snapshot.collected_utc_ns == doc["diagnostics"]["snapshot_collected_utc_ns"], session
        assert snapshot.collected_utc_ns < prepared.start_utc_ns - 505_000_000_000, session
        payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
        catalogue = parse_element_sets(payload)
        candidates = [
            int(number)
            for name, number in zip(catalogue.names, catalogue.satellite_numbers, strict=True)
            if name.upper().startswith("STARLINK")
        ]
        evidence = canonical_digest(
            dict(windows=prepared.evidence_sha256, tle=snapshot.digest, candidates=candidates)
        )
        assert evidence == doc["evidence_sha256"], session
        config = doc["configuration"]
        assert canonical_digest(config) == doc["configuration_sha256"], session
        binding = canonical_digest(
            dict(
                input=source.input_manifest_sha256,
                analysis=source.analysis_manifest_sha256,
                evidence=evidence,
                configuration=config,
            )
        )
        assert binding == doc["diagnostics"]["checkpoint_binding"], session
        rows.append(
            dict(
                session=session,
                verified=True,
                input_manifest_sha256=source.input_manifest_sha256,
                analysis_manifest_sha256=source.analysis_manifest_sha256,
                prepared_window_evidence_sha256=prepared.evidence_sha256,
                evidence_sha256=evidence,
                configuration_sha256=doc["configuration_sha256"],
                snapshot_sha256=snapshot.digest,
                snapshot_collected_utc_ns=snapshot.collected_utc_ns,
                checkpoint_binding=binding,
                window_count=len(prepared.observations.window_ids),
                candidate_count=len(candidates),
                candidate_inventory_sha256=canonical_digest(candidates),
                window_ids_sha256=hashlib.sha256(
                    "\n".join(prepared.observations.window_ids).encode()
                ).hexdigest(),
            )
        )
    cli_source = (
        Path(inspect.getfile(prepare_position_windows)).parent.parent / "cli/regional_position.py"
    )
    sources = [
        Path(__file__),
        cli_source,
        Path(inspect.getfile(prepare_position_windows)),
        Path(inspect.getfile(exclude_labelled_starlink_debris)),
    ]
    result = dict(
        verified=True,
        elapsed_s=time.monotonic() - begun,
        cases=rows,
        source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        scope=(
            "Published capture/analysis, exact original archived snapshot, full filtered STARLINK "
            "candidate order, window evidence, configuration and checkpoint binding; "
            "no orbit propagation or fitting."
        ),
    )
    (HERE / "verification.json").write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            dict(
                verified=True,
                elapsed_s=result["elapsed_s"],
                cases=[
                    dict(
                        session=r["session"],
                        windows=r["window_count"],
                        candidates=r["candidate_count"],
                    )
                    for r in rows
                ],
            )
        )
    )


if __name__ == "__main__":
    main()
