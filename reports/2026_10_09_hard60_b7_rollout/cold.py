"""Bounded cold CLI replay, without borrowed numerical receipts."""

import json
import time
from pathlib import Path

from leo.cli.regional_position import configuration, run_regional_position_analysis
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_v3 import B7Store

HERE = Path(__file__).resolve().parent
SESSION = "scan-fw-f6399482c82aa4ae"
OUTPUT = Path("/srv/postgres-nvme/leo-analysis-scratch/b7-cold-4105aae8b")

if __name__ == "__main__":
    started = time.monotonic()
    slices = []
    for _ in range(6):
        result = run_regional_position_analysis(
            Path("/srv/bulk/leo"),
            Path("/var/lib/leo/tle"),
            SESSION,
            output_root=OUTPUT,
            maximum_seconds=500,
        )
        slices.append(result)
        print(json.dumps(result), flush=True)
        if result["state"] == "complete":
            break
    status = B7Store(OUTPUT).status(SESSION)
    assert status.manifest is not None, "Cold replay exhausted six checkpointed slices"
    assert status.manifest.document.configuration_sha256 == canonical_digest(configuration())
    receipt = dict(
        session_id=SESSION,
        output_root=str(OUTPUT),
        slices=slices,
        elapsed_s=time.monotonic() - started,
        manifest=status.manifest.model_dump(mode="json"),
        scope="Cold regional grid and downstream fits; no borrowed checkpoints",
    )
    (HERE / "cold.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (HERE / "cold.png").write_bytes(B7Store(OUTPUT).artifact(SESSION, "V16"))
