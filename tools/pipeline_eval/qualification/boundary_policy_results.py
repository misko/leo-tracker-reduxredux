"""Audit fresh and archived paired tile-guard dispositions separately."""

import argparse
import csv
import gzip
import io
import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants.compact_tile_interior import guard, margin
from . import boundary_policy_trial as trial
from . import screening_figures as standard
from .armijo_finish_results import pack

SHIFTED = trial.SCREEN / "redesign/compact-transfer"
LABELS = {
    "center": "Interior offer",
    "near-inside": "1.5 km inside",
    "near-outside": "1.5 km outside",
    "far-omission": "27.5 km outside",
    "containing": "Containing offer",
    "omitted": "Near omitted offer",
    "measured-containing": "Measured roof containing",
    "measured-shifted-containing": "Measured shifted containing",
}


def verified(folder, name):
    path = folder / name
    lock = trial.read(path)
    for file, digest in lock.get("files", lock).items():
        if trial.digest(folder / file) != digest:
            raise ValueError(f"{folder.name}/{file} differs from its sealed evidence")
    return lock


def row_stream(path):
    with gzip.open(path, "rt") as stream:
        return list(map(json.loads, stream))


def guarded_pair(row, tile):
    return [
        dict(
            row,
            method=trial.METHODS[0],
            result=guard(row["result"], tile),
            decision_cli_wall_s=None,
        ),
        dict(row, method=trial.METHODS[1], decision_cli_wall_s=None),
    ]


def common_query(case, target, mode):
    return dict(
        id=case["id"],
        recording=case["session"],
        condition=mode,
        truth=target["site"],
        bindings=dict(input_sha256=sha256(encoded(case)).hexdigest()),
    )


def fresh(work, out):
    lock = verified(out, "prediction-lock.json")
    private = work / "private.json"
    if trial.digest(private) != trial.read(out / "input-lock.json")["private_sha256"]:
        raise ValueError("geographic labels differ from the prospective commitment")
    planned = {r["id"]: r for r in trial.read(out / "requests.json")}
    if set(planned) != set(lock["cases"]) or len(planned) != 8:
        raise ValueError("fresh scheduled roster changed")
    rows = row_stream(out / "positions.jsonl.gz")
    by = {(r["id"], r["method"]): r for r in rows}
    if len(by) != len(rows) or set(by) != {(i, m) for i in planned for m in trial.METHODS}:
        raise ValueError("the blind seal lacks complete paired results")
    private_data = trial.read(private)
    labels = private_data["labels"]
    if set(labels) != set(planned):
        raise ValueError("geographic labels do not cover the frozen roster")
    for ident, case in planned.items():
        target = labels[ident]
        expected = 12.5 - trial.MODES[target["mode"]]
        actual = margin(target["site"], dict(center=case["tile"], width_km=25.0))
        if abs(actual - expected) > 0.02 or target["session"] != case["session"]:
            raise ValueError("fresh truth does not match the four fixed offer geometry")
        extended = [by[ident, method] for method in trial.METHODS]
        if any(
            not r["off_exact_byte_match"]
            or r["native_sha256"] != case["native_sha256"]
            or r["catalogue_sha256"] != case["catalog_sha256"]
            for r in extended
        ):
            raise ValueError("fresh flag or installed scientific input differs from its seal")
    save_json(out / "truth-after-lock.json", private_data)
    return (
        rows,
        [common_query(c, labels[i], labels[i]["mode"]) for i, c in planned.items()],
        {i: dict(center=c["tile"], width_km=25.0) for i, c in planned.items()},
    )


def archived_simulations():
    prior = trial.OLDER
    verified(prior, "prediction-lock.json")
    verified(prior, "score-lock.json")
    targets = trial.read(prior / "truth-after-lock.json")["targets"]
    requests = {r["id"]: r for r in trial.read(prior / "requests.json")}
    rows = row_stream(prior / "positions.jsonl.gz")
    expected = {(i, m) for i in requests for m in ("phase-release", "compact")}
    if len(rows) != len(expected) or {(r["id"], r["method"]) for r in rows} != expected:
        raise ValueError("earlier retrospective panel must include every archived offer/profile")
    tiles = {i: dict(center=r["tile"], width_km=25.0) for i, r in requests.items()}
    queries = [common_query(r, targets[i], targets[i]["condition"]) for i, r in requests.items()]
    panels = {}
    for method in ("phase-release", "compact"):
        paired = []
        for row in rows:
            if row["method"] != method:
                continue
            # The earlier outside-namespace time counters describe the launcher.
            original = dict(row, worker_cpu_s=None, peak_rss_kib=None, source_method=method)
            paired.extend(guarded_pair(original, tiles[row["id"]]))
        panels[f"archived-{method}"] = (paired, queries, tiles)
    return panels


