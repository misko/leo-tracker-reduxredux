"""Audit and score the full saved-IQ path with pruned fine CFO search."""

import argparse
import csv
import gzip
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution
from . import capture_whole_results as whole
from . import field_exact_waveform as trial
from . import prepared_capture_waveform_results as prepared
from .capture_detector_lineage import keyed_rows
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import MARGIN_GATE, _sha
from .prefix_figures import csv_file
from .selector_waveform_results import endpoint

CHART = "field-exact-waveform"
HISTORIC = "capture_combined_complete_iq"
ASSEMBLE = whole.assemble
NUMERIC = (
    "integer_epoch_sample",
    "fractional_epoch_offset_samples",
    "fractional_tracking_cfo_hz",
    "fractional_exact_score",
    "fractional_control_score",
    "fractional_margin",
)
GATE = "passed_fractional_margin_gate"
CANDIDATE_FIELDS = ("candidate_rank", *NUMERIC, GATE)
PROVENANCE_FIELDS = (
    "window_count",
    "processed_windows",
    "invalid_capture",
    "excluded_windows",
    "skipped_fast_score",
    "rf_mapping_authorities",
)


def changes(a, b):
    return sorted(
        key
        for key in a.keys() | b.keys()
        if key not in a or key not in b or encoded(a[key]) != encoded(b[key])
    )


def without(d, *keys):
    return {key: value for key, value in d.items() if key not in keys}


def ordered_differences(a, b):
    return abs(len(a) - len(b)) + sum(encoded(x) != encoded(y) for x, y in zip(a, b, strict=False))


def parity(current, archived):
    documents = (current, archived)
    probes = [d["source"]["probes"] for d in documents]
    clocks = {
        name: encoded(current[name]) == encoded(archived[name])
        for name in ("schema_version", "clock_anchor", "delivery_clocks", "last_sample_counter")
    }
    validity = {
        name: encoded(current["provenance"][name]) == encoded(archived["provenance"][name])
        for name in PROVENANCE_FIELDS
    }
    source = changes(
        *(without(d["source"], "probes", "analysis_manifest_sha256") for d in documents)
    )
    indexed = [keyed_rows(p) for p in probes]
    samples = [
        p
        for difference in (
            indexed[0].keys() - indexed[1].keys(),
            indexed[1].keys() - indexed[0].keys(),
        )
        for p in difference
    ]
    rank_masks = Counter()
    differing = Counter({k: 0 for k in CANDIDATE_FIELDS})
    maximum = Counter({k: 0.0 for k in NUMERIC})
    exact = Counter()
    coverage = Counter()
    gates = Counter()
    mismatch = []
    for key in sorted(indexed[0].keys() & indexed[1].keys()):
        p, q = (d[key] for d in indexed)
        a, b = (r["candidates"] for r in (p, q))
        coverage.update(compared_probes=1, compared_candidates=min(len(a), len(b)))
        physical = changes(without(p, "candidates"), without(q, "candidates"))
        masks = ([r.get("candidate_rank") for r in rows] for rows in (a, b))
        rank_a, rank_b = masks
        margin_a, margin_b = ([r.get(GATE) for r in rows] for rows in (a, b))
        gate_a, gate_b = (
            [r for r, passed in zip(ranks, passed, strict=True) if passed]
            for ranks, passed in ((rank_a, margin_a), (rank_b, margin_b))
        )
        rank_masks.update(
            differing_masks=rank_a != rank_b,
            differing_empty_probes=bool(a) != bool(b),
            differing_candidate_counts=len(a) != len(b),
        )
        gates.update(
            differing_gate_masks=gate_a != gate_b,
            differing_gate_sequence=margin_a != margin_b,
            differing_positive_probes=bool(gate_a) != bool(gate_b),
        )
        fields = set()
        for x, y in zip(a, b, strict=False):
            changed = changes(x, y)
            fields.update(changed)
            differing.update(changed)
            exact["candidates"] += not changed
            for name in set(NUMERIC) & set(changed):
                if type(x.get(name)) in (float, int) and type(y.get(name)) in (float, int):
                    maximum[name] = max(maximum[name], abs(x[name] - y[name]))
        exact["probes"] += encoded(p) == encoded(q)
        if fields or physical or rank_a != rank_b:
            mismatch.append(
                dict(
                    visit=key[0],
                    receiver=key[1],
                    fields=sorted(fields),
                    physical_fields=physical,
                    current_rank_mask=rank_a,
                    archive_rank_mask=rank_b,
                    current_gate_mask=gate_a,
                    archive_gate_mask=gate_b,
                )
            )
    totals = {}
    for name, rows in zip(("fresh", "reference"), probes, strict=True):
        candidates = [r for p in rows for r in p["candidates"]]
        totals[name] = dict(
            probes=len(rows),
            candidates=len(candidates),
            empty_probes=sum(not p["candidates"] for p in rows),
            gate_passes=sum(r.get(GATE) is True for r in candidates),
            probes_with_gate_pass=sum(
                any(r.get(GATE) is True for r in p["candidates"]) for p in rows
            ),
            gate_formula_errors=sum(
                type(r.get(GATE)) is not bool
                or type(r.get("fractional_margin")) not in (int, float)
                or r[GATE] != (r["fractional_margin"] >= MARGIN_GATE)
                for r in candidates
            ),
            candidate_schema_errors=sum(set(r) != set(CANDIDATE_FIELDS) for r in candidates),
            probes_sha256=trial.base.recording.digest(rows),
        )
    ordered = list(indexed[0]) == list(indexed[1])
    numeric_differences = sum(differing[k] for k in NUMERIC)
    exact_enough = (
        all(clocks.values())
        and all(validity.values())
        and not source
        and ordered
        and not mismatch
        and not samples
        and all(
            not t["gate_formula_errors"] and not t["candidate_schema_errors"]
            for t in totals.values()
        )
    )
    classification = (
        "exact"
        if exact_enough
        else "numeric_difference"
        if numeric_differences
        else "support_or_gate_difference"
    )
    return dict(
        classification=classification,
        comparisons=dict(coverage),
        exact=dict(exact),
        per_candidate_field=dict(differing),
        max_absolute_numeric_delta=dict(maximum),
        rank_masks=dict(rank_masks),
        gate_equivalence=dict(gates),
        counts=totals,
        clock_fields_exact=clocks,
        capture_validity_fields_exact=validity,
        delivery_clock_rows_differ=ordered_differences(
            current["delivery_clocks"], archived["delivery_clocks"]
        ),
        source_fields_differ=source,
        probe_order_exact=ordered,
        unmatched_probes=sorted(samples),
        changed_probes=mismatch,
    )


