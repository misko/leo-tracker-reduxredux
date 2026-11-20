"""Assemble complete primary-only factors, freeze the compact solve, then score."""

import argparse
import csv
import gzip
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution, validate_result
from ..variants.selective_capture import visit_pairs
from . import capture_whole_results as whole
from . import scout_stage_figures as plot
from . import single_pass_position as trial
from .field_exact_waveform_results import parity
from .full_held_scores import held_references
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .selector_waveform_results import endpoint

METHODS = (trial.METHOD, trial.prior.METHOD, whole.FOUR, whole.FIVE)
LABELS = (
    "12 anchors only",
    "Original conditional 12/22",
    "Full wide four-region",
    "Full wide five-region",
)
SERIES = ("one", "one_native_factors", "stock", "all_visits")
WIDE_FOUR = trial.base.BULK / "leo-dev/whole-band-BCw8KqMY/DS26-0237/wide/recording/native.json"
WIDE_FIVE = (
    trial.HISTORICAL.parents[1] / "support-preserving/fifth-crossover/native/DS26-0237.json.gz"
)


def collect(work, lock):
    launch = whole_iq.read(work / "launch.json")
    exits = whole_iq.read(work / "raw-exits.json")
    source = _sha(work / "source-lock.json")
    selected, output, workers, compressed_bytes = set(lock["selected"]), {}, {}, 0
    if launch["source_lock_sha256"] != source or exits["exits"] != {
        str(cpu): 0 for cpu, _, _ in lock["workers"]
    }:
        raise ValueError("selected replay did not complete on every assigned worker")
    for cpu, total, spans in lock["workers"]:
        data = work / f"cpu-{cpu}.jsonl"
        log = work / f"cpu-{cpu}.log"
        records = data.read_text().splitlines()
        terminal = json.loads(records.pop())
        start, end = terminal["start"], terminal["end"]
        if (
            (terminal["kind"], terminal["cpu"], terminal["count"]) != ("worker", cpu, total)
            or terminal["source_lock_sha256"] != source
            or start["pid"] != end["pid"]
            or start["cgroup"] != end["cgroup"]
            or any(
                r["cpus"] != [cpu]
                or r["memory.max"] != whole_iq.MEMORY
                or r["memory.swap.max"]
                or r["memory.swap.current"]
                or r["memory.events.oom_kill"]
                for r in (start, end)
            )
        ):
            raise ValueError("worker resource receipt does not match the frozen service")
        rows = iter(map(json.loads, records))
        for segment, first, stop, offset in spans:
            expected = [v for v in range(offset + first, offset + stop) if v in selected]
            for visit in expected:
                r = next(rows)
                if (r["kind"], r["segment"], r["sequence"], r["visit"]) != (
                    "visit",
                    segment,
                    visit - offset,
                    visit,
                ) or visit in output:
                    raise ValueError("selected replay visit escaped its authenticated shard")
                output[visit] = r
            receipt = next(rows)
            if (
                (receipt["kind"], receipt["segment"], receipt["first"], receipt["stop"])
                != ("chunk", segment, first, stop)
                or receipt["manifest_digest"]
                != "sha256:" + lock["recording"]["segments"][segment]["sha256"]
                or receipt["compressed_bytes"] < 1
            ):
                raise ValueError("capture chunk did not authenticate the selected factors")
            compressed_bytes += receipt["compressed_bytes"]
        if next(rows, None) is not None:
            raise ValueError("worker emitted additional unassigned visits")
        workers[str(cpu)] = dict(
            terminal=terminal, results_sha256=_sha(data), service_log_sha256=_sha(log)
        )
    if set(output) != selected:
        raise ValueError("the raw primary factors are incomplete")
    return output, dict(
        workers=workers,
        wall_s=exits["wall_s"],
        authenticated_compressed_bytes=compressed_bytes,
        authenticated_chunks=sum(len(spans) for _, _, spans in lock["workers"]),
        measured_worker_cpu_s=sum(
            r["terminal"]["end"]["cpu.stat.usage_usec"]
            - r["terminal"]["start"]["cpu.stat.usage_usec"]
            for r in workers.values()
        )
        * 1e-6,
    )


