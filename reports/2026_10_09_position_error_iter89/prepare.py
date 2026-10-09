"""Freeze metadata-only successor boundaries and code; no live recording inventory."""

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = ROOT / "reports/2026_10_09_position_error_iter75/local"
MINT = Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds17_post_ds16/mint.py")
DS18 = Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds18_post_ds17/local/manifest.json")
START = "2026-10-09T02:02:21+00:00"
END = "2026-10-09T15:46:15+00:00"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    destination = HERE / "protocol.json"
    assert not destination.exists()
    assert sha(PARENT / "manifest.json") == "71e7477408e31449c14f85a7ae87155780e88c2503dc06544ab00a59016483af"
    assert sha(DS18) == "894a6f4b7055e5f6bd602f94ce3acf7f722f204c68c2b521a06dfd6be35a7516"
    parent = json.loads((PARENT / "manifest.json").read_bytes())
    assert parent["dataset_id"] == "POST18-RESERVE"
    assert parent["capture_start_window_utc"][1] == START
    assert len(parent["captures"]) == 11
    seal = json.loads((PARENT / "seal.json").read_bytes())
    for name, expected in seal["files"].items():
        assert "sha256:" + sha(PARENT / name) == expected, name
    environment = subprocess.check_output(
        ["systemctl", "show", "leo-api.service", "-p", "Environment", "--value"], text=True
    ).strip()
    entries = environment.split()
    selected = [e.split("=", 1)[1] for e in entries if e.startswith("PYTHONPATH=")]
    assert len(selected) == 1
    pythonpath = selected[0]
    runtime_roots = [Path(p) for p in pythonpath.split(":")]
    files = {MINT, MINT.parent / "test_mint.py", PARENT / "manifest.json", PARENT / "seal.json", DS18}
    files.update(HERE.glob("*.py"))
    files.update(HERE.glob("*.md"))
    for root in runtime_roots:
        assert root.is_dir()
        files.update(root.rglob("*.py"))
        files.update(root.rglob("*.so"))
    python = Path("/opt/leo-tracker/current-api/.venv/bin/python")
    files.add(python.resolve())
    plan = dict(
        dataset_id="POST18-NEWER-20261009", parent_dataset="POST18-RESERVE",
        start=START, end=END,
        cutoff_authority="clock.curr_time returned2026-10-09 15:46:15 UTC before first live inventory; whole-second cutoff",
        scope="Metadata-only unchanged read-only mint. No RF, holds, analysis, localization outcome access or production change.",
        membership="Every whole sealed adaptive recording started in[start,end), sealed byend; published plus unpublished firmware archives; no quality/analysis-readiness gate. Both receivers together. Explicit partials/exclusions.",
        parent_manifest_sha256=sha(PARENT / "manifest.json"), parent_seal_sha256=sha(PARENT / "seal.json"),
        ds18_manifest_sha256=sha(DS18), existing_reserve_members=11,
        existing_reserve_policy="All eleven POST18-RESERVE outcomes remain closed; successor is disjoint by frozen window and identities.",
        python_executable=str(python), python_resolved=str(python.resolve()), frozen_api_pythonpath=pythonpath,
        mint_source=str(MINT), parent_authority=str(PARENT), output=str(HERE / "local"),
        random_seed="leo-post18-newer-20261009-groups-v1",
        grouping="Connected whole-acquisition groups from recorded shared campaign/capture/parent IDs, duplicate manifest/IQ identities, plus fixed2hUTC capture-start blocks. Metadata-only longer shared acquisitions unioned before assignment; missing metadata/independence limitations explicit.",
        split="Consumed-evidence groups forceddevelopment. Other groups SHA256-rank frozen seed+canonical sorted member identities; lowest floor(0.2*groups) reserved, minimumone only if at leastfive unconsumedgroups. No chronology/quality/outcome rebalancing.",
        known_consumed_sessions=["scan-fw-7ebf76971ca06c00"],
        exposure="Exact session/digest matching emits filenames+identity tokens only, no localization lines or values. Search both report worktrees including ignored/local receipts; record permission failures, scope and limitations. Classify outcome consumption separately from metadata-only matches; no-match is not unseen proof.",
        outcome_gate="No new localization output or PNG access until candidate/control and numerical policy frozen; new reserve stays closed through development tuning and final candidate freeze.",
        source_sha256={str(p): sha(p) for p in sorted(files)},
    )
    destination.write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps(dict(status="prepared_not_inventoried", source_files=len(files),
                         cutoff=END, protocol_sha256=sha(destination)), indent=2))


if __name__ == "__main__":
    main()