def measured():
    roof = trial.ROOF
    archive = verified(roof, "prediction-lock.json")
    rows = row_stream(roof / "positions.jsonl.gz")
    if set(archive["cases"]) != {"DS26-0014", "DS29-0127"} or len(rows) != 2:
        raise ValueError("the measured wide cohort differs from the complete two-case panel")
    truth, _ = standard._roof_authority()
    resources = trial.read(roof / "resources.json")
    tiles, queries, paired = {}, [], []
    for row in rows:
        ident = row["id"]
        tile = dict(center=row["tile"]["center"], width_km=row["tile"].get("width_km", 25.0))
        if row["method"] != "fresh_wide_four_full_iq" or tile["width_km"] != 25.0:
            raise ValueError("measured inputs require the same exact compact square")
        latlon = truth[ident]["truth"]
        if margin(latlon, tile) <= 0:
            raise ValueError("the archival measured original tile is not containing")
        queries.append(
            dict(
                id=ident,
                recording=ident,
                condition="measured-containing",
                truth=latlon,
                bindings=dict(input_sha256=row["input_sha256"]),
            )
        )
        tiles[ident] = tile
        timing = resources[ident]
        original = dict(
            row,
            source_method=row["method"],
            worker_wall_s=timing.get("position_s"),
            worker_cpu_s=None,
            peak_rss_kib=None,
        )
        paired.extend(guarded_pair(original, tile))
    verified(SHIFTED / "measured-retry", "prediction-lock.json")
    verified(SHIFTED, "compact-secant-measured-shift-lock.json")
    row = trial.read(SHIFTED / "measured-retry/prediction.json")
    (query,) = trial.read(SHIFTED / "compact-secant-measured-shift-queries.json")["queries"]
    ident = row["id"]
    if (
        ident != query["id"]
        or any(row[k] != v for k, v in query["bindings"].items())
        or (margin(query["truth"], row["tile"]) <= 0)
    ):
        raise ValueError("authentic shifted archive lacks the bound exact compact containing offer")
    tiles[ident] = row["tile"]
    queries.append(
        dict(
            query,
            condition="measured-shifted-containing",
            bindings=dict(input_sha256=row["worker_input_sha256"]),
        )
    )
    original = dict(
        row,
        source_method=row["method"],
        input_sha256=row["worker_input_sha256"],
        worker_wall_s=row["wall_s"],
        worker_cpu_s=None,
        peak_rss_kib=None,
    )
    paired.extend(guarded_pair(original, row["tile"]))
    return paired, queries, tiles


def check_pair(before, after):
    validate_result(before)
    validate_result(after)
    for arm, source in before["arms"].items():
        dest = after["arms"][arm]
        if source.get("rf_rms_hz") != dest.get("rf_rms_hz") or (
            source.get("latlon") is not None
            and source["latlon"] != (dest.get("latlon") or dest.get("forced_latlon"))
        ):
            raise ValueError("the guard changed the selected estimate or RF residual")


def dispositions(cohort, rows, queries, tiles):
    by = {(r["id"], r["method"]): r for r in rows}
    for case in queries:
        ident, mode, truth = case["id"], case["condition"], case["truth"]
        is_inside = margin(truth, tiles[ident]) > 0
        off, on = (by[ident, method] for method in reversed(trial.METHODS))
        original, guarded = off["result"], on["result"]
        if guard(original, tiles[ident]) != guarded:
            raise ValueError("paired disposition differs from the frozen numerical decision")
        check_pair(original, guarded)
        for arm in ARMS:
            base, filtered = original["arms"][arm], guarded["arms"][arm]
            start, selected = base.get("latlon"), filtered.get("latlon")
            survived = selected is not None
            removed = start is not None and not survived
            yield dict(
                cohort=cohort,
                id=ident,
                site=case["recording"],
                condition=mode,
                arm=arm,
                truth_margin_km=margin(truth, tiles[ident]),
                truth_inside=is_inside,
                original_status=original["status"],
                guarded_status=guarded["status"],
                guarded_reason=guarded.get("reason"),
                original_published=start is not None,
                guarded_published=survived,
                no_original_estimate=start is None and base.get("forced_latlon") is None,
                legitimate_guard_withheld=is_inside and removed,
                false_original_publication=not is_inside and start is not None,
                false_guarded_publication=not is_inside and survived,
                false_publication_stopped=not is_inside and removed,
                selected_margin_km=None if start is None else margin(start, tiles[ident]),
                original_error_km=distance_km(start, truth),
                guarded_error_km=distance_km(selected, truth),
                forced_error_km=distance_km(filtered.get("forced_latlon"), truth),
                conditional_rf_rms_hz=base.get("rf_rms_hz"),
                worker_wall_s=off.get("worker_wall_s"),
                worker_cpu_s=off.get("worker_cpu_s"),
                peak_rss_kib=off.get("peak_rss_kib"),
                decision_cli_wall_s=on.get("decision_cli_wall_s"),
            )


