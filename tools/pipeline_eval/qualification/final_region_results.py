"""Score publication from sealed roof and offered-region compact endpoints."""

import argparse
import gzip
import json
import tarfile
from collections import defaultdict
from pathlib import Path
from time import perf_counter_ns

from .. import figure_books, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds, validate_result
from ..variants import compact_tile_interior, final_region
from . import final_region_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .sequential_fix_results import roof_references, sealed
from .sequential_fix_timing import service_metrics

BASELINE = trial.sequential.SCREEN / "factors/full-comparison"
SEQUENTIAL = trial.sequential.REPORT
POSITIONS = "positions.jsonl.gz"
PROSPECTIVE_LOCK = "prospective-prediction-lock.json"
MODES = ("stock", "guarded")
TILES = ("native_sha256", "catalog_sha256", "tile")
CONDITIONS = {
    "original": "Original roof offer",
    "shifted-containing": "Containing offer, 15 km east",
    "disjoint": "Disjoint offer, 30 km east",
    "near-containing": "Near face, site inside",
    "near-omission": "Near face, site outside",
    "clear-omission": "Disjoint offer, site outside",
}


def first_numerical_failures(report):
    path = report / "preflight-attempts.tar.gz"
    rows = {}
    if path.is_file():
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.name.endswith("/prediction.json"):
                    continue
                result = json.load(archive.extractfile(member))
                log = member.name.removesuffix("prediction.json") + "service.log"
                raw = archive.extractfile(log).read()
                status = result["result"]["status"]
                if status == "timed_out" or b"orbit phase interpolation never extrapolates" in raw:
                    rows[result["id"], result["tile"]["id"]] = result
    return rows


def compact_rows(report):
    lock = whole_iq.read(report / PROSPECTIVE_LOCK)
    for name, digest in lock["files"].items():
        whole_iq.checked(report / name, digest)
    plan = whole_iq.read(report / "prospective-source-lock.json")
    expected = {(row["id"], row["offer"], row["cpu"]) for row in plan["assignments"]}
    rows = list(
        map(json.loads, gzip.decompress((report / trial.ATTEMPTS).read_bytes()).splitlines())
    )
    if len(rows) != lock["attempts"] or {(r["id"], r["offer"], r["cpu"]) for r in rows} != expected:
        raise ValueError("first-attempt ledger does not match the complete prospective plan")
    skies = defaultdict(set)
    prior = first_numerical_failures(report)
    primary = []
    for row in rows:
        key = row["id"], row["offer"]
        if key in prior:
            repeat = row["result"]["status"]
            row = dict(prior.pop(key), offer=row["offer"], corrected_harness_repeat_status=repeat)
        primary.append(row)
        spec = plan["cases"][row["id"]]
        tile = next(t for t in spec["offers"] if t["id"] == row["offer"])
        if (
            row["checkpoint"] != "full"
            or row["tile"] != tile
            or {row["input_native_sha256"], row["recorded_native_sha256"]}
            != {spec["spec"]["native_sha256"]}
            or row["track_config_sha256"] != spec["spec"]["config_sha256"]
            or any(row[k] != spec["spec"][k] for k in ("catalog_sha256", "original_request_sha256"))
        ):
            raise ValueError("prospective fit differs from its sealed input")
        if row["result"]["status"] == "ok":
            sky = row["result"]["metrics"]["causal_audit"]["selected_tle_sha256"]
            skies[row["id"]].add(sky)
        resources = service_metrics(row)
        if (
            resources["memory_peak_mib"] is None
            or resources["memory_peak_mib"] > plan["memory_bytes"] / 1024**2
            or resources["swap_peak_bytes"] != plan["swap_max_bytes"]
        ):
            raise ValueError("prospective attempt lacks the registered service envelope")
    if prior:
        raise ValueError("a first numerical attempt has no matching registered offer")
    if any(len(values) > 1 for values in skies.values()):
        raise ValueError("changing the fitted tile changed the fixed causal sky screen")
    return primary


