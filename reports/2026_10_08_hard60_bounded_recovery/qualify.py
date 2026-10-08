"""Integrated DS16 regression: verified baseline stages, freshly computed recovery.

This is not a fresh search. The baseline read port rejects unknown stages and
never writes to production. New recovery checkpoints are isolated per scan.
Run with the production interpreter and the reviewed source on PYTHONPATH.
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from inputs import ExperimentCheckpoints, load_case, write_json

HERE = Path(__file__).resolve().parent

from leo.application.hard60_runner import run_hard60  # noqa: E402
from leo.application.regional_position_report import regional_position_document  # noqa: E402
from leo.cli.regional_position import configuration  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.presentation.regional_position import render_regional_position  # noqa: E402


def qualify(label):
    config = configuration()
    destination = HERE / "cohort" / f"{label}.json"
    if destination.exists():
        old = json.loads(destination.read_text())
        assert old["configuration_sha256"] == canonical_digest(config)
        return old
    begun = time.monotonic()
    case = load_case(label)
    prefix = canonical_digest(config["run"]) + ":"
    replayed = set()
    added = ExperimentCheckpoints(
        HERE / "checkpoints" / label,
        {"configuration": config, "baseline": case.document},
    )

    class Checkpoints:
        def get(self, key):
            assert key.startswith(prefix)
            stage = key.removeprefix(prefix)
            if stage.startswith("recovery:"):
                return added.get(key)
            replayed.add(stage)
            return case.checkpoint(stage)

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
    doc = regional_position_document(
        result,
        session_id=case.document["session_id"],
        input_digest=case.document["input_manifest_sha256"],
        analysis_digest=case.document["analysis_manifest_sha256"],
        evidence_digest=case.document["evidence_sha256"],
        configuration=config,
        windows=case.document["windows"],
        reference=(
            case.document["reference_latitude_deg"],
            case.document["reference_longitude_deg"],
        ),
        reference_evidence="Frozen DS16 reference, applied after selection",
    )
    actual = doc.model_dump(mode="json")
    frozen = json.loads((HERE / "frozen-inputs.json").read_text())[label]
    comparisons = {}
    for arm in actual["methods"][0]["arms"]:
        name, selected = arm["name"], arm["selected"]
        expected = frozen["prototype_arms"][name]["selected"]
        # Physical position within 1 m and objective within 0.001 nats.
        for field, tolerance in (("east_km", 0.001), ("north_km", 0.001), ("objective", 0.001)):
            np.testing.assert_allclose(selected[field], expected[field], atol=tolerance, rtol=0)
        assert selected["converged"] and selected["stationarity"] <= 0.001
        baseline = next(
            a["selected"] for a in case.document["methods"][0]["arms"] if a["name"] == name
        )
        comparisons[name] = {"baseline": baseline, "actual": selected, "prototype": expected}
    receipt = {
        "label": label,
        "session_id": case.document["session_id"],
        "configuration_sha256": canonical_digest(config),
        "baseline_stages_replayed": len(replayed),
        "failed_points": result["recovery"]["attempted_points"],
        "recovered_points": result["recovery"]["converged_points"],
        "added_finals": len(result["recovery"]["final_optimizers"]),
        "arms": comparisons,
        "elapsed_s": time.monotonic() - begun,
    }
    if label in ("S14", "S27"):
        write_json(HERE / f"{label}-document.json", actual)
        (HERE / f"{label}.png").write_bytes(render_regional_position(doc, "V16"))
    write_json(destination, receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("labels", nargs="+")
    for label in parser.parse_args().labels:
        row = qualify(label)
        print(json.dumps({k: v for k, v in row.items() if k != "arms"}), flush=True)
