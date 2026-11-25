"""Prepare and run the frozen DS30-0016/0107 original-waveform opt-in panel."""

import argparse
import fcntl
import json
import os
import resource
import subprocess
import tarfile
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import monotonic, time_ns

import ds30_paired_worker as paired
from combined_small_panel_entry import GRID

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FROZEN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/frozen-build")
SLOTS = Path("/tmp/leo-v3-prefetch-live-0016-result01/build.json")
STOCK = Path("/opt/leo-algo08/algo08v3")
RELEASE = paired.PYTHON.parents[2]
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
STOCK_PIN = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
CONTROL = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
TRIAL = "bb4d1466c6b3dbc3333ad3be71ce2dade103356fa5a8c6f5bb56bf599b66c282"
ARCHIVE_PIN = "4e9bc6d3d62cda6e915db62d28e4c114c82693b70768ba90bb258071fef015f5"
SLOT_COMMIT = "d9a477b9a3a494632d043e27eade0ad75ff84427"
CAP_SECONDS = 40
CASES = {
    "DS30-0016": dict(
        order=["charted", "trial"],
        issued=808,
        admitted=713,
        members=13,
        encoded=991734597,
        decision="complete",
        stage="/dev/shm/leo-v3-guarded-selective-0016-stage01",
        admission="7139e35e91870e05aa95b2eecddb9cf6beeb231428cb986be3f1935fe010b243",
        reference="660dec373641a410d30a0695378df859922adde4868561b8457ae88e45e921dd",
    ),
    "DS30-0107": dict(
        order=["trial", "charted"],
        issued=29,
        admitted=27,
        members=1,
        encoded=33519983,
        decision="withheld",
        stage="/dev/shm/leo-v3-continued-cfo-0107-pair01",
        admission="c8db772f9f37003d360955adc27bff4fd0fc0af2e136f157fecd646e2802ffee",
        reference="283023da9ed2ead7f50c5f5e2b9a5f45e89f4162c9c71e8f82641ff110c5e1ba",
    ),
}


def digest(body):
    return sha256(body).hexdigest()


def check(path, pin):
    body = path.read_bytes()
    if digest(body) != pin.removeprefix("sha256:"):
        raise ValueError(f"Unapproved panel input {path}")
    return body


def write(path, value):
    with path.open("x") as file:
        json.dump(value, file, sort_keys=True, allow_nan=False, indent=2)
        file.write("\n")
    return digest(path.read_bytes())


def runtime_paths(root, role):
    return root / role, root / (role + "-build.json")


def checked_source_delta(unchanged, slot_build):
    if {k: v for k, v in unchanged.items() if k != "sources"} != {
        k: v for k, v in slot_build.items() if k != "sources"
    }:
        raise ValueError("The qualified slot build changed scientific assets or configuration")
    original, trial = unchanged["sources"], slot_build["sources"]
    changed = {
        name for name in original.keys() | trial.keys() if original.get(name) != trial.get(name)
    }
    if changed != {
        f"reports/ALGO08/v3/{name}.py"
        for name in ("integrated_original_batch", "prefetch_snapshots", "legacy_snapshot_reuse")
    }:
        raise ValueError("The qualified runtime differs outside the private prefetch port")
    return changed


def restore(root):
    body = check(FROZEN / "source-archive.tar.gz", ARCHIVE_PIN)
    builds = {"charted": check(FROZEN / "build.json", CONTROL), "trial": check(SLOTS, TRIAL)}
    delta = checked_source_delta(*(json.loads(data) for data in builds.values()))
    for role, data in builds.items():
        tree, manifest = runtime_paths(root, role)
        tree.mkdir()
        with tarfile.open(fileobj=BytesIO(body)) as archive:
            archive.extractall(tree, filter="data")
        if role == "trial":
            for name in sorted(delta):
                source = subprocess.check_output(
                    [
                        "git",
                        "-c",
                        f"safe.directory={REPO}",
                        "-C",
                        str(REPO),
                        "show",
                        f"{SLOT_COMMIT}:{name}",
                    ]
                )
                if digest(source) != json.loads(data)["sources"][name].removeprefix("sha256:"):
                    raise ValueError(f"Slot donor does not reproduce {name}")
                (tree / name).write_bytes(source)
        manifest.write_bytes(data)


