"""Publish real conditional-antenna calls and positions on matched saved recordings."""

import argparse
import csv
import gzip
import io
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distribution
from ..variants import second_on_miss
from ..variants.selective_capture import same_support, visit_pairs
from . import one_lane_whole_results as baseline
from . import scout_stage_figures as plot
from . import second_on_miss_whole as trial
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
MATCH = ("paired_capture_sha256", "original_request_sha256", "catalog_sha256", "tile")
METHODS = {"four": trial.prior.STOCK, "one": trial.prior.METHOD, "candidate": trial.METHOD}


def audit(control, one, actual, rf_centers, seen):
    expected, decisions = second_on_miss.project(control, rf_centers)
    if expected != actual:
        raise ValueError(
            "independent dual-stock projection differs from actual conditional native bytes"
        )
    dispatch = [[d["visit"], d["primary_receiver"], d["partner_required"]] for d in decisions]
    if dispatch != seen:
        raise ValueError("actual whole-IQ native call decisions differ from independent projection")
    tally = Counter()
    receivers = Counter()
    same_support(control, one)
    ordered = [visit_pairs(doc["source"]["probes"]) for doc in (control, one, actual)]
    for d, (_, original), (_, one_pair), (_, acquired) in zip(decisions, *ordered, strict=True):
        primary = d["primary_receiver"]
        tally["valid_visits"] += 1
        partner = d["partner_required"]
        receivers[primary] += 1
        receivers[1 - primary] += partner
        tally["partner_calls"] += partner
        tally["single_calls"] += not partner
        if one_pair[primary] != acquired[primary]:
            raise ValueError("one-lane parent differs on a measured primary physical row")
        if not partner and one_pair != acquired:
            raise ValueError("a positive primary visit changed its always-one observation rows")
        for role, probes in zip(
            ("four", "one", "candidate"), (original, one_pair, acquired), strict=True
        ):
            tally[f"{role}_positive_probes"] += sum(
                not second_on_miss.needs_partner(p) for p in probes
            )
            tally[f"{role}_gate_candidates"] += sum(
                c["passed_fractional_margin_gate"] is True for p in probes for c in p["candidates"]
            )
        tally["partner_positive_rescues"] += partner and not second_on_miss.needs_partner(
            acquired[1 - primary]
        )
    return dict(
        tally,
        receiver_calls=[receivers[k] for k in (0, 1)],
        physical_receiver_analyses=sum(receivers.values()),
        original_invalid=expected["provenance"]["invalid_capture"],
        projected_native_sha256=sha256(
            (whole_iq.recording.encoded(expected) + "\n").encode()
        ).hexdigest(),
    )


