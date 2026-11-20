"""Publish the measured four-cell antenna comparison and its factorial contrasts."""

import argparse
import gzip
from hashlib import sha256

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution
from . import partner_on_hit_trial as trial
from . import screening_figures
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .staggered_reconstruction_results import original_rows
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
read = whole_iq.read
PRIMARY, HIT, MISS, STOCK = trial.one.METHOD, trial.METHOD, trial.miss.METHOD, trial.fixed.FOUR
METHODS = (PRIMARY, HIT, MISS, STOCK)
LABELS = ("Alternating primary only", "Partner on hit", "Partner on miss", "Both stock lanes")
CONTRASTS = (
    "add_hit_without_miss",
    "add_hit_with_miss",
    "add_miss_without_hit",
    "add_miss_with_hit",
    "interaction",
)


def effects(primary, hit, miss, both):
    def delta(a, b):
        return a - b if a is not None and b is not None else None

    interaction = delta(delta(both, miss), delta(hit, primary))
    terms = (
        delta(hit, primary),
        delta(both, miss),
        delta(miss, primary),
        delta(both, hit),
        interaction,
    )
    return dict(zip(CONTRASTS, terms, strict=True))


def verify(work, plan, rows, proof, parent_rows, prior_proof):
    planned = {r["id"]: r for r in plan["schedule"]}
    if len(rows) != len(trial.CASES) or {r["id"] for r in rows} != set(trial.CASES):
        raise ValueError("the eight scheduled recordings must each have a terminal row")
    resources = []
    for row in rows:
        ident = row["id"]
        if any(row[k] != v for k, v in planned[ident].items()):
            raise ValueError("result did not use its frozen numerical input")
        folder = work / ident / HIT
        if read(folder / "attempt.json") != row:
            raise ValueError("terminal row changed from measured numerical service")
        native = whole_iq.checked(folder / "recording/native.json", row["native_sha256"])
        projected, witness = trial.certificate(ident, parent_rows, prior_proof)
        if witness != proof[ident] or sha256(encoded(projected) + b"\n").hexdigest() != _sha(
            native
        ):
            raise ValueError("the physical packet allocation failed to reproduce")
        request = whole_iq.checked(
            folder / "recording/request.json", row["prepared_request_sha256"]
        )
        _, original = whole_iq.binding(ident)
        trial.verify_request(
            read(request), original, native_path=native, native_sha256=_sha(native)
        )
        log = whole_iq.checked(folder / "service.log", row["log_sha256"])
        write(REPORT / "logs" / f"{ident}.log.gz", gzip.compress(log.read_bytes(), mtime=0))
        sample = row.get("position_resources") or {}
        if row["terminal"] == "success" and (
            not sample or row["result"]["metrics"]["observations"] != witness["observations"][HIT]
        ):
            raise ValueError("successful position lacks the actual sample or expected observations")
        for edge in ("start", "end"):
            if sample and (
                sample[edge]["cpus"] != [row["cpu"]]
                or sample[edge]["memory.max"] != plan["memory_bytes"]
                or sample[edge]["memory.swap.max"] != 0
                or sample[edge]["memory.swap.current"] != 0
                or sample[edge]["nice"] != 10
            ):
                raise ValueError("service left its prescribed resource bounds")
        resources.append(
            dict(
                id=ident,
                cpu=row["cpu"],
                terminal=row["terminal"],
                status=row["result"]["status"],
                position_wall_s=sample.get("wall_s"),
                position_cpu_s=sample.get("cpu_s"),
                peak_bytes=sample.get("peak_bytes"),
                swap_bytes=sample.get("end", {}).get("memory.swap.current"),
                supervisor_wall_s=row.get("supervisor_wall_s"),
                detector_wall_s=None,
            )
        )
    return resources


def metrics(rows, refs, census):
    scores = trial.fixed.scored(rows, refs)
    series = {(r["id"], r["method"], r["arm"]): r for r in scores}
    counters = {(r["id"], r["method"]): r["result"]["metrics"] for r in rows}
    deltas = []
    for ident in trial.CASES:
        cohort = "challenge" if ident in trial.hard.HARD else "known-control"
        for arm in ARMS:
            subset = [series[ident, method, arm] for method in METHODS]
            for record in subset:
                method = record["method"]
                record["cohort"] = cohort
                record["receiver_calls"] = census[ident]["calls"][method]
                record["gated_probes"] = census[ident]["observations"][method]
                record["solver_observations"] = counters[ident, method].get("observations")
                record["tracks"] = counters[ident, method].get("tracks")
            for name in ("error_km", "rf_rms_hz", "tracks"):
                values = [r[name] for r in subset]
                deltas.append(
                    dict(
                        id=ident,
                        cohort=cohort,
                        arm=arm,
                        measure=name,
                        **dict(zip(METHODS, values, strict=True)),
                        **effects(*values),
                    )
                )
    return scores, deltas