def roof_rows():
    name = "v5_secant_fit.jsonl.gz"
    lock = whole_iq.read(BASELINE / "roof-lock.json")
    path = whole_iq.checked(BASELINE / name, lock["files"][name])
    rows = list(map(json.loads, gzip.decompress(path.read_bytes()).splitlines()))
    if len(rows) != 135 or {r["id"] for r in rows} != set(lock["cases"]):
        raise ValueError("the genuine compact roof ledger must include all 135 recordings")
    return rows


def selected(row, earlier=None, released=False):
    if earlier is None:
        stock = row
        start = perf_counter_ns()
        guarded_result = final_region.publish(row["result"], row["tile"], enabled=True)
        elapsed = perf_counter_ns() - start
        guarded = dict(row, result=guarded_result)
    else:
        stock = final_region.select(earlier, row, released=released)
        start = perf_counter_ns()
        guarded = final_region.select(earlier, row, released=released, enabled=True)
        elapsed = perf_counter_ns() - start
    a, b = stock["result"], guarded["result"]
    validate_result(b)
    if a["status"] != "ok" and a != b:
        raise ValueError("the publication policy replaced an earlier withholding or failure")
    if (
        a is not b
        and {k: v for k, v in b["metrics"].items() if k != "exact_tile_margin_km"} != (a["metrics"])
    ):
        raise ValueError("the publication policy changed numeric fit metrics")
    for arm, endpoint in a.get("arms", {}).items():
        other = b["arms"][arm]
        if endpoint.get("rf_rms_hz") != other.get("rf_rms_hz") or (
            endpoint["latlon"] is not None
            and endpoint["latlon"] not in (other["latlon"], other.get("forced_latlon"))
        ):
            raise ValueError("the publication policy changed the selected endpoint or its RF fit")
    return stock, guarded, elapsed


def cases(report):
    roof, fresh = roof_rows(), compact_rows(report)
    refs = roof_references({row["id"] for row in (*roof, *fresh)})
    for row in roof:
        tile = dict(row["tile"], width_km=25.0)
        yield "roof", "original", refs[row["id"]], selected(row | {"tile": tile})
    for folder, offer, condition in (
        (SEQUENTIAL, "east-15-km", "shifted-containing"),
        (SEQUENTIAL / "omitted", "east-30-km", "disjoint"),
    ):
        _, groups, decisions = sealed(folder)
        for (ident, offered, _), (_, earlier, full) in groups.items():
            if offered == offer:
                yield (
                    "released",
                    condition,
                    refs[ident],
                    selected(full, earlier, decisions[(ident, offer)]["released"]),
                )
    for row in fresh:
        ref = refs[row["id"]]
        margin = compact_tile_interior.margin(ref["truth"], row["tile"])
        condition = (
            "near-containing"
            if margin >= 0
            else "near-omission"
            if margin >= -5
            else "clear-omission"
        )
        yield "prospective", condition, ref, selected(row)


def arm_score(ident, panel, condition, mode, row, margin, reference, arm):
    result = row["result"]
    endpoint = result.get("arms", {}).get(arm, {})
    truth = reference["truth"]
    geographic = distance_km(endpoint.get("latlon"), truth)
    selected_point = endpoint.get("latlon") or endpoint.get("forced_latlon")
    record = dict(
        id=ident,
        recording=row["id"],
        panel=panel,
        condition=condition,
        mode=mode,
        arm=arm,
        status=result["status"],
        reason=result.get("reason"),
        truth_tile_margin_km=margin,
        selected_tile_margin_km=compact_tile_interior.margin(selected_point, row["tile"])
        if selected_point is not None
        else None,
        geographic_error_km=geographic,
        forced_error_km=distance_km(endpoint.get("forced_latlon"), truth),
        selected_error_km=distance_km(selected_point, truth),
        false_publication=margin < 0 and geographic is not None,
        rf_rms_hz=endpoint.get("rf_rms_hz"),
        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
    )
    for role in ROLES:
        original = reference["reference"][role][arm]
        key = role.replace("-", "_")
        error = original["error_km"]
        record.update(
            {
                f"{key}_reference_status": original["status"],
                f"{key}_reference_km": error,
                f"{key}_within_5pct": geographic is not None and geographic <= 1.05 * error
                if error is not None
                else None,
                f"{key}_within_10pct": geographic is not None and geographic <= 1.10 * error
                if error is not None
                else None,
            }
        )
    return record


