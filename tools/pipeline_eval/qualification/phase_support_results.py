"""Score sealed blind native phase support and build the standard roof figures."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from statistics import median

from ..__main__ import encoded, references, save_json, write
from ..scoring import ARMS, coordinate, distance_km, distribution, thresholds
from . import native_joint_full as panel
from . import phase_support_trial as trial


def records(path):
    return list(map(json.loads, gzip.decompress(path.read_bytes()).splitlines()))


def owners(row, arm="fitted_c"):
    traces = row["result"]["metrics"].get("phase_support", {}).get("fit", {})
    return {tuple(record["key"]): record for record in traces.get(arm, {}).get("owners", [])}


def authority(output):
    lock = trial.base.phase._read(output / "prediction-lock.json")
    if lock["predictions_sha256"] != trial.digest((output / "predictions.jsonl.gz").read_bytes()):
        raise ValueError("candidate predictions were not sealed")
    raw = (output / "plan.json").read_bytes()
    if lock["plan_sha256"] != trial.digest(raw):
        raise ValueError("candidate plan differs from the prediction binding")
    plan = json.loads(raw)
    attempts = records(output / "predictions.jsonl.gz")
    scheduled = {(r["id"], r["policy"]) for r in plan["scheduled"]}
    got = {(r["id"], r["policy"]) for r in attempts}
    if len(got) != len(attempts) or not got <= scheduled or len(got) != lock["attempted"]:
        raise ValueError("attempts do not match the locked roster")
    for file, value in plan["source"]["files"].items():
        if trial.digest((trial.ROOT / file).read_bytes()) != value:
            raise ValueError("phase support source differs from the original trial")
    control = panel.REPORT / "positions.jsonl.gz"
    if trial.digest(control.read_bytes()) != plan["source"]["stock_positions_sha256"]:
        raise ValueError("archived matched native joint control differs")
    reference = {r["id"]: r for r in records(control)}
    for row in attempts:
        control = reference[row["id"]]
        for k in ("input_sha256", "native_sha256", "catalog_sha256", "tile"):
            if row[k] != control[k]:
                raise ValueError(f"{row['id']}: variant request differs from matched stock {k}")
        if row["result"]["status"] in ("ok", "withheld") and (
            row["observation_sha256"] != control["observation_sha256"]
            or row["address_space_limit_mib"] != 512
            or row["proc_memory_kib"]["VmPeak"] > 512 * 1024
            or any("localization_v3" in p or "/v5_" in p for p in row["imported_first_party"])
        ):
            raise ValueError(f"{row['id']}: worker violated the unchanged native input boundary")
    return plan, attempts, reference, scheduled - got


def summarize(attempts, archived, refs, plan):
    keys = set(plan["primary"])

    def group(ident):
        if ident in plan["confirmation"]:
            return "confirmation"
        if ident in keys:
            return "disputed"
        return "roof"

    cases = sorted({r["id"] for r in attempts if r["policy"] == "causal"})
    rows = []
    for r in [*attempts, *(dict(archived[k], policy="stock") for k in cases)]:
        result = r["result"]
        truth = refs[r["recording"]]["truth"]
        for arm in ARMS:
            value = result.get("arms", {}).get(arm, {})
            rows.append(
                dict(
                    id=r["id"],
                    recording=r["recording"],
                    policy=r["policy"],
                    arm=arm,
                    cohort="omitted" if r["id"] != r["recording"] else group(r["id"]),
                    status=result["status"],
                    reason=result.get("reason"),
                    error_km=distance_km(value.get("latlon"), truth),
                    forced_error_km=distance_km(value.get("forced_latlon"), truth),
                    conditional_rms_hz=value.get("rf_rms_hz"),
                    associated_observations=result["metrics"].get("associated_observations"),
                    v5_error_km=refs[r["recording"]]["reference"]
                    .get("baseline", {})
                    .get(arm, {})
                    .get("error_km"),
                )
            )
    summary = {}
    for method in ("stock", "causal", "fixed", "wide"):
        for cohort in ("all-roof", "disputed", "confirmation", "omitted"):
            for arm in ARMS:
                available = [
                    r
                    for r in rows
                    if r["policy"] == method
                    and r["arm"] == arm
                    and (
                        r["cohort"] == cohort or (cohort == "all-roof" and r["cohort"] != "omitted")
                    )
                ]
                if not available:
                    continue
                summary[f"{method}/{cohort}/{arm}"] = dict(
                    statuses=Counter(r["status"] for r in available),
                    within_km=thresholds([r["error_km"] for r in available]),
                    **{
                        k: distribution(r[k] for r in available)
                        for k in (
                            "error_km",
                            "forced_error_km",
                            "conditional_rms_hz",
                            "associated_observations",
                        )
                    },
                )
    return rows, summary


def audit_owners(attempts):
    by_id = {(r["id"], r["policy"]): r for r in attempts}
    compared = {}
    for ident in trial.DISPUTED:
        fixed = by_id.get((ident, "fixed"))
        if not fixed:
            continue
        before = owners(fixed)
        for policy in ("causal", "wide"):
            current = by_id.get((ident, policy))
            if not current:
                continue
            after = owners(current)
            shared = before.keys() & after.keys()
            compared[f"{ident}/{policy}"] = dict(
                fixed_tracks=len(before),
                candidate_tracks=len(after),
                common_tracks=len(shared),
                changed_satellite=sum(before[k]["norad"] != after[k]["norad"] for k in shared),
                changed_lift=sum(before[k]["alias"] != after[k]["alias"] for k in shared),
                inserted_tracks=len(after.keys() - before.keys()),
                dropped_tracks=len(before.keys() - after.keys()),
                maximum_phase_s=max((abs(r["phase_s"]) for r in after.values()), default=0),
                satellite_67315=[r for r in after.values() if r["norad"] == 67315],
            )
    return compared


def pack(path, rows):
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


def figures(output, attempts, archived, omitted):
    candidates = sorted((r for r in attempts if r["policy"] == "causal"), key=lambda r: r["id"])
    if any(r["result"]["status"] not in ("ok", "withheld") for r in candidates):
        # The comparison plots use observation hashes for both completed workers.
        candidates = [r for r in candidates if r["result"]["status"] in ("ok", "withheld")]
    charts = []
    for scope, title, condition, key in (
        ("roof", "Age-adaptive phase support on the roof", "roof", "one"),
        ("transfer", "Age-adaptive phase support on omitted offers", "omitted", "candidate"),
    ):
        selected = [r for r in candidates if (r["id"] not in omitted) == (condition == "roof")]
        cases = [r["id"] for r in selected]
        if not cases:
            continue
        plot = f"{condition}-positions.jsonl.gz"
        control = f"{condition}-stock.jsonl.gz"
        pack(output / plot, selected)
        pack(output / control, [archived[i] for i in cases])
        names = [plot, control, "prediction-lock.json", "owner-deltas.json"]
        extra = {}
        if condition == "omitted":
            queries = f"{condition}-queries.json"
            save_json(output / queries, dict(queries=[omitted[i] for i in cases]))
            names.append(queries)
            extra["queries"] = queries
        seal = f"{condition}-figure-lock.json"
        save_json(
            output / seal,
            dict(
                cases=cases,
                files={n: trial.digest((output / n).read_bytes()) for n in names},
                plan_sha256=trial.digest((output / "plan.json").read_bytes()),
            ),
        )
        charts.append(
            dict(
                id=f"phase_support_{condition}",
                method="phase_support_causal",
                scope=scope,
                title=title,
                caption=(
                    "Blind complete native GLRT with identical Graph and gate. Causal age "
                    "and catalogue disagreement set the per-orbit range before assignment."
                ),
                cases=cases,
                seal=seal,
                series=[
                    dict(
                        key=key,
                        label="Causal per-orbit support",
                        file=plot,
                        value="phase_support_causal",
                        forced_label="Causal support forced diagnostic",
                    ),
                    dict(
                        key="stock",
                        label="Original joint phase support",
                        file=control,
                        value="native_joint_orbits",
                        match=[
                            "input_sha256",
                            "native_sha256",
                            "catalog_sha256",
                            "observation_sha256",
                        ],
                    ),
                ],
                source_lock=dict(file="plan.json", digest_key="plan_sha256"),
                provenance=["prediction-lock.json", "owner-deltas.json"],
                **extra,
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=charts))


def score(output):
    plan, attempts, archived, missing = authority(output)
    ids = {r["recording"] for r in attempts}
    refs = {}
    for prefix, source in (("DS26-", "ds26-all159"), ("DS29-", "roof16")):
        refs.update(
            {r["id"]: r for r in references(source, [i for i in ids if i.startswith(prefix)])[1]}
        )
    queries = json.loads((panel.REPORT / "omitted-queries.json").read_bytes())["queries"]
    omitted = {r["id"]: r for r in queries}
    for query in omitted.values():
        base = refs.get(query["recording"])
        if base and coordinate(query["truth"]) != coordinate(base["truth"]):
            raise ValueError("omitted truth binding differs from the frozen recording")
    rows, summary = summarize(attempts, archived, refs, plan)
    fresh = {r["id"]: r for r in attempts if r["policy"] == "fixed"}
    stock_equal = {
        ident: all(r["result"]["arms"][a] == archived[ident]["result"]["arms"][a] for a in ARMS)
        for ident, r in fresh.items()
    }
    recent = [r for r in attempts if r["policy"] == "causal"]
    history = [r["result"]["metrics"].get("phase_support", {}).get("history") for r in recent]
    history = [r for r in history if r and "history_bytes" in r]
    cost = {
        k: distribution(r[k] for r in history)
        for k in (
            "history_bytes",
            "retained_tle_bytes",
            "numeric_port_bytes",
            "expanded_orbits",
            "width_pairs",
            "fallback_orbits",
            "sgp4_calls",
            "cpu_s",
            "wall_s",
        )
    }
    cost["median_wall_s"] = median(r["worker_wall_s"] for r in recent)
    cost["stock_median_wall_s"] = median(archived[r["id"]]["worker_wall_s"] for r in recent)
    cost["maximum_worker_rss_kib"] = max((r.get("resident_peak_kib", 0) for r in recent), default=0)
    save_json(
        output / "scores.json",
        dict(
            rows=rows,
            summary=summary,
            history_cost=cost,
            stock_equal=stock_equal,
            missing=sorted(missing),
        ),
    )
    save_json(output / "owner-deltas.json", audit_owners(attempts))
    figures(output, attempts, archived, omitted)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=trial.REPORT)
    score(p.parse_args().output)
