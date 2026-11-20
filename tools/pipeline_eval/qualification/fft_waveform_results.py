"""Compare frozen 256- and 512-point full measurements before scoring the held roof."""

import argparse
import csv
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import distribution
from . import batched_waveform_results as batches
from . import capture_whole_results as whole
from . import fft_waveform as trial
from . import field_exact_waveform_results as peer
from .coarse_waveform_results import factor_changes
from .full_v5_check import _sha
from .prefix_figures import csv_file

ASSEMBLE = whole.assemble
COMPACT = whole.compact_rows
CHART = "fft256-waveform"


def prior_path(lock, name):
    return whole_iq.checked(trial.PREDECESSOR / name, lock["previous_prediction"][name])


def assemble(case, lock, shards):
    native, counts = ASSEMBLE(case, lock, shards)
    source, provenance = native["source"], native["provenance"]
    digest = trial.base.recording.digest
    detector = digest([provenance["detector_sha256"], trial.LIBRARY_SHA, trial.PANEL_SHA])
    analysis = digest([source["analysis_manifest_sha256"], detector])
    provenance.update(
        scope="screened original capture with the stored 256-point prepared FFT",
        detector_sha256=detector,
        run_id="replay-" + analysis[7:39],
    )
    source["analysis_manifest_sha256"] = analysis
    return native, counts


def compact_rows(work, lock, raw):
    rows, resources, historical = COMPACT(work, lock, raw)
    earlier = prior_path(lock, whole.POS)
    (reference,) = [r for r in whole.rows_from(earlier) if r["method"] == trial.incumbent.METHOD]
    if reference["id"] != trial.IDENT or any(reference[k] != rows[0][k] for k in whole.MINIMAL):
        raise ValueError("the prior complete 512 fit has a different capture or causal request")
    return rows + [reference], resources, historical | {"prior_complete_512_sha256": _sha(earlier)}


