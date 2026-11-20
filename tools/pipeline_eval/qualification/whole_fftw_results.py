"""Seal the fresh FFTW replays before joining independent stock and NumPy controls."""

import argparse
import gzip
from collections import Counter
from pathlib import Path

from .. import figure_books, iq_comparison_results, iq_service, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES
from . import frontier_whole_replay_results as prior
from . import scout_control_check, whole_band_results
from . import whole_fftw_trial as trial
from .full_held_scores import held_references
from .full_v5_check import _sha
from .winner_stream_results import csv_file

ARCHIVE = trial.prior.REPORT
ROLES_WITH_RUNS = ("stock", "numpy", "fftw")
NAMES = {"stock": "Stock 21-bin wide", "numpy": "NumPy differential", "fftw": "FFTW differential"}
AUTHORITY = (*scout_control_check.INPUT_FIELDS, "paired_capture_sha256")
PREDICTIONS, RESOURCES, VISITS = "positions.jsonl.gz", "resources.json", "visits.jsonl.gz"


def pack(path, rows):
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


def pending(work):
    missing = []
    for ident in trial.CASES:
        folder = work / ident
        service = folder / "candidate/service.json"
        failed = (folder / "candidate-failure.json").is_file()
        if service.is_file():
            done = (
                iq_service.succeeded(whole_iq.read(service))
                and (folder / "candidate/end.json").is_file()
            )
            if done or failed:
                continue
        elif failed and not (folder / "candidate/service-launch.json").exists():
            continue
        missing.append(ident)
    return missing


def seal(work, out=trial.REPORT):
    if (out / "prediction-lock.json").is_file():
        scout_control_check.sealed(out)
        return
    if pending(work):
        raise ValueError("the two prospective FFTW services have pending terminal receipts")
    lock = trial.binding(work)
    raw_positions, traces, resources, archive_names = [], [], {}, []
    for ident in trial.CASES:
        row, resource, native = whole_band_results.attempt(
            work, ident, "candidate", lock, method=trial.METHOD
        )
        raw_positions.append(row)
        resources[ident] = {"fftw": resource}
        attempt = work / ident / "candidate"
        if native is not None:
            member = f"native/{ident}.json.gz"
            write(out / member, gzip.compress(native.read_bytes(), compresslevel=6, mtime=0))
            archive_names.append(member)
            data = prior.detector_rows(attempt)
            visit_rows = list(prior.trace_rows(ident, "fftw", data))
            resource["fftw_intervention"] = prior.scout_trace(attempt, visit_rows)
            resource["logical_native_sha256"] = data[2]
            traces.extend(visit_rows)
    prior.protect_resources(resources)
    pack(out / PREDICTIONS, raw_positions)
    pack(out / VISITS, traces)
    save_json(out / RESOURCES, resources)
    names = ["PROTOCOL.md", "source-lock.json", PREDICTIONS, RESOURCES, VISITS, *archive_names]
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=list(trial.CASES),
            files={name: _sha(out / name) for name in names},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def verify_prior(new, previous, freeze):
    fields = (
        "recording",
        "request_sha256",
        "catalog_sha256",
        "tile",
        "orbit_snapshots",
        "clock_authority",
        "capture_native_sha256",
    )
    if (
        set(new["cases"]) != set(previous["cases"])
        or previous["activation"]["prospective_lock_sha256"] != freeze
        or new["receiver_files"] != previous["receiver_files"]
        or new["native_sources"] != previous["native_sources"]
        or any(new[k] != previous[k] for k in ("limit_s", "memory_max", "swap_max"))
        or previous["detectors"]["candidate"]["sha256"] != new["detectors"]["candidate"]["sha256"]
        or any(new["cases"][i][k] != previous["cases"][i][k] for i in new["cases"] for k in fields)
    ):
        raise ValueError("the independent controls differ in scientific input or service budget")


