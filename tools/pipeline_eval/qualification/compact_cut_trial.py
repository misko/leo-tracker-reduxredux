"""Source-lock and run the explicit compact receiver against its phase-release donor."""

import argparse
import gzip
import json
import re
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import cavity_runtime, compact_cut, whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS, validate_result
from . import compact_cut_probe as probe
from .cavity_pressure_trial import command_flags
from .direct_cavity_cap import systemd_fields
from .full_v5_check import BULK, _sha

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "acquisition-frontier/compact-cut"
ARCHIVE = SCREEN / "recovery/full-receivers"
ROSTER = {"DS26-0036": 12, "DS29-0357": 13, "DS26-0090": 12}
HELD = "DS26-0090"
STOCK, CANDIDATE = "v5_phase_stock_cut_control", "v5_compact_cut"
LIMIT = 210
EXCLUDED = {
    "DS26-0036",
    "DS29-0082",
    "DS29-0357",
    "DS26-0112",
    "DS26-0237",
    "DS29-0127",
    "DS26-0122",
    "DS26-0052",
    "DS26-0146",
    "DS29-0174",
    "DS29-0316",
    "DS26-0026",
    "DS29-0247",
}
SALT = "receiver-compact-cut-holdout-v1"


def binding(ident):
    case, request = whole_iq.binding(ident)
    native = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    request_path = BULK / case["request"]["path"]
    if (
        request["job"]["native_input"]["sha256"] != "sha256:" + case["native"]["sha256"]
        or request["job"]["search_center"] != case["regions"][0]["center"]
    ):
        raise ValueError("frozen native factors or offer changed")
    return dict(
        native=str(native),
        request=str(request_path),
        request_sha256=_sha(request_path),
        native_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        tile=case["regions"][0],
    )


def sources():
    p = Path(probe.__file__)
    return {
        str(x.relative_to(ROOT)): _sha(x)
        for x in (
            Path(__file__),
            p,
            p.with_name("ranked_fit_probe.py"),
            Path(compact_cut.__file__),
            REPORT / "PROTOCOL.md",
        )
    }


def installation(root):
    files = whole_iq.receiver_identity(root)
    c_files = whole_iq.native_sources(root)
    python = [root / name for name in files if name.endswith(".py")]
    return dict(
        root=str(root),
        files=files,
        compiler_sources=c_files,
        source_files=len(python) + len(c_files),
        python_lines=sum(len(p.read_bytes().splitlines()) for p in python),
        source_bytes=sum(p.stat().st_size for p in (*python, *(root / n for n in c_files))),
    )


def check_install(root, declared, files):
    installed = installation(root)
    if installed != declared:
        raise ValueError("standalone installation differs from manifest")
    actual = {
        name: digest
        for name, digest in (installed["files"] | installed["compiler_sources"]).items()
        if name.endswith((".py", ".c")) and name not in {"__main__.py", "tools/__init__.py"}
    }
    if actual != {name: sha256(data).hexdigest() for name, data in files.items()}:
        raise ValueError("installed scientific source differs from the released file set")


def stage(work, stock):
    path = ARCHIVE / "positions.jsonl.gz"
    archive_digest = whole_iq.read(ARCHIVE / "roof-lock.json")["files"][path.name]
    whole_iq.checked(path, archive_digest)
    with gzip.open(path) as stream:
        eligible = [
            row["id"]
            for row in map(json.loads, stream)
            if row["method"] == "v5_secant_fit"
            and row["result"]["status"] == "ok"
            and 0 < row.get("call_s", 0) < 85
            and row["id"] not in EXCLUDED
            and not row["result"]["metrics"]["cavity_offered"]
        ]
    roster = sorted(eligible, key=lambda name: sha256(f"{SALT}:{name}".encode()).digest())
    if roster[0] != HELD:
        raise ValueError("held archive no longer selects the declared input")
    donor = cavity_runtime.release_files(cavity_runtime.RELEASE, "phase-release")
    roots = {STOCK: stock, CANDIDATE: work / "candidate"}
    builds = {key: installation(root) for key, root in roots.items()}
    check_install(stock, builds[STOCK], donor)
    check_install(roots[CANDIDATE], builds[CANDIDATE], compact_cut.compact_sources(donor))
    for name, checksum in builds[STOCK]["files"].items():
        if name.endswith(".so") and builds[CANDIDATE]["files"].get(name) != checksum:
            raise ValueError("revised package changed a native binary")
    if builds[STOCK]["compiler_sources"] != builds[CANDIDATE]["compiler_sources"]:
        raise ValueError("revised package changed a compiler source")
    if any(
        subprocess.check_output(
            ["findmnt", "-T", str(root), "-n", "-o", "FSTYPE"], text=True
        ).strip()
        != "ext4"
        for root in roots.values()
    ):
        raise ValueError("compare both installations from local ext4")
    save_json(
        work / "plan.json",
        dict(
            builds=builds,
            sources=sources(),
            bindings={name: binding(name) for name in ROSTER},
            cpus=ROSTER,
            orders={
                name: [CANDIDATE, STOCK] if name == HELD else [STOCK, CANDIDATE] for name in ROSTER
            },
            held_selection=dict(salt=SALT, candidates=roster, archive_sha256=archive_digest),
            limit_s=LIMIT,
            cap_bytes=whole_iq.MEMORY,
            swap_bytes=0,
        ),
    )


