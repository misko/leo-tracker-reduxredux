"""Bind family allocation, same-input archive parity and standard position charts."""

import argparse
import json
from pathlib import Path

from ..__main__ import local_output, save_json
from ..scoring import ARMS, distance_km
from . import family_memory_trial as trial
from . import screening_figures as figures
from .marginal_offset_results import _rows
from .native_lean_eval import _write_predictions
from .phase_confirmation import _read, digest
from .prefix_figures import csv_file
from .secant_full import _verify_files

FILES = ("positions.jsonl.gz", "stock-positions.jsonl.gz", "archived-positions.jsonl.gz")
INPUTS = ("input_sha256", "native_sha256", "catalog_sha256", "tile", "detector")


def parity(candidate, reference):
    if any(candidate[k] != reference[k] for k in ("id", *INPUTS)):
        raise ValueError("family-memory comparison has mismatched scientific inputs")
    a, b = (r["result"] for r in (candidate, reference))
    if a["status"] != "ok" or b["status"] != "ok":
        return dict(compared=False, statuses=[a["status"], b["status"]])
    x, y = (r["metrics"] for r in (a, b))
    fresh, ref = (r["composed_memory_measurement"]["evidence"] for r in (x, y))
    keys = ("frequency_score", "conditional_rms_hz", "associated_observations")
    proof = dict(
        endpoints=a["arms"] == b["arms"],
        timed_science_receipts=fresh == ref,
        orbital_work=x["bounded_recovery_rows"] == y["bounded_recovery_rows"],
        optimizer_counts={k: v for k, v in x["position_optimizer"].items() if k != "wall_s"}
        == {k: v for k, v in y["position_optimizer"].items() if k != "wall_s"},
    )
    proof.update(
        {f"{arm}_{k}": x.get(f"{arm}_{k}") == y.get(f"{arm}_{k}") for arm in ARMS for k in keys}
    )
    if "family_memory_audit" in y:
        (first,), (second,) = (r["family_memory_audit"] for r in (x, y))
        old_width, new_width = (
            next(
                e["shape"]["receipt_sha256"]
                for e in row["events"]
                if e["stage"] == "full_catalogue_widths"
            )
            for row in (first, second)
        )
        proof["causal_widths_exact"] = old_width == new_width
        for k in (
            "profiles",
            "generated_profiles_sha256",
            "rank_order_sha256",
            "confidence_sha256",
        ):
            proof[k] = first[k] == second[k]
    return dict(compared=True, exact=all(proof.values()), checks=proof)


def metrics(row):
    m = row["result"]["metrics"]
    composed = m.get("composed_memory_measurement", {})
    stage = next((s for s in composed.get("stages", []) if s["stage"] == "confidence_for"), {})
    family = m.get("family_memory_audit", [])
    return dict(
        cpu=row["cpu"],
        worker_cpu_s=row["worker_cpu_s"],
        worker_wall_s=row["worker_wall_s"],
        peak_rss_kib=composed.get("after", {}).get("peak_rss_kib"),
        family_peak_rss_kib=stage.get("after", {}).get("peak_rss_kib"),
        family_entry_rss_kib=stage.get("before", {}).get("rss_kib"),
        family_return_rss_kib=stage.get("after", {}).get("rss_kib"),
        family_wall_s=stage.get("wall_s"),
        family_cpu_s=stage.get("cpu_s"),
        traces=family,
    )


def partial_observer(work, row):
    marker = work / "cpu18-release.json"
    if not marker.exists() or row["result"]["status"] == "ok":
        return None
    release = _read(marker)
    if (row["id"], row["method"], row["cpu"]) != (release["id"], release["method"], release["cpu"]):
        return None
    row["result"]["metrics"]["last_worker_status"] = row["result"]["reason"]
    row["result"]["reason"] = release["reason"]
    log = work / row["id"] / row["method"] / "worker.log"
    prefix = "family-allocation: "
    (trace,) = [
        json.loads(line.removeprefix(prefix))
        for line in log.read_text().splitlines()
        if line.startswith(prefix)
    ]
    return dict(trace=trace, release=release)


