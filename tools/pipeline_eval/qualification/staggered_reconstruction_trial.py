"""Reconstruct the sealed twenty complete cases and run actual compact positions."""

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import selective_capture, staggered_native
from ..variants import staggered_reconstruction as policy
from ..variants.iq_stream import _read_prefix
from . import capture_release, fresh_replay, support_cross_trial
from . import complete_detector_roster as roster
from .bracketed_position import check_release
from .fractional_runtime_whole import verify_request
from .full_v5_check import BULK, _sha
from .portable_gate_trials import compressed_rows
from .whole_pressure_trial import rows_from

REPORT = roster.SCREEN / "receiver-choice/staggered-reconstruction"
METHOD = "staggered_reconstruction"
RUNTIME = "stored-complete-per-lane-reconstruction"
CPUS = (2, 3, 4, 5)
LIMIT = support_cross_trial.LIMIT
NATIVE_ROOTS = (
    roster.EIGHT,
    roster.TWO,
    roster.TEN,
    roster.SCREEN / "support-preserving/whole-center-union",
    roster.SCREEN / "support-preserving/fifth-crossover",
    roster.SCREEN / "acquisition-support/fresh-waveform",
    roster.SCREEN / "acquisition-support/scout-full",
    roster.SCREEN / "receiver-core/full-stride",
)
RAW_ROOT = Path("/var/tmp/leo-frontier-whole-20261119/runs")
read = whole_iq.read


