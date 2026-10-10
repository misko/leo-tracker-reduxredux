"""Seal completed frequency receipts and clean model bindings; no model or IQ read."""

import json
from collections import Counter

from run import HERE, ROOT, sha

AUTHORITIES = {
    "reports/2026_10_09_position_error_iter128/protocol.json": (
        "42190e78696a8ee89a1ba6cd34cd1ba59b0bcd654fd623b4c2f736dea1240b0d"
    ),
    "reports/2026_10_10_position_error_iter132/protocol.json": (
        "08624494f298852b5b29bacf89e1cb3c12c54c05698c3b42e8a0804e8bb34567"
    ),
    "reports/2026_10_10_position_error_iter134/protocol.json": (
        "a0f2990b471d3c62ec8037ff23849aefa35673384e4641817e9559cfccf963e0"
    ),
}


def admit_receipts(label, parity, iq, rows):
    """Terminal failures remain members; missing or inconsistent receipts block freeze."""
    if parity["label"] != label or parity["status"] not in ("complete", "failed"):
        raise ValueError("clean parity member not terminal")
    if iq["label"] != label or iq["status"] not in ("complete", "complete-with-failures"):
        raise ValueError("frequency member not terminal")
    ids = [row["window_id"] for row in rows]
    allowed = {
        "complete",
        "unsupported-sample-rate",
        "missing-visit-length",
        "visit-resource-cap",
        "visit-read-failed",
        "parity-or-window-failed",
        "budget-exhausted",
        "input-or-replay-failed",
    }
    if not {row["status"] for row in rows} <= allowed:
        raise ValueError("unreviewed frequency row status")
    if len(ids) != len(set(ids)) or len(ids) != iq["rows"] or iq["rows"] != iq["expected"]:
        raise ValueError("original frequency coverage inconsistent")
    if not iq["coverage_complete"]:
        raise ValueError("frequency coverage not terminal")
    if dict(Counter(row["status"] for row in rows)) != iq["counts"]:
        raise ValueError("frequency status counts differ")
    if iq["status"] == "complete" and any(row["status"] != "complete" for row in rows):
        raise ValueError("frequency success contains failures")
    return dict(parity=parity["status"], frequency=iq["status"], observations=len(ids))


def verify_original_membership(rows, metadata):
    ids = [row["window_id"] for row in rows]
    expected = metadata["window_ids"]
    if len(ids) != len(expected) or len(set(ids)) != len(ids) or set(ids) != set(expected):
        raise ValueError("frequency rows differ from original observation membership")


