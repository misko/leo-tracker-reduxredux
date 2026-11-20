"""Authenticate standalone workers and score the frozen stock-first archive replay."""

import argparse
import gzip
import json
import math
from collections import Counter
from pathlib import Path

from .. import corpus
from ..__main__ import (
    encoded,
    implementation_digest,
    local_output,
    read_predictions,
    save_json,
)
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds
from . import causal_orbit_fit_trial as integrated
from . import deadline_roof_model as model
from . import failed_only_benchmark as route
from . import full_receiver_comparison as auth
from .orbit_domain_results import BINDING_FIELDS
from .phase_support_results import pack
from .prefix_figures import csv_file

REPORT = auth.SCREEN / "integration/failed-only"
REPLAY = "v5_failed_only_archive"
POSITIONS = "positions.jsonl.gz"
STOCK = "compact-positions.jsonl.gz"
REPAIRS = "measured-repairs.jsonl.gz"
COHORTS = ("all159", "common127", "excluded32")


def observed_wall(row):
    if row["result"]["status"] == "unavailable" and not row.get("attempted"):
        return None
    measured = row["result"]["metrics"].get("candidate_s")
    if row["result"]["status"] == "timed_out" or measured is None:
        measured = row.get("worker_wall_s")
    if measured is None or not math.isfinite(measured) or measured <= 0:
        raise ValueError(f"{row['id']} has no actual worker interval")
    return measured


def previous_witnesses():
    folder = integrated.prior.REPORT
    file = "diagnostic-traces.jsonl.gz"
    release = auth.seal(folder, "prediction-lock.json", (file, STOCK))
    if release["source_lock_sha256"] != auth.sha(folder / "source-lock.json"):
        raise ValueError("previous-orbit diagnostic changed its source lock")
    with gzip.open(folder / file, "rt") as stream:
        rows = {r["id"]: r for r in map(json.loads, stream)}
    baseline = read_predictions(folder / STOCK)
    for ident, row in rows.items():
        if (
            row["stack"][-1] != dict(call="previous_bank", file="orbit_modes.py", line=44)
            or row["error"] not in ("", None)
            or not row["invalid_previous"]
            or baseline[ident]["result"]["reason"] != "AssertionError"
        ):
            raise ValueError(f"{ident} lacks the original previous-orbit failure witness")
    return baseline, rows


def authenticated():
    items, common, compact, _, audit = model.auth_archives()
    refs = model.verify_original_refs(items, common, audit)
    _, frozen = corpus._selection("ds26-all159")
    release = auth.seal(integrated.REPORT, "prediction-lock.json", (POSITIONS, STOCK))
    source_path = integrated.REPORT / "source-lock.json"
    source = auth.read(source_path)
    if release["source_lock_sha256"] != auth.sha(source_path) or encoded(source) != encoded(
        integrated.source_lock()
    ):
        raise ValueError(
            "integrated measured guard worker no longer matches its scientific sources"
        )
    measured = read_predictions(integrated.REPORT / POSITIONS)
    matched = read_predictions(integrated.REPORT / STOCK)
    auth.roster_matches(release["cases"], measured, "integrated guard")
    auth.roster_matches(measured, matched, "integrated matched compact")
    older, witness = previous_witnesses()
    for ident, stock in compact.items():
        item = items[ident]
        if item.get("unavailable"):
            continue
        auth.require_fields(stock, dict(frozen_request_sha256=item["request"]["sha256"]))
        if ident in measured:
            row = measured[ident]
            binding = {key: stock[key] for key in BINDING_FIELDS}
            auth.require_fields(
                row,
                dict(
                    binding,
                    method=route.REPAIR,
                    attempted=True,
                    source_lock_sha256=release["source_lock_sha256"],
                ),
            )
            auth.require_fields(matched[ident], dict(binding, result=stock["result"]))
            auth.require_fields(source["bindings"][ident], binding)
            if ident in witness:
                auth.require_fields(older[ident], dict(binding, result=stock["result"]))
    masks = {}
    for ident, stock in compact.items():
        cause = route.retry_cause(
            stock, bool(stock.get("input_sha256")), previous_verified=ident in witness
        )
        masks[ident] = cause
    selected = {ident for ident, cause in masks.items() if cause}
    if len(selected) != 8 or not selected <= measured.keys():
        raise ValueError("eligible exceptions do not match the measured eight repairs")
    return items, refs, common, compact, measured, masks, frozen


