"""Fit matched historical recordings under the prospectively frozen retry timer and hash."""

import argparse
import subprocess
from pathlib import Path

from .. import whole_iq
from ..__main__ import save_json, write
from . import adaptive_arrival_position as position
from . import arrival_queue, bracketed_position, parallel_position, retry_cadence_trial
from . import retry_policy_holdout_results as frozen
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file

REPORT = retry_cadence_trial.REPORT.parent / "retry-policy-retrospective"
POLICY = frozen.trial.REPORT / "policy-lock.json"
POLICY_SHA256 = "ca36b6bc3483bcd51ad8309e753da8fe347a1250a4b03ab5e378c59b074b6f35"
CPUS = (16, 18)
ORDERS = {
    "DS26-0237": (CPUS[0], (frozen.TWO, frozen.CONTROL)),
    "DS29-0082": (CPUS[1], (frozen.CONTROL, frozen.TWO)),
}
COUNTS = {"DS26-0237": (1063, 392, 303), "DS29-0082": (650, 193, 147)}
METHODS = {
    frozen.TWO: "retry_retrospective_two_failures",
    frozen.CONTROL: "retry_retrospective_hash",
    frozen.FULL: "retry_retrospective_full_conditional",
}
COHORT = "Prior capture cases · retrospective"


def check_policy():
    seal = whole_iq.read(whole_iq.checked(POLICY, POLICY_SHA256))
    if seal["case"] != "DS26-0162" or not set(METHODS).issubset(seal["rules"]):
        raise ValueError("use the independent third-case selector freeze")
    for path, sha in seal["implementation"].items():
        whole_iq.checked(Path(path), sha)
    return seal


def measured_support(ident, original, primary):
    full, initial, events, schedules, summary = frozen.counters(ident, original, primary)
    by_mode = {row["policy"]: row for row in summary}
    a, h = by_mode[frozen.TWO], by_mode[frozen.CONTROL]
    if (
        h["attempts"] != a["attempts"]
        or (a["attempts"], a["rescues"], h["rescues"]) != COUNTS[ident]
    ):
        raise ValueError("retrospective counts disagree with the independent holdout team's census")
    return full, initial, events, schedules, by_mode


