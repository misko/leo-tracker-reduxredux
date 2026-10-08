"""Prepare isolated standard baselines and run the frozen candidate on remaining members."""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path[:0] = [str(REPORTS / f"2026_10_08_position_error_iter{n}") for n in ("20", "28")]
# isort: off
from newer import additional_region  # noqa: E402
from extension import extend_pipeline  # noqa: E402
from pipeline import run_pipeline  # noqa: E402
from inputs import Case, write_json  # noqa: E402
import numpy as np  # noqa: E402
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris  # noqa: E402
from leo.analysis.regional_position_bank import build_regional_bank  # noqa: E402
from leo.application.regional_position_inputs import prepare_position_windows  # noqa: E402
from leo.cli.regional_position import configuration, run_regional_position_analysis  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.contracts.regional_position import RegionalPrior  # noqa: E402
from leo.operations.tle_archive import TleArchiveReader  # noqa: E402
from leo.sky.propagation import parse_element_sets  # noqa: E402
from leo.storage.adaptive_hop import AdaptiveHopIqStore  # noqa: E402
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore  # noqa: E402
from leo.storage.regional_position_v2 import Hard60Store  # noqa: E402
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore  # noqa: E402
# isort: on

ROOT = Path("/srv/bulk/leo")


def load_case(document, checkpoint_root):
    inputs = ScannerTrackingInputStore(ROOT)
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
            checkpoint_root, document["session_id"], document["diagnostics"]["checkpoint_binding"]
        ),
        canonical_digest(document["configuration"]["run"]),
    )


def run(label):
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS.parent / name).read_bytes()).hexdigest() == digest, name
    member = next(m for m in protocol["members"] if m["inventory_label"] == label)
    path = HERE / "results" / f"{label}.json"
    if path.exists():
        raise FileExistsError(path)
    try:
        store = AdaptiveHopIqStore(ROOT, read_only=True)
        try:
            publication = store.inspect(member["session_id"])
            assert publication.manifest.uncompressed_sha256 == member["uncompressed_sha256"]
            if member["recording_manifest_sha256"]:
                assert publication.manifest_sha256 == member["recording_manifest_sha256"]
            input_digest = publication.manifest_sha256
        finally:
            store.close()
        assert canonical_digest(configuration()) == protocol["baseline_configuration"]
        checkpoint_root = ROOT
        live = Hard60Store(ROOT).status(member["session_id"]).manifest
        if live is not None and live.document.configuration_sha256 == canonical_digest(
            configuration()
        ):
            document = live.document.model_dump(mode="json")
            baseline_mode = "compatible_publication"
        else:
            checkpoint_root = Path(protocol["isolated_output_root"])
            progress = []
            for _ in range(4):
                receipt = run_regional_position_analysis(
                    ROOT,
                    Path("/var/lib/leo/tle"),
                    member["session_id"],
                    output_root=checkpoint_root,
                    maximum_seconds=500,
                )
                progress.append(receipt)
                write_json(HERE / "progress" / f"{label}.json", progress)
                print(label, "baseline", receipt, flush=True)
                if receipt["state"] == "complete":
                    break
            else:
                write_json(
                    HERE / "pending" / f"{label}.json",
                    dict(member=member, reason="four bounded baseline slices exhausted"),
                )
                return
            document = (
                Hard60Store(checkpoint_root)
                .status(member["session_id"])
                .manifest.document.model_dump(mode="json")
            )
            baseline_mode = "isolated_standard_baseline"
        assert document["input_manifest_sha256"] == input_digest
        assert document["configuration_sha256"] == protocol["baseline_configuration"]
        write_json(HERE / "baselines" / f"{label}.json", document)
        case = load_case(document, checkpoint_root)
        additional, receipt = additional_region(case, label)
        write_json(HERE / "regions" / f"{label}.json", additional)
        upstream = run_pipeline(case, document, additional)
        extension = extend_pipeline(case, document, additional, upstream)
        for stage in (*upstream["stages"].values(), *extension["stages"].values()):
            zero = stage["zero-c"]
            if "vector" in zero:
                assert zero["vector"][6] == 0
                assert all(v == 0 for v in zero.get("rf_drift_coefficients", []))
        output = dict(
            status="complete",
            member=member,
            baseline_mode=baseline_mode,
            upstream=upstream,
            extension=extension,
            regional_receipt=receipt,
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
        )
    except Exception as error:
        write_json(path, dict(status="failed", member=member, error=repr(error)))
        print(label, "FAILED", repr(error), flush=True)
        return
    write_json(path, output)
    print(label, {a: r["error_km"] for a, r in extension["operational"].items()}, flush=True)


if __name__ == "__main__":
    for label in sys.argv[1:]:
        run(label)
