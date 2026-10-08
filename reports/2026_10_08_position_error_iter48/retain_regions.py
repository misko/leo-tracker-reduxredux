"""Add a 50 km-separated region set to consumed DS16-046 without changing its grid."""

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter45"))
# isort: off
from complete_members import load_case  # noqa: E402
from extension import extend_pipeline  # noqa: E402
from pipeline import run_pipeline  # noqa: E402
from newer import Hard60Configuration, run_hard60, regional_position_document  # noqa: E402
from newer import ReplayCheckpoints, RegionalSliceExpired, configuration  # noqa: E402
from inputs import ExperimentCheckpoints, json_value, write_json  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402
# isort: on


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS.parent / name).read_bytes()).hexdigest() == digest, name
    output = HERE / "result.json"
    if output.exists():
        raise FileExistsError(output)
    original = json.loads(
        (REPORTS / "2026_10_08_position_error_iter45/baselines/DS16-046.json").read_text()
    )
    previous = json.loads(
        (REPORTS / "2026_10_08_position_error_iter45/results/DS16-046.json").read_text()
    )
    # The baseline wins both arms against sep25, so comparing it with sep50 preserves
    # every previously eligible regional winner without fabricating a merged document.
    assert previous["upstream"]["regional_sources"] == {
        "fitted-c": "baseline",
        "zero-c": "baseline",
    }
    case = load_case(original, Path(plan["baseline_checkpoint_root"]))
    config = replace(Hard60Configuration(), basin_separation_km=50)
    prefix = canonical_digest(json_value(config)) + ":"
    cache = ExperimentCheckpoints(
        HERE / "local/checkpoints",
        dict(original=canonical_digest(original), configuration=json_value(config)),
    )
    borrowed = set()
    result = None
    for _ in range(4):
        try:
            result = run_hard60(
                case.prepared.observations,
                case.bank,
                case.prior,
                case.prepared.bootstrap_tracks,
                ReplayCheckpoints(case, cache, prefix, borrowed),
                configuration=config,
                maximum_seconds=500,
            )
            break
        except RegionalSliceExpired as error:
            print("Checkpointed", str(error), flush=True)
    if result is None:
        raise TimeoutError("Four bounded regional slices exhausted")
    doc_config = configuration()
    doc_config["run"] = json_value(config)
    document = regional_position_document(
        result,
        session_id=original["session_id"],
        input_digest=original["input_manifest_sha256"],
        analysis_digest=original["analysis_manifest_sha256"],
        evidence_digest=original["evidence_sha256"],
        configuration=doc_config,
        windows=original["windows"],
        reference=(original["reference_latitude_deg"], original["reference_longitude_deg"]),
        reference_evidence="Existing reference applied after inference only",
        diagnostics={k: original["diagnostics"][k] for k in ("bank", "snapshot_sha256")},
    ).model_dump(mode="json")

    def grid(doc):
        return [(r["east_km"], r["north_km"], r["spacing_km"]) for r in doc["methods"][0]["points"]]

    assert grid(document) == grid(original)
    write_json(HERE / "regions.json", document)
    upstream = run_pipeline(case, original, document)
    extension = extend_pipeline(case, original, document, upstream)
    for stage in (*upstream["stages"].values(), *extension["stages"].values()):
        zero = stage["zero-c"]
        if "vector" in zero:
            assert zero["vector"][6] == 0
            assert all(v == 0 for v in zero.get("rf_drift_coefficients", []))
    write_json(
        output,
        dict(
            upstream=upstream,
            extension=extension,
            previous_operational=previous["extension"]["operational"],
            identical_grid=True,
            borrowed_stages=sorted(borrowed),
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
        ),
    )
    print(
        upstream["regional_sources"],
        {a: r["error_km"] for a, r in extension["operational"].items()},
        flush=True,
    )


if __name__ == "__main__":
    main()