def assemble(case, lock, shards):
    native, counts = ASSEMBLE(case, lock, shards)
    source, provenance = native["source"], native["provenance"]
    digest = trial.base.recording.digest
    detector = digest(
        [provenance["detector_sha256"], trial.PANEL_SHA, lock["sources"][str(Path(trial.__file__))]]
    )
    analysis = digest([source["analysis_manifest_sha256"], detector])
    provenance.update(
        detector_sha256=detector,
        run_id="replay-" + analysis[7:39],
        scope="fresh original capture detector with prepared grid, row selector and pruned fine",
    )
    source["analysis_manifest_sha256"] = analysis
    return native, counts


def source(lock, name):
    return whole_iq.checked(trial.PREVIOUS / name, lock["comparison"][name])


def historical_position(lock, positions):
    (original,) = [r for r in whole.rows_from(source(lock, whole.POS)) if r["method"] == HISTORIC]
    if original["id"] != trial.IDENT or any(original[k] != positions[0][k] for k in whole.MINIMAL):
        raise ValueError(
            "older original position did not use the matched capture and causal request"
        )
    return original


def historical_wide_resources(lock, positions):
    folder = trial.REPORT.parents[1] / "latency-and-support/complete-timing"
    receipt = whole_iq.read(folder / "prediction-lock.json")
    path = whole_iq.checked(folder / "resources.csv", receipt["files"]["resources.csv"])
    roles = {r["method"]: r for r in positions if r["method"] in (whole.FOUR, whole.FIVE)}
    with path.open(newline="") as stream:
        matching = [
            r for r in csv.DictReader(stream) if r["id"] == trial.IDENT and r["method"] in roles
        ]
    if len(matching) != 2 or {r["method"] for r in matching} != set(roles):
        raise ValueError("matched prior wide resource rows are missing")
    for row in matching:
        pair = roles[row["method"]]
        expected = (
            lock["original"]["native"]["sha256"],
            lock["original"]["request"]["sha256"],
            lock["original"]["catalog"]["sha256"],
            pair["native_sha256"],
        )
        if expected != tuple(
            row[k] for k in ("capture_sha256", "request_sha256", "catalog_sha256", "native_sha256")
        ):
            raise ValueError("prior wide resources do not bind their capture and position inputs")
    return dict(
        files={str(p): _sha(p) for p in (path, folder / "prediction-lock.json")},
        methods={
            r["method"]: {
                key: float(r[key])
                for key in (
                    "raw_s",
                    "position_s",
                    "position_cpu_s",
                    "worker_s",
                    "peak_bytes",
                    "detector_calls",
                    "detector_wall_within_20",
                    "recorded_clock_span_s",
                    *(
                        f"detector_call_{metric}_{p}_ms"
                        for metric in ("wall", "cpu")
                        for p in ("p50", "p95", "p99", "max")
                    ),
                )
            }
            for r in matching
        },
    )


