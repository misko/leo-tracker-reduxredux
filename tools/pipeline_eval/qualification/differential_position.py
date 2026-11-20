"""Run the complete scheduled differential timing intervention through phase-release."""

import argparse
import gzip
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..variants.anchor_receiver import splice_probes
from . import bracketed_position as installed
from .bracketed_position_results import scientific, service_result
from .full_v5_check import _sha
from .phase_support_results import pack
from .whole_pressure_trial import rows_from

PARENT = installed.SCREEN / "acquisition-frontier/differential-pilot"
REPORT = PARENT.parent / "differential-position"
MODES = ("stock", "causal", "sham")
METHODS = {mode: f"differential_position_{mode}" for mode in MODES}
LANES = {6: ("DS26-0162", "DS29-0082"), 7: ("DS29-0519", "DS26-0237")}
PREFIX = {"primary": "", "confirmation": "-confirmation"}
GATE = "passed_fractional_margin_gate"
BOUNDARY = "Scheduled partial-IQ differential pilot substitution through installed phase-release"


def ungzip(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def key(p):
    return p["visit_index"], p["receiver_id"]


def winner(p):
    return max(
        (c for c in p["candidates"] if c[GATE]),
        key=lambda c: (c["fractional_margin"], -c["candidate_rank"]),
        default=None,
    )


def splice(document, rows, stock_sha, detector_sha, evidence_sha):
    """Check both lanes before applying complete packets and preserve all capture fields."""
    visits = {r["visit"] for _, r in rows}
    if document["schema_version"] != 2 or len(visits) != len(rows):
        raise ValueError("invalid native schema or repeated scheduled visit")
    source = document["source"]
    stock = {key(p): p for p in source["probes"] if p["visit_index"] in visits}
    patches, audit = defaultdict(list), []
    for split, row in rows:
        visit, designated = row["visit"], row["receiver"]
        receivers = tuple(row["receiver_ids"])
        if len(receivers) != 2 or len(set(receivers)) != 2 or designated not in receivers:
            raise ValueError("unexpected scheduled receiver geometry")
        keys = tuple((visit, lane) for lane in receivers)
        reference = [stock[k] for k in keys]
        if row["baseline"] != reference or any(
            p["valid_start_counter"] != row["counter"] for p in reference
        ):
            raise ValueError("scheduled waveform does not bind stock probes")
        available = row["status"] == "processed"
        payloads = row["probes"] if available else dict.fromkeys((*MODES, "off"), reference)
        if payloads["stock"] != reference or payloads["off"] != reference:
            raise ValueError("raw stock or hint-off differs from archived stock")
        for mode in MODES:
            actual = payloads[mode]
            if tuple(map(key, actual)) != keys or any(
                p != q
                for p, q in zip(actual, reference, strict=True)
                if p["receiver_id"] != designated
            ):
                raise ValueError("treatment changed the unhinted physical lane")
            if available:
                patches[mode].append(
                    dict(
                        visit=visit,
                        sample_start=row["counter"],
                        equal_status=True,
                        native=actual,
                        iq_sha256=row["iq_sha256"],
                    )
                )
            for original, p in zip(reference, actual, strict=True):
                selected = winner(p)
                audit.append(
                    dict(
                        split=split,
                        visit=visit,
                        mode=mode,
                        receiver=p["receiver_id"],
                        designated=p["receiver_id"] == designated,
                        status=row["status"],
                        reason=row.get("reason"),
                        iq_sha256=row["iq_sha256"],
                        kind=row["kind"],
                        channel=p["channel"],
                        edge=p["edge"],
                        rf_hz=p["actual_rf_hz"],
                        counter=p["valid_start_counter"],
                        changed=p != original,
                        winner_changed=selected != winner(original),
                        candidate_count=len(p["candidates"]),
                        passes=sum(c[GATE] for c in p["candidates"]),
                        winner_cfo_hz=selected["fractional_tracking_cfo_hz"] if selected else None,
                    )
                )
    composed = {mode: document for mode in MODES}
    for mode, rows in patches.items():
        derived, changed = splice_probes(
            document,
            dict(
                rows=rows,
                producer={"run_id": document["provenance"]["run_id"]},
                archive_audit=dict(archive_exclusions_equal=True, archive_sha256=stock_sha),
                source_sha256=evidence_sha,
                kernel_sha256=detector_sha,
            ),
        )
        if changed != sum(r["changed"] for r in audit if r["mode"] == mode):
            raise ValueError("native edit count does not match locked packets")
        # The derived hash lives in the request/receipt. Preserve original capture metadata.
        composed[mode] = dict(document, source=dict(source, probes=derived["source"]["probes"]))
    return composed, audit


def detector_rows(path, digest):
    files = whole_iq.read(whole_iq.checked(path, digest))["files"]
    primary = ungzip(
        whole_iq.checked(path.parent / "input-lock.json.gz", files["input-lock.json.gz"])
    )
    confirmation = whole_iq.read(
        whole_iq.checked(path.parent / "confirmation-lock.json", files["confirmation-lock.json"])
    )
    rows = defaultdict(list)
    cohort = {ident for lane in LANES.values() for ident in lane}
    if primary["cases"].keys() != cohort or confirmation["cases"].keys() != cohort:
        raise ValueError("differential panel did not match the four recordings")
    for ident in sorted(cohort):
        for split, appendix in PREFIX.items():
            name = f"{ident}{appendix}.json.gz"
            if split == "primary" and files[name] != confirmation["primary"][ident]:
                raise ValueError("confirmation binds a different primary run")
            authority = primary if split == "primary" else confirmation
            actual = ungzip(whole_iq.checked(path.parent / name, files[name]))
            planned = authority["cases"][ident]
            if len(actual) != (6 if split == "primary" else 2) or len(planned) != len(actual):
                raise ValueError("scheduled denominator changed")
            for locked, observed in zip(planned, actual, strict=True):
                if observed["case"] != ident or any(observed[k] != v for k, v in locked.items()):
                    raise ValueError("executed window differs from its sealed plan")
                rows[ident].append((split, observed))
    return rows, files


def stage(work, report, detector_lock, digest):
    if work.exists() or (report / "source-lock.json").exists():
        raise FileExistsError("the position roster already has a prospective lock")
    paired, detector_files = detector_rows(detector_lock, digest)
    path = installed.PRIOR / "prediction-lock.json"
    authority = whole_iq.read(whole_iq.checked(path, installed.PRIOR_SHA))["files"]

    def checked(name):
        return whole_iq.checked(installed.PRIOR / name, authority[name])

    release = whole_iq.read(checked("source-lock.json"))
    installed.check_release(release)
    historical = {
        r["id"]: r
        for r in rows_from(checked("positions.jsonl.gz"))
        if r["method"] == "wide-cfo-stride_control"
    }
    resources = whole_iq.read(checked("resources.json"))
    cases, audit = {}, []
    for cpu, lane in LANES.items():
        for ident in lane:
            case, original = whole_iq.binding(ident)
            job = original["job"]
            stock, resource = historical[ident], resources[ident]["control"]
            name = f"native/control/{ident}.json.gz"
            blob = gzip.decompress(checked(name).read_bytes())
            native_sha = stock["native_sha256"]
            doc = json.loads(blob)
            kernel = resource["detector_sha256"]
            if (
                stock["result"]["status"] != "ok"
                or case["session_id"] != doc["source"]["session_id"]
                or case["request"]["sha256"] != stock["original_request_sha256"]
                or case["catalog"]["sha256"] != stock["catalog_sha256"]
                or job["search_center"] != stock["tile"]["center"]
                or doc["source"]["input_manifest_sha256"] != resource["input_manifest_sha256"]
                or doc["provenance"]["detector_sha256"] != "sha256:" + kernel
            ):
                raise ValueError("full wide archive does not bind original request")
            staged, points = splice(doc, paired[ident], native_sha, kernel, digest)
            audit.extend(dict(id=ident, **point) for point in points)
            modes = {}
            for mode, native in staged.items():
                directory = work / ident / mode
                payload = encoded(native) + b"\n"
                edited = any(r["changed"] for r in points if r["mode"] == mode)
                if (payload != blob) != edited:
                    raise ValueError("stock-equivalent payload must preserve archive bytes")
                native_path = directory / "native.json"
                write(native_path, payload)
                if mode == "stock":
                    whole_iq.checked(native_path, native_sha)
                request = directory / "request.json"
                save_json(
                    request,
                    dict(
                        native=str(native_path),
                        native_sha256=_sha(native_path),
                        session=case["session_id"],
                        config=job["track_config"],
                        archive=job["tle_root"],
                        tile=job["search_center"],
                        screen=job["screen_center"],
                        install=release["receiver"],
                        cpu=cpu,
                    ),
                )
                modes[mode] = dict(
                    native_sha256=_sha(native_path),
                    request_sha256=_sha(request),
                    identical=not edited,
                )
            cases[ident] = dict(
                baseline=stock,
                capture_era_native_sha256=case["native"]["sha256"],
                cpu=cpu,
                native_archive_sha256=authority[name],
                modes=modes,
                config=job["track_config"],
                causal_snapshots=original["causal_snapshots"],
                input_manifest_sha256=doc["source"]["input_manifest_sha256"],
            )
    pack(report / "window-audit.jsonl.gz", audit)
    path = report / "source-lock.json"
    paths = (
        Path(__file__),
        Path(installed.__file__),
        Path(whole_iq.raw.__file__),
        report / "PROTOCOL.md",
    )
    save_json(
        path,
        dict(
            cases=cases,
            paths={str(p): _sha(p) for p in paths},
            detector_lock_sha256=digest,
            detector_files_sha256=detector_files,
            full_stride_lock_sha256=installed.PRIOR_SHA,
            receiver=release["receiver"],
            receiver_files=release["receiver_files"],
            native_sources=release["native_sources"],
            limit_s=installed.LIMIT,
            memory_max=whole_iq.MEMORY,
            swap_max=0,
            audit_sha256=_sha(report / "window-audit.jsonl.gz"),
        ),
    )
    save_json(work / "source-lock.json", {"report_sha256": _sha(path)})


def selection(work, report):
    expect = whole_iq.read(work / "source-lock.json")["report_sha256"]
    lock = whole_iq.read(whole_iq.checked(report / "source-lock.json", expect))
    for path, digest in lock["paths"].items():
        whole_iq.checked(Path(path), digest)
    whole_iq.checked(report / "window-audit.jsonl.gz", lock["audit_sha256"])
    installed.check_release(lock)
    return lock


def attempt(work, ident, name, spec):
    path = work / ident / name
    for file, field in (("native.json", "native_sha256"), ("request.json", "request_sha256")):
        whole_iq.checked(path / file, spec["modes"][name][field])
    if not (path / "service.json").exists():
        installed.launch_case(path, spec["cpu"])
    return service_result(path, spec["cpu"])


def run(work, report):
    locked = selection(work, report)

    def replay(lane):
        for ident in lane:
            spec = locked["cases"][ident]
            fresh, _ = attempt(work, ident, "stock", spec)
            if fresh["status"] == "ok" and scientific(fresh) != scientific(
                spec["baseline"]["result"]
            ):
                raise ValueError(f"{ident} fresh control scientific parity failed")
            for mode in MODES[1:]:
                if not spec["modes"][mode]["identical"]:
                    attempt(work, ident, mode, spec)

    with ThreadPoolExecutor(max_workers=len(LANES)) as pool:
        list(pool.map(replay, LANES.values()))


def seal(work, report):
    locked = selection(work, report)
    rows, resources = [], {}
    files = [
        "source-lock.json",
        "window-audit.jsonl.gz",
        "PROTOCOL.md",
        "resources.json",
        "positions.jsonl.gz",
    ]
    for ident, spec in locked["cases"].items():
        baseline = spec["baseline"]
        resources[ident] = {}
        for mode in MODES:
            desc, path = spec["modes"][mode], work / ident / mode
            whole_iq.checked(path / "native.json", desc["native_sha256"])
            whole_iq.checked(path / "request.json", desc["request_sha256"])
            if mode != "stock" and desc["identical"]:
                result, measurement = (
                    baseline["result"],
                    dict(origin="identical stock native bytes"),
                )
            else:
                result, measurement = service_result(path, spec["cpu"])
                measurement["origin"] = "fresh paired phase-release"
                for suffix in ("service.log", "position.json"):
                    if (path / suffix).exists():
                        name = f"{ident}-{mode}-{suffix}"
                        write(report / name, (path / suffix).read_bytes())
                        files.append(name)
            measurement["status"] = result["status"]
            if mode == "stock" and result["status"] == "ok":
                if scientific(result) != scientific(baseline["result"]):
                    raise ValueError("fresh stock failed run-level science parity")
                measurement["archive_science_exact"] = True
            resources[ident][mode] = measurement
            rows.append(
                dict(
                    baseline,
                    method=METHODS[mode],
                    native_sha256=desc["native_sha256"],
                    input_sha256=desc["request_sha256"],
                    stock_native_sha256=baseline["native_sha256"],
                    capture_era_native_sha256=spec["capture_era_native_sha256"],
                    result=result,
                    origin=measurement["origin"],
                    boundary=BOUNDARY,
                )
            )
    pack(report / "positions.jsonl.gz", rows)
    save_json(report / "resources.json", resources)
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=list(locked["cases"]),
            files={name: _sha(report / name) for name in files},
            source_sha256=_sha(Path(__file__)),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run", "seal"))
    parser.add_argument("--work", type=local_output, required=True)
    parser.add_argument("--out", type=local_output, default=REPORT)
    parser.add_argument("--detector-sha256")
    args = parser.parse_args()
    if args.action == "stage":
        if not args.detector_sha256:
            parser.error("stage requires the frozen detector SHA-256")
        stage(args.work, args.out, PARENT / "prediction-lock.json", args.detector_sha256)
    else:
        {"run": run, "seal": seal}[args.action](args.work, args.out)


if __name__ == "__main__":
    main()
