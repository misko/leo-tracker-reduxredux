"""Pinned DS16 inputs and isolated experiment cache through public storage ports."""

import json
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path

import numpy as np

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
ROOT = Path("/srv/bulk/leo")


def json_value(value):
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(json_value(value), indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


@dataclass
class Case:
    document: dict
    prepared: object
    bank: object
    prior: RegionalPrior
    checkpoints: RegionalCheckpointStore
    checkpoint_prefix: str

    def checkpoint(self, key):
        receipt = self.checkpoints.get(self.checkpoint_prefix + ":" + key)
        if receipt is None:
            raise KeyError(f"Missing pinned baseline stage: {key}")
        return receipt


def load_case(label):
    frozen = json.loads((HERE / "frozen-inputs.json").read_text())[label]
    document = (
        Hard60Store(ROOT).status(frozen["session_id"]).manifest.document.model_dump(mode="json")
    )
    assert canonical_digest(document) == frozen["baseline_document_digest"]
    inputs = ScannerTrackingInputStore(ROOT)
    try:
        source = inputs.load(document["session_id"])
    finally:
        inputs.close()
    assert source.input_manifest_sha256 == document["input_manifest_sha256"]
    assert source.analysis_manifest_sha256 == document["analysis_manifest_sha256"]
    prepared = prepare_position_windows(source)
    assert len(prepared.observations.window_ids) == document["windows"]
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
    assert snapshot.digest == document["diagnostics"]["snapshot_sha256"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = np.array(
        [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")],
        dtype=int,
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


class ExperimentCheckpoints:
    """Isolated report cache; never writes baseline or published production products."""

    def __init__(self, directory, binding):
        self.directory = Path(directory)
        self.binding = canonical_digest(binding)

    def path(self, key):
        return self.directory / (canonical_digest({"key": key})[7:] + ".json")

    def get(self, key):
        path = self.path(key)
        if not path.exists():
            return None
        receipt = json.loads(path.read_text())
        assert receipt["key"] == key and receipt["binding"] == self.binding
        assert canonical_digest(receipt["value"]) == receipt["value_sha256"]
        return receipt["value"]

    def put(self, key, value):
        value = json_value(value)
        old = self.get(key)
        if old is not None:
            assert old == value, "Immutable experiment checkpoint conflict"
            return
        write_json(
            self.path(key),
            {
                "key": key,
                "binding": self.binding,
                "value": value,
                "value_sha256": canonical_digest(value),
            },
        )