def merge(document, replacements, selected, binding):
    """Retain the full detector's physical and clock authority in original order."""
    source, provenance = document["source"], document["provenance"]
    original = dict(visit_pairs(source["probes"]))
    if replacements.keys() != set(selected) or not replacements.keys() <= original.keys():
        raise ValueError("replacement roster differs from the frozen historical retry visits")
    rows, changes = [], []
    for visit, archived in original.items():
        if visit not in replacements:
            rows.extend(archived)
            continue
        replacement = replacements[visit]
        primary = replacement["probes"]
        old_hit = list(map(trial.assay.positive, archived))
        hit = list(map(trial.assay.positive, primary))
        if (
            len(primary) != 2
            or sum(hit) != 1
            or replacement["attempts"] != [[rx, 12, hit[rx]] for rx in (0, 1)]
            or not old_hit[hit.index(True)]
            or primary[hit.index(True)] != archived[hit.index(True)]
        ):
            raise ValueError("primary result violates the original conditional retry gate")
        for rx, (new, old) in enumerate(zip(primary, archived, strict=True)):
            if {k: v for k, v in new.items() if k != "candidates"} != {
                k: v for k, v in old.items() if k != "candidates"
            }:
                raise ValueError("replayed probe changed physical authority")
            changes.append(
                dict(
                    visit=visit,
                    receiver=rx,
                    exact=old == new,
                    conditional_candidates=len(old["candidates"]),
                    primary_candidates=len(new["candidates"]),
                    conditional_gate=sum(
                        c["passed_fractional_margin_gate"] for c in old["candidates"]
                    ),
                    primary_gate=sum(c["passed_fractional_margin_gate"] for c in new["candidates"]),
                    conditional_positive=old_hit[rx],
                    primary_positive=hit[rx],
                )
            )
        rows.extend(primary)
    digest = trial.base.recording.digest
    detector = digest([provenance["detector_sha256"], trial.METHOD, binding])
    analysis = digest([source["analysis_manifest_sha256"], detector, rows])
    return dict(
        document,
        provenance=dict(
            provenance,
            detector_sha256=detector,
            run_id="replay-" + analysis[7:39],
            scope="complete primary-only original capture factors from prepared archived no-retry "
            "visits and fresh replay of both receivers at original retry visits",
        ),
        source=dict(source, probes=rows, analysis_manifest_sha256=analysis),
    ), changes


def merged_evidence(work, lock):
    rows, resources = collect(work, lock)
    parent = trial.assay.read_gzip(trial.parent_path(lock, "native.json.gz"))
    current, changes = merge(parent, rows, lock["selected"], _sha(work / "source-lock.json"))
    factors = parity(current, parent)
    if (
        factors["unmatched_probes"]
        or not factors["probe_order_exact"]
        or not all(factors["clock_fields_exact"].values())
        or not all(factors["capture_validity_fields_exact"].values())
        or any(
            c["gate_formula_errors"] or c["candidate_schema_errors"]
            for c in factors["counts"].values()
        )
        or factors["counts"]["reference"]["probes_with_gate_pass"] != 3740
        or factors["counts"]["fresh"]["probes_with_gate_pass"] != 3292
    ):
        raise ValueError("complete primary wave did not preserve its physical and gate contracts")
    return current, rows, resources, changes, factors