def indexed(rows):
    result = {int(row["visit"]): row for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate visit in a same-recording timing ledger")
    return result


def pair_timings(new, old, new_grid, old_grid):
    recent, preceding, current_coarse, prior_coarse = map(indexed, (new, old, new_grid, old_grid))
    if recent.keys() != current_coarse.keys() or preceding.keys() != prior_coarse.keys():
        raise ValueError("detector and coarse timings differ in visit support")
    result = []
    for visit, a in sorted(recent.items()):
        b = preceding[visit]
        g, h = current_coarse[visit], prior_coarse[visit]
        fixed = ("status", "segment", "sequence", "channel", "actual_schedule_rf_hz", "rf_ordinal")
        if (
            any(str(a[k]) != str(b[k]) for k in fixed)
            or a["status"] != g["status"]
            or b["status"] != h["status"]
            or int(g["cpu"]) != int(h["cpu"])
            or int(a["folded_calls"]) != int(g["calls"])
            or int(b["folded_calls"]) != int(h["calls"])
        ):
            raise ValueError(f"512/256 comparison has a changed physical visit or CPU at {visit}")
        result.append(
            dict(
                visit=visit,
                cpu=int(g["cpu"]),
                channel=int(a["channel"]),
                ordinal=int(a["rf_ordinal"]),
                status=a["status"],
                detector_cpu_512_ms=float(b["cpu_ms"]),
                detector_cpu_256_ms=float(a["cpu_ms"]),
                detector_wall_512_ms=float(b["wall_ms"]),
                detector_wall_256_ms=float(a["wall_ms"]),
                coarse_cpu_512_ms=int(h["coarse_cpu_ns"]) / 1e6,
                coarse_cpu_256_ms=int(g["coarse_cpu_ns"]) / 1e6,
                grids_512=int(b["folded_calls"]),
                grids_256=int(a["folded_calls"]),
                workspace_512_bytes=int(h["peak_workspace"]),
                workspace_256_bytes=int(g["peak_workspace"]),
            )
        )
    return result


def pairing_summary(rows):
    valid = [r for r in rows if r["status"] == "processed"]
    result = {}
    for key in ("detector_cpu", "detector_wall", "coarse_cpu"):
        a, b = ([r[f"{key}_{n}_ms"] for r in valid] for n in (512, 256))
        result[key] = dict(
            prepared_512=distribution(a),
            stored_256=distribution(b),
            saved_ms=distribution([x - y for x, y in zip(a, b, strict=True)]),
            total_512_s=sum(a) * 0.001,
            total_256_s=sum(b) * 0.001,
            within_20_512=sum(x <= 20 for x in a),
            within_20_256=sum(x <= 20 for x in b),
        )
    return result


def summarize(work, lock, raw, rows, shards, grid, fine, positions, services):
    def read_csv(name):
        with prior_path(lock, name).open(newline="") as stream:
            return list(csv.DictReader(stream))

    previous = whole_iq.read(prior_path(lock, "audit.json"))
    prior = read_csv("timing.csv")
    paired = pair_timings(rows, prior, grid, read_csv("coarse.csv"))
    paired_path = trial.REPORT / "paired-timing.csv"
    if paired:
        csv_file(paired_path, paired)
    launch = whole_iq.read(work / "launch.json")["start_s"]
    endpoints = {r["method"]: peer.endpoint(r["result"]) for r in positions}
    new, old, archive = (
        endpoints.get(method) for method in (trial.METHOD, trial.incumbent.METHOD, whole.ARCHIVED)
    )
    clocks = {
        name: dict(
            cpus=item["end"]["cpus"],
            wall_s=item["wall_s"],
            cgroup_cpu_s=item["end"]["cpu.stat.usage_usec"] * 1e-6,
            peak_bytes=item["end"]["memory.peak"],
            swap_bytes=item["end"]["memory.swap.current"],
            raw_launch_through_coordinates_s=item["end"]["monotonic_s"] - launch,
        )
        for name, item in services.items()
        if "end" in item
    }
    smoke = whole_iq.read(work / "smoke.json")
    stats = dict(
        comparison_boundary="Same recording, chunks and assigned CPUs in separate full host runs",
        qualification=dict(
            complete_capture="measured_native_sha256" in raw,
            archive_field_class=raw.get("parity", {}).get("classification", "incomplete"),
            both_new_compact_services_returned=bool(new and archive),
            position_equals_512=(new == old if new else None),
            position_equals_archive=(new == archive if new and archive else None),
        ),
        publisher_sha256=_sha(Path(__file__)),
        as_run_source_snapshot_sha256=_sha(trial.REPORT / "source-snapshot.json"),
        launch_witness_count=len(smoke["rows"]),
        public_or_attempt_launch_differences=[
            dict(visit=row["visit"], fields=[k for k, same in row["same"].items() if not same])
            for row in smoke["rows"]
            if not all(row["same"].values())
        ],
        host_worker_wall_s=dict(prepared_512=previous["raw"]["wall_s"], stored_256=raw["wall_s"]),
        host_worker_cpu_s=dict(
            prepared_512=previous["raw"]["completed_worker_cpu_s"],
            stored_256=raw["completed_worker_cpu_s"],
        ),
        paired_visit_count=len(paired),
        changed_grid_count_visits=sum(r["grids_512"] != r["grids_256"] for r in paired),
        paired_timing_sha256=_sha(paired_path) if paired else None,
        paired_timing=pairing_summary(paired),
        detector_timing=dict(
            prepared_512=peer.timing_stats(prior), stored_256=peer.timing_stats(rows)
        ),
        stored_256_ordinal_tails=batches.ordinal_tails(rows),
        partial_or_complete_prefix=batches.prefix_audit(lock, rows, shards, raw["scheduled"]),
        new_position_services=clocks,
        previous_position_services=previous["position"],
        position_endpoints=endpoints,
        historical_fast_resources=peer.historical_wide_resources(lock, positions),
        coarse=dict(
            workspace_256_bytes=max((r["peak_workspace"] for r in grid), default=0),
            workspace_512_bytes=max((r["workspace_512_bytes"] for r in paired), default=0),
        ),
        fine={key: sum(r[key] for r in fine) for key in trial.FINE_COUNTERS},
    )
    if "measured_native_sha256" in raw:
        candidate = whole_iq.read(work / "measured.json")
        baseline = trial.payload(prior_path(lock, "native.json.gz"))
        comparison = peer.parity(candidate, baseline)
        stats["fully_measured_field_comparison_256_vs_512"] = comparison
        stats["positive_measurement_matches_256_vs_512"] = factor_changes(candidate, baseline)
    return stats


def descriptors(report, raw, summary):
    series = (
        ("one", trial.METHOD, "Fresh complete stored 256 FFT"),
        ("one_native_factors", trial.incumbent.METHOD, "Earlier complete prepared 512 FFT"),
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
                    title="DS29-0519 position from matched complete FFT lengths",
                    caption="Both full FFT lengths and fast controls share the signed recording, "
                    "the original 25 km offer and the causal TLE request.",
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
    title = "Complete 256- and 512-point detector replay clocks"
    note = (
        "Same authenticated IQ, chunk partition, CPU roster and detector support. "
        "The host runs were sequential. The dashed line marks 20 ms."
    )
    fig, axes = plot.canvas(title, f"DS29-0519 · {raw['valid']:,} matched valid visits", note)
    for ax, key, label in zip(
        axes, ("detector_cpu", "detector_wall"), ("CPU", "Wall"), strict=True
    ):
        d = summary["paired_timing"][key]
        plot.paired(
            ax,
            ["Median", "95th percentile", "99th percentile"],
            [(d["prepared_512"][p], d["stored_256"][p]) for p in ("p50", "p95", "p99")],
            title=f"Complete detector {label}",
            xlabel="Host milliseconds",
            fmt=".1f",
        )
        ax.axvline(20, color=plot.DIAGNOSTIC, linestyle="--", linewidth=1.4)
    plot.key(fig, "Earlier prepared 512-point", "Frozen stored 256-point")
    fig.savefig(report / "timing.png", dpi=165, facecolor="white")
    fig.savefig(report / "timing.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id=CHART + "-timing",
            title=title,
            note=note,
            sample=f"{raw['valid']:,} valid visits of {raw['scheduled']:,} scheduled visits",
            boundary="Resident CI16 through both original detector lanes and factor projection",
            seal="timing-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="paired-timing.csv",
        ),
    )
    names = (
        "timing.csv",
        "paired-timing.csv",
        "timing.png",
        "timing.pdf",
        "stage-figure.json",
        "comparison.json",
        "prediction-lock.json",
    )
    save_json(
        report / "timing-lock.json", dict(files={name: _sha(report / name) for name in names})
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("position", "publish"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    with (
        trial.configured(),
        patch.multiple(
            whole,
            REPORT=trial.REPORT,
            assemble=assemble,
            parity=peer.parity,
            compact_rows=compact_rows,
        ),
        patch.multiple(batches, trial=trial, descriptors=descriptors, summarize=summarize),
        patch.object(peer, "trial", trial),
    ):
        trial.incumbent.previous.check_evidence(args.work)
        if args.action == "position":
            whole.position(args.work)
        else:
            batches.publish(args.work, trial.REPORT)


if __name__ == "__main__":
    main()
