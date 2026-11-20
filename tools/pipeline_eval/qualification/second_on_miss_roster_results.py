"""Publish the sealed compact outcomes, three matched policies, and physical parity."""

import argparse
import gzip
from hashlib import sha256

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution
from . import complete_detector_roster as fixed
from . import one_lane_roster as one
from . import one_lane_roster_results as prior
from . import screening_figures, staggered_benchmark
from . import second_on_miss_roster as trial
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
DIRECT_REPORT = REPORT.with_name("second-on-miss-whole")
DIRECT_METHOD = "second_on_miss_whole"
METHODS = (trial.METHOD, fixed.FOUR, one.METHOD)
ONE_SCORE = "668a28b1d3e3181ed44847e6ca51fcd0aa5452112bef6899284b25bc3808d791"


def verify_worker(work, plan, candidate, stock, single):
    fixed.same_capture(candidate, stock)
    fixed.same_capture(candidate, single)
    ident = candidate["id"]
    result = candidate["result"]
    resource = candidate.get("position_resources") or {}
    if candidate["terminal"] != "not-launched":
        folder = work / ident / trial.METHOD
        if (
            candidate["stock_native_sha256"] != stock["native_sha256"]
            or candidate["one_lane_native_sha256"] != single["native_sha256"]
            or whole_iq.read(folder / "attempt.json") != candidate
        ):
            raise ValueError(f"{ident} changed measured comparators or terminal worker receipt")
        whole_iq.checked(folder / "recording/native.json", candidate["native_sha256"])
        whole_iq.checked(folder / "recording/request.json", candidate["prepared_request_sha256"])
        log = whole_iq.checked(folder / "service.log", candidate["log_sha256"])
        write(REPORT / "logs" / f"{ident}.log.gz", gzip.compress(log.read_bytes(), mtime=0))
    if candidate["terminal"] == "success" and not resource:
        raise ValueError(f"{ident} lost an actual worker resource witness")
    for witness in (resource.get("start"), resource.get("end")):
        if witness and (
            witness["cpus"] != [candidate["cpu"]]
            or witness["memory.max"] != plan["memory_bytes"]
            or witness["memory.swap.max"]
            or witness["memory.swap.current"]
        ):
            raise ValueError(f"{ident} violated its frozen service resources")
    return dict(
        id=ident,
        cpu=candidate["cpu"],
        terminal=candidate["terminal"],
        status=result["status"],
        position_wall_s=resource.get("wall_s"),
        position_cpu_s=resource.get("cpu_s"),
        peak_bytes=resource.get("peak_bytes"),
        supervisor_wall_s=candidate.get("supervisor_wall_s"),
        retained_gated_probes=candidate.get("positive_probes"),
        position_observations=result["metrics"].get("observations"),
        native_detector_wall_s=None,
        native_detector_cpu_s=None,
    )


def scores(rows, refs):
    scored = fixed.scored(rows, refs)
    lookup = {(r["id"], r["arm"], r["method"]): r["error_km"] for r in scored}
    for row in scored:
        error = row["error_km"]
        before = (row["baseline_km"], *(lookup[row["id"], row["arm"], m] for m in METHODS[1:]))
        for label, reference in zip(("original", "stock", "always_single"), before, strict=True):
            delta = 100 * (error / reference - 1) if error is not None and reference else None
            row[f"delta_pct_{label}"] = delta
            row[f"within_symmetric_5pct_{label}"] = delta is not None and abs(delta) <= 5
            row[f"within_symmetric_10pct_{label}"] = delta is not None and abs(delta) <= 10
    return scored


def summarize(data, refs, groups):
    rows = []
    for cohort, ids in groups.items():
        for arm in ARMS:
            incoming = [r for r in data if r["id"] in ids and r["arm"] == arm]
            for method in (*METHODS, *ROLES):
                item = fixed.summary_row(incoming, ids, cohort, arm, method)
                subset = [r for r in incoming if r["method"] == method]
                rms = (
                    [r["rf_rms_hz"] for r in subset]
                    if subset
                    else [refs[ident]["reference"][method][arm].get("rf_rms_hz") for ident in ids]
                )
                r = distribution(rms)
                rows.append(dict(item, rf_n=r["n"], rf_p50_hz=r["p50"], rf_p95_hz=r["p95"]))
    return rows