def fine_telemetry(work, grid, reused_capture):
    by_worker = {cpu: {} for cpu, _, _ in reused_capture["workers"]}
    for cpu in by_worker:
        for line in (work / f"cpu-{cpu}.log").read_text().splitlines():
            if line.startswith(trial.TRACE):
                row = json.loads(line.removeprefix(trial.TRACE))
                if row["ordinal"] in by_worker[cpu]:
                    raise ValueError("duplicate per-visit fine call ledger")
                by_worker[cpu][row["ordinal"]] = row
    result = []
    for row in grid:
        fine = by_worker[row["cpu"]][row["ordinal"]]
        if row["status"] != "processed" and (fine["calls"] or fine["fallbacks"]):
            raise ValueError(f"fine route processed capture exclusion {row['visit']}")
        if (fine["calls"] > 0) != (fine["frames"] > 0 and fine["bins"] > 0):
            raise ValueError(
                f"fine route call ledger has inconsistent work at visit {row['visit']}"
            )
        result.append(dict(visit=row["visit"], status=row["status"], cpu=row["cpu"], **fine))
    return result


def timing_stats(samples):
    valid = [r for r in samples if r["status"] == "processed"]
    result = {}
    for key in ("cpu_ms", "wall_ms"):
        values = [float(r[key]) for r in valid]
        worst = sorted(valid, key=lambda r: -float(r[key]))[:10]
        result[key] = dict(
            distribution(values),
            within_20=sum(value <= 20 for value in values),
            total_cpu_s=sum(values) * 1e-3 if key == "cpu_ms" else None,
            worst=[dict(visit=int(row["visit"]), ms=float(row[key])) for row in worst],
        )
    return result


