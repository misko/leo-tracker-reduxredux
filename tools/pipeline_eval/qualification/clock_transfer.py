"""Seal the four frozen native clock models on independent blind GLRT factors."""

import argparse
import gzip
import json
import os
import secrets
import subprocess
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import perf_counter

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distribution, validate_result
from . import clock_offset_results as original
from . import clock_offset_trial as reference
from . import clock_transfer_inputs as custodian
from .fresh_scenes import _new, _read, _score_rows, _sha
from .full_v5_check import BULK, _load_case

ROOT = custodian.ROOT
REPORT = ROOT / "reports/2026_11_19_receiver_screening/recovery/clock-transfer"
ARCHIVE = "predictions.jsonl.gz"
METHODS = original.METHODS
CPUS = {13, 14}
CAP = 45
BATCH = 480
FROZEN = {
    str(
        Path("tools/pipeline_eval/variants") / "clock_offset.py"
    ): "d354090c42709d28805d8668ca5cdd68dd932e13d7625caf54ce25a5e0afbcca",
    str(
        Path("tools/pipeline_eval/qualification") / "clock_offset_worker.py"
    ): "8622534a262054a3f263dd9bebd4a0e4b8d8154a2b217c593fc00e1680e8c720",
    str(
        Path("tools/pipeline_eval/variants") / "marginal_offset.py"
    ): "8839eb317aa07cade9e695b3a775bac3c55ca8f91e8910d7a815a99c03df9cc6",
    str(
        Path("tools/pipeline_eval/variants") / "joint_clock_model.py"
    ): "80d5c75b783d29d07a869bcd96ec0d9ffca805d34a054adfc190477e656cac9c",
    str(
        (reference.REPORT / "prediction-lock.json").relative_to(ROOT)
    ): "601ad20889937be7feffe3e2c985c3848a5d5781721b9daf5318102f5cc05623",
}


def source_bindings(bundle):
    if any(_sha(ROOT / name) != digest for name, digest in FROZEN.items()):
        raise ValueError("a four-model source differs from the sealed physical release")
    extra = (
        Path(__file__),
        REPORT / "PROTOCOL.md",
        Path(custodian.__file__),
        Path(custodian.empirical.__file__),
        Path(custodian.cold.__file__),
        custodian.empirical.TRACE,
        custodian.empirical.AUDIT,
        *custodian.PAST,
        Path(reference.__file__),
        Path(original.__file__),
        ROOT / "tools/pipeline_eval/qualification/native_joint_full_results.py",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
    )
    return dict(
        physical_release=FROZEN,
        files={str(p.resolve().relative_to(ROOT)): _sha(p) for p in extra},
        streamed_dependencies=reference.base.base.sources(bundle),
        methods=list(METHODS),
    )


def prepare(root, bundle):
    root.mkdir(mode=0o700)
    _new(root / "source-lock.json", source_bindings(bundle))
    selector = custodian.snapshots()
    _new(root / "catalogue-inventory.json", selector)
    donor, receipts = custodian.empirical.donors()
    _new(root / "donor-receipt.json", receipts)
    config = _load_case("DS26-0036")["track_config"]
    path = BULK / config["path"]
    if _sha(path) != config["sha256"]:
        raise ValueError("the archive Graph constants changed")
    custodian.generate(root, donor, secrets.token_bytes(32), selector, path.read_bytes())
    _new(
        root / "input-lock.json",
        dict(
            public={str(f.relative_to(root)): _sha(f) for f in sorted((root / "public").iterdir())},
            private={
                str(f.relative_to(root)): _sha(f) for f in sorted((root / "private").iterdir())
            },
            sources={
                name: _sha(root / name)
                for name in (
                    "source-lock.json",
                    "donor-receipt.json",
                    "catalogue-inventory.json",
                )
            },
        ),
    )


