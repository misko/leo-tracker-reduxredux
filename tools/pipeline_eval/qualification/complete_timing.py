"""Reconstruct the official four/five-region runtime companion from sealed receipts."""

import argparse
from hashlib import sha256
from pathlib import Path
from statistics import median

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from . import complete_detector_roster as roster
from . import wide_roster as historic
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

SCREEN = roster.SCREEN
REPORT = roster.BASE / "complete-timing"
CROSS = SCREEN / "support-preserving/fifth-crossover"
UNION = SCREEN / "support-preserving/whole-center-union"
PHYSICAL = ("raw_authority", "clock_sha256", "excluded_sha256", "probes_sha256")
RELEASES = {
    roster.FOUR: historic.STOCK_SHA,
    roster.FIVE: "3d1d1451b151b36dbcd6750326396bbfe6a1b0c5bd5b79e7555676ad65ba2342",
}
STAGES = ("raw", "assembly", "position")


class Evidence:
    def __init__(self):
        self.hashes = {}
        self.documents = {}

    def file(self, path, digest=None):
        name = str(path.relative_to(SCREEN))
        if name not in self.hashes:
            self.hashes[name] = _sha(path)
        if digest is not None and self.hashes[name] != digest:
            raise ValueError(f"Sealed receipt changed: {name}")
        return path

    def read(self, path, digest=None):
        self.file(path, digest)
        if path not in self.documents:
            self.documents[path] = whole_iq.read(path)
        return self.documents[path]

    def member(self, folder, seal, name):
        return self.read(folder / name, seal["files"][name])

    def rows(self, folder, seal, name):
        return rows_from(self.file(folder / name, seal["files"][name]))


def release(plan):
    files = dict(plan["receiver_files"])
    files.pop("native/manifest.json", None)  # The normalized historical audit binds relocation.
    return sha256(encoded(dict(files=files, native_sources=plan["native_sources"]))).hexdigest()


def receipt_status(position, resources):
    position_status = position["result"]["status"]
    service_status = resources["service"]["systemd"].get("Result")
    if (position_status in ("ok", "withheld")) != (service_status == "success"):
        raise ValueError("Position and final native service statuses disagree")
    return position_status, service_status


def clock_budget(raw_s, worker_s, span):
    return (
        raw_s <= span if raw_s is not None and span is not None else None,
        worker_s <= span if worker_s is not None and span is not None else None,
    )


