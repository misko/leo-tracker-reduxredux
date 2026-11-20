"""Authenticate and score the complete screened DS29-0519 batched waveform."""

import argparse
import gzip
import json
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES
from . import batched_waveform as trial
from . import capture_whole_results as whole
from . import field_exact_waveform_results as peer
from . import prepared_capture_waveform as prepared_trial
from . import prepared_capture_waveform_results as prepared
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .scheduled_capture_waveform import metadata

ASSEMBLE = whole.assemble
CHART = "batched-waveform"


def assemble(case, lock, shards):
    document, counts = ASSEMBLE(case, lock, shards)
    provenance, source = document["provenance"], document["source"]
    digest = trial.base.recording.digest
    detector = digest(
        [provenance["detector_sha256"], trial.PANEL_SHA, lock["sources"][str(Path(trial.__file__))]]
    )
    analysis = digest([source["analysis_manifest_sha256"], detector])
    provenance.update(
        scope="fresh screened original capture with prepared grid, row selector and batched fine",
        detector_sha256=detector,
        run_id="replay-" + analysis[7:39],
    )
    source["analysis_manifest_sha256"] = analysis
    return document, counts


def prefix_count(visits, scheduled):
    return next((i for i in range(scheduled) if i not in visits), scheduled)


def trace_rows(path, marker):
    for line in path.read_text().splitlines(keepends=True):
        if line.startswith(marker) and line.endswith("\n"):
            yield json.loads(line.removeprefix(marker))


def trace(work, lock, shards, workers):
    """Accept timing only for visits from chunks with an authenticated close."""
    owner = {r["visit"] for _, rows in shards.values() for r in rows}
    spans, fine = [], []
    for cpu, _, _ in lock["workers"]:
        log = work / f"cpu-{cpu}.log"
        with (work / f"cpu-{cpu}.jsonl").open("rb") as stream:
            records = [json.loads(line) for line in stream if line.endswith(b"\n")]
        visits = [r for r in records if r["kind"] == "visit"]
        complete = workers[str(cpu)]["terminal"] is not None
        trace_count = len(visits)
        grid = list(trace_rows(log, prepared_trial.TRACE))
        native = list(trace_rows(log, trial.TRACE))
        if complete and (len(native) != trace_count or len(grid) != trace_count):
            raise ValueError("completed worker lost paired coarse and batched telemetry")
        selected = prepared.joined_cache(visits, grid[:trace_count], owner, complete=complete)
        spans.extend(dict(cpu=cpu, **row) for row in selected)
        for item in selected:
            row = native[item["ordinal"]]
            any_call = row["calls"] + row["fallbacks"] > 0
            if row["ordinal"] != item["ordinal"] or (any_call and item["status"] != "processed"):
                raise ValueError("batched telemetry does not bind the actual replay window")
            fine.append(dict(visit=item["visit"], status=item["status"], cpu=cpu, **row))
    if {r["visit"] for r in spans} != owner or {r["visit"] for r in fine} != owner:
        raise ValueError("an authenticated chunk lacks its batched fine receipt")
    return (sorted(output, key=lambda r: r["visit"]) for output in (spans, fine))


def timing_rows(samples, case, shards):
    recorded, _ = metadata(case)
    shard_index = {r["visit"]: r for _, rows in shards.values() for r in rows}
    result = []
    for row in samples:
        source = shard_index[row["visit"]]
        channel, rf, ordinal, _ = recorded[row["visit"]]
        result.append(
            dict(
                **row,
                segment=source["segment"],
                sequence=source["sequence"],
                channel=channel,
                actual_schedule_rf_hz=rf,
                rf_ordinal=ordinal,
            )
        )
    return result


def ordinal_tails(rows):
    valid = [r for r in rows if r["status"] == "processed"]
    result = {}
    for channel in sorted({r["channel"] for r in valid}):
        rows_at_channel = [r for r in valid if r["channel"] == channel]
        result[channel] = {
            key: [
                {name: r[name] for name in ("visit", "segment", "sequence", "rf_ordinal", key)}
                for r in sorted(rows_at_channel, key=lambda r: -r[key])[:5]
            ]
            for key in ("cpu_ms", "wall_ms")
        }
    return result


