"""Authenticate complete capture-era shards and compare both compact calibration arms."""

import argparse
import gzip
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distribution, validate_result
from . import capture_whole as trial
from . import scout_stage_figures as plot
from .capture_detector_lineage import compare_rows, keyed_rows
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import BULK, _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .screening_figures import generate
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
ARCHIVED = "capture_archived_factors_compact"
FOUR, FIVE = "complete_four_regions", "complete_five_regions"
POS = "positions.jsonl.gz"
MINIMAL = ("paired_capture_sha256", "original_request_sha256", "catalog_sha256", "tile")


def shard_records(rows, chunks, cpu, planned, source_sha):
    """Trust visit evidence only after its matching compressed chunk closes."""
    accepted, pending = {}, []
    cursor = 0
    terminal = None
    for row in rows:
        if terminal is not None:
            raise ValueError("data appeared after the verified raw terminal")
        kind = row["kind"]
        if kind == "visit":
            pending.append(row)
        elif kind == "chunk":
            if cursor >= len(chunks):
                raise ValueError("raw worker emitted an unassigned chunk")
            segment, first, stop, base = chunks[cursor]
            if (
                (row["segment"], row["first"], row["stop"]) != (segment, first, stop)
                or len(pending) != stop - first
                or row["compressed_bytes"] < 1
                or any(
                    (p["segment"], p["sequence"], p["visit"]) != (segment, i, base + i)
                    for i, p in enumerate(pending, start=first)
                )
            ):
                raise ValueError("raw chunk did not authenticate its exact assigned visit range")
            accepted[(segment, first)] = (row, pending)
            pending = []
            cursor += 1
        elif kind == "worker":
            before, after = row["start"], row["end"]
            if (
                pending
                or cursor != len(chunks)
                or row["cpu"] != cpu
                or row["count"] != planned
                or row["source_lock_sha256"] != source_sha
                or any(
                    timing["cpus"] != [cpu]
                    or timing["memory.max"] != whole_iq.MEMORY
                    or timing["memory.swap.max"] != 0
                    or timing["memory.swap.current"] != 0
                    or timing["memory.events.oom_kill"] != 0
                    for timing in (before, after)
                )
                or before["cgroup"] != after["cgroup"]
                or before["pid"] != after["pid"]
                or before["cpu.stat.usage_usec"] > after["cpu.stat.usage_usec"]
            ):
                raise ValueError("terminal raw resource or work ledger differs from the launch")
            terminal = row
        else:
            raise ValueError("unexpected raw replay record")
    return accepted, terminal


def collect(work, lock):
    exits = whole_iq.read(work / "raw-exits.json")
    launch = whole_iq.read(work / "launch.json")
    source_sha = _sha(work / "source-lock.json")
    if launch["source_lock_sha256"] != source_sha or set(exits["exits"]) != {
        str(c[0]) for c in lock["workers"]
    }:
        raise ValueError("raw process ledger differs from its source and CPU plan")
    shards, workers = {}, {}
    for cpu, valid, chunks in lock["workers"]:
        path = work / f"cpu-{cpu}.jsonl"
        with path.open("rb") as stream:
            accepted, terminal = shard_records(
                (json.loads(line) for line in stream if line.endswith(b"\n")),
                chunks,
                cpu,
                valid,
                source_sha,
            )
        if set(shards) & set(accepted):
            raise ValueError("multiple raw workers own the same chunk")
        if bool(terminal) != (exits["exits"][str(cpu)] == 0):
            raise ValueError("worker terminal and service exit give inconsistent states")
        shards.update(accepted)
        workers[str(cpu)] = dict(
            exit_code=exits["exits"][str(cpu)],
            terminal=terminal,
            chunks=len(accepted),
            output_sha256=_sha(path),
            service_log_sha256=_sha(work / f"cpu-{cpu}.log"),
        )
    return shards, workers, exits["wall_s"]