def observed(source, case, plan, position, resources, deadline, *, method, full_raw=True):
    ident = case.get("id", position["id"])
    capture = case.get("capture_native_sha256", case.get("capture_era_native_sha256"))
    if (
        ident != position["id"]
        or capture
        != position.get("paired_capture_sha256", position.get("capture_era_native_sha256"))
        or any(
            position[k] != case[j]
            for k, j in (
                ("catalog_sha256", "catalog_sha256"),
                ("original_request_sha256", "request_sha256"),
                ("tile", "tile"),
            )
        )
    ):
        raise ValueError(f"Input identity differs for {ident}")
    if (plan["memory_max"], plan["swap_max"]) != (whole_iq.MEMORY, 0):
        raise ValueError(f"Resource cap differs for {ident}")
    if resources.get("detector_sha256", RELEASES[method]) != RELEASES[method]:
        raise ValueError(f"Wrong detector release for {ident}")
    status, service_status = receipt_status(position, resources)
    marks = resources.get("stages", [])
    if any(
        m["memory.max"] != whole_iq.MEMORY
        or m["memory.swap.max"] != 0
        or m["memory.swap.current"] != 0
        for m in marks
    ):
        raise ValueError(f"Actual resource cap differs for {ident}")
    counts = resources.get("counts", {})
    calls = resources.get("dual_calls")
    within = resources.get("within_20ms")
    if full_raw and (
        counts["recording_windows"] != case["recording"]["window_count"]
        or counts["processed_windows"] + counts["invalid_capture"] != counts["recording_windows"]
        or counts["probe_rows"] != 2 * counts["processed_windows"]
        or counts["iq_bytes"] != 1_600_000 * counts["recording_windows"]
        or calls != counts["processed_windows"]
        or not 0 <= within <= calls
        or resources["input_manifest_sha256"] != case["clock_authority"]
        or any(not resources.get(key) for key in PHYSICAL)
        or any(
            resources[key]["n"] != calls
            for key in (
                "detector_call_wall_ms",
                "detector_call_cpu_ms",
            )
        )
    ):
        raise ValueError(f"Complete raw support or call inventory differs for {ident}")
    span = counts.get("window_delivery_span_s")
    raw_s, assembly_s, position_s = (resources.get(f"{k}_s") for k in STAGES)
    worker_s = resources.get("wall_s")
    raw_realtime, worker_realtime = clock_budget(raw_s if full_raw else None, worker_s, span)
    if worker_s is not None and (
        len(marks) != 4
        or abs(worker_s - sum((raw_s, assembly_s, position_s))) > 2e-5
        or abs(worker_s - (marks[-1]["monotonic_s"] - marks[0]["monotonic_s"])) > 2e-5
    ):
        raise ValueError(f"Complete-stage timing does not reconcile for {ident}")
    if len(marks) == 4 and worker_s is not None:
        cpu = [r["cpu.stat.usage_usec"] / 1e6 for r in marks]
        cpu_by_stage = {
            f"{k}_cpu_s": b - a for k, a, b in zip(STAGES, cpu[:-1], cpu[1:], strict=True)
        }
        if abs(sum(cpu_by_stage.values()) - resources["cpu_s"]) > 2e-5:
            raise ValueError(f"CPU clocks do not reconcile for {ident}")
    else:
        cpu_by_stage = {}
    service = resources["service"]
    systemd_cpu = service["systemd"].get("CPUUsageNSec")
    journal = service.get("service_wall_s")
    journal_events = service.get("monotonic", {})
    if journal is not None and journal_events.get("terminal_event_usec") is not None:
        interval = journal_events["terminal_event_usec"] - journal_events["start_event_usec"]
        if abs(journal - interval / 1e6) > 1e-6:
            raise ValueError(f"Journal elapsed time differs from its service clocks for {ident}")
    position_arms = position["result"].get("arms") or {}
    payload = dict(
        id=ident,
        method=method,
        source=source,
        service_unit=service["unit"],
        service_result=service_status,
        position_status=status,
        both_positions=all(
            (position_arms.get(a) or {}).get("latlon") is not None for a in ("c0", "fitted_c")
        ),
        scientific_outcome_sha256=sha256(encoded(roster.scientific_outcome(position))).hexdigest(),
        clock_authority=case["clock_authority"],
        capture_sha256=capture,
        request_sha256=case["request_sha256"],
        catalog_sha256=case["catalog_sha256"],
        native_sha256=position.get("native_sha256"),
        detector_sha256=RELEASES[method],
        receiver_release_sha256=release(plan),
        full_raw_verified=full_raw,
        scheduled_windows=case["recording"]["window_count"],
        detector_calls=calls,
        detector_wall_within_20=within,
        detector_wall_fraction=within / calls if calls else None,
        invalid_visits=counts.get("invalid_capture"),
        recorded_clock_span_s=span,
        raw_s=raw_s,
        assembly_s=assembly_s,
        position_s=position_s,
        worker_s=worker_s,
        raw_within_recorded_span=raw_realtime,
        worker_within_recorded_span=worker_realtime,
        worker_cpu_s=resources.get("cpu_s"),
        detector_cpu_s=counts.get("detector_cpu_s"),
        service_journal_s=journal,
        service_supervisor_s=service.get("supervisor_s"),
        service_cgroup_cpu_s=int(systemd_cpu) / 1e9 if str(systemd_cpu).isdigit() else None,
        timeout_or_failure_s=resources.get("wall_to_failure_s"),
        cpu_to_failure_s=resources.get("cpu_to_failure_s"),
        service_deadline_s=deadline,
        peak_bytes=resources.get("max_bytes", resources.get("charged_peak_to_failure_bytes")),
        start_monotonic_s=marks[0]["monotonic_s"] if marks else None,
        end_monotonic_s=marks[-1]["monotonic_s"] if worker_s is not None else None,
        cores=marks[0]["cpus"] if marks else None,
        nice=marks[0]["nice"] if marks else None,
        boot_id=service.get("binding", {}).get("boot_id"),
        service_log_sha256=service.get("log_sha256"),
        **cpu_by_stage,
        **{k: resources.get(k) for k in PHYSICAL},
    )
    for boundary in ("wall", "cpu"):
        quantile = resources.get(f"detector_call_{boundary}_ms", {})
        for k in ("p50", "p95", "p99", "max"):
            payload[f"detector_call_{boundary}_{k}_ms"] = quantile.get(k)
    return payload