def assay_crosscheck(lock, primary, visited):
    (plan,) = (Path(name) for name in lock["input_locks"] if Path(name).name == "input-lock.json")
    whole_iq.checked(plan, lock["input_locks"][str(plan)])
    path = plan.with_name(f"{trial.IDENT}.json.gz")
    evidence = trial.assay.read_gzip(path)
    held = whole_iq.read(plan)["cases"][trial.IDENT]["rows"]
    if (
        evidence["case"] != trial.IDENT
        or evidence["input_lock_sha256"] != _sha(plan)
        or [r["visit"] for r in evidence["rows"]] != [r["visit"] for r in held]
    ):
        raise ValueError("independent IQ sample does not bind the same frozen held plan")
    probes = dict(visit_pairs(primary["source"]["probes"]))
    tallies, measured_pairs = Counter(), []
    for observed, planned in zip(evidence["rows"], held, strict=True):
        visit = observed["visit"]
        conditional = observed["evidence"]["conditional"]
        result = observed["evidence"]["primary12"]
        retry = len(conditional["attempts"]) == 3
        if (
            retry != (visit in visited)
            or conditional["probes"] != planned["probes"]
            or tuple(result["probes"]) != probes[visit]
            or (retry and observed["iq_sha256"] != visited[visit]["iq_sha256"])
        ):
            raise ValueError(f"independent IQ sample disagrees on visit {visit}")
        tallies[f"{observed['cohort']}_{'retry' if retry else 'no_retry'}"] += 1
        if retry and observed["cohort"] == trial.assay.HELD:
            clocks = observed["clocks"]
            by_mode = [
                {r["repetition"]: r for r in clocks[mode]} for mode in ("conditional", "primary12")
            ]
            if any(set(times) != set(range(trial.assay.REPEATS)) for times in by_mode):
                raise ValueError("independent retry timings lost paired repetitions")
            for i in range(trial.assay.REPEATS):
                conditional_time, primary_time = (mode[i] for mode in by_mode)
                measured_pairs.append((conditional_time["cpu_ns"] - primary_time["cpu_ns"]) * 1e-6)
    return path, dict(
        visits=dict(tallies),
        cpu=evidence["cpu"],
        held_retry_paired_cpu_savings_ms=distribution(measured_pairs),
    )


def position(work):
    lock, _ = trial.base.configure(work)
    document, _, _, _, _ = merged_evidence(work, lock)
    native = work / "primary.json"
    payload = encoded(document) + b"\n"
    if native.exists() and native.read_bytes() != payload:
        raise ValueError("measured primary factors changed between attempts")
    if not native.exists():
        write(native, payload)
    plan = work / "publisher-lock.json"
    publisher = dict(publisher_sha256=_sha(Path(__file__)), native_sha256=_sha(native))
    if plan.exists() and whole_iq.read(plan) != publisher:
        raise ValueError("publication plan changed")
    save_json(plan, publisher)
    case, original = whole_iq.binding(trial.IDENT)
    whole.terminal_position(
        work, "primary12", native, work / "actual", lock["workers"][0][0], lock, case, original
    )
    if whole_iq.read(work / "actual/terminal.json")["exit_code"]:
        raise RuntimeError("compact solve failed under its host resource cap")


def pinned_positions(work, lock):
    folder = work / "actual"
    native = work / "primary.json"
    pub = whole_iq.read(work / "publisher-lock.json")
    terminal = whole_iq.read(folder / "terminal.json")
    raw = whole_iq.read(folder / "raw.json")
    end = whole_iq.read(folder / "end.json")
    plan = whole_iq.read(folder / "plan.json")
    request = whole_iq.checked(folder / "recording/request.json", raw["request_sha256"])
    whole_iq.checked(folder / "service.log", terminal["log_sha256"])
    if (
        pub != dict(publisher_sha256=_sha(Path(__file__)), native_sha256=_sha(native))
        or terminal["exit_code"]
        or raw["native_sha256"] != "sha256:" + pub["native_sha256"]
        or plan["source_lock_sha256"] != _sha(work / "source-lock.json")
        or end["memory.max"] != whole_iq.MEMORY
        or end["memory.swap.max"]
        or end["memory.swap.current"]
        or end["memory.events.oom_kill"]
        or end["cpus"] != [lock["workers"][0][0]]
    ):
        raise ValueError("compact position terminal does not bind the frozen waveform and request")
    _, original = whole_iq.binding(trial.IDENT)
    whole_iq.verify_request(
        whole_iq.read(request),
        original,
        native_path=str(native),
        native_sha256=raw["native_sha256"],
    )
    outcome = whole_iq.read(folder / "position.json")
    validate_result(outcome)
    common = dict(
        id=trial.IDENT,
        mode="matched-tile",
        cohort="complete primary-only factors",
        paired_capture_sha256=lock["original"]["native"]["sha256"],
        original_request_sha256=lock["original"]["request"]["sha256"],
        catalog_sha256=lock["original"]["catalog"]["sha256"],
        tile=lock["original"]["tile"],
    )
    rows = [dict(common, method=trial.METHOD, result=outcome, native_sha256=pub["native_sha256"])]
    for path, methods in (
        (trial.parent_path(lock, whole.POS), [trial.prior.METHOD]),
        (
            whole_iq.checked(
                trial.HISTORICAL / "all-positions.jsonl.gz", lock["historical_positions_sha256"]
            ),
            [whole.FOUR, whole.FIVE],
        ),
    ):
        for method in methods:
            (row,) = [
                r for r in whole.rows_from(path) if r["id"] == trial.IDENT and r["method"] == method
            ]
            if any(row[k] != common[k] for k in whole.MINIMAL):
                raise ValueError("prior position differs in physical recording, request, or offer")
            validate_result(row["result"])
            rows.append(dict(row, cohort=common["cohort"]))
    return rows, dict(terminal, end=end)