def compare_hints(numpy, fftw):
    changed_hints = changed_insertions = scheduled = 0
    for old, new in zip(numpy, fftw, strict=True):
        if old["visit"] != new["visit"] or old["status"] != new["status"]:
            raise ValueError("the candidate implementations must preserve visit boundaries")
        if old["status"] != "processed":
            continue
        scheduled += 2
        for key in ("hints", "changed"):
            before, after = (r["differential"][key] for r in (old, new))
            count = sum(a != b for a, b in zip(before, after, strict=True))
            if key == "hints":
                changed_hints += count
            else:
                changed_insertions += count
    return dict(
        compared_receiver_visits=scheduled,
        different_rank_one_hints=changed_hints,
        different_hint_insertions=changed_insertions,
    )


def compare_case(rows, traces):
    result = {}
    for reference in ("stock", "numpy"):
        before, after = rows[reference], rows["fftw"]
        if any(before[k] != after[k] for k in AUTHORITY):
            raise ValueError("position requests must use the same causal catalogue and tile")
        complete = bool(traces[reference]) and bool(traces["fftw"])
        raw = prior.compare_probes(traces[reference], traces["fftw"]) if complete else None
        info = dict(
            raw_complete={k: bool(traces[k]) for k in (reference, "fftw")},
            native_bytes_exact=(
                before["native_sha256"] == after["native_sha256"] if complete else None
            ),
            candidate_array_and_gate_counts=raw,
            position=scout_control_check.endpoints(after["result"], before["result"]),
        )
        normalized = (prior.scientific_result(r["result"]) for r in (before, after))
        info["normalized_solver_exact"] = (
            encoded(next(normalized)) == encoded(next(normalized))
            if all(r["result"]["status"] in ("ok", "withheld") for r in (before, after))
            else None
        )
        if reference == "numpy" and complete:
            info["rank_one_and_insertion"] = compare_hints(traces[reference], traces["fftw"])
        result[reference] = info
    return result


def load_comparison(out):
    own, own_sha = scout_control_check.sealed(out)
    earlier, prior_sha = scout_control_check.sealed(ARCHIVE)
    if prior.TRACE not in earlier["files"]:
        raise ValueError("the independent NumPy/stock probe and timing audit is still pending")
    ours, previous = (whole_iq.read(folder / "source-lock.json") for folder in (out, ARCHIVE))
    freeze = str((ARCHIVE / "prospective-lock.json").relative_to(whole_iq.ROOT))
    verify_prior(ours, previous, ours["inputs"][freeze])
    methods = dict(
        stock=iq_comparison_results.method(previous["spec"]["id"], "control"),
        numpy=iq_comparison_results.method(previous["spec"]["id"], "candidate"),
        fftw=trial.METHOD,
    )
    rows = {
        role: scout_control_check.positions(
            out if role == "fftw" else ARCHIVE, own if role == "fftw" else earlier, method
        )
        for role, method in methods.items()
    }
    old_roles = {"control": "stock", "candidate": "numpy"}
    merged = prior.load_rows(out / VISITS) + [
        dict(row, role=old_roles[row["role"]]) for row in prior.load_rows(ARCHIVE / prior.TRACE)
    ]
    resource_old = whole_iq.read(ARCHIVE / RESOURCES)
    resource_new = whole_iq.read(out / RESOURCES)
    resources = {
        i: {old_roles[k]: val for k, val in resource_old[i].items()} | resource_new[i]
        for i in trial.CASES
    }
    prior.protect_resources(resources)
    audit = {}
    for ident in trial.CASES:
        traces = {
            role: [r for r in merged if (r["id"], r["role"]) == (ident, role)]
            for role in ROLES_WITH_RUNS
        }
        audit[ident] = compare_case({role: group[ident] for role, group in rows.items()}, traces)
    save_json(
        out / "audit.json",
        dict(
            cases=audit,
            independent_fftw_prediction_lock_sha256=own_sha,
            independent_numpy_and_stock_prediction_lock_sha256=prior_sha,
        ),
    )
    return rows, [r for r in merged if r["status"] == "processed"], resources, methods


