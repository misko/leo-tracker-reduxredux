"""Hash-only preparation of the bounded saved-state diagnostic; never execute it."""

import datetime
import hashlib
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def build_plan(upstream, member, chosen, sources, upstream_digest):
    assert member in upstream["members"]
    assert member["member"]["inventory_label"] == "DS17-033"
    assert len(chosen) == 6 and len({row[0] for row in chosen}) == 6
    assert all(sources.get(k) == v for k, v in upstream["source_sha256"].items())
    return dict(
        member=member,
        saved_states=[list(row) for row in chosen],
        upstream_protocol_sha256=upstream_digest,
        source_sha256=sources,
        maximum_seconds=120,
        maximum_full_objective_calls=6,
        maximum_fixed_mask_likelihood_calls=6,
        optimizer_calls=0,
        maximum_workers=1,
        threads_per_worker=1,
        deadline="Soft between-call checks including reconstruction; overruns reported",
        selection="Six immutable failed-prefit/probe/Newton states, no new perturbation",
        reference_scope="Inherited107/51 provenance admission only, no reference evaluation",
        instrumentation_limits="No full KKT/horizon margins; no position-improvement claim",
        queue="After110 and111, without displacing107",
    )


def prepare():
    previous = HERE.parent / "2026_10_09_position_error_iter107"
    path = previous / "protocol.json"
    upstream = json.loads(path.read_text())
    sources = dict(upstream["source_sha256"])
    for name, expected in sources.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    receipt_path = previous / "results/DS17-033/candidate.json"
    receipt = json.loads(receipt_path.read_text())
    member = next(
        m for m in upstream["members"] if m["member"].get("inventory_label") == "DS17-033"
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["label"] == "DS17-033" and receipt["phase"] == "candidate"
    assert receipt["protocol_sha256"] == digest and receipt["status"] == "complete"
    chosen = runpy.run_path(str(HERE / "run.py"))["states"](receipt)
    for file in [
        path,
        receipt_path,
        *sorted(HERE.glob("*.py")),
        HERE / "PLAN.md",
        HERE / "README.md",
    ]:
        sources[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    plan = build_plan(upstream, member, chosen, sources, digest)
    plan["frozen_utc"] = datetime.datetime.now(datetime.UTC).isoformat()
    return plan


if __name__ == "__main__":
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
        stream.write("\n")
