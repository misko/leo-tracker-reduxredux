"""Prepare saved-endpoint diagnostic freeze; never launch numerical work."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def plan_from_pilot(pilot, sources, pilot_digest):
    assert len(pilot["potential_members"]) == 148 and len(pilot["members"]) == 12
    assert len({b["member"]["session_id"] for b in pilot["members"]}) == 12
    assert all(b in pilot["potential_members"] for b in pilot["members"])
    for dataset in ("DS16", "DS17", "DS18"):
        assert sum(b["member"]["dataset"] == dataset for b in pilot["members"]) == 4
    return dict(
        pilot_protocol_sha256=pilot_digest,
        members=pilot["members"],
        potential_members=pilot["potential_members"],
        frozen_sha256=sources,
        optimizer_calls=0,
        maximum_workers=2,
        threads_per_worker=1,
        shards=2,
        design_budget_bytes=512 * 1024**2,
        chunk_rows=4096,
        projection_algorithm="Globally normalized joint spatial/nuisance streamed thin QR",
        workspace_policy="Three full-design copies plus fixed chunk and small-factor allowance",
        svd_rtol=None,
        arms=["fitted-c", "zero-c"],
        endpoint_policy="Ordinary archived B7 endpoints only",
        scope="Complete-data projected PSD proxy; fixed-nuisance affine observed spatial block",
        bounds_omitted=True,
        observed_schur_complement=None,
        reference_scope="Inherited provenance admission only; no reference-guided decisions",
        failures="All12 retained; resource/input failures explicit; no replacement",
    )


def prepare():
    path = HERE.parent / "2026_10_09_position_error_iter110/protocol.json"
    pilot = json.loads(path.read_text())
    sources = dict(pilot["source_sha256"])
    for name, expected in sources.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for file in sorted(HERE.iterdir()):
        if file.is_file() and file.suffix in (".py", ".md"):
            sources[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    plan = plan_from_pilot(pilot, sources, hashlib.sha256(path.read_bytes()).hexdigest())
    plan["frozen_utc"] = datetime.datetime.now(datetime.UTC).isoformat()
    return plan


def main():
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print("Saved-endpoint diagnostic frozen; no recording evaluated")


if __name__ == "__main__":
    main()
