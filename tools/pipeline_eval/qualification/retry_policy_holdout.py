"""Replay both original primaries on every final-positive DS26-0162 visit."""

import argparse
import json
import subprocess
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, encoded, save_json
from ..variants import retry_cadence, retry_policy_holdout
from ..variants.selective_capture import visit_pairs
from . import scheduled_capture_waveform
from . import single_pass_position as lower
from .full_v5_check import _sha

IDENT = "DS26-0162"
REPORT = ROOT / "reports/2026_11_19_receiver_screening/retry-and-transfer/retry-policy-holdout"
WORK = Path("/srv/bulk/leo-dev/retry-policy-holdout-20261119-A")
ASSAY = lower.assay
BASE = lower.base
CPUS = (2, 3, 4, 5)
MODULE = "tools.pipeline_eval.qualification.retry_policy_holdout"
METHOD = "holdout_primary12"


@contextmanager
def configured():
    with patch.multiple(BASE, IDENT=IDENT, REPORT=REPORT, METHOD=METHOD, MODULE=MODULE):
        yield


def signed_archive(lock):
    location = lock["original"]["native"]
    return whole_iq.read(whole_iq.checked(BASE.BULK / location["path"], location["sha256"]))


def roster(probes):
    return {visit for visit, pair in probes.items() if any(map(ASSAY.positive, pair))}


def witnesses(probes, excluded):
    result = []
    for hits in ((False, False), (False, True), (True, False), (True, True)):
        choices = [
            v
            for v, p in probes.items()
            if v not in excluded and tuple(map(ASSAY.positive, p)) == hits
        ]
        result.extend(
            sorted(choices, key=lambda v: sha256(encoded([IDENT, "primary-v1", v])).digest())[:2]
        )
    return sorted(result)


def freeze(work):
    from .fresh_replay_results import sealed

    if work.exists() or (REPORT / "source-lock.json").exists():
        raise FileExistsError("use a new prospective replay scope")
    case, request = whole_iq.binding(IDENT)
    config = sealed(lower.prior.REPORT, "prediction-lock.json")
    predecessor = whole_iq.checked(
        lower.prior.REPORT / "source-lock.json", config["files"]["source-lock.json"]
    )
    reference = whole_iq.read(predecessor)
    assay = sealed(ASSAY.REPORT, "qualification-lock.json")
    input_path = whole_iq.checked(
        ASSAY.REPORT / "input-lock.json", assay["files"]["input-lock.json"]
    )
    input_ = whole_iq.read(input_path)["cases"][IDENT]
    prior_path = whole_iq.checked(
        ASSAY.REPORT / f"{IDENT}.json.gz", assay["files"][f"{IDENT}.json.gz"]
    )
    release = input_["producer"]
    capture = BASE.capture_release.read_capture(case)
    producer = BASE.capture_release.producer(case, capture)
    capture["case"] = {k: case[k] for k in ("id", "run_id", "session_id")}
    if (
        str(producer.root) != release["producer"]
        or capture["edge"] != "upper"
        or capture["input_manifest_sha256"] != release["input_manifest_sha256"]
    ):
        raise ValueError("independent waveform assay refers to another capture")
    original = dict(
        native=case["native"],
        request=case["request"],
        catalog=case["catalog"],
        tile=case["regions"][0],
        causal_snapshots=request["causal_snapshots"],
    )
    archive = signed_archive(dict(original=original))
    probes = dict(visit_pairs(archive["source"]["probes"]))
    selected = roster(probes)
    sequence, chunks = scheduled_capture_waveform.metadata(case)
    invalid = {r["visit"] for r in archive["provenance"]["excluded_windows"]}
    if (len(probes), len(selected)) != (6713, 3153) or set(range(len(sequence))) != set(
        probes
    ) | invalid:
        raise ValueError("signed physical support and final gate roster disagree")
    controls = witnesses(probes, {r["visit"] for r in input_["rows"]})
    smoke = []
    for visit in controls:
        segment, _, _, offset = next(c for c in chunks if c[3] + c[1] <= visit < c[3] + c[2])
        smoke.append((segment, visit - offset, visit))
    with patch.object(lower, "CPUS", CPUS):
        workers = lower.partition(chunks, selected)
    bindings = (
        Path(__file__),
        Path(lower.__file__),
        Path(ASSAY.__file__),
        Path(ASSAY.single_pass.__file__),
        Path(retry_policy_holdout.__file__),
        Path(__file__).with_name("retry_cadence_trial.py"),
        Path(retry_cadence.__file__),
        REPORT / "PROTOCOL.md",
    )
    sources = release["sources"] | {str(p): _sha(p) for p in bindings}
    readable = {p: h for p, h in sources.items() if Path(p).stat().st_mode & 4}
    work.mkdir(mode=0o755)
    inputs = work / "smoke-input.json"
    save_json(inputs, {str(v): probes[v] for v in controls})
    inputs.chmod(0o644)
    seal = dict(
        id=IDENT,
        capture=capture,
        recording=case["recording"],
        original=original,
        producer=str(producer.root),
        sources=readable,
        workers=workers,
        smoke=smoke,
        signed_archive_sha256=case["native"]["sha256"],
        selected=sorted(selected),
        invalid=sorted(invalid),
        python=reference["python"],
        python_sha256=reference["python_sha256"],
        raw_limit_s=720,
        position_limit_s=180,
        smoke_input_sha256=_sha(inputs),
        independent=dict(
            path=str(prior_path),
            sha256=_sha(prior_path),
            input=str(input_path),
            input_sha256=_sha(input_path),
        ),
        evidence_sources={str(p): _sha(p) for p in (predecessor, input_path, prior_path)}
        | {p: h for p, h in sources.items() if p not in readable},
        **{k: reference[k] for k in ("receiver", "receiver_files", "libraries", "memory_max")},
    )
    for dest in (work / "source-lock.json", REPORT / "source-lock.json"):
        save_json(dest, seal)
        dest.chmod(0o644)
    BASE.configure(work)
    print(
        "Authenticated positive-gate roster",
        [(cpu, n, len(spans)) for cpu, n, spans in workers],
        flush=True,
    )


