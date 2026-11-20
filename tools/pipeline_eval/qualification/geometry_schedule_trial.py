"""Freeze a geometry-led slot schedule before reading original donor output."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean
from time import perf_counter, process_time
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from ..variants import geometry_schedule as model
from . import adaptive_visits_trial as base
from .full_v5_check import _sha
from .phase_support_results import pack

REPORT = base.fixed.SCREEN / "original-schedule/geometry-schedule"
QUANTILES = (0.50, 0.75, 0.90)
MODES = ("geometry", "hash")


def snapshot(request, first):
    eligible = [k for k in request["causal_snapshots"] if int(k.split("-", 1)[0]) <= first]
    if not eligible:
        raise ValueError("the request has no pre-capture TLE snapshot")
    name = max(eligible, key=lambda k: int(k.split("-", 1)[0]))
    digest = request["causal_snapshots"][name]
    handle = Path(request["job"]["tle_root"]) / "archive" / "space-track" / name
    return whole_iq.checked(handle, digest), int(name.split("-", 1)[0])


def prepare(ident, archives, extensions):
    _, request = base.roster.bind(ident, extensions)
    if request["job"]["evaluation_reference"] is not None:
        raise ValueError("geometric selection needs a truth-free offer")
    fast = base.roster.stock_document(archives[ident])
    first = fast["clock_anchor"]["after"]["realtime_ns"]
    handle, date = snapshot(request, first)
    start, cpu = perf_counter(), process_time()
    bank = model.ephemeris(handle.read_text(), first, request["job"]["search_center"])
    prep_cpu, prep_wall = process_time() - cpu, perf_counter() - start
    features, forecasts, work = model.predict(fast, bank, QUANTILES)
    work.update(
        orbit_prepare_cpu_s=prep_cpu,
        orbit_prepare_wall_s=prep_wall,
        total_selector_cpu_s=process_time() - cpu,
        total_selector_wall_s=perf_counter() - start,
        snapshot_sha256=_sha(handle),
        snapshot_start_utc_ns=date,
        capture_start_utc_ns=first,
        visible_satellites=len(bank.satellites),
        offer=request["job"]["search_center"],
    )
    return fast, features, forecasts, work


def choices(fast, features, index):
    rows = [dict(row, score=float(row["eligible"][index])) for row in features]
    result = base.selections(fast, 1.0, rows)
    return {"geometry": result["novel"], "hash": result["hash"]}


def contrast(fast, features, forecasts, index):
    selected = choices(fast, features, index)
    by_mode = {key: model.check_selected(fast, forecasts, rows) for key, rows in selected.items()}
    return {k: mean(r["gauge"] for r in rows) for k, rows in by_mode.items()}


def stage(work, cpus):
    if (REPORT / "source-lock.json").exists():
        raise FileExistsError("the geometry-directed held cohort is already staged")
    prior = whole_iq.read(base.REPORT / "source-lock.json")
    groups, archives, bindings, extensions, release = base.roster.inventory()
    endpoint = base.prior.REPORT / "endpoint-lock.json"
    authority = whole_iq.read(whole_iq.checked(endpoint, base.PRIOR_ENDPOINT_SHA))
    inventory = whole_iq.read(base.fixed.member(base.prior.REPORT, authority, "source-lock.json"))
    held = base.select_holdout(inventory["cases"])
    if (
        held != sorted(prior["cases"])
        or release != prior["release"]
        or set(groups["all"]) != inventory["cases"].keys()
    ):
        raise ValueError("earlier position control roster or compact release changed")
    work.mkdir(parents=True, exist_ok=False)
    dev = {ident: prepare(ident, archives, extensions) for ident in base.DEVELOPMENT}
    trials = []
    for index, quantile in enumerate(QUANTILES):
        scores = {ident: contrast(f, a, b, index) for ident, (f, a, b, _) in dev.items()}
        trials.append(
            dict(
                quantile=quantile,
                scores=scores,
                gain_hz=mean(r["geometry"] - r["hash"] for r in scores.values()),
            )
        )
    del dev
    selected = max(trials, key=lambda q: (q["gain_hz"], q["quantile"]))
    index = QUANTILES.index(selected["quantile"])
    rule = REPORT / "rule-lock.json"
    files = (Path(__file__), Path(model.__file__), REPORT / "PROTOCOL.md")
    save_json(
        rule,
        dict(
            development=base.DEVELOPMENT,
            held=held,
            chosen=selected,
            trials=trials,
            files={str(p.resolve()): _sha(p) for p in files},
        ),
    )
    print("Frozen", selected["quantile"], held, flush=True)
    jobs, cases = [], {}
    for i, ident in enumerate(held):
        fast, features, forecasts, resources = prepare(ident, archives, extensions)
        slots = choices(fast, features, index)
        slot_lock = REPORT / "slots" / f"{ident}.json"
        save_json(slot_lock, slots)
        checks = {mode: model.check_selected(fast, forecasts, slots[mode]) for mode in MODES}
        case, request, _, repeated, original, _ = base.paired.bind(
            ident, archives, bindings, extensions
        )
        if fast["source"] != repeated["source"]:
            raise ValueError("held selection used different fast packets")
        del repeated
        manifest = fast["source"]["input_manifest_sha256"]
        if manifest != inventory["cases"][ident]["manifest"]:
            raise ValueError("the archive full-control physical manifest changed")
        summary = dict(
            manifest=manifest,
            fast_sha256=archives[ident]["native_sha256"],
            valid_visits=fast["provenance"]["processed_windows"],
            eligible_visits=len(features),
            selector_cpu_ms=resources["total_selector_cpu_s"] * 1000,
            selector=resources,
            slots_sha256=_sha(slot_lock),
            **bindings[ident],
        )
        for offset, mode in enumerate(MODES):
            probes, witness = model.visits.project(fast, original, checks[mode])
            lineage = REPORT / "lineage" / f"{ident}-{mode}.jsonl.gz"
            pack(lineage, witness)
            witness_hash = _sha(lineage)
            derived = whole_iq.recording.digest(
                ["geometry-schedule/v1", mode, ident, _sha(rule), witness_hash]
            )
            doc = dict(
                fast,
                source=dict(fast["source"], probes=probes, analysis_manifest_sha256=derived),
                provenance=dict(fast["provenance"], run_id="geometry-schedule-" + derived[7:31]),
            )
            doc["provenance"].pop("detector_sha256")
            cpu = cpus[(i + offset) % len(cpus)]
            attempt = base.paired.prepare(
                work,
                ident,
                case,
                request,
                encoded(doc) + b"\n",
                bindings[ident],
                release,
                mode,
                cpu=cpu,
            )
            jobs.append(
                dict(attempt, method=f"geometry_schedule_{mode}", witness_sha256=witness_hash)
            )
            summary[mode] = dict(
                base.summarize(witness),
                witness_sha256=witness_hash,
                supported=sum(q["supported"] for q in checks[mode]),
                mean_gauge_hz=mean(q["gauge"] for q in checks[mode]),
            )
        cases[ident] = summary
        print(
            ident,
            [
                (
                    m,
                    summary[m]["calls"],
                    summary[m]["supported"],
                    round(summary[m]["mean_gauge_hz"], 3),
                )
                for m in MODES
            ],
            resources,
            flush=True,
        )
    save_json(
        REPORT / "source-lock.json",
        dict(
            cases=cases,
            jobs=jobs,
            release=release,
            cpus=cpus,
            limit_s=base.LIMIT,
            rule_lock_sha256=_sha(rule),
            prior_endpoint_sha256=base.PRIOR_ENDPOINT_SHA,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
        ),
    )
    save_json(work / "source-lock.json", dict(sha256=_sha(REPORT / "source-lock.json")))


def run(work):
    source = whole_iq.read(
        whole_iq.checked(
            REPORT / "source-lock.json", whole_iq.read(work / "source-lock.json")["sha256"]
        )
    )
    frozen = whole_iq.read(whole_iq.checked(REPORT / "rule-lock.json", source["rule_lock_sha256"]))
    for name, digest in frozen["files"].items():
        whole_iq.checked(Path(name), digest)
    base.roster.check_release(source["release"])

    def lane(cpu):
        for attempt in source["jobs"]:
            if attempt["cpu"] == cpu:
                base.compact.service(work, attempt)

    with (
        patch.object(base.compact, "LIMIT", source["limit_s"]),
        ThreadPoolExecutor(max_workers=len(source["cpus"])) as pool,
    ):
        list(pool.map(lane, source["cpus"]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("stage", "run"))
    cli.add_argument("--work", type=local_output, required=True)
    cli.add_argument("--cpus", type=int, nargs="+", default=(22, 23))
    a = cli.parse_args()
    if a.action == "stage":
        if len(set(a.cpus)) != len(a.cpus) or not set(a.cpus) <= {22, 23}:
            cli.error("use the reserved geometry CPUs")
        stage(a.work, tuple(a.cpus))
    else:
        run(a.work)
