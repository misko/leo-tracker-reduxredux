"""Read and verify ordinary failure receipts through the public checkpoint port."""

import datetime
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from leo.application.hard60_runner import Hard60Configuration
from leo.application.regional_position_runner import json_value
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    published = HERE / "published-v3.json"
    document = json.loads(published.read_text())["manifest"]["document"]
    failures = document["diagnostics"]["b7"]["regional_failures"]
    failed = {row["basin"] for row in failures["baseline"] if row["stage"] == "calibration"}
    retained = document["diagnostics"]["retained_basins"]
    candidates = [
        row for row in retained if f"point:{row['east_km']:g}:{row['north_km']:g}" in failed
    ]
    selected = min(candidates, key=lambda row: (row["score"], row["east_km"], row["north_km"]))
    key = f"point:{selected['east_km']:g}:{selected['north_km']:g}"
    binding = document["diagnostics"]["checkpoint_binding"]
    store = RegionalCheckpointStore(Path("/srv/bulk/leo"), document["session_id"], binding)
    keys = ["b7-shared:" + key]
    for separation in (12.5, 25.0, 50.0):
        config = replace(Hard60Configuration(), basin_separation_km=separation)
        keys.append(canonical_digest(json_value(config)) + ":" + key + ":calibration")
    checkpoints = {}
    for name in keys:
        value = store.get(name)
        assert value is not None, name
        checkpoints[name] = dict(value=value, value_sha256=canonical_digest(value))
    result = dict(
        extracted_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        session_id=document["session_id"],
        checkpoint_binding=binding,
        selection="Lowest ordinary score among retained baseline calibration-failure basins",
        selected_basin=selected,
        point_key=key,
        checkpoints=checkpoints,
        source_publication_sha256=hashlib.sha256(published.read_bytes()).hexdigest(),
        extractor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        port="RegionalCheckpointStore.get; binding/key/value digest/canonical encoding verified",
        command="sudo -n env PYTHONPATH=src:. /opt/leo-tracker/releases/"
        "47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python "
        "reports/2026_10_09_position_error_iter93/extract_checkpoints.py",
        scope="Read only: no put/writer, numerical fit, production mutation or reference selection",
    )
    with (HERE / "verified-checkpoints.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("Verified", len(checkpoints), "checkpoint receipts for", key)


if __name__ == "__main__":
    main()