def assemble(case, lock, shards):
    """Commit real detector rows in capture order through the existing native assembler."""
    expected = {(i, first) for _, _, chunks in lock["workers"] for i, first, _, _ in chunks}
    if expected != set(shards):
        raise ValueError("incomplete raw replay cannot emit complete native factors")
    lanes = ([], [])
    binary_sha = "sha256:" + sha256(encoded(lock["libraries"])).hexdigest()
    for segment in range(len(case["recording"]["segments"])):
        pieces = [shards[key] for key in sorted(shards) if key[0] == segment]
        if (
            not pieces
            or pieces[0][0]["first"] != 0
            or any(x[0]["stop"] != y[0]["first"] for x, y in zip(pieces, pieces[1:], strict=False))
        ):
            raise ValueError("segment has unexpected gaps")
        facts = {tuple(r[k] for k in ("path", "manifest_digest", "radio_id")) for r, _ in pieces}
        if len(facts) != 1:
            raise ValueError("worker receipts disagree about the same segment")
        path, digest, radio = facts.pop()
        visits = [row for _, rows in pieces for row in rows]
        lanes[segment % 2].extend(visits)
        lanes[segment % 2].append(
            dict(
                kind="segment",
                segment=segment,
                count=len(visits),
                path=path,
                manifest_digest=digest,
                radio_id=radio,
                library_sha256=binary_sha,
                detector_cpu_s=sum(r["detector_cpu_s"] for r in visits),
            )
        )
    for i, lane in enumerate(lanes):
        lane.append(dict(kind="worker", worker=i))
    document, counts = trial.recording.native_document(case, lanes, lock["capture"])
    document["provenance"]["scope"] = (
        "fresh original capture detector with the qualified combined FFT and refinement kernels"
    )
    return document, counts


def parity(current, original):
    for field in ("schema_version", "clock_anchor", "delivery_clocks", "last_sample_counter"):
        if current[field] != original[field]:
            raise ValueError(f"recorded physical clock or native layout changed: {field}")
    if {
        k: v
        for k, v in current["source"].items()
        if k not in ("probes", "analysis_manifest_sha256")
    } != {
        k: v
        for k, v in original["source"].items()
        if k not in ("probes", "analysis_manifest_sha256")
    }:
        raise ValueError("complete input authority or physical recording changed")
    for field in (
        "window_count",
        "processed_windows",
        "invalid_capture",
        "excluded_windows",
        "skipped_fast_score",
        "rf_mapping_authorities",
    ):
        if current["provenance"][field] != original["provenance"][field]:
            raise ValueError(f"recorded validity or physical exclusions changed: {field}")
    a, b = (doc["source"]["probes"] for doc in (current, original))
    result = compare_rows(a, b)
    if list(keyed_rows(a)) != list(keyed_rows(b)):
        raise ValueError("physical probes changed order")
    changed, differences, gates = [], Counter(), Counter()
    for p, q in zip(a, b, strict=True):
        first, second = p["candidates"], q["candidates"]
        x, y = (
            tuple(c["passed_fractional_margin_gate"] for c in group) for group in (first, second)
        )
        gates.update(
            dict(
                current=sum(x),
                archived=sum(y),
                current_probes=bool(any(x)),
                archived_probes=bool(any(y)),
                changed_probes=any(x) != any(y),
                changed_sequence=x != y,
            )
        )
        if encoded(p) != encoded(q):
            fields = set().union(
                *(
                    {k for k in f if encoded(f[k]) != encoded(g[k])}
                    for f, g in zip(first, second, strict=False)
                )
            )
            if len(first) != len(second):
                fields.add("candidate_count")
            for f, g in zip(first, second, strict=False):
                for k in fields & f.keys():
                    if type(f[k]) in (int, float):
                        differences[k] = max(differences[k], abs(f[k] - g[k]))
            changed.append(
                dict(
                    visit=p["visit_index"],
                    receiver=p["receiver_id"],
                    fields=sorted(fields),
                    measured_candidates=len(first),
                    archived_candidates=len(second),
                )
            )
    return dict(
        result,
        clocks_and_physical_support_exact=True,
        gate_counts=dict(gates),
        differences=changed,
        max_absolute_field_delta=dict(differences),
    )


def summary_rows(shards):
    return sorted(
        [
            dict(
                visit=r["visit"],
                status=r["status"],
                cpu_ms=1000 * r["detector_cpu_s"],
                wall_ms=1000 * r["detector_wall_s"],
                folded_calls=r["grid_calls"],
            )
            for _, rows in shards.values()
            for r in rows
        ],
        key=lambda row: row["visit"],
    )