def summarize(scores):
    cohorts = defaultdict(list)
    for row in scores:
        cohorts[row["panel"], row["condition"], row["mode"], row["arm"]].append(row)
    return [
        dict(
            panel=panel,
            condition=condition,
            mode=mode,
            arm=arm,
            attempted=len(group),
            published=sum(row["geographic_error_km"] is not None for row in group),
            withheld=sum(row["status"] == "withheld" for row in group),
            failed=sum(row["status"] not in ("ok", "withheld") for row in group),
            false_publications=sum(row["false_publication"] for row in group),
            expected_coverage=sum(row["truth_tile_margin_km"] >= 0 for row in group),
            within_km=thresholds([row["geographic_error_km"] for row in group]),
            geographic_error_km=distribution(row["geographic_error_km"] for row in group),
            forced_error_km=distribution(row["forced_error_km"] for row in group),
            rf_rms_hz=distribution(row["rf_rms_hz"] for row in group),
            frequency_score=distribution(row["frequency_score"] for row in group),
            baseline_available=sum(row["baseline_reference_km"] is not None for row in group),
            baseline_within_5pct=sum(row["baseline_within_5pct"] is True for row in group),
            baseline_within_10pct=sum(row["baseline_within_10pct"] is True for row in group),
        )
        for (panel, condition, mode, arm), group in sorted(cohorts.items())
    ]


def ablation(scores):
    matches = defaultdict(dict)
    fields = ("geographic_error_km", "selected_error_km", "rf_rms_hz", "frequency_score")
    for row in scores:
        matches[row["panel"], row["condition"], row["mode"], row["id"]][row["arm"]] = row
    rows = []
    for (panel, condition, mode, ident), paired in matches.items():
        delta = {}
        for field in fields:
            zero, fitted = (paired[arm][field] for arm in ARMS)
            delta[field] = fitted - zero if zero is not None and fitted is not None else None
        rows.append(dict(panel=panel, condition=condition, mode=mode, id=ident, **delta))
    return rows


def descriptors(report, queries, ids):
    provenance = ["source-authority.json", "scores.csv", "summary.json", PROSPECTIVE_LOCK]
    titles = {
        "roof": "Terminal tile guard on the 135 original roof offers",
        "released": "Terminal tile guard on the four released offer controls",
        "prospective": "Terminal tile guard on 18 prospective recorded roof offers",
    }
    charts = []
    for panel, title in titles.items():
        roof = panel == "roof"
        seal = f"{panel}-figure-lock.json"
        files = [POSITIONS, *provenance]
        extras = {}
        if not roof:
            filename = f"{panel}-queries.json"
            save_json(report / filename, dict(queries=queries[panel]))
            present = {q["condition"] for q in queries[panel]}
            extras = dict(
                queries=filename,
                condition_labels={k: v for k, v in CONDITIONS.items() if k in present},
            )
            files.append(filename)
        save_json(report / seal, dict(cases=ids[panel], files={f: _sha(report / f) for f in files}))
        charts.append(
            dict(
                id=f"final-region-{panel}",
                method=f"final_region_{panel}",
                scope="roof" if roof else "transfer",
                cases="sealed",
                title=title,
                caption=(
                    "Both modes use identical recorded original GLRT and the same numerical fits. "
                    "The published pair requires both fits to clear the nearest 25 km tile face "
                    "by more than 20 m. All recordings come from one measured roof."
                ),
                seal=seal,
                provenance=provenance,
                series=[
                    dict(
                        key="one" if roof else "candidate",
                        file=POSITIONS,
                        value=f"{panel}_guarded",
                        label="20 m paired guard",
                        forced_label="Withheld fit, diagnostic only",
                    ),
                    dict(
                        key="stock",
                        file=POSITIONS,
                        value=f"{panel}_stock",
                        label="Guard off",
                        match=list(TILES),
                    ),
                ],
                **extras,
            )
        )
    save_json(report / "figures.json", dict(version=2, charts=charts))