def reference(case):
    root = Path("/dev/shm") / f"leo-v3-stock-raw-repeat-{case}-01"
    seal = json.loads(check(root / "prediction-seal.json", CASES[case]["reference"]))
    if seal["admission.json"] != CASES[case]["admission"]:
        raise ValueError("Installed reference does not bind the frozen source request")
    return root, seal


def source_case(case):
    spec = CASES[case]
    root, _ = reference(case)
    prior = json.loads(check(root / "admission.json", spec["admission"]))["request"]
    recording = Path(prior["recording"])
    staged = Path(spec["stage"]) / recording.name
    offered, archive = Path(prior["region"]), Path(prior["archive"]["root"])
    check(offered, prior["offer_sha256"])
    payload = sorted(staged.glob("*/*.ci16.zst"))
    indexes = sorted(staged.glob("*/windows-*.jsonl"))
    manifests = sorted(staged.glob("*/manifest.json"))
    if (len(payload), len(indexes), sum(p.stat().st_size for p in payload)) != (
        spec["members"],
        spec["members"],
        spec["encoded"],
    ) or not manifests:
        raise ValueError("The enrolled complete staged original is missing or has changed extent")
    causal = sorted((archive / "archive/space-track").glob("*.tle"))
    if len(causal) != (46 if case == "DS30-0016" else 51):
        raise ValueError("Incomplete original causal catalogue")
    metadata = [*indexes, *manifests, *causal, offered]
    authority = dict(
        schema="algo08v3-original-request-v1",
        recording=str(recording),
        session_id=prior["session"],
        inventory_sha256=prior["inventory"],
        raw_authority_sha256=prior["authority"],
        window_count=spec["issued"],
        causal_cutoff_utc_ns=prior["cutoff_utc_ns"],
        archive_sha256=prior["archive"]["snapshots_sha256"],
        region_sha256="sha256:" + prior["offer_sha256"],
    )
    return dict(
        authority=authority,
        archive=str(archive),
        offer=str(offered),
        staged=str(staged),
        files=[str(p) for p in [*payload, *metadata]],
        reference=str(root),
    )


def residency(paths):
    device = Path("/dev/shm").stat().st_dev
    for path in paths:
        file = Path(path)
        if (
            not file.is_relative_to("/dev/shm")
            or file.resolve(strict=True) != file
            or file.stat().st_dev != device
            or not file.is_file()
        ):
            raise ValueError(f"Expected original direct resident tmpfs input {file}")
    rows = json.loads(
        subprocess.check_output(
            [
                "/usr/bin/fincore",
                "--bytes",
                "--json",
                "-o",
                "RES,SIZE,FILE",
                *paths,
            ]
        )
    )["fincore"]
    if {row["file"] for row in rows} != set(paths) or len(rows) != len(paths):
        raise ValueError("The original residency metadata is incomplete")
    absent = [row for row in rows if row["res"] < row["size"]]
    return dict(files=len(rows), bytes=sum(row["size"] for row in rows), nonresident=absent)


def require_resident(paths):
    found = residency(paths)
    if found["nonresident"]:
        raise ValueError("An original waveform or causal input is no longer resident")
    return found


def capsule(command, work, inputs):
    args = [
        "/usr/bin/bwrap",
        "--unshare-all",
        "--unshare-user",
        "--disable-userns",
        "--die-with-parent",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
    ]
    for name in ("bin", "lib", "lib64"):
        args += ["--symlink", f"usr/{name}", f"/{name}"]
    runtime = paired.PYTHON.resolve(strict=True).parents[1]
    for path in (
        Path("/usr"),
        Path("/etc/ld.so.cache"),
        Path("/etc/fonts"),
        Path("/etc/passwd"),
        Path("/etc/group"),
        runtime,
        STOCK,
        RELEASE,
        Path("/tmp"),
        Path("/dev/shm"),
    ):
        args += ["--ro-bind", str(path), str(path)]
    args += [
        "--ro-bind",
        inputs["staged"],
        inputs["authority"]["recording"],
        "--bind",
        str(work),
        str(work),
        "--remount-ro",
        "/",
        "--chdir",
        str(work),
    ]
    environment = {
        key: value
        for key, value in paired.environment(work).items()
        if key.endswith("_THREADS") or key in ("OMP_THREAD_LIMIT", "MPLCONFIGDIR", "TMPDIR")
    }
    for key, value in (
        environment | dict(PATH="/usr/bin:/bin", LANG="C.UTF-8", XDG_CACHE_HOME=str(work / "tmp"))
    ).items():
        args += ["--setenv", key, value]
    return [*args, "--", *map(str, command)]


