"""Coordinator-only source audit and declared group controls; never tunes a model."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import ds7_eval as e  # noqa: E402

WAVE = Path(__file__).resolve().parent
PLAN = ROOT / "reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json"


def audit(path):
    data = e.read_json(path)
    source = data["source"]
    for kind in ("request", "response", "seal"):
        assert e.file_digest(Path(source[kind + "_path"])) == source[kind + "_sha256"]
    run = Path(source["seal_path"]).parent
    seal = e.read_sealed(run / "seal.json", "ds7-run-seal/v1")
    assert {str(p.relative_to(run)) for p in run.rglob("*") if p.is_file()} == set(
        seal["files"]
    ) | {"seal.json"}
    for name, digest in seal["files"].items():
        assert e.file_digest(run / name) == digest
    request = e.read_json(Path(source["request_path"]))
    response = e.read_json(Path(source["response_path"]))
    assert request["unit"]["session_ids"] == [data["session_id"]]
    assert request["captures"][0]["manifest_sha256"] == data["manifest_sha256"]
    assert source["unit_id"] == request["unit"]["unit_id"] == response["unit_id"]
    for key in ("status", "converged", "boundary_hit", "estimate", "rf_rms_hz"):
        assert data[key] == response[key]
    # Preserve unqualified source rows; the frozen control adapter must abstain.
    score = WAVE / "coordinator" / (run.name + "-score-v1")
    if not score.exists():
        e.evaluate(e.DEFAULT_DATASET, run, score)
    return data


def main(group):
    unit_id = "group8-" + group
    unit = next(u for u in e.read_json(PLAN)["units"] if u["unit_id"] == unit_id)
    base = e.read_json(
        ROOT / "reports/2026_09_27_ds7_wave5/coordinator/controls-cumulative32-index.json"
    )
    members = {}
    for sid in unit["session_ids"]:
        path = WAVE / "solver" / ("scan-estimates-group" + group) / (sid + ".json")
        data = audit(path)
        members[sid] = {
            "session_id": sid,
            "manifest_sha256": data["manifest_sha256"],
            "state": "ready",
            "reason": None,
            "artifacts": [
                {"kind": "scan_estimate", "path": str(path), "sha256": e.file_digest(path)}
            ],
        }
    base["captures"] = [
        members.get(
            r["session_id"],
            {
                **r,
                "state": "unavailable",
                "reason": "Outside declared control group",
                "artifacts": [],
            },
        )
        for r in base["captures"]
    ]
    stem = WAVE / "coordinator" / ("controls-group" + group)
    index, frozen = Path(str(stem) + "-index.json"), Path(str(stem) + "-inputs.json")
    e.write_json(index, base)
    e.freeze_inputs(PLAN, index, frozen)
    e.write_json(
        Path(str(stem) + "-source-audit.json"),
        {
            "verified_session_ids": list(members),
            "exact_response_fields": True,
            "source_run_inventories_verified": True,
        },
    )
    for method in ("equal", "inverse_rms2", "lowest_rms75"):
        run = WAVE / "controls" / (method + "-group" + group + "-v1")
        e.run(
            PLAN,
            frozen,
            ROOT / ("config/ds7/controls-wave2-" + method + ".json"),
            run,
            max_seconds=10,
            unit_seconds=10,
            selected_units=[unit_id],
        )
        score = WAVE / "coordinator" / ("controls-" + method + "-group" + group + "-score-v1")
        e.evaluate(e.DEFAULT_DATASET, run, score)
        print(json.dumps(e.read_json(score / "scores.json")["trials"]), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
