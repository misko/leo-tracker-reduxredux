"""Run a frozen stored-factor availability cross and matched stock endpoints."""

import argparse
import gzip
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from . import bounded_cavity_trial, margin_admission_trial, support_cross
from .fractional_runtime_whole import verify_request
from .full_v5_check import BULK, _sha
from .margin_admission_inputs import WIDE, read
from .portable_gate_trials import compressed_rows

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "track-recovery/support-cross"
BAND = SCREEN / "detector-origins/whole-band"
CASES = {"DS29-0082": 6, "DS26-0237": 7}
ORDER = (*support_cross.CELLS, "capture")
LIMIT = 210


def checked(folder, member):
    digest = read(folder / "prediction-lock.json")["files"][member]
    return whole_iq.checked(folder / member, digest)


def sources():
    source = read(checked(WIDE, "source-lock.json"))
    reference = read(checked(BAND, "source-lock.json"))
    receiver = Path(source["receiver"])
    inventory = whole_iq.receiver_identity(receiver)
    if inventory != source["receiver_files"]:
        raise ValueError("installed phase release differs from the sealed four-start repeat")
    original_inventory = reference["receiver_files"]
    differences = {
        name: dict(replay=inventory.get(name), historical=original_inventory.get(name))
        for name in sorted(inventory.keys() | original_inventory.keys())
        if inventory.get(name) != original_inventory.get(name)
    }
    return dict(
        receiver=str(receiver),
        receiver_files=inventory,
        cases=reference["cases"],
        historical_receiver_differences=differences,
    )


def load(ident, source):
    case, request = whole_iq.binding(ident)
    bound = source["cases"][ident]
    wide = checked(BAND, f"native/{ident}.json.gz")
    repeat = checked(WIDE, f"native/control/{ident}.json.gz")
    left = gzip.decompress(wide.read_bytes())
    if left != gzip.decompress(repeat.read_bytes()):
        raise ValueError("repeated wide factors are not byte-identical to original")
    right = whole_iq.checked(BULK / case["native"]["path"], bound["capture_native_sha256"])
    if (
        case["request"]["sha256"] != bound["request_sha256"]
        or case["catalog"]["sha256"] != bound["catalog_sha256"]
        or request["job"]["search_center"] != bound["tile"]["center"]
        or {k: v.removeprefix("sha256:") for k, v in request["causal_snapshots"].items()}
        != bound["history"]
    ):
        raise ValueError("session, offer or causal orbital authority differs from the wide control")
    return case, request, bound, left, right.read_bytes()


def stage(work, ident, source):
    case, parent, bound, a, b = load(ident, source)
    wide, capture = map(json.loads, (a, b))
    roster = support_cross.join(wide, capture)
    native_sha, capture_sha = (sha256(content).hexdigest() for content in (a, b))
    probes = wide["source"]["probes"]
    audit = dict(
        id=ident,
        **support_cross.census(probes, roster),
        encoded_roster_sha256=sha256(
            encoded([support_cross.metadata(p) for p in probes])
        ).hexdigest(),
        acquisition_sha256=sha256(
            encoded({key: wide[key] for key in support_cross.CLOCK_FIELDS})
        ).hexdigest(),
        exclusions_sha256=sha256(encoded(wide["provenance"]["excluded_windows"])).hexdigest(),
        support_order_sha256=sha256(encoded(roster)).hexdigest(),
        wide_sha256=native_sha,
        capture_sha256=capture_sha,
        request_sha256=bound["request_sha256"],
        catalogue_sha256=bound["catalog_sha256"],
        causal_history=parent["causal_snapshots"],
    )
    jobs = []
    for name in ORDER:
        path = work / ident / name
        folder = path / "recording"
        folder.mkdir(parents=True, exist_ok=False)
        native = folder / "native.json"
        request = folder / "request.json"
        if name in ("wide", "capture"):
            content, payload = (a, wide) if name == "wide" else (b, capture)
        else:
            payload = support_cross.intervene(wide, capture, roster, name)
            lineage = whole_iq.recording.digest(
                ["probe-availability-cross/v1", name, native_sha, capture_sha]
            )
            payload["source"]["analysis_manifest_sha256"] = lineage
            payload["provenance"] = dict(
                payload["provenance"], run_id="support-cross-" + lineage[7:33]
            )
            content = encoded(payload) + b"\n"
        write(native, content)
        actual = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
        verify_request(read(request), parent, native_path=native, native_sha256=actual)
        save_json(path / "plan.json", dict(receiver=source["receiver"]))
        save_json(path / "raw.json", dict(native_sha256=actual, request_sha256=_sha(request)))
        rows = payload["source"]["probes"]
        availability = sum(support_cross.positive(p) for p in rows)
        keep, restore = support_cross.CELLS.get(name, (False, True))
        expected = (
            audit["total"].get("11", 0)
            + keep * audit["total"].get("10", 0)
            + restore * audit["total"].get("01", 0)
        )
        if availability != expected or len(rows) != len(roster):
            raise ValueError("native factors differ from the frozen 2×2 availability cell")
        jobs.append(
            dict(
                id=ident,
                condition=name,
                method="probe_support_" + name,
                mode="matched-tile",
                cpu=CASES[ident],
                native_sha256=actual.removeprefix("sha256:"),
                paired_capture_sha256=capture_sha,
                parent_wide_sha256=native_sha,
                original_request_sha256=bound["request_sha256"],
                catalog_sha256=bound["catalog_sha256"],
                tile=bound["tile"],
                positive_probes=availability,
                original_probes=len(roster),
                positive_candidates=sum(
                    c[support_cross.GATE] is True for p in rows for c in p["candidates"]
                ),
                prepared_request_sha256=_sha(request),
            )
        )
    return jobs, audit