def command(root, case, work, inputs, role, extra=()):
    tree, manifest = runtime_paths(root, role)
    role_args = (
        *paired.original_options(
            inputs["authority"]["recording"],
            inputs["archive"],
            inputs["offer"],
            work / "publication",
        ),
        "--authority",
        root / (case + "-authority.json"),
        "--authority-sha256",
        inputs["authority_sha256"],
        "--build",
        manifest,
        "--build-sha256",
        CONTROL if role == "charted" else TRIAL,
        *extra,
    )
    entry = (
        [tree / "reports/ALGO08/v3/integrated_original_batch.py"]
        if role == "charted"
        else [HERE / "combined_small_panel_entry.py", tree, "--"]
    )
    return capsule([paired.PYTHON, "-IB", *entry, *role_args], work, inputs)


def new_work(path):
    path.mkdir()
    (path / "fonts").mkdir()
    (path / "tmp").mkdir()
    return path


def check_command(argv):
    result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise ValueError(f"Metadata or ports preflight failed: {result.stderr.strip()}")
    return json.loads(result.stdout.splitlines()[-1])


def protocol_pin():
    return digest((HERE / "combined-small-panel-protocol.md").read_bytes())


def source_pins():
    return {
        name: digest((HERE / name).read_bytes())
        for name in (
            "combined_small_panel.py",
            "combined_small_panel_entry.py",
            "combined_small_panel_score.py",
            "combined_small_panel_residency.py",
            "ds30_paired_worker.py",
            "ds30_paired_inputs.py",
        )
    }


def prepare(root):
    start = monotonic()
    root.mkdir(mode=0o700)
    restore(root)
    cases = {}
    for case, spec in CASES.items():
        inputs = source_case(case)
        inputs["residency"] = residency(inputs["files"])
        inputs["authority_sha256"] = "sha256:" + write(
            root / (case + "-authority.json"), inputs["authority"]
        )
        work = new_work(root / (case + "-preflight"))
        preflight = {}
        for role in spec["order"]:
            preflight[role] = check_command(
                command(root, case, work, inputs, role, ["--preflight"])
            )
            if preflight[role] != dict(
                preflight="ready", session_id=inputs["authority"]["session_id"], waveform_opens=0
            ):
                raise ValueError(
                    "Signed metadata preflight did not cover the expected original source"
                )
        inputs["preflight"] = preflight
        if case == "DS30-0016":
            probe = capsule(
                [
                    paired.PYTHON,
                    "-IB",
                    HERE / "combined_small_panel_entry.py",
                    "--probe-ports",
                    runtime_paths(root, "trial")[0],
                ],
                work,
                inputs,
            )
            inputs["ports"] = check_command(probe)
            installed = check_command(capsule([STOCK / "run", "--verify"], work, inputs))
            if installed.get("frozen_specification") != STOCK_PIN:
                raise ValueError("Installed ALGO08v3 identity changed")
        cases[case] = inputs
    print(
        write(
            root / "ready.json",
            dict(
                protocol_sha256=protocol_pin(),
                sources=source_pins(),
                caps=CAP_SECONDS,
                grid=str(GRID),
                cases=cases,
                controls=CASES,
                installed=installed,
                preflight_elapsed_s=monotonic() - start,
            ),
        )
    )


def verify_ready(root, pin):
    ready = json.loads(check(root / "ready.json", pin))
    if (
        ready["protocol_sha256"] != protocol_pin()
        or ready["sources"] != source_pins()
        or ready["controls"] != CASES
        or ready["caps"] != CAP_SECONDS
    ):
        raise ValueError("The frozen treatment, order or publication verifier changed")
    for case, inputs in ready["cases"].items():
        if any(inputs[key] != value for key, value in source_case(case).items()):
            raise ValueError("The staged custody no longer matches the frozen panel")
        check(root / (case + "-authority.json"), inputs["authority_sha256"])
    return ready