def _public(root, bundle):
    seal = _read(root / "input-lock.json")
    if _read(root / "source-lock.json") != source_bindings(bundle) or any(
        _sha(root / p) != sha for p, sha in (seal["public"] | seal["sources"]).items()
    ):
        raise ValueError("the source or public input differs from the prospective seal")
    rows = _read(root / "public/requests.json")
    if len(rows) != 25 or len({r["id"] for r in rows}) != 25:
        raise ValueError("transfer requires 25 distinct offers")
    return rows


def _attempt(root, row, cpu, bundle):
    packet, raw = row["packet"], encoded(row["packet"])
    public = root / "public"
    paths = dict(
        native=public / f"{row['capture_id']}.json",
        catalogue=public / f"{packet['catalogue']['sha256']}.tle",
        track_config=public / "track-config.json",
    )
    start = perf_counter()
    try:
        completed = subprocess.run(
            reference.command(cpu, paths, bundle),
            input=raw,
            capture_output=True,
            check=True,
            timeout=CAP,
        )
        outcome = json.loads(completed.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        stderr = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1500:]
        status = "timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed"
        outcome = dict(result=reference.base.failed(status, stderr or str(err)))
    validate_result(outcome["result"])
    elapsed = perf_counter() - start
    print(row["id"], outcome["result"]["status"], round(elapsed, 2), flush=True)
    return dict(
        id=row["id"],
        capture_id=row["capture_id"],
        cohort="blind",
        tile=packet["offer"],
        method=METHODS[0],
        mode="supplied-tile",
        wall_s=elapsed,
        **outcome,
        input_sha256=custodian.cold._sha(raw),
        native_sha256=packet["native"]["sha256"],
        catalog_sha256=packet["catalogue"]["sha256"],
        cpu=cpu,
    )


def predict(root, bundle):
    cpus = sorted(os.sched_getaffinity(0))
    if not cpus or not set(cpus) <= CPUS:
        raise ValueError("pin the transfer to CPUs13 and 14")
    queries = _public(root, bundle)
    started, remaining, guard = perf_counter(), deque(queries), Lock()

    def lane(cpu):
        results = []
        while perf_counter() - started < BATCH - CAP - 5:
            with guard:
                if not remaining:
                    break
                row = remaining.popleft()
            results.append(_attempt(root, row, cpu, bundle))
        return results

    with ThreadPoolExecutor(len(cpus)) as pool:
        rows = [r for batch in pool.map(lane, cpus) for r in batch]
    for row in remaining:
        packet = row["packet"]
        rows.append(
            dict(
                id=row["id"],
                capture_id=row["capture_id"],
                cohort="blind",
                tile=packet["offer"],
                method=METHODS[0],
                mode="supplied-tile",
                wall_s=None,
                input_sha256=custodian.cold._sha(encoded(packet)),
                native_sha256=packet["native"]["sha256"],
                catalog_sha256=packet["catalogue"]["sha256"],
                result=reference.base.failed("missing", "not started before the batch deadline"),
            )
        )
    groups = original._models({r["id"]: r for r in rows}, {})
    if any(len(sample) != 25 for sample in groups.values()):
        raise ValueError("every four-model offer must remain in the prediction roster")
    _public(root, bundle)
    data = gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0)
    custodian.cold._new(root / ARCHIVE, data)
    _new(
        root / "prediction-lock.json",
        dict(
            input_lock_sha256=_sha(root / "input-lock.json"),
            predictions_sha256=_sha(root / ARCHIVE),
            cases=[q["id"] for q in queries],
            methods=list(METHODS),
            worker_wall_s=perf_counter() - started,
            statuses=dict(Counter(r["result"]["status"] for r in rows)),
        ),
    )