def raw_evidence(work):
    lock, _ = trial.configure(work)
    case, _ = whole_iq.binding(trial.IDENT)
    shards, workers, wall = collect(work, lock)
    samples = summary_rows(shards)
    archive = whole_iq.read(
        whole_iq.checked(
            BULK / lock["original"]["native"]["path"], lock["original"]["native"]["sha256"]
        )
    )
    audit = dict(
        scheduled=case["recording"]["window_count"],
        completed=len(samples),
        valid=sum(r["status"] == "processed" for r in samples),
        invalid=sum(r["status"] == "invalid_capture" for r in samples),
        workers=workers,
        wall_s=wall,
        compressed_bytes=sum(r[0]["compressed_bytes"] for r in shards.values()),
        planned_chunks=sum(len(r[2]) for r in lock["workers"]),
        completed_chunks=len(shards),
        measured_folded_calls=sum(r["folded_calls"] for r in samples),
    )
    terminals = [row["terminal"] for row in workers.values() if row["terminal"]]
    audit["completed_worker_cpu_s"] = (
        sum(r["end"]["cpu.stat.usage_usec"] - r["start"]["cpu.stat.usage_usec"] for r in terminals)
        * 1e-6
    )
    audit["total_measured_detector_cpu_s"] = sum(r["cpu_ms"] for r in samples) * 1e-3
    audit["largest_worker_peak_bytes"] = max(
        (r["end"]["memory.peak"] for r in terminals), default=None
    )
    audit["largest_worker_process_rss_kib"] = max(
        (r["end"]["rss_peak_kib"] for r in terminals), default=None
    )
    if audit["completed"] == audit["scheduled"] and all(
        r["exit_code"] == 0 for r in workers.values()
    ):
        fused, counts = assemble(case, lock, shards)
        audit["parity"] = parity(fused, archive)
        audit["counts"] = counts
        dest = work / "measured.json"
        data = encoded(fused) + b"\n"
        if dest.exists() and dest.read_bytes() != data:
            raise ValueError("assembled actual position input changed between authority checks")
        if not dest.exists():
            write(dest, data)
        audit["measured_native_sha256"] = _sha(dest)
    valid = [r for r in samples if r["status"] == "processed"]
    audit["valid_detector"] = {
        key: dict(distribution([r[key] for r in valid]), within_20=sum(r[key] <= 20 for r in valid))
        for key in ("cpu_ms", "wall_ms")
    }
    return lock, case, audit, samples


def terminal_position(work, label, source, directory, cpu, lock, case, original):
    directory.mkdir(exist_ok=False)
    recording = directory / "recording"
    recording.mkdir()
    binding = trial.recording.bind_request(case, source, recording / "request.json")
    request = whole_iq.read(recording / "request.json")
    whole_iq.verify_request(
        request, original, native_path=str(source), native_sha256=binding["native_sha256"]
    )
    save_json(
        directory / "raw.json",
        dict(
            native_sha256=binding["native_sha256"], request_sha256=_sha(recording / "request.json")
        ),
    )
    save_json(
        directory / "plan.json",
        dict(
            receiver=lock["receiver"],
            cpu=cpu,
            label=label,
            case=trial.IDENT,
            source_lock_sha256=_sha(work / "source-lock.json"),
        ),
    )
    if whole_iq.receiver_identity(Path(lock["receiver"])) != lock["receiver_files"]:
        raise ValueError("installed compact position source changed")
    command = trial.service(
        f"leo-capture-position-{label}-{uuid4().hex[:8]}",
        lock["position_limit_s"],
        [
            "taskset",
            "-c",
            str(cpu),
            "env",
            f"TMPDIR={directory}",
            *(f"{k}={v}" for k, v in trial.recording.SINGLE_THREAD.items()),
            sys.executable,
            "-B",
            "-m",
            whole_iq.MODULE,
            "position",
            str(directory),
        ],
    )
    before = perf_counter()
    with (directory / "service.log").open("xb") as log:
        try:
            process = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=lock["position_limit_s"] + 25,
                check=False,
            )
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
    elapsed = perf_counter() - before
    save_json(
        directory / "terminal.json",
        dict(
            command=command,
            wall_s=elapsed,
            exit_code=exit_code,
            log_sha256=_sha(directory / "service.log"),
        ),
    )


