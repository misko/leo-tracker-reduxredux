"""Replay and seal the independent blind phase-acquisition study."""

import argparse
import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, read_predictions, save_json, write
from ..scoring import validate_result
from ..variants import phase_capture as method
from . import native_joint_full as full
from . import native_joint_trial as joint

OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/refinement/phase-capture"
WORKER = Path(__file__).with_name("phase_capture_worker.py")
DEVELOPMENT = ("DS26-0223", "DS29-0316")
CONFIRMATION = ("DS26-0120", "DS26-0150", "DS29-0604", "DS29-0519")
OMITTED = ("DS26-0277-omitted", "DS29-0127-omitted")
IDS = (*DEVELOPMENT, *CONFIRMATION, *OMITTED)
CPUS = (4, 5)
CAP = 130


def setup():
    locked = joint.phase._read(full.REPORT / "prediction-lock.json")
    joint.secant_full._verify_files(full.REPORT, locked["files"])
    archived = read_predictions(full.REPORT / "positions.jsonl.gz")
    plan = joint.phase._read(full.REPORT / "plan.json")
    queries = {row["id"]: row for row in plan["cases"]}
    candidates = joint.phase.frozen_inputs()
    framed = []
    for ident in IDS:
        row = queries[ident]
        item = candidates.get(row["recording"]) or joint.native._load_case(row["recording"])
        packet, paths = joint.native.request(item, "native", offer=row["packet"]["offer"])
        receipt = archived[ident]
        expected = joint.phase.corpus._sha(encoded(packet))
        if packet != row["packet"] or receipt["input_sha256"] != expected:
            raise ValueError(f"{ident} differs from its original native joint request")
        framed.append((row, paths, receipt))
    return framed, dict(
        cases=[row for row, _, _ in framed],
        cpus=list(CPUS),
        timeout_s=CAP,
        frozen=joint.sources(joint.BUNDLE),
        sources={
            str(path.relative_to(ROOT)): joint.phase.digest(path)
            for path in (Path(__file__), WORKER, Path(method.__file__), OUTPUT / "PROTOCOL.md")
        },
        reference_plan_sha256=joint.phase.digest(full.REPORT / "plan.json"),
        reference_predictions_sha256=joint.phase.digest(full.REPORT / "positions.jsonl.gz"),
    )


def measure(job, cpu):
    row, paths, control = job
    packet = row["packet"]
    command = joint.command(cpu, paths, joint.BUNDLE)
    command[command.index(str(joint.WORKER))] = str(WORKER)
    command[-3:-3] = [
        "--ro-bind",
        str(Path(method.__file__)),
        "/worker/tools/pipeline_eval/variants/phase_capture.py",
    ]
    raw = encoded(packet)
    start = perf_counter()
    try:
        proc = subprocess.run(command, input=raw, capture_output=True, check=True, timeout=CAP)
        out = json.loads(proc.stdout)
        if (
            control.get("observation_sha256")
            and out["observation_sha256"] != control["observation_sha256"]
        ):
            raise ValueError("Graph differs from the authenticated original trial")
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1800:]
        out = dict(
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=detail or str(err),
                boundary=method.BOUNDARY,
                metrics={},
                arms={arm: dict(latlon=None, forced_latlon=None) for arm in method.lean.ARMS},
            )
        )
    validate_result(out["result"])
    out.update(
        {k: row[k] for k in ("id", "recording", "cohort")},
        method=method.METHOD,
        cpu=cpu,
        worker_wall_s=perf_counter() - start,
        input_sha256=control["input_sha256"],
        native_sha256=packet["native"]["sha256"],
        catalog_sha256=packet["catalogue"]["sha256"],
        tile=packet["offer"],
    )
    print(
        out["id"],
        out["result"]["status"],
        out["result"]["reason"],
        "anchors",
        out["result"]["metrics"].get("captured_orbits"),
        round(out["worker_wall_s"], 2),
        flush=True,
    )
    return out


def run(work):
    jobs, manifest = setup()
    work.mkdir(parents=True, exist_ok=False)
    save_json(OUTPUT / "plan.json", manifest)
    start = perf_counter()

    def lane(i):
        for job in jobs[i::2]:
            row = measure(job, CPUS[i])
            save_json(work / (row["id"] + ".json"), row)

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lane, range(2)))
    _, current = setup()
    if current != manifest:
        raise ValueError("locked input and source changed during measurement")
    rows = [joint.phase._read(work / (k + ".json")) for k in IDS]
    trace = [dict(id=r["id"], **r.pop("phase_evidence")) for r in rows if "phase_evidence" in r]
    write(
        OUTPUT / "positions.jsonl.gz",
        gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0),
    )
    write(
        OUTPUT / "phase-evidence.jsonl.gz",
        gzip.compress(b"".join(encoded(r) + b"\n" for r in trace), mtime=0),
    )
    files = ["positions.jsonl.gz", "phase-evidence.jsonl.gz", "plan.json", "PROTOCOL.md"]
    save_json(
        OUTPUT / "prediction-lock.json",
        dict(
            cases=list(IDS),
            wall_s=perf_counter() - start,
            files={name: joint.phase.digest(OUTPUT / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    run(parser.parse_args().work)