def bind(case):
    return dict(
        paired_capture_sha256=case["native"]["sha256"],
        original_request_sha256=case["request"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        tile=case["regions"][0],
    )


def materialize(ident, original, primary, full, selection, policy, input_key):
    doc = frozen.policy_input(original, primary, full, selection, policy, input_key)
    doc["provenance"]["scope"] = f"Complete {ident} factors with historical retry policy {policy}"
    parallel_position.physical_match(doc, original)
    return doc


def stage(work, out):
    if not work.is_relative_to(Path("/var/tmp")) or bracketed_position.LIMIT != 210:
        raise ValueError("use the frozen ext4 workspace and 210-second cap")
    filesystem = subprocess.check_output(
        ["findmnt", "-n", "-o", "FSTYPE", "-T", "/var/tmp"], text=True
    )
    if filesystem.strip() != "ext4":
        raise ValueError("position scratch must use ext4")
    if work.exists() or (out / "selection-lock.json").exists():
        raise FileExistsError("choose an unused retrospective work scope")
    check_policy()
    work.mkdir()
    out.mkdir(parents=True, exist_ok=True)
    write(out / "holdout-policy-lock.json", POLICY.read_bytes())
    jobs, support, full_rows, cases, files = (
        [],
        [],
        [],
        {},
        ["holdout-policy-lock.json", "PROTOCOL.md"],
    )
    for ident, (cpu, order) in ORDERS.items():
        original, primary, release, reference = retry_cadence_trial.sources(ident)
        case, request = whole_iq.binding(ident)
        binding = bind(case)
        if (
            any(reference[k] != value for k, value in binding.items())
            or original["source"]["session_id"] != case["session_id"]
            or request["job"]["search_center"] != binding["tile"]["center"]
        ):
            raise ValueError("position comparator belongs to another causal request")
        full, initial, events, schedules, by_mode = measured_support(ident, original, primary)
        selection = f"selection/{ident}.json.gz"
        arrival_queue.writegz(
            out / selection,
            [
                dict(
                    visit=v,
                    receiver=key[0],
                    actual_rf_hz=key[1],
                    monotonic_ns=t,
                    rescue=hit,
                    timer=v in schedules[frozen.TWO],
                    hash=v in schedules[frozen.CONTROL],
                )
                for v, key, t, hit in events
            ],
        )
        files.append(selection)
        cases[ident] = dict(
            **binding,
            holdout_policy_sha256=POLICY_SHA256,
            selection_sha256=_sha(out / selection),
            seed=original["source"]["input_manifest_sha256"],
            parent_locks=retry_cadence_trial.PARENTS[ident],
            causal_snapshots=request["causal_snapshots"],
            compact_receiver=release["receiver"],
            receiver_files=release["receiver_files"],
        )
        full_rows.append(
            dict(
                reference,
                method=METHODS[frozen.FULL],
                policy=frozen.FULL,
                cohort=COHORT,
                comparison_origin="Sealed full-conditional compact result",
            )
        )
        for policy in (*order, frozen.FULL):
            support.append(by_mode[policy])
        for policy in order:
            folder = work / ident / policy
            folder.mkdir(parents=True)
            native = materialize(
                ident,
                original,
                initial,
                full,
                schedules[policy],
                policy,
                _sha(out / selection),
            )
            native_sha, request_sha = position.position_input(
                folder, case, request, release, native, cpu
            )
            files.append(f"requests/{ident}-{policy}.json")
            write(out / files[-1], (folder / "request.json").read_bytes())
            jobs.append(
                dict(
                    id=ident,
                    mode="matched-tile",
                    cohort=COHORT,
                    policy=policy,
                    method=METHODS[policy],
                    comparison_origin="Fresh independent compact position service",
                    cpu=cpu,
                    native_sha256=native_sha,
                    position_request_sha256=request_sha,
                    positive_probes=by_mode[policy]["positives"],
                    **binding,
                )
            )
    csv_file(out / "retry-counts.csv", support)
    files.append("retry-counts.csv")
    save_json(
        out / "selection-lock.json",
        dict(
            cases=cases,
            jobs=jobs,
            full_conditional=full_rows,
            program_sha256=_sha(Path(__file__)),
            cap_s=bracketed_position.LIMIT,
            files={n: _sha(out / n) for n in files},
        ),
    )
    print([(s["id"], s["policy"], s["attempts"], s["rescues"]) for s in support], flush=True)


def run(work, out):
    report = out / "selection-lock.json"
    lock = whole_iq.read(report)
    if lock["program_sha256"] != _sha(Path(__file__)) or lock["cap_s"] != bracketed_position.LIMIT:
        raise ValueError("position plan and runtime must match the staged job")
    for name, sha in lock["files"].items():
        whole_iq.checked(out / name, sha)
    check_policy()
    if any((work / r["id"] / r["policy"] / "service.json").exists() for r in lock["jobs"]):
        raise FileExistsError("run once with an independent service per policy and case")
    data = parallel_position.fit_jobs(work, out, lock["jobs"], CPUS)
    files = set(lock["files"]) | {"selection-lock.json", "positions.jsonl.gz"}
    for row in data:
        path = work / row["id"] / row["policy"]
        for name in ("service.json", "start.json", "end.json"):
            if (path / name).is_file():
                relative = f"services/{row['id']}-{row['policy']}-{name}"
                write(out / relative, (path / name).read_bytes())
                files.add(relative)
        if row["service_log"]:
            files.add(row["service_log"])
    rows = sorted(data + lock["full_conditional"], key=lambda r: (r["id"], r["policy"]))
    pack(out / "positions.jsonl.gz", rows)
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=sorted(ORDERS),
            files={name: _sha(out / name) for name in sorted(files)},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("work", type=Path)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    {"stage": stage, "run": run}[args.action](args.work.resolve(), args.out.resolve())