def compare(work, lock, raw, samples, positions, terminal):
    launch = whole_iq.read(work / "launch.json")
    previous_lock = whole_iq.read(source(lock, "source-lock.json"))
    previous = whole_iq.read(source(lock, "audit.json"))
    with source(lock, "timing.csv").open(newline="") as stream:
        prior_samples = list(csv.DictReader(stream))
    prior_index = {int(r["visit"]): r["status"] for r in prior_samples}
    if len(prior_index) != len(prior_samples) or any(
        prior_index[r["visit"]] != r["status"] for r in samples
    ):
        raise ValueError("prior complete detector timings disagree on visit/validity support")
    shards, _, _ = whole.collect(work, lock)
    grid = prepared.cache(work)
    fine = fine_telemetry(work, grid, lock)
    pane = whole_iq.read(trial.PANEL / "summary.json")
    endpoints = {r["method"]: endpoint(r["result"]) for r in positions}
    previous_detector = timing_stats(prior_samples)
    current_detector = timing_stats(samples)
    score = dict(
        full_clock_comparison="Different complete implementations, CPU rosters and host times",
        capture_edge=lock["capture"]["edge"],
        authenticated_iq_bytes=sum(r["input_bytes"] for _, rows in shards.values() for r in rows),
        cpu_rosters=dict(
            fresh=[r[0] for r in lock["workers"]],
            previous=[r[0] for r in previous_lock["workers"]],
        ),
        detector_timing=dict(fresh=current_detector, previous_combined=previous_detector),
        raw_wall_s=dict(fresh=raw["wall_s"], previous_combined=previous["raw"]["wall_s"]),
        worker_cpu_s=dict(
            fresh=raw["completed_worker_cpu_s"],
            previous_combined=previous["raw"]["completed_worker_cpu_s"],
        ),
        fresh_position={
            name: dict(
                wall_s=r["wall_s"],
                cgroup_cpu_s=r["end"]["cpu.stat.usage_usec"] * 1e-6,
                memory_peak_bytes=r["end"]["memory.peak"],
                supervisor_rss_peak_kib=r["end"]["rss_peak_kib"],
                swap_bytes=r["end"]["memory.swap.current"],
                replay_launch_to_coordinates_s=r["end"]["monotonic_s"] - launch["start_s"],
                cpus=r["end"]["cpus"],
            )
            for name, r in terminal.items()
            if "end" in r
        },
        position_endpoints=endpoints,
        historical_wide_resources=historical_wide_resources(lock, positions),
        prior_compact_services=previous["position"],
        fresh_equals_archive=(
            endpoints[trial.METHOD] == endpoints[whole.ARCHIVED]
            if endpoints.get(trial.METHOD) and endpoints.get(whole.ARCHIVED)
            else None
        ),
        fresh_equals_previous_combined=(
            endpoints[trial.METHOD] == endpoints[HISTORIC] if endpoints.get(trial.METHOD) else None
        ),
        fine=dict(
            **{key: sum(row[key] for row in fine) for key in trial.FINE_COUNTERS},
            workspace_bytes=max((row["workspace_bytes"] for row in fine), default=0),
            visits_with_fallback=sum(row["fallbacks"] > 0 for row in fine),
            valid_visits_without_fine_search=sum(
                row["status"] == "processed" and not (row["calls"] or row["fallbacks"])
                for row in fine
            ),
        ),
        coarse=dict(
            **{
                key: sum(row[key] for row in grid)
                for key in (
                    "calls",
                    "cache_hits",
                    "cold_builds",
                    "filter_ffts",
                    "input_ffts",
                    "inverse_ffts",
                    "coarse_cpu_ns",
                )
            },
            workspace_bytes=max((row["peak_workspace"] for row in grid), default=0),
        ),
        isolated_row_wise_comparison=dict(
            qualification_sha256=trial.PANEL_SHA,
            all_roots_paired_cpu_ms=pane["paired_cpu_ms"],
            this_recording_held_panel=pane["cases"][trial.IDENT],
        ),
    )
    if "measured_native_sha256" in raw:
        fresh = whole_iq.read(work / "measured.json")
        old = json.loads(gzip.decompress(source(lock, "native.json.gz").read_bytes()))
        score["against_previous_complete"] = parity(fresh, old)
    original = raw.get("parity", {})
    score["qualification"] = dict(
        complete_capture=(raw["completed"], raw["valid"], raw["completed_chunks"])
        == (6772, 4868, 106),
        original_fields=original.get("classification", "incomplete"),
        earlier_complete_fields=score.get("against_previous_complete", {}).get(
            "classification", "incomplete"
        ),
        independent_compact_positions=all(
            endpoints.get(method) for method in (trial.METHOD, whole.ARCHIVED)
        ),
        same_compact_endpoints=score["fresh_equals_archive"],
    )
    return score, grid, fine


def position_figure(out, predictions):
    series = (
        ("one", trial.METHOD, "Fresh pruned fine-CFO replay"),
        (
            "one_native_factors",
            whole.ARCHIVED,
            "Original archived factors, independent compact fit",
        ),
        ("stock", whole.FOUR, "Earlier complete wide four-region replay"),
        ("all_visits", whole.FIVE, "Earlier complete wide five-region replay"),
    )
    methods = {row["method"] for row in predictions}
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id=CHART,
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="prediction-lock.json",
                    title="Position from the pruned fine-CFO waveform replay",
                    caption="DS29-0082 used the original causal catalogue and 25 km offer. "
                    "Both calibration settings shared candidates, priors and search budgets.",
                    provenance=[
                        "source-lock.json",
                        "audit.json",
                        "comparison.json",
                        "positions.jsonl.gz",
                    ],
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
                        if method in methods
                    ],
                )
            ],
        ),
    )
    whole.generate(out / "charts", evidence=out)


