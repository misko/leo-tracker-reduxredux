"""Compare genuine four- and five-region raw-IQ receivers on the whole scheduled roster."""

import argparse
import csv
from hashlib import sha256

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, validate_result
from . import screening_figures
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_band_results import COMMON
from .whole_pressure_trial import rows_from

SCREEN = screening_figures.REPORT
BASE = SCREEN / "latency-and-support"
REPORT = BASE / "complete-roster"
TWELVE = SCREEN / "track-recovery/wide-roster"
EIGHT = SCREEN / "arrival-and-timing/fresh-replay"
TEN = BASE / "fifth-completion"
TWO = BASE / "new-waveforms"
PINS = (
    (
        TWELVE,
        "all-figure-lock.json",
        "cc04b4499bece1da0a447cb965d5c6998a463cfdb850e5169a94194445fa24e3",
    ),
    (
        EIGHT,
        "eight-figure-lock.json",
        "7520dee62bdd2e62e910861f0aadee1f561dfc51dae36c3c19a3639cfc0adf29",
    ),
    (TEN, "source-lock.json", "dbb4d13979448f8141e713f0d904e0ea445df123affdb2be28edcece1cfd1ff6"),
    (TWO, "source-lock.json", "a2bd77f451ce6c1544ddd9c497fc7cdb495beec080d542c38a12b3675df3bea1"),
)
FOUR = "complete_four_regions"
FIVE = "complete_five_regions"
EARLY = "complete_four_first_attempt"
BINDINGS = ("paired_capture_sha256", "original_request_sha256", "catalog_sha256", "tile")
REFS = dict(authority="roof-authority.json", predictions="fresh-v5.jsonl.gz")


def frozen_roster():
    sources, groups = {}, []
    for folder, name, digest in PINS:
        doc = whole_iq.read(whole_iq.checked(folder / name, digest))
        groups.append(set(doc["cases"]))
        sources[str((folder / name).relative_to(SCREEN))] = digest
    twelve, eight, ten, two = groups
    if ten != twelve - eight or (eight | twelve) & two or list(map(len, groups)) != [12, 8, 10, 2]:
        raise ValueError("completion must cover every earlier stock-only recording and two new IDs")
    return dict(
        sources=sources,
        original_stock=sorted(twelve),
        original_pair=sorted(eight),
        fifth_completion=sorted(ten),
        fresh=sorted(two),
        all=sorted(twelve | eight | two),
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
    )


def receiver_identity(plan):
    return (
        {key: value["sha256"] for key, value in plan["detectors"].items()},
        plan["receiver_files"],
        plan["native_sources"],
        plan["memory_max"],
        plan["swap_max"],
    )


def member(folder, receipt, name):
    return whole_iq.checked(folder / name, receipt["files"][name])


def select(rows, name, cases):
    selected = {}
    for row in rows:
        if row["method"] != name:
            continue
        ident = row["id"]
        if ident in selected:
            raise ValueError(f"repeated {name} position for {ident}")
        capture = row.get("paired_capture_sha256", row.get("capture_era_native_sha256"))
        if not capture or row.get("capture_era_native_sha256", capture) != capture:
            raise ValueError(f"inconsistent capture-era input for {ident}")
        if any(not row.get(key) for key in BINDINGS[1:]):
            raise ValueError(
                f"missing original request, orbit catalogue or offered region for {ident}"
            )
        result = row["result"]
        validate_result(result)
        if result["status"] == "ok" and not row.get("native_sha256"):
            raise ValueError(
                f"successful {ident} position lacks its measured native receiver input"
            )
        if result["status"] in ("ok", "withheld") and set(result.get("arms", {})) != set(ARMS):
            raise ValueError(f"missing numerical calibration arm for {ident}")
        selected[ident] = dict(row, paired_capture_sha256=capture)
    if set(selected) != set(cases):
        raise ValueError(f"{name} must furnish a terminal result on every assigned recording")
    return selected


def same_capture(left, right):
    if any(left[key] != right[key] for key in ("id", *BINDINGS)):
        raise ValueError(
            "receivers used different original measurements, requests, tiles or catalogues"
        )


def scientific_outcome(row):
    result = row["result"]
    metrics = {k: v for k, v in result["metrics"].items() if k != "stage_s"}
    return row["native_sha256"], result["status"], result.get("reason"), result.get("arms"), metrics


