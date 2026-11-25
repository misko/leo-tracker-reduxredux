"""Prepare and run the frozen DS30-0016/0107 original-waveform opt-in panel."""

import argparse
import fcntl
import json
import os
import resource
import subprocess
import sys
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
CAP_SECONDS = {"DS30-0016": 17, "DS30-0107": 7}
DRIVER = Path("/tmp/leo-v3-ds30-paired-evaluation/reports/ALGO08/v3/ds30_paired_evaluation.py")
DRIVER_PIN = "26b996e90e7ad4c467c551426a69e048d6078cf3c8087c741f9eef3c10f7df31"
FRESH_NS = 2_000_000_000
NATURAL_CAP = 8 * 1024 * 1024
FAILED_WARM_PIN = "c8a2c39eb13a3fcf113b8d1649cadb3700af885dd7604b5fd2b6d3f5178f4abe"
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


def bounded_natural_source(found, original, *, page):
    if any(
        not Path(row["file"]).is_relative_to(original) or not row["file"].endswith(".ci16.zst")
        for row in found["nonresident"]
    ):
        raise ValueError("Natural admission allows only paged original compressed members")
    missing = sum(
        ((row["size"] + page - 1) // page) * page - row["res"] for row in found["nonresident"]
    )
    if not 0 <= missing <= NATURAL_CAP:
        raise ValueError("The existing original exceeds the frozen 8 MiB nonresident extent bound")
    return dict(found, nonresident_page_bytes=missing, allowance_bytes=NATURAL_CAP)


def source_before(inputs, natural_swap):
    if natural_swap:
        return bounded_natural_source(
            residency(inputs["files"]), Path(inputs["staged"]), page=os.sysconf("SC_PAGE_SIZE")
        )
    return require_resident(inputs["files"])


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


def command(root, case, work, inputs, role, extra=(), *, meter=False):
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
    worker = [paired.PYTHON, "-IB", *entry, *role_args]
    if meter:
        worker = [
            paired.PYTHON,
            "-IB",
            HERE / "combined_small_panel_meter.py",
            work / "numeric-process.json",
            *worker,
        ]
    return capsule(worker, work, inputs)


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


def protocol_pin(natural_swap=False):
    body = (HERE / "combined-small-panel-protocol.md").read_bytes()
    if natural_swap:
        check(HERE / "measurements/combined-small-panel-0016-conditioning.json", FAILED_WARM_PIN)
        body += (HERE / "combined-small-panel-natural-protocol.md").read_bytes()
    return digest(body)


def source_pins():
    return {
        name: digest((HERE / name).read_bytes())
        for name in (
            "combined_small_panel.py",
            "combined_small_panel_entry.py",
            "combined_small_panel_score.py",
            "combined_small_panel_residency.py",
            "combined_small_panel_meter.py",
            "ds30_paired_worker.py",
            "ds30_paired_inputs.py",
            "profiled_grid_export_admission.py",
            "field_crossover_admission_watch.py",
        )
    }


def controller_preflight():
    from combined_small_panel_score import verifier_paths

    verifier_paths()
    from tools.pipeline_eval.qualification.paired_publication import child_usage

    return sorted(child_usage())


def prepare(root, *, natural_swap=False):
    start = monotonic()
    controller_counters = controller_preflight()
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
            meter_check = check_command(
                command(root, case, work, inputs, "charted", ["--preflight"], meter=True)
            )
            meter_receipt = json.loads((work / "numeric-process.json").read_bytes())
            if meter_check != preflight["charted"] or not meter_receipt["cpu_s"] > 0:
                raise ValueError(
                    "The inner worker meter did not observe the original metadata preflight"
                )
            inputs["meter_preflight"] = meter_receipt
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
                protocol_sha256=protocol_pin(natural_swap),
                sources=source_pins(),
                caps=CAP_SECONDS,
                natural_swap=natural_swap,
                grid=str(GRID),
                cases=cases,
                controls=CASES,
                installed=installed,
                controller_counters=controller_counters,
                preflight_elapsed_s=monotonic() - start,
            ),
        )
    )


