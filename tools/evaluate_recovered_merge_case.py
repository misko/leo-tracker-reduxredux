"""Evaluate sealed recovery fits using their own verified offline reference product."""

import argparse
import json
from pathlib import Path

from continuous_merge_study import sha, write

from leo.application.regional_position_report import regional_position_document
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_v3 import B7Store


def evaluate(case, reference_root):
    position = case / "positions"
    protocol = json.loads((position / "experiment.json").read_bytes())
    census = json.loads((case / "census.json").read_bytes())
    variants = ("baseline", "consistent")
    paths = {v: position / v / "terminal.json" for v in variants}
    results = {v: json.loads(p.read_bytes()) for v, p in paths.items()}
    if any(r["status"] != "complete" for r in results.values()):
        raise ValueError("all matched numerical fits must be complete before evaluation")
    seal = {
        "position_protocol_sha256": sha(position / "experiment.json"),
        "terminals": {v: sha(p) for v, p in paths.items()},
        "reference_usage": "none before this seal",
    }
    seal_path = position / "evaluation-seal-baseline-consistent.json"
    if seal_path.exists() and json.loads(seal_path.read_bytes()) != seal:
        raise ValueError("the sealed numerical authority changed")
    if not seal_path.exists():
        write(seal_path, seal)
    status = B7Store(reference_root).status(protocol["session_id"])
    if status.manifest is None:
        raise ValueError("the specified offline B7 reference product is missing")
    authority = status.manifest.document
    if authority.input_manifest_sha256 != census["input_manifest_sha256"]:
        raise ValueError("reference product belongs to another recording")
    reference = (authority.reference_latitude_deg, authority.reference_longitude_deg)
    rows = []
    for variant, result in results.items():
        prepared = json.loads((case / (variant + ".json")).read_bytes())
        document = regional_position_document(
            result["result"],
            session_id=protocol["session_id"],
            input_digest=census["input_manifest_sha256"],
            analysis_digest=census["analysis_manifest_sha256"],
            evidence_digest=prepared["evidence_sha256"],
            configuration=protocol["configuration"],
            windows=census["windows"],
            reference=reference,
            reference_evidence=authority.reference_evidence,
        )
        for arm in next(m for m in document.methods if m.name == "V16").arms:
            selected = arm.selected
            final = next((r for r in result["result"]["finals"] if r["arm"] == arm.name), None)
            rows.append(
                {
                    "variant": variant,
                    "arm": arm.name,
                    "reference_error_m": selected.horizontal_error_m if selected else None,
                    "objective": selected.objective if selected else None,
                    "posterior_rms_hz": selected.posterior_rms_hz if selected else None,
                    "accepted_stage": (final or {}).get("accepted_stage"),
                }
            )
    write(
        position / "evaluation-offline-reference-baseline-consistent.json",
        {
            "dataset": protocol["dataset"],
            "session_id": protocol["session_id"],
            "reference": reference,
            "reference_evidence": authority.reference_evidence,
            "reference_product_root": str(reference_root),
            "reference_document_sha256": canonical_digest(authority.model_dump(mode="json")),
            "seal_sha256": sha(seal_path),
            "script_sha256": sha(Path(__file__)),
            "rows": rows,
            "scope": (
                "The same recording's offline B7 product supplies the configured "
                "reference convention; no reference from another recording is substituted "
                "and no inference result is changed."
            ),
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("--reference-products", required=True, type=Path)
    args = parser.parse_args()
    evaluate(args.case, args.reference_products)