def from_archive(evidence, entry, registry, pinned_release):
    source = registry["studies"][entry["study"]]
    folder = SCREEN / source["path"]
    seal = evidence.read(folder / "prediction-lock.json", source["prediction_sha256"])
    plan = evidence.member(folder, seal, "source-lock.json")
    assets = evidence.member(folder, seal, "resources.json")
    ident, branch = entry["id"], source["branch"]
    resources = assets[ident] if branch == "wide" else assets[ident][branch]
    if (
        release(plan) != pinned_release
        or sha256(encoded(plan["receiver_files"])).hexdigest() != entry["receiver_files_sha256"]
        or entry["service_unit"] != resources["service"]["unit"]
        or entry["service_log_sha256"] != resources["service"]["log_sha256"]
        or any(
            entry.get(k) != resources.get(k)
            for k in (
                "raw_s",
                "wall_s",
                "cpu_s",
                "within_20ms",
                "dual_calls",
                "wall_to_failure_s",
                "detector_sha256",
            )
        )
    ):
        raise ValueError(f"Stock attempt mismatch for {ident}")
    return observed(
        source["path"],
        plan["cases"][ident],
        plan,
        entry,
        resources,
        entry["deadline_s"],
        method=roster.FOUR,
        full_raw=entry["full_raw_verified"],
    )


def local_pairs(evidence, folder, seal, roles, methods, base):
    plan = evidence.member(folder, seal, "source-lock.json")
    if release(plan) != release(base):
        raise ValueError("Installed position receiver release changed")
    # These resource objects include the complete detector call summaries and service receipts.
    data = evidence.member(folder, seal, "resources.json")
    rows = evidence.rows(folder, seal, "positions.jsonl.gz")
    cases = list(data)
    by_role = {
        role: roster.select(rows, name, cases) for role, name in zip(roles, methods, strict=True)
    }
    values = {}
    for role, method in zip(roles, (roster.FOUR, roster.FIVE), strict=True):
        values[method] = {}
        for ident, resources in data.items():
            resource = resources[role]
            position = by_role[role][ident]
            candidate = plan["cases"][ident]
            budget = resource.get("planned_deadline_s", plan["limit_s"])
            if role in plan["detectors"] and plan["detectors"][role]["sha256"] != RELEASES[method]:
                raise ValueError("Released detector SHA differs from roster")
            if folder == UNION and role == "candidate":
                active = evidence.member(folder, seal, "candidate-lock-v2.json")
                if active["assets"]["candidate"]["sha256"] != RELEASES[method]:
                    raise ValueError("Union release differs from the qualified fifth detector")
            raw_name = (
                f"native/{ident}.json.gz" if role == "union" else f"native/{role}/{ident}.json.gz"
            )
            if raw_name in seal["files"]:
                evidence.file(folder / raw_name, seal["files"][raw_name])
            log_name = f"{ident}.service.log" if role == "union" else f"{ident}-{role}.service.log"
            if log_name in seal["files"]:
                evidence.file(folder / log_name, resource["service"]["log_sha256"])
                evidence.file(folder / log_name, seal["files"][log_name])
            if folder == CROSS and role == "control":
                historical = evidence.member(folder, seal, "historical-authority.json")
                parent_sha = historical["parents"]["whole-replay"]["prediction_sha256"]
                if (
                    historical["native"][f"{ident}/control"]["native_sha256"]
                    != (position["native_sha256"])
                ):
                    raise ValueError("Crossover stock points to a different native position")
                if ident in historical["parents"]["whole-replay"]["cases"]:
                    parent = SCREEN / "acquisition-frontier/whole-replay"
                    parent_seal = evidence.read(parent / "prediction-lock.json", parent_sha)
                    historical_resource = evidence.member(parent, parent_seal, "resources.json")[
                        ident
                    ]["control"]
                    if historical_resource["service"]["unit"] != resource["service"]["unit"]:
                        raise ValueError("Crossover matched another historical service invocation")
            values[method][ident] = observed(
                str(folder.relative_to(SCREEN)),
                candidate,
                plan,
                position,
                resource,
                budget,
                method=method,
            )
    return values


