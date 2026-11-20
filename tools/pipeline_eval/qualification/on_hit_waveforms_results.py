"""Seal complete partner-on-hit waveform output and its two calibration arms."""

import argparse
import csv
import gzip
from collections import Counter
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distribution
from ..variants import partner_on_hit, second_on_miss
from ..variants.selective_capture import visit_pairs
from . import on_hit_waveforms as trial
from . import second_on_miss_whole_results as stages
from . import whole_band_results as measured
from .exact_wide_iq_results import detector_rows
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .screening_figures import generate
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
POS = "positions.jsonl.gz"
PLAN = trial.partner_on_hit_trial
METHODS = dict(hit=trial.METHOD, four=PLAN.fixed.FOUR, one=PLAN.one.METHOD, miss=PLAN.miss.METHOD)


def controls(lock):
    files = (
        (
            PLAN.fixed.REPORT,
            "all-figure-lock.json",
            lock["complete_four_lock_sha256"],
            "all-positions.jsonl.gz",
        ),
        (PLAN.one.REPORT, "prediction-lock.json", lock["prior_one_prediction_sha256"], POS),
        (PLAN.miss.REPORT, "prediction-lock.json", PLAN.MISS_PIN, POS),
    )
    records = {}
    for role, (folder, certificate, pin, name) in zip(("four", "one", "miss"), files, strict=True):
        proof = whole_iq.read(whole_iq.checked(folder / certificate, pin))
        matched = rows_from(whole_iq.checked(folder / name, proof["files"][name]))
        records[role] = {
            row["id"]: row
            for row in matched
            if row["id"] in lock["cases"] and row["method"] == METHODS[role]
        }
        if set(records[role]) != set(lock["cases"]):
            raise ValueError("earlier compact control differs from selected complete recordings")
    return records


def audit(stock, actual, schedule, calls, native_sha):
    expected, counts = partner_on_hit.project(stock, schedule)
    if expected != actual or sha256(encoded(expected) + b"\n").hexdigest() != native_sha:
        raise ValueError("candidate factors differ from independent exact dual-stock projection")
    by_rx, by_rf = Counter(), {}
    for (visit, primary, hit), entry, (index, lanes) in zip(
        calls, schedule, visit_pairs(stock["source"]["probes"]), strict=True
    ):
        expected_call = not second_on_miss.needs_partner(lanes[primary])
        if (
            (visit, primary) != (entry["visit"], entry["selected_receiver"])
            or type(hit) is not bool
            or hit != expected_call
            or visit != index
        ):
            raise ValueError("actual partner decision disagrees with original stock gate")
        by_rx[primary] += 1
        by_rx[1 - primary] += hit
        work = by_rf.setdefault(str(entry["rf_center_hz"]), [0, 0])
        work[primary] += 1
        work[1 - primary] += hit
    measures = counts["valid_visits"]
    hits = counts["primary_hits"]
    call_counts = dict(
        four=2 * measures, one=measures, miss=2 * measures - hits, hit=sum(by_rx.values())
    )
    admitted = dict(
        four=hits + counts["covisible_partner_hits"] + counts["partner_only_hits"],
        one=hits,
        hit=hits + counts["covisible_partner_hits"],
        miss=hits + counts["partner_only_hits"],
    )
    return dict(
        counts,
        native_sha256=native_sha,
        exact_native_bytes=True,
        receiver_calls=call_counts,
        gate_positive_probes=admitted,
        actual_receiver_calls=[by_rx[i] for i in (0, 1)],
        actual_calls_by_rf=by_rf,
        emitted_gate_candidates=sum(
            p["passed_fractional_margin_gate"] is True
            for row in actual["source"]["probes"]
            for p in row["candidates"]
        ),
    )