def smoke(work):
    lock, libs = BASE.configure(work)
    references = whole_iq.read(
        whole_iq.checked(work / "smoke-input.json", lock["smoke_input_sha256"])
    )
    rows = []
    with lower.detector(lock, libs) as evaluate:
        for segment, first, visit in lock["smoke"]:
            (window,) = BASE.open_span(lock, segment, first, first + 1).windows()
            primary, pt = evaluate(window, "primary12")
            conditional, ct = evaluate(window, "conditional")
            if (
                window.acquisition["global_visit"] != visit
                or conditional["probes"] != references[str(visit)]
                or conditional["attempts"][:2] != primary["attempts"]
                or (
                    len(conditional["attempts"]) == 2 and primary["public"] != conditional["public"]
                )
            ):
                raise ValueError(f"independent raw preflight changed at visit {visit}")
            rows.append(
                dict(
                    visit=visit,
                    iq_sha256=window.iq_sha256,
                    primary=primary,
                    conditional=conditional,
                    primary_timing=pt,
                    conditional_timing=ct,
                )
            )
    print(encoded(dict(rows=rows, source_lock_sha256=_sha(work / "source-lock.json"))).decode())


def raw(work, cpu):
    from leo.storage import short_window

    lock, libs = BASE.configure(work)
    _, total, chunks = next(x for x in lock["workers"] if x[0] == cpu)
    selected = set(lock["selected"])
    start, measured, verified = BASE.resources.memory(), 0, []
    if start["cpus"] != [cpu]:
        raise ValueError("worker outside its planned CPU")
    member = short_window.ShortWindowReader._member

    def stream(reader, name, size, digest):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return BASE.resources.AuthenticatedMember(path, size, digest, verified)
        return member(reader, name, size, digest)

    def emit(record):
        print(encoded(record).decode(), flush=True)

    with (
        lower.detector(lock, libs) as evaluate,
        patch.object(short_window.ShortWindowReader, "_member", stream),
    ):
        for segment, first, stop, offset in chunks:
            source = BASE.open_span(lock, segment, first, stop)
            count, before, previous = 0, perf_counter(), len(verified)
            for sequence, window in enumerate(source.windows(), first):
                visit = offset + sequence
                if (
                    visit != window.acquisition["global_visit"]
                    or sequence != window.sequence
                    or window.target["edge"] != lock["capture"]["edge"]
                ):
                    raise ValueError("signed visit order or physical edge changed")
                if visit in selected:
                    result, timing = evaluate(window, "primary12")
                    emit(
                        dict(
                            kind="visit",
                            segment=segment,
                            sequence=sequence,
                            visit=visit,
                            iq_sha256=window.iq_sha256,
                            probes=result["probes"],
                            attempts=result["attempts"],
                            **timing,
                        )
                    )
                    measured += 1
                count += 1
            if count != stop - first or len(verified) != previous + 1:
                raise ValueError("capture chunk was incomplete or failed authentication")
            emit(
                dict(
                    kind="chunk",
                    segment=segment,
                    first=first,
                    stop=stop,
                    manifest_digest=source.manifest_digest,
                    compressed_bytes=verified[-1],
                    wall_s=perf_counter() - before,
                )
            )
    if measured != total:
        raise ValueError("measured visits differ from the frozen final-positive roster")
    emit(
        dict(
            kind="worker",
            cpu=cpu,
            count=measured,
            start=start,
            end=BASE.resources.memory(),
            source_lock_sha256=_sha(work / "source-lock.json"),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "smoke", "run", "raw"))
    parser.add_argument("work", type=Path, nargs="?", default=WORK)
    parser.add_argument("cpu", type=int, nargs="?", default=CPUS[0])
    args = parser.parse_args()
    with configured():
        if args.action == "freeze":
            freeze(args.work)
        elif args.action == "preflight":
            result = subprocess.run(
                BASE.service(
                    f"leo-holdout-preflight-{uuid4().hex[:8]}",
                    100,
                    BASE.command(args.work, args.cpu, "smoke"),
                ),
                check=True,
                stdout=subprocess.PIPE,
                timeout=115,
            )
            save_json(args.work / "smoke.json", json.loads(result.stdout))
        elif args.action == "smoke":
            smoke(args.work)
        elif args.action == "run":
            lock, _ = BASE.configure(args.work)
            for source, digest in lock["evidence_sources"].items():
                whole_iq.checked(Path(source), digest)
            BASE.run(args.work)
        else:
            raw(args.work, args.cpu)


if __name__ == "__main__":
    main()