def completion(evidence, plan, ids, pending):
    folder = roster.TEN
    path = folder / "prediction-lock.json"
    seal = evidence.read(path) if path.is_file() else None
    if seal is not None:
        evidence.file(folder / "source-lock.json", seal["files"]["source-lock.json"])
        if set(seal["cases"]) != set(ids):
            raise ValueError("Fifth completion sealed a different roster")
    elif not pending:
        raise FileNotFoundError("Terminal fifth-completion prediction lock is pending")
    values = {}
    for ident in ids:
        filename = f"attempts/{ident}.json"
        if not (folder / filename).is_file():
            if not pending or seal is not None:
                raise ValueError(f"Missing terminal completion attempt for {ident}")
            values[ident] = dict(
                id=ident,
                method=roster.FIVE,
                source=str(folder.relative_to(SCREEN)),
                service_result="pending",
                position_status="pending",
            )
            continue
        attempt = (
            evidence.member(folder, seal, filename) if seal else evidence.read(folder / filename)
        )
        for name, digest in attempt["files"].items():
            evidence.file(folder / name, digest)
            if seal and seal["files"][name] != digest:
                raise ValueError(f"Completion inner and outer seals differ for {ident}")
        resources, position = attempt["resources"], attempt["row"]
        service = resources["service"]
        authority = attempt["authority"]
        receipts = attempt["files"]
        prefix = f"receipts/{ident}/"
        plan_digest = receipts.get(prefix + "plan.json")
        if plan_digest is not None and service.get("binding", {}).get("plan_sha256") != plan_digest:
            raise ValueError(f"Candidate service launch binding differs for {ident}")
        if receipts.get(prefix + "service.log") != service.get("log_sha256"):
            raise ValueError(f"Candidate service log binding differs for {ident}")
        if plan["detectors"]["candidate"]["sha256"] != RELEASES[roster.FIVE]:
            raise ValueError("Completion uses another fifth release")
        if authority["complete_raw"] and (
            position["native_sha256"] != authority["native_sha256"]
            or any(resources[key] != authority[key] for key in (*PHYSICAL, "input_manifest_sha256"))
        ):
            raise ValueError(f"Candidate result and raw receipt disagree for {ident}")
        row = observed(
            str(folder.relative_to(SCREEN)),
            plan["cases"][ident],
            plan,
            position,
            resources,
            plan["limit_s"],
            method=roster.FIVE,
            full_raw=authority["complete_raw"],
        )
        if row["cores"] is not None and row["cores"] != plan["cases"][ident]["cpus"]:
            raise ValueError(f"Completion service ran on unscheduled cores for {ident}")
        values[ident] = row
    return values