def stage_figure(out, summary, raw):
    if not raw["valid"]:
        return
    plot = whole.plot
    title = "Detector latency on the complete upper-edge replay"
    note = (
        "Timings cover resident CI16 through dual-lane detection and projection. "
        "The two full runs used different detector implementations and CPU rosters. "
        "The dashed line marks 20 ms."
    )
    fig, axes = plot.canvas(title, f"DS29-0082 · {raw['valid']:,} valid saved visits", note)
    for ax, key, label in zip(axes, ("cpu_ms", "wall_ms"), ("CPU", "Wall"), strict=True):
        d = summary["detector_timing"]
        plot.paired(
            ax,
            ["Median", "95th percentile", "99th percentile"],
            [
                tuple(d[run][key][p] for run in ("previous_combined", "fresh"))
                for p in ("p50", "p95", "p99")
            ],
            title=f"Dual receiver detector {label}",
            xlabel="Host milliseconds",
            fmt=".1f",
        )
        ax.axvline(20, color=plot.DIAGNOSTIC, linewidth=1.4, linestyle="--")
    plot.key(fig, "Earlier combined detector", "Prepared + row selector + pruned fine")
    fig.savefig(out / "timing.png", dpi=165, facecolor="white")
    fig.savefig(out / "timing.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id=CHART + "-timing",
            title=title,
            sample=f"{raw['valid']:,} valid visits of {raw['scheduled']:,} scheduled visits",
            boundary="Resident CI16 through dual-lane detection and projection",
            note=note,
            seal="timing-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="timing.csv",
        ),
    )
    names = (
        "timing.png",
        "timing.pdf",
        "timing.csv",
        "comparison.json",
        "prediction-lock.json",
        "stage-figure.json",
    )
    save_json(out / "timing-lock.json", dict(files={name: _sha(out / name) for name in names}))


def publish(work, out):
    lock, _, raw, samples = whole.raw_evidence(work)
    positions, terminal, historical = whole.compact_rows(work, lock, raw)
    positions.append(historical_position(lock, positions))
    summary, grid, fine = compare(work, lock, raw, samples, positions, terminal)
    assets = [out / "source-lock.json", out / "PROTOCOL.md"]
    inputs = [work / f for f in ("launch.json", "raw-exits.json", "smoke.json")]
    inputs.extend(sorted(work.glob("cpu-*.log")))
    for name in terminal:
        inputs.extend(p for p in sorted((work / name).rglob("*")) if p.is_file())
    for path in inputs:
        dest = out / "receipts" / path.relative_to(work)
        write(dest, path.read_bytes())
        assets.append(dest)
    if "measured_native_sha256" in raw:
        dest = out / "native.json.gz"
        write(dest, gzip.compress((work / "measured.json").read_bytes(), compresslevel=5, mtime=0))
        assets.append(dest)
    save_json(out / "audit.json", dict(raw=raw, position=terminal, historical=historical))
    save_json(out / "comparison.json", summary)
    for name, rows in (("timing.csv", samples), ("coarse.csv", grid), ("fine.csv", fine)):
        if rows:
            csv_file(out / name, rows)
            assets.append(out / name)
    whole.pack(out / whole.POS, positions)
    assets.extend(out / name for name in ("audit.json", "comparison.json", whole.POS))
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=[trial.IDENT],
            publisher_sha256=_sha(Path(__file__)),
            files={str(p.relative_to(out)): _sha(p) for p in assets},
        ),
    )
    sealed(out, "prediction-lock.json")
    _, (reference,) = held_references(None, [trial.IDENT])
    csv_file(out / "scores.csv", geographic(positions, {trial.IDENT: reference}))
    csv_file(
        out / "v5-roles.csv",
        [
            dict(
                id=trial.IDENT,
                role=role,
                arm=arm,
                error_km=reference["reference"][role][arm]["error_km"],
                rf_rms_hz=reference["reference"][role][arm].get("rf_rms_hz"),
                status=reference["reference"][role][arm]["status"],
                wall_s=reference["reference"][role][arm].get("wall_s"),
            )
            for role in ROLES
            for arm in ARMS
        ],
    )
    save_json(
        out / "score-lock.json",
        dict(
            files={name: _sha(out / name) for name in ("scores.csv", "v5-roles.csv")},
            prediction_lock_sha256=_sha(out / "prediction-lock.json"),
        ),
    )
    stage_figure(out, summary, raw)
    position_figure(out, positions)


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
            parity=parity,
        ),
    ):
        trial.check_evidence(args.work)
        if args.action == "position":
            whole.position(args.work)
        else:
            publish(args.work, trial.REPORT)


if __name__ == "__main__":
    main()