def seal_archive(output):
    items, refs, common, compact, measured, masks, frozen = authenticated()
    settings = dict(
        cases=list(compact),
        cohorts=dict(common127=list(common), excluded32=[k for k in compact if k not in common]),
        mask=masks,
        corpus=frozen,
        cap_s=route.CAP_S,
        routing_sources={
            p.name: auth.sha(p)
            for p in (
                Path(route.__file__),
                Path(__file__),
                REPORT / "PROTOCOL.md",
            )
        },
        method_sha256=implementation_digest(route.METHOD, Path(route.__file__)),
        independent_archives={
            str(p.relative_to(auth.SCREEN)): auth.sha(p)
            for p in (
                model.COMPARISON / "all159-figure-lock.json",
                model.NATIVE_REPORT / "all159-figure-lock.json",
                integrated.REPORT / "source-lock.json",
                integrated.REPORT / "prediction-lock.json",
                integrated.prior.REPORT / "prediction-lock.json",
            )
        },
        track_config_sha256={
            k: item.get("track_config", {}).get("sha256") for k, item in items.items()
        },
    )
    output.mkdir(parents=True, exist_ok=True)
    save_json(output / "source-lock.json", settings)
    save_json(output / "original-four-scores.json", refs)
    rows = []
    for ident, stock in compact.items():
        cause = masks[ident]
        repair = measured[ident] if cause else None
        stock_wall, repair_wall = observed_wall(stock), observed_wall(repair) if repair else None
        total = None if stock_wall is None else stock_wall + (repair_wall or 0)
        rows.append(
            dict(
                stock,
                method=REPLAY,
                result=repair["result"] if repair else stock["result"],
                source="offline_serial_replay",
                routing=dict(
                    selected="repair" if repair else "stock" if stock_wall is not None else "none",
                    cause=cause,
                    stock_status=stock["result"]["status"],
                    stock_raw_status=stock.get("reported_worker_status", stock["result"]["status"]),
                    stock_reason=stock["result"].get("reason"),
                    stock_wall_s=stock_wall,
                    repair_wall_s=repair_wall,
                    serial_estimate_s=total,
                ),
            )
        )
    pack(output / POSITIONS, rows)
    pack(output / STOCK, compact.values())
    pack(output / REPAIRS, [measured[ident] for ident, cause in masks.items() if cause])
    files = (POSITIONS, STOCK, REPAIRS, "source-lock.json", "original-four-scores.json")
    auth_file = {name: auth.sha(output / name) for name in files}
    save_json(output / "prediction-lock.json", dict(cases=list(compact), files=auth_file))


def rf(result, arm):
    return result["arms"][arm].get("rf_rms_hz", result["metrics"].get(f"{arm}_conditional_rms_hz"))


def score_rows(refs, groups, stock, routed):
    for ident, row in routed.items():
        prior = stock[ident]
        ref = refs[ident]
        for arm in ARMS:
            scored = {}
            for name, item in (("stock", prior), ("router", row)):
                result = item["result"]
                point = result["arms"][arm]
                scored |= {
                    f"{name}_status": result["status"],
                    f"{name}_error_km": distance_km(point["latlon"], ref["truth"]),
                    f"{name}_conditional_rms_hz": rf(result, arm),
                }
            roles = {
                f"{role}_{key}": ref["reference"][role][arm].get(key)
                for role in ROLES
                for key in ("status", "error_km", "rf_rms_hz")
            }
            yield (
                dict(
                    id=ident,
                    arm=arm,
                    cohort="common127" if ident in groups["common127"] else "excluded32",
                )
                | scored
                | roles
                | row["routing"]
            )