def publish(work, report):
    report = local_output(report)
    plan = _read(work / "plan.json")
    if plan["source"] != trial.sources():
        raise ValueError("new or inherited sources differ from the pre-run plan")
    prev = trial.archive.REPORT
    _verify_files(prev, _read(prev / "prediction-lock.json")["files"])
    prior = _rows(prev / "uncapped-positions.jsonl.gz")[trial.DS29]
    tiled_root = trial.archive.PRIOR
    _verify_files(tiled_root, _read(tiled_root / "prediction-lock.json")["files"])
    tiled = _rows(tiled_root / "tile-positions.jsonl.gz")[trial.DS26]
    canonical = plan["inputs"]
    result, resources, scores, tracked = {}, {}, [], []
    refs, _ = figures.shared._frozen_roof()
    for ident in (trial.DS29, trial.DS26):
        paths = [work / f"{ident}-{method}.json" for method in trial.MODES]
        if ident == trial.DS26 and not any(p.exists() for p in paths):
            continue
        rows = [_read(path) for path in paths]
        for row in rows:
            if any(row[k] != v for k, v in canonical[ident]["native"].items()) or (
                row["input_sha256"] != canonical[ident]["request_sha256"]
            ):
                raise ValueError("actual science request differs from the sealed family roster")
        candidate, stock = rows
        partial = partial_observer(work, stock)
        archived_row = prior if ident == trial.DS29 else tiled
        row_set = [*rows, archived_row]
        result[ident] = {"fresh": parity(candidate, stock)}
        if ident == trial.DS29:
            result[ident]["archived_candidate"] = parity(candidate, prior)
            result[ident]["archived_instrumented_stock"] = parity(stock, prior)
        else:
            result[ident]["archived_candidate"] = trial.archive.same_science(tiled, candidate)
        resources[ident] = {
            tag: metrics(row)
            for tag, row in zip(("candidate", "fresh", "archived"), row_set, strict=True)
        }
        if partial is not None:
            trace = partial["trace"]
            resources[ident]["fresh"].update(
                family_peak_rss_kib=trace["after"]["peak_rss_kib"],
                family_entry_rss_kib=trace["before"]["rss_kib"],
                family_return_rss_kib=trace["after"]["rss_kib"],
                family_wall_s=trace["wall_s"],
                family_cpu_s=trace["cpu_s"],
                traces=[trace],
                interrupted=partial["release"],
            )
            (current,) = candidate["result"]["metrics"]["family_memory_audit"]
            result[ident]["partial_stock_profiles_exact"] = all(
                trace[k] == current[k]
                for k in (
                    "profiles",
                    "generated_profiles_sha256",
                    "rank_order_sha256",
                    "confidence_sha256",
                )
            )
        for source, row in zip(("candidate", "fresh", "archived"), row_set, strict=True):
            tracked.append((source, row))
            for arm in ARMS:
                scores.append(
                    dict(
                        id=ident,
                        source=source,
                        method=row["method"],
                        arm=arm,
                        result=row["result"]["status"],
                        error_km=distance_km(
                            row["result"]["arms"][arm]["latlon"], refs[ident]["truth"]
                        ),
                        conditional_rms_hz=row["result"]["metrics"].get(
                            f"{arm}_conditional_rms_hz"
                        ),
                    )
                )
    save_json(report / "plan.json", plan)
    save_json(report / "source-lock.json", plan["source"])
    save_json(report / "comparison.json", result)
    save_json(report / "stage-allocation.json", resources)
    csv_file(report / "scores.csv", scores)
    for name, source in zip(FILES, ("candidate", "fresh", "archived"), strict=True):
        _write_predictions(report / name, [row for tag, row in tracked if tag == source])
    files = {
        name: digest(report / name)
        for name in (
            *FILES,
            "plan.json",
            "source-lock.json",
            "comparison.json",
            "stage-allocation.json",
            "scores.csv",
        )
    }
    charts = []
    for ident in result:
        archived = ident == trial.DS29
        group = "ordinary-ds29" if archived else "ordinary-ds26"
        lock = f"{group}-figure-lock.json"
        keys = ("one", "stock", "all_visits")
        roles = (*trial.MODES, trial.MODES[1] if archived else tiled["method"])
        labels = (
            "Sampled prior widths",
            "Fresh composed stock",
            "Archived composed stock" if archived else "Archived tiled-salvage stock",
        )
        series = [
            dict(
                key=k,
                value=m,
                label=label,
                file=name,
                where=dict(id=ident),
                native_authority="ordinary",
                **({"match": INPUTS} if k != "one" else {}),
            )
            for k, m, label, name in zip(keys, roles, labels, FILES, strict=True)
        ]
        save_json(report / lock, dict(cases=[ident], files=files))
        spec = dict(
            id=f"{trial.fast.METHOD}-{group}",
            method=trial.fast.METHOD,
            scope="roof",
            title=f"Family-confidence memory on {ident}",
            cases=[ident],
            seal=lock,
            caption="Fresh composed pairs share ordinary native detections. "
            "The original four v5 references use capture-era factors.",
            provenance=["stage-allocation.json", "comparison.json"],
            series=series,
        )
        figures._chart(report, spec)
        charts.append(spec)
    save_json(report / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", default=trial.REPORT, type=Path)
    args = parser.parse_args()
    publish(args.work, args.report)