def detector_timing(lock, rows):
    with trial.parent_path(lock, "timing.csv").open(newline="") as stream:
        old = {
            int(row["visit"]): row for row in csv.DictReader(stream) if row["status"] == "processed"
        }
    if len(old) != 6766 or not rows.keys() <= old.keys() or set(rows) != set(lock["selected"]):
        raise ValueError("historical timing does not span the same valid visit roster")
    samples = []
    for visit, current in sorted(rows.items()):
        previous = old[visit]
        samples.append(
            dict(
                visit=visit,
                conditional_cpu_ms=float(previous["cpu_ms"]),
                conditional_wall_ms=float(previous["wall_ms"]),
                primary_cpu_ms=current["cpu_ns"] * 1e-6,
                primary_wall_ms=current["wall_ns"] * 1e-6,
                primary_grids=current["primary_grids"],
                primary_inverse_ffts=current["fft_inverses"],
                conditional_grids=int(previous["folded_calls"]),
            )
        )
    totals = {
        field: distribution([row[field] for row in samples])
        for field in (
            "conditional_cpu_ms",
            "conditional_wall_ms",
            "primary_cpu_ms",
            "primary_wall_ms",
        )
    }
    all_s = sum(float(r["cpu_ms"]) for r in old.values()) * 1e-3
    selected_old = sum(row["conditional_cpu_ms"] for row in samples) * 1e-3
    selected_new = sum(row["primary_cpu_ms"] for row in samples) * 1e-3
    total_estimate = all_s - selected_old + selected_new
    conditional_primary_grids = sum(row["visits"] * row["primary"] for row in lock["census"])
    projected_grids = 15_330 + sum(r["primary_grids"] - r["conditional_grids"] for r in samples)
    if conditional_primary_grids != projected_grids:
        raise ValueError("measured primary work differs from the historical primary grid census")
    totals.update(
        historical_complete_detector_cpu_s=all_s,
        historical_selected_detector_cpu_s=selected_old,
        historical_nonretry_detector_cpu_s=all_s - selected_old,
        measured_selected_detector_cpu_s=selected_new,
        estimated_complete_primary_detector_cpu_s=total_estimate,
        estimated_ideal_four_core_detector_only_wall_s=total_estimate / 4,
        estimated_ideal_four_core_conditional_detector_only_wall_s=all_s / 4,
        measured_selected_within_20_ms=sum(row["primary_wall_ms"] <= 20 for row in samples),
        complete_primary_grids=projected_grids,
        measured_primary_grids=sum(r["primary_grids"] for r in samples),
    )
    return samples, totals


