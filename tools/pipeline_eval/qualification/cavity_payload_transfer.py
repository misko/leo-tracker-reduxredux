"""Compare the sealed complete and reduced standalone receiver on blinded native packets."""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

from ..__main__ import encoded, local_output, save_json
from ..scoring import validate_result
from . import edge_holdouts as prior
from . import edge_interval_trial as recent
from .fresh_scenes import _read, _sha

REPORT = prior.REPORT.parents[1] / "next/cavity-payload-transfer"
RELEASE = Path("/srv/bulk/leo-dev/cavity-trim-hZWtOlK5/paired")
OBSERVER = Path(__file__).with_name("direct_lifetime_trial.py")
CPUS = (9, 10, 12, 13)
SITES = (((35.0, 55.0), (0.72, 1.25)), ((-15.0, -63.0), (1.2, 1.85)))
PACKAGES = ("small", "full")
LIMIT_S, MEMORY = 165, 512 * 1024**2
ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "OPENBLAS_NUM_THREADS")
WORKER = """
import json, runpy, sys
from pathlib import Path
root, tmp = (Path(x).resolve() for x in sys.argv[2:4])
sys.path.insert(0, str(root))
worker = runpy.run_path(sys.argv[1])["observe"]
worker.__globals__["TMP"] = tmp
worker(sys.argv[4], int(sys.argv[5]), root, sys.argv[6:])
origins = {n: str(Path(m.__file__).resolve()) for n, m in sys.modules.items()
           if n.split('.')[0] in ('leo', 'tools') and getattr(m, '__file__', None)}
print('origins '+json.dumps(origins,sort_keys=True), file=sys.stderr, flush=True)
assert all(Path(v).is_relative_to(root) for v in origins.values())
"""


def history_context():
    old, used = recent.prior_context()
    labels, packets = (
        _read(recent.REPORT / name) for name in ("released-labels.json", "public-captures.json")
    )
    for ident, row in labels.items():
        old.add(tuple(row["location"]))
        used.update((row["trajectory"]["sha256"], packets[ident]["source"]["sha256"]))
    return old, used


def bound_packages(release):
    plan = _read(release / "plan.json")
    if {v for v in plan["packages"]} != set(PACKAGES):
        raise ValueError("invalid package plan")
    if plan["packages"]["small"]["binaries"] != plan["packages"]["full"]["binaries"]:
        raise ValueError("package comparison changed numerical libraries")
    for name, receipt in plan["packages"].items():
        files = (
            receipt["files"]
            | receipt["binaries"]
            | {
                "native/manifest.json": receipt["native_manifest_sha256"],
            }
        )
        if any(_sha(release / name / f) != d for f, d in files.items()):
            raise ValueError("package source or numerical binary changed")
        if _sha(release / f"{name}.tar.gz") != receipt["archive_sha256"]:
            raise ValueError("declared distribution archive changed")
    return plan["packages"]


def prepare(root, captures):
    compact = prior.worker.compact
    config = root / "public/track-config.json"
    save_json(config, dict(config=compact.portable_v5.TRACK_CONFIG))
    for (screen_center, _), ident in zip(SITES, captures, strict=True):
        packet = _read(root / "public" / f"{ident}.json")
        raw = root / "public" / f"{ident}.native.json"
        if _sha(raw) != packet["packet_sha256"]:
            raise ValueError("native factor binding changed")
        native = root / "public" / f"{ident}.complete.json"
        native.write_bytes(encoded(compact.complete_native(_read(raw))))
        catalogue = packet["source"]["sha256"]
        stamps, paths, inventory = compact.history_at(packet["cutoff"], catalogue)
        archive = root / "public" / f"tle-{ident}"
        leaf = archive / "archive/space-track"
        leaf.mkdir(parents=True)
        for row in stamps:
            digest = row["sha256"]
            destination = leaf / f"{row['collected_utc_ns']}-{digest}.tle"
            if not destination.is_file():
                shutil.copyfile(paths[digest], destination)
            if _sha(destination) != digest:
                raise ValueError("copied archive snapshot differs from collection digest")
        shared = dict(
            capture_id=ident,
            native_sha256=_sha(native),
            original_factor_sha256=_sha(raw),
            catalog_sha256=catalogue,
            history_sha256=prior.INPUTS.cold._sha(encoded(stamps)),
            track_config_sha256=_sha(config),
            screen_center=list(screen_center),
        )
        for offer in (packet["tiles"][0], packet["tiles"][-1]):
            bound = dict(shared, id=offer["id"], tile=offer)
            bound["input_sha256"] = prior.INPUTS.cold._sha(encoded(bound))
            yield bound, native, config, archive, inventory


