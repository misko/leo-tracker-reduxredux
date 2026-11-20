"""Bind the fixed quarter-miss projection and run the complete prespecified panel."""

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import one_lane_schedule, partner_on_hit, quarter_miss
from . import antenna_fresh_full as fresh
from . import fresh_replay, partner_holdout
from . import partner_on_hit_trial as trial
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .phase_support_results import pack
from .staggered_reconstruction_trial import tune_plan
from .whole_pressure_trial import rows_from

REPORT = partner_holdout.REPORT.with_name("quarter-miss")
METHOD = "quarter_miss"
PRIMARY = trial.one.METHOD
PINS = (14, 15, 18, 19)
POLICY_PIN = "bcf1694986518ca081e6c266f6a800cca84616b663232f04280678a7bb28ff58"
read = whole_iq.read


def lock_policy():
    lock = read(whole_iq.checked(REPORT / "policy-lock.json", POLICY_PIN))
    for name, digest in lock["source_sha256"].items():
        whole_iq.checked(ROOT / name, digest)
    if lock["policy"] != quarter_miss.POLICY:
        raise ValueError("prospective numerical policy changed")
    return lock


def control_rows(folder, lock, filename):
    return rows_from(trial.fixed.member(folder, lock, filename))


def authority():
    lock = lock_policy()
    earlier = sealed(partner_holdout.REPORT, "prediction-lock.json")
    incoming = sealed(fresh.REPORT, "prediction-lock.json")
    if lock["held14"] != earlier["holdout"] or lock["prospective2"] != incoming["cases"]:
        raise ValueError("recordings differ from the prespecified disjoint cohorts")
    fresh_plan = read(trial.fixed.member(fresh.REPORT, incoming, "source-lock.json"))
    _, _, _, stock, audits, release, extensions, _, _ = partner_holdout.authority()
    if any(fresh_plan[k] != v for k, v in release.items()):
        raise ValueError("new and old stock factors used a different position receiver")
    earlier_rows = control_rows(partner_holdout.REPORT, earlier, "positions.jsonl.gz")
    earlier_hit = trial.fixed.select(earlier_rows, trial.METHOD, earlier["cases"])
    history = read(trial.fixed.member(partner_holdout.REPORT, earlier, "packet-audit.json"))
    measured = control_rows(fresh.REPORT, incoming, "positions.jsonl.gz")
    new = {
        name: trial.fixed.select(measured, name, incoming["cases"])
        for name in (fresh.STOCK, fresh.METHOD)
    }
    return lock, incoming, fresh_plan, stock, audits, release, extensions, earlier_hit, history, new


def prepare_held(ident, stock, audits, extensions, old_hit, history):
    proof = history[ident]
    before = audits[PRIMARY][ident]
    document = trial.one.stock_document(proof["archive"])
    native_sha = stock[trial.fixed.FOUR][ident]["native_sha256"]
    if (
        proof["archive"]["native_sha256"] != native_sha
        or document["source"]["input_manifest_sha256"] != proof["clock_authority"]
    ):
        raise ValueError("stock native array or acquisition-clock authority changed")
    centers = {(r["channel"], r["edge"]): r["rf_center_hz"] for r in before["rf_mapping"]}
    with partner_holdout.binding_context(ident, extensions):
        case, request = whole_iq.binding(ident)
    return case, request, stock[trial.fixed.FOUR][ident], old_hit[ident], document, centers, proof


def prepare_fresh(ident, receipt, plan, measured):
    stock, hit = (measured[k][ident] for k in (fresh.STOCK, fresh.METHOD))
    trial.fixed.same_capture(stock, hit)
    with fresh_replay.patched_case(plan):
        case, request = whole_iq.binding(ident)
    centers, _, clocks = tune_plan(case)
    filename = f"native/control/{ident}.json.gz"
    path = trial.fixed.member(fresh.REPORT, receipt, filename)
    canonical = gzip.decompress(path.read_bytes())
    document = json.loads(canonical)
    if (
        sha256(canonical).hexdigest() != stock["native_sha256"]
        or document["source"]["input_manifest_sha256"] != clocks
        or clocks != plan["cases"][ident]["clock_authority"]
    ):
        raise ValueError("fresh stock factors do not match their recorded waveform and solver")
    dispatch = f"dispatch/{ident}/dispatch.json"
    path = trial.fixed.member(fresh.REPORT, receipt, dispatch)
    proof = dict(
        archive=dict(
            path=str(fresh.REPORT / filename),
            file_sha256=receipt["files"][filename],
            native_sha256=stock["native_sha256"],
        ),
        clock_authority=clocks,
        selected_primary_sha256=sha256(encoded(read(path))).hexdigest(),
    )
    return case, request, stock, hit, document, centers, proof


def job(work, case, request, baseline, release, cpu, method, condition, doc, positive):
    jobdir = work / case["id"] / condition
    native, target = jobdir / "recording/native.json", jobdir / "recording/request.json"
    write(native, encoded(doc) + b"\n")
    key = whole_iq.recording.bind_request(case, native, target)["native_sha256"]
    trial.verify_request(read(target), request, native_path=native, native_sha256=key)
    save_json(jobdir / "plan.json", dict(receiver=release["receiver"]))
    save_json(jobdir / "raw.json", dict(native_sha256=key, request_sha256=_sha(target)))
    return dict(
        id=case["id"],
        cpu=cpu,
        method=method,
        condition=condition,
        mode="matched-tile",
        stock_native_sha256=baseline["native_sha256"],
        native_sha256=_sha(native),
        prepared_request_sha256=_sha(target),
        positive_probes=positive,
        **{k: baseline[k] for k in trial.fixed.BINDINGS},
    )


