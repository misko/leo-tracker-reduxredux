"""Bind emitted, measured paced GLRT packets to the frozen compact position receiver."""

import argparse
import gzip
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS
from ..variants.selective_capture import visit_pairs
from . import arrival_queue, bracketed_position, recording_to_v5, whole_center_union
from .bracketed_position_results import service_result
from .frontier_whole_replay_results import fingerprint as archived_probe_hash
from .full_v5_check import _sha
from .phase_support_results import pack
from .whole_pressure_trial import rows_from

REPORT = whole_center_union.REPORT.parents[1] / "arrival-and-timing/adaptive-arrival"
PARENT = whole_center_union.REPORT
QUEUE = arrival_queue.REPORT
WORK = Path("/srv/bulk/leo-dev/receiver-screening-20261119/adaptive-arrival-position")
PARENT_PIN = "14ab3e27d00c79c090896a55c6d9340fe6eb2c99077d59ddfbc0f4d0a1a31c6a"
QUEUE_PIN = "25f1073fed1e70d10465f80ad9414d92366cfd14eae5836a61348c3d2f4f47f1"
CPU = {"DS26-0197": 0, "DS29-0316": 1}
ORDER = {"DS26-0197": ("stock", "adaptive", "fifth"), "DS29-0316": ("fifth", "adaptive", "stock")}
ARCHIVE = {"stock": "control", "fifth": "candidate"}
PARENT_METHOD = {"stock": whole_center_union.BASELINE, "fifth": whole_center_union.METHOD}
METHOD = {mode: "adaptive_arrival_" + mode for mode in ("stock", "fifth", "adaptive")}
POSITION_BOUNDARY = "Actual paced saved-IQ emissions through the frozen compact position receiver"


def checked_member(folder, name, files):
    if Path(name).name != name:
        raise ValueError("paced receipt member escapes its report directory")
    return whole_iq.checked(folder / name, files[name])


def parent_member(name, lock):
    return whole_iq.checked(PARENT / name, lock["files"][name])


def document_authority(doc):
    """Ignore only the alternate detector lineage and the corresponding packets."""
    return (
        {k: v for k, v in doc.items() if k not in ("source", "provenance")},
        {k: v for k, v in doc["source"].items() if k not in ("probes", "analysis_manifest_sha256")},
        {k: v for k, v in doc["provenance"].items() if k not in ("detector_sha256", "run_id")},
    )


def load_control(ident):
    archived = whole_iq.read(whole_iq.checked(PARENT / "prediction-lock.json", PARENT_PIN))
    paced = whole_iq.read(whole_iq.checked(QUEUE / "source-lock.json", QUEUE_PIN))
    if set(archived["cases"]) != set(CPU) or paced["parent_prediction_sha256"] != PARENT_PIN:
        raise ValueError("the preceding detector or arrival-queue authority changed")
    release = whole_iq.read(parent_member("source-lock.json", archived))
    bracketed_position.check_release(release)
    case, request = whole_iq.binding(ident)
    source = release["cases"][ident]
    if (
        case["recording"] != source["recording"]
        or case["regions"][0] != source["tile"]
        or case["catalog"]["sha256"] != source["catalog_sha256"]
        or case["request"]["sha256"] != source["request_sha256"]
        or case["native"]["sha256"] != source["capture_native_sha256"]
        or request["causal_snapshots"] != source["orbit_snapshots"]
    ):
        raise ValueError("capture, original solver offer or causal catalogue changed")
    known = {
        row["method"]: row
        for row in rows_from(parent_member("positions.jsonl.gz", archived))
        if row["id"] == ident
    }
    docs, refs = {}, {}
    positions = {}
    for policy, arm in ARCHIVE.items():
        position = known[PARENT_METHOD[policy]]
        member = parent_member(f"native/{arm}/{ident}.json.gz", archived)
        blob = gzip.decompress(member.read_bytes())
        doc = json.loads(blob)
        asset = paced["assets"][arm]
        if (
            sha256(blob).hexdigest() != position["native_sha256"]
            or position["mode"] != "matched-tile"
            or position["tile"] != source["tile"]
            or position["catalog_sha256"] != source["catalog_sha256"]
            or position["original_request_sha256"] != source["request_sha256"]
            or position["paired_capture_sha256"] != source["capture_native_sha256"]
            or doc["source"]["session_id"] != case["session_id"]
            or doc["source"]["input_manifest_sha256"] != source["clock_authority"]
            or doc["source"]["raw_recording_authority_digest"]
            != paced["cases"][ident]["raw_recording_sha256"]
            or doc["provenance"]["detector_sha256"] != "sha256:" + asset["sha256"]
        ):
            raise ValueError("published packets or archived fit do not bind the physical request")
        cutoff = paced["cases"][ident]["modes"][arm]
        refs[policy] = arrival_queue.readgz(
            whole_iq.checked(QUEUE / cutoff["events"], cutoff["sha256"])
        )
        positions[policy] = position
        docs[policy] = doc
    if document_authority(docs["stock"]) != document_authority(docs["fifth"]):
        raise ValueError("the source factors do not share the original acquisition authority")
    verify_original_packet_hashes(parent_member("visits.jsonl.gz", archived), ident, docs, refs)
    return docs, refs, positions, case, request, release