def prepare():
    for path, expected in AUTHORITIES.items():
        if sha(ROOT / path) != expected:
            raise ValueError("published authority changed: " + path)
    iq_path, clean_path, replay_path = [ROOT / name for name in AUTHORITIES]
    iq_plan, clean_plan = [json.loads(path.read_text()) for path in (iq_path, clean_path)]
    replay_plan = json.loads(replay_path.read_text())
    iq_members = {m["label"]: m for m in iq_plan["members"]}
    if replay_plan["member"] != iq_members["DS18-029"]:
        raise ValueError("successor changes original member inputs")
    if set(iq_members) != {m["label"] for m in clean_plan["members"]} or len(iq_members) != 12:
        raise ValueError("fixed twelve-member coverage differs")
    sources = dict(clean_plan["sources"])
    # Clean132 already pins106's executable fitter/qualification dependencies.
    # Do not inherit106's historical reference-bearing data as new runtime inputs.
    numerical_files = (
        "run.py",
        "compare.py",
        "measurement.py",
        "batch.py",
        "freeze.py",
        "PLAN.md",
        "test_compare.py",
        "test_measurement.py",
        "test_production_model.py",
        "test_run.py",
        "test_freeze.py",
    )
    for path in [HERE / name for name in numerical_files]:
        sources[str(path.relative_to(ROOT))] = sha(path)
    for relative in (
        "tests/analysis/test_hard60_joint.py",
        "tests/analysis/test_regional_position_score.py",
    ):
        sources[relative] = sha(ROOT / relative)
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError("frozen source changed: " + name)
    inputs = dict(AUTHORITIES)
    members = []
    for binding in clean_plan["members"]:
        label = binding["label"]
        if binding["session_id"] != iq_members[label]["session_id"]:
            raise ValueError("recording identity differs")
        parity_path = clean_path.parent / "results" / (label + ".json")
        iq_receipt = iq_path.parent / "results" / label / "result.json"
        original_receipt = iq_receipt
        selected_protocol = iq_path
        lineage = []
        if label == "DS18-029":
            original_iq = json.loads(original_receipt.read_text())
            original_rows = original_receipt.with_name("rows.jsonl")
            if (
                original_iq["protocol_sha256"] != sha(iq_path)
                or original_iq["metadata_sha256"] != iq_members[label]["metadata_sha256"]
                or original_iq["rows_sha256"] != sha(original_rows)
            ):
                raise ValueError("original failure provenance changed")
            for path in (original_receipt, original_rows):
                inputs[str(path.relative_to(ROOT))] = sha(path)
            lineage.append(
                dict(
                    receipt=str(original_receipt.relative_to(ROOT)),
                    status=original_iq["status"],
                    counts=original_iq["counts"],
                    elapsed_s=original_iq["elapsed_s"],
                )
            )
            iq_receipt = replay_path.parent / "results/result.json"
            selected_protocol = replay_path
        rows_path = iq_receipt.with_name("rows.jsonl")
        parity, iq = [json.loads(path.read_text()) for path in (parity_path, iq_receipt)]
        if (
            parity["protocol_sha256"] != sha(clean_path)
            or iq["protocol_sha256"] != sha(selected_protocol)
            or iq["metadata_sha256"] != iq_members[label]["metadata_sha256"]
            or iq["rows_sha256"] != sha(rows_path)
        ):
            raise ValueError("foreign or changed terminal receipt")
        rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
        coverage = admit_receipts(label, parity, iq, rows)
        metadata_path = ROOT / iq_members[label]["metadata_path"]
        if sha(metadata_path) != iq_members[label]["metadata_sha256"]:
            raise ValueError("original observation metadata changed")
        metadata = json.loads(metadata_path.read_text())
        verify_original_membership(rows, metadata)
        inputs[iq_members[label]["metadata_path"]] = iq_members[label]["metadata_sha256"]
        lineage.append(
            dict(
                receipt=str(iq_receipt.relative_to(ROOT)),
                status=iq["status"],
                counts=iq["counts"],
                elapsed_s=iq["elapsed_s"],
            )
        )
        for path in (parity_path, iq_receipt, rows_path):
            inputs[str(path.relative_to(ROOT))] = sha(path)
        members.append(
            dict(
                label=label,
                dataset=binding["dataset"],
                session_id=binding["session_id"],
                case_binding=binding,
                parity_receipt=str(parity_path.relative_to(ROOT)),
                iq_receipt=str(iq_receipt.relative_to(ROOT)),
                rows_path=str(rows_path.relative_to(ROOT)),
                coverage=coverage,
                frequency_lineage=lineage,
                frequency_replay_elapsed_s=sum(item["elapsed_s"] for item in lineage),
            )
        )
    return dict(
        members=members,
        sources=sources,
        inputs=inputs,
        maximum_fit_calls=72,
        maximum_seconds_per_fit=90,
        maximum_iterations_per_fit=600,
        variants=["original", "logparabola", "newton"],
        arms=["fitted-c", "zero-c"],
        starts="same ordinary fitted-derived vector and clocks; c0 RF locks only",
        frequency_sigma_hz=125,
        slope_half_width_hz_s=60,
        qualification_threshold=0.001,
        maximum_workers=1,
        threads_per_worker=1,
        scope="Consumed fixed12 final-model sensitivity; no operational variant selection",
        failure_policy="All members retained, no retries or missing-measurement imputation",
        reference_scope="Evaluation only after all twelve member results are terminal",
    )


if __name__ == "__main__":
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
        stream.write("\n")
