"""Run exact ranked cavity nomination in a capped standalone pair."""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import fit_work_trial as shared
from . import ranked_fit_probe as probe
from .direct_cavity_cap import systemd_fields

COMMON = shared.COMMON
REPORT = shared.REPORT.parent.parent / "receiver-core/ranked-fit"
CASES = {"DS29-0247": 12, "DS26-0237": 13, "DS26-0122": 13}
HELD = "DS26-0122"
STOCK, CANDIDATE = "v5_ranked_fit_stock", "v5_ranked_fit"
LIMIT = 185
TARGET = "leo/analysis/localization_v3/family_cavity.py"
MANIFEST = "native/manifest.json"
BEFORE = (
    "    else:\n"
    '        mode_bank = build_modes(d["scan"], [j], [j] if supported else [], "physical")'
)
AFTER = '    elif supported:\n        mode_bank = build_modes(d["scan"], [j], [j], "physical")'


def revised(source):
    if source.count(BEFORE) != 1:
        raise ValueError("unexpected ranked fine nomination source")
    new = source.replace(BEFORE, AFTER, 1)
    compile(new, TARGET, "exec")
    return new


def sources():
    return {
        str(p): COMMON.sha(p)
        for p in (Path(__file__), Path(probe.__file__), REPORT / "PROTOCOL.md")
    }


def copy_install(source, dest, identity, optimize=False):
    shared.verify_install(source, identity)
    dest.mkdir(exist_ok=False)
    for name in identity["files"] | identity["compiler_sources"]:
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, path)
    manifest = dest / MANIFEST
    manifest.write_text(manifest.read_text().replace(str(source) + "/", str(dest) + "/"))
    if optimize:
        path = dest / TARGET
        path.write_text(revised(path.read_text()))
    files = whole_iq.receiver_identity(dest)
    changed = {name for name, checksum in files.items() if identity["files"].get(name) != checksum}
    expected = {MANIFEST, TARGET} if optimize else {MANIFEST}
    if set(files) != set(identity["files"]) or changed != expected:
        raise ValueError("standalone implementation differed from the intended overlay")
    subprocess.run(
        [
            str(shared.pressure.direct.v5_lean.PYTHON),
            "-IB",
            "-c",
            "import runpy; from pathlib import Path; "
            "runpy.run_path(str(Path.cwd()))['activate'](Path.cwd()); "
            "from leo.analysis.localization_v4.backend import read_manifest, validate_manifest; "
            "validate_manifest(read_manifest(Path('native/manifest.json')), check_provider=True)",
        ],
        cwd=dest,
        timeout=15,
        check=True,
    )
    return dict(files=files, compiler_sources=identity["compiler_sources"], changed=sorted(changed))


def lock(work):
    filesystem = subprocess.check_output(
        ["findmnt", "-T", str(work.parent), "-n", "-o", "FSTYPE"], text=True
    ).strip()
    if filesystem != "ext4":
        raise ValueError("local ext4 scratch is required for this replay")
    work.mkdir(exist_ok=False, parents=True)
    base = shared.BASE
    installed = COMMON.read(base / "candidate-lock.json")
    stock = copy_install(base / "candidate", work / "stock", installed)
    save_json(
        work / "plan.json",
        dict(
            cases={ident: shared.binding(ident) for ident in CASES},
            cpus=CASES,
            order={
                ident: [CANDIDATE, STOCK] if ident == HELD else [STOCK, CANDIDATE]
                for ident in CASES
            },
            stock_install=stock,
            original_phase_release_sha256=COMMON.sha(base / "candidate-lock.json"),
            sources=sources(),
            memory_bytes=512 * 2**20,
            swap_bytes=0,
            service_limit_s=LIMIT,
        ),
    )


