"""Seal the preserved terminal receipts after the supervisor stop call failed."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS
from .input_factor_bridge import REPO, _sha, check, read
from .peak_null_trial import METHODS, REPORT

DEADLINE_ID = "DS29-0247"
UNIT = "leo-cavity-transfer-250b559ac9c4.service"


def timeout_receipt(binding, supervisor, transcript, stdout_bytes, deadline_s, cpu):
    enter = int(supervisor["ActiveEnterTimestampMonotonic"])
    leave = int(supervisor["ActiveExitTimestampMonotonic"])
    wall = (leave - enter) / 1e6
    if stdout_bytes or supervisor["Result"] != "timeout" or not deadline_s <= wall < deadline_s + 1:
        raise ValueError("worker has returned output or lacks a verified deadline")
    runtime = {name: [] for name in ("proof", "stage", "finish", "origins")}
    for line in transcript.splitlines():
        label, _, detail = line.partition(" ")
        if label in runtime:
            runtime[label].append(json.loads(detail))
    (proof,) = runtime["proof"]
    if proof["cpu"] != cpu or not proof["cgroup"].endswith("/" + UNIT):
        raise ValueError("service deadline is not bound to this inference process")
    result = dict(
        status="timed_out",
        reason="service deadline with no returned worker stdout",
        boundary="Wide native GLRT factors through the capped phase-release receiver",
        metrics={},
        arms={arm: {"latlon": None} for arm in ARMS},
    )
    return dict(
        binding,
        method=METHODS[0],
        result=result,
        cpu=cpu,
        wall_s=wall,
        exit_code=None,
        runtime=runtime,
        diagnostics=["systemd Result=timeout", "empty stdout"],
        supervisor=supervisor,
    )


def recover(root, report):
    seal = report / "prediction-lock.json"
    if seal.exists():
        raise ValueError("existing prediction seal")
    lock = read(report / "source-lock.json")
    for filename, digest in lock["files"].items():
        check(REPO / filename, digest)
    bundle = Path(lock["receiver_path"])
    for filename, digest in lock["phase_release_files"].items():
        check(bundle / filename, digest)
    requests = read(report / "requests.json")
    partials = [root / f"partial-{index}.json" for index in range(len(lock["worker_cpus"]))]
    rows = [row for path in partials for row in read(path)]
    identifiers = {(row["id"], row["method"]) for row in rows}
    expected = {(ident, method) for ident in lock["cases"] for method in METHODS}
    if len(identifiers) != len(rows) or expected - identifiers != {(DEADLINE_ID, METHODS[0])}:
        raise ValueError("the incomplete output ledger does not match the failed service")
    for ident, pair in requests.items():
        for method, row in pair.items():
            flavor = "adjusted" if method == METHODS[0] else "wide"
            check(root / f"{ident}.{flavor}.json", row["native_sha256"])
    for row in rows:
        if any(row[k] != v for k, v in requests[row["id"]][row["method"]].items()):
            raise ValueError("partial prediction differs from its sealed request")
        scratch = root / row["method"] / "runs" / row["id"] / bundle.name
        check(scratch / "stderr", row["stderr_sha256"])

    terminal = root / f"{DEADLINE_ID}-terminal.service"
    supervisor = dict(line.split("=", maxsplit=1) for line in terminal.read_text().splitlines())
    scratch = root / METHODS[0] / "runs" / DEADLINE_ID / bundle.name
    stderr, stdout = scratch / "stderr", scratch / "stdout"
    stdout_bytes = stdout.stat().st_size
    timeout = timeout_receipt(
        requests[DEADLINE_ID][METHODS[0]],
        supervisor,
        stderr.read_text(),
        stdout_bytes,
        lock["deadline_s"],
        lock["worker_cpus"][1],
    )
    timeout["stderr_sha256"] = _sha(stderr)
    rows.append(timeout)
    receipt = report / "deadline-terminal.json"
    save_json(
        receipt,
        dict(
            unit=UNIT,
            capture=DEADLINE_ID,
            method=METHODS[0],
            supervisor=supervisor,
            stdout_bytes=stdout_bytes,
            stdout_sha256=sha256(b"").hexdigest(),
            stderr_sha256=timeout["stderr_sha256"],
            supervisor_sha256=_sha(terminal),
            partial_sha256={p.name: _sha(p) for p in partials},
            recovered_by_sha256=_sha(Path(__file__)),
        ),
    )
    predictions = report / "predictions.jsonl.gz"
    rows.sort(key=lambda row: (row["id"], row["method"]))
    write(predictions, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    files = (
        "source-lock.json",
        "requests.json",
        "causal-history.json",
        "factor-audit.json",
        "winner-changes.json.gz",
        predictions.name,
        receipt.name,
    )
    save_json(
        seal,
        dict(
            cases=lock["cases"],
            methods=list(METHODS),
            files={name: _sha(report / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=local_output)
    recover(parser.parse_args().root, REPORT)
