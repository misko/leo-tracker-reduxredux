"""Benchmark normal collection and reassemble authentic complete waveform shards."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path

from .. import original_receiver, whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from . import batched_waveform, field_exact_waveform, scout_stage_figures, selector_waveform
from . import capture_whole_results as common
from .fresh_replay_results import sealed
from .full_v5_check import _sha

REPORT = scout_stage_figures.SCREENING / "coarse-and-navigation/scan-accounting"
WORK = Path("/var/tmp/leo-scan-accounting-20261120-A")
BASELINE = ROOT
CANDIDATE = Path("/srv/bulk/leo-dev/pipeline-eval-20261118/clean-checkout")
WORKER = Path(__file__).with_name("scan_accounting_worker.py")
CPU = 13
PASS_ORDER = (
    ("baseline", "candidate"),
    ("candidate", "baseline"),
    ("baseline", "candidate"),
    ("candidate", "baseline"),
)
CASES = {
    "DS26-0237": (selector_waveform.WORK, selector_waveform.REPORT, selector_waveform.METHOD),
    "DS29-0082": (
        field_exact_waveform.WORK,
        field_exact_waveform.REPORT,
        field_exact_waveform.METHOD,
    ),
    "DS29-0519": (batched_waveform.WORK, batched_waveform.REPORT, batched_waveform.METHOD),
}
MODULES = (
    "tools/pipeline_eval/original_receiver.py",
    "tools/pipeline_eval/qualification/capture_whole.py",
    "tools/pipeline_eval/qualification/capture_whole_results.py",
)


def source_diff(old, new):
    counts = {}
    for name in MODULES:
        a = (old / name).read_text().splitlines()
        b = (new / name).read_text().splitlines()
        edits = SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
        counts[name] = dict(
            baseline_lines=len(a),
            candidate_lines=len(b),
            net_change=len(b) - len(a),
            removed_lines=sum(j - i for tag, i, j, _, _ in edits if tag != "equal"),
            added_lines=sum(j - i for tag, _, _, i, j in edits if tag != "equal"),
        )
    return counts


def snapshot(path, digest):
    return REPORT / "sources/qualification" / f"{path.name}.{digest}.gz"


def freeze(work, baseline, candidate, cpu):
    if work.exists() or (REPORT / "plan.json").exists():
        raise FileExistsError("choose a fresh measurement scope")
    if cpu not in os.sched_getaffinity(0):
        raise ValueError("benchmark CPU is outside the available affinity")
    if baseline.resolve() == candidate.resolve():
        raise ValueError("collector versions require separate checkout roots")
    work.mkdir(mode=0o755)
    REPORT.mkdir(parents=True, exist_ok=True)
    sources, roots = {}, dict(baseline=str(baseline), candidate=str(candidate))
    for mode, path in ((m, Path(r)) for m, r in roots.items()):
        sources[mode] = {name: _sha(path / name) for name in MODULES}
        for name in MODULES:
            output = REPORT / "sources" / mode / (Path(name).name + ".gz")
            write(output, gzip.compress((path / name).read_bytes(), mtime=0))
    cases = {}
    for ident, (data, folder, method) in CASES.items():
        receipt = sealed(folder, "prediction-lock.json")
        lock = whole_iq.read(
            whole_iq.checked(data / "source-lock.json", receipt["files"]["source-lock.json"])
        )
        audit = whole_iq.read(
            whole_iq.checked(folder / "audit.json", receipt["files"]["audit.json"])
        )
        native_sha = audit["raw"]["measured_native_sha256"]
        whole_iq.checked(data / "measured.json", native_sha)
        if (
            gzip.decompress(
                whole_iq.checked(
                    folder / "native.json.gz", receipt["files"]["native.json.gz"]
                ).read_bytes()
            )
            != (data / "measured.json").read_bytes()
        ):
            raise ValueError("raw waveform native differs from its published factors")
        persisted = {
            "source-lock.json": receipt["files"]["source-lock.json"],
            "launch.json": receipt["files"]["receipts/launch.json"],
            "raw-exits.json": receipt["files"]["receipts/raw-exits.json"],
            "measured.json": native_sha,
        }
        for cpu_id, _, _ in lock["workers"]:
            worker = audit["raw"]["workers"][str(cpu_id)]
            persisted[f"cpu-{cpu_id}.jsonl"] = worker["output_sha256"]
            persisted[f"cpu-{cpu_id}.log"] = worker["service_log_sha256"]
        for name, digest in persisted.items():
            whole_iq.checked(data / name, digest)
        cases[ident] = dict(
            work=str(data),
            report=str(folder),
            method=method,
            files=persisted,
            prediction_lock_sha256=_sha(folder / "prediction-lock.json"),
            positions_sha256=receipt["files"]["positions.jsonl.gz"],
        )
    plan = dict(
        cases=cases,
        roots=roots,
        sources=sources,
        diff=source_diff(baseline, candidate),
        cpu=cpu,
        pairs=PASS_ORDER,
        worker_sha256=_sha(WORKER),
        orchestrator_sha256=_sha(Path(__file__)),
        runtime=str(sys.executable),
        runtime_sha256=_sha(Path(sys.executable)),
    )
    for path in (WORKER, Path(__file__)):
        write(snapshot(path, _sha(path)), gzip.compress(path.read_bytes(), mtime=0))
    for path in (work / "plan.json", REPORT / "plan.json"):
        save_json(path, plan)
        path.chmod(0o644)


def plan_for(work):
    plan = whole_iq.read(whole_iq.checked(work / "plan.json", _sha(REPORT / "plan.json")))
    for path, field in ((WORKER, "worker_sha256"), (Path(__file__), "orchestrator_sha256")):
        digest = plan[field]
        if _sha(path) != digest and (
            sha256(gzip.decompress(snapshot(path, digest).read_bytes())).hexdigest() != digest
        ):
            raise ValueError("the exact measured qualification code is unavailable")
    return plan


def manifest(work, ident, mode, plan):
    case = plan["cases"][ident]
    target = work / f"{ident}-{mode}-input.json"
    save_json(
        target,
        dict(
            raw_source_lock_sha256=case["files"]["source-lock.json"],
            sources=plan["sources"][mode],
        ),
    )
    target.chmod(0o644)
    return target


def collect_runs(work):
    plan = plan_for(work)
    if plan["worker_sha256"] != _sha(WORKER) or plan["orchestrator_sha256"] != _sha(Path(__file__)):
        raise ValueError("a new timing run needs the same source or a newly frozen experiment")
    receipts = {}
    for ident, case in plan["cases"].items():
        data = Path(case["work"])
        tracked = {mode: manifest(work, ident, mode, plan) for mode in plan["roots"]}
        rows = []
        for pair, sequence in enumerate(plan["pairs"]):
            for order, mode in enumerate(sequence):
                root = plan["roots"][mode]
                env = os.environ | THREAD_ENV | {"PYTHONPATH": root}
                cmd = [
                    "taskset",
                    "-c",
                    str(plan["cpu"]),
                    plan["runtime"],
                    "-BP",
                    str(WORKER),
                    "collect",
                    root,
                    str(data),
                    str(tracked[mode]),
                    str(plan["cpu"]),
                ]
                if pair == 0:
                    cmd += ["--payload", str(work / f"{ident}-{mode}.collection.json")]
                result = subprocess.run(
                    cmd, cwd=work, env=env, stdout=subprocess.PIPE, check=True, timeout=60
                )
                row = json.loads(result.stdout)
                if row["python_sha256"] != plan["runtime_sha256"] or row["checkout"] != root:
                    raise ValueError("unexpected collector process identity")
                rows.append(dict(pair=pair, order=order, mode=mode, command=cmd, **row))
        payloads = [work / f"{ident}-{mode}.collection.json" for mode in plan["roots"]]
        hashes = {_sha(path) for path in payloads}
        if hashes != {r["collection_sha256"] for r in rows} or len(hashes) != 1:
            raise ValueError(f"public worker and chunk collection changed for {ident}")
        for name, digest in case["files"].items():
            whole_iq.checked(data / name, digest)
        receipts[ident] = rows
        print(ident, "public collector agreement", len(rows), "fresh processes", flush=True)
    save_json(work / "collect.json", receipts)


def restore_shards(payload):
    shards = {tuple(key): (chunk, visits) for key, chunk, visits in payload["shards"]}
    if len(shards) != len(payload["shards"]):
        raise ValueError("duplicate chunk key after collection")
    return shards


def scientific(document):
    return dict(
        document,
        source={k: v for k, v in document["source"].items() if k != "analysis_manifest_sha256"},
        provenance={
            k: v
            for k, v in document["provenance"].items()
            if k not in ("scope", "detector_sha256", "run_id")
        },
    )


def assemble(work):
    plan = plan_for(work)
    clocks = whole_iq.read(work / "collect.json")
    audit = {}
    for ident, cfg in plan["cases"].items():
        data = Path(cfg["work"])
        lock = whole_iq.read(data / "source-lock.json")
        case = original_receiver.input_case(ident, None, None)
        pubs = []
        for mode in ("baseline", "candidate"):
            path = work / f"{ident}-{mode}.collection.json"
            digest = {r["collection_sha256"] for r in clocks[ident] if r["mode"] == mode}
            (bound,) = digest
            current = whole_iq.read(whole_iq.checked(path, bound))
            chunks = restore_shards(current)
            doc, counts = common.assemble(case, lock, chunks)
            pubs.append((doc, counts, current))
        (left, lc, first), (right, rc, _) = pubs
        historical = whole_iq.read(
            whole_iq.checked(data / "measured.json", cfg["files"]["measured.json"])
        )
        if (
            encoded(left) != encoded(right)
            or lc != rc
            or encoded(scientific(left)) != encoded(scientific(historical))
        ):
            raise ValueError("the common assembler changed scientific fields")
        native = work / f"{ident}-native.json"
        write(native, encoded(right) + b"\n")
        parity = common.parity(right, historical)
        audit[ident] = dict(
            native_sha256=_sha(native),
            native_scientific_parity=parity,
            historical_native_sha256=cfg["files"]["measured.json"],
            counts=rc,
            original_workers={
                key: row["terminal"]["count"] for key, row in first["workers"].items()
            },
            authenticated_chunks=len(first["shards"]),
            collection_sha256=clocks[ident][0]["collection_sha256"],
            baseline_candidate_native_bytes_equal=True,
        )
        print(ident, "exact fresh-native scientific parity", rc, flush=True)
    save_json(work / "assembly.json", audit)


def position(work, ident):
    plan = plan_for(work)
    seal = work / "source-lock.json"
    if seal.exists():
        whole_iq.checked(seal, _sha(work / "plan.json"))
    else:
        write(seal, (work / "plan.json").read_bytes())
    bound = whole_iq.read(work / "assembly.json")[ident]
    data = Path(plan["cases"][ident]["work"])
    lock = whole_iq.read(
        whole_iq.checked(
            data / "source-lock.json", plan["cases"][ident]["files"]["source-lock.json"]
        )
    )
    case = original_receiver.input_case(ident, None, None)
    original = original_receiver.binding(case)
    native = whole_iq.checked(work / f"{ident}-native.json", bound["native_sha256"])
    from unittest.mock import patch

    with patch.object(common.trial, "IDENT", ident):
        common.terminal_position(
            work,
            ident.lower(),
            native,
            work / f"{ident}-position",
            plan["cpu"],
            lock,
            case,
            original,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "collect", "assemble", "position"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("case", choices=tuple(CASES), nargs="?")
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--candidate", type=Path, default=CANDIDATE)
    parser.add_argument("--cpu", type=int, default=CPU)
    parser.add_argument("--report", type=local_output, default=REPORT)
    args = parser.parse_args()
    REPORT = args.report
    if args.action == "freeze":
        freeze(args.work, args.baseline.resolve(), args.candidate.resolve(), args.cpu)
    elif args.action == "collect":
        collect_runs(args.work)
    elif args.action == "assemble":
        assemble(args.work)
    elif args.case is not None:
        position(args.work, args.case)
    else:
        parser.error("a recording is required for position")
