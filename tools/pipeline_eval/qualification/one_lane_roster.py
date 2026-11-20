"""Run actual compact positions on a frozen, one-antenna stock-factor projection."""

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants.selective_capture import visit_pairs
from . import complete_detector_roster as fixed
from . import fresh_replay, staggered_benchmark, staggered_reconstruction_trial, support_cross_trial
from .bracketed_position import check_release
from .fractional_runtime_whole import verify_request
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .phase_support_results import pack

REPORT = fixed.SCREEN / "pilot-influence/one-lane-roster"
METHOD = "one_lane_roster"
CPUS = (20, 21)
PROTOCOL = REPORT / "PROTOCOL.md"
ROSTER = staggered_benchmark.REPORT / "roster.json"
RECONSTRUCTION = staggered_benchmark.RECONSTRUCTED
FRESH = staggered_benchmark.FRESH
ROSTER_SHA = "745cfa3eb23ee9a34ea0dbd2c50527536e5d520ed7f8fa5b100e1622dab8bc9d"
RECONSTRUCTION_SHA = "ba4e4f42af9bf28ebca15c6bc5115f10173823bbb05f3d215eb8aa90dd06e07b"
FRESH_RAW_SHA = "199c96ddf9048d7763eee57bc589163092f49027da4aa209584abf426247d17f"
STOCK_SHA = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"
BOUNDARY = "Complete saved stock antenna factors through actual compact position"