def wide_factors(primary, positions):
    counts = {}
    by_method = {r["method"]: r for r in positions}
    for method, path in ((whole.FOUR, WIDE_FOUR), (whole.FIVE, WIDE_FIVE)):
        data = path.read_bytes()
        native = gzip.decompress(data) if path.suffix == ".gz" else data
        if sha256(native).hexdigest() != by_method[method]["native_sha256"]:
            raise ValueError("wide position does not bind the native probes being counted")
        reference = json.loads(native)
        comparison = parity(primary, reference)
        if (
            comparison["unmatched_probes"]
            or not comparison["probe_order_exact"]
            or not all(comparison["clock_fields_exact"].values())
            or not all(comparison["capture_validity_fields_exact"].values())
            or any(r["physical_fields"] for r in comparison["changed_probes"])
        ):
            raise ValueError("wide factors use a different physical capture")
        counts[method] = dict(
            path=str(path),
            sha256=_sha(path),
            native_sha256=by_method[method]["native_sha256"],
            counts=comparison["counts"]["reference"],
            gates=comparison["gate_equivalence"],
        )
    return counts


def render_stage(out, timing):
    fig, axes = plot.canvas(
        "Detector cost on DS26-0237 original retry visits",
        "1,592 matched visits · saved IQ · two physical receivers per visit",
        "Conditional timings used host CPUs 0–7 and selected primary timings used CPUs 12–15. "
        "Detector timing excludes IQ decode, file authentication and position.",
    )
    for ax, key, title in zip(axes, ("cpu", "wall"), ("CPU cost", "Monotonic wall"), strict=True):
        values = [timing[f"{mode}_{key}_ms"] for mode in ("conditional", "primary")]
        plot.paired(
            ax,
            ["Original conditional", "12 anchors only"],
            [(v["p50"], v["p95"]) for v in values],
            title=title,
            xlabel="Host milliseconds",
            fmt=".1f",
        )
    plot.key(fig, "Median", "95th percentile")
    fig.savefig(out / "timing.png", dpi=165, facecolor="white")
    fig.savefig(out / "timing.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)
    assets = ("timing.png", "timing.pdf", "timing.csv", "audit.json", "prediction-lock.json")
    save_json(out / "timing-lock.json", {"files": {name: _sha(out / name) for name in assets}})
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="single-pass-primary-retry-timing",
            title="Primary-only original detector timing",
            sample="1,592 DS26-0237 retry-eligible saved-IQ visits",
            boundary="Resident CI16 through two complete original physical detector projections",
            note="The conditional and primary-only costs came from different executions. "
            "Detector costs exclude decode, authentication and compact solve.",
            seal="timing-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="timing.csv",
        ),
    )


