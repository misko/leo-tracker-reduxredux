"""Score one-offer roof predictions only after the blind replay is sealed."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json, write
from ..scoring import ARMS, distribution, thresholds
from . import boundary_roof as trial
from . import native_joint_full_results as shared

offers = trial.offers
phase = trial.phase
METHODS = trial.METHODS
CONDITIONS = offers.CONDITIONS
LABELS = dict(
    zip(CONDITIONS, ("Original", "1–2 km inside", "1–2 km outside", "6 km outside"), strict=True)
)
PHYSICAL_FIELDS = ("latlon", "forced_latlon", "rf_rms_hz", "frequency_score", "radius_km")


def gate(row):
    result = row["result"]
    if result["status"] != "ok":
        return row
    arms = result["arms"]
    if all(
        arm.get("radius_km") is not None
        and arm.get("latlon") is not None
        and shared.roi_margin(arm["latlon"], row["tile"]) >= arm["radius_km"]
        for arm in arms.values()
    ):
        return row
    return dict(
        row,
        result=dict(
            result,
            status="withheld",
            reason="nominal_position_radius_crosses_tile_edge",
            arms={key: dict(arm, latlon=None, region_id=None) for key, arm in arms.items()},
        ),
    )


def validated_rows(output, work):
    lock = phase._read(output / "prediction-lock.json")
    trial.clock.base.secant_full._verify_files(output, lock["files"])
    if lock["evaluator_sha256"] != phase.digest(work / "evaluator.json"):
        raise ValueError("evaluator labels changed after the worker seal")
    oracle = phase._read(work / "evaluator.json")
    plan = phase._read(output / "roster.json")
    labels = {r["id"]: r for r in oracle["labels"]}
    if set(labels) != set(lock["cases"]):
        raise ValueError("the offer-maker and receiver rosters differ")
    records = {m: read_predictions(output / f"{m}.jsonl.gz") for m in METHODS}
    graph_by_recording = {}
    for method, series in records.items():
        if set(series) != set(labels):
            raise ValueError("unsealed receiver roster")
        for ident, row in series.items():
            label = labels[ident]
            for key in ("tile", "input_sha256", "recording"):
                if row[key] != label[key]:
                    raise ValueError(f"{method}/{ident} differs from the scored offer")
            graph = row.get("observation_sha256")
            if graph and graph_by_recording.setdefault(row["recording"], graph) != graph:
                raise ValueError("same native recording rebuilt different Graphs across offers")
    for label in labels.values():
        margin = shared.roi_margin(label["truth"], label["tile"])
        requested = label["requested_margin_km"]
        if abs(margin - label["true_margin_km"]) > 1e-6 or (
            requested is not None and abs(margin - requested) > 1e-6
        ):
            raise ValueError("sealed offer did not place truth at the measured margin")
        if (margin < 0) != (label["condition"] in ("near-outside", "six-outside")):
            raise ValueError("offer classification differs from its measured geometry")
    return lock, plan, labels, records


def score_rows(records, labels, *, containment=False):
    rows = []
    for method, series in records.items():
        for ident, original in series.items():
            row = gate(original) if containment else original
            label = labels[ident]
            for arm in ARMS:
                data = row["result"]["arms"][arm]
                held = row["result"]["metrics"].get("held_by_arm", {}).get(arm, {})
                rows.append(
                    dict(
                        id=ident,
                        method=method,
                        recording=row["recording"],
                        arm=arm,
                        dataset=row["recording"].split("-", 1)[0],
                        condition=label["condition"],
                        face=label["face"],
                        true_tile_margin_km=label["true_margin_km"],
                        fitted_tile_margin_km=shared.roi_margin(
                            data.get("forced_latlon"), label["tile"]
                        ),
                        radius_km=data.get("radius_km"),
                        held_rf_rms_hz=held.get("held_rf_rms_hz"),
                        **shared.geodata(row, arm, label["truth"]),
                    )
                )
    return rows


def aggregate(rows):
    output = []
    for method in METHODS:
        for arm in ARMS:
            pairs = [r for r in rows if r["method"] == method and r["arm"] == arm]
            per_recording = {}
            metrics = []
            for condition in CONDITIONS:
                data = [r for r in pairs if r["condition"] == condition]
                for row in data:
                    per_recording.setdefault(row["recording"], {})[condition] = row["status"]
                metrics.append(
                    dict(
                        condition=condition,
                        scheduled=len(data),
                        statuses=dict(Counter(r["status"] for r in data)),
                        reasons=dict(Counter(r["reason"] for r in data if r["reason"] is not None)),
                        within_km=thresholds([r["error_km"] for r in data]),
                        **{
                            metric: distribution(r[metric] for r in data)
                            for metric in (
                                "error_km",
                                "forced_error_km",
                                "conditional_rms_hz",
                                "held_score",
                                "held_rf_rms_hz",
                                "fitted_tile_margin_km",
                                "radius_km",
                                "worker_wall_s",
                                "worker_cpu_s",
                                "peak_rss_kib",
                                "vm_peak_kib",
                            )
                        },
                    )
                )
            omission_counts = Counter(
                sum(d[condition] == "ok" for condition in ("near-outside", "six-outside"))
                for d in per_recording.values()
            )
            output.append(
                dict(
                    method=method,
                    arm=arm,
                    conditions=metrics,
                    per_recording=per_recording,
                    omissions_scheduled=2 * len(per_recording),
                    omitted_publications=sum(k * v for k, v in omission_counts.items()),
                    affected_recordings=omission_counts[1] + omission_counts[2],
                    per_recording_omission_counts=dict(omission_counts),
                )
            )
    return output


def archived_agreement(records, labels):
    output = []
    for folder, method in ((trial.clock.REPORT, METHODS[0]), (trial.fixed.REPORT, METHODS[1])):
        lock = phase._read(folder / "prediction-lock.json")
        trial.clock.base.secant_full._verify_files(folder, lock["files"])
        stock = read_predictions(folder / "positions.jsonl.gz")
        for ident, label in labels.items():
            if label["condition"] != "original":
                continue
            current = records[method][ident]
            old = stock[label["recording"]]
            a, b = current["result"], old["result"]
            physical = all(
                a["arms"][arm].get(k) == b["arms"][arm].get(k)
                for arm in ARMS
                for k in PHYSICAL_FIELDS
            )
            output.append(
                dict(
                    recording=label["recording"],
                    method=method,
                    same_graph=current.get("observation_sha256") == old.get("observation_sha256"),
                    same_physical_arms_and_decision=physical and a["status"] == b["status"],
                )
            )
    return output


def figures(output, plan, labels, records, lock, *, containment=False):
    files = lock["files"].copy()
    cases = lock["cases"]
    queries = []
    for ident in cases:
        label = labels[ident]
        ref = records[METHODS[0]][ident]
        bindings = {k: ref[k] for k in ("input_sha256", "native_sha256", "catalog_sha256")}
        queries.append(
            dict(
                id=ident,
                condition=label["condition"],
                recording=label["recording"],
                truth=label["truth"],
                bindings=bindings,
            )
        )
    save_json(output / "figure-queries.json", dict(queries=queries))
    files["figure-queries.json"] = phase.digest(output / "figure-queries.json")
    graphs = all(
        r.get("observation_sha256") for series in records.values() for r in series.values()
    )
    specs = []
    for guard in (False, True) if containment else (False,):
        key = "containment" if guard else "original-gates"
        names = {}
        for method in METHODS:
            if guard:
                name = f"{method}-containment.jsonl.gz"
                files[name] = shared.pack(output, name, [gate(r) for r in records[method].values()])
            else:
                name = f"{method}.jsonl.gz"
            names[method] = name
        seal = f"{key}-figure-lock.json"
        save_json(output / seal, dict(cases=cases, files=files))
        specs.append(
            dict(
                id=f"boundary-roof-{plan['cohort']}-{key}",
                method=METHODS[0],
                scope="transfer",
                title="Roof offers with position-radius containment"
                if guard
                else "Near-edge roof offers",
                caption="Same archived native recordings with four supplied tiles per recording.",
                cases=cases,
                seal=seal,
                queries="figure-queries.json",
                condition_labels=LABELS,
                series=[
                    dict(
                        key="candidate",
                        label="Native smooth oscillator",
                        file=names[METHODS[0]],
                        value=METHODS[0],
                    ),
                    dict(
                        key="stock",
                        label="Native fixed-training update",
                        file=names[METHODS[1]],
                        value=METHODS[1],
                        match=["input_sha256", "tile"] + (["observation_sha256"] if graphs else []),
                    ),
                ],
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=specs))


def score(output, work):
    lock, plan, labels, records = validated_rows(output, work)
    if phase.digest(work / "requests.json") != plan["requests_sha256"]:
        raise ValueError("blind requests changed after the worker seal")
    for name in ("requests.json", "evaluator.json"):
        write(output / name, (work / name).read_bytes())
    rows = score_rows(records, labels)
    group = aggregate(rows)
    archive = archived_agreement(records, labels)
    summary = dict(groups=group, archived_original_repeats=archive, batch_wall_s=lock["wall_s"])
    shared.csv_file(output / "scores.csv", rows)
    reserve = plan["cohort"] == "reserve"
    if reserve:
        guarded = score_rows(records, labels, containment=True)
        shared.csv_file(output / "containment-scores.csv", guarded)
        summary["containment"] = aggregate(guarded)
    else:
        summary["triggers_reserve"] = any(r["omitted_publications"] >= 5 for r in group)
    save_json(output / "summary.json", summary)
    figures(output, plan, labels, records, lock, containment=reserve)
    return summary


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("cohort", choices=("primary", "reserve"))
    cli.add_argument("--work", type=Path, default=offers.WORK)
    cli.add_argument("--output", type=Path, default=offers.REPORT)
    args = cli.parse_args()
    result = score(args.output / args.cohort, args.work / args.cohort)
    print(result.get("triggers_reserve"))


if __name__ == "__main__":
    main()