def service(work, row):
    path = work / row["id"] / row["condition"]
    if (
        _sha(path / "recording/native.json") != row["native_sha256"]
        or _sha(path / "recording/request.json") != row["prepared_request_sha256"]
    ):
        raise ValueError("staged worker input changed after plan seal")
    unit = "leo-support-cross-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--collect",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        f"--property=MemoryMax={whole_iq.MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--property=RuntimeMaxSec={LIMIT}s",
        f"--setenv=TMPDIR={path}",
        *(f"--setenv={k}={v}" for k, v in whole_iq.recording.SINGLE_THREAD.items()),
        "taskset",
        "-c",
        str(row["cpu"]),
        sys.executable,
        "-B",
        "-m",
        margin_admission_trial.__name__,
        "worker",
        "--unit",
        unit,
        "--cpu",
        str(row["cpu"]),
        "--work",
        str(path),
    ]
    start = monotonic()
    log = path / "service.log"
    with log.open("xb") as stream:
        process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
    elapsed = monotonic() - start
    output = log.read_text(errors="replace")
    result, terminal = bounded_cavity_trial.result_for(
        output, process.returncode, path / "position.json"
    )
    resource = path / "measured.json"
    result = dict(
        row,
        unit=unit,
        terminal=terminal,
        result=result,
        supervisor_wall_s=elapsed,
        position_resources=read(resource) if resource.is_file() else None,
        log_sha256=_sha(log),
        service_receipt=[
            line.strip()
            for line in output.splitlines()
            if line.strip().startswith(
                ("Finished with result:", "CPU time consumed:", "Memory peak:", "Service runtime:")
            )
        ],
    )
    save_json(path / "attempt.json", result)
    print(row["id"], row["condition"], result["result"]["status"], round(elapsed, 2), flush=True)
    return result


def run(work):
    if (REPORT / "plan.json").exists():
        raise FileExistsError("a prospectively sealed support replay already exists")
    work.mkdir(exist_ok=False)
    source = sources()
    jobs, audit = [], []
    for ident in CASES:
        records, receipt = stage(work, ident, source)
        jobs.extend(records if CASES[ident] == 6 else records[::-1])
        audit.append(receipt)
    save_json(REPORT / "join-audit.json", audit)
    plan = dict(
        cases=CASES,
        schedule=jobs,
        worker_limit_s=LIMIT,
        memory_bytes=whole_iq.MEMORY,
        swap_bytes=0,
        receiver=source["receiver"],
        receiver_files=source["receiver_files"],
        historical_receiver_differences=source["historical_receiver_differences"],
        files={
            str(path.relative_to(ROOT)): _sha(path)
            for path in (
                Path(__file__),
                Path(support_cross.__file__),
                Path(whole_iq.__file__),
                Path(margin_admission_trial.__file__),
                REPORT / "PROTOCOL.md",
                REPORT / "join-audit.json",
                BAND / "prediction-lock.json",
                WIDE / "prediction-lock.json",
            )
        },
    )
    save_json(REPORT / "plan.json", plan)
    plan_sha = _sha(REPORT / "plan.json")
    print("sealed", plan_sha, [(r["id"], r["total"]) for r in audit], flush=True)

    def lane(ident):
        return [service(work, row) for row in jobs if row["id"] == ident]

    start = monotonic()
    with ThreadPoolExecutor(len(CASES)) as pool:
        rows = [r for batch in pool.map(lane, CASES) for r in batch]
    write(REPORT / "predictions.jsonl.gz", compressed_rows(rows))
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(CASES),
            attempts=len(rows),
            measured_wall_s=monotonic() - start,
            files={
                "plan.json": plan_sha,
                "predictions.jsonl.gz": _sha(REPORT / "predictions.jsonl.gz"),
                "join-audit.json": _sha(REPORT / "join-audit.json"),
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
