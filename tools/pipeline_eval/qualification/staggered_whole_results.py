"""Seal measured staggered positions and audit every antenna against its released branch."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from .. import iq_service, whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distribution, validate_result
from ..variants.selective_capture import visit_pairs
from . import screening_figures
from . import staggered_whole as trial
from .arrival_queue import fingerprint
from .fresh_replay_results import ROOF_REFERENCES, geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

POSITIONS = "positions.jsonl.gz"
VISITS = "visits.jsonl.gz"
CONTROLS = {"control": "receiver_choice_four", "candidate": "receiver_choice_five"}
PAIR_FIELDS = ("paired_capture_sha256", "original_request_sha256", "catalog_sha256", "tile", "mode")


def per_call(rows):
    valid = [r for r in rows if r["status"] == "processed"]
    result = dict(physical_visits_seen=len(rows), native_calls=len(valid))
    if valid:
        for field in ("wall", "typed", "cpu"):
            sample = [r[f"{field}_ns"] for r in valid]
            values = distribution(v / 1e6 for v in sample)
            result.update({f"native_{field}_{q}_ms": values[q] for q in ("p50", "p95", "p99")})
            if field != "cpu":
                count = sum(x <= 20_000_000 for x in sample)
                result[f"{field}_within_20ms"] = count
                result[f"{field}_within_20ms_fraction"] = count / len(sample)
        result["decoded_within_20ms"] = result["wall_within_20ms"]
        result["decoded_within_20ms_fraction"] = result["wall_within_20ms_fraction"]
        for lane in (0, 1):
            values = distribution(r["lanes"][lane]["cpu_ns"] / 1e6 for r in valid)
            result[f"lane{lane}_cpu_p50_ms"] = values["p50"]
    return result


def measurement(folder, ident, plan):
    service = whole_iq.read(folder / "service.json")
    log = whole_iq.checked(folder / "service.log", service["log_sha256"])
    if whole_iq.read(folder / "plan.json") != plan:
        raise ValueError("measured service differs from the staggered source seal")
    source = plan["capture"]["case"]
    trace_path = folder / "visits.jsonl"
    raw_path = folder / "raw-worker.json"
    trace = trace_path if trace_path.is_file() else None
    raw = whole_iq.read(raw_path) if raw_path.is_file() else None
    records = [] if trace is None else rows_from_plain(trace, complete=raw is not None)
    stats = dict(
        id=ident,
        raw_complete=raw is not None,
        detector_cores=[trial.MAIN, trial.HELPER],
        limit_s=trial.LIMIT_S,
        **per_call(records),
    )
    start = whole_iq.read(folder / "start.json") if (folder / "start.json").is_file() else None
    stages = [start] if start else []
    proof = dict(service=service)
    native, digest = None, None
    handoff = None
    if raw:
        if trace is None or _sha(trace) != raw["trace_sha256"]:
            raise ValueError("staggered raw trace changed after its terminal receipt")
        native = whole_iq.checked(folder / "recording/native.json", raw["native_sha256"])
        digest = _sha(native)
        expected = source["recording"]["window_count"]
        if (
            [r["visit"] for r in records] != list(range(expected))
            or stats["native_calls"] != raw["counts"]["processed_windows"]
            or raw["compressed_chunks"] < 1
        ):
            raise ValueError("the complete raw receipt lacks the frozen samples or call ledger")
        stages.extend((raw["start"], raw["end"]))
        stats.update(
            raw_worker_wall_s=raw["end"]["monotonic_s"] - raw["start"]["monotonic_s"],
            raw_worker_rss_kib=raw["end"]["rss_peak_kib"],
            raw_wall_s=raw["end"]["monotonic_s"] - start["monotonic_s"],
            compressed_chunks=raw["compressed_chunks"],
            compressed_bytes=raw["compressed_bytes"],
            counts=raw["counts"],
        )
        proof["raw"] = raw
    if (folder / "raw.json").is_file():
        handoff = whole_iq.read(folder / "raw.json")
        if handoff["native_sha256"] != digest:
            raise ValueError("position request does not bind the emitted native input")
        whole_iq.checked(folder / "recording/request.json", handoff["request_sha256"])
        stages.append(handoff["position_start"])
        stats["raw_wall_s"] = stages[-1]["monotonic_s"] - start["monotonic_s"]
        proof["native_bound_request_sha256"] = handoff["request_sha256"]
    state = service["systemd"]["Result"]
    if iq_service.succeeded(service):
        if handoff is None:
            raise ValueError("a successful service has no position input binding")
        end = whole_iq.read(folder / "end.json")
        stages.append(end)
        result = whole_iq.read(folder / "position.json")
        stats.update(
            pipeline_wall_s=end["monotonic_s"] - start["monotonic_s"],
            position_wall_s=end["monotonic_s"] - handoff["position_start"]["monotonic_s"],
            cgroup_cpu_s=(end["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"]) / 1e6,
            charged_peak_bytes=end["memory.peak"],
        )
    else:
        result = dict(
            status="timed_out" if state == "timeout" else "failed",
            reason=state,
            boundary="Complete saved IQ through staggered native and position",
            metrics={},
            arms={arm: {"latlon": None} for arm in ARMS},
        )
        stats["wall_to_terminal_s"] = service.get("supervisor_s", service.get("service_wall_s"))
    validate_result(result)
    if any(
        stage["cgroup"] != start["cgroup"]
        or stage["memory.max"] != whole_iq.MEMORY
        or stage["memory.swap.max"] != 0
        or stage["memory.swap.current"] != 0
        or stage["memory.peak"] > whole_iq.MEMORY
        for stage in stages
    ):
        raise ValueError("staggered recording left the assigned bounded cgroup")
    stats["position_status"] = result["status"]
    proof["stages"] = stages
    position = dict(
        id=ident,
        method=trial.METHOD,
        mode="matched-tile",
        cohort="fresh saved IQ",
        paired_capture_sha256=source["native"]["sha256"],
        capture_era_native_sha256=source["native"]["sha256"],
        original_request_sha256=source["request"]["sha256"],
        catalog_sha256=source["catalog"]["sha256"],
        tile=source["regions"][0],
        result=result,
    )
    if digest:
        position["native_sha256"] = digest
    return position, stats, proof, records, native, log


def rows_from_plain(path, *, complete=True):
    with path.open() as stream:
        return [json.loads(line) for line in stream if complete or line.endswith("\n")]


def seal(work, report):
    lock = whole_iq.read(
        whole_iq.checked(
            report / "source-lock.json", whole_iq.read(work / "launch-lock.json")["source_sha256"]
        )
    )
    files = ["source-lock.json", "PROTOCOL.md", "resources.json", "timing.csv", VISITS, POSITIONS]
    rows, traces, resources = [], [], {}
    for ident, plan in lock["cases"].items():
        position, stats, proof, events, native, log = measurement(work / ident, ident, plan)
        rows.append(position)
        traces.extend(dict(id=ident, **row) for row in events)
        resources[ident] = dict(stats, witnesses=proof)
        log_name = f"{ident}.service.log"
        write(report / log_name, log.read_bytes())
        files.append(log_name)
        if native:
            name = f"native/{ident}.json.gz"
            write(report / name, gzip.compress(native.read_bytes(), mtime=0))
            files.append(name)
    pack(report / POSITIONS, rows)
    pack(report / VISITS, traces)
    save_json(report / "resources.json", resources)
    timing = [
        {k: v for k, v in resource.items() if k not in ("witnesses", "counts", "detector_cores")}
        for resource in resources.values()
    ]
    fields = list(dict.fromkeys(k for row in timing for k in row))
    csv_file(report / "timing.csv", [{k: row.get(k) for k in fields} for row in timing])
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=list(lock["cases"]),
            files={name: _sha(report / name) for name in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def authority(document):
    """Keep every physical field while omitting detector and branch lineage."""
    return dict(
        document,
        source={
            k: v
            for k, v in document["source"].items()
            if k not in ("probes", "analysis_manifest_sha256")
        },
        provenance={
            k: v
            for k, v in document["provenance"].items()
            if k not in ("run_id", "detector_sha256", "scope")
        },
    )


def parity(trace, native, controls, references):
    if any(authority(ref) != authority(native) for ref in controls.values()):
        raise ValueError("staggered observable/counter/clock authority differs from released arms")
    roles = tuple(CONTROLS)
    selected = dict(visit_pairs(native["source"]["probes"]))
    source = {role: dict(visit_pairs(controls[role]["source"]["probes"])) for role in roles}
    if any(list(pairs) != list(selected) for pairs in source.values()):
        raise ValueError("released branches disagree on valid physical visit IDs")
    bands = defaultdict(Counter)
    by_role = {role: Counter() for role in roles}
    mismatches = []
    counts = Counter()
    for i, (row, stock, fifth) in enumerate(zip(trace, *references, strict=True)):
        for control in (stock, fifth):
            names = ("visit", "status", "visit_metadata_sha256")
            if [row[k] for k in names] != [control[k] for k in names] or row["visit"] != i:
                raise ValueError(f"physical visit metadata differs at visit {i}")
        if row["status"] == "invalid_capture":
            if (
                i in selected
                or "fifth_lane" in row
                or len({x["full_visit_sha256"] for x in (row, stock, fifth)}) != 1
            ):
                raise ValueError("invalid acquisition changed or advanced the schedule")
            counts["invalid"] += 1
            continue
        tally = bands[row["rf_center_hz"]]
        lane = (tally[0] + tally[1]) % 2
        if row["fifth_lane"] != lane:
            raise ValueError(f"per-RF stagger sequence changed at visit {i}")
        tally[lane] += 1
        counts["valid"] += 1
        for rx, probe in enumerate(selected[i]):
            key = "candidate" if rx == lane else "control"
            ref = fifth if rx == lane else stock
            expected = source[key][i][rx]
            actual_probe, expected_probe = fingerprint(probe), fingerprint(expected)
            actual_array = fingerprint(probe["candidates"])
            expected_array = ref["probes"][rx]["payload_sha256"]
            if fingerprint(expected["candidates"]) != expected_array:
                raise ValueError(f"released {key} rows disagree with their receipt at visit {i}")
            matches = actual_probe == expected_probe and actual_array == expected_array
            by_role[key][f"rx{rx}_matched"] += int(matches)
            by_role[key][f"rx{rx}_mismatched"] += int(not matches)
            if not matches:
                mismatches.append(
                    dict(
                        visit=i,
                        rx=rx,
                        role=key,
                        actual_probe_sha256=actual_probe,
                        expected_probe_sha256=expected_probe,
                        actual_candidates_sha256=actual_array,
                        expected_candidates_sha256=expected_array,
                    )
                )
            counts[key] += 1
        counts["visits_changed_from_stock"] += (
            row["full_visit_sha256"] != stock["full_visit_sha256"]
        )
        counts["visits_changed_from_fifth"] += (
            row["full_visit_sha256"] != fifth["full_visit_sha256"]
        )
    if counts["valid"] != len(selected) or len(trace) != native["provenance"]["window_count"]:
        raise ValueError("comparison omitted expected physical probe support")
    return dict(
        counts,
        status="mismatch" if mismatches else "exact",
        per_role_lane=by_role,
        discrepancies=mismatches,
        rf_fifth_lanes={rf: dict(count) for rf, count in bands.items()},
    )


def exact_audit(report):
    child = sealed(report, "prediction-lock.json")
    parent = sealed(trial.PARENT, "raw-prediction-lock.json")
    own, external = defaultdict(list), defaultdict(list)
    for row in rows_from(report / VISITS):
        own[row["id"]].append(row)
    for row in rows_from(trial.PARENT / VISITS):
        external[row["id"], row["role"]].append(row)
    parent_authority = whole_iq.read(trial.PARENT / "raw-authority.json")
    predictions = {row["id"]: row for row in rows_from(report / POSITIONS)}
    audits = {}
    for ident in child["cases"]:
        native = f"native/{ident}.json.gz"
        names = {role: f"native/{role}/{ident}.json.gz" for role in CONTROLS}
        if native not in child["files"] or any(
            name not in parent["files"] for name in names.values()
        ):
            audits[ident] = dict(
                status="incomplete", reason="one or more complete native streams unavailable"
            )
            continue
        raw_digests = dict(
            staggered=predictions[ident]["native_sha256"],
            **{role: parent_authority[ident][role]["native_sha256"] for role in CONTROLS},
        )
        own_document = read_gzip(report / native, raw_digests["staggered"])
        released = {
            role: read_gzip(trial.PARENT / name, raw_digests[role]) for role, name in names.items()
        }
        try:
            observed = parity(
                own[ident], own_document, released, [external[ident, role] for role in CONTROLS]
            )
        except ValueError as error:
            observed = dict(status="unverifiable", reason=str(error))
        audits[ident] = dict(observed, native_sha256=raw_digests)
    save_json(
        report / "probe-parity.json",
        dict(
            cases=audits,
            raw_parent_sha256=_sha(trial.PARENT / "raw-prediction-lock.json"),
            prediction_sha256=_sha(report / "prediction-lock.json"),
        ),
    )


def read_gzip(path, expected):
    data = gzip.decompress(path.read_bytes())
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"native document SHA-256 differs from its prediction binding: {path}")
    return json.loads(data)


def stage(report):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullFormatter

    own = sealed(report, "prediction-lock.json")
    traces = defaultdict(list)
    for row in rows_from(report / VISITS):
        if row["status"] == "processed":
            traces[row["id"]].append(row["wall_ns"] / 1e6)
    stats = whole_iq.read(report / "resources.json")
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
    fig.suptitle("Staggered detector on complete saved IQ", fontsize=18, fontweight="bold")
    colors = ("#0d7773", "#49608f")
    for i, ident in enumerate(own["cases"]):
        values = sorted(traces[ident])
        if values:
            axes[0].step(
                values,
                [(k + 1) / len(values) for k in range(len(values))],
                where="post",
                color=colors[i],
                label=ident,
            )
        row = stats[ident]
        raw = row.get("raw_wall_s")
        if raw is not None:
            axes[1].barh(
                i, raw, height=0.48, color="#117d79", label="Raw and handoff" if not i else None
            )
        fit = row.get("position_wall_s")
        if fit is not None:
            axes[1].barh(
                i,
                fit,
                left=raw,
                height=0.48,
                color="#7592a4",
                label="Both position fits" if not i else None,
            )
        if fit is None:
            axes[1].text(
                (row.get("wall_to_terminal_s") or raw or 0) * 0.5,
                i,
                row["position_status"],
                va="center",
                ha="center",
                color="#983a30",
            )
    axes[0].axvline(20, color="#ac4b42", ls="--", label="20 ms")
    axes[0].set(
        xscale="log", xlabel="Complete native response (ms)", ylabel="Fraction of native calls"
    )
    axes[0].set_xticks([10, 20, 50, 100, 500, 1000], labels=[10, 20, 50, 100, 500, 1000])
    axes[0].xaxis.set_minor_formatter(NullFormatter())
    axes[1].set(
        xlabel="Elapsed host service time (s)",
        yticks=range(len(own["cases"])),
        yticklabels=own["cases"],
    )
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="x", alpha=0.22)
        ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    for ext in ("png", "pdf"):
        fig.savefig(report / f"staggered-whole-timing.{ext}", dpi=155)
    plt.close(fig)
    names = (
        "prediction-lock.json",
        "timing.csv",
        "staggered-whole-timing.png",
        "staggered-whole-timing.pdf",
    )
    save_json(
        report / "stage-lock.json",
        dict(cases=own["cases"], files={n: _sha(report / n) for n in names}),
    )
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="staggered-whole-timing",
            title="Staggered detector on complete saved IQ",
            boundary="Whole raw-IQ replay and position in one capped service",
            sample="Two lower-edge recordings · one fifth-center antenna per valid visit",
            note="Unpaced replay. The native clock starts with a complete CI16 window.",
            seal="stage-lock.json",
            image="staggered-whole-timing.png",
            pdf="staggered-whole-timing.pdf",
            csv="timing.csv",
        ),
    )


def score(report):
    own = sealed(report, "prediction-lock.json")
    parent = sealed(trial.PARENT, "prediction-lock.json")
    roof = sealed(trial.PARENT, "score-lock.json")
    for name in ROOF_REFERENCES.values():
        write(
            report / name, whole_iq.checked(trial.PARENT / name, roof["files"][name]).read_bytes()
        )
    selected = rows_from(report / POSITIONS)
    controls = rows_from(trial.PARENT / POSITIONS)
    merged = [*selected, *controls]
    paired = {r["id"]: r for r in selected}
    if len(controls) != 2 * len(paired) or any(
        any(r[k] != paired[r["id"]][k] for k in PAIR_FIELDS) for r in controls
    ):
        raise ValueError("staggered and released branch endpoints use different physical cases")
    for name, lock in (("parent-prediction-lock.json", parent), ("parent-score-lock.json", roof)):
        save_json(report / name, lock)
    exact_audit(report)
    pack(report / "matched-positions.jsonl.gz", merged)
    (ds26, ds29) = own["cases"]
    _, (ref_old,) = held_references(None, [ds26])
    roof_inputs = dict(files={n: _sha(report / n) for n in ROOF_REFERENCES.values()})
    refs = {
        ds26: ref_old,
        **screening_figures.new_roof_references(report, roof_inputs, ROOF_REFERENCES, [ds29]),
    }
    csv_file(report / "position-scores.csv", geographic(merged, refs))
    files = (
        "prediction-lock.json",
        "matched-positions.jsonl.gz",
        "position-scores.csv",
        "probe-parity.json",
        "parent-prediction-lock.json",
        "parent-score-lock.json",
        *ROOF_REFERENCES.values(),
    )
    save_json(
        report / "figure-lock.json",
        dict(
            cases=own["cases"],
            files={n: _sha(report / n) for n in files},
        ),
    )
    series = [
        dict(
            key=key,
            value=method,
            label=label,
            file="matched-positions.jsonl.gz",
            native_field="paired_capture_sha256",
            **({"match": list(PAIR_FIELDS)} if key != "one" else {}),
        )
        for key, method, label in (
            ("one", trial.METHOD, "Measured staggered fifth center"),
            ("stock", CONTROLS["control"], "Stock four centers"),
            ("all_visits", CONTROLS["candidate"], "Fifth center on both antennas"),
        )
    ]
    save_json(
        report / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="staggered-whole",
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    title="Staggered fifth center on complete saved IQ",
                    caption=(
                        "Two lower-edge recordings from one roof. All three policies used the same "
                        "phase-release position model, causal catalogue and offer. "
                        "Original v5 used capture-era factors."
                    ),
                    seal="figure-lock.json",
                    provenance=list(files),
                    roof_references=ROOF_REFERENCES,
                    series=series,
                )
            ],
        ),
    )
    screening_figures.generate(report / "charts", evidence=report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "audit", "score", "stage"))
    parser.add_argument("--work", type=local_output)
    parser.add_argument("--report", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.work, args.report)
    else:
        {"audit": exact_audit, "score": score, "stage": stage}[args.action](args.report)


if __name__ == "__main__":
    main()