def summarize(rows):
    output = []
    for cohort in COHORTS:
        for arm in ARMS:
            group = [r for r in rows if r["arm"] == arm and cohort in ("all159", r["cohort"])]
            kinds = {}
            for name in ("stock", "router", *ROLES):
                e = f"{name}_error_km"
                matched = [
                    r for r in group if r[e] is not None and r["baseline_error_km"] is not None
                ]
                kinds[name] = dict(
                    statuses=Counter(r[f"{name}_status"] for r in group),
                    error_km=distribution(r[e] for r in group),
                    within_km=thresholds([r[e] for r in group]),
                    paired=len(matched),
                    within10pct=sum(r[e] <= 1.10 * r["baseline_error_km"] for r in matched),
                    paired_error_km=distribution(r[e] for r in matched),
                    paired_v5_km=distribution(r["baseline_error_km"] for r in matched),
                    conditional_rms_hz=distribution(
                        r.get(f"{name}_conditional_rms_hz", r.get(f"{name}_rf_rms_hz"))
                        for r in group
                    ),
                )
            output.append(
                dict(
                    cohort=cohort,
                    arm=arm,
                    offered=len(group),
                    methods=kinds,
                    serial_estimate_s=distribution(r["serial_estimate_s"] for r in group),
                    stock_wall_s=distribution(r["stock_wall_s"] for r in group),
                    repair_wall_s=distribution(r["repair_wall_s"] for r in group),
                    retry_causes=Counter(r["cause"] for r in group if r["cause"]),
                )
            )
    return output


def figures(output, groups, stock, routed):
    charts = []
    for cohort in ("all159", "excluded32"):
        cases = list(stock) if cohort == "all159" else groups[cohort]
        archive, replay = (f"{cohort}-{suffix}.jsonl.gz" for suffix in ("stock", "replay"))
        pack(output / archive, [stock[ident] for ident in cases])
        pack(output / replay, [routed[ident] for ident in cases])
        lock = f"{cohort}-figure-lock.json"
        provenance = ["scores.csv", "summary.json", "prediction-lock.json"]
        save_json(
            output / lock,
            dict(
                cases=cases, files={n: auth.sha(output / n) for n in (archive, replay, *provenance)}
            ),
        )
        charts.append(
            dict(
                id=f"failed-only-{cohort}",
                method=REPLAY,
                scope="roof",
                cases=f"ds26-{cohort}",
                title=f"Stock-first compact v5 exception replay · {cohort}",
                caption=(
                    "Measured standalone compact and repair workers, combined offline under the "
                    "frozen retry rule. All original offers and both calibration arms remain."
                ),
                seal=lock,
                provenance=provenance,
                series=[
                    dict(
                        key="one", label="Stock-first exception replay", file=replay, value=REPLAY
                    ),
                    dict(
                        key="stock",
                        label="Unchanged compact v5",
                        file=archive,
                        value=model.COMPACT,
                        match=list(BINDING_FIELDS),
                    ),
                ],
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=charts))


def score(output):
    authority = auth.seal(
        output,
        "prediction-lock.json",
        (
            POSITIONS,
            STOCK,
            REPAIRS,
            "source-lock.json",
            "original-four-scores.json",
        ),
    )
    lock = auth.read(output / "source-lock.json")
    groups = lock["cohorts"]
    refs = auth.read(output / "original-four-scores.json")
    stock, routed = (read_predictions(output / name) for name in (STOCK, POSITIONS))
    for rows in (refs, stock, routed):
        auth.roster_matches(rows, authority["cases"], "stock-first comparison")
    data = list(score_rows(refs, groups, stock, routed))
    csv_file(output / "scores.csv", data)
    save_json(output / "summary.json", summarize(data))
    save_json(
        output / "score-lock.json",
        dict(
            prediction_lock_sha256=auth.sha(output / "prediction-lock.json"),
            files={name: auth.sha(output / name) for name in ("scores.csv", "summary.json")},
        ),
    )
    figures(output, groups, stock, routed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("seal", "score"))
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    (seal_archive if args.stage == "seal" else score)(local_output(args.out))