def join_roster(twelve, eight, completion, fresh, groups):
    stock = select(twelve, "wide_iq_roster_primary", groups["original_stock"])
    early = select(twelve, "wide_iq_roster_original_first", groups["original_stock"])
    old_stock = select(eight, "fresh_replay_stock", groups["original_pair"])
    fifth = select(eight, "fresh_replay_fifth", groups["original_pair"])
    fifth.update(select(completion, "fifth_completion_candidate", groups["fifth_completion"]))
    fifth.update(select(fresh, "new_waveforms_fifth", groups["fresh"]))
    for ident in stock.keys() & old_stock.keys():
        same_capture(stock[ident], old_stock[ident])
        if scientific_outcome(stock[ident]) != scientific_outcome(old_stock[ident]):
            raise ValueError(f"overlapping stock outcomes disagree for {ident}")
    stock = old_stock | stock | select(fresh, "new_waveforms_stock", groups["fresh"])
    early = stock | early
    result = []
    for ident in groups["all"]:
        for method, row in ((FOUR, stock[ident]), (FIVE, fifth[ident]), (EARLY, early[ident])):
            same_capture(row, stock[ident])
            result.append(dict(row, method=method))
    return result


def verify_raw_pair(stock, evidence, candidate):
    if not evidence["complete_raw"]:
        if candidate["result"]["status"] == "ok" or candidate.get("native_sha256"):
            raise ValueError("an incomplete raw stream cannot support a completed position")
        return
    if (
        not evidence.get("native_sha256")
        or evidence["native_sha256"] != candidate.get("native_sha256")
        or any(
            not evidence.get(key) or evidence[key] != stock.get(key)
            for key in ("input_manifest_sha256", *COMMON)
        )
    ):
        raise ValueError("native measurements, capture clocks or excluded visits differ")


def stock_capture_authority(completion, wide_receipt, control_sha, candidates, raw):
    attempt_lock = whole_iq.read(member(TWELVE, wide_receipt, "prediction-lock.json"))
    attempts = whole_iq.read(member(TWELVE, attempt_lock, "attempts.json"))
    primary = {row["id"]: row for row in attempts if row["primary"]}
    for ident, case in completion["cases"].items():
        row = primary[ident]
        if (
            not row["full_raw_verified"]
            or row["detector_sha256"] != control_sha
            or row["input_manifest_sha256"] != case["clock_authority"]
            or row["capture_era_native_sha256"] != case["capture_native_sha256"]
            or row["catalog_sha256"] != case["catalog_sha256"]
            or row["original_request_sha256"] != case["request_sha256"]
            or row["tile"] != case["tile"]
        ):
            raise ValueError(
                f"historical stock run differs from the candidate waveform or request for {ident}"
            )
        verify_raw_pair(row, raw[ident], candidates[ident])


def inputs(groups):
    receipts = {}
    all_rows = {}
    for folder, receipt_name, filename in (
        (TWELVE, "all-figure-lock.json", "positions.jsonl.gz"),
        (EIGHT, "eight-figure-lock.json", "eight-positions.jsonl.gz"),
        (TEN, "prediction-lock.json", "positions.jsonl.gz"),
        (TWO, "prediction-lock.json", "positions.jsonl.gz"),
    ):
        receipt = whole_iq.read(folder / receipt_name)
        all_rows[folder] = rows_from(member(folder, receipt, filename))
        receipts[str((folder / receipt_name).relative_to(SCREEN))] = _sha(folder / receipt_name)
    eight_receipt = whole_iq.read(EIGHT / "eight-figure-lock.json")
    reference_raw = whole_iq.read(member(EIGHT, eight_receipt, "raw-prediction-lock.json"))
    original = whole_iq.read(member(EIGHT, reference_raw, "source-lock.json"))
    for folder in (TEN, TWO):
        seal = whole_iq.read(folder / "prediction-lock.json")
        plan = whole_iq.read(member(folder, seal, "source-lock.json"))
        if receiver_identity(plan) != receiver_identity(original):
            raise ValueError(
                "pooled receiver changed detector, position executable or memory boundary"
            )
        if folder == TEN:
            stock_capture_authority(
                plan,
                whole_iq.read(TWELVE / "all-figure-lock.json"),
                original["detectors"]["control"]["sha256"],
                select(all_rows[TEN], "fifth_completion_candidate", groups["fifth_completion"]),
                whole_iq.read(member(folder, seal, "raw-authority.json")),
            )
    rows = join_roster(all_rows[TWELVE], all_rows[EIGHT], all_rows[TEN], all_rows[TWO], groups)
    return rows, receipts


def write_references(out, receipts):
    authority, predictions = [], []
    for folder, seal_name in ((EIGHT, "eight-figure-lock.json"), (TWO, "all-figure-lock.json")):
        seal = whole_iq.read(folder / seal_name)
        authority.extend(whole_iq.read(member(folder, seal, REFS["authority"]))["cases"])
        predictions.extend(rows_from(member(folder, seal, REFS["predictions"])))
        receipts[str((folder / seal_name).relative_to(SCREEN))] = _sha(folder / seal_name)
    save_json(out / REFS["authority"], dict(cases=authority))
    pack(out / REFS["predictions"], predictions)
    extended = [row["id"] for row in authority]
    seal = dict(files={name: _sha(out / name) for name in REFS.values()})
    return screening_figures.new_roof_references(out, seal, REFS, extended)