def seal(work):
    if (REPORT / "prediction-lock.json").exists():
        raise FileExistsError("already sealed raw and position attempts")
    lock = trial.source(work)
    source = trial.prior.REPORT
    old = sealed(source, "prediction-lock.json", lock["prior_one_receipt_sha256"])
    presentation = sealed(source, "score-lock.json")
    existing = rows_from(source / POS)
    with (source / "deadlines.csv").open(newline="") as stream:
        old_clocks = list(csv.DictReader(stream))
    older_summary = {
        (row["id"], "four" if row["role"] == "control" else "one"): row for row in old_clocks
    }
    pool, resources, stages, audit_rows, assets = [], {}, [], {}, []
    for ident, frozen in lock["cases"].items():
        old_rows = {
            role: next(r for r in existing if r["id"] == ident and r["method"] == METHODS[role])
            for role in ("four", "one")
        }
        plan = dict(lock, detectors={"candidate": lock["detectors"][ident]})
        row, details, native = measured.attempt(work, ident, "candidate", plan, method=trial.METHOD)
        if any(row[k] != prior[k] for prior in old_rows.values() for k in MATCH):
            raise ValueError("actual second-on-miss used a different input or causal offer")
        resources[ident] = dict(
            candidate=details,
            four=older_summary[ident, "four"],
            one=older_summary[ident, "one"],
        )
        pool.extend([*old_rows.values(), row])
        existing_run = work / ident / "candidate"
        kept = REPORT / "receipts" / ident
        result = audit_rows[ident] = dict(
            raw_complete=native is not None, status=row["result"]["status"]
        )
        if native is not None:
            always_one = f"native/{ident}.json.gz"
            one_bytes = gzip.decompress(
                whole_iq.checked(source / always_one, old["files"][always_one]).read_bytes()
            )
            if sha256(one_bytes).hexdigest() != old_rows["one"]["native_sha256"]:
                raise ValueError("whole always-one bytes differ from its position authority")
            original = baseline.control_source(frozen["control"])
            mapped, _, clock = trial.prior.parent.tune_plan(frozen)
            if clock != frozen["clock_authority"]:
                raise ValueError("physical RF dispatch changed from its original capture clock")
            seen = whole_iq.read(existing_run / "actual-dispatch.json")
            result.update(
                audit(original, json.loads(one_bytes), whole_iq.read(native), mapped, seen)
            )
            if result["projected_native_sha256"] != row["native_sha256"]:
                raise ValueError("serialized native output differs from the policy projection")
            result["actual_native_sha256"] = row["native_sha256"]
            result["same_native_bytes"] = True
            _, elapsed, logical = detector_rows(existing_run)
            ordered = sorted(elapsed, key=lambda x: x["visit"])
            for (visit, rx, used_partner), timing in zip(seen, ordered, strict=True):
                if visit != timing["visit"]:
                    raise ValueError("detector clock and conditional native call do not align")
                stages.append(
                    dict(
                        id=ident,
                        visit=visit,
                        primary=rx,
                        calls=1 + int(used_partner),
                        cpu_ms=1e3 * timing["cpu_s"],
                        wall_ms=1e3 * timing["wall_s"],
                        lane=timing["lane"],
                    )
                )
            result["logical_native_sha256"] = logical
            write(REPORT / always_one, gzip.compress(native.read_bytes(), compresslevel=5, mtime=0))
            assets.append(always_one)
        for name in (
            "plan.json",
            "start.json",
            "raw.json",
            "end.json",
            "actual-dispatch.json",
            "service.json",
            "service-launch.json",
            "service.log",
            "service-supervisor.json",
        ):
            path = existing_run / name
            if not path.is_file():
                continue
            if name == "service.log":
                whole_iq.checked(path, details["service"]["log_sha256"])
            target = kept / name
            write(target, path.read_bytes())
            assets.append(str(target.relative_to(REPORT)))
        failed = existing_run.parent / "candidate-failure.json"
        if failed.is_file():
            target = kept / failed.name
            write(target, failed.read_bytes())
            assets.append(str(target.relative_to(REPORT)))
    pack(REPORT / POS, pool)
    pack(REPORT / "visit-timing.jsonl.gz", stages)
    save_json(REPORT / "resources.json", resources)
    save_json(REPORT / "parity.json", audit_rows)
    assets.extend(
        (
            POS,
            "visit-timing.jsonl.gz",
            "resources.json",
            "parity.json",
            "preflight.json",
            "source-lock.json",
            "PROTOCOL.md",
        )
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(lock["cases"]),
            files={n: _sha(REPORT / n) for n in assets},
            publisher_sha256=_sha(Path(__file__)),
            prior_position_sha256=old["files"][POS],
            prior_timing_sha256=presentation["files"]["deadlines.csv"],
        ),
    )


def stats(rows):
    return {
        k: dict(distribution(v), within_20=sum(x <= 20 for x in v))
        for k in ("wall_ms", "cpu_ms")
        if (v := [r[k] for r in rows])
    }