def condition(root, pin):
    if os.sched_getaffinity(0) != {3} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Conditioning requires low-priority CPU 3")
    priority = subprocess.check_output(
        ["/usr/bin/ionice", "-p", str(os.getpid())], text=True
    ).strip()
    if priority != "idle":
        raise ValueError("Conditioning requires idle I/O")
    case = "DS30-0016"
    inputs = verify_ready(root, pin)["cases"][case]
    if not inputs["residency"]["nonresident"]:
        raise ValueError("The passive original was already resident")
    before = residency(inputs["files"])
    files = [row["file"] for row in before["nonresident"]]
    work = new_work(root / "condition")
    started = monotonic()
    args = [
        paired.PYTHON,
        "-IB",
        HERE / "combined_small_panel_residency.py",
        inputs["staged"],
        *files,
    ]
    receipt = {}
    try:
        receipt = check_command(capsule(args, work, inputs)) if files else {}
    finally:
        after = residency(inputs["files"])
        write(
            work / "outcome.json",
            dict(
                ready_sha256=pin,
                raw_clock=receipt,
                elapsed_with_isolation_s=monotonic() - started,
                before=before,
                after=after,
                eligible=not after["nonresident"],
            ),
        )
    if after["nonresident"]:
        raise ValueError("The existing staged original failed the one-pass resident conditioning")


def launch(root, pin, case):
    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("The paid original child requires the cleared low-priority CPU 2")
    priority = subprocess.check_output(
        ["/usr/bin/ionice", "-p", str(os.getpid())], text=True
    ).strip()
    if priority != "best-effort: prio 7":
        raise ValueError("The paid original child requires best-effort I/O priority 7")
    ready = verify_ready(root, pin)
    inputs = ready["cases"][case]
    if (
        case == "DS30-0107"
        and not (root / "DS30-0016" / "case.json").is_file()
        and not ready["cases"]["DS30-0016"]["residency"]["nonresident"]
    ):
        raise ValueError("Complete the preregistered 0016 pair before 0107")
    from combined_small_panel_score import checked_publication

    with LOCK.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        conditioning = None
        if case == "DS30-0016" and inputs["residency"]["nonresident"]:
            outcome = root / "condition/outcome.json"
            body = outcome.read_bytes()
            prep = json.loads(body)
            if prep["ready_sha256"] != pin or not prep["eligible"]:
                raise ValueError(
                    "The positive case lacks successful separate warm-source conditioning"
                )
            conditioning = digest(body)
        before = require_resident(inputs["files"])
        area = root / case
        area.mkdir()
        records = {}
        for role in CASES[case]["order"]:
            work = new_work(area / role)
            role_before = require_resident(inputs["files"])
            argv = command(root, case, work, inputs, role)
            write(
                work / "launch.json",
                dict(
                    command=argv,
                    ready_sha256=pin,
                    executed_at_ns=time_ns(),
                    all_source_pages=role_before,
                ),
            )
            faults = resource.getrusage(resource.RUSAGE_CHILDREN).ru_minflt
            process = paired.child(argv, work, CAP_SECONDS, lock.fileno())
            process["minor_faults"] = (
                resource.getrusage(resource.RUSAGE_CHILDREN).ru_minflt - faults
            )
            write(work / "process.json", process)
            if process["exit_code"] or process["timed_out"]:
                raise ValueError(
                    f"The paid {case} {role} failed. Its process receipt remains sealed"
                )
            verified = checked_publication(work, role, case, inputs, process)
            write(work / "verified.json", verified)
            records[role] = dict(
                result_sha256=digest((work / "verified.json").read_bytes()),
                process=process,
                source_after=require_resident(inputs["files"]),
            )
        after = require_resident(inputs["files"])
        print(
            write(
                area / "case.json",
                dict(
                    case=case,
                    ready_sha256=pin,
                    results=records,
                    before=before,
                    after=after,
                    order=CASES[case]["order"],
                    conditioning_sha256=conditioning,
                ),
            )
        )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prepare", "condition", "launch", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--ready-pin")
    cli.add_argument("--case", choices=CASES)
    args = cli.parse_args()
    if (
        args.root != args.root.resolve()
        or args.root.parent != Path("/dev/shm")
        or args.root.exists()
        and args.root.stat().st_dev != Path("/dev/shm").stat().st_dev
    ):
        raise ValueError("Use a private panel output directory in tmpfs")
    if args.action == "prepare" and args.case is None and args.ready_pin is None:
        prepare(args.root)
    elif args.action == "condition" and args.case is None and args.ready_pin:
        condition(args.root, args.ready_pin)
    elif args.action == "launch" and args.case and args.ready_pin:
        launch(args.root, args.ready_pin, args.case)
    elif args.action == "score" and args.case is None and args.ready_pin:
        from combined_small_panel_score import score

        score(args.root, args.ready_pin)
    else:
        cli.error("Choose prepare, a sealed launch with --case, or the sealed panel score")


if __name__ == "__main__":
    main()