def bundle(work):
    lockfile = work / "plan.json"
    plan = COMMON.read(lockfile)
    profiles = {}
    for ident in CASES:
        if ident == HELD:
            continue
        path = work / "runs" / ident / STOCK / "attempt.json"
        row = COMMON.read(path)
        if (
            row["service_status"] != "success"
            or row["ready"]["memory.max"] != plan["memory_bytes"]
            or not row["nomination"]["calls"].get("mode_without_support")
        ):
            raise ValueError("each development run must demonstrate unused orbital mode work")
        profiles[ident] = COMMON.sha(path)
    identity = copy_install(work / "stock", work / "candidate", plan["stock_install"], True)
    save_json(
        work / "candidate-lock.json",
        identity | {"plan_sha256": COMMON.sha(lockfile), "profile_sha256": profiles},
    )


def run(work, ident, method):
    lockfile = work / "plan.json"
    plan = COMMON.read(lockfile)
    cpu, bound = CASES[ident], plan["cases"][ident]
    if (
        plan["sources"] != sources()
        or bound != shared.binding(ident)
        or os.sched_getaffinity(0) != {cpu}
        or os.nice(0) < 10
    ):
        raise ValueError("choose the frozen factor input, source code and CPU pin")
    if method == STOCK:
        root, identity = work / "stock", plan["stock_install"]
    else:
        root, identity = work / "candidate", COMMON.read(work / "candidate-lock.json")
        if identity["plan_sha256"] != COMMON.sha(lockfile):
            raise ValueError("optimized implementation has a different frozen plan")
    shared.verify_install(root, identity)
    order = plan["order"][ident]
    paths = work / "runs" / ident
    if method == order[1] and not (paths / order[0] / "attempt.json").is_file():
        raise ValueError("run the preregistered first method")
    out = paths / method
    out.mkdir(exist_ok=False, parents=True)
    unit = "leo-ranked-nomination-" + uuid4().hex[:10]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={root}",
        f"--property=MemoryMax={plan['memory_bytes']}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=Nice=10",
        "--property=MemoryAccounting=yes",
        f"--setenv=TMPDIR={out}",
        "taskset",
        "-c",
        str(cpu),
        str(shared.pressure.direct.v5_lean.PYTHON),
        "-IB",
        str(Path(probe.__file__)),
        str(root),
        str(cpu),
        *shared.pressure.command_flags(bound),
    ]
    log_path, position_path = out / "service.log", out / "position.json"
    start = monotonic()
    with position_path.open("xb") as output, log_path.open("xb") as log:
        try:
            child = subprocess.run(
                command, stdout=output, stderr=log, timeout=LIMIT + 8, check=False
            )
            returncode = child.returncode
        except subprocess.TimeoutExpired:
            returncode = 124
    wall = monotonic() - start
    fields = systemd_fields(unit)
    records = {}
    text = log_path.read_text(errors="replace")
    for line in text.splitlines():
        tag, _, data = line.partition(" ")
        if tag in {"ready", "nomination", "finish"}:
            records[tag] = json.loads(data)
    terminal = re.search(r"Finished with result: (\S+)", text)
    status = terminal[1] if terminal else fields["Result"]
    if status == "success" and returncode == 0:
        result = COMMON.read(position_path)
    else:
        failure = "timed_out" if returncode == 124 or status == "timeout" else "failed"
        result = shared.pressure.direct.v5_lean._no_fix(
            f"Linux capped service {status}", status=failure
        )
    shared.pressure.direct.validate_result(result)
    save_json(
        out / "attempt.json",
        dict(
            bound,
            plan_sha256=COMMON.sha(lockfile),
            source_install=identity,
            method=method,
            cpu=cpu,
            order=order.index(method),
            wall_s=wall,
            service_status=status,
            service_kernel=fields,
            returncode=returncode,
            log_sha256=COMMON.sha(log_path),
            result=result,
            **records,
        ),
    )
    print(ident, method, status, round(wall, 2), records.get("nomination"), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("operation", choices=("lock", "bundle", "run"))
    p.add_argument("case", nargs="?", choices=CASES)
    p.add_argument("method", nargs="?", choices=(STOCK, CANDIDATE))
    a = p.parse_args()
    folder = local_output(a.work)
    if a.operation == "lock":
        lock(folder)
    elif a.operation == "bundle":
        bundle(folder)
    else:
        run(folder, a.case, a.method)