def timing_chart(samples, audit_rows, out):
    cases = list(audit_rows)
    groups = {
        ident: {
            calls: [r for r in samples if r["id"] == ident and r["calls"] == calls]
            for calls in (1, 2)
        }
        for ident in cases
    }
    scoped = [
        (ident, calls, stats(items))
        for ident, arms in groups.items()
        for calls, items in arms.items()
        if items
    ]
    figure, axes = plot.canvas(
        "One or two native antenna calls after the primary margin gate",
        "Complete detector calls on the same recorded RF schedules",
        "Both paths include CI16 staging and physical row projection. The position solver "
        "receives actual remeasured packets. These host measurements include observed load.",
    )
    labels = [
        f"{ident} · {count} {'call' if count == 1 else 'calls'}" for ident, count, _ in scoped
    ]
    for axis, key in zip(axes, ("cpu_ms", "wall_ms"), strict=True):
        plot.paired(
            axis,
            labels,
            [(entry[key]["p50"], entry[key]["p95"]) for _, _, entry in scoped],
            title=f"Observed detector {key.split('_')[0].upper()}",
            xlabel="Host milliseconds",
            fmt=".2f",
        )
    plot.key(figure, "Median", "95th percentile")
    for ext in ("png", "pdf"):
        fd = io.BytesIO()
        opts = {"dpi": 165} if ext == "png" else {"metadata": {"CreationDate": None}}
        figure.savefig(fd, format=ext, facecolor="white", **opts)
        write(out / f"timing.{ext}", fd.getvalue())
    plot.plt.close(figure)
    artifacts = ("timing.png", "timing.pdf", "timing.csv", "prediction-lock.json")
    save_json(out / "timing-lock.json", dict(files={name: _sha(out / name) for name in artifacts}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="second-on-miss-whole-timing",
            title="Measured whole-replay one- and two-antenna detector calls",
            sample=f"{len(samples):,} actual detector visits "
            f"across {len({r['id'] for r in samples})} recordings",
            boundary="One or two detector calls including CI16 staging and fractional routing",
            note="The native gate alone determines whether the second antenna runs. "
            "Timing is measured on saved IQ.",
            seal="timing-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="timing.csv",
        ),
    )


def publish():
    receipt = sealed(REPORT, "prediction-lock.json")
    resources = whole_iq.read(REPORT / "resources.json")
    audits = whole_iq.read(REPORT / "parity.json")
    samples = rows_from(REPORT / "visit-timing.jsonl.gz")
    rows = rows_from(REPORT / POS)
    _, reference = held_references(None, receipt["cases"])
    scores = geographic(rows, {p["id"]: p for p in reference})
    csv_file(REPORT / "scores.csv", scores)
    timings = {}
    for ident, historical in resources.items():
        group = [r for r in samples if r["id"] == ident]
        detail = historical["candidate"]
        timings[ident] = dict(
            complete=stats(group),
            by_native_calls={n: stats([r for r in group if r["calls"] == n]) for n in (1, 2)},
            detector_cpu_s=sum(r["cpu_ms"] for r in group) / 1e3,
            **{
                key: detail.get(key)
                for key in (
                    "wall_s",
                    "cpu_s",
                    "raw_s",
                    "assembly_s",
                    "position_s",
                    "max_bytes",
                    "swap_bytes",
                )
            },
            service_wall_s=detail["service"].get("service_wall_s"),
        )
    counts = {
        role: {
            arm: dict(
                attempted=len(panel),
                published=sum(r["error_km"] is not None for r in panel),
                within_5pct=sum(r["within_5pct"] for r in panel),
                within_10pct=sum(r["within_10pct"] for r in panel),
                position_km=distribution([r["error_km"] for r in panel]),
                rf_rms_hz=distribution([r["conditional_rms_hz"] for r in panel]),
            )
            for arm in ARMS
            if (panel := [r for r in scores if r["method"] == method and r["arm"] == arm])
        }
        for role, method in METHODS.items()
    }
    save_json(REPORT / "summary.json", dict(arms=counts, native=audits, timings=timings))
    if samples:
        csv_file(REPORT / "timing.csv", samples)
        timing_chart(samples, audits, REPORT)
    products = (POS, "scores.csv", "summary.json", "prediction-lock.json", "parity.json")
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=receipt["cases"], files={n: _sha(REPORT / n) for n in products}),
    )
    arms = (
        ("candidate", "one", "Second antenna on primary miss"),
        ("four", "stock", "Archived dual stock"),
        ("one", "one_native_factors", "Archived alternating one antenna"),
    )
    save_json(
        REPORT / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="second-on-miss-whole",
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="figure-lock.json",
                    title="Second antenna after a primary miss on two complete saved recordings",
                    caption=(
                        "Actual saved IQ, original 25 km offers and both calibration settings. "
                        "The original strict pilot gate decides whether the second antenna runs."
                    ),
                    provenance=products[1:],
                    series=[
                        dict(
                            key=key,
                            label=label,
                            file=POS,
                            value=METHODS[role],
                            native_field="paired_capture_sha256",
                            match=MATCH,
                        )
                        for role, key, label in arms
                    ],
                )
            ],
        ),
    )
    generate(REPORT / "charts", evidence=REPORT)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("seal", "publish"))
    cli.add_argument("--work", default=trial.WORK, type=local_output)
    args = cli.parse_args()
    if args.phase == "seal":
        seal(args.work)
    else:
        publish()
