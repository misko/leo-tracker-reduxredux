"""Read saved public research checkpoint metadata, never recordings/models/truth."""

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UPSTREAM = ROOT / "reports/2026_10_09_position_error_iter107"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label(member):
    return member["member"].get("inventory_label", member["member"].get("dataset_label"))


def main():
    protocol_path = UPSTREAM / "protocol.json"
    plan = json.loads(protocol_path.read_text())
    if len(plan["members"]) != 193 or len({label(m) for m in plan["members"]}) != 193:
        raise ValueError("Expected exact full193 membership")
    digest = sha(protocol_path)
    path = ROOT / "reports/2026_10_09_position_error_iter105/overlay.py"
    spec = importlib.util.spec_from_file_location("public_overlay105_for137", path)
    port = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(port)
    rows = []
    sizes = []
    for member in plan["members"]:
        name = label(member)
        directory = UPSTREAM / "results" / name
        sizes.append((directory / "candidate.json").stat().st_size)
        source = port.Overlay(directory / "stages", digest, ROOT, {}, compatible=False)
        stages = {}
        for arm in ("fitted-c", "zero-c"):
            key = "candidate107:b7:B7:" + arm
            receipt = source.get(key)
            fit = None if receipt is None else receipt["result"]
            state = {} if fit is None else fit.get("joint_state", {})
            stages[arm] = dict(
                key=key,
                present=receipt is not None,
                qualified=bool(fit and fit["converged"]),
                reason=None if receipt is None else receipt.get("reason"),
                joint_state_fields=sorted(state),
                vector_length=None if fit is None else len(fit["vector"]),
                clock_length=None if fit is None else len(fit["clock_coefficients"]),
                baseline_rows=len(state.get("receiver_baseline_hz", [])),
                centers=len(state.get("satellite_centers_s", [])),
                nodes=len(state.get("clock_nodes_s", [])),
                receipt_path=str(source.path(key).relative_to(ROOT)),
                receipt_sha256=sha(source.path(key)) if receipt is not None else None,
            )
        docs = []
        for descriptor in member["sources"]:
            document_path = UPSTREAM / descriptor["sanitized_path"]
            docs.append(
                dict(
                    name=descriptor["name"],
                    path=str(document_path.relative_to(ROOT)),
                    present=document_path.exists(),
                    sha256=descriptor["sanitized_sha256"],
                    model_identity_mismatches=descriptor.get("model_identity_mismatches"),
                )
            )
        rows.append(
            dict(
                label=name,
                session_id=member["member"]["session_id"],
                dataset=name.split("-")[0],
                b7=stages,
                documents=docs,
                missing_model_identity=[
                    k
                    for k in (
                        "input_manifest_sha256",
                        "analysis_manifest_sha256",
                        "evidence_sha256",
                        "prior_signature",
                        "score_signature",
                        "snapshot_sha256",
                        "bank_signature",
                    )
                    if not member.get("model_identity", {}).get(k)
                ],
            )
        )
    result = dict(
        scope=(
            "Metadata-only existing 193 development source feasibility; "
            "no fits/recordings/reference-error queries"
        ),
        members=rows,
        counts=dict(Counter(r["dataset"] for r in rows)),
        b7_qualified={
            a: sum(r["b7"][a]["qualified"] for r in rows) for a in ("fitted-c", "zero-c")
        },
        b7_missing={
            a: sum(not r["b7"][a]["present"] for r in rows) for a in ("fitted-c", "zero-c")
        },
        candidate_container_bytes=sum(sizes),
        source_provenance={
            str(protocol_path.relative_to(ROOT)): digest,
            str(path.relative_to(ROOT)): sha(path),
        },
        limitation=(
            "Stage qualification alone does not establish operational selection "
            "or selected bank IDs; latest 107 candidate operational metadata remains required"
        ),
    )
    with (HERE / "source-feasibility.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