def prefix_audit(lock, rows, shards, scheduled):
    frontier = prefix_count({r["visit"] for r in rows}, scheduled)
    index = {r["visit"]: r for _, visits in shards.values() for r in visits}
    native = lock["original"]["native"]
    archive = whole_iq.read(whole_iq.checked(trial.base.BULK / native["path"], native["sha256"]))
    expected = {visit: probes for visit, probes in trial.visit_pairs(archive["source"]["probes"])}
    changes = [
        visit
        for visit in sorted(index)
        if encoded(index[visit]["probes"]) != encoded(expected.get(visit, []))
    ]
    return dict(
        authenticated_visits=len(index),
        contiguous_from_start=frontier,
        prefix_valid=sum(index[v]["status"] == "processed" for v in range(frontier)),
        differing_authenticated_visit_factors=changes,
    )


def summarize(work, lock, raw, rows, shards, grid, fine, positions, services):
    launch = whole_iq.read(work / "launch.json")["start_s"]
    panel = whole_iq.read(trial.PANEL / "summary.json")
    endpoints = {r["method"]: peer.endpoint(r["result"]) for r in positions}
    compact = {
        name: dict(
            cpus=row["end"]["cpus"],
            wall_s=row["wall_s"],
            cgroup_cpu_s=row["end"]["cpu.stat.usage_usec"] * 1e-6,
            peak_bytes=row["end"]["memory.peak"],
            swap_bytes=row["end"]["memory.swap.current"],
            raw_launch_through_coordinates_s=row["end"]["monotonic_s"] - launch,
        )
        for name, row in services.items()
        if "end" in row
    }
    return dict(
        qualification=dict(
            complete_capture="measured_native_sha256" in raw,
            native_fields=raw.get("parity", {}).get("classification", "incomplete"),
            batched_calls_without_fallback=bool(fine) and not any(r["fallbacks"] for r in fine),
            both_compact_services_returned=bool(
                endpoints.get(trial.METHOD) and endpoints.get(whole.ARCHIVED)
            ),
            fresh_equals_archive=(
                endpoints.get(trial.METHOD) == endpoints.get(whole.ARCHIVED)
                if len(compact) == 2
                else None
            ),
        ),
        detector_timing=peer.timing_stats(rows),
        detector_ordinal_tails=ordinal_tails(rows),
        partial_or_complete_prefix=prefix_audit(lock, rows, shards, raw["scheduled"]),
        coarse=dict(
            **{
                key: sum(r[key] for r in grid)
                for key in ("calls", "cold_builds", "cache_hits", "coarse_cpu_ns", "inverse_ffts")
            },
            workspace_bytes=max((r["peak_workspace"] for r in grid), default=0),
        ),
        fine=dict(
            **{key: sum(r[key] for r in fine) for key in trial.FINE_COUNTERS},
            workspace_bytes=max((r["workspace_bytes"] for r in fine), default=0),
            visits_with_fallback=sum(r["fallbacks"] > 0 for r in fine),
        ),
        host_worker_wall_s=raw["wall_s"],
        host_worker_cpu_s=raw["completed_worker_cpu_s"],
        position_endpoints=endpoints,
        position_services=compact,
        historical_fast_resources=peer.historical_wide_resources(lock, positions),
        isolated_same_visit_timings=dict(
            four_case_panel_sha256=trial.PANEL_SHA,
            pooled=panel["pooled"]["detector"],
            case=panel["cases"][trial.IDENT]["detector"],
        ),
    )


