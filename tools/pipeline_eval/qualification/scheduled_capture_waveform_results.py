"""Verify the independently scheduled raw factors and score the complete replay."""

import argparse
import gzip
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distribution, validate_result
from . import capture_whole_results as whole
from . import scheduled_capture_waveform as trial
from .fresh_replay_results import geographic
from .full_held_scores import held_references
from .full_v5_check import BULK, _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .screening_figures import generate

REPORT = trial.REPORT
COMPLETE = "original_capture_all_factors_compact"
POS = "positions.jsonl.gz"


def verified_schedule(schedule):
    """Rebuild the selected set by taking one arithmetic progression on each RF lane."""
    lanes = defaultdict(list)
    for visit, (channel, rf, ordinal, _) in enumerate(schedule):
        lane = lanes[(channel, rf)]
        if ordinal != len(lane):
            raise ValueError("signed RF ordinal is discontinuous")
        lane.append(visit)
    chosen = {
        visit
        for (channel, _), visits in lanes.items()
        for visit in visits[(1 - channel) % trial.PERIOD :: trial.PERIOD]
    }
    if chosen != {visit for visit, row in enumerate(schedule) if row[-1]}:
        raise ValueError("independent per-RF progression differs from frozen policy")
    return chosen


def expected_projection(original, chosen):
    probes = [
        p if p["visit_index"] in chosen else dict(p, candidates=[])
        for p in original["source"]["probes"]
    ]
    return dict(original, source=dict(original["source"], probes=probes))


def review_visits(shards, chosen, excluded):
    result, counts, by_rf = [], Counter(), {}
    for _, (_, rows) in sorted(shards.items()):
        for row in rows:
            v = row["visit"]
            expected = (
                "invalid_capture"
                if v in excluded
                else "processed"
                if v in chosen
                else "skipped_policy"
            )
            if row["status"] != expected or row["selected"] != (v in chosen):
                raise ValueError(
                    "measured dispatch or original hardware validity differs from schedule"
                )
            if (expected == "processed") != bool(row["grid_calls"]):
                raise ValueError("measured original acquisition work differs from policy")
            counts[expected] += 1
            stats = by_rf.setdefault(str(row["rf_center_hz"]), dict(counts=Counter(), acquired=[]))
            stats["counts"][expected] += 1
            stats["counts"]["selected_hardware_invalid"] += v in chosen and v in excluded
            if expected == "processed":
                stats["acquired"].append(row["delivery_clock"]["monotonic_ns"])
            result.append(
                dict(
                    visit=v,
                    rf_center_hz=row["rf_center_hz"],
                    status=expected,
                    cpu_ms=1e3 * row["detector_cpu_s"],
                    wall_ms=1e3 * row["detector_wall_s"],
                    folded_calls=row["grid_calls"],
                    scheduled_selected=row["selected"],
                )
            )
    coverage = {
        rf: dict(
            counts=s["counts"],
            max_gap_s=max((b - a for a, b in pairwise(s["acquired"])), default=0) * 1e-9,
        )
        for rf, s in by_rf.items()
    }
    return result, dict(counts), coverage