def position(work):
    lock, case, result, _ = raw_evidence(work)
    if "measured_native_sha256" not in result:
        print(
            "Retaining incomplete authentic raw coverage. No compact receiver starts.", flush=True
        )
        return
    _, original = whole_iq.binding(trial.IDENT)
    archive = whole_iq.checked(
        BULK / lock["original"]["native"]["path"], lock["original"]["native"]["sha256"]
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [
            pool.submit(
                terminal_position,
                work,
                label,
                source,
                work / label,
                worker[0],
                lock,
                case,
                original,
            )
            for worker, (label, source) in zip(
                lock["workers"][:2],
                (("actual", work / "measured.json"), ("archive", archive)),
                strict=True,
            )
        ]
        for task in tasks:
            task.result()


def compact_rows(work, lock, audit):
    rows, clocks = [], {}
    common = dict(
        id=trial.IDENT,
        mode="matched-tile",
        cohort="complete original detector replay",
        paired_capture_sha256=lock["original"]["native"]["sha256"],
        original_request_sha256=lock["original"]["request"]["sha256"],
        catalog_sha256=lock["original"]["catalog"]["sha256"],
        tile=lock["original"]["tile"],
    )
    for label, method, digest in (
        ("actual", trial.METHOD, audit.get("measured_native_sha256")),
        ("archive", ARCHIVED, common["paired_capture_sha256"]),
    ):
        directory = work / label
        if not directory.is_dir():
            if "measured_native_sha256" in audit:
                raise ValueError("complete raw replay needs both compact terminal receipts")
            if label == "archive":
                continue
            state, reason = (
                "timed_out",
                "Independent detector shards did not finish within the bounded replay",
            )
        else:
            terminal = whole_iq.read(directory / "terminal.json")
            whole_iq.checked(directory / "service.log", terminal["log_sha256"])
            plan = whole_iq.read(directory / "plan.json")
            raw = whole_iq.read(directory / "raw.json")
            whole_iq.checked(directory / "recording/request.json", raw["request_sha256"])
            if (
                plan["source_lock_sha256"] != _sha(work / "source-lock.json")
                or raw["native_sha256"] != "sha256:" + digest
            ):
                raise ValueError("compact terminal does not bind its claimed native factors")
            clocks[label] = terminal
            logs = (directory / "service.log").read_text()
            state, reason = (
                (
                    "timed_out"
                    if terminal["exit_code"] == 124 or "timed out" in logs.lower()
                    else "failed"
                ),
                "Compact position service returned a nonzero exit",
            )
            if terminal["exit_code"] == 0:
                end = whole_iq.read(directory / "end.json")
                if (
                    end["memory.max"] != whole_iq.MEMORY
                    or end["memory.swap.max"]
                    or end["memory.swap.current"]
                    or end["memory.events.oom_kill"]
                ):
                    raise ValueError("compact receiver exceeded its independently capped service")
                clocks[label]["end"] = end
                outcome = whole_iq.read(directory / "position.json")
                validate_result(outcome)
                rows.append(dict(common, method=method, result=outcome, native_sha256=digest))
                continue
        rows.append(
            dict(
                common,
                method=method,
                native_sha256=digest,
                result=dict(
                    status=state,
                    reason=reason,
                    boundary="Complete recorded IQ through original detector and compact position",
                    metrics={},
                    arms={name: {"latlon": None} for name in ARMS},
                ),
            )
        )
    prior_folder = REPORT.parents[1] / "latency-and-support/complete-roster"
    receipt = sealed(prior_folder, "all-figure-lock.json")
    path = whole_iq.checked(
        prior_folder / "all-positions.jsonl.gz", receipt["files"]["all-positions.jsonl.gz"]
    )
    historic = [
        dict(row, cohort=common["cohort"])
        for row in rows_from(path)
        if row["id"] == trial.IDENT and row["method"] in (FOUR, FIVE)
    ]
    if {row["method"] for row in historic} != {FOUR, FIVE} or any(
        row[k] != common[k] for row in historic for k in MINIMAL
    ):
        raise ValueError("wide control positions differ in recording, causal request or tile")
    return (
        rows + historic,
        clocks,
        dict(
            path=str(path),
            sha256=_sha(path),
            receipt_sha256=_sha(prior_folder / "all-figure-lock.json"),
        ),
    )


def timing_figure(out, audit):
    if audit["valid"] == 0:
        return
    fig, axes = plot.canvas(
        "Complete capture-era FFT replay on a recorded waveform",
        "DS29-0082 · CPU and wall per valid archived visit",
        "Recorded windows ran on independent capped host processes. "
        "Position and IQ decode sit outside the detector clock.",
    )
    for ax, key, label in zip(axes, ("cpu_ms", "wall_ms"), ("CPU", "Wall"), strict=True):
        values = audit["valid_detector"][key]
        plot.paired(
            ax,
            [f"{audit['valid']:,} valid visits"],
            [(values["p50"], values["p95"])],
            title=f"Dual receiver detector {label}",
            xlabel="Host milliseconds",
            fmt=".1f",
        )
    plot.key(fig, "Median", "95th percentile")
    fig.savefig(out / "timing.png", dpi=165, facecolor="white")
    fig.savefig(out / "timing.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)
    inputs = ("timing.png", "timing.pdf", "timing.csv", "prediction-lock.json")
    save_json(out / "timing-lock.json", {"files": {p: _sha(out / p) for p in inputs}})
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="capture-whole-detector-time",
            title="Complete original capture replay detector timings",
            sample=f"{audit['valid']:,} valid visits of {audit['scheduled']:,} scheduled visits",
            boundary="Resident CI16 through both receivers' original detector and projection",
            note="Independent capped host workers replayed saved data. "
            "The report gives aggregate CPU and parallel throughput separately.",
            seal="timing-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="timing.csv",
        ),
    )