def sources():
    from ..variants import one_lane_schedule, staggered_native

    paths = (
        Path(__file__),
        PROTOCOL,
        Path(one_lane_schedule.__file__),
        Path(staggered_native.__file__),
        Path(staggered_reconstruction_trial.__file__),
        Path(support_cross_trial.__file__),
        Path(support_cross_trial.margin_admission_trial.__file__),
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def inventory():
    groups = whole_iq.read(whole_iq.checked(ROSTER, ROSTER_SHA))["groups"]
    initial = sealed(RECONSTRUCTION, "prediction-lock.json", RECONSTRUCTION_SHA)
    before = whole_iq.read(fixed.member(RECONSTRUCTION, initial, "plan.json"))
    audit = whole_iq.read(fixed.member(RECONSTRUCTION, initial, "packet-audit.json"))
    raw = sealed(FRESH, "raw-prediction-lock.json", FRESH_RAW_SHA)
    recent = whole_iq.read(fixed.member(FRESH, raw, "source-lock.json"))
    fresh = whole_iq.read(fixed.member(FRESH, raw, "raw-authority.json"))
    if (
        len(groups["all"]) != 22
        or len(groups["difficult"]) != 6
        or len(groups["fresh"]) != 2
        or sorted(audit) != groups["reconstructed"]
        or sorted(fresh) != groups["fresh"]
        or set(groups["all"]) != set(audit) | set(fresh)
        or set(recent["cases"]) != set(fresh)
    ):
        raise ValueError("one-lane replay requires the exact earlier 20 and new 2 roster")
    release = {k: before[k] for k in ("receiver", "receiver_files", "native_sources")}
    if any(recent[k] != v for k, v in release.items()):
        raise ValueError("paired source policies were fit by different receiver releases")
    check_release(release)
    old_extensions = {}
    for path, ident in (
        (fixed.EIGHT / "source-lock.json", "DS29-0047"),
        (fixed.TWO / "source-lock.json", "DS29-0330"),
    ):
        old_extensions[ident] = whole_iq.read(path)
    bindings = {r["id"]: {k: r[k] for k in fixed.BINDINGS} for r in before["scheduled"]}
    media = {ident: r["input_archives"]["stock"] for ident, r in audit.items()}
    extensions = old_extensions | dict.fromkeys(fresh, recent)
    for ident, item in fresh.items():
        case, control = recent["cases"][ident], item["control"]
        if not control["complete"]:
            raise ValueError("new2 must have a complete physical stock capture")
        name = f"native/control/{ident}.json.gz"
        media[ident] = dict(
            path=str(FRESH / name),
            file_sha256=raw["files"][name],
            native_sha256=control["native_sha256"],
        )
        keys = ("capture_native_sha256", "request_sha256", "catalog_sha256", "tile")
        bindings[ident] = {a: case[b] for a, b in zip(fixed.BINDINGS, keys, strict=True)}
    return groups, media, bindings, extensions, release


def stock_document(record):
    path = whole_iq.checked(Path(record["path"]), record["file_sha256"])
    data = path.read_bytes()
    body = gzip.decompress(data) if path.suffix == ".gz" else data
    if sha256(body).hexdigest() != record["native_sha256"]:
        raise ValueError("stock archive has different scientific bytes")
    return json.loads(body)


def audit_projection(source, projected, schedule):
    """Assert exact preservation of selected lanes and physically empty alternate envelopes."""
    if any(source[k] != projected[k] for k in source if k not in ("source", "provenance")):
        raise ValueError("duty projection changed the recording clocks or sample counters")
    ignore = {"probes", "analysis_manifest_sha256"}
    if {k: v for k, v in source["source"].items() if k not in ignore} != {
        k: v for k, v in projected["source"].items() if k not in ignore
    }:
        raise ValueError("duty projection changed the physical recording authority")
    if source["provenance"]["excluded_windows"] != projected["provenance"]["excluded_windows"]:
        raise ValueError("duty projection changed excluded raw acquisitions")
    old = visit_pairs(source["source"]["probes"])
    probes = visit_pairs(projected["source"]["probes"])
    counts = dict(
        valid_visits=0,
        masked_probe_rows=0,
        stock_positive_probes=0,
        positive_probes=0,
        stock_candidates=0,
        retained_candidates=0,
    )
    for (a, stock), (b, rows), selected in zip(old, probes, schedule, strict=True):
        rx = selected["selected_receiver"]
        if a != b or a != selected["visit"] or rx not in (0, 1):
            raise ValueError("selected schedule lost physical visit order")
        if encoded(rows[rx]) != encoded(stock[rx]) or encoded(rows[1 - rx]) != encoded(
            dict(stock[1 - rx], candidates=[])
        ):
            raise ValueError("retained lane changed or suppressed lane has a candidate")
        counts["valid_visits"] += 1
        counts["masked_probe_rows"] += 1
        counts["stock_positive_probes"] += sum(
            any(c["passed_fractional_margin_gate"] for c in p["candidates"]) for p in stock
        )
        counts["positive_probes"] += any(
            c["passed_fractional_margin_gate"] for c in rows[rx]["candidates"]
        )
        counts["stock_candidates"] += sum(len(p["candidates"]) for p in stock)
        counts["retained_candidates"] += len(rows[rx]["candidates"])
    return counts


def bind(ident, extensions):
    if ident not in extensions:
        return whole_iq.binding(ident)
    with fresh_replay.patched_case(extensions[ident]):
        return whole_iq.binding(ident)


def prepare(work, ident, archive, binding, extension, release, cpu):
    from ..variants.one_lane_schedule import project

    case, original = bind(ident, extension)
    if binding != dict(
        paired_capture_sha256=case["native"]["sha256"],
        original_request_sha256=case["request"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        tile=case["regions"][0],
    ):
        raise ValueError("stock projection differs from its original truth-free request")
    document = stock_document(archive)
    centers, manifests, clock = staggered_reconstruction_trial.tune_plan(case)
    if (
        document["source"]["session_id"] != case["session_id"]
        or document["source"]["input_manifest_sha256"] != clock
        or document["provenance"]["window_count"] != case["recording"]["window_count"]
        or document["provenance"]["detector_sha256"] != "sha256:" + STOCK_SHA
    ):
        raise ValueError("stock factors differ from their physical wide four-center authority")
    projected, schedule = project(document, centers)
    statistics = audit_projection(document, projected, schedule)
    if (
        statistics["valid_visits"] != document["provenance"]["processed_windows"]
        or statistics["valid_visits"] + len(document["provenance"]["excluded_windows"])
        != case["recording"]["window_count"]
    ):
        raise ValueError("stored stock must contain every valid factor pair and capture exclusion")
    job = work / ident / METHOD
    native, request = job / "recording/native.json", job / "recording/request.json"
    write(native, encoded(projected) + b"\n")
    committed = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
    verify_request(whole_iq.read(request), original, native_path=native, native_sha256=committed)
    save_json(job / "plan.json", dict(receiver=release["receiver"]))
    save_json(job / "raw.json", dict(native_sha256=committed, request_sha256=_sha(request)))
    row = dict(
        id=ident,
        method=METHOD,
        mode="matched-tile",
        condition=METHOD,
        cpu=cpu,
        **binding,
        native_sha256=_sha(native),
        prepared_request_sha256=_sha(request),
        stock_native_sha256=archive["native_sha256"],
        **statistics,
    )
    audit = dict(
        id=ident,
        native_archive=archive,
        clock_authority=clock,
        manifests=manifests,
        rf_mapping=[
            dict(channel=c, edge=e, rf_center_hz=rf) for (c, e), rf in sorted(centers.items())
        ],
        selected_visit_sha256=sha256(encoded(schedule)).hexdigest(),
        **statistics,
    )
    return row, audit


def freeze(work):
    groups, media, bindings, extensions, release = inventory()
    if (REPORT / "plan.json").exists():
        raise FileExistsError("the one-lane roster is already frozen")
    work.mkdir(exist_ok=False)
    for ident, archive in media.items():
        original = Path(archive["path"])
        if not original.is_relative_to(Path("/var/tmp")):
            continue
        copy = REPORT / "stock" / f"{ident}.json.gz"
        payload = whole_iq.checked(original, archive["file_sha256"]).read_bytes()
        write(copy, gzip.compress(payload, mtime=0))
        media[ident] = dict(
            archive, path=str(copy), file_sha256=_sha(copy), parent_path=str(original)
        )
    priority = list(dict.fromkeys([*groups["difficult"], *groups["fresh"], *groups["all"]]))
    scheduled, audits, errors = [], {}, {}
    for i, ident in enumerate(priority):
        cpu = CPUS[i % len(CPUS)]
        try:
            row, audit = prepare(
                work, ident, media[ident], bindings[ident], extensions, release, cpu
            )
        except (OSError, ValueError, KeyError, StopIteration) as error:
            errors[ident] = str(error)
            row = dict(
                id=ident,
                method=METHOD,
                condition=METHOD,
                cpu=cpu,
                mode="matched-tile",
                **bindings[ident],
                native_sha256=None,
            )
        else:
            audits[ident] = audit
        scheduled.append(row)
    save_json(REPORT / "packet-audit.json", audits)
    save_json(
        REPORT / "plan.json",
        dict(
            groups=groups,
            jobs=scheduled,
            errors=errors,
            sources=sources(),
            cpus=CPUS,
            limit_s=support_cross_trial.LIMIT,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            **release,
            packet_audit_sha256=_sha(REPORT / "packet-audit.json"),
            parent_roster_sha256=ROSTER_SHA,
            parent_stock_sha256={"frozen_twenty": RECONSTRUCTION_SHA, "fresh_two": FRESH_RAW_SHA},
        ),
    )
    save_json(work / "launch-lock.json", dict(plan_sha256=_sha(REPORT / "plan.json")))
    print("frozen", len(scheduled), "inputs", len(audits), "errors", errors, flush=True)


def run(work):
    path = whole_iq.checked(
        REPORT / "plan.json", whole_iq.read(work / "launch-lock.json")["plan_sha256"]
    )
    plan = whole_iq.read(path)
    if plan["sources"] != sources():
        raise ValueError("staged numerical inputs or methods changed before launch")
    check_release(plan)

    def lane(cpu):
        for row in plan["jobs"]:
            if row["cpu"] != cpu:
                continue
            if row["id"] in plan["errors"]:
                yield dict(
                    row,
                    terminal="not-launched",
                    result=dict(
                        status="unavailable",
                        reason=plan["errors"][row["id"]],
                        boundary=BOUNDARY,
                        arms={a: dict(latlon=None) for a in ("c0", "fitted_c")},
                        metrics={},
                    ),
                )
            else:
                yield support_cross_trial.service(work, row)

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        rows = sorted(
            (r for outcome in pool.map(lambda cpu: list(lane(cpu)), CPUS) for r in outcome),
            key=lambda row: row["id"],
        )
    pack(REPORT / "positions.jsonl.gz", rows)
    files = (
        "positions.jsonl.gz",
        "plan.json",
        "packet-audit.json",
        "PROTOCOL.md",
        *(str(p.relative_to(REPORT)) for p in sorted((REPORT / "stock").glob("*.json.gz"))),
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=plan["groups"]["all"],
            files={name: _sha(REPORT / name) for name in files},
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inventory", "freeze", "run"))
    parser.add_argument("--work", type=local_output)
    args = parser.parse_args()
    if args.action == "inventory":
        groups, media, _, _, _ = inventory()
        for ident, archive in media.items():
            stock_document(archive)
            print(ident, archive["native_sha256"], Path(archive["path"]).name)
        print(len(groups["all"]), "complete authenticated stock archives")
    else:
        {"freeze": freeze, "run": run}[args.action](args.work)


if __name__ == "__main__":
    main()
