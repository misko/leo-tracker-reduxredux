"""Uniform additive baseline+sep25+sep50 evaluation, preserving every member."""

import hashlib
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter51"))
from cohort_inputs import BaselinePending, load, read  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter50"))
# isort: off
from region_pipeline import run_pipeline  # noqa: E402
from extension import extend_pipeline  # noqa: E402
from newer import Hard60Configuration, run_hard60, regional_position_document  # noqa: E402
from newer import ReplayCheckpoints, RegionalSliceExpired, configuration  # noqa: E402
from inputs import ExperimentCheckpoints, json_value, write_json  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402
# isort: on


def grid(document):
    return [
        (r["east_km"], r["north_km"], r["spacing_km"]) for r in document["methods"][0]["points"]
    ]


def regional(case, baseline, label, separation, archived):
    config = replace(Hard60Configuration(), basin_separation_km=separation)
    if archived:
        document = read(REPORTS.parent / archived)
        assert document["configuration"]["run"] == json_value(config)
        for key in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256"):
            assert document[key] == baseline[key]
        assert grid(document) == grid(baseline)
        return document, dict(
            mode="archived",
            path=archived,
            sha256=hashlib.sha256((REPORTS.parent / archived).read_bytes()).hexdigest(),
        )
    destination = HERE / "regions" / label / f"sep{separation}.json"
    if destination.exists():
        raise FileExistsError("Preserve first regional result")
    prefix = canonical_digest(json_value(config)) + ":"
    cache = ExperimentCheckpoints(
        HERE / "local/checkpoints" / label / f"sep{separation}",
        dict(baseline=canonical_digest(baseline), config=json_value(config)),
    )
    borrowed, result = set(), None
    begun = time.monotonic()
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
            print(label, separation, "checkpointed", str(error), flush=True)
    if result is None:
        raise TimeoutError("Four bounded regional slices exhausted")
    doc_config = configuration()
    doc_config["run"] = json_value(config)
    document = regional_position_document(
        result,
        session_id=baseline["session_id"],
        input_digest=baseline["input_manifest_sha256"],
        analysis_digest=baseline["analysis_manifest_sha256"],
        evidence_digest=baseline["evidence_sha256"],
        configuration=doc_config,
        windows=baseline["windows"],
        reference=(baseline["reference_latitude_deg"], baseline["reference_longitude_deg"]),
        reference_evidence="Existing reference applied after inference only",
        diagnostics={k: case.document["diagnostics"][k] for k in ("bank", "snapshot_sha256")},
    ).model_dump(mode="json")
    assert grid(document) == grid(baseline)
    write_json(destination, document)
    return document, dict(
        mode="new_replay",
        borrowed_stages=sorted(borrowed),
        elapsed_s=time.monotonic() - begun,
        document_digest=canonical_digest(document),
    )


def main(label):
    protocol = read(HERE / "protocol.json")
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS.parent / name).read_bytes()).hexdigest() == digest, name
    for canary in ("DS18-009", "DS16-046", "S41", "DS17-008"):
        assert (
            read(REPORTS / "2026_10_08_position_error_iter50/results" / f"{canary}.json")["status"]
            == "complete"
        )
    binding = next(r for r in protocol["members"] if r["member"]["inventory_label"] == label)
    destination = HERE / "results" / f"{label}.json"
    if destination.exists():
        raise FileExistsError(destination)
    begun = time.monotonic()
    try:
        case, baseline, previous = load(binding)
        for key in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256"):
            assert case.document[key] == baseline[key], key
        assert list(case.bank.numbers) == case.document["diagnostics"]["bank"]["retained_numbers"]
        documents = dict(baseline=baseline)
        receipts = {}
        for separation in (25, 50):
            name = f"sep{separation}"
            documents[name], receipts[name] = regional(
                case, baseline, label, separation, binding.get(f"{name}_path")
            )
        upstream = run_pipeline(case, documents)
        winning = documents[upstream["regional_sources"]["fitted-c"]]
        extension = extend_pipeline(case, winning, winning, upstream)
        for stage in (*upstream["stages"].values(), *extension["stages"].values()):
            zero = stage["zero-c"]
            if "vector" in zero:
                assert zero["vector"][6] == 0
                assert all(v == 0 for v in zero.get("rf_drift_coefficients", []))
        output = dict(
            status="complete",
            member=binding["member"],
            upstream=upstream,
            extension=extension,
            previous_candidate=previous,
            baseline_arms={a["name"]: a["selected"] for a in baseline["methods"][0]["arms"]},
            baseline_document_digest=canonical_digest(baseline),
            region_receipts=receipts,
            elapsed_s=time.monotonic() - begun,
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
        )
    except BaselinePending as error:
        write_json(
            HERE / "pending" / f"{label}.json", dict(member=binding["member"], reason=str(error))
        )
        print(label, "PENDING", str(error), flush=True)
        return
    except Exception as error:
        write_json(destination, dict(status="failed", member=binding["member"], error=repr(error)))
        print(label, "FAILED", repr(error), flush=True)
        return
    write_json(destination, output)
    print(
        label,
        upstream["regional_sources"],
        {a: r["error_km"] for a, r in extension["operational"].items()},
        flush=True,
    )


if __name__ == "__main__":
    for label in sys.argv[1:]:
        main(label)
