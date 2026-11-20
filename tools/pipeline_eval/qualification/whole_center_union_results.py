"""Seal full matched raw measurements and score independent fifth-center position results."""

import argparse
import gzip
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distribution
from . import diagnostic_whole_results as comparison
from . import frontier_whole_replay_results as traces
from . import screening_figures
from . import whole_band_results as measured
from . import whole_center_union as trial
from . import whole_center_union_candidate as candidate
from .exact_wide_iq_results import timing_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

POSITION = "positions.jsonl.gz"
VISITS = "visits.jsonl.gz"
PROBES = "probe-audit.json"
METHOD = {"control": trial.BASELINE, "candidate": trial.METHOD}


def check_union_lanes(extra, hints):
    if len(extra) != 2 or len(hints) != 2:
        raise ValueError("fifth-center telemetry requires both receivers")
    counts = Counter()
    for lane, hint in zip(extra, hints, strict=True):
        stock, selected = lane["ordinary"], lane["selected"]
        if len(stock) > 4 or selected[: len(stock)] != stock or len(selected) > len(stock) + 1:
            raise ValueError("the fifth-center lane displaced a stock proposal")
        added = selected[len(stock) :]
        if added and (added != [hint] or hint in stock):
            raise ValueError("the fifth-center lane did not append only its exact distinct hint")
        original_epochs = {
            epoch
            for center in stock
            for epoch in range(center - 1, center + 2)
            if 0 <= epoch < 13_333
        }
        hint_epochs = (
            {epoch for epoch in range(hint - 1, hint + 2) if 0 <= epoch < 13_333}
            if hint is not None
            else set()
        )
        if (
            lane["added_epochs"] != len(hint_epochs - original_epochs)
            or lane["active_epochs"] != len(hint_epochs | original_epochs)
            or bool(added) != bool(lane["added_epochs"])
        ):
            raise ValueError(
                "native fifth-center trace does not match the deduplicated epoch union"
            )
        peaks = {tuple(key) for key in lane["stock_peak_keys"]}
        if (
            len(peaks) != lane["stock_peaks"]
            or any(
                epoch not in original_epochs or not 0 <= cfo_bin < 21 for epoch, cfo_bin in peaks
            )
            or not 0 <= lane["retained_stock"] <= lane["stock_peaks"]
            or not 0 <= lane["retained_extra"] <= lane["extra_peaks"]
            or lane["retained_stock"] + lane["retained_extra"] > 8
        ):
            raise ValueError("native coarse peak inventory or shared top-eight trace is invalid")
        counts["receiver_probes"] += 1
        counts["stock_centers_retained"] += len(stock)
        counts["with_hint"] += hint is not None
        counts["actual_fifth_centers"] += bool(added)
        counts["stock_only_or_deduplicated"] += not added
        for key in (
            "added_epochs",
            "stock_peaks",
            "extra_peaks",
            "retained_stock",
            "retained_extra",
        ):
            counts[key] += lane[key]
    return counts


def union_telemetry(rows):
    total = Counter()
    for visit in rows:
        if visit["status"] == "processed":
            telemetry = visit["differential"]
            total.update(check_union_lanes(telemetry["center_union_lanes"], telemetry["hints"]))
    return dict(total)


def unavailable(work, out, reason):
    lock = trial.source(work)
    if not reason.strip() or (out / candidate.PIN).exists():
        raise ValueError("an activated whole-IQ candidate cannot be marked unavailable")
    for ident in lock["cases"]:
        if (
            not (work / ident / "control/service.json").exists()
            and not (work / ident / "control-failure.json").exists()
        ):
            raise ValueError("stock controls must be terminal before the unavailable seal")
    save_json(
        out / "candidate-unavailable.json",
        dict(
            reason=reason,
            cases=list(lock["cases"]),
            stock_source_sha256=_sha(out / "source-lock.json"),
        ),
    )


def missing(row, authority):
    borrowed = {
        k: row[k]
        for k in (
            "id",
            "tile",
            "mode",
            "catalog_sha256",
            "original_request_sha256",
            "cohort",
            "paired_capture_sha256",
        )
    }
    return dict(
        borrowed,
        method=trial.METHOD,
        result=dict(
            status="unavailable",
            reason=authority["reason"],
            boundary="Full saved IQ through position",
            metrics={},
            arms={arm: {"latlon": None} for arm in ARMS},
        ),
    )


