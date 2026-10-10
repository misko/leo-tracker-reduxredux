"""Metadata-only preparation; actual freeze requires parent authorization."""

import hashlib
import json
from pathlib import Path

from execute import POLICY
from ports import ROOT

HERE = Path(__file__).resolve().parent
AUTHORITIES = {
    110: "64797ea7bdb2b04f0561fc876e7bb82b3911b27456b0702cc4ceb9b4be18758c",
    117: "827832cfdc24c9ddf8cfba1a457c87322a15bce85a80c95e34fff52fa4a1a793",
    123: "96b45034497dd50b0134a95510190d577d9e192928b9880a6830ee9cec79bb43",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def selected_identity(row):
    member = row["member"]
    return {
        key: member[key]
        for key in (
            "dataset",
            "inventory_label",
            "session_id",
            "recording_manifest_sha256",
            "uncompressed_sha256",
        )
    }


def forbid_evaluation(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if any(token in key.lower() for token in ("reference", "error_m", "error_km")):
                raise ValueError("evaluation field in inference document")
            forbid_evaluation(child)
    elif isinstance(value, list):
        for child in value:
            forbid_evaluation(child)


def prepare():
    for iteration, expected in AUTHORITIES.items():
        authority = ROOT / f"reports/2026_10_09_position_error_iter{iteration}/protocol.json"
        if sha(authority) != expected:
            raise ValueError("published membership/precedent authority changed")
    authorities = [
        ROOT / f"reports/2026_10_09_position_error_iter{n}/protocol.json" for n in (110, 117)
    ]
    plans = [json.loads(path.read_text()) for path in authorities]
    identities = [[selected_identity(row) for row in plan["members"]] for plan in plans]
    if identities[0] != identities[1] or len(identities[0]) != 12:
        raise ValueError("preselected cohort differs")
    if len({m["session_id"] for m in identities[0]}) != 12:
        raise ValueError("duplicate cohort session")
    if any(
        sum(m["dataset"] == dataset for m in identities[0]) != 4
        for dataset in ("DS16", "DS17", "DS18")
    ):
        raise ValueError("four per dataset required")
    parent = ROOT / "reports/2026_10_09_position_error_iter123/protocol.json"
    precedent = json.loads(parent.read_text())
    sources = dict(precedent["source_sha256"])
    inputs = {str(path.relative_to(ROOT)): sha(path) for path in [*authorities, parent]}
    members = []
    loader = precedent["binding"]
    for identity in identities[0]:
        label = identity["inventory_label"]
        document_path = (
            ROOT / f"reports/2026_10_09_position_error_iter107/documents/{label}-baseline.json"
        )
        document = json.loads(document_path.read_text())
        forbid_evaluation(document)
        if document["session_id"] != identity["session_id"]:
            raise ValueError("sanitized member session mismatch")
        for name in ("input_manifest_sha256", "analysis_manifest_sha256", "evidence_sha256"):
            if not document.get(name):
                raise ValueError("missing input authority: " + name)
        inputs[str(document_path.relative_to(ROOT))] = sha(document_path)
        members.append(
            dict(
                label=label,
                dataset=identity["dataset"],
                membership=identity,
                exposure="previously consumed conditional development",
                binding=dict(
                    session_id=identity["session_id"],
                    loader_source=loader["loader_source"],
                    loader_sha256=loader["loader_sha256"],
                    document_path=str(document_path.relative_to(ROOT)),
                    document_sha256=sha(document_path),
                ),
            )
        )
    for path in [*HERE.glob("*.py"), HERE / "PLAN.md", HERE / "RUN.md"]:
        if not path.name.startswith("test_"):
            sources[str(path.relative_to(ROOT))] = sha(path)
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError("inherited source changed: " + name)
    return dict(
        members=members,
        policy=POLICY,
        source_sha256=sources,
        input_sha256=inputs,
        scope="fresh matched native/fixed fitted discovery; consumed random12 pilot",
        archived_parity="not claimed; no original checkpoints imported",
        reference_scope="evaluation only after all twelve selections sealed",
        extension="complete descriptive metrics and paired regressions before full cohort decision",
    )


if __name__ == "__main__":
    value = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