def scored(rows, references):
    data = []
    for row in rows:
        case, result = references[row["id"]], row["result"]
        for arm in ARMS:
            endpoint = result.get("arms", {}).get(arm, {})
            error = distance_km(endpoint.get("latlon"), case["truth"])
            status = endpoint.get("status", result["status"])
            if status == "ok" and error is None:
                status = "withheld"
            controls = {role: case["reference"][role][arm]["error_km"] for role in ROLES}
            before = controls["baseline"]
            eligible = error is not None and before is not None
            data.append(
                dict(
                    id=row["id"],
                    method=row["method"],
                    arm=arm,
                    status=status,
                    reason=endpoint.get("reason", result.get("reason")),
                    error_km=error,
                    forced_error_km=distance_km(endpoint.get("forced_latlon"), case["truth"]),
                    within_5pct=eligible and error <= 1.05 * before,
                    within_10pct=eligible and error <= 1.10 * before,
                    rf_rms_hz=endpoint.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    **{f"{k}_km": value for k, value in controls.items()},
                )
            )
    return data


def summary_row(data, ids, cohort, arm, method):
    is_reference = method in ROLES
    rows = [r for r in data if r["method"] == (FOUR if is_reference else method)]
    errors = {r["id"]: r[f"{method}_km" if is_reference else "error_km"] for r in rows}
    if set(errors) != set(ids) or len(rows) != len(ids):
        raise ValueError("each scheduled recording must be counted once per arm")
    counts = [
        sum(
            errors[r["id"]] is not None
            and r["baseline_km"] is not None
            and errors[r["id"]] <= limit * r["baseline_km"]
            for r in rows
        )
        for limit in (1.05, 1.10)
    ]
    dist = distribution(errors.values())
    return dict(
        cohort=cohort,
        arm=arm,
        method=method,
        scheduled=len(ids),
        published=dist["n"],
        within_5pct=counts[0],
        within_10pct=counts[1],
        median_km=dist["p50"],
        p95_km=dist["p95"],
    )


def statistics(scores, groups):
    output, differences = [], []
    for label in ("all", "original_pair", "fifth_completion", "fresh"):
        ids = set(groups[label])
        for arm in ARMS:
            data = [r for r in scores if r["id"] in ids and r["arm"] == arm]
            output.extend(
                summary_row(data, ids, label, arm, m) for m in (*ROLES, FOUR, FIVE, EARLY)
            )
            stock = {r["id"]: r["error_km"] for r in data if r["method"] == FOUR}
            for row in data:
                if row["method"] != FIVE:
                    continue
                before, after = stock[row["id"]], row["error_km"]
                change = None if before is None or after is None else 1000 * (after - before)
                differences.append(
                    dict(
                        cohort=label,
                        arm=arm,
                        id=row["id"],
                        four_km=before,
                        five_km=after,
                        five_minus_four_m=change,
                    )
                )
    return output, differences


def verify_timed_positions(rows, timings):
    expected = {(r["id"], r["method"]): r for r in rows}
    seen = set()
    for timing in timings:
        key = timing["id"], timing["method"]
        if key not in expected or key in seen:
            raise ValueError("unexpected or repeated timed receiver run")
        row = expected[key]
        outcome_sha256 = sha256(encoded(scientific_outcome(row))).hexdigest()
        if (
            timing["request_sha256"] != row["original_request_sha256"]
            or timing["capture_sha256"] != row["paired_capture_sha256"]
            or timing["catalog_sha256"] != row["catalog_sha256"]
            or timing["scientific_outcome_sha256"] != outcome_sha256
        ):
            raise ValueError("timing differs from the scored input and scientific outcome")
        seen.add(key)
    if seen != set(expected):
        raise ValueError("missing measured timing or terminal service receipt")


def export_timing(out, rows, receipts):
    folder = BASE / "complete-timing"
    path = folder / "prediction-lock.json"
    seal = whole_iq.read(path)
    if set(seal["cases"]) != {r["id"] for r in rows}:
        raise ValueError("timed roster differs from the geographic roster")
    timings = []
    names = {
        "resources.csv": "runtime.csv",
        "first-attempt.csv": "runtime-first-attempt.csv",
        "summary.json": "runtime-summary.json",
    }
    paths = {name: member(folder, seal, name) for name in names}
    for name in ("resources.csv", "first-attempt.csv"):
        with paths[name].open(newline="") as stream:
            timings.extend(csv.DictReader(stream))
    verify_timed_positions(rows, timings)
    for name, target in names.items():
        write(out / target, paths[name].read_bytes())
    receipts[str(path.relative_to(SCREEN))] = _sha(path)