def inputs(pending=False):
    evidence = Evidence()
    groups = evidence.read(roster.REPORT / "roster.json")
    if groups != roster.frozen_roster():
        raise ValueError("Runtime companion requires the exact official roster")
    evidence.file(roster.REPORT / "PROTOCOL.md", groups["protocol_sha256"])
    for path, digest in groups["sources"].items():
        evidence.file(SCREEN / path, digest)
    older = evidence.read(roster.EIGHT / "eight-figure-lock.json")
    old_six_authority = evidence.member(roster.EIGHT, older, "eight-authority.json")
    all_six = evidence.read(
        CROSS / "all-six-figure-lock.json", old_six_authority["original_figure_lock_sha256"]
    )
    six = evidence.member(CROSS, all_six, "six-authority.json")
    cross = evidence.read(CROSS / "prediction-lock.json", six["retrospective_predictions"])
    union = evidence.read(UNION / "prediction-lock.json", six["fresh_predictions"])
    original = evidence.member(roster.EIGHT, older, "prediction-lock.json")
    base = evidence.member(roster.EIGHT, original, "source-lock.json")
    two = evidence.read(roster.TWO / "prediction-lock.json")
    newest = evidence.member(roster.TWO, two, "source-lock.json")
    plan = evidence.read(roster.TEN / "source-lock.json")
    if roster.receiver_identity(plan) != roster.receiver_identity(base) or (
        roster.receiver_identity(newest) != roster.receiver_identity(base)
    ):
        raise ValueError("Fresh or completion pair changed the common receiver release")

    stock, five = {}, {}
    for folder, seal, roles, methods in (
        (CROSS, cross, ("control", "union"), ("fifth_crossover_stock", "fifth_crossover_union")),
        (
            UNION,
            union,
            ("control", "candidate"),
            ("whole_center_union_stock", "whole_center_union"),
        ),
        (
            roster.EIGHT,
            original,
            ("control", "candidate"),
            ("fresh_replay_stock", "fresh_replay_fifth"),
        ),
        (roster.TWO, two, ("control", "candidate"), ("new_waveforms_stock", "new_waveforms_fifth")),
    ):
        arms = local_pairs(evidence, folder, seal, roles, methods, base)
        stock.update(arms[roster.FOUR])
        five.update(arms[roster.FIVE])
    original_pairs = set(groups["original_pair"]) | set(groups["fresh"])
    if set(stock) != original_pairs or set(five) != original_pairs:
        raise ValueError("Source-study roles differ from the official ten local pairs")
    history = evidence.read(roster.TWELVE / "all-figure-lock.json")
    history_run = evidence.member(roster.TWELVE, history, "prediction-lock.json")
    registry = evidence.member(roster.TWELVE, history_run, "roster-lock.json")
    attempts = evidence.member(roster.TWELVE, history_run, "attempts.json")
    primary, earliest = {}, {}
    selected = [r for r in attempts if r["primary"] or r["original_first"]]
    for entry in selected:
        ident = entry["id"]
        row = from_archive(evidence, entry, registry, release(base))
        if entry["primary"]:
            if ident in stock and any(
                row[k] != stock[ident][k]
                for k in (
                    "service_unit",
                    "native_sha256",
                    "scientific_outcome_sha256",
                    "clock_authority",
                    "raw_s",
                    "worker_s",
                )
            ):
                raise ValueError(f"Overlapping fixed primary timing source differs for {ident}")
            primary[ident] = row
        if entry["original_first"]:
            earliest[ident] = row
    if set(primary) != set(groups["original_stock"]) or set(earliest) != set(
        groups["original_stock"]
    ):
        raise ValueError("Historic selected attempts differ from the fixed twelve")
    # The paired releases must bind to the same archived and physical clock even on a timeout.
    stock.update(primary)
    earliest = stock | earliest
    five.update(completion(evidence, plan, groups["fifth_completion"], pending))
    for ident in groups["all"]:
        same_recording(stock[ident], earliest[ident])
        if five[ident]["position_status"] != "pending":
            same_recording(stock[ident], five[ident])
    return groups, stock, five, earliest, evidence


def same_recording(before, after):
    keys = (
        "id",
        "clock_authority",
        "capture_sha256",
        "catalog_sha256",
        "request_sha256",
        "receiver_release_sha256",
        "scheduled_windows",
    )
    if any(before[k] != after[k] for k in keys):
        raise ValueError(f"Pair has different recording or installed solver for {before['id']}")
    if (
        before["full_raw_verified"]
        and after["full_raw_verified"]
        and any(
            before[k] != after[k]
            for k in (*PHYSICAL, "detector_calls", "invalid_visits", "recorded_clock_span_s")
        )
    ):
        raise ValueError(f"Pair has different valid waveform support for {before['id']}")


def context(before, after):
    """Pair provenance distinguishes matched scheduling from later core reuse."""
    if after["position_status"] == "pending":
        return "pending", None
    same = before["cores"] == after["cores"] and before["cores"] is not None
    if before["source"] == after["source"] and before["source"] in {
        str(p.relative_to(SCREEN)) for p in (UNION, roster.EIGHT, roster.TWO)
    }:
        if not same or not before["boot_id"] or before["boot_id"] != after["boot_id"]:
            raise ValueError("Declared same-core pair changed hardware clock or core assignment")
        earlier, later = sorted((before, after), key=lambda r: r["start_monotonic_s"])
        if earlier["end_monotonic_s"] is not None and (
            earlier["end_monotonic_s"] > later["start_monotonic_s"]
        ):
            raise ValueError("Declared sequential services overlapped")
        return "same_core_same_study", "stock_first" if earlier is before else "fifth_first"
    return ("separate_same_cores" if same else "separate_different_cores"), None