def tabulate(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["cohort"], row["condition"], row["arm"]].append(row)
    return {
        "/".join(key): dict(
            attempts=len(items),
            statuses=dict(Counter(r["guarded_status"] for r in items)),
            **{
                k: sum(r[k] for r in items)
                for k in (
                    "original_published",
                    "guarded_published",
                    "no_original_estimate",
                    "legitimate_guard_withheld",
                    "false_original_publication",
                    "false_guarded_publication",
                    "false_publication_stopped",
                )
            },
            **{
                k: distribution(r[k] for r in items)
                for k in (
                    "original_error_km",
                    "guarded_error_km",
                    "forced_error_km",
                    "conditional_rf_rms_hz",
                    "worker_wall_s",
                    "worker_cpu_s",
                    "peak_rss_kib",
                    "decision_cli_wall_s",
                )
            },
        )
        for key, items in groups.items()
    }


def figure(out, cohort, rows, queries, scores):
    pos, qname, lock = (
        f"{cohort}-positions.jsonl.gz",
        f"{cohort}-queries.json",
        f"{cohort}-figure-lock.json",
    )
    pack(out, pos, rows)
    save_json(out / qname, dict(queries=queries))
    names = (pos, qname, "prediction-lock.json", "source-lock.json", "retrospective-sources.json")
    save_json(
        out / lock,
        dict(cases=[r["id"] for r in queries], files={n: trial.digest(out / n) for n in names}),
    )
    headings = {
        "fresh": "Paired 20 m tile-face guard on two new simulated sites",
        "archived-phase-release": "Phase-release tile-face decisions on four archived sites",
        "archived-compact": "Archived base compact tile-face decisions on four simulated sites",
        "measured": "Tile-face guard on measured compact roof endpoints",
    }
    notes = "Same selected coordinates and RF estimate, with one terminal paired decision."
    if cohort == "fresh":
        only = [r for r in scores if r["arm"] == "c0"]
        remaining = sum(r["false_guarded_publication"] for r in only)
        notes += f" {remaining} false regional fixes remain after the guard."
    if cohort == "measured":
        notes += " The shifted containing reattempt timed out."
    return dict(
        id=f"boundary-policy-{cohort}",
        method=trial.METHODS[0],
        scope="transfer",
        cases="sealed",
        title=headings[cohort],
        caption=notes,
        seal=lock,
        queries=qname,
        condition_labels={
            k: v for k, v in LABELS.items() if any(r["condition"] == k for r in queries)
        },
        provenance=list(names[2:]),
        series=[
            dict(
                key="candidate",
                label="Paired interior guard",
                forced_label="Guarded forced",
                file=pos,
                value=trial.METHODS[0],
            ),
            dict(
                key="stock",
                label="Original compact decision",
                file=pos,
                value=trial.METHODS[1],
                match=["input_sha256"],
            ),
        ],
    )


def score(work, out):
    primary = fresh(work, out)
    source = (
        trial.OLDER / "prediction-lock.json",
        trial.OLDER / "score-lock.json",
        trial.ROOF / "prediction-lock.json",
        SHIFTED / "measured-retry/prediction-lock.json",
        SHIFTED / "compact-secant-measured-shift-lock.json",
    )
    save_json(out / "retrospective-sources.json", {str(p): trial.digest(p) for p in source})
    cohorts = {"fresh": primary, **archived_simulations(), "measured": measured()}
    rows, visuals = [], []
    for name, (predictions, queries, tiles) in cohorts.items():
        scored = list(dispositions(name, predictions, queries, tiles))
        rows.extend(scored)
        visuals.append(figure(out, name, predictions, queries, scored))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    write(out / "scores.csv", buffer.getvalue().encode())
    save_json(out / "summary.json", tabulate(rows))
    save_json(out / "figures.json", dict(version=1, charts=visuals))
    names = (
        "prediction-lock.json",
        "scores.csv",
        "summary.json",
        "truth-after-lock.json",
        "retrospective-sources.json",
        "figures.json",
        *(f"{n}-figure-lock.json" for n in cohorts),
    )
    save_json(out / "score-lock.json", dict(files={n: trial.digest(out / n) for n in names}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--out", default=trial.OUT, type=Path)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    score(args.work.resolve(), args.out.resolve())
    if args.render:
        standard.generate(args.out / "charts", evidence=args.out)


if __name__ == "__main__":
    main()
