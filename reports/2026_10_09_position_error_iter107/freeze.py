"""Seal metadata/full source closure and reviewed coarse policy; launch nothing."""

import datetime
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location("freeze107_" + name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run = load_script("run")
batch = load_script("batch")
policy = load_script("old_coarse_policy")
interleave, label, OLD = batch.interleave, batch.label, policy.OLD


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def closure():
    hashes = {}
    for name in ("2026_10_09_position_error_iter105", "2026_10_09_position_error_iter106"):
        protocol = HERE.parent / name / "protocol.json"
        plan = json.loads(protocol.read_text())
        for source, expected in plan["source_sha256"].items():
            assert digest(ROOT / source) == expected, source
            if source in hashes:
                assert hashes[source] == expected, "Conflicting upstream closures"
            hashes[source] = expected
        hashes[str(protocol.relative_to(ROOT))] = digest(protocol)
    paths = set((HERE / "documents").glob("*.json"))
    paths.update(
        HERE / name
        for name in (
            "source-plan.json",
            "source-preflight.json",
            "source_plan.py",
            "source_adapters.py",
            "source_preflight.py",
            "old_coarse_policy.py",
            "test_old_coarse_policy.py",
            "SOURCE_REVIEW.md",
            "OLD_COARSE_PROPOSAL.md",
            "cohort.py",
            "run.py",
            "controller.py",
            "batch.py",
            "freeze.py",
            "test_run.py",
            "test_batch.py",
            "DRIVER.md",
            "README.md",
        )
    )
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if (
            path.is_file()
            and path.suffix in (".py", ".so")
            and (
                path.is_relative_to(ROOT / "reports")
                or path.is_relative_to(ROOT / "src/leo")
                or "/worker/src/leo/" in str(path)
            )
        ):
            paths.add(path)
    for path in paths:
        key = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        hashes[key] = digest(path)
    return hashes


def main():
    destination = HERE / "protocol.json"
    assert not destination.exists(), "Preserve frozen protocol"
    source = json.loads((HERE / "source-plan.json").read_text())
    members = interleave(source["members"])
    counts = Counter(m.get("dataset", m["member"].get("dataset")) for m in members)
    assert counts == dict(DS16=63, DS17=51, DS18=34, **{"POST18-development": 45})
    labels = [label(member) for member in members]
    assert len(labels) == len(set(labels)) == 193
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        members=members,
        labels=labels,
        slice_seconds=500,
        maximum_slices_per_phase=6,
        phases=["baseline", "candidate"],
        maximum_workers=2,
        threads_per_worker=1,
        shards=2,
        ordering="Round-robin DS16/DS17/DS18/newer, lexical labels; no outcome priority",
        b7_policy=run.B7_POLICY,
        hard60_configuration=run.pilot.core.json_value(run.Hard60Configuration()),
        allow_reviewed_legacy_coarse=True,
        legacy_coarse_known_hashes=OLD,
        legacy_coarse_scope=(
            "Only exact historical baseline point -> b7-shared point; literal metadata and "
            "runtime identity/objective/feasibility/KKT checks; no completed-stage aliases"
        ),
        baseline=(
            "All three current ordinary passes/current existing recovery and fresh unchanged B7; "
            "no blind reuse of105 endpoints"
        ),
        candidate=(
            "Unchanged105 direct102 prefit/fresh103 correction-postfit optional102 polish; "
            "retain ordinary candidates"
        ),
        c_scope="Shared calibration/association, matched c=0/fitted-c final and B7 arms",
        failures=(
            "All193 remain in coverage; terminal baseline failure means candidate not run; "
            "six-slice exhaustion retains baseline fallback"
        ),
        reference_scope=(
            "Known coordinates/errors never choose seeds/regions/winners; historical51 archived "
            "error equality is immutable provenance validation only "
            "(see106 REFERENCE_DEPENDENCY_AUDIT)"
        ),
        scope="Consumed development census; no reserve access, RF or deployment",
        source_sha256=closure(),
    )
    run.write(destination, plan)
    print("Frozen193-member research protocol; no numerical work launched", flush=True)


if __name__ == "__main__":
    main()