def verify_ready(root, pin):
    ready = json.loads(check(root / "ready.json", pin))
    if (
        ready["protocol_sha256"] != protocol_pin(ready.get("natural_swap", False))
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
    ready = verify_ready(root, pin)
    if ready.get("natural_swap"):
        raise ValueError("Natural sample access rules out a new conditioning attempt")
    inputs = ready["cases"][case]
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


def authorized_order(root, ready, case, role):
    area = root / case
    first, second = CASES[case]["order"]
    if (area / role).exists() or role == second and not (area / first / "verified.json").is_file():
        raise ValueError("Require one fresh transaction in the registered within-case order")
    positive = root / "DS30-0016"
    if (
        case == "DS30-0107"
        and not (positive / "case.json").is_file()
        and not ready["cases"]["DS30-0016"]["residency"]["nonresident"]
    ):
        raise ValueError("Complete the preregistered 0016 pair before 0107")
    return max(
        (
            json.loads(path.read_bytes())["finished_unix_ns"]
            for path in root.glob("DS30-*/**/process.json")
        ),
        default=0,
    )


def official_0218_is_pending(rows):
    matched = [row for row in rows if row["case"] == "DS30-0218"]
    if len(matched) != 2 or {row["algorithm"] for row in matched} != {"installed", "successor"}:
        return False
    if any(
        row["verified_pair"]
        or row["admission_state"] != "deferred_storage_busy"
        or row["raw_identity_sha256"]
        != "sha256:9b08c27dfd179fcfa112d19bc6c4b1f10b3efd3f948005a8a298dc9b927866c9"
        for row in matched
    ):
        return False
    roles = {row["algorithm"]: row for row in matched}
    incumbent, successor = roles["installed"], roles["successor"]
    return (
        incumbent["outcome"] == "complete"
        and incumbent["acquisition_verified"]
        and successor["outcome"] == "pending"
        and not successor["acquisition_verified"]
        and all(
            successor[key] is None
            for key in ("attempt", "child_started_unix_ns", "attempt_result_sha256")
        )
    )


def driver_window(event, pid, last_finish, case, *, pending_0218):
    campaign = FROZEN.parent
    path = campaign / event["event"]
    if (
        path.parent != campaign / "cases" / event["case"] / "events"
        or int(path.name.split("-", 1)[0]) != event["unix_ns"]
        or json.loads(check(path, event["event_sha256"]))["state"] != "deferred_storage_busy"
    ):
        raise ValueError("Require a sealed official backing-storage deferral")
    proc = Path("/proc") / str(pid)
    words = (proc / "cmdline").read_bytes().split(b"\0")
    if (
        not any(
            a == os.fsencode(DRIVER) and b == b"run" for a, b in zip(words, words[1:], strict=False)
        )
        or b"--watch" not in words
        or (proc / "task" / str(pid) / "children").read_text().strip()
    ):
        raise ValueError("The official paired controller already has an active child or changed")
    if pending_0218:
        exported = check(campaign / "rows.jsonl", event["export_sha256"])
        if (
            case != "DS30-0107"
            or event["case"] != "DS30-0218"
            or not official_0218_is_pending(map(json.loads, exported.splitlines()))
        ):
            raise ValueError("The exact official 0218 successor is no longer pending and unstarted")
    age = time_ns() - event["unix_ns"]
    if (
        not 0 <= age <= FRESH_NS
        or event["unix_ns"] <= last_finish
        or 30 - age / 1e9 < CAP_SECONDS[case] + 6
    ):
        raise ValueError("A fresh deferral with room for the bounded worker is required")


def conditioning_pin(root, inputs, case, ready_pin):
    if case != "DS30-0016" or not inputs["residency"]["nonresident"]:
        return None
    body = (root / "condition/outcome.json").read_bytes()
    prep = json.loads(body)
    if prep["ready_sha256"] != ready_pin or not prep["eligible"]:
        raise ValueError("The positive case lacks successful separate warm-source conditioning")
    return digest(body)


def launch_cell(
    root, pin, ready, case, role, pid, event, last_finish, conditioning, *, pending_0218
):
    from combined_small_panel_score import checked_publication

    inputs = ready["cases"][case]
    natural_swap = ready.get("natural_swap", False)
    work = root / case / role
    argv = [
        "/usr/bin/taskset",
        "-c",
        "2",
        "/usr/bin/ionice",
        "-c2",
        "-n7",
        *command(root, case, work, inputs, role, meter=(case == "DS30-0016")),
    ]
    with LOCK.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = source_before(inputs, natural_swap)
        driver_window(event, pid, last_finish, case, pending_0218=pending_0218)
        work.parent.mkdir(exist_ok=True)
        new_work(work)
        write(
            work / "launch.json",
            dict(
                command=argv,
                ready_sha256=pin,
                driver_pid=pid,
                event=event,
                cap_s=CAP_SECONDS[case],
                pending_0218=pending_0218,
                natural_swap=natural_swap,
                source_before=before,
                previous_exit_unix_ns=last_finish,
            ),
        )
        faults = resource.getrusage(resource.RUSAGE_CHILDREN).ru_minflt
        process = paired.child(argv, work, CAP_SECONDS[case], lock.fileno())
        process["minor_faults"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_minflt - faults
        write(work / "process.json", process)
        after = residency(inputs["files"])
    if process["exit_code"] or process["timed_out"] or (after["nonresident"] and not natural_swap):
        raise ValueError(
            f"The paid {case} {role} failed exit or residency. Its receipt is retained"
        )
    verified = checked_publication(work, role, case, inputs, process)
    verified_pin = write(work / "verified.json", verified)
    write(
        work / "cell-seal.json",
        dict(
            result_sha256=verified_pin,
            event=event,
            process=process,
            source_before=before,
            source_after=after,
            natural_swap=natural_swap,
        ),
    )
    order = CASES[case]["order"]
    if role == order[-1]:
        records = {
            key: json.loads((work.parent / key / "cell-seal.json").read_bytes()) for key in order
        }
        write(
            work.parent / "case.json",
            dict(
                case=case,
                ready_sha256=pin,
                results=records,
                order=order,
                conditioning_sha256=conditioning,
                natural_swap=natural_swap,
            ),
        )
    return dict(
        status="verified_original_cell",
        case=case,
        role=role,
        event=event,
        process=process,
        verification=verified["verification"],
        verified_sha256=verified_pin,
    )


def watch(root, pin, case, role, pid, *, pending_0218):
    if os.sched_getaffinity(0) != {3} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Run the admission and verifier on low-priority CPU 3")
    sys.path.insert(0, str(REPO))
    from reports.ALGO08.v3.profiled_grid_export_admission import observe

    if pending_0218 and case != "DS30-0107":
        raise ValueError("Only the registered short pair can fill the pending 0218 gap")
    ready = verify_ready(root, pin)
    natural_swap = ready.get("natural_swap", False)
    if natural_swap and (case != "DS30-0016" or pending_0218):
        raise ValueError("Natural sample access was registered only for the normal 0016 admission")
    if ready["controller_counters"] != controller_preflight():
        raise ValueError("The independent controller's timing interface changed")
    last_finish = authorized_order(root, ready, case, role)
    inputs = ready["cases"][case]
    conditioning = None if natural_swap else conditioning_pin(root, inputs, case, pin)
    source_before(inputs, natural_swap)
    check(DRIVER, DRIVER_PIN)
    result = observe(
        lambda event: launch_cell(
            root,
            pin,
            ready,
            case,
            role,
            pid,
            event,
            last_finish,
            conditioning,
            pending_0218=pending_0218,
        ),
        "DS30-0218" if pending_0218 else None,
    )
    write(root / f"watch-{case}-{role}-{result['watching_from']}.json", result)
    print(json.dumps(result))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prepare", "condition", "watch", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--ready-pin")
    cli.add_argument("--case", choices=CASES)
    cli.add_argument("--role", choices=("charted", "trial"))
    cli.add_argument("--driver-pid", type=int)
    cli.add_argument("--pending-0218", action="store_true")
    cli.add_argument(
        "--natural-swap",
        action="store_true",
        help="prepare the fixed 0016 natural-access comparison",
    )
    args = cli.parse_args()
    if (
        args.root != args.root.resolve()
        or args.root.parent != Path("/dev/shm")
        or args.root.exists()
        and args.root.stat().st_dev != Path("/dev/shm").stat().st_dev
    ):
        raise ValueError("Use a private panel output directory in tmpfs")
    if args.action == "prepare" and args.case is None and args.ready_pin is None:
        prepare(args.root, natural_swap=args.natural_swap)
    elif args.action == "condition" and args.case is None and args.ready_pin:
        condition(args.root, args.ready_pin)
    elif args.action == "watch" and all((args.case, args.role, args.ready_pin, args.driver_pid)):
        watch(
            args.root,
            args.ready_pin,
            args.case,
            args.role,
            args.driver_pid,
            pending_0218=args.pending_0218,
        )
    elif args.action == "score" and args.ready_pin:
        from combined_small_panel_score import score

        score(args.root, args.ready_pin, selection=args.case)
    else:
        cli.error("Choose prepare, condition, a single sealed watch, or score")


if __name__ == "__main__":
    main()