def seal(work):
    if (REPORT / "prediction-lock.json").exists():
        raise FileExistsError("the completed whole-IQ attempt is sealed")
    with trial.configured(work):
        lock = trial.raw_service.source(work)
    prior = controls(lock)
    output, assets, timings, results, resources = [], [], [], {}, {}
    for ident, info in lock["cases"].items():
        case = work / ident / "candidate"
        historical = [prior[r][ident] for r in ("four", "one", "miss")]
        plan = dict(lock, detectors={"candidate": lock["detectors"][ident]})
        row, clocks, native = measured.attempt(work, ident, "candidate", plan, method=trial.METHOD)
        for old in historical:
            PLAN.fixed.same_capture(row, old)
        output.extend([*historical, row])
        resources[ident] = clocks
        proof = results[ident] = dict(
            status=row["result"]["status"], raw_complete=native is not None
        )
        if native is not None:
            stock = PLAN.one.stock_document(info["stock"])
            if info["stock"]["native_sha256"] != prior["four"][ident]["native_sha256"]:
                raise ValueError(
                    "original measured dual-stock factors did not feed the exact control"
                )
            schedule = whole_iq.read(
                whole_iq.checked(Path(info["dispatch"]["path"]), info["dispatch"]["sha256"])
            )
            observed = whole_iq.read(case / "actual-dispatch.json")
            proof.update(
                audit(stock, whole_iq.read(native), schedule, observed, row["native_sha256"])
            )
            for arm_role, record in zip(
                ("four", "one", "miss", "hit"), [*historical, row], strict=True
            ):
                if (
                    record["result"]["status"] == "ok"
                    and record["result"]["metrics"]["observations"]
                    != proof["gate_positive_probes"][arm_role]
                ):
                    raise ValueError(
                        "successful solver observations did not match its native packet census"
                    )
            _, visits, logical = detector_rows(case)
            visits.sort(key=lambda x: x["visit"])
            for (visit, rx, partner), t in zip(observed, visits, strict=True):
                if visit != t["visit"]:
                    raise ValueError(
                        "native clock ledger does not match each actual conditional visit"
                    )
                timings.append(
                    dict(
                        id=ident,
                        visit=visit,
                        primary=rx,
                        calls=1 + int(partner),
                        lane=t["lane"],
                        cpu_ms=1e3 * t["cpu_s"],
                        wall_ms=1e3 * t["wall_s"],
                    )
                )
            proof["logical_native_sha256"] = logical
            path = REPORT / "native" / f"{ident}.json.gz"
            write(path, gzip.compress(native.read_bytes(), compresslevel=5, mtime=0))
            assets.append(path)
        for name in (
            "start.json",
            "raw.json",
            "end.json",
            "position.json",
            "plan.json",
            "service.json",
            "service.log",
            "service-launch.json",
            "service-supervisor.json",
            "actual-dispatch.json",
        ):
            src = case / name
            if src.is_file():
                if name == "service.log":
                    whole_iq.checked(src, clocks["service"]["log_sha256"])
                dst = REPORT / "receipts" / ident / name
                write(dst, src.read_bytes())
                assets.append(dst)
        fail = case.parent / "candidate-failure.json"
        if fail.is_file():
            dst = REPORT / "receipts" / ident / fail.name
            write(dst, fail.read_bytes())
            assets.append(dst)
    for name, value in (("parity.json", results), ("resources.json", resources)):
        save_json(REPORT / name, value)
        assets.append(REPORT / name)
    for name, data in ((POS, output), ("visit-timing.jsonl.gz", timings)):
        pack(REPORT / name, data)
        assets.append(REPORT / name)
    assets.extend(REPORT / name for name in ("source-lock.json", "PROTOCOL.md", "selection.json"))
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(lock["cases"]),
            files={str(p.relative_to(REPORT)): _sha(p) for p in assets},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def publish(out):
    receipt = sealed(REPORT, "prediction-lock.json")
    values = rows_from(REPORT / POS)
    _, refs = held_references(None, receipt["cases"])
    scores = geographic(
        [dict(row, cohort="independent confirmation") for row in values], {r["id"]: r for r in refs}
    )
    resources = whole_iq.read(REPORT / "resources.json")
    replay = rows_from(REPORT / "visit-timing.jsonl.gz")
    native = whole_iq.read(REPORT / "parity.json")
    csv_file(out / "scores.csv", scores)
    historical = PLAN.fixed.BASE / "complete-timing"
    timings = whole_iq.read(historical / "prediction-lock.json")
    path = whole_iq.checked(historical / "resources.csv", timings["files"]["resources.csv"])
    with path.open(newline="") as stream:
        old = [
            r
            for r in csv.DictReader(stream)
            if r["id"] in receipt["cases"] and r["method"] == METHODS["four"]
        ]
    save_json(out / "stock-timing.json", dict(resources_sha256=_sha(path), rows=old))
    by_case = {}
    for ident, resource in resources.items():
        records = [r for r in replay if r["id"] == ident]
        by_case[ident] = dict(
            calls=stages.stats(records),
            conditional={n: stages.stats([r for r in records if r["calls"] == n]) for n in (1, 2)},
            detector_cpu_s=sum(r["cpu_ms"] for r in records) * 1e-3,
            **{
                k: resource.get(k)
                for k in (
                    "wall_s",
                    "cpu_s",
                    "raw_s",
                    "assembly_s",
                    "position_s",
                    "max_bytes",
                    "swap_bytes",
                    "wall_to_failure_s",
                )
            },
            service_wall_s=resource["service"].get("service_wall_s"),
        )
    measures = {}
    for role, method in METHODS.items():
        measures[role] = {}
        for arm in ARMS:
            items = [r for r in scores if r["method"] == method and r["arm"] == arm]
            measures[role][arm] = dict(
                expected=len(items),
                published=sum(r["error_km"] is not None for r in items),
                within_5pct=sum(r["within_5pct"] for r in items),
                within_10pct=sum(r["within_10pct"] for r in items),
                geo=distribution([r["error_km"] for r in items]),
                rf_rms=distribution([r["conditional_rms_hz"] for r in items]),
            )
    save_json(out / "summary.json", dict(positions=measures, actual_host=by_case, native=native))
    if replay:
        csv_file(out / "timing.csv", replay)
        stages.timing_chart(replay, native, out)
        spec = whole_iq.read(out / "stage-figure.json")
        save_json(
            out / "stage-figure.json",
            dict(
                spec,
                id="on-hit-waveforms-timing",
                title="Measured detector calls when the partner runs on a primary hit",
            ),
        )
    deps = (POS, "prediction-lock.json", "scores.csv", "summary.json", "parity.json")
    save_json(
        out / "figure-lock.json",
        dict(cases=receipt["cases"], files={n: _sha(out / n) for n in deps}),
    )
    fields = (
        ("hit", "one", "Partner on primary hit"),
        ("one", "one_native_factors", "Alternating one antenna"),
        ("four", "stock", "Both stock antennas"),
        ("miss", "all_visits", "Partner on primary miss"),
    )
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="on-hit-waveforms",
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="figure-lock.json",
                    title="Partner on hit from complete waveforms to compact position",
                    caption=(
                        "Actual saved IQ on two confirmation recordings with original causal "
                        "inputs and 25 km offers. One and miss use earlier projected factors."
                    ),
                    provenance=deps[1:],
                    series=[
                        dict(
                            key=key,
                            label=label,
                            file=POS,
                            value=METHODS[role],
                            native_field="paired_capture_sha256",
                            match=PLAN.fixed.BINDINGS,
                        )
                        for role, key, label in fields
                    ],
                )
            ],
        ),
    )
    generate(out / "charts", evidence=out)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("stage", choices=("seal", "publish"))
    cli.add_argument("--work", type=local_output, default=trial.WORK)
    args = cli.parse_args()
    if args.stage == "seal":
        seal(args.work)
    else:
        publish(REPORT)