def assemble(work):
    with patch.object(trial.prior, "REPORT", REPORT):
        lock, _ = trial.prior.configure(work)
    case, original = whole_iq.binding(trial.IDENT)
    archive = whole_iq.checked(
        BULK / lock["original"]["native"]["path"], lock["original"]["native"]["sha256"]
    )
    doc = whole_iq.read(archive)
    schedule = whole_iq.read(whole_iq.checked(work / "schedule.json", lock["schedule_sha256"]))
    chosen = verified_schedule(schedule)
    excluded = {r["visit"] for r in doc["provenance"]["excluded_windows"]}
    shards, workers, wall = whole.collect(work, lock)
    timings, calls, coverage = review_visits(shards, chosen, excluded)
    selected = [r for r in timings if r["status"] == "processed"]
    done = len(timings) == len(schedule) and all(w["exit_code"] == 0 for w in workers.values())
    terminal = [w["terminal"] for w in workers.values() if w["terminal"]]
    audit = dict(
        complete=done,
        raw_wall_s=wall,
        decoder_scheduled=len(schedule),
        actual_rows=len(timings),
        workers=workers,
        compressed_bytes=sum(r[0]["compressed_bytes"] for r in shards.values()),
        largest_worker_peak_bytes=max((w["end"]["memory.peak"] for w in terminal), default=None),
        largest_worker_rss_kib=max((w["end"]["rss_peak_kib"] for w in terminal), default=None),
        calls=calls,
        folded_calls=sum(r["folded_calls"] for r in timings),
        coverage_by_rf=coverage,
        nominated=len(chosen),
        scheduled_selected_hardware_invalid=len(chosen & excluded),
        total_detector_cpu_s=sum(r["cpu_ms"] for r in selected) * 1e-3,
        workers_cpu_s=sum(
            w["end"]["cpu.stat.usage_usec"] - w["start"]["cpu.stat.usage_usec"] for w in terminal
        )
        * 1e-6,
        detector={
            key: dict(
                distribution([r[key] for r in selected]),
                within_20=sum(r[key] <= 20 for r in selected),
            )
            for key in ("cpu_ms", "wall_ms")
        },
    )
    if done:
        prepared = {
            key: (
                receipt,
                [
                    dict(row, status="processed") if row["status"] == "skipped_policy" else row
                    for row in rows
                ],
            )
            for key, (receipt, rows) in shards.items()
        }
        actual, count = whole.assemble(case, lock, prepared)
        actual["provenance"]["scope"] = (
            "quarter-scheduled original capture detector and authenticated skipped physical slots"
        )
        comparison = expected_projection(doc, chosen)
        audit["parity"] = whole.parity(actual, comparison)
        probe_counts = [
            sum(
                any(c["passed_fractional_margin_gate"] for c in p["candidates"])
                for p in d["source"]["probes"]
            )
            for d in (actual, comparison, doc)
        ]
        audit.update(
            native_counts=count,
            positive_probes=dict(
                zip(
                    ("actual", "archived_scheduled", "archived_complete"), probe_counts, strict=True
                )
            ),
            reference_selected_probe_rows=2 * len(chosen - excluded),
            projected_probe_sha256=trial.prior.recording.digest(comparison["source"]["probes"]),
        )
        data = encoded(actual) + b"\n"
        path = work / "measured.json"
        if path.exists() and path.read_bytes() != data:
            raise ValueError("scheduled native output changed across seals")
        if not path.exists():
            write(path, data)
        audit["native_sha256"] = _sha(path)
    return lock, case, original, archive, audit, timings


def position(work):
    lock, case, original, archive, audit, _ = assemble(work)
    jobs = [("full", archive)]
    if audit["complete"]:
        jobs.insert(0, ("scheduled", work / "measured.json"))
    with ThreadPoolExecutor(max_workers=len(jobs)) as runner:
        tasks = [
            runner.submit(
                whole.terminal_position,
                work,
                label,
                source,
                work / label,
                cpu,
                lock,
                case,
                original,
            )
            for (label, source), cpu in zip(jobs, trial.CPUS, strict=False)
        ]
        for task in tasks:
            task.result()


def compact_results(work, lock, audit):
    rows, evidence = [], {}
    source = lock["original"]
    common = dict(
        id=trial.IDENT,
        mode="matched-tile",
        cohort="independent full saved waveform",
        paired_capture_sha256=source["native"]["sha256"],
        original_request_sha256=source["request"]["sha256"],
        catalog_sha256=source["catalog"]["sha256"],
        tile=source["tile"],
    )
    for label, method, digest in (
        ("scheduled", trial.METHOD, audit.get("native_sha256")),
        ("full", COMPLETE, source["native"]["sha256"]),
    ):
        base = work / label
        outcome = dict(
            status="timed_out",
            reason="Scheduled full waveform did not complete",
            metrics={},
            arms={arm: {"latlon": None} for arm in ARMS},
            boundary="Scheduled original detector and compact position",
        )
        if base.is_dir():
            terminal = whole_iq.read(base / "terminal.json")
            raw = whole_iq.read(base / "raw.json")
            whole_iq.checked(base / "recording/request.json", raw["request_sha256"])
            whole_iq.checked(base / "service.log", terminal["log_sha256"])
            if raw["native_sha256"] != "sha256:" + digest:
                raise ValueError("compact service measured a different prepared input")
            evidence[label] = terminal
            if terminal["exit_code"] == 0:
                end = whole_iq.read(base / "end.json")
                if (
                    end["memory.max"] != whole_iq.MEMORY
                    or end["memory.swap.max"]
                    or end["memory.swap.current"]
                    or end["memory.events.oom_kill"]
                ):
                    raise ValueError("compact service lost its independent resource bound")
                evidence[label]["end"] = end
                outcome = whole_iq.read(base / "position.json")
                validate_result(outcome)
            else:
                outcome.update(
                    status="timed_out" if terminal["exit_code"] == 124 else "failed",
                    reason="Compact service did not return a result",
                )
        elif digest is not None:
            raise ValueError("complete waveform requires the compact terminal receipt")
        rows.append(dict(common, method=method, native_sha256=digest, result=outcome))
    return rows, evidence


