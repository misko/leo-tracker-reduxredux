"""Preserve the original regional winner through verified public checkpoint reads."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from leo.application.hard60_runner import Hard60Configuration
from leo.application.regional_position_runner import json_value
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "2026_10_09_position_error_iter93"


def main():
    document = json.loads((PARENT / "published-v3.json").read_text())["manifest"]["document"]
    store = RegionalCheckpointStore(
        Path("/srv/bulk/leo"), document["session_id"], document["diagnostics"]["checkpoint_binding"]
    )
    config = Hard60Configuration()
    regions = {}
    for arm in document["methods"][0]["arms"]:
        source = document["diagnostics"]["b7"]["regional_sources"][arm["name"]]
        basin = arm["selected"]["source_basin"]
        name = source + ":" + basin
        if name in regions:
            continue
        separation = dict(baseline=12.5, sep25=25.0, sep50=50.0)[source]
        prefix = canonical_digest(json_value(replace(config, basin_separation_km=separation)))
        keys = [f"{prefix}:{basin}:calibration", f"{prefix}:{basin}:association"]
        keys += [
            f"{prefix}:{basin}:{a}:{start}"
            for a in ("zero-c", "fitted-c")
            for start in config.final_starts
        ]
        values = {}
        for key in keys:
            value = store.get(key)
            assert value is not None, key
            values[key] = dict(value=value, value_sha256=canonical_digest(value))
        regions[name] = dict(source=source, basin=basin, prefix=prefix, checkpoints=values)
    receipt = dict(
        session_id=document["session_id"],
        checkpoint_binding=document["diagnostics"]["checkpoint_binding"],
        selection="Published ordinary regional sources/basins; no reference-error selection",
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        regions=regions,
        port="RegionalCheckpointStore.get; no writes or production mutation",
    )
    with (HERE / "ordinary-winner-checkpoints.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print("Verified ordinary regional winner receipts:", len(regions))


if __name__ == "__main__":
    main()