def descriptors(report, raw, summary):
    series = (
        ("one", trial.METHOD, "Fresh complete batched fine-CFO replay"),
        ("one_native_factors", whole.ARCHIVED, "Original archive, independent compact fit"),
        ("stock", whole.FOUR, "Earlier complete fast four-region replay"),
        ("all_visits", whole.FIVE, "Earlier complete fast five-region replay"),
    )
    save_json(
        report / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id=CHART,
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="prediction-lock.json",
                    title="Position on the screened lower-edge waveform",
                    caption="DS29-0519 retained its original 25 km offer and causal archive. "
                    "Both compact calibration arms run with matched scientific support.",
                    provenance=["source-lock.json", "audit.json", "comparison.json", whole.POS],
                    series=[
                        dict(
                            key=key,
                            file=whole.POS,
                            value=method,
                            label=label,
                            native_field="paired_capture_sha256",
                            match=whole.MINIMAL,
                        )
                        for key, method, label in series
                        if method in summary["position_endpoints"]
                    ],
                )
            ],
        ),
    )
    whole.generate(report / "charts", evidence=report)
    if not raw["valid"]:
        return
    plot = whole.plot
    title = "Batched fine CFO on the screened lower-edge recording"
    note = (
        "Resident IQ through both original physical detector lanes and factor projection. "
        "The dashed line marks the 20 ms budget."
    )
    fig, axes = plot.canvas(title, f"DS29-0519 · {raw['valid']:,} authenticated valid visits", note)
    for ax, key, name in zip(axes, ("cpu_ms", "wall_ms"), ("CPU", "Wall"), strict=True):
        d = summary["detector_timing"][key]
        plot.paired(
            ax,
            ["Median / P95", "P99 / Maximum"],
            [(d["p50"], d["p95"]), (d["p99"], d["max"])],
            title=f"Complete detector {name}",
            xlabel="Host milliseconds",
            fmt=".1f",
        )
        ax.axvline(20, color=plot.DIAGNOSTIC, linestyle="--", linewidth=1.4)
    plot.key(fig, "Median or P99", "P95 or maximum")
    fig.savefig(report / "timing.png", dpi=165, facecolor="white")
    fig.savefig(report / "timing.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id=CHART + "-timing",
            title=title,
            sample=f"{raw['valid']:,} valid visits of {raw['scheduled']:,} scheduled visits",
            boundary="Resident CI16 through both screened original capture lanes and projection",
            seal="timing-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="timing.csv",
            note=note,
        ),
    )
    files = ("timing.csv", "timing.png", "timing.pdf", "stage-figure.json", "prediction-lock.json")
    save_json(report / "timing-lock.json", dict(files={p: _sha(report / p) for p in files}))


def publish(work, report):
    lock, case, raw, samples = whole.raw_evidence(work)
    shards, workers, _ = whole.collect(work, lock)
    grid, fine = trace(work, lock, shards, workers)
    rows = timing_rows(samples, case, shards)
    positions, services, historical = whole.compact_rows(work, lock, raw)
    summary = summarize(work, lock, raw, rows, shards, grid, fine, positions, services)
    assets = [report / "source-lock.json", report / "PROTOCOL.md"]
    for path in (
        work / "launch.json",
        work / "raw-exits.json",
        work / "smoke.json",
        *sorted(work.glob("cpu-*.log")),
        *(p for fit in services for p in sorted((work / fit).rglob("*")) if p.is_file()),
    ):
        dest = report / "receipts" / path.relative_to(work)
        write(dest, path.read_bytes())
        assets.append(dest)
    if "measured_native_sha256" in raw:
        dest = report / "native.json.gz"
        write(dest, gzip.compress((work / "measured.json").read_bytes(), compresslevel=5, mtime=0))
        assets.append(dest)
    for name, data in (("timing.csv", rows), ("coarse.csv", grid), ("fine.csv", fine)):
        if data:
            csv_file(report / name, data)
            assets.append(report / name)
    save_json(report / "audit.json", dict(raw=raw, position=services, historical=historical))
    save_json(report / "comparison.json", summary)
    whole.pack(report / whole.POS, positions)
    assets.extend(report / name for name in ("audit.json", "comparison.json", whole.POS))
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=[trial.IDENT],
            publisher_sha256=_sha(Path(__file__)),
            files={str(p.relative_to(report)): _sha(p) for p in assets},
        ),
    )
    sealed(report, "prediction-lock.json")
    _, (reference,) = held_references(None, [trial.IDENT])
    csv_file(report / "scores.csv", geographic(positions, {trial.IDENT: reference}))
    roles = reference["reference"]
    csv_file(
        report / "v5-roles.csv",
        [
            dict(
                id=trial.IDENT,
                role=role,
                arm=arm,
                error_km=r["error_km"],
                rf_rms_hz=r.get("rf_rms_hz"),
                status=r["status"],
                wall_s=r.get("wall_s"),
            )
            for role in ROLES
            for arm in ARMS
            for r in (roles[role][arm],)
        ],
    )
    save_json(
        report / "score-lock.json",
        dict(
            files={name: _sha(report / name) for name in ("scores.csv", "v5-roles.csv")},
            prediction_lock_sha256=_sha(report / "prediction-lock.json"),
        ),
    )
    descriptors(report, raw, summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("position", "publish"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    with (
        trial.configured(),
        patch.multiple(whole, REPORT=trial.REPORT, assemble=assemble, parity=peer.parity),
        patch.object(peer, "trial", trial),
    ):
        trial.previous.check_evidence(args.work)
        if args.action == "position":
            whole.position(args.work)
        else:
            publish(args.work, trial.REPORT)


if __name__ == "__main__":
    main()