def summarize_runtime(resources, traces):
    table = prior.timing_rows(resources, traces)
    for row in table:
        ident, role = row["id"], row["role"]
        item = resources[ident][role]
        data = [
            r["differential"]
            for r in traces
            if (r["id"], r["role"]) == (ident, role) and "differential" in r
        ]
        row.update(
            scout_cpu_s=sum(r["scout_cpu_ns"] for r in data) / 1e9 if data else None,
            wall_to_failure_s=item.get("wall_to_failure_s"),
            cpu_to_failure_s=item.get("cpu_to_failure_s"),
            positive_candidates=item.get("counts", {}).get("positive_candidates"),
        )
    return table


def add_scores(rows, resources):
    _, references = held_references(None, list(trial.CASES))
    by_id = {r["id"]: r["reference"] for r in references}
    for role, keyed in rows.items():
        temp = [dict(row, method="current_candidate") for row in keyed.values()]
        stats = {ident: {"candidate": values[role]} for ident, values in resources.items()}
        for row in iq_comparison_results.score_rows(temp, stats, references, "current"):
            row["branch"] = role
            for name in ROLES:
                ref = by_id[row["id"]][name][row["arm"]]
                row[f"{name}_km"] = ref["error_km"]
                row[f"{name}_status"] = ref["status"]
            yield row


def publish(out=trial.REPORT):
    rows, traces, resources, methods = load_comparison(out)
    pack(out / "comparison.jsonl.gz", [row for group in rows.values() for row in group.values()])
    csv_file(out / "deadlines.csv", summarize_runtime(resources, traces))
    scores = list(add_scores(rows, resources))
    csv_file(out / "scores.csv", scores)
    summary = {}
    for role in ROLES_WITH_RUNS:
        summary[role] = {
            arm: Counter(
                attempted=len(sample),
                published=sum(r["published"] for r in sample),
                within_5pct=sum(r["within_5pct"] is True for r in sample),
                within_10pct=sum(r["within_10pct"] is True for r in sample),
            )
            for arm in ARMS
            if (sample := [r for r in scores if r["branch"] == role and r["arm"] == arm])
        }
    save_json(out / "summary.json", summary)
    provenance = [
        "prediction-lock.json",
        "audit.json",
        "scores.csv",
        "deadlines.csv",
        "summary.json",
    ]
    save_json(
        out / "figure-lock.json",
        dict(
            cases=list(trial.CASES),
            files={p: _sha(out / p) for p in ("comparison.jsonl.gz", *provenance)},
            source_lock_sha256=_sha(out / "source-lock.json"),
        ),
    )
    series = []
    for role, key in zip(
        ("fftw", "numpy", "stock"), ("one", "one_native_factors", "stock"), strict=True
    ):
        row = dict(
            key=key,
            label=NAMES[role],
            value=methods[role],
            file="comparison.jsonl.gz",
            native_authority="frozen",
            native_field="paired_capture_sha256",
        )
        if role != "fftw":
            row["match"] = list(AUTHORITY)
        series.append(row)
    chart = dict(
        id="frontier-whole-fftw",
        method=trial.METHOD,
        scope="roof",
        cases=list(trial.CASES),
        title="Native FFTW scout on two complete held recordings",
        caption="Same-window FFTW and NumPy scouts feed the same wide detector and phase release. "
        "Stock wide uses original starts. All run on the same saved IQ and original tile. "
        "The four original v5 controls use capture-era factors.",
        seal="figure-lock.json",
        provenance=provenance,
        series=series,
        source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
    )
    save_json(out / "figures.json", dict(version=1, charts=[chart]))
    figure_books.generate(out / "charts", ARMS, panel="screening", evidence=out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("pending", "seal", "publish"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    if args.command == "pending":
        missing = pending(args.work)
        for ident in missing:
            print(ident)
        raise SystemExit(2 if missing else 0)
    if args.command == "seal":
        seal(args.work)
    else:
        publish()


if __name__ == "__main__":
    main()