def prepare(work, payload, cpu, fresh_cpu, release):
    case, request, stock, hit, document, centers, prior = payload
    ident = case["id"]
    if tuple(stock[k] for k in trial.fixed.BINDINGS) != (
        case["native"]["sha256"],
        case["request"]["sha256"],
        case["catalog"]["sha256"],
        case["regions"][0],
    ):
        raise ValueError(f"{ident} changed truth-free localization input")
    trial.fixed.same_capture(stock, hit)
    only, schedule = one_lane_schedule.project(document, centers)
    projected, decisions, counts = quarter_miss.project(document, schedule)
    reference, _ = partner_on_hit.project(document, schedule)
    only_sha = sha256(encoded(only) + b"\n").hexdigest()
    if (
        sha256(encoded(schedule)).hexdigest() != prior["selected_primary_sha256"]
        or sha256(encoded(reference) + b"\n").hexdigest() != hit["native_sha256"]
        or prior.get("one_lane_native_sha256", only_sha) != only_sha
    ):
        raise ValueError(f"{ident} changed packet contents or the already measured schedule")
    p, h, m, audits, rescued, visits = (
        counts[k]
        for k in (
            "primary_hits",
            "covisible_partner_hits",
            "partner_only_hits",
            "audited_misses",
            "audited_partner_hits",
            "valid_visits",
        )
    )
    pos = {PRIMARY: p, trial.METHOD: p + h, METHOD: p + h + rescued, trial.fixed.FOUR: p + h + m}
    if (
        stock["result"]["metrics"].get("observations") != pos[trial.fixed.FOUR]
        or hit["result"]["metrics"].get("observations") != pos[trial.METHOD]
    ):
        raise ValueError(f"{ident} archived control solver saw a different observation set")
    evidence = dict(
        id=ident,
        stock_native=prior["archive"],
        clock_authority=prior["clock_authority"],
        selected_primary_sha256=prior["selected_primary_sha256"],
        audited_selection_sha256=sha256(encoded(decisions)).hexdigest(),
        one_lane_native_sha256=only_sha,
        hit_native_sha256=hit["native_sha256"],
        observations=pos,
        calls={
            PRIMARY: visits,
            trial.METHOD: visits + p,
            METHOD: visits + p + audits,
            trial.fixed.FOUR: 2 * visits,
        },
        **counts,
    )
    jobs = [job(work, case, request, stock, release, cpu, METHOD, METHOD, projected, pos[METHOD])]
    if fresh_cpu is not None:
        jobs.append(
            job(
                work,
                case,
                request,
                stock,
                release,
                fresh_cpu,
                PRIMARY,
                "fresh-primary",
                only,
                pos[PRIMARY],
            )
        )
    return jobs, evidence


def run(work):
    if (REPORT / "plan.json").exists():
        raise FileExistsError("quarter-miss experiment already froze numerical inputs")
    lock, incoming, plan, stock, audits, release, extensions, earlier, history, actual = authority()
    work.mkdir(exist_ok=False)
    schedule, proof = [], {}
    entries = (*lock["prospective2"], *lock["held14"])
    for i, ident in enumerate(entries):
        prospective = ident in lock["prospective2"]
        payload = (
            prepare_fresh(ident, incoming, plan, actual)
            if prospective
            else prepare_held(ident, stock, audits, extensions, earlier, history)
        )
        options, proof[ident] = prepare(
            work,
            payload,
            PINS[i % len(PINS)],
            PINS[i + 2] if prospective else None,
            release,
        )
        schedule.extend(options)
    save_json(REPORT / "packet-audit.json", proof)
    sources = [
        Path(__file__),
        Path(trial.service.__file__),
        Path(trial.service.margin_admission_trial.__file__),
        Path(partner_holdout.__file__),
        Path(partner_on_hit.__file__),
        Path(one_lane_schedule.__file__),
    ]
    save_json(
        REPORT / "plan.json",
        dict(
            held14=lock["held14"],
            prospective2=lock["prospective2"],
            schedule=schedule,
            policy_sha256=POLICY_PIN,
            files={str(p.relative_to(ROOT)): _sha(p) for p in sources},
            packet_audit_sha256=_sha(REPORT / "packet-audit.json"),
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            service_limit_s=trial.service.LIMIT,
            **release,
        ),
    )
    print("frozen", len(schedule), "fits", _sha(REPORT / "plan.json"), flush=True)

    def lane(cpu):
        return [trial.service.service(work, row) for row in schedule if row["cpu"] == cpu]

    with ThreadPoolExecutor(len(PINS)) as pool:
        outputs = [row for group in pool.map(lane, PINS) for row in group]
    pack(REPORT / "predictions.jsonl.gz", outputs)
    members = ("policy-lock.json", "plan.json", "packet-audit.json", "predictions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(entries),
            files={name: _sha(REPORT / name) for name in members},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