def sources():
    paths = (
        Path(__file__),
        REPORT / "PROTOCOL.md",
        Path(policy.__file__),
        Path(staggered_native.__file__),
        Path(selective_capture.__file__),
        Path(support_cross_trial.__file__),
        Path(support_cross_trial.margin_admission_trial.__file__),
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def load_controls():
    seal_path = roster.REPORT / "all-figure-lock.json"
    lock = read(seal_path)
    inventory = read(roster.member(roster.REPORT, lock, "roster.json"))
    cases = inventory["all"]
    if inventory != roster.frozen_roster() or len(cases) != 20 or set(cases) != set(lock["cases"]):
        raise ValueError("complete roof roster differs from its original prospective schedule")
    data = rows_from(roster.member(roster.REPORT, lock, "all-positions.jsonl.gz"))
    stock, fifth = (roster.select(data, name, cases) for name in (roster.FOUR, roster.FIVE))
    for case in cases:
        roster.same_capture(stock[case], fifth[case])
    return lock, cases, stock, fifth


def measured_source(ident, wanted):
    paths = [
        path for folder in NATIVE_ROOTS for path in (folder / "native").rglob(f"{ident}.json.gz")
    ]
    for name in ("control", "candidate"):
        raw = RAW_ROOT / ident / name / "recording/native.json"
        if raw.is_file():
            paths.append(raw)
    found = {}
    for path in paths:
        raw = path.read_bytes()
        body = gzip.decompress(raw) if path.suffix == ".gz" else raw
        digest = sha256(body).hexdigest()
        if digest in wanted:
            found.setdefault(digest, (str(path), sha256(raw).hexdigest(), json.loads(body)))
        if found.keys() == set(wanted):
            break
    if found.keys() != set(wanted):
        raise FileNotFoundError(
            "required original stock/fifth native bytes unavailable under exact hash"
        )
    return [found[h] for h in wanted]


def tune_plan(meta):
    mapping, digests, inventory = {}, [], []
    for idx, record in enumerate(meta["recording"]["segments"]):
        path = BULK / record["path"]
        data = _read_prefix(path, 65537)
        if len(data) > 65536 or sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("physical tuning segment differs from its recording authority")
        manifest = json.loads(data)
        targets = manifest["configuration"]["targets"]
        lhs = {(t["channel"], t["edge"]): t["rf_center_hz"] for t in targets}
        if len(lhs) != len(targets) or any(type(v) is not int or v <= 0 for v in lhs.values()):
            raise ValueError("recorded target needs one integer RF center per physical tune")
        if mapping and lhs != mapping:
            raise ValueError("segment changed the mapping from observed channel to frequency")
        mapping = lhs
        digests.append(dict(record, valid_receiver_ids=manifest["receiver_ids"]))
        inventory.append(
            dict(
                scope=f"segment-{idx:08d}",
                path=str(path.parent),
                manifest_digest="sha256:" + record["sha256"],
                windows=manifest["window_count"],
            )
        )
    if not mapping or any(s["valid_receiver_ids"] != [0, 1] for s in digests):
        raise ValueError("alternation requires an authenticated physical stereo recording")
    if sum(row["windows"] for row in inventory) != meta["recording"]["window_count"]:
        raise ValueError("physical segment roster differs from the complete native frame count")
    identity = capture_release.inventory_digest(inventory, meta["recording"]["window_count"])
    return mapping, digests, identity


def reconstruct(work, ident, stock, fifth, source, extensions, pin):
    if ident in extensions:
        with fresh_replay.patched_case(extensions[ident]):
            case, request = whole_iq.binding(ident)
    else:
        case, request = whole_iq.binding(ident)
    if (
        case["catalog"]["sha256"] != stock["catalog_sha256"]
        or case["request"]["sha256"] != stock["original_request_sha256"]
        or case["native"]["sha256"] != stock["paired_capture_sha256"]
        or request["job"]["search_center"] != stock["tile"]["center"]
    ):
        raise ValueError("reconstructed data must use exact truth-free request and causal tile")
    wanted = (stock["native_sha256"], fifth["native_sha256"])
    parents = measured_source(ident, wanted)
    docs = [row[2] for row in parents]
    for branch, document in zip(("control", "candidate"), docs, strict=True):
        checksum = source["detectors"][branch]["sha256"].removeprefix("sha256:")
        if (
            document["provenance"]["detector_sha256"] != "sha256:" + checksum
            or document["source"]["session_id"] != case["session_id"]
            or document["provenance"]["window_count"] != case["recording"]["window_count"]
        ):
            raise ValueError("canonical native parents use a different renderer or recording")
    centers, manifests, authority = tune_plan(case)
    if any(doc["source"]["input_manifest_sha256"] != authority for doc in docs):
        raise ValueError("native detector documents reference another physical IQ inventory")
    hybrid, witness, counts = policy.assemble(*docs, centers, encoded)
    selection = sha256(encoded(witness)).hexdigest()
    evidence = dict(
        id=ident,
        **counts,
        selected_packet_sequence_sha256=selection,
        input_archives={
            name: dict(path=row[0], file_sha256=row[1], native_sha256=sha)
            for name, row, sha in zip(("stock", "fifth"), parents, wanted, strict=True)
        },
        segment_manifests=manifests,
        rf_mapping=[
            dict(channel=c, edge=e, rf_center_hz=rf) for (c, e), rf in sorted(centers.items())
        ],
    )
    lineage = whole_iq.recording.digest([policy.POLICY, *wanted, selection])
    document = dict(
        docs[0],
        source=dict(
            docs[0]["source"],
            probes=hybrid,
            analysis_manifest_sha256=lineage,
        ),
    )
    provenance = dict(
        docs[0]["provenance"],
        run_id="staggered-reconstruction-" + lineage[7:27],
        scope="Complete archived per-lane factor reconstruction; no detector run",
    )
    provenance.pop("detector_sha256")
    document["provenance"] = provenance
    folder = work / ident / METHOD
    output = folder / "recording/native.json"
    fresh = folder / "recording/request.json"
    write(output, encoded(document) + b"\n")
    actual = whole_iq.recording.bind_request(case, output, fresh)["native_sha256"]
    verify_request(read(fresh), request, native_path=output, native_sha256=actual)
    save_json(folder / "plan.json", dict(receiver=source["receiver"]))
    save_json(folder / "raw.json", dict(native_sha256=actual, request_sha256=_sha(fresh)))
    row = dict(
        id=ident,
        method=METHOD,
        condition=METHOD,
        mode="matched-tile",
        cpu=pin,
        native_sha256=actual.removeprefix("sha256:"),
        prepared_request_sha256=_sha(fresh),
        stock_native_sha256=wanted[0],
        fifth_native_sha256=wanted[1],
        provenance=dict(boundary=RUNTIME, detector_runtime_measured=False),
        positive_probes=counts["staggered_positive"],
        positive_candidates=counts["staggered_gated_candidates"],
        **{key: stock[key] for key in roster.BINDINGS},
    )
    return row, evidence


def stage(work):
    work.mkdir(exist_ok=False)
    if (REPORT / "plan.json").exists():
        raise FileExistsError("staggered reconstruction already frozen")
    _, ids, four, five = load_controls()
    old = read(roster.EIGHT / "eight-figure-lock.json")
    fresh = read(roster.TWO / "all-figure-lock.json")
    old_raw = read(roster.member(roster.EIGHT, old, "raw-prediction-lock.json"))
    new_raw = read(roster.member(roster.TWO, fresh, "raw-prediction-lock.json"))
    first = read(roster.member(roster.EIGHT, old_raw, "source-lock.json"))
    newest = read(roster.member(roster.TWO, new_raw, "source-lock.json"))
    check_release(first)
    if roster.receiver_identity(first) != roster.receiver_identity(newest):
        raise ValueError("complete 20-case sources disagree on installed detector or receiver")
    extensions = {"DS29-0047": first, "DS29-0330": newest}
    cases, inputs, excluded = [], {}, {}
    for index, ident in enumerate(ids):
        pin = CPUS[index % len(CPUS)]
        try:
            row, proof = reconstruct(work, ident, four[ident], five[ident], first, extensions, pin)
        except (OSError, ValueError, KeyError) as e:
            excluded[ident] = str(e)
            row = dict(
                id=ident,
                method=METHOD,
                cpu=pin,
                native_sha256=None,
                provenance=dict(boundary=RUNTIME, detector_runtime_measured=False),
                **{k: four[ident][k] for k in roster.BINDINGS},
            )
        else:
            inputs[ident] = proof
        cases.append(row)
    save_json(REPORT / "packet-audit.json", inputs)
    save_json(
        REPORT / "plan.json",
        dict(
            roster=ids,
            scheduled=cases,
            excluded=excluded,
            sources=sources(),
            policy=policy.POLICY,
            parent_sha256=_sha(roster.REPORT / "all-figure-lock.json"),
            packet_audit_sha256=_sha(REPORT / "packet-audit.json"),
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            service_limit_s=LIMIT,
            **{k: first[k] for k in ("receiver", "receiver_files", "native_sources")},
        ),
    )
    print(
        "Pre-inference 20-case lock", _sha(REPORT / "plan.json"), "exclusions", excluded, flush=True
    )


def unavailable(row, reason):
    return dict(
        row,
        terminal="not-launched",
        result=dict(
            status="unavailable",
            reason=reason,
            boundary="Stored lane factors through compact receiver position",
            arms={a: dict(latlon=None) for a in ("c0", "fitted_c")},
            metrics={},
        ),
    )


def run(work):
    plan = read(REPORT / "plan.json")
    if sources() != plan["sources"]:
        raise ValueError("scientific sources changed after the prospective input lock")
    check_release(plan)

    def lane(cpu):
        return [
            support_cross_trial.service(work, row)
            if row["id"] not in plan["excluded"]
            else unavailable(row, plan["excluded"][row["id"]])
            for row in plan["scheduled"]
            if row["cpu"] == cpu
        ]

    with ThreadPoolExecutor(4) as pool:
        rows = [r for group in pool.map(lane, CPUS) for r in group]
    write(REPORT / "positions.jsonl.gz", compressed_rows(sorted(rows, key=lambda r: r["id"])))
    output = ("plan.json", "packet-audit.json", "positions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=plan["roster"],
            attempted=sum(row["terminal"] != "not-launched" for row in rows),
            files={name: _sha(REPORT / name) for name in output},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    stage(args.work)
    run(args.work)
