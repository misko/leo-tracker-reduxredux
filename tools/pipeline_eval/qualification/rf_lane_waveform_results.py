"""Seal the measured exclusive RF acquisition and the complete independent ledgers."""

import argparse
import gzip
from collections import Counter
from pathlib import Path

from .. import original_receiver, whole_iq
from ..__main__ import local_output, save_json, write
from . import paced_controlled_source
from . import parallel_acquisition as replay
from . import parallel_acquisition_results as results
from . import parallel_acquisition_source as staging
from . import rf_lane_waveform as trial
from .full_v5_check import _sha

BASELINE_SHA = "4ecd18e9a91b84ee40056141df5073ea10eb3e55934382f1db54156528b05417"


def check_resource_limits(snapshot, cpu, memory):
    expected = {
        "memory.max": memory,
        "memory.swap.max": 0,
        "memory.swap.current": 0,
        "memory.events.oom": 0,
        "memory.events.oom_kill": 0,
    }
    if any(snapshot[key] != value for key, value in expected.items()):
        raise ValueError("replay service exceeded its measured memory or swap boundary")
    if cpu is not None and snapshot["cpus"] != [cpu]:
        raise ValueError("replay service aggregate came from the wrong CPU allocation")


def audit_case(work, stage, report, case):
    source_dir, raw = stage / case, work / case
    spec, ready, events, _ = replay.source_input(source_dir)
    route = trial.routing_evidence(spec, events)
    plan = whole_iq.read(raw / "plan.json")
    peak = original_receiver.selector_evidence("row-wise", Path(spec["producer"]))
    cpus = dict(zip((*replay.ROLES, "publisher"), trial.CPUS[case], strict=True))
    if (
        plan["cpus"] != cpus
        or spec["cpu"] != cpus["publisher"]
        or plan["waiting_slots"] != 1
        or plan["peak_selector"] != peak
        or any(ready[phase]["cpu"] != spec["cpu"] for phase in ("start", "end"))
    ):
        raise ValueError("launch plan changed the prospective lane or measured CPU reservation")
    before, after = ready["start"], ready["end"]
    if before["cgroup"] != after["cgroup"] or after["memory.stat.shmem"] < ready["bytes"]:
        raise ValueError("the separate stage service does not own the complete staged IQ")
    source = whole_iq.read(raw / "source-resources.json")
    for snapshot in (before, after, *source["stage_charge"].values()):
        check_resource_limits(snapshot, None, paced_controlled_source.CAP)
        if snapshot["cgroup"] != after["cgroup"]:
            raise ValueError("staging charge moved to another cgroup before replay completion")
    if any(r["memory.stat.shmem"] < ready["bytes"] for r in source["stage_charge"].values()):
        raise ValueError("staged IQ must remain charged to its source cgroup during replay")
    for role, cpu in cpus.items():
        resources = source if role == "publisher" else whole_iq.read(raw / f"{role}-resources.json")
        for phase in ("startup", "start", "end"):
            check_resource_limits(resources[phase], cpu, whole_iq.MEMORY)
        if len({resources[phase]["cgroup"] for phase in ("startup", "start", "end")}) != 1:
            raise ValueError("replay process changed cgroup across its measured interval")
    audited, files = results.audit_case(work, stage, report, case, routing=route)
    counts = Counter(event["center_hz"] for event in events if event["status"] == "processed")
    original_assigned = counts[route["selected_rf_hz"]]
    assigned_by_role = dict(
        original=original_assigned, wide=sum(counts.values()) - original_assigned
    )
    for role in replay.ROLES:
        branch = audited["branches"][role]
        assigned = assigned_by_role[role]
        summary = branch["summary"]
        dispositions = summary["counts"]
        if (
            dispositions.get("queued", 0) + dispositions.get("dropped_busy", 0) != assigned
            or dispositions.get("unassigned", 0) + assigned != audited["valid_visits"]
            or dispositions.get("invalid_capture", 0) != audited["invalid_visits"]
        ):
            raise ValueError("recorded branch admissions did not partition all valid stereo visits")
        summary["assigned_visits"] = assigned
        summary["cpu_per_assigned_visit_ns"] = summary["worker_cpu_ns"] / assigned
    return dict(
        audited,
        routing=route,
        selected_rf_hz=route["selected_rf_hz"],
        valid_visits_by_rf_hz=counts,
        peak_selector=peak,
        cpus=cpus,
    ), files


def publish(work, stage, report):
    manifest = report / "manifest.json"
    if manifest.exists():
        raise FileExistsError("the exclusive RF acquisition is already sealed")
    cases, files = {}, ["PROTOCOL.md"]
    for case in trial.CPUS:
        cases[case], names = audit_case(work, stage, report, case)
        files.extend(names)
    previous = whole_iq.checked(staging.REPORT / manifest.name, BASELINE_SHA)
    source_cost = dict(
        cases={case: row["stage"] for case, row in cases.items()},
        scope="complete authenticated IQ predecoded into separately charged host tmpfs",
        measurement="original monotonic delivery offsets and concurrent bounded worker service",
        worker_budget_s=replay.BUDGET_S,
        staging_budget_s=staging.STAGE_LIMIT_S,
        waiting_slots=replay.CAPACITY - 1,
    )
    save_json(report / "stage.json", source_cost)
    files.append("stage.json")
    sources = {}
    for path in trial.PROGRAMS:
        source = work / "measured-sources" / path.name
        name = f"{path.name}.gz"
        write(report / name, gzip.compress(source.read_bytes(), mtime=0))
        files.append(name)
        sources[str(path)] = dict(archive=name, sha256=_sha(source))
    save_json(
        manifest,
        dict(
            schema_version=1,
            cutoff="last scheduled physical delivery, including hardware-invalid captures",
            cases=cases,
            stage="stage.json",
            measured_sources=sources,
            legacy_clock_control=dict(
                manifest=str(previous),
                sha256=BASELINE_SHA,
                matching_peak_selector=False,
                note="The previous simultaneous replay used the installed original peak selector.",
            ),
            files={name: _sha(report / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=trial.WORK)
    parser.add_argument("--stage", type=Path, default=trial.STAGE)
    parser.add_argument("--report", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    publish(args.work, args.stage, args.report)
