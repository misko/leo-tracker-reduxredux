"""Posthoc position evaluation after sealing a complete matched replay pair."""

import argparse
import json
from pathlib import Path

from continuous_merge_study import LOCAL, sha, write

from leo.application.regional_position_report import regional_position_document
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store


def evaluate(case, variants):
    position = case / "positions"
    protocol = json.loads((position / "experiment.json").read_bytes())
    census = json.loads((case / "census.json").read_bytes())
    terminals = {}
    for variant in variants:
        path = position / variant / "terminal.json"
        value = json.loads(path.read_bytes())
        if value["status"] != "complete":
            raise ValueError("matched variant has no completed numerical result: " + variant)
        terminals[variant] = value
    seal_path = position / ("evaluation-seal-" + "-".join(variants) + ".json")
    seal = {
        "position_protocol_sha256": sha(position / "experiment.json"),
        "terminals": {v: sha(position / v / "terminal.json") for v in variants},
        "reference_usage": "none before this seal",
    }
    if seal_path.exists():
        if json.loads(seal_path.read_bytes()) != seal:
            raise ValueError("evaluation authority changed")
    else:
        write(seal_path, seal)
    # References are metadata of the published comparison, accessed through
    # its public read-only adapter. They never enter the replay or merger.
    published = B7Store(Path("/srv/bulk/leo")).status(protocol["session_id"]).manifest
    if published is None:
        published = Hard60Store(Path("/srv/bulk/leo")).status(protocol["session_id"]).manifest
    if published is None:
        raise ValueError("published reference authority unavailable")
    reference = (
        published.document.reference_latitude_deg,
        published.document.reference_longitude_deg,
    )
    results = {}
    for variant, terminal in terminals.items():
        prepared = json.loads((case / (variant + ".json")).read_bytes())
        document = regional_position_document(
            terminal["result"],
            session_id=protocol["session_id"],
            input_digest=census["input_manifest_sha256"],
            analysis_digest=census["analysis_manifest_sha256"],
            evidence_digest=prepared["evidence_sha256"],
            configuration=protocol["configuration"],
            windows=census["windows"],
            reference=reference,
            reference_evidence=published.document.reference_evidence,
        )
        method = next(m for m in document.methods if m.name == "V16")
        arms = {}
        for arm in method.arms:
            selected = arm.selected.model_dump(mode="json") if arm.selected is not None else None
            final = next((r for r in terminal["result"]["finals"] if r["arm"] == arm.name), None)
            state = ((final or {}).get("fit") or {}).get("joint_state", {})
            arms[arm.name] = {
                "selected": selected,
                "satellites": (final or {}).get("satellites"),
                "accepted_stage": (final or {}).get("accepted_stage"),
                "likelihood_nll": state.get("likelihood_nll"),
                "timing_penalty": state.get("timing_penalty"),
                "nuisance_penalty": state.get("nuisance_penalty"),
            }
        results[variant] = arms
    write(
        position / ("evaluation-" + "-".join(variants) + ".json"),
        {
            "dataset": protocol["dataset"],
            "session_id": protocol["session_id"],
            "role": protocol["role"],
            "reference": reference,
            "reference_evidence": published.document.reference_evidence,
            "seal_sha256": sha(seal_path),
            "results": results,
            "scope": (
                "Matched pipeline intervention with common initial bank/observations/prior/budget; "
                "production accepted outputs. Interpret c effects only at common stationary stages "
                "with common final banks, because per-arm fallbacks may select different stages."
            ),
        },
    )
    print(
        json.dumps(
            {
                variant: {
                    arm: {
                        "horizontal_error_m": (value["selected"] or {}).get("horizontal_error_m"),
                        "objective": (value["selected"] or {}).get("objective"),
                        "posterior_rms_hz": (value["selected"] or {}).get("posterior_rms_hz"),
                        "likelihood_nll": value["likelihood_nll"],
                        "accepted_stage": value["accepted_stage"],
                    }
                    for arm, value in arms.items()
                }
                for variant, arms in results.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=("DS20", "DS16"))
    parser.add_argument("session_id")
    parser.add_argument("--variants", nargs="+", default=["baseline", "replace-guard"])
    args = parser.parse_args()
    evaluate(LOCAL / args.dataset / args.session_id, args.variants)