def run_case(work, ident):
    plan_file = work / "plan.json"
    plan = whole_iq.read(plan_file)
    row, cpu = binding(ident), plan["cpus"][ident]
    if plan["sources"] != sources() or row != plan["bindings"][ident]:
        raise ValueError("trial no longer matches its source and input lock")
    for index, method in enumerate(plan["orders"][ident]):
        install = plan["builds"][method]
        root = Path(install["root"])
        if installation(root) != install:
            raise ValueError("installed receiver differs from locked source")
        out = work / ident / method
        out.mkdir(exist_ok=False, parents=True)
        unit = "leo-compact-cut-" + uuid4().hex[:10]
        command = [
            "systemd-run",
            "--user",
            "--wait",
            "--pipe",
            f"--unit={unit}",
            f"--working-directory={root}",
            "-p",
            f"MemoryMax={plan['cap_bytes']}",
            "-p",
            "MemorySwapMax=0",
            "-p",
            "MemoryAccounting=yes",
            "-p",
            "Nice=10",
            "-p",
            f"RuntimeMaxSec={LIMIT}s",
            f"--setenv=TMPDIR={out}",
            "taskset",
            "-c",
            str(cpu),
            sys.executable,
            "-IB",
            str(Path(probe.__file__)),
            str(root),
            str(cpu),
            *command_flags(row),
        ]
        result_path, log = out / "position.json", out / "service.log"
        start = monotonic()
        with result_path.open("xb") as output, log.open("xb") as stderr:
            try:
                exitcode = subprocess.run(
                    command, stdout=output, stderr=stderr, timeout=LIMIT + 10, check=False
                ).returncode
            except subprocess.TimeoutExpired:
                exitcode = 124
        wall_s, kernel = monotonic() - start, systemd_fields(unit)
        lines = log.read_text(errors="replace")
        terminal = re.search(r"Finished with result: (\S+)", lines)
        status = terminal[1] if terminal else kernel["Result"]
        evidence = {}
        for line in lines.splitlines():
            name, _, value = line.partition(" ")
            if name in {"ready", "finish", "decisions", "imports"}:
                evidence[name] = json.loads(value)
        if exitcode == 0 and status == "success":
            result = whole_iq.read(result_path)
        else:
            result = dict(
                status="timed_out" if exitcode == 124 or status == "timeout" else "failed",
                reason=f"Linux bounded receiver service {status}",
                boundary="Capture-era native factors through compact v5 receiver position",
                arms={arm: {"latlon": None} for arm in ARMS},
                metrics={},
            )
        validate_result(result)
        save_json(
            out / "attempt.json",
            dict(
                id=ident,
                cpu=cpu,
                order=index,
                method=method,
                wall_s=wall_s,
                returncode=exitcode,
                service_status=status,
                kernel=kernel,
                measures=evidence,
                result=result,
                plan_sha256=_sha(plan_file),
                native_sha256=row["native_sha256"],
                result_sha256=_sha(result_path),
                service_log_sha256=_sha(log),
            ),
        )
        print(ident, method, status, round(wall_s, 2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("stage").add_argument("stock", type=Path)
    subparsers.add_parser("run").add_argument("case", choices=ROSTER)
    a = parser.parse_args()
    work = local_output(a.work)
    if a.operation == "stage":
        stage(work, a.stock.resolve())
    else:
        run_case(work, a.case)
