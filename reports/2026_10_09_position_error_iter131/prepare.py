"""Metadata-only explicit successor to129's failedDS16-020 admission."""

import hashlib
import json
from pathlib import Path

from inference_loader import inference_document

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare():
    parent_path = ROOT / "reports/2026_10_09_position_error_iter129/protocol.json"
    previous_path = ROOT / "reports/2026_10_09_position_error_iter107/protocol.json"
    if sha(parent_path) != "0b75b4df82b8493fef26f35f0d372cdbc69171fa9f6d85d2dccb34473d4247a3":
        raise ValueError("129 frozen authority changed")
    parent = json.loads(parent_path.read_text())
    previous = json.loads(previous_path.read_text())
    member = next(m for m in parent["members"] if m["label"] == "DS16-020")
    source = next(
        m for m in previous["members"] if m["member"].get("inventory_label") == "DS16-020"
    )
    if source["member"]["session_id"] != member["membership"]["session_id"]:
        raise ValueError("successor member differs")
    result_path = previous_path.parent / "results/DS16-020/baseline.json"
    result = json.loads(result_path.read_text())
    if result["status"] != "complete" or result["label"] != "DS16-020":
        raise ValueError("107 physical signature authority unavailable")
    expected = result["input_binding"]
    required = (
        "input_digest",
        "evidence_digest",
        "score_signature",
        "bank_signature",
        "observation_order_signature",
    )
    if set(expected) != set(required) or not all(expected.values()):
        raise ValueError("incomplete physical signatures")
    model = source["model_identity"]
    if not model["snapshot_sha256"] or not model["bank_signature"]:
        raise ValueError("missing reconstructed inference authority")
    document_path = ROOT / member["binding"]["document_path"]
    document = inference_document(json.loads(document_path.read_text()))
    if (
        expected["input_digest"] != document["input_manifest_sha256"]
        or expected["evidence_digest"] != document["evidence_sha256"]
    ):
        raise ValueError("historical input/evidence differ")
    clean_member = dict(
        member,
        binding=dict(member["binding"], model_identity=model, expected_input_binding=expected),
    )
    sources = dict(parent["source_sha256"])
    # Freeze only the extracted inference projection in this new protocol. Do not
    # use a whole107 reference-bearing membership/document digest as admission.
    inputs = {str(path.relative_to(ROOT)): sha(path) for path in (parent_path, document_path)}
    # Explicitly preserve the129 failure as a separate record, never replace it.
    failure_path = parent_path.parent / "results/DS16-020/search/result.json"
    failure = json.loads(failure_path.read_text())
    if failure["status"] != "failed":
        raise ValueError("successor is only for preserved failed admission")
    inputs[str(failure_path.relative_to(ROOT))] = sha(failure_path)
    for path in [*HERE.glob("*.py"), HERE / "README.md"]:
        if not path.name.startswith("test_"):
            sources[str(path.relative_to(ROOT))] = sha(path)
    for name, expected_hash in sources.items():
        if sha(ROOT / name) != expected_hash:
            raise ValueError("inherited source changed: " + name)
    return dict(
        members=[clean_member],
        policy=parent["policy"],
        source_sha256=sources,
        input_sha256=inputs,
        scope="separate clean admission successor, consumedDS16-020 only",
        previous_failure_preserved=True,
        no_reference_admission=True,
        inference_authority_projection=dict(model_identity=model, input_binding=expected),
        authority_sources=dict(
            model_identity=str(previous_path.relative_to(ROOT)),
            input_binding=str(result_path.relative_to(ROOT)),
            policy="whitelisted inference fields only; no whole-reference-document digest",
        ),
        observation_policy="exact frozen107 row/content/order signature before bank build",
        reference_scope="evaluation only after both successor branches seal",
    )


if __name__ == "__main__":
    value = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