def charts(out, rows, groups):
    specs = []
    for key, title, group, second in (
        ("all", "Four and five GLRT timing regions on twenty complete recordings", "all", FIVE),
        (
            "ten",
            "Adding the extra timing region on all ten previously stock-only recordings",
            "fifth_completion",
            FIVE,
        ),
        (
            "first",
            "Stock coverage using the earlier twelve-recording first-attempt ledger",
            "all",
            EARLY,
        ),
    ):
        cases = groups[group]
        name = f"{key}-positions.jsonl.gz"
        pack(out / name, [r for r in rows if r["id"] in cases and r["method"] in (FOUR, second)])
        files = ["roster.json", "inputs.json", "scores.csv", "summary.csv", "paired-errors.csv"]
        chart_id = f"complete-detector-roster-{key}"
        spec = dict(
            id=chart_id,
            method=second,
            scope="roof",
            cases="sealed",
            title=title,
            caption=(
                "Same surveyed roof, same recordings, original four v5 reference options. "
                + (
                    "Published first-launch results replace stock on the earlier twelve only."
                    if second == EARLY
                    else "Every scheduled complete-IQ receiver run counts."
                )
            ),
            seal=f"{key}-figure-lock.json",
            provenance=files,
            series=[
                dict(
                    key=role,
                    file=name,
                    value=method,
                    label=label,
                    native_field=BINDINGS[0],
                    match=list(BINDINGS),
                )
                for role, method, label in (
                    (
                        "one",
                        second,
                        "Five timing regions"
                        if second == FIVE
                        else "Stock with historical first attempts",
                    ),
                    ("stock", FOUR, "Four timing regions"),
                )
            ],
        )
        if group == "all":
            spec["roof_references"] = REFS
            files.extend(REFS.values())
        save_json(
            out / spec["seal"], dict(cases=cases, files={p: _sha(out / p) for p in [name, *files]})
        )
        specs.append(spec)
    save_json(out / "figures.json", dict(version=2, charts=specs))
    screening_figures.generate(out / "charts", evidence=out)


def run(out, freeze_only=False):
    roster = frozen_roster()
    if freeze_only:
        save_json(out / "roster.json", roster)
        return
    if whole_iq.read(REPORT / "roster.json") != roster:
        raise ValueError("upstream selection changed after the twenty recordings were frozen")
    rows, receipts = inputs(roster)
    extended = write_references(out, receipts)
    _, published = held_references(None, sorted(set(roster["all"]) - extended.keys()))
    scores = scored(rows, {r["id"]: r for r in published} | extended)
    summary, pairs = statistics(scores, roster)
    export_timing(out, rows, receipts)
    save_json(out / "roster.json", roster)
    save_json(out / "inputs.json", receipts)
    csv_file(out / "scores.csv", scores)
    csv_file(out / "summary.csv", summary)
    csv_file(out / "paired-errors.csv", pairs)
    charts(out, rows, roster)
    return summary


def show(summary, out):
    print("Calibration   Receiver              Fixes   Within +10%  Median km    P95 km")
    names = {
        "baseline": "v5 no repair",
        "selective-gap": "v5 selective gap",
        "omitted-track-one": "v5 one omitted",
        "omitted-tracks": "v5 two omitted",
        FOUR: "Four regions",
        FIVE: "Five regions",
    }
    for row in summary:
        if row["cohort"] != "all" or row["method"] not in names:
            continue
        fixes = f"{row['published']}/{row['scheduled']}"
        counts = f"{row['within_10pct']}/{row['scheduled']}"
        median, tail = (
            f"{row[key]:.3f}" if row[key] is not None else "—" for key in ("median_km", "p95_km")
        )
        print(
            f"{row['arm']:13s} {names[row['method']]:18s} {fixes:>5s} {counts:>12s} "
            f"{median:>10s} {tail:>9s}"
        )
    cost = whole_iq.read(out / "runtime-summary.json")["groups"]["all"]
    for method in (FOUR, FIVE):
        measured = cost[method]
        print(
            f"{names[method]} took {measured['median_worker_s']:.1f} s median through position, "
            f"{measured['detector_wall_within_20']}/{measured['detector_calls']} "
            "complete detector calls within 20 ms"
        )
    print(f"Per-recording results and paired charts in {out}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--freeze", action="store_true", help="Write the prespecified recording roster only"
    )
    cli.add_argument("--out", type=local_output, default=REPORT)
    args = cli.parse_args()
    run(args.out, args.freeze)
