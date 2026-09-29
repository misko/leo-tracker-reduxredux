"""Preserve installed RF-normalization source provenance without radio reads."""

import hashlib
import inspect
import json
import sys
from pathlib import Path

import leo.analysis.persistent_hop_trajectory as trajectory
import leo.application.scanner_trajectory as projection
import leo.operations.adaptive_tle_position_inputs as inputs

HERE = Path(__file__).resolve().parent
target = HERE / "runtime_sources"
target.mkdir(exist_ok=False)
rows = []
for module in (trajectory, projection, inputs):
    path = Path(inspect.getfile(module))
    data = path.read_bytes()
    (target / path.name).write_bytes(data)
    rows.append(
        dict(
            module=module.__name__,
            path=str(path),
            copy=str((target / path.name).relative_to(HERE)),
            sha256=hashlib.sha256(data).hexdigest(),
        )
    )
reference = trajectory.PersistentHopTrajectoryConfig().canonical_rf_hz
assert reference == 11_200_000_000.0
with (HERE / "source-audit.json").open("x") as f:
    json.dump(dict(python=sys.version, canonical_rf_hz=reference, sources=rows), f, indent=2)
print("Preserved three installed normalization modules; canonical RF", reference)