def seal(work, out):
    if (out / "prediction-lock.json").exists():
        raise FileExistsError("the terminal predictions are already sealed")
    common = trial.source(work)
    no_candidate = out / "candidate-unavailable.json"
    if no_candidate.exists():
        if (out / candidate.PIN).exists():
            raise ValueError("the frozen activation and unavailability are incompatible")
        unavailable_authority = whole_iq.read(no_candidate)
        if unavailable_authority["stock_source_sha256"] != _sha(out / "source-lock.json"):
            raise ValueError("the unavailable candidate belongs to another source")
        files = [no_candidate.name]
    else:
        _, active = candidate.candidate_lock(work)
        common["detectors"]["candidate"] = active["assets"]["candidate"]
        unavailable_authority = None
        files = [candidate.PIN, candidate.INITIAL_PIN, candidate.GATE]
    rows, visit_rows, resources, audits = [], [], {}, {}
    for ident, scheduled in common["cases"].items():
        resources[ident], per_role, per_visit, part = {}, {}, {}, {}
        for role, method in METHOD.items():
            if role == "candidate" and unavailable_authority:
                row = missing(per_role["control"], unavailable_authority)
                receipt, native = {"service": {}}, None
            else:
                row, receipt, native = measured.attempt(work, ident, role, common, method=method)
            per_role[role] = row
            resources[ident][role] = receipt
            rows.append(row)
            folder = work / ident / role
            if native is not None:
                per_visit[role], part[role] = comparison.trace_bundle(ident, role, folder, receipt)
                name = f"native/{role}/{ident}.json.gz"
                write(out / name, gzip.compress(native.read_bytes(), mtime=0))
                files.append(name)
            log = folder / "service.log"
            if log.is_file():
                whole_iq.checked(log, receipt["service"]["log_sha256"])
                name = f"{ident}-{role}.service.log"
                write(out / name, log.read_bytes())
                files.append(name)
        if any(
            per_role["control"][key] != per_role["candidate"][key]
            for key in (*comparison.PHYSICAL_KEYS, "mode")
        ):
            raise ValueError("the pair changed the original physical request")
        audit = audits[ident] = {"raw_complete": list(part)}
        if "candidate" in part:
            folder = work / ident / "candidate"
            audit["native_scout"] = traces.scout_trace(folder, part["candidate"])
            audit["union_admissions"] = union_telemetry(part["candidate"])
        if set(part) == set(METHOD):
            comparison.matched_physical(
                resources[ident]["control"],
                resources[ident]["candidate"],
                scheduled,
            )
            audit.update(
                comparison.gate_stability(
                    per_visit["control"],
                    per_visit["candidate"],
                    part["control"],
                    part["candidate"],
                )
            )
        visit_rows.extend(visit for branch in part.values() for visit in branch)
    traces.protect_resources(resources)
    pack(out / POSITION, rows)
    pack(out / VISITS, visit_rows)
    save_json(out / PROBES, audits)
    save_json(out / "resources.json", resources)
    files.extend(
        (
            "source-lock.json",
            "selection.json",
            "PROTOCOL.md",
            POSITION,
            VISITS,
            PROBES,
            "resources.json",
        )
    )
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=list(common["cases"]),
            files={name: _sha(out / name) for name in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def paired_scores(scores):
    keys = ("error_km", "conditional_rms_hz", "frequency_score")
    pairs = {}
    for score in scores:
        pairs.setdefault((score["id"], score["method"]), {})[score["arm"]] = score
    deltas = []
    for (ident, method), arms in pairs.items():
        deltas.append(
            dict(
                id=ident,
                method=method,
                **{
                    f"fitted_minus_zero_{key}": arms["fitted_c"][key] - arms["c0"][key]
                    if all(arms[arm][key] is not None for arm in ARMS)
                    else None
                    for key in keys
                },
            )
        )
    summary = {}
    for role, method in METHOD.items():
        summary[role] = {}
        for arm in ARMS:
            rows = [r for r in scores if r["method"] == method and r["arm"] == arm]
            summary[role][arm] = dict(
                attempted=len(rows),
                published=sum(r["error_km"] is not None for r in rows),
                within_5pct=sum(r["within_5pct"] for r in rows),
                within_10pct=sum(r["within_10pct"] for r in rows),
                errors_km=distribution([r["error_km"] for r in rows]),
            )
    return deltas, summary


def score(out):
    lock = whole_iq.read(out / "prediction-lock.json")
    for name, digest in lock["files"].items():
        whole_iq.checked(out / name, digest)
    rows = rows_from(out / POSITION)
    _, references = held_references(None, lock["cases"])
    scores = comparison.geographic(rows, {r["id"]: r for r in references})
    csv_file(out / "scores.csv", scores)
    contrasts, summary = paired_scores(scores)
    csv_file(out / "calibration.csv", contrasts)
    save_json(out / "summary.json", summary)
    resources = whole_iq.read(out / "resources.json")
    visits = [r for r in rows_from(out / VISITS) if r["status"] == "processed"]
    save_json(out / "visit-coverage.json", comparison.visit_coverage(visits))
    timing = timing_rows(resources, visits)
    for row in timing:
        item = resources[row["id"]][row["role"]]
        row["wall_to_failure_s"] = item.get("wall_to_failure_s")
        row["cpu_to_failure_s"] = item.get("cpu_to_failure_s")
        row["service_wall_s"] = item["service"].get("service_wall_s", row["service_wall_s"])
        data = [
            r["differential"]
            for r in visits
            if r["id"] == row["id"] and r["role"] == row["role"] and "differential" in r
        ]
        row["scout_cpu_s"] = sum(x["scout_cpu_ns"] for x in data) / 1e9 if data else None
    csv_file(out / "deadlines.csv", timing)
    traces.draw_resources(out, lock["cases"], timing, visits)
    files = [
        "prediction-lock.json",
        "scores.csv",
        "calibration.csv",
        "summary.json",
        "deadlines.csv",
        PROBES,
        "visit-coverage.json",
    ]
    panels = [("all", lock["cases"]), *((ident.lower(), [ident]) for ident in lock["cases"])]
    charts = []
    for key, cases in panels:
        file = POSITION if key == "all" else f"{key}-positions.jsonl.gz"
        if key != "all":
            pack(out / file, [r for r in rows if r["id"] in cases])
        figure_lock = f"{key}-figure-lock.json"
        save_json(
            out / figure_lock,
            dict(cases=cases, files={name: _sha(out / name) for name in (file, *files)}),
        )
        title = (
            "Keep four stock starts and add one differential start"
            if key == "all"
            else f"Fifth-center whole-IQ benchmark on {cases[0]}"
        )
        charts.append(
            dict(
                id=f"whole-center-union-{key}",
                method=trial.METHOD,
                scope="roof",
                cases="sealed",
                title=title,
                caption=(
                    "Manifest-selected complete saved IQ, original phase release and 25 km region. "
                    "Four original v5 options use capture-era inputs. "
                    "Both recordings come from one roof."
                ),
                seal=figure_lock,
                provenance=files,
                series=[
                    dict(
                        key="one",
                        value=trial.METHOD,
                        label="Four stock starts + optional fifth",
                        file=file,
                        native_field="paired_capture_sha256",
                    ),
                    dict(
                        key="stock",
                        value=trial.BASELINE,
                        label="Stock four starts",
                        file=file,
                        native_field="paired_capture_sha256",
                        match=["original_request_sha256", "catalog_sha256", "tile", "mode"],
                    ),
                ],
            )
        )
    save_json(out / "figures.json", dict(version=1, charts=charts))
    screening_figures.generate(out / "charts", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score", "unavailable"))
    parser.add_argument("--work", default=trial.WORK, type=local_output)
    parser.add_argument("--out", default=trial.REPORT, type=local_output)
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.work, args.out)
    elif args.action == "score":
        score(args.out)
    elif args.reason:
        unavailable(args.work, args.out, args.reason)
    else:
        parser.error("--reason is required to record candidate unavailability")
