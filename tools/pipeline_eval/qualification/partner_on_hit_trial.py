"""Authenticate the other three antenna cells and fit the missing hit-only cell."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import one_lane_schedule, partner_on_hit, second_on_miss
from . import complete_detector_roster as fixed
from . import hard_pilots_eval as hard
from . import one_lane_roster as one
from . import second_on_miss_roster as miss
from . import support_cross_trial as service
from .bracketed_position import check_release
from .fractional_runtime_whole import verify_request
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .phase_support_results import pack
from .whole_pressure_trial import rows_from

REPORT = one.REPORT.with_name("partner-on-hit")
METHOD = "partner_on_hit"
CASES = (*hard.HARD, *hard.CONTROLS)
PINS = (6, 7, 8, 9, 10, 11)
MISS_PIN = "3483476c6fb403423510c85d3185f1f51837de75f21f4c5d3c4e4c7e23f911a7"
STOCK_PIN = "2bc3768d2c146adc402992f5bbb5714119c2be77ec1959fa6c16329bdebef73a"
read = whole_iq.read


def controls():
    parents, published, audits, releases = {}, {}, {}, []
    for module, digest in ((one, miss.SINGLE_PIN), (miss, MISS_PIN)):
        lock = sealed(module.REPORT, "prediction-lock.json", digest)
        doc = read(fixed.member(module.REPORT, lock, "plan.json"))
        releases.append({k: doc[k] for k in ("receiver", "receiver_files", "native_sources")})
        path = fixed.member(module.REPORT, lock, "positions.jsonl.gz")
        published[module.METHOD] = fixed.select(rows_from(path), module.METHOD, lock["cases"])
        audits[module.METHOD] = read(fixed.member(module.REPORT, lock, "packet-audit.json"))
        parents[module.METHOD] = digest
    if releases[0] != releases[1]:
        raise ValueError("parent scientific installations differ")
    release = releases[0]
    check_release(release)
    lock = read(whole_iq.checked(fixed.REPORT / "all-figure-lock.json", STOCK_PIN))
    raw = rows_from(fixed.member(fixed.REPORT, lock, "all-positions.jsonl.gz"))
    published[fixed.FOUR] = fixed.select(raw, fixed.FOUR, lock["cases"])
    parents[fixed.FOUR] = STOCK_PIN
    for ident in CASES:
        fixed.same_capture(published[one.METHOD][ident], published[fixed.FOUR][ident])
        fixed.same_capture(published[miss.METHOD][ident], published[fixed.FOUR][ident])
    return parents, published, audits, release


def certificate(ident, published, audits):
    before, after = (audits[k][ident] for k in (one.METHOD, miss.METHOD))
    stock, primary, missing = (published[k][ident] for k in (fixed.FOUR, one.METHOD, miss.METHOD))
    archive = before["native_archive"]
    if (
        archive != after["stock_native"]
        or before["clock_authority"] != after["clock_authority"]
        or before["rf_mapping"] != after["rf_mapping"]
        or archive["native_sha256"] != stock["native_sha256"]
        or primary["stock_native_sha256"] != stock["native_sha256"]
        or missing["stock_native_sha256"] != stock["native_sha256"]
        or missing["one_lane_native_sha256"] != primary["native_sha256"]
    ):
        raise ValueError(f"{ident} archived cells did not share the same physical stock body")
    document = one.stock_document(archive)
    if document["source"]["input_manifest_sha256"] != before["clock_authority"]:
        raise ValueError(f"{ident} does not bind the previously authenticated recording")
    centers = {(r["channel"], r["edge"]): r["rf_center_hz"] for r in before["rf_mapping"]}
    first, schedule = one_lane_schedule.project(document, centers)
    other, decisions = second_on_miss.project(document, centers)
    for doc, row, dispatch, expected in (
        (first, primary, schedule, before["selected_visit_sha256"]),
        (other, missing, decisions, after["dispatch_sha256"]),
    ):
        if (
            sha256(encoded(doc) + b"\n").hexdigest() != row["native_sha256"]
            or sha256(encoded(dispatch)).hexdigest() != expected
        ):
            raise ValueError(f"{ident} did not reproduce a previous numerical input byte-for-byte")
    projected, counts = partner_on_hit.project(document, schedule)
    valid, p, h, m = (
        counts[k]
        for k in ("valid_visits", "primary_hits", "covisible_partner_hits", "partner_only_hits")
    )
    positives = {fixed.FOUR: p + h + m, one.METHOD: p, miss.METHOD: p + m, METHOD: p + h}
    for method in (fixed.FOUR, one.METHOD, miss.METHOD):
        if published[method][ident]["result"]["metrics"].get("observations") != positives[method]:
            raise ValueError(f"{ident} parent solver observations disagreed with the gated census")
    evidence = dict(
        id=ident,
        archive=archive,
        clock_authority=before["clock_authority"],
        selected_primary_sha256=before["selected_visit_sha256"],
        partner_on_miss_sha256=after["dispatch_sha256"],
        one_lane_native_sha256=primary["native_sha256"],
        second_on_miss_native_sha256=missing["native_sha256"],
        observations=positives,
        calls={
            fixed.FOUR: 2 * valid,
            one.METHOD: valid,
            miss.METHOD: 2 * valid - p,
            METHOD: valid + p,
        },
        **counts,
    )
    return projected, evidence


def stage(work, ident, cpu, published, audits, release):
    stock = published[fixed.FOUR][ident]
    case, original = whole_iq.binding(ident)
    if tuple(stock[k] for k in fixed.BINDINGS) != (
        case["native"]["sha256"],
        case["request"]["sha256"],
        case["catalog"]["sha256"],
        case["regions"][0],
    ):
        raise ValueError("original truth-free scientific request changed")
    projected, evidence = certificate(ident, published, audits)
    job = work / ident / METHOD
    native, request = job / "recording/native.json", job / "recording/request.json"
    write(native, encoded(projected) + b"\n")
    actual = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
    verify_request(read(request), original, native_path=native, native_sha256=actual)
    save_json(job / "plan.json", dict(receiver=release["receiver"]))
    save_json(job / "raw.json", dict(native_sha256=actual, request_sha256=_sha(request)))
    return dict(
        id=ident,
        method=METHOD,
        condition=METHOD,
        cpu=cpu,
        mode="matched-tile",
        stock_native_sha256=stock["native_sha256"],
        native_sha256=_sha(native),
        prepared_request_sha256=_sha(request),
        positive_probes=evidence["observations"][METHOD],
        **{k: stock[k] for k in fixed.BINDINGS},
    ), evidence


def run(work):
    if (REPORT / "plan.json").exists():
        raise FileExistsError("partner-on-hit schedule was already frozen")
    parents, published, audits, release = controls()
    work.mkdir(exist_ok=False)
    sources = {
        str(path.relative_to(ROOT)): _sha(path)
        for path in (
            Path(__file__),
            Path(partner_on_hit.__file__),
            Path(one_lane_schedule.__file__),
            Path(second_on_miss.__file__),
            Path(service.__file__),
            Path(service.margin_admission_trial.__file__),
            REPORT / "PROTOCOL.md",
        )
    }
    schedule, proof = [], {}
    for i, ident in enumerate(CASES):
        row, proof[ident] = stage(work, ident, PINS[i % len(PINS)], published, audits, release)
        schedule.append(row)
    save_json(REPORT / "packet-audit.json", proof)
    save_json(
        REPORT / "plan.json",
        dict(
            cases=list(CASES),
            schedule=schedule,
            parents=parents,
            sources=sources,
            limit_s=service.LIMIT,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            packet_audit_sha256=_sha(REPORT / "packet-audit.json"),
            **release,
        ),
    )
    print("frozen", len(schedule), "cases", _sha(REPORT / "plan.json"), flush=True)

    def lane(cpu):
        return [service.service(work, row) for row in schedule if row["cpu"] == cpu]

    with ThreadPoolExecutor(len(PINS)) as pool:
        predictions = [row for group in pool.map(lane, PINS) for row in group]
    pack(REPORT / "predictions.jsonl.gz", sorted(predictions, key=lambda row: row["id"]))
    members = ("plan.json", "packet-audit.json", "predictions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(cases=list(CASES), files={n: _sha(REPORT / n) for n in members}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
