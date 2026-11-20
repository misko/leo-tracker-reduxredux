"""Seal the recorded-IQ comparison and rescore both calibration arms offline."""

import argparse
import gzip
import io
import json
import tarfile
from hashlib import sha256

from .. import corpus, whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS, ROLES, distance_km, validate_result
from ..variants import winner_stream
from . import whole_winner_trial as trial
from .full_receiver_comparison import read, require_fields, seal, sha
from .winner_stream_results import csv_file, scientific_result

MODES = {"stock": "whole_winner_stock", "private": "whole_winner"}
CASES = sorted(trial.SCHEDULE)
POSITIONS = "positions.jsonl.gz"
SOURCES = "as-measured-source.tar.gz"
SUPPORT = (
    "input_manifest_sha256",
    "raw_authority",
    "clock_sha256",
    "excluded_sha256",
    "probes_sha256",
)


def snapshot(work, study, case, mode):
    folder = work / "attempts" / case / mode
    expected = study["cases"][case]
    plan = read(folder / "plan.json")
    service = read(folder / "service.json")
    require_fields(
        plan,
        dict(
            case=case,
            cpus=list(trial.CPUS),
            limit_s=trial.LIMIT,
            capture_era_request=expected["frozen_request_sha256"],
            recording=expected["recording"],
            detector_sha256=study["detector_sha256"],
            receiver_files=study["bindings"][mode],
        ),
    )
    require_fields(service["binding"], dict(plan_sha256=sha(folder / "plan.json")))
    if service["log_sha256"] != sha(folder / "service.log"):
        raise ValueError("whole-IQ terminal service log differs from its sealed receipt")
    raw = read(folder / "raw.json") if (folder / "raw.json").exists() else None
    end = read(folder / "end.json") if (folder / "end.json").exists() else None
    start = read(folder / "start.json") if (folder / "start.json").exists() else None
    completed = whole_iq.iq_service.succeeded(service) and end is not None
    files = folder / "recording"
    observed = None
    lane_bytes = sum(f.stat().st_size for f in files.glob("replayed-*.jsonl"))
    lane_hashes = [sha(p) for p in sorted(files.glob("replayed-*.jsonl"))]
    if raw:
        require_fields(raw, {"native_sha256": "sha256:" + expected["native_sha256"]})
        require_fields(start, {"cpus": list(trial.CPUS), "nice": study["nice"]})
        marks = [start, raw["raw_end"], raw["position_start"]] + ([end] if end else [])
        for marker in marks:
            if (
                marker["cgroup"] != start["cgroup"]
                or marker["memory.max"] != study["memory"]
                or marker["memory.swap.max"]
                or marker["memory.swap.current"]
            ):
                raise ValueError("recorded-IQ worker left its original resource envelope")
        case_row, original = whole_iq.binding(case)
        capture = read(files / "capture.json")
        from .capture_release import producer

        decoder = str(producer(case_row, capture).root)
        if mode == "stock":
            native = whole_iq.checked(files / "native.json", raw["native_sha256"])
            actual_request = whole_iq.checked(files / "request.json", raw["request_sha256"])
            whole_iq.verify_request(
                read(actual_request),
                original,
                native_path=str(native),
                native_sha256=raw["native_sha256"],
            )
            with native.open("rb") as stream:
                private_digest, private_bytes = winner_stream.convert(
                    stream,
                    io.BytesIO(),
                    expected["native_sha256"],
                )
            handoff_bytes = native.stat().st_size
        else:
            request = whole_iq.checked(
                folder / "position-request.json", raw["position_request_sha256"]
            )
            if read(request) != original or (files / "native.json").exists():
                raise ValueError(
                    "private receiver changed the original request or wrote public factors"
                )
            require_fields(
                raw, dict(capture_sha256=sha(files / "capture.json"), decoder_root=decoder)
            )
            private = whole_iq.checked(files / "native.winners", raw["private_sha256"])
            private_digest, private_bytes = raw["private_sha256"], private.stat().st_size
            handoff_bytes = raw["handoff_bytes"]
            if handoff_bytes != private_bytes:
                raise ValueError("private handoff byte count differs from the delivered file")
            for i, digest in enumerate(raw["lane_sha256"]):
                whole_iq.checked(files / f"replayed-{i}.jsonl", digest)
        observed = dict(
            **{key: raw[key] for key in SUPPORT},
            private_sha256=private_digest,
            private_bytes=private_bytes,
            counts={k: v for k, v in raw["counts"].items() if k != "detector_cpu_s"},
            capture_sha256=sha(files / "capture.json"),
            decoder=decoder,
            compressed_bytes=[row["compressed_bytes"] for row in raw["lanes"]],
            compressed_chunks=[row["compressed_chunks"] for row in raw["lanes"]],
        )
    else:
        handoff_bytes = None
    if completed:
        result = read(folder / "position.json")
        validate_result(result)
    else:
        failure = service["systemd"].get("Result")
        result = dict(
            status="timed_out" if failure == "timeout" else "failed",
            reason=f"Saved-IQ service {failure}",
            metrics={},
            arms={arm: dict(latlon=None) for arm in ARMS},
        )
    return dict(
        id=case,
        method=MODES[mode],
        role=mode,
        result=result,
        mode="matched-tile",
        tile=expected["tile"],
        native_sha256=expected["native_sha256"],
        catalog_sha256=expected["catalog_sha256"],
        capture_native_sha256=expected["capture_native_sha256"],
        input_sha256=expected["frozen_request_sha256"],
        decoder_provenance=observed,
        start=start,
        raw_end=raw["raw_end"] if raw else None,
        end=end,
        position_start=raw["position_start"] if raw else None,
        handoff_bytes=handoff_bytes,
        lane_bytes=lane_bytes,
        lane_sha256=lane_hashes,
        detector_cpu_s=raw["counts"]["detector_cpu_s"] if raw else None,
        service=service,
    )