def aggregate(scores, deltas, refs):
    totals, contrasts = [], []
    groups = {
        "all": trial.CASES,
        "challenge": trial.hard.HARD,
        "known-control": trial.hard.CONTROLS,
    }
    for cohort, ids in groups.items():
        for arm in ARMS:
            group = [r for r in scores if r["id"] in ids and r["arm"] == arm]
            for method in (*METHODS, *ROLES):
                row = trial.fixed.summary_row(group, ids, cohort, arm, method)
                subset = [r for r in group if r["method"] == method]
                rms = (
                    [r["rf_rms_hz"] for r in subset]
                    if subset
                    else [refs[i]["reference"][method][arm].get("rf_rms_hz") for i in ids]
                )
                dist = distribution(rms)
                totals.append(
                    dict(row, conditional_rf_n=dist["n"], conditional_rf_p50_hz=dist["p50"])
                )
            for measure in ("error_km", "rf_rms_hz", "tracks"):
                paired = [
                    r
                    for r in deltas
                    if r["id"] in ids and r["arm"] == arm and r["measure"] == measure
                ]
                for name in CONTRASTS:
                    inputs = [r[name] for r in paired if r[name] is not None]
                    dist = distribution(inputs)
                    contrasts.append(
                        dict(
                            cohort=cohort,
                            arm=arm,
                            measure=measure,
                            contrast=name,
                            scheduled=len(ids),
                            paired=dist["n"],
                            lower=sum(x < 0 for x in inputs),
                            median=dist["p50"],
                            min=dist["min"],
                            max=dist["max"],
                        )
                    )
    return totals, contrasts


def figure():
    members = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "scores.csv",
        "effects.csv",
        "effects-summary.csv",
        "summary.csv",
        "capture-era-v5.csv",
        "support.csv",
        "resources.csv",
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=list(trial.CASES), files={name: _sha(REPORT / name) for name in members}),
    )
    keys = ("one_native_factors", "one", "all_visits", "stock")
    chart = dict(
        id="partner-on-hit-factorial",
        method=HIT,
        scope="roof",
        cases="sealed",
        seal="figure-lock.json",
        title="Partner antenna observations on primary hits and misses",
        caption=(
            "Four stored-factor inputs share one physical acquisition and RF primary schedule. "
            "Eight recordings, including six earlier challenges. The partner-on-hit fits "
            "were newly measured with both calibration arms. Calls are schedule counts."
        ),
        provenance=list(members[1:]),
        series=[
            dict(
                key=key,
                label=label,
                file=members[0],
                value=method,
                native_field="paired_capture_sha256",
                match=[*trial.fixed.BINDINGS, "stock_native_sha256"],
            )
            for key, method, label in zip(keys, METHODS, LABELS, strict=True)
        ],
    )
    save_json(REPORT / "figures.json", dict(version=2, charts=[chart]))


def publish(work):
    lock = sealed(REPORT, "prediction-lock.json")
    plan = read(trial.fixed.member(REPORT, lock, "plan.json"))
    proof = read(trial.fixed.member(REPORT, lock, "packet-audit.json"))
    rows = rows_from(trial.fixed.member(REPORT, lock, "predictions.jsonl.gz"))
    parents, parent_rows, audits, _ = trial.controls()
    if parents != plan["parents"] or any(_sha(ROOT / n) != d for n, d in plan["sources"].items()):
        raise ValueError("pre-inference source changed")
    csv_file(REPORT / "resources.csv", verify(work, plan, rows, proof, parent_rows, audits))
    all_rows = rows + [
        dict(parent_rows[m][i], stock_native_sha256=parent_rows[STOCK][i]["native_sha256"])
        for m in (PRIMARY, MISS, STOCK)
        for i in trial.CASES
    ]
    _, origin = held_references(None, trial.CASES)
    refs = {r["id"]: r for r in origin}
    scores, deltas = metrics(all_rows, refs, proof)
    summary, contrasts = aggregate(scores, deltas, refs)
    for name, records in (
        ("scores.csv", scores),
        ("effects.csv", deltas),
        ("summary.csv", summary),
        ("effects-summary.csv", contrasts),
        ("capture-era-v5.csv", original_rows(refs, parent_rows[STOCK])),
    ):
        csv_file(REPORT / name, records)
    support = []
    for ident in trial.CASES:
        item = proof[ident]
        support.append(
            dict(
                id=ident,
                **{
                    k: item[k]
                    for k in (
                        "valid_visits",
                        "invalid_visits",
                        "primary_hits",
                        "covisible_partner_hits",
                        "partner_only_hits",
                        "neither_hits",
                    )
                },
                **{f"{method}_calls": item["calls"][method] for method in METHODS},
                **{f"{method}_observations": item["observations"][method] for method in METHODS},
            )
        )
    csv_file(REPORT / "support.csv", support)
    pack(REPORT / "positions.jsonl.gz", all_rows)
    figure()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work)
    if args.plot:
        screening_figures.generate(args.plot, evidence=REPORT)