def figures(rows, groups, new_authority, new_positions):
    charts = []
    for key, title in (
        ("all", "Second stock antenna only after a miss on the complete roof roster"),
        ("hard6", "Second stock antenna after a miss on six earlier difficult recordings"),
        ("new2", "Second stock antenna after a miss on the new lower-edge recordings"),
        ("direct2", "Stored-factor fits on the two direct IQ overlap recordings"),
    ):
        ids = groups[key]
        files = [
            "prediction-lock.json",
            "packet-audit.json",
            "scores.csv",
            "summary.csv",
            "resources.csv",
            "input-reproduction.json",
        ]
        if (REPORT / "direct-iq-parity.json").is_file():
            files.append("direct-iq-parity.json")
        archive = f"{key}-matched-positions.jsonl.gz"
        pack(REPORT / archive, [r for r in rows if r["id"] in ids])
        existing, _ = staggered_benchmark.export_references(
            REPORT, key, ids, new_authority, new_positions
        )
        files.extend(existing.values())
        lock = f"{key}-figure-lock.json"
        save_json(
            REPORT / lock, dict(cases=ids, files={f: _sha(REPORT / f) for f in (archive, *files)})
        )
        series = [
            dict(
                key=k,
                file=archive,
                value=method,
                label=label,
                native_field="paired_capture_sha256",
                **({"match": list(fixed.BINDINGS)} if k != "one" else {}),
            )
            for k, method, label in zip(
                ("one", "stock", "one_native_factors"),
                METHODS,
                (
                    "Second antenna on primary miss",
                    "Both stock antennas",
                    "One stock antenna every visit",
                ),
                strict=True,
            )
        ]
        chart = dict(
            id=f"second-on-miss-roster-{key}",
            method=trial.METHOD,
            scope="roof",
            cases="sealed",
            title=title,
            seal=lock,
            provenance=files,
            series=series,
            caption=(
                "Projected complete stock antenna arrays through actual compact fits. "
                "Suppressed partners keep an empty physical probe slot. "
                "Original v5 used capture-era factors. Direct IQ timings are separate."
            ),
        )
        if existing:
            chart["roof_references"] = existing
        charts.append(chart)
    save_json(REPORT / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(REPORT / "charts", evidence=REPORT)


def direct_alignment(work, candidates):
    lock = sealed(DIRECT_REPORT, "prediction-lock.json")
    if sorted(lock["cases"]) != list(trial.DIRECT):
        raise ValueError("the direct IQ comparator changed the predeclared overlap")
    raw = fixed.member(DIRECT_REPORT, lock, "positions.jsonl.gz")
    found = fixed.select(rows_from(raw), DIRECT_METHOD, lock["cases"])
    prepared = {r["id"]: r for r in candidates}
    results = []
    for ident in lock["cases"]:
        live, reconstructed = found[ident], prepared[ident]
        fixed.same_capture(live, reconstructed)
        member = f"native/{ident}.json.gz"
        exact, digest = None, None
        if member in lock["files"]:
            payload = gzip.decompress(fixed.member(DIRECT_REPORT, lock, member).read_bytes())
            digest = sha256(payload).hexdigest()
            if digest != live["native_sha256"].removeprefix("sha256:"):
                raise ValueError(f"{ident} direct fits did not use the native replay output")
            if reconstructed.get("native_sha256"):
                own = work / ident / trial.METHOD / "recording/native.json"
                exact = (
                    payload == whole_iq.checked(own, reconstructed["native_sha256"]).read_bytes()
                )
        a, b = reconstructed["result"], live["result"]
        science = {
            key: all(
                a["arms"][key].get(p) == b["arms"][key].get(p)
                for p in ("latlon", "forced_latlon", "rf_rms_hz")
            )
            if a["status"] == b["status"] == "ok"
            else None
            for key in ARMS
        }
        results.append(
            dict(
                id=ident,
                direct_status=b["status"],
                projection_status=a["status"],
                direct_native_sha256=digest,
                projected_native_sha256=reconstructed.get("native_sha256"),
                exact_native_bytes=exact,
                exact_position_and_rf_by_arm=science,
            )
        )
    name = "direct-iq-parity.json"
    save_json(
        REPORT / name,
        dict(
            direct_prediction_sha256=_sha(DIRECT_REPORT / "prediction-lock.json"),
            projected_prediction_sha256=_sha(REPORT / "prediction-lock.json"),
            cases=results,
        ),
    )
    return name


def score(work):
    result = sealed(REPORT, "prediction-lock.json")
    reproduced = sealed(REPORT, "input-reproduction.json")
    plan = whole_iq.read(REPORT / "plan.json")
    groups = plan["groups"]
    if result["cases"] != groups["all"]:
        raise ValueError("published outcomes changed the 22 scheduled cases")
    single_lock = sealed(one.REPORT, "prediction-lock.json", trial.SINGLE_PIN)
    sealed(one.REPORT, "score-lock.json", ONE_SCORE)
    stock = prior.released_stock(groups)
    always = fixed.select(
        rows_from(fixed.member(one.REPORT, single_lock, "positions.jsonl.gz")),
        one.METHOD,
        groups["all"],
    )
    candidates = fixed.select(rows_from(REPORT / "positions.jsonl.gz"), trial.METHOD, groups["all"])
    timings = []
    for job in plan["jobs"]:
        ident = job["id"]
        row = candidates[ident]
        if any(row[k] != v for k, v in job.items()):
            raise ValueError(f"{ident} changed its frozen numerical request")
        if (
            row["native_sha256"]
            and reproduced["cases"][ident]["native_sha256"] != row["native_sha256"]
        ):
            raise ValueError(f"{ident} changed detector inputs after source reproduction")
        timings.append(verify_worker(work, plan, row, stock[ident], always[ident]))
    raw_support = whole_iq.read(REPORT / "packet-audit.json")
    csv_file(
        REPORT / "support.csv",
        [
            dict(id=ident, **{k: v for k, v in value.items() if isinstance(v, int)})
            for ident, value in raw_support.items()
        ],
    )
    csv_file(REPORT / "resources.csv", timings)
    auth, original = staggered_benchmark.fresh_references()
    _, fresh = staggered_benchmark.export_references(REPORT, "score", groups["all"], auth, original)
    _, old = held_references(None, [i for i in groups["all"] if i not in fresh])
    for row in original:
        for arm in ARMS:
            fresh[row["id"]]["reference"][row["method"]][arm]["rf_rms_hz"] = row["result"]["arms"][
                arm
            ].get("rf_rms_hz")
    refs = {r["id"]: r for r in old} | fresh
    panel = [*candidates.values(), *stock.values(), *always.values()]
    options = dict(
        all=groups["all"], hard6=groups["difficult"], new2=groups["fresh"], direct2=groups["direct"]
    )
    options.update({g: [i for i in groups["all"] if i.startswith(g)] for g in ("DS26", "DS29")})
    table = scores(panel, refs)
    csv_file(REPORT / "scores.csv", table)
    csv_file(REPORT / "summary.csv", summarize(table, refs, options))
    files = [
        "prediction-lock.json",
        "support.csv",
        "resources.csv",
        "scores.csv",
        "summary.csv",
        "figures.json",
        "input-reproduction.json",
        *(f"{name}-figure-lock.json" for name in ("all", "hard6", "new2", "direct2")),
    ]
    if (DIRECT_REPORT / "prediction-lock.json").is_file():
        files.append(direct_alignment(work, list(candidates.values())))
    figures(panel, options, auth, original)
    save_json(
        REPORT / "score-lock.json",
        dict(cases=groups["all"], files={n: _sha(REPORT / n) for n in files}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    score(parser.parse_args().work)
