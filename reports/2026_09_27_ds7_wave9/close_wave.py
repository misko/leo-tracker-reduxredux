"""Close the completed tranche after both preparation and fitting lanes finish."""

import datetime
import subprocess
import sys
from pathlib import Path

WAVE = Path(__file__).resolve().parent
ROOT = WAVE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ds7_eval as e  # noqa: E402


def main():
    prior_root = ROOT / "reports/2026_09_27_ds7_wave8"
    prior = e.read_json(prior_root / "closeout.json")
    prep10 = e.read_json(WAVE / "inputs/group10/controller-terminal-receipt.json")
    assert prep10["state"] == "complete" and len(prep10["sessions_added"]) == 8
    assert prep10["controller_wall_seconds"] < 1200
    for key, base in (("wave_files", prior_root), ("source_files", ROOT)):
        for name, digest in prior[key].items():
            assert e.file_digest(base / name) == digest, name
    panels = [
        e.read_json(WAVE / "solver" / f"group8-{g}-terminal-receipt.json") for g in ("10",)
    ]
    assert all(len(p["trials"]) == 9 and p["total_adapter_seconds"] <= 900 for p in panels)
    for panel in panels:
        for run in panel["runs"]:
            assert e.file_digest(Path(run["path"]) / "seal.json") == run["seal_sha256"]
    seals = []
    for path in sorted(WAVE.rglob("seal.json")):
        seal = e.read_json(path)
        assert e.seal_object({k: v for k, v in seal.items() if k != "content_sha256"}) == seal
        assert {
            str(p.relative_to(path.parent)) for p in path.parent.rglob("*") if p.is_file()
        } == set(seal["files"]) | {"seal.json"}
        for name, digest in seal["files"].items():
            assert e.file_digest(path.parent / name) == digest
        seals.append(str(path.relative_to(WAVE)))
    scores = {}
    singles = {}
    for path in sorted((WAVE / "coordinator").glob("*/scores.json")):
        trials = e.read_json(path)["trials"]
        for row in trials:
            if row["kind"] == "single":
                assert row["unit_id"] not in singles
                singles[row["unit_id"]] = row
            else:
                scores[path.parent.name] = row
    assert len(singles) == 8 and len(scores) == 4
    index = e.read_json(prior_root / "coordinator/controls-cumulative80-index.json")
    additions = {}
    for group in ("10",):
        inputs = e.read_sealed(
            WAVE / "coordinator" / f"controls-group{group}-inputs.json", "ds7-inputs/v1"
        )
        for row in inputs["captures"]:
            if row["state"] == "ready":
                assert row["session_id"] not in additions
                additions[row["session_id"]] = row
    index["captures"] = [additions.get(r["session_id"], r) for r in index["captures"]]
    assert sum(r["state"] == "ready" for r in index["captures"]) == 88
    index_path = WAVE / "coordinator/controls-cumulative88-index.json"
    e.write_json(index_path, index)
    e.freeze_inputs(
        ROOT / "reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json",
        index_path,
        WAVE / "coordinator/controls-cumulative88-inputs.json",
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "reports/2026_09_27_ds7_full88/audit_estimates_v2.py"),
            "--inputs",
            str(WAVE / "coordinator/controls-cumulative88-inputs.json"),
            "--output",
            str(WAVE / "coordinator/coverage88-final.json"),
        ],
        check=True,
    )
    lines = [
        "# Wave 9 results",
        "",
        "All eight final singles and the complete group10 panel were evaluated. All 88 individual recordings now have sealed outcomes. Full88 pooled evaluation is separate and no pooled result is claimed here.",
        "",
        "The inherited DS6 prior alone has 809.029 m error against the unsurveyed DS7 reference. This was a post hoc coordinator diagnostic, not an independently selected model. Compare all results against it; this exposed single-site evaluation does not establish surveyed or generalized accuracy.",
        "",
        "| Run | Status | Qualified | Error (m) | Capture span (s) |",
        "|---|---|---|---:|---:|",
    ]
    for name, row in sorted(scores.items()):
        error = row["horizontal_error_m"]
        error_text = "—" if error is None else f"{error:.3f}"
        lines.append(
            f"| {name} | {row['status']} | {row['qualified']} | {error_text} | "
            f"{row['capture_span_seconds']:.3f} |"
        )
    lines += [
        "",
        "Statuses and qualification are retained above for every group10 method. Group performance is not a full88 pooled result.",
        "",
        "| Single | Qualified | Error (m) |",
        "|---|---|---:|",
    ]
    for name, row in sorted(singles.items()):
        lines.append(f"| {name} | {row['qualified']} | {row['horizontal_error_m']:.3f} |")
    lines += [
        "",
        "Individual qualification is retained in the table and cumulative audit. The earlier single062 remains boundary-unqualified, so full88 controls must abstain under the frozen policy. No score-dependent selection or retry was used.",
        "",
        "The final preparation worker finished within 1,200 seconds, with 240-second per-capture and 3 GiB address-space caps. The scientific panel remained below 900 adapter seconds. No raw IQ or new RF collection was used. Input integrity, source bindings and all sealed run inventories were verified; no model code changed, so the prior 91-test validation remains applicable.",
        "",
        "The merged input preserves the prior80 rows exactly and accounts for all88 identities. The cumulative88 estimate input includes the unqualified source row. Under the unchanged full88 specification, controls must retain abstention when any upstream single is unqualified. The full88 joint fit uses observation/bank inputs independently. No partial pooled result was scored.",
    ]
    with (WAVE / "RESULTS.md").open("x") as stream:
        stream.write("\n".join(lines) + "\n")
    source_files = dict(prior["source_files"])
    audit_path = ROOT / "reports/2026_09_27_ds7_full88/audit_estimates_v2.py"
    source_files[str(audit_path.relative_to(ROOT))] = e.file_digest(audit_path)
    source_files[str((prior_root / "closeout.json").relative_to(ROOT))] = e.file_digest(
        prior_root / "closeout.json"
    )
    for name, digest in source_files.items():
        assert e.file_digest(ROOT / name) == digest
    files = {
        str(p.relative_to(WAVE)): e.file_digest(p)
        for p in sorted(WAVE.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.name != "closeout.json"
    }
    e.write_json(
        WAVE / "closeout.json",
        e.seal_object(
            {
                "schema": "ds7-wave9-closeout/v1",
                "closed_utc": datetime.datetime.now(datetime.UTC).isoformat(),
                "dataset_sha256": e.DS7_SHA256,
                "status": "complete",
                "goal_achieved": False,
                "full88_evaluated": False,
                "evaluated_single_count_cumulative": 88,
                "prepared_capture_count_in_final_input": 88,
                "remaining_unprepared_in_final_input": 0,
                "prior_center_diagnostic_m": 809.029031551158,
                "raw_iq_read_bytes": 0,
                "new_rf_collection": False,
                "wave9_workers_running": False,
                "adapter_seconds_by_group": {
                    p["selected_units"][-1]: p["total_adapter_seconds"] for p in panels
                },
                "group_scores": scores,
                "directory_seals_verified": seals,
                "wave_files": files,
                "source_files": source_files,
            }
        ),
    )
    print(e.file_digest(WAVE / "closeout.json"))


if __name__ == "__main__":
    main()
