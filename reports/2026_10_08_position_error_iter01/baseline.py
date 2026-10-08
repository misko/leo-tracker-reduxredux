"""DS17 baseline recovery, preserving verified existing numerical checkpoints."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026_10_08_hard60_bounded_recovery"))
from inputs import Case, ExperimentCheckpoints, write_json  # noqa: E402

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris  # noqa: E402
from leo.analysis.regional_position_bank import build_regional_bank  # noqa: E402
from leo.application.hard60_runner import run_hard60  # noqa: E402
from leo.application.regional_position_inputs import prepare_position_windows  # noqa: E402
from leo.application.regional_position_report import regional_position_document  # noqa: E402
from leo.cli.regional_position import configuration  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.contracts.regional_position import RegionalPrior  # noqa: E402
from leo.operations.tle_archive import TleArchiveReader  # noqa: E402
from leo.sky.propagation import parse_element_sets  # noqa: E402
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore  # noqa: E402
from leo.storage.regional_position_v2 import Hard60Store  # noqa: E402
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore  # noqa: E402

ROOT = Path("/srv/bulk/leo")


def protocol():
    from freeze import digest

    assert digest(HERE / "protocol.json") == (HERE / "protocol.sha256").read_text().strip()
    return json.loads((HERE / "protocol.json").read_text())


def original(label):
    row = next(r for r in protocol()["membership"] if r["label"] == label)
    path = HERE / "published" / f"{label}.json"
    if path.exists():
        return json.loads(path.read_text())
    status = Hard60Store(ROOT).status(row["session_id"])
    if status.manifest is None:
        raise ValueError(f"Baseline publication pending: {label}")
    document = status.manifest.document.model_dump(mode="json")
    member = next(
        r
        for r in json.loads((HERE / "ds17-manifest.json").read_text())["captures"]
        if r["session_id"] == row["session_id"]
    )
    assert document["input_manifest_sha256"] == member["recording_manifest_sha256"]
    assert document["configuration"]["run"].get("recovery_policy") in (None, "failed-coarse-box-v1")
    write_json(path, document)
    return document


def load_case(label):
    document = original(label)
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
        [i for i, n in enumerate(catalogue.names) if n.upper().startswith("STARLINK")]
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
            ROOT, document["session_id"], document["diagnostics"]["checkpoint_binding"]
        ),
        canonical_digest(document["configuration"]["run"]),
    )


def run(label):
    output = HERE / "baseline" / f"{label}.json"
    config = configuration()
    assert canonical_digest(config) == protocol()["baseline_configuration"]
    if output.exists():
        return
    doc = original(label)
    if doc["configuration_sha256"] == canonical_digest(config):
        write_json(output, doc)
        print(label, "current published baseline", flush=True)
        return
    case = load_case(label)
    prefix = canonical_digest(config["run"]) + ":"
    added = ExperimentCheckpoints(
        HERE / "checkpoints" / label,
        {
            "configuration": config,
            "baseline_document_digest": canonical_digest(doc),
        },
    )

    class Checkpoints:
        def get(self, key):
            assert key.startswith(prefix)
            stage = key.removeprefix(prefix)
            return added.get(key) if stage.startswith("recovery:") else case.checkpoint(stage)

        def put(self, key, value):
            assert key.removeprefix(prefix).startswith("recovery:")
            added.put(key, value)

    result = run_hard60(
        case.prepared.observations,
        case.bank,
        case.prior,
        case.prepared.bootstrap_tracks,
        Checkpoints(),
        maximum_seconds=1800,
    )
    document = regional_position_document(
        result,
        session_id=doc["session_id"],
        input_digest=doc["input_manifest_sha256"],
        analysis_digest=doc["analysis_manifest_sha256"],
        evidence_digest=doc["evidence_sha256"],
        configuration=config,
        windows=doc["windows"],
        reference=(doc["reference_latitude_deg"], doc["reference_longitude_deg"]),
        reference_evidence="Frozen existing evaluation reference; applied after selection",
        diagnostics={k: doc["diagnostics"][k] for k in ("bank", "snapshot_sha256")},
    )
    write_json(output, document.model_dump(mode="json"))
    print(label, "baseline complete", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("labels", nargs="+")
    for label in parser.parse_args().labels:
        run(label)
