"""Publish full upper-edge timing, factor fidelity and matched compact fits."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import batched_waveform_results as batches
from . import capture_whole_results as whole
from . import coarse_waveform as trial
from . import field_exact_waveform_results as peer
from .full_v5_check import _sha, compare_probes

ASSEMBLE = whole.assemble
CHART = "coarse-waveform"


def assemble(case, lock, shards):
    native, counts = ASSEMBLE(case, lock, shards)
    provenance, source = native["provenance"], native["source"]
    digest = trial.base.recording.digest
    detector = digest([provenance["detector_sha256"], lock["selection"], trial.PANEL_SHA])
    analysis = digest([source["analysis_manifest_sha256"], detector])
    provenance.update(
        scope="complete selected upper-edge capture waveform replay",
        detector_sha256=detector,
        run_id="replay-" + analysis[7:39],
    )
    source["analysis_manifest_sha256"] = analysis
    return native, counts


def original_retry_counts(grid):
    """Resolve the intact 512-point schedule from measured inverse work per visit."""
    count, repeats = 0, 0
    for row in grid:
        calls, inverses = row["calls"], row["inverse_ffts"]
        retry, remainder = divmod(inverses - calls * 104286, 191037 - 104286)
        if remainder or retry not in (0, 1, 2) or (calls and calls - retry not in (2, 3, 4)):
            raise ValueError("actual folded work does not identify the original anchor schedule")
        count += retry > 0
        repeats += retry > 1
    return dict(retry_visits=count, visits_with_repeated_retry_grid=repeats)


def nested_retry_counts(work, grid):
    """Count logical retry evaluations separately from physical add-ten grid calls."""
    traces = defaultdict(dict)
    for cpu in {row["cpu"] for row in grid}:
        log = work / f"cpu-{cpu}.log"
        for receipt in batches.trace_rows(log, trial.NESTED_TRACE):
            ordinal = receipt["ordinal"]
            if ordinal in traces[cpu]:
                raise ValueError("duplicate nested visit telemetry")
            traces[cpu][ordinal] = receipt
    result, lanes = Counter(), defaultdict(Counter)
    for row in grid:
        item = traces[row["cpu"]][row["ordinal"]]
        attempts = item["attempts"]
        primary, retry = attempts[:2], attempts[2:]
        valid = row["status"] == "processed"
        expected = (
            [(rx, 22) for rx, _, gated in primary if not gated]
            if sum(gated for _, _, gated in primary) == 1
            else []
        )
        if (
            (valid and [tuple(a[:2]) for a in primary] != [(0, 12), (1, 12)])
            or (not valid and (attempts or item["reuses"]))
            or [tuple(a[:2]) for a in retry] != expected
            or len(retry) > 1
            or bool(item["reuses"]) != bool(retry)
            or not 0 <= item["reuses"] <= 2
        ):
            raise ValueError(f"nested cache or physical trigger changed at visit {row['visit']}")
        result.update(
            retries=len(retry),
            additional_grids=item["reuses"],
            rescues=sum(passed for _, _, passed in retry),
            visits_with_repeated_addition=item["reuses"] > 1,
            merge_cpu_ns=item["merge_cpu_ns"],
        )
        result["max_partial_bytes"] = max(result["max_partial_bytes"], item["partial_bytes"])
        for rx, _, gated in retry:
            lanes[str(rx)].update(retries=1, rescues=gated)
    return dict(result, per_receiver={name: dict(counts) for name, counts in lanes.items()})


def factor_changes(fresh, archived):
    old, new = (doc["source"]["probes"] for doc in (archived, fresh))
    result = Counter()
    lanes = defaultdict(Counter)
    for a, b in zip(old, new, strict=True):
        matching = compare_probes(a, b, 10_000_000)
        before, after = (matching[k] for k in ("production_positive", "native_positive"))
        delta = dict(
            old_candidates=matching["production_complete"],
            new_candidates=matching["native_complete"],
            old_passes=before,
            new_passes=after,
            matched_passes=len(matching["positive_matches"]),
            old_only_passes=matching["production_only"],
            new_only_passes=matching["native_only"],
            lost_positive_probes=bool(before and not after),
            gained_positive_probes=bool(after and not before),
            replaced_winner_probes=bool(before and after and not matching["positive_matches"]),
        )
        result.update(delta)
        lanes[str(a["receiver_id"])].update(delta)
    return dict(result, per_receiver={name: dict(counts) for name, counts in lanes.items()})


def summarize(work, lock, raw, rows, shards, grid, fine, positions, services):
    launch = whole_iq.read(work / "launch.json")["start_s"]
    endpoints = {row["method"]: peer.endpoint(row["result"]) for row in positions}
    selected = lock["selection"]["name"]
    stages = {
        name: dict(
            wall_s=r["wall_s"],
            cgroup_cpu_s=r["end"]["cpu.stat.usage_usec"] * 1e-6,
            peak_bytes=r["end"]["memory.peak"],
            swap_bytes=r["end"]["memory.swap.current"],
            cpus=r["end"]["cpus"],
            raw_launch_through_coordinates_s=r["end"]["monotonic_s"] - launch,
        )
        for name, r in services.items()
        if "end" in r
    }
    retry = original_retry_counts(grid) if selected == "incumbent-batched" else None
    nested = nested_retry_counts(work, grid) if selected == "nested-12-add10" else None
    changes = None
    if "measured_native_sha256" in raw:
        reference = lock["original"]["native"]
        original = whole_iq.read(
            whole_iq.checked(trial.base.BULK / reference["path"], reference["sha256"])
        )
        changes = factor_changes(whole_iq.read(work / "measured.json"), original)
    return dict(
        qualification=dict(
            complete_capture="measured_native_sha256" in raw,
            field_class=raw.get("parity", {}).get("classification", "incomplete"),
            both_compact_services_returned=len(stages) == 2,
            fresh_equals_archive=(
                endpoints[trial.METHOD] == endpoints[whole.ARCHIVED] if len(stages) == 2 else None
            ),
        ),
        source_binding_sha256=_sha(trial.REPORT / "binding-lock.json"),
        scope_publisher_sha256=_sha(Path(__file__)),
        selection=lock["selection"],
        original_retry_opportunities=lock["original_retry_opportunities"],
        measured_original_retry_counts=retry,
        nested_retry_counts=nested,
        original_to_fresh_candidate_changes=changes,
        host_worker_wall_s=raw["wall_s"],
        host_worker_cpu_s=raw["completed_worker_cpu_s"],
        detector_timing=peer.timing_stats(rows),
        detector_ordinal_tails=batches.ordinal_tails(rows),
        partial_or_complete_prefix=batches.prefix_audit(lock, rows, shards, raw["scheduled"]),
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
        compact_services=stages,
        position_endpoints=endpoints,
        historical_fast_resources=peer.historical_wide_resources(lock, positions),
    )


def descriptors(report, raw, summary):
    series = (
        ("one", trial.METHOD, "Fresh complete selected detector"),
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
                    title="Complete upper-edge DS26-0162 waveform and position",
                    caption="Both compact calibration arms share the original 25 km offer "
                    "and causal TLE request with the earlier complete fast controls.",
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
    title = "Detector latency on the upper-edge DS26-0162 replay"
    note = (
        "The measurement begins with resident CI16 and includes both original physical lanes, "
        "the selected retry search and projection. The dashed line marks 20 ms."
    )
    fig, axes = plot.canvas(title, f"{raw['valid']:,} authenticated valid waveform visits", note)
    for ax, key, label in zip(axes, ("cpu_ms", "wall_ms"), ("CPU", "Wall"), strict=True):
        m = summary["detector_timing"][key]
        plot.paired(
            ax,
            ["Median / P95", "P99 / Maximum"],
            [(m["p50"], m["p95"]), (m["p99"], m["max"])],
            title=f"Complete detector {label}",
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
            note=note,
            sample=f"{raw['valid']:,} valid visits of {raw['scheduled']:,} scheduled visits",
            boundary="Resident IQ through both physical lanes and projection",
            seal="timing-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="timing.csv",
        ),
    )
    names = ("timing.csv", "timing.png", "timing.pdf", "stage-figure.json", "prediction-lock.json")
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
        patch.multiple(whole, REPORT=trial.REPORT, assemble=assemble, parity=peer.parity),
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