def publish(work, out):
    lock, _, audit, samples = raw_evidence(work)
    positions, clocks, historical = compact_rows(work, lock, audit)
    assets = [REPORT / "source-lock.json", REPORT / "PROTOCOL.md"]
    for path in (
        work / "launch.json",
        work / "raw-exits.json",
        work / "smoke.json",
        *sorted(work.glob("cpu-*.log")),
    ):
        dest = out / "receipts" / path.name
        write(dest, path.read_bytes())
        assets.append(dest)
    for label in clocks:
        for path in sorted((work / label).rglob("*")):
            if path.is_file():
                dest = out / "receipts" / path.relative_to(work)
                write(dest, path.read_bytes())
                assets.append(dest)
    if "measured_native_sha256" in audit:
        dest = out / "native.json.gz"
        write(dest, gzip.compress((work / "measured.json").read_bytes(), compresslevel=5, mtime=0))
        assets.append(dest)
    save_json(out / "audit.json", dict(raw=audit, position=clocks, historical=historical))
    csv_file(out / "timing.csv", samples)
    pack(out / POS, positions)
    _, refs = held_references(None, [trial.IDENT])
    csv_file(out / "scores.csv", geographic(positions, {r["id"]: r for r in refs}))
    assets.extend(out / name for name in ("audit.json", "timing.csv", POS, "scores.csv"))
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=[trial.IDENT],
            files={str(p.relative_to(out)): _sha(p) for p in assets},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )
    timing_figure(out, audit)
    series = (
        ("stock", FOUR, "Earlier full stock four-region IQ replay"),
        ("one", trial.METHOD, "Fresh complete capture-era replay"),
        ("one_native_factors", ARCHIVED, "Original archived capture factors, fresh compact solver"),
        ("all_visits", FIVE, "Earlier full fifth-region IQ replay"),
    )
    methods = {r["method"] for r in positions}
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="capture-whole-original",
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="prediction-lock.json",
                    title="Original capture detector from a complete recording",
                    caption="DS29-0082 used the original causal catalogue and 25 km offer. "
                    "The parallel host replay used capped workers.",
                    provenance=["source-lock.json", "audit.json", "scores.csv"],
                    series=[
                        dict(
                            key=key,
                            file=POS,
                            value=method,
                            label=label,
                            native_field="paired_capture_sha256",
                            match=MINIMAL,
                        )
                        for key, method, label in series
                        if method in methods
                    ],
                )
            ],
        ),
    )
    generate(out / "charts", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("position", "publish"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    if args.action == "position":
        position(args.work)
    else:
        publish(args.work, REPORT)
