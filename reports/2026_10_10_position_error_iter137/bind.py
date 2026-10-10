"""Bind clean source-document identities to selected inference projections."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UPSTREAM = HERE.parent / "2026_10_09_position_error_iter107"


def main():
    authority = json.loads((UPSTREAM / "protocol.json").read_text())
    rows = []
    provenance = []
    for member in authority["members"]:
        label = member["member"].get("inventory_label", member["member"].get("dataset_label"))
        selected_path = HERE / "selected" / (label + ".json")
        selected = json.loads(selected_path.read_text())
        source_hash = selected.pop("preparation_source_sha256", None)
        if source_hash is not None:
            provenance.append(dict(label=label, candidate_sha256=source_hash))
            # Explicit preparation migration separates source integrity from
            # inference admission. No numerical receipt is changed.
            selected_path.write_text(json.dumps(selected, indent=2, allow_nan=False) + "\n")
        identity = member.get("model_identity")
        if identity is None:
            identity = member["sources"][0]["model_identity"]
        compatible = []
        for source in member["sources"]:
            # Source documents may describe different regional hypotheses, but
            # the capture/evidence/prior/bank authority must match exactly.
            if source.get("model_identity", identity) != identity:
                continue
            path = UPSTREAM / source["sanitized_path"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != source["sanitized_sha256"]:
                raise ValueError("Sanitized source hash mismatch")
            compatible.append(dict(path=str(path.relative_to(ROOT)), sha256=digest))
        if not compatible:
            raise ValueError("No exact model-identity source document")
        rows.append(
            dict(
                label=label,
                session_id=selected["session_id"],
                membership=member["member"],
                model_identity=identity,
                expected_input_binding=selected["input_binding"],
                compatible_documents=compatible,
                selected_path=str(selected_path.relative_to(ROOT)),
                selected_sha256=hashlib.sha256(selected_path.read_bytes()).hexdigest(),
            )
        )
    with (HERE / "bindings.json").open("x") as stream:
        json.dump(dict(members=rows), stream, indent=2, allow_nan=False)
        stream.write("\n")
    with (HERE / "preparation-provenance.json").open("x") as stream:
        json.dump(dict(members=provenance), stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
