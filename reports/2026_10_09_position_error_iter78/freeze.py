"""Bind the full cohort and imported source closure before any sensitivity fits."""

import datetime
import hashlib
import json
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
runpy.run_path(str(HERE / "evaluate.py"), run_name="frozen_import_only")
from sensitivity_policy import regional_path  # noqa: E402


def read(path):
    return json.loads(path.read_text())


def main():
    assert not (HERE / "protocol.json").exists(), "Do not replace a frozen protocol"
    snapshot_path = ROOT / "reports/2026_10_09_position_error_iter65/snapshot.json"
    old_path = ROOT / "reports/2026_10_09_position_error_iter51/protocol.json"
    old = read(old_path)
    bindings = {m["member"]["inventory_label"]: m for m in old["members"]}
    files = {snapshot_path, old_path}
    files.update(ROOT / path for path in old["source_sha256"])
    files.update(
        HERE / name
        for name in (
            "evaluate.py",
            "sensitivity_policy.py",
            "test_sensitivity_policy.py",
            "freeze.py",
        )
    )
    for module in tuple(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and path.endswith(".py"):
            path = Path(path).resolve()
            if path.is_relative_to(ROOT / "reports") or "/worker/src/leo/" in str(path):
                files.add(path)
    members = []
    for case in read(snapshot_path)["cases"]:
        path = ROOT / case["result_source"]
        files.add(path)
        result = read(path)
        region = regional_path(result, path, ROOT)
        if region is not None:
            assert region.exists(), region
            files.add(region)
        members.append(
            dict(
                member=case["member"],
                result_source=case["result_source"],
                loader_binding=bindings[case["member"]["inventory_label"]],
            )
        )
    assert len(members) == 148
    hashes = {
        str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p): hashlib.sha256(
            p.read_bytes()
        ).hexdigest()
        for p in sorted(files)
    }
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        sigmas=[0.25, 0.125, 0.5],
        shards=2,
        maximum_seconds=90,
        maximum_iterations=600,
        members=members,
        source_sha256=hashes,
        execution="Start only after both experiment71 workers terminate; "
        "two single-thread workers.",
        policy="Every sigma starts from the same archived extension seed. Both c arms share bank, "
        "centers, observations, priors and budget. No sequential warm starts across sigmas. "
        "Keep independent convergence gate; fallback to archived accepted control per arm.",
        audit="Reconstructed sigma0.25 objectives must reproduce both archived raw final scores "
        "within1e-6 before fitting. New90s control differences from old20s are reported.",
        reporting="All148, dataset and exposure subgroups, baseline/new0.25/candidates, "
        "mean/median/p95/worst, paired1m regressions, raw convergence/fallbacks, "
        "input failures, frequency RMS separately. No truth-selected per-scan winner.",
        validation="Consumed development only. No independent validation claim or deployment. "
        "POST18 reserve remains outcome-unexamined. No new RF collection.",
    )
    (HERE / "protocol.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(len(members), "members;", len(hashes), "pinned inputs and sources")


if __name__ == "__main__":
    main()