def publish(work, out):
    lock, _ = trial.base.configure(work)
    positions, clock = pinned_positions(work, lock)
    document, visited, raw, changes, factors = merged_evidence(work, lock)
    native = work / "primary.json"
    if encoded(document) + b"\n" != native.read_bytes():
        raise ValueError("assembled factors differ from the pre-truth compact solve input")
    receipt = out / "prediction-lock.json"
    if receipt.exists():
        previous = whole_iq.read(receipt)
        for name, digest in previous["files"].items():
            whole_iq.checked(out / name, digest)
        for name in ("launch.json", "publisher-lock.json", "actual/position.json"):
            whole_iq.checked(work / name, previous["files"][f"receipts/{name}"])
    if out != trial.REPORT:
        out.mkdir(parents=True, exist_ok=True)
        for name in ("source-lock.json", "PROTOCOL.md"):
            source = trial.REPORT / name
            target = out / name
            if target.exists():
                whole_iq.checked(target, _sha(source))
            else:
                write(target, source.read_bytes())
    timing_rows, timing = detector_timing(lock, visited)
    csv_file(out / "timing.csv", timing_rows)
    csv_file(out / "changed-visits.csv", changes)
    whole.pack(out / whole.POS, positions)
    write(out / "native.json.gz", gzip.compress(native.read_bytes(), compresslevel=5, mtime=0))
    files = [
        "PROTOCOL.md",
        "source-lock.json",
        "native.json.gz",
        whole.POS,
        "timing.csv",
        "changed-visits.csv",
    ]
    evidence = [
        work / name
        for name in (
            "smoke.json",
            "smoke-input.json",
            "launch.json",
            "raw-exits.json",
            "publisher-lock.json",
        )
    ]
    evidence.extend(path for path in sorted((work / "actual").rglob("*")) if path.is_file())
    evidence.extend(path for path in sorted(work.glob("cpu-*")) if path.is_file())
    for path in evidence:
        destination = Path("receipts") / path.relative_to(work)
        payload = path.read_bytes()
        if path.suffix == ".jsonl":
            destination = destination.with_suffix(".jsonl.gz")
            payload = gzip.compress(payload, compresslevel=5, mtime=0)
        write(out / destination, payload)
        files.append(str(destination))
    plan, sample_checks = assay_crosscheck(lock, document, visited)
    sample_receipt = f"receipts/independent-{trial.IDENT}.json.gz"
    write(out / sample_receipt, plan.read_bytes())
    files.append(sample_receipt)
    files.extend(
        str(path.relative_to(out)) for path in sorted((out / "receipts/preflight-a").glob("*"))
    )
    details = dict(
        stages=dict(
            selected_raw=raw,
            compact=clock,
            conditional_historical={
                k: v
                for k, v in whole_iq.read(trial.parent_path(lock, "audit.json"))["raw"].items()
                if k
                in (
                    "completed_worker_cpu_s",
                    "wall_s",
                    "total_measured_detector_cpu_s",
                    "valid_detector",
                    "largest_worker_peak_bytes",
                )
            },
        ),
        timing=timing,
        factor_comparison=factors,
        independent_sample_crosscheck=sample_checks,
        position_endpoints={r["method"]: endpoint(r["result"]) for r in positions},
        wide_factors=wide_factors(document, positions),
        gate_transitions=dict(
            Counter(
                f"{int(r['conditional_positive'])}->{int(r['primary_positive'])}" for r in changes
            )
        ),
    )
    save_json(out / "audit.json", details)
    files.append("audit.json")
    frozen = dict(
        cases=[trial.IDENT],
        files={name: _sha(out / name) for name in files},
        publisher_sha256=_sha(Path(__file__)),
    )
    if receipt.exists() and whole_iq.read(receipt) != frozen:
        raise ValueError("already frozen pre-truth predictions differ from these outputs")
    save_json(receipt, frozen)

    _, (truth,) = held_references(None, [trial.IDENT])
    scores = whole.geographic(positions, {trial.IDENT: truth})
    csv_file(out / "scores.csv", scores)
    csv_file(
        out / "v5-controls.csv",
        [
            dict(
                role=role,
                arm=arm,
                error_km=truth["reference"][role][arm]["error_km"],
                conditional_rms_hz=truth["reference"][role][arm].get("rf_rms_hz"),
            )
            for role in ROLES
            for arm in ARMS
        ],
    )
    save_json(
        out / "score-lock.json",
        dict(
            prediction_lock_sha256=_sha(receipt),
            files={f: _sha(out / f) for f in ("scores.csv", "v5-controls.csv")},
        ),
    )
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="single-pass-primary-position",
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal=receipt.name,
                    title="Position with the original primary anchors only",
                    caption="The primary-only replay recomputed both receivers on original "
                    "retry visits. All positions used the same 25 km offer and causal request.",
                    provenance=["source-lock.json", "audit.json"],
                    series=[
                        dict(
                            key=key,
                            file=whole.POS,
                            value=method,
                            label=label,
                            native_field="paired_capture_sha256",
                            match=whole.MINIMAL,
                        )
                        for key, method, label in zip(SERIES, METHODS, LABELS, strict=True)
                    ],
                )
            ],
        ),
    )
    render_stage(out, timing)
    whole.generate(out / "charts", evidence=out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("position", "publish"))
    parser.add_argument("work", type=local_output, nargs="?", default=trial.WORK)
    parser.add_argument("--output", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    with trial.configured():
        if args.action == "position":
            position(args.work)
        else:
            publish(args.work, args.output)


if __name__ == "__main__":
    main()