def stage(out, audit):
    if not audit["calls"].get("processed"):
        return
    figure, axes = whole.plot.canvas(
        "Complete original acquisition on a quarter schedule",
        "DS26-0162 · detector work on selected valid raw visits",
        "Selected visits include both physical receivers and the complete configured search. "
        "Raw readers still authenticate skipped visits.",
    )
    for ax, key in zip(axes, ("cpu_ms", "wall_ms"), strict=True):
        d = audit["detector"][key]
        whole.plot.paired(
            ax,
            [f"{d['n']:,} measured visits"],
            [(d["p50"], d["p95"])],
            title=key.split("_")[0].upper(),
            xlabel="Host milliseconds",
            fmt=".1f",
        )
    whole.plot.key(figure, "Median", "95th percentile")
    figure.savefig(out / "timing.png", dpi=165, facecolor="white")
    figure.savefig(out / "timing.pdf", facecolor="white", metadata={"CreationDate": None})
    whole.plot.plt.close(figure)
    files = ("prediction-lock.json", "timing.csv", "timing.png", "timing.pdf")
    save_json(out / "timing-lock.json", dict(files={f: _sha(out / f) for f in files}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="scheduled-original-waveform-timing",
            title="Original acquisition timing on the staggered quarter schedule",
            sample=f"{audit['calls']['processed']:,} measured selected dual-antenna visits",
            boundary="Resident CI16 through dual-receiver original detector and factor projection",
            note="Skipped visits retain signed clocks and authentication during saved-IQ replay.",
            seal="timing-lock.json",
            image="timing.png",
            csv="timing.csv",
            pdf="timing.pdf",
        ),
    )


def publish(work, out):
    lock, _, _, _, audit, timings = assemble(work)
    records, positions = compact_results(work, lock, audit)
    assets = [out / "source-lock.json", out / "PROTOCOL.md"]
    receipts = [work / f for f in ("launch.json", "smoke.json", "raw-exits.json")]
    receipts.extend(work.glob("cpu-*.log"))
    for label in positions:
        receipts.extend(p for p in (work / label).rglob("*") if p.is_file())
    for path in receipts:
        dst = out / "receipts" / path.relative_to(work)
        write(dst, path.read_bytes())
        assets.append(dst)
    if audit["complete"]:
        dst = out / "native.json.gz"
        write(dst, gzip.compress((work / "measured.json").read_bytes(), compresslevel=5, mtime=0))
        assets.append(dst)
    write(out / "schedule.json", (work / "schedule.json").read_bytes())
    save_json(out / "audit.json", dict(raw=audit, position=positions))
    csv_file(out / "timing.csv", timings)
    pack(out / POS, records)
    _, refs = held_references(None, [trial.IDENT])
    csv_file(out / "scores.csv", geographic(records, {r["id"]: r for r in refs}))
    assets.extend(out / n for n in ("audit.json", "timing.csv", POS, "schedule.json", "scores.csv"))
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=[trial.IDENT],
            files={str(p.relative_to(out)): _sha(p) for p in assets},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )
    stage(out, audit)
    series = (
        ("one", trial.METHOD, "Actual quarter-scheduled original capture IQ"),
        ("stock", COMPLETE, "All original archived factors with fresh compact solve"),
    )
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="scheduled-original-waveform",
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="prediction-lock.json",
                    title="Original acquisition on a fixed quarter waveform schedule",
                    caption="DS26-0162 with the original tile and causal catalogue. "
                    "The fixed cadence retains complete visits on each RF lane.",
                    provenance=["source-lock.json", "audit.json", "scores.csv"],
                    series=[
                        dict(
                            key=k,
                            file=POS,
                            value=method,
                            label=label,
                            native_field="paired_capture_sha256",
                            match=whole.MINIMAL,
                        )
                        for k, method, label in series
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
