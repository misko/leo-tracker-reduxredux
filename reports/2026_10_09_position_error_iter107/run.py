"""Bounded full193 current-B7 versus generic recovery research driver."""

import argparse
import copy
import hashlib
import os
import time
from dataclasses import replace
from pathlib import Path

from cohort import Sources, load_member, pilot

from leo.application.hard60_b7 import B7_POLICY, SharedPoints, regional_winners, run_joint_stages
from leo.application.hard60_runner import Hard60Configuration, run_hard60
from leo.contracts.digests import canonical_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
read = pilot.read
write = pilot.write


class Overlay(pilot.Overlay):
    """Local immutable operations plus a verified external source get port."""

    def __init__(self, directory, digest, source, deadline):
        super().__init__(directory, digest, HERE, {}, compatible=False)
        self.source, self.deadline = source, deadline
        self.local_hits = 0

    def get(self, key):
        cached = super().get(key)
        if cached is not None:
            self.local_hits += 1
            return cached
        if time.monotonic() >= self.deadline:
            raise pilot.core.RegionalSliceExpired(key)
        return self.source.get(key)


def run_baseline(case, cache, stage, deadline):
    regions = {}
    for name, separation in zip(("baseline", "sep25", "sep50"), (12.5, 25.0, 50.0), strict=True):
        regions[name] = run_hard60(
            case["observations"],
            case["bank"],
            case["prior"],
            case["tracks"],
            SharedPoints(cache),
            configuration=replace(Hard60Configuration(), basin_separation_km=separation),
            maximum_seconds=max(0.001, deadline - time.monotonic()),
        )
    operational, attempts, reasons = run_joint_stages(
        case["observations"],
        case["bank"],
        case["prior"],
        regions,
        lambda key, budget, operation: stage("baseline107:" + key, budget, operation),
    )
    return dict(regions=regions, operational=operational, attempts=attempts, reasons=reasons)


def run_candidate(case, baseline, stage):
    regions = copy.deepcopy(baseline["regions"])
    inventory = pilot.regional_triggers(
        regions,
        input_digest=case["binding"]["input_digest"],
        score_signature=case["binding"]["score_signature"],
        bank_signature=case["binding"]["bank_signature"],
        minimum_local_radius_km=Hard60Configuration().minimum_local_radius_km,
    )
    assert len(inventory["candidates"]) <= 3 * Hard60Configuration().basins
    for trigger in inventory["candidates"]:
        name = "direct107:" + canonical_digest(trigger["identity"])[7:]
        regions[name] = pilot.recovered_region(
            case["observations"], case["bank"], case["prior"], trigger, stage
        )
    operational, attempts, reasons = run_joint_stages(
        case["observations"],
        case["bank"],
        case["prior"],
        regions,
        lambda key, budget, operation: stage("candidate107:" + key, budget, operation),
    )
    return dict(
        regions=regions,
        operational=operational,
        attempts=attempts,
        reasons=reasons,
        inventory=inventory,
        baseline_operational=baseline["operational"],
        regional_before=regional_winners(baseline["regions"]),
        regional_after=regional_winners(regions),
    )


def main(label, phase):
    plan = read(HERE / "protocol.json")
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    assert (
        plan["slice_seconds"] == 500
        and plan["maximum_slices_per_phase"] == 6
        and plan["maximum_workers"] == 2
    )
    assert plan["b7_policy"] == B7_POLICY
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        assert os.environ.get(variable) == "1"
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    sources = read(HERE / "source-plan.json")
    member = next(
        m
        for m in sources["members"]
        if m["member"].get("inventory_label", m["member"].get("dataset_label")) == label
    )
    assert label in plan["labels"]
    directory = HERE / "results" / label
    destination = directory / (phase + ".json")
    baseline_path = directory / "baseline.json"
    if destination.exists():
        assert read(destination)["protocol_sha256"] == digest
        return
    baseline = read(baseline_path) if baseline_path.exists() else None
    if baseline is not None:
        assert baseline["protocol_sha256"] == digest
    if phase == "candidate":
        assert baseline is not None and baseline["status"] == "complete"
    slot = pilot.claim_slice(directory / "slices", phase, digest)
    if slot is None:
        write(
            destination,
            dict(
                status="budget-exhausted",
                phase=phase,
                protocol_sha256=digest,
                operational=baseline["operational"] if baseline else {},
                fallback_available=bool(baseline),
            ),
        )
        return
    report = dict(protocol_sha256=digest, label=label, phase=phase, slice=slot)
    began = time.monotonic()
    deadline = began + 500
    source = None
    cache = None

    def cost_fields():
        elapsed = time.monotonic() - began
        previous = sum(
            read(path).get("elapsed_s", 0)
            for path in (directory / "slices").glob(f"{phase}-*.done.json")
        )
        return dict(
            elapsed_s=elapsed,
            phase_elapsed_s=previous + elapsed,
            cost_scope=(
                "Current slice includes loading and all stage/source work; phase cost sums "
                "persisted done slices, interrupted undelivered slices have unknown duration"
            ),
            source_port_metrics=None if source is None else source.metrics,
            local_checkpoint_hits=0 if cache is None else cache.local_hits,
        )

    try:
        case = load_member(member)
        report["load_seconds"] = time.monotonic() - began
        source = Sources(
            member, case, allow_legacy_coarse=plan.get("allow_reviewed_legacy_coarse", False)
        )
        cache = Overlay(directory / "stages", digest, source, deadline)
        report.update(
            input_binding=case["binding"],
            cache_compatibility=case["ordinary_compatibility"],
            legacy_coarse_eligibility=case["legacy_coarse_eligibility"],
        )

        def stage(key, budget, operation):
            cached = cache.get(key)
            if cached is not None:
                return cached
            if time.monotonic() + budget >= deadline:
                raise pilot.core.RegionalSliceExpired(key)
            try:
                value = dict(result=pilot.core.json_value(operation()), reason=None)
            except (ValueError, TimeoutError, AssertionError) as error:
                value = dict(result=None, reason=f"{type(error).__name__}: {error}")
            cache.put(key, value)
            return value

        result = (
            run_baseline(case, cache, stage, deadline)
            if phase == "baseline"
            else run_candidate(case, baseline, stage)
        )
        write(
            destination,
            dict(
                report,
                status="complete",
                **result,
                source_coarse_audits=source.audits,
                source_rejections=source.failures,
                **cost_fields(),
            ),
        )
        report["status"] = "complete"
    except pilot.core.RegionalSliceExpired as error:
        report.update(status="pending", reason=str(error))
    except Exception as error:
        report.update(status="failed", reason=repr(error))
        write(
            destination,
            dict(
                report,
                operational=baseline["operational"] if baseline else {},
                fallback_available=bool(baseline),
                **cost_fields(),
            ),
        )
    if report["status"] == "pending" and slot == 6:
        report["status"] = "budget-exhausted"
        write(
            destination,
            dict(
                report,
                operational=baseline["operational"] if baseline else {},
                fallback_available=bool(baseline),
                **cost_fields(),
            ),
        )
    report.update(cost_fields())
    write(directory / "slices" / f"{phase}-{slot:02d}.done.json", report)
    print(label, phase, report["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--phase", choices=("baseline", "candidate"), required=True)
    arguments = parser.parse_args()
    main(arguments.label, arguments.phase)
