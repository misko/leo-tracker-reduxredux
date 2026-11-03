"""Read pinned capture timing metadata through its public storage port."""

import hashlib
import inspect
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    plan_path = HERE.parent / "2026_09_29_donor_residual_transfer/plan.json"
    plan = json.loads(plan_path.read_text())
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    rows, hashes = [], {}
    for u in plan["units"]:
        if u["role"] != "target":
            continue
        for i, entry in enumerate(u["group"]["inputs"]):
            obs_path = Path(
                next(a["path"] for a in entry["artifacts"] if a["kind"] == "observations")
            )
            expected = next(a["sha256"] for a in entry["artifacts"] if a["kind"] == "observations")
            digest = hashlib.sha256(obs_path.read_bytes()).hexdigest()
            assert "sha256:" + digest == expected
            hashes[str(obs_path.relative_to(ROOT))] = digest
            obs = json.loads(obs_path.read_text())
            capture = store.inspect(entry["session_id"])
            assert capture.manifest_sha256 == obs["manifest_sha256"] == entry["manifest_sha256"]
            t = capture.manifest.timing
            rows.append(
                dict(
                    unit_id=u["unit_id"],
                    session_id=entry["session_id"],
                    manifest_sha256=capture.manifest_sha256,
                    observation_start_utc_ns=obs["start_utc_ns"],
                    fitted_tau_s=u["x"][i + 2],
                    timing=t.model_dump(mode="json") if t else None,
                    terminal=capture.manifest.receipt.terminal.model_dump(mode="json"),
                )
            )
        print(u["unit_id"], len(rows), file=sys.stderr, flush=True)
    assert len(rows) == len({r["session_id"] for r in rows}) == 72
    for p in (plan_path, HERE / "PROTOCOL.md", HERE / "export.py"):
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    runtime = {}
    for obj in (AdaptiveHopIqStore, type(t)):
        path = Path(inspect.getfile(obj))
        runtime[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    print(json.dumps(dict(hashes=hashes, runtime=runtime, rows=rows), indent=2))


if __name__ == "__main__":
    main()