def verify_original_packet_hashes(path, ident, docs, refs):
    """Cross-check the queued envelope digest against the archive's actual native rows."""
    reference = {arm: mode for mode, arm in ARCHIVE.items()}
    probes = matched_probes(docs)
    offsets = Counter()
    with gzip.open(path, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            if row["id"] != ident:
                continue
            mode = reference[row["role"]]
            visit = offsets[mode]
            dispatch = refs[mode][visit]
            if any(row[k] != dispatch[k] for k in ("visit", "status", "full_visit_sha256")):
                raise ValueError("previous paced envelope hash disagrees with the whole-IQ archive")
            paired = probes[mode].get(visit, ())
            for native, sealed in zip(paired, row["probes"], strict=True):
                if (
                    native["receiver_id"] != sealed["receiver_id"]
                    or archived_probe_hash(native["candidates"]) != sealed["payload_sha256"]
                ):
                    raise ValueError("published native packets do not bind their envelope digest")
            offsets[mode] += 1
    if offsets != {mode: len(rows) for mode, rows in refs.items()}:
        raise ValueError("previous whole-IQ source lacks complete raw envelope provenance")


def matched_probes(docs):
    probes = {mode: dict(visit_pairs(doc["source"]["probes"])) for mode, doc in docs.items()}
    if list(probes["stock"]) != list(probes["fifth"]):
        raise ValueError("stock and fifth factors cover different valid physical visits")
    for visit, stock in probes["stock"].items():
        for first, second in zip(stock, probes["fifth"][visit], strict=True):
            if any(
                first[k] != second[k] for k in first.keys() | second.keys() if k != "candidates"
            ):
                raise ValueError("published stock and fifth physical probe metadata differ")
    return probes


def chosen_packets(trace, run_mode, docs, refs):
    """Require the selected detector's exact raw envelope at every emitted visit."""
    probes = matched_probes(docs)
    doc = docs["stock"]
    clocks = doc["delivery_clocks"]
    hardware = {r["visit"]: r for r in doc["provenance"]["excluded_windows"]}
    if len(clocks) != len(trace) or len(clocks) != doc["provenance"]["window_count"]:
        raise ValueError("paced trace lacks the original complete physical visit inventory")
    if (set(probes["stock"]) | set(hardware)) != set(range(len(clocks))) or (
        set(probes["stock"]) & set(hardware)
    ):
        raise ValueError(
            "archived first-detector visit and hardware-exclusion ledgers overlap or omit"
        )
    keys = ("visit", "arrival_ns", "sample_start", "sample_end", "status")
    retained, selected, dropped = [], [], []
    counters = Counter()
    width = doc["source"]["probe_ms"] * doc["source"]["sample_rate_hz"] // 1000
    first = clocks[0]["monotonic_ns"]
    for visit, (event, stock, fifth, clock) in enumerate(
        zip(trace, refs["stock"], refs["fifth"], clocks, strict=True)
    ):
        bad = hardware.get(visit)
        if bad is not None:
            start, end = bad["sample_start"], bad["sample_end"]
        else:
            start = probes["stock"][visit][0]["valid_start_counter"]
            end = start + width
            if probes["stock"][visit][1]["valid_start_counter"] != start:
                raise ValueError("published physical receivers disagree about sample start")
        status = "invalid_capture" if bad is not None else "processed"
        identity = (visit, clock["monotonic_ns"] - first, start, end, status)
        if any(tuple(row[k] for k in keys) != identity for row in (event, stock, fifth)) or any(
            row["delivery_clock"] != clock for row in (stock, fifth)
        ):
            raise ValueError("paced visit, validity, clock or sample counters changed")
        outcome, policy, digest = event["outcome"], event["policy"], event.get("actual_sha256")
        if bad is not None:
            if stock["full_visit_sha256"] != fifth["full_visit_sha256"] or (
                outcome,
                policy,
                digest,
            ) != ("invalid_capture", None, stock["full_visit_sha256"]):
                raise ValueError("a recorded hardware exclusion cannot enter either detector")
            counters["invalid_capture"] += 1
        elif outcome == "queue_drop":
            if policy is not None or digest is not None or event["outstanding_at_admission"] != 2:
                raise ValueError("a queue drop requires a full queue and no detector output")
            dropped.append(visit)
            counters["queue_drop"] += 1
        elif outcome == "emitted":
            before = event["outstanding_at_admission"]
            expected = ("stock" if before else "fifth") if run_mode == "adaptive" else run_mode
            if before not in (0, 1) or policy != expected:
                raise ValueError("emitted detector policy does not match the paced mode")
            authority = stock if policy == "stock" else fifth
            if digest != authority["full_visit_sha256"]:
                raise ValueError(
                    "emitted detector envelope hash does not match the selected policy"
                )
            selected.append([visit, policy, digest])
            retained.extend(probes[policy][visit])
            counters[policy] += 1
        else:
            raise ValueError(
                "original valid visit must either emit a measured packet or queue-drop"
            )
    counts = dict(
        recorded=len(trace),
        valid=len(probes["stock"]),
        emitted=len(selected),
        stock=counters["stock"],
        fifth=counters["fifth"],
        invalid_capture=counters["invalid_capture"],
        queue_drop=counters["queue_drop"],
    )
    return retained, selected, dropped, counts


def materialize(ident, mode, trace_sha, docs, positions, retained, selection):
    """Reuse a complete exact input, otherwise write one new scientific provenance."""
    if len(retained) != 2 * len(selection):
        raise ValueError("every emitted visit must have exactly two selected native factors")
    prefer = (mode,) if mode in ARCHIVE else tuple(ARCHIVE)
    for policy in prefer:
        if retained == docs[policy]["source"]["probes"]:
            return docs[policy], policy
    base = docs["stock"]
    provenance = dict(base["provenance"])
    used = {key for _, key, _ in selection}
    if len(used) == 1:
        provenance["detector_sha256"] = docs[next(iter(used))]["provenance"]["detector_sha256"]
    else:
        provenance.pop("detector_sha256", None)
    lineage = recording_to_v5.digest(
        [
            "adaptive-arrival-emitted-native/v1",
            ident,
            mode,
            trace_sha,
            {key: spec["native_sha256"] for key, spec in positions.items()},
            selection,
        ]
    )
    provenance.update(
        run_id="replay-" + lineage[7:39],
        processed_windows=len(selection),
        scope="Native outputs confirmed against actual paced detector emissions",
    )
    return dict(
        base,
        provenance=provenance,
        source=dict(base["source"], probes=retained, analysis_manifest_sha256=lineage),
    ), None


def raw_attempt(report, ident, mode):
    stem = f"{ident}-{mode}"
    path = report / f"{stem}-lock.json"
    seal = whole_iq.read(path)
    if (
        seal["status"] not in ("complete", "failed")
        or seal["raw_verified"] is not (seal["status"] == "complete")
        or (seal["id"], seal["mode"]) != (ident, mode)
    ):
        raise ValueError("paced detector lock lacks a terminal verification state")
    source = whole_iq.read(
        whole_iq.checked(report / "source-lock.json", seal["source_lock_sha256"])
    )
    if (
        source["prior_arrival_source_sha256"] != QUEUE_PIN
        or source["parent_prediction_sha256"] != PARENT_PIN
        or source["order"][ident] != list(ORDER[ident])
        or source["memory_max"] != whole_iq.MEMORY
        or source["memory_swap_max"] != 0
    ):
        raise ValueError("paced detector lock points to a different experiment")
    for member in seal["files"]:
        checked_member(report, member, seal["files"])
    trace = checked_member(report, f"{stem}-trace.json.gz", seal["files"])
    return seal, path, trace


def empty_result(status, reason):
    return dict(
        status=status,
        reason=reason,
        boundary=POSITION_BOUNDARY,
        metrics={"position_attempted": False},
        arms={a: dict(latlon=None) for a in ARMS},
    )


def position_input(out, case, request, release, doc, cpu):
    path = out / "native.json"
    write(path, (recording_to_v5.encoded(doc) + "\n").encode())
    job = request["job"]
    save_json(
        out / "request.json",
        dict(
            native=str(path),
            native_sha256=_sha(path),
            session=case["session_id"],
            config=job["track_config"],
            archive=job["tle_root"],
            tile=job["search_center"],
            screen=job["screen_center"],
            install=release["receiver"],
            cpu=cpu,
        ),
    )
    return _sha(path), _sha(out / "request.json")


def run(work, report, ident, mode):
    launch = whole_iq.read(report / "position-source-lock.json")
    whole_iq.checked(Path(__file__), launch["materializer_sha256"])
    whole_iq.checked(report / "source-lock.json", launch["paced_source_sha256"])
    for program, digest in launch["sources"].items():
        whole_iq.checked(ROOT / program, digest)
    seal, raw_lock, trace_path = raw_attempt(report, ident, mode)
    docs, refs, positions, case, request, release = load_control(ident)
    fixed = positions["stock"]
    cpu = CPU[ident]
    out = work / ident / mode
    out.mkdir(parents=True, exist_ok=False)
    prefix = f"{ident}-{mode}-position"
    trace_sha = _sha(trace_path)
    base = dict(
        id=ident,
        method=METHOD[mode],
        paced_mode=mode,
        mode="matched-tile",
        cpu=cpu,
        tile=fixed["tile"],
        catalog_sha256=fixed["catalog_sha256"],
        original_request_sha256=fixed["original_request_sha256"],
        paired_capture_sha256=fixed["paired_capture_sha256"],
        parent_native_sha256={label: row["native_sha256"] for label, row in positions.items()},
        native_sha256=None,
        request_sha256=None,
        trace_sha256=trace_sha,
        raw_lock=raw_lock.name,
        raw_lock_sha256=_sha(raw_lock),
        raw_verified=seal["raw_verified"],
        raw_status=seal["status"],
        counts=None,
        position_source_sha256=_sha(report / "position-source-lock.json"),
    )
    if seal["status"] == "complete" and seal["raw_verified"]:
        trace = arrival_queue.readgz(trace_path)
        retained, selected, dropped, counts = chosen_packets(trace, mode, docs, refs)
        doc, reuse = materialize(ident, mode, trace_sha, docs, positions, retained, selected)
        base.update(counts=counts, emission_sha256=sha256(encoded(selected)).hexdigest())
        save_json(report / f"{prefix}-emissions.json", dict(emitted=selected, queue_drops=dropped))
        if reuse:
            source, result = "exact complete factor reuse", positions[reuse]["result"]
            base["native_sha256"] = positions[reuse]["native_sha256"]
        elif not retained:
            source, result = (
                "valid paced attempt returned no emitted packets",
                empty_result("withheld", "no_emitted_native_packets"),
            )
        else:
            source = "fresh compact solve on emitted factors"
            base["native_sha256"], base["request_sha256"] = position_input(
                out, case, request, release, doc, cpu
            )
            result = None
    else:
        source = "paced detector failed verification or completion"
        result = empty_result("unavailable", source)
    submission = report / f"{prefix}-input.json"
    save_json(submission, dict(base, origin=source, program_sha256=_sha(Path(__file__))))
    resources = {}
    resources_path = None
    if result is None:
        whole_iq.checked(out / "request.json", base["request_sha256"])
        whole_iq.checked(out / "native.json", base["native_sha256"])
        bracketed_position.launch_case(out, cpu)
        result, resources = service_result(out, cpu)
        resources_path = report / f"{prefix}-service.log"
        write(resources_path, (out / "service.log").read_bytes())
    dest = report / f"{prefix}.jsonl.gz"
    pack(dest, [dict(base, origin=source, result=result, resources=resources)])
    evidence = [dest, submission]
    if (emission := report / f"{prefix}-emissions.json").is_file():
        evidence.append(emission)
    if resources_path:
        evidence.append(resources_path)
    save_json(
        report / f"{prefix}-lock.json",
        dict(
            cases=[ident],
            mode=mode,
            raw_lock_sha256=base["raw_lock_sha256"],
            files={p.name: _sha(p) for p in evidence},
        ),
    )
    print(ident, mode, result["status"], source, flush=True)


def freeze(report):
    path = report / "position-source-lock.json"
    if path.exists():
        raise FileExistsError("the prospective position authority already exists")
    source = report / "source-lock.json"
    paced = whole_iq.read(source)
    release = whole_iq.read(
        parent_member(
            "source-lock.json",
            whole_iq.read(whole_iq.checked(PARENT / "prediction-lock.json", PARENT_PIN)),
        )
    )
    if set(paced["cases"]) != set(CPU) or paced["parent_prediction_sha256"] != PARENT_PIN:
        raise ValueError("paced input does not match the position roster")
    bracketed_position.check_release(release)
    save_json(
        path,
        dict(
            paced_source_sha256=_sha(source),
            candidate_cpu=CPU,
            order=ORDER,
            materializer_sha256=_sha(Path(__file__)),
            sources={
                str(program.relative_to(ROOT)): _sha(program)
                for program in (
                    Path(bracketed_position.__file__),
                    Path(__file__).with_name("bracketed_position_results.py"),
                )
            },
            parent_prediction_sha256=PARENT_PIN,
            prior_arrival_source_sha256=QUEUE_PIN,
            receiver=release["receiver"],
            receiver_files=release["receiver_files"],
            cgroup=dict(memory_max=whole_iq.MEMORY, swap_max=0, limit_s=bracketed_position.LIMIT),
        ),
    )


def watch(work, report, ident, limit):
    end = monotonic() + limit
    for mode in ORDER[ident]:
        final = report / f"{ident}-{mode}-position-lock.json"
        source = report / f"{ident}-{mode}-lock.json"
        if final.is_file():
            continue
        while not source.is_file():
            if monotonic() >= end:
                raise TimeoutError(f"paced raw attempt has no terminal seal for {ident}/{mode}")
            sleep(2)
        run(work, report, ident, mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cmd = parser.add_subparsers(dest="action", required=True)
    cmd.add_parser("freeze").add_argument("--report", type=local_output, default=REPORT)
    for name in ("run", "watch"):
        stage = cmd.add_parser(name)
        stage.add_argument("case", choices=CPU)
        stage.add_argument("--work", type=local_output, default=WORK)
        stage.add_argument("--report", type=local_output, default=REPORT)
        if name == "run":
            stage.add_argument("mode", choices=METHOD)
        else:
            stage.add_argument("--limit", type=int, default=1500)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.report)
    elif args.action == "run":
        run(args.work, args.report, args.case, args.mode)
    else:
        watch(args.work, args.report, args.case, args.limit)


if __name__ == "__main__":
    main()