def delta(before, after):
    return None if before is None or after is None else after - before


def paired(groups, stock, five):
    out = []
    for ident in groups["all"]:
        control, candidate = stock[ident], five[ident]
        schedule, order = context(control, candidate)
        group = next(
            k for k in ("original_pair", "fifth_completion", "fresh") if ident in groups[k]
        )
        row = dict(
            id=ident,
            cohort=group,
            pair_context=schedule,
            order=order,
            stock_source=control["source"],
            fifth_source=candidate["source"],
            stock_cores=control["cores"],
            fifth_cores=candidate.get("cores"),
        )
        for name in (
            "service_result",
            "position_status",
            "both_positions",
            "detector_calls",
            "detector_wall_within_20",
            "detector_wall_fraction",
            "recorded_clock_span_s",
            "raw_within_recorded_span",
            "worker_within_recorded_span",
            "raw_s",
            "position_s",
            "worker_s",
            "worker_cpu_s",
            "detector_cpu_s",
            "service_journal_s",
            "detector_call_wall_p50_ms",
            "detector_call_cpu_p50_ms",
            "service_deadline_s",
        ):
            row[f"stock_{name}"], row[f"fifth_{name}"] = control.get(name), candidate.get(name)
            if name.endswith(("_s", "_ms", "_fraction")):
                row[f"fifth_minus_stock_{name}"] = delta(control.get(name), candidate.get(name))
        out.append(row)
    return out


def stats(rows):
    verified = [r for r in rows if r.get("full_raw_verified")]
    worker = [r for r in rows if r.get("worker_s") is not None]
    calls = sum(r["detector_calls"] for r in verified)
    fast = sum(r["detector_wall_within_20"] for r in verified)
    result = dict(
        scheduled=len(rows),
        terminal=sum(r["position_status"] != "pending" for r in rows),
        raw_verified=len(verified),
        worker_measured=len(worker),
        both_positions=sum(bool(r.get("both_positions")) for r in rows),
        detector_calls=calls,
        detector_wall_within_20=fast,
        detector_wall_fraction=fast / calls if calls else None,
        raw_within_recorded_span=sum(r.get("raw_within_recorded_span") is True for r in verified),
        worker_within_recorded_span=sum(r["worker_within_recorded_span"] is True for r in worker),
    )
    for name in (
        "raw_s",
        "position_s",
        "worker_s",
        "worker_cpu_s",
        "detector_cpu_s",
        "service_journal_s",
        "detector_call_wall_p50_ms",
        "detector_call_cpu_p50_ms",
    ):
        values = [r[name] for r in rows if r.get(name) is not None]
        result[f"measured_{name}"] = len(values)
        result[f"median_{name}"] = median(values) if values else None
    return result


def summarize(groups, stock, five, early, pairs):
    grouped = {}
    same = {r["id"] for r in pairs if r["pair_context"] == "same_core_same_study"}
    cohorts = {
        k: groups[k]
        for k in ("all", "original_stock", "original_pair", "fifth_completion", "fresh")
    }
    cohorts["same_core_same_study"] = sorted(same)
    cohorts["separate_executions"] = sorted(
        r["id"] for r in pairs if r["pair_context"].startswith("separate")
    )
    for label, ids in cohorts.items():
        grouped[label] = {
            k: stats([rows[i] for i in ids])
            for k, rows in (
                (roster.FOUR, stock),
                (roster.FIVE, five),
                (roster.EARLY, early),
            )
        }
    return grouped


def table(path, rows):
    names = dict.fromkeys(k for row in rows for k in row)
    csv_file(path, [{k: r.get(k) for k in names} for r in rows])