def _verify(root, bundle):
    queries = _public(root, bundle)
    lock = _read(root / "prediction-lock.json")
    if (
        lock["input_lock_sha256"] != _sha(root / "input-lock.json")
        or lock["predictions_sha256"] != _sha(root / ARCHIVE)
        or lock["cases"] != [r["id"] for r in queries]
        or lock["methods"] != list(METHODS)
    ):
        raise ValueError("unsealed clock transfer predictions")
    with gzip.open(root / ARCHIVE, "rt") as stream:
        records = list(map(json.loads, stream))
    if len(records) != 25 or {r["id"] for r in records} != set(lock["cases"]):
        raise ValueError("incorrect prediction roster")
    indexed = {r["id"]: r for r in queries}
    for row in records:
        plan = indexed[row["id"]]
        packet = plan["packet"]
        binding = dict(
            capture_id=plan["capture_id"],
            tile=packet["offer"],
            input_sha256=custodian.cold._sha(encoded(packet)),
            native_sha256=packet["native"]["sha256"],
            catalog_sha256=packet["catalogue"]["sha256"],
        )
        if any(row[key] != value for key, value in binding.items()):
            raise ValueError("prediction changed the shared Graph input")
    return original._models({r["id"]: r for r in records}, {})


def score(root, output, bundle):
    results = _verify(root, bundle)
    lock = _read(root / "input-lock.json")
    if any(_sha(root / name) != sha for name, sha in lock["private"].items()):
        raise ValueError("private targets differ from the prospective commitment")
    targets = _read(root / "private/truth.json")
    cases = []
    compact = {
        q: dict(
            row,
            condition=(
                "present"
                if not row["condition"].endswith("outside") and row["condition"] != "shuffle"
                else "missing"
                if row["condition"] != "shuffle"
                else "shuffle"
            ),
        )
        for q, row in targets.items()
    }
    for rows in results.values():
        for row in rows.values():
            for result in _score_rows([row], compact):
                arm = result["arm"]
                metrics = row["result"]["metrics"]
                held = metrics.get("conditional_held_by_arm", {}).get(arm, {})
                fitted = metrics.get("final_model", {}).get(arm, {})
                cases.append(
                    dict(
                        result,
                        role=targets[row["id"]]["condition"],
                        margin_km=targets[row["id"]]["margin_km"],
                        fitted_conditional_hz=fitted.get("fit_conditional_rf_rms_hz"),
                        held_conditional_hz=held.get("conditional_held_rf_rms_hz"),
                        held_deviance=held.get("held_deviance_per_point"),
                        held_points=held.get("held_points"),
                    )
                )
    groups = []
    for method in METHODS:
        for arm in ARMS:
            for condition in custodian.KINDS:
                subset = [
                    r
                    for r in cases
                    if (r["method"], r["arm"], r["role"]) == (method, arm, condition)
                ]
                groups.append(
                    dict(
                        method=method,
                        arm=arm,
                        role=condition,
                        attempts=len(subset),
                        published=sum(r["published"] for r in subset),
                        within5=sum(
                            r["error_km"] is not None and r["error_km"] <= 5 for r in subset
                        ),
                        **{
                            k: distribution(r[k] for r in subset)
                            for k in (
                                "error_km",
                                "forced_error_km",
                                "fitted_conditional_hz",
                                "held_conditional_hz",
                                "held_deviance",
                            )
                        },
                    )
                )
    for name in (
        ARCHIVE,
        "source-lock.json",
        "input-lock.json",
        "prediction-lock.json",
        "donor-receipt.json",
    ):
        write(output / name, (root / name).read_bytes())
    for name in ("truth.json", "draws.json"):
        write(output / name, (root / "private" / name).read_bytes())
    write(output / "seed.hex", (root / "private/seed.bin").read_bytes().hex().encode() + b"\n")
    save_json(output / "scores.json", dict(cases=cases, groups=groups))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "predict", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path, default=REPORT)
    parser.add_argument("--bundle", type=Path, default=reference.base.base.BUNDLE)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.root, args.bundle)
    elif args.stage == "predict":
        predict(args.root, args.bundle)
    else:
        score(args.root, args.out, args.bundle)