def capped(root, release, job, variant, cpu):
    row, native, config, archive, _ = job
    bundle = release / variant
    unit = "leo-cavity-transfer-" + uuid4().hex[:12]
    scratch = root / "runs" / row["id"] / variant
    scratch.mkdir(parents=True)
    opts = dict(
        native=native,
        native_sha256=row["native_sha256"],
        session=row["capture_id"],
        track_config=config,
        config_sha256=row["track_config_sha256"],
        archive=archive,
        native_backend=bundle / "native/manifest.json",
        library=bundle / "projector.so",
        width_km=row["tile"]["width_km"],
    )
    flags = [p for key, v in opts.items() for p in ("--" + key.replace("_", "-"), str(v))]
    flags.extend(
        [
            "--tile",
            *map(str, row["tile"]["center"]),
            "--screen-center",
            *map(str, row["screen_center"]),
        ]
    )
    command = [
        "systemd-run",
        "--user",
        "--pipe",
        "--wait",
        f"--unit={unit}",
        f"--working-directory={bundle}",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT_S}s",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--setenv=TMPDIR={scratch}",
        *(f"--setenv={name}=1" for name in ENV),
        "taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-IB",
        "-c",
        WORKER,
        str(OBSERVER.resolve()),
        str(bundle),
        str(scratch),
        unit,
        str(cpu),
        *flags,
    ]
    started = perf_counter()
    stdout, stderr = (scratch / name for name in ("stdout", "stderr"))
    service_wait_expired = False
    with stdout.open("xb") as out, stderr.open("xb") as log:
        try:
            completed = subprocess.run(
                command, stdout=out, stderr=log, timeout=LIMIT_S + 12, check=False
            )
            code = completed.returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=5)
            service_wait_expired, code = True, None
    elapsed = perf_counter() - started
    seen = {k: [] for k in ("proof", "stage", "finish", "origins")}
    diagnostics = []
    for line in stderr.read_text(errors="replace").splitlines():
        label, _, value = line.partition(" ")
        if label in seen:
            seen[label].append(json.loads(value))
        elif label != "reached":
            diagnostics.append(line)
    if code == 0 and all(seen[k] for k in ("proof", "finish", "origins")):
        result = _read(stdout)
    else:
        timed = service_wait_expired or any("result: timeout" in text for text in diagnostics)
        memory = any("oom-kill" in text for text in diagnostics)
        state = "timed_out" if timed else "failed"
        reason = (
            "service deadline" if timed else "512 MiB service OOM" if memory else "service failure"
        )
        result = prior.worker.compact.portable_v5.unavailable(reason) | {"status": state}
    validate_result(result)
    print(row["id"], variant, result["status"], round(elapsed, 2), flush=True)
    return dict(
        row,
        method=f"v5_cavity_payload_{variant}",
        result=result,
        cpu=cpu,
        wall_s=elapsed,
        exit_code=code,
        runtime=seen,
        diagnostics=diagnostics[-12:],
        stderr_sha256=_sha(stderr),
    )


def replay(root, release, output):
    receipt = output / "prediction-lock.json"
    if receipt.exists():
        raise ValueError("a prospective prediction seal already exists")
    packages = bound_packages(release)
    save_json(
        output / "source-lock.json",
        dict(
            package_plan_sha256=_sha(release / "plan.json"),
            packages=packages,
            files={
                str(path): _sha(path)
                for path in (
                    Path(__file__),
                    OBSERVER,
                    Path(prior.__file__),
                    Path(prior.INPUTS.__file__),
                    output / "PROTOCOL.md",
                )
            },
        ),
    )
    with patch.multiple(prior, SITES=SITES, prior_context=history_context):
        captures = list(prior.draw(root, [secrets.token_bytes(32) for _ in SITES]))
    jobs = list(prepare(root, captures))
    locks = {
        str(f.relative_to(root)): _sha(f)
        for folder in ("public", "private")
        for f in sorted((root / folder).rglob("*"))
        if f.is_file()
    }
    save_json(output / "input-lock.json", locks)
    save_json(output / "causal-history.json", {job[0]["capture_id"]: job[-1] for job in jobs})
    save_json(output / "requests.json", [job[0] for job in jobs])
    began = perf_counter()

    def pair(index, job):
        order = PACKAGES if index % 2 == 0 else PACKAGES[::-1]
        return [capped(root, release, job, name, CPUS[index]) for name in order]

    with ThreadPoolExecutor(max_workers=4) as pool:
        runners = [pool.submit(pair, i, job) for i, job in enumerate(jobs)]
        rows = [r for done in runners for r in done.result()]
    if any(_sha(root / name) != digest for name, digest in locks.items()):
        raise ValueError("blinded requests or labels changed during inference")
    if bound_packages(release) != packages:
        raise ValueError("package changed while measuring")
    save_json(output / "predictions.json", rows)
    evidence = (
        "source-lock.json",
        "input-lock.json",
        "causal-history.json",
        "requests.json",
        "predictions.json",
    )
    save_json(
        receipt,
        dict(files={name: _sha(output / name) for name in evidence}, wall_s=perf_counter() - began),
    )
    for path, folder in (("public-captures.json", "public"), ("released-labels.json", "private")):
        save_json(output / path, {c: _read(root / folder / f"{c}.json") for c in captures})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--release", type=Path, default=RELEASE)
    args = cli.parse_args()
    if not set(CPUS) <= os.sched_getaffinity(0):
        cli.error("pin to all four authorized cores")
    replay(local_output(args.root), args.release.resolve(), REPORT)