def plot(out, pairs):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.lines import Line2D

    matched = [r for r in pairs if r["pair_context"] == "same_core_same_study"]
    separate = [r for r in pairs if r["pair_context"] != "same_core_same_study"]
    rows = matched + separate
    fig, axs = plt.subplots(1, 3, figsize=(13, 8.5), layout="constrained")
    labels = [r["id"] for r in rows]
    colors = ("#52667A", "#00776F")

    def relative(row, method, field):
        value = row[f"{method}_{field}"]
        span = row[f"{method}_recorded_clock_span_s"]
        return value / span if value is not None and span else None

    panels = (
        (
            "Detector calls completed in 20 ms",
            "Share of measured calls",
            lambda r, m: r[f"{m}_detector_wall_fraction"],
            (0, 1.04),
        ),
        (
            "Raw phase",
            "Elapsed / captured delivery span",
            lambda r, m: relative(r, m, "raw_s"),
            (0, 1.3),
        ),
        (
            "Raw through both position arms",
            "Elapsed / captured delivery span",
            lambda r, m: relative(r, m, "worker_s"),
            (0, 1.32),
        ),
    )
    for side, (ax, (title, xlabel, get, limits)) in enumerate(zip(axs, panels, strict=True)):
        ax.axhspan(-0.5, len(matched) - 0.5, color="#F0F4F7", linewidth=0)
        ax.axhline(len(matched) - 0.5, color="#96A3AE", linewidth=0.7)
        ax.axvline(1, color="#96624A", linewidth=0.8, linestyle="--")
        for i, r in enumerate(rows):
            a, b = (get(r, m) for m in ("stock", "fifth"))
            if a is not None and b is not None:
                ax.plot([a, b], [i, i], color="#C8D0D7", linewidth=1, zorder=2)
            for v, c in zip((a, b), colors, strict=True):
                if v is not None:
                    ax.scatter(v, i, s=22, color=c, zorder=3)
        ax.set(title=title, xlabel=xlabel, xlim=limits, yticks=range(len(rows)))
        ax.set_yticklabels(labels if side == 0 else [])
        ax.set_ylim(len(rows) - 0.5, -0.5)
        ax.grid(axis="x", color="#E4E7EA", linewidth=0.7)
        ax.spines[["top", "right"]].set_visible(False)
    fig.legend(
        handles=[
            Line2D([0], [0], marker="o", color=c, linestyle="", label=label)
            for c, label in zip(
                colors, ("Stock four regions", "Released fifth center"), strict=True
            )
        ],
        loc="outside lower center",
        ncols=2,
        fontsize=8,
        frameon=False,
    )
    fig.suptitle(
        "Complete-IQ host timing on the 20-recording roster\n"
        "Shaded rows share a sequential same-core protocol"
    )
    fig.savefig(out / "stage.png", dpi=150)
    fig.savefig(out / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(out, pending=False):
    groups, stock, five, early, evidence = inputs(pending)
    pairs = paired(groups, stock, five)
    totals = summarize(groups, stock, five, early, pairs)
    out.mkdir(parents=True, exist_ok=True)
    table(out / "stage.csv", pairs)
    table(
        out / "resources.csv", [r for ident in groups["all"] for r in (stock[ident], five[ident])]
    )
    table(
        out / "first-attempt.csv",
        [
            dict(
                early[ident],
                method=roster.EARLY,
                same_as_fixed_primary=(
                    early[ident]["service_unit"] == stock[ident]["service_unit"]
                ),
            )
            for ident in groups["all"]
        ],
    )
    save_json(
        out / "summary.json",
        dict(
            roster=groups,
            groups=totals,
            pair_contexts={
                label: [r["id"] for r in pairs if r["pair_context"] == label]
                for label in sorted({r["pair_context"] for r in pairs})
            },
            position_arm_timing="shared process for c0 and fitted_c",
            complete_cutoff_ms=20,
            measures="offline archived host receipts",
        ),
    )
    plot(out, pairs)
    n = totals["all"][roster.FIVE]["terminal"]
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="complete-timing",
            title="Complete-IQ host deadline and runtime companion",
            sample=f"20 scheduled whole-recording pairs with {n} terminal fifth-center services",
            boundary="Saved complete dual-receiver IQ → detector → assembly and both position arms",
            note="Six pairs share a planned core assignment. Fourteen use separate executions.",
            seal="prediction-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )
    names = (
        "stage.csv",
        "resources.csv",
        "first-attempt.csv",
        "summary.json",
        "stage.png",
        "stage.pdf",
        "stage-figure.json",
    )
    if (out / "README.md").is_file():
        names += ("README.md",)
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=groups["all"],
            files={n: _sha(out / n) for n in names},
            source_receipts=evidence.hashes,
            builder_sha256=_sha(Path(__file__)),
        ),
    )
    return totals


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=REPORT)
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args()
    publish(args.out, args.allow_pending)