def execute(report):
    positions, scores, timing = [], [], []
    queries, ids = defaultdict(list), defaultdict(list)
    for panel, condition, ref, (stock, guarded, guard_ns) in cases(report):
        ident = stock["id"] if panel == "roof" else f"{stock['id']}-{stock['tile']['id']}"
        ids[panel].append(ident)
        bindings = dict(
            native_sha256=stock.get("native_sha256") or stock["recorded_native_sha256"],
            catalog_sha256=stock["catalog_sha256"],
            tile=stock["tile"],
        )
        margin = compact_tile_interior.margin(ref["truth"], stock["tile"])
        if (margin >= 0) != (condition in ("original", "shifted-containing", "near-containing")):
            raise ValueError(f"retrospective condition differs from surveyed geometry for {ident}")
        if panel != "roof":
            queries[panel].append(
                dict(
                    id=ident,
                    condition=condition,
                    recording=stock["id"],
                    truth=ref["truth"],
                    bindings=bindings,
                )
            )
        receipt = service_metrics(stock) if "service" in stock else {}
        timing.append(
            dict(
                id=ident,
                panel=panel,
                condition=condition,
                selected_branch=stock.get("checkpoint", "full"),
                guard_wall_ns=guard_ns,
                raw_status=stock["result"]["status"],
                guarded_status=guarded["result"]["status"],
                corrected_harness_repeat_status=stock.get("corrected_harness_repeat_status"),
                **receipt,
            )
        )
        for mode, row in zip(MODES, (stock, guarded), strict=True):
            positions.append(
                dict(id=ident, method=f"{panel}_{mode}", result=row["result"], **bindings)
            )
            scores.extend(
                arm_score(ident, panel, condition, mode, row, margin, ref, arm) for arm in ARMS
            )
    csv_file(report / "scores.csv", scores)
    fields = dict.fromkeys(k for row in timing for k in row)
    csv_file(report / "guard-timing.csv", [{k: row.get(k) for k in fields} for row in timing])
    csv_file(report / "coefficient-ablation.csv", ablation(scores))
    write(
        report / POSITIONS, gzip.compress(b"".join(encoded(r) + b"\n" for r in positions), mtime=0)
    )
    save_json(
        report / "summary.json",
        dict(
            cohorts=summarize(scores),
            guard_wall_ns={
                panel: distribution(r["guard_wall_ns"] for r in timing if r["panel"] == panel)
                for panel in ids
            },
        ),
    )
    authorities = (
        BASELINE / "roof-lock.json",
        SEQUENTIAL / "prediction-lock.json",
        SEQUENTIAL / "omitted/prediction-lock.json",
        Path(final_region.__file__),
        Path(compact_tile_interior.__file__),
        Path(trial.sequential.WORKER),
        Path(__file__),
    )
    archival = (
        "historical-scorer-sources.tar.gz",
        "historical-handoff-sources.tar.gz",
        "preflight-attempts.tar.gz",
        "preflight-source.tar.gz",
        "preflight-source-lock.json",
        "prospective-service-logs.tar.gz",
    )
    save_json(
        report / "source-authority.json",
        dict(
            files={str(p.relative_to(trial.ROOT)): _sha(p) for p in authorities},
            archived_files={
                name: _sha(report / name) for name in archival if (report / name).exists()
            },
        ),
    )
    descriptors(report, queries, ids)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=trial.REPORT)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    execute(args.report)
    if args.render:
        figure_books.generate(args.report / "charts", ARMS, panel="screening", evidence=args.report)
    names = (
        "figures.json",
        "source-authority.json",
        "summary.json",
        "scores.csv",
        "guard-timing.csv",
        "coefficient-ablation.csv",
        POSITIONS,
        PROSPECTIVE_LOCK,
    )
    if args.render:
        names = (*names, "charts/manifest.json")
    save_json(
        args.report / "score-lock.json", dict(files={f: _sha(args.report / f) for f in names})
    )


if __name__ == "__main__":
    main()