def score(source, dest, *, packing=False):
    names = (POSITIONS, "source-lock.json", SOURCES)
    if not packing:
        receipt = seal(source, "prediction-lock.json", names)
        require_fields(
            receipt, dict(cases=CASES, source_lock_sha256=sha(source / "source-lock.json"))
        )
    study = read(source / "source-lock.json")
    with tarfile.open(source / SOURCES, "r:gz") as archive:
        for name, pin in study["sources"].items():
            content = archive.extractfile(name)
            if content is None or sha256(content.read()).hexdigest() != pin:
                raise ValueError("the archived measurement source differs from the frozen plan")
    require_fields(
        study, dict(cpu_pins=list(trial.CPUS), limit_s=trial.LIMIT, memory=whole_iq.MEMORY, swap=0)
    )
    with gzip.open(source / POSITIONS, "rt") as stream:
        rows = [json.loads(line) for line in stream]
    if [(r["id"], r["role"]) for r in rows] != [(i, role) for i in CASES for role in MODES]:
        raise ValueError("missing, duplicate or changed full-IQ pair")
    measured = {(r["id"], r["role"]): r for r in rows}
    for ident in CASES:
        first, second = (measured[ident, role] for role in study["cases"][ident]["order"])
        if (
            first["end"] is not None
            and second["start"] is not None
            and first["end"]["monotonic_s"] > second["start"]["monotonic_s"]
        ):
            raise ValueError("full-IQ pair overlapped or used a different measurement order")
    refs = {r["id"]: r for r in corpus.references("roof16")}
    scores, resources, comparisons = [], [], {}
    control = {}
    for row in rows:
        ident, role, result = (row[k] for k in ("id", "role", "result"))
        bound = study["cases"][ident]
        require_fields(
            row,
            {
                k: bound[k]
                for k in ("native_sha256", "catalog_sha256", "tile", "capture_native_sha256")
            },
        )
        validate_result(result)
        before, after, raw, position = (
            row[key] for key in ("start", "end", "raw_end", "position_start")
        )
        service = row["service"]
        resources.append(
            dict(
                id=ident,
                role=role,
                status=result["status"],
                reason=result.get("reason"),
                service_result=service["systemd"]["Result"],
                supervisor_wall_s=service["supervisor_s"],
                complete_iq_wall_s=after["monotonic_s"] - before["monotonic_s"] if after else None,
                complete_iq_cpu_s=(after["cpu.stat.usage_usec"] - before["cpu.stat.usage_usec"])
                / 1e6
                if after
                else None,
                effective_peak_mib=after["memory.peak"] / 2**20 if after else None,
                swap_bytes=after["memory.swap.current"] if after else None,
                oom_kills=after["memory.events.oom_kill"] if after else None,
                raw_wall_s=raw["monotonic_s"] - before["monotonic_s"] if raw else None,
                detector_cpu_s=row["detector_cpu_s"],
                handoff_wall_s=position["monotonic_s"] - raw["monotonic_s"] if position else None,
                handoff_cpu_s=(position["cpu.stat.usage_usec"] - raw["cpu.stat.usage_usec"]) / 1e6
                if position
                else None,
                handoff_process_peak_mib=position["rss_peak_kib"] / 1024 if position else None,
                handoff_bytes=row["handoff_bytes"],
                lane_bytes=row["lane_bytes"],
                position_s=after["monotonic_s"] - position["monotonic_s"] if after else None,
            )
        )
        for name in ARMS:
            arm, ref = result["arms"][name], refs[ident]
            point = arm.get("latlon")
            scores.append(
                dict(
                    id=ident,
                    role=role,
                    arm=name,
                    status=result["status"],
                    error_km=distance_km(point, ref["truth"]) if point is not None else None,
                    conditional_rms_hz=arm.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(f"{name}_frequency_score"),
                    **{k: ref["reference"][k][name]["error_km"] for k in ROLES},
                )
            )
        if role == "stock":
            control[ident] = row
        else:
            stock = control[ident]
            paired = after is not None and stock["end"] is not None
            comparisons[ident] = dict(
                paired=paired,
                exact=scientific_result(stock["result"]) == scientific_result(result)
                if paired
                else None,
                identical_handoff_projection=stock["decoder_provenance"]
                == row["decoder_provenance"]
                if row["decoder_provenance"] and stock["decoder_provenance"]
                else None,
            )
    dest.mkdir(exist_ok=True, parents=True)
    csv_file(dest / "scores.csv", scores)
    csv_file(dest / "resources.csv", resources)
    save_json(dest / "parity.json", comparisons)
    if packing:
        artifacts = (*names, "parity.json", "scores.csv", "resources.csv")
        if (dest / "initial-launch.json").exists():
            artifacts += ("initial-launch.json",)
        save_json(
            dest / "prediction-lock.json",
            dict(
                cases=CASES,
                source_lock_sha256=sha(source / "source-lock.json"),
                files={n: sha(dest / n) for n in artifacts},
            ),
        )
    return comparisons


def pack(work, out):
    out.mkdir(exist_ok=True, parents=True)
    path = whole_iq.checked(work / "study.json", (work / "study.sha256").read_text().strip())
    (out / "source-lock.json").write_bytes(path.read_bytes())
    study = read(path)
    if not (out / SOURCES).is_file():
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for name, pin in study["sources"].items():
                content = whole_iq.checked(ROOT / name, pin).read_bytes()
                member = tarfile.TarInfo(name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        (out / SOURCES).write_bytes(gzip.compress(buffer.getvalue(), mtime=0))
    rows = [snapshot(work, study, ident, mode) for ident in CASES for mode in MODES]
    data = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
    (out / POSITIONS).write_bytes(gzip.compress(data, mtime=0))
    return score(out, out, packing=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=local_output)
    p.add_argument("--out", default=trial.REPORT, type=local_output)
    p.add_argument("--pack", action="store_true")
    args = p.parse_args()
    print(json.dumps((pack if args.pack else score)(args.source, args.out), indent=2))


if __name__ == "__main__":
    main()
