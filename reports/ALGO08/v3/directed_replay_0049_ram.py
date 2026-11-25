"""Prove isolated RAM admission and reuse the exact archived directed sweep."""

import argparse
import ctypes
import errno
import fcntl
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, RUSAGE_SELF, getrusage
import select
import signal
import socket
import subprocess
import sys
from time import monotonic, time_ns
from types import SimpleNamespace

from . import empty_lane_directed_replay as replay


RELEASE = replay.RELEASE
PYTHON = RELEASE / "venv/bin/python"
RUNTIME = PYTHON.resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
FROZEN_PLAN = Path("/tmp/leo-v3-empty-lane-directed-0049-plan01.json")
PLAN_PIN = "0075e0f970a4e5debd2d9398603bd600cd5df38573898324ce4019ae2c3c09e9"
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
DRIVER = Path("/tmp/leo-v3-ds30-paired-evaluation/reports/ALGO08/v3/ds30_paired_evaluation.py")
DRIVER_PIN = "26b996e90e7ad4c467c551426a69e048d6078cf3c8087c741f9eef3c10f7df31"
TIMEOUT = 12.0
FRESH_NS = 2_000_000_000
WATCH_SECONDS = 55
RETRY_NS = 30_000_000_000
PRIORITY = "DS30-0218"
THREADS = ("BLIS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS","OMP_NUM_THREADS",
           "OMP_THREAD_LIMIT","OPENBLAS_NUM_THREADS")
PROGRAM = ("reports/ALGO08/v3/directed_replay_0049_ram.py",) + tuple(
    f"reports/ALGO08/v3/{name}.py" for name in (
        "anchor_cfo_innovation","calibration_transport","capped_revisit","directed_donor",
        "directed_verifier_trial","ds30_paired_inputs","empty_lane_arrival","empty_lane_directed_replay",
        "first30_native_agreement","full_successor_score","matched_donor_0049","missed_owner_support",
        "original_prefix_scaling","prefetch_prefix_0049","receiver_refine_pgo_trial","satellite_set_transfer",
        "signed_cfo_time","signed_cfo_time_readout","track_cfo_denoise","within_aperture_chirp")
) + ("tools/pipeline_eval/__init__.py","tools/pipeline_eval/scoring.py",
     "tools/pipeline_eval/variants/__init__.py","tools/pipeline_eval/variants/carrier_continuation.py") + tuple(
    f"tools/pipeline_eval/variants/experimental/{name}.py" for name in (
        "receiver_benchmark","receiver_brackets","receiver_build","receiver_cfo_peak_bound",
        "receiver_refine_bound","receiver_tracking")
)
INSIDE_PLAN = Path("/directed-plan.json")


def pins():
    runtime = (PYTHON.resolve(),RELEASE/"src/leo/storage/fast_scan.py",
               RELEASE/"src/leo/storage/short_window.py",RELEASE/"src/leo/scanner/fast_scan_analysis.py")
    return {str(path):replay.tag(path) for path in runtime}


def resident(files):
    """Inspect resident pages without reading or warming any enrolled extent."""
    tmp_device = Path("/tmp").stat().st_dev
    records = {}
    for value in files:
        path = Path(value)
        stat = path.stat()
        if not path.is_file() or path.resolve(strict=True) != path or stat.st_dev != tmp_device:
            raise ValueError(f"Expected a direct tmpfs waveform operand {path}")
        records[str(path)] = [stat.st_dev,stat.st_ino,stat.st_size]
    try:
        result = subprocess.check_output(["/usr/bin/fincore","-bJ","-o","RES,SIZE,FILE",*records],
                                         text=True,timeout=2)
    except subprocess.TimeoutExpired as error:
        raise ValueError("The passive resident-page census exceeded two seconds") from error
    checked = {r["file"]:r for r in json.loads(result)["fincore"]}
    if checked.keys() != records.keys() or any(
            row["size"] != records[path][2] or row["res"] < row["size"] for path,row in checked.items()):
        raise ValueError("At least one original member, index, or manifest has nonresident bytes")
    return dict(files=records,resident_bytes=sum(r["res"] for r in checked.values()),
                logical_bytes=sum(r["size"] for r in checked.values()))


def locked_description(fd, path):
    """Prove both identity and inherited exclusive flock without unlocking it."""
    if not os.path.samestat(os.fstat(fd),path.stat()):
        raise ValueError("Inherited descriptor is a different inode from the bound lock")
    with path.open("rb") as independent:
        try:
            fcntl.flock(independent,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            raise ValueError("The inherited lock was not already held")
    try:
        fcntl.flock(fd,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise ValueError("The lock is held by a different open-file description") from error


def command(root, plan, cpu, filter_fd, *, proof):
    args = ["/usr/bin/taskset","-c",str(cpu),"/usr/bin/bwrap","--unshare-all","--unshare-user",
            "--disable-userns","--die-with-parent","--cap-drop","ALL","--clearenv","--seccomp",str(filter_fd),
            "--proc","/proc","--dev","/dev","--bind",str(root/"empty"),"/dev/shm"]
    for name in ("bin","lib","lib64"):
        args += ["--symlink",f"usr/{name}",f"/{name}"]
    private = ((root/"program",Path("/directed-program")),(root/"plan.json",INSIDE_PLAN),
               (root/"verifier.so",replay.LIBRARY),(root/"pilot.f32",replay.ASSET),
               (root/"proof.lock" if proof else replay.LOCK,replay.LOCK))
    runtime = (Path("/usr"),Path("/etc/ld.so.cache"),RELEASE/"venv",RELEASE/"src",RUNTIME)
    for path in (*runtime,*map(Path,plan["original_source"]["files"])):
        args += ["--ro-bind",str(path),str(path)]
    for source,target in private:
        args += ["--ro-bind",str(source),str(target)]
    args += ["--bind",str(root/"scratch"),"/directed-scratch"]
    args += ["--remount-ro","/dev/shm","--remount-ro","/","--chdir","/directed-program"]
    environment = dict.fromkeys(THREADS,"1") | dict(PATH="/usr/bin:/bin",LANG="C.UTF-8",
                                                    TMPDIR="/directed-scratch",MPLCONFIGDIR="/directed-scratch",
                                                    PYTHONPATH=f"/directed-program:{RELEASE}/src")
    for name,value in environment.items():
        args += ["--setenv",name,value]
    return args + ["--",str(PYTHON),"-Bm","reports.ALGO08.v3.directed_replay_0049_ram",
                   "proof" if proof else "sweep"]


def isolation(plan, *, proof):
    expected_cpu = {3} if proof else {2}
    if os.sched_getaffinity(0) != expected_cpu or os.getpriority(os.PRIO_PROCESS,0) < 15:
        raise ValueError("Require the enrolled low-priority CPU assignment")
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        before, after = line.split(" - ",1)
        fields = before.split()
        mounts[fields[4]] = (after.split()[0],fields[5].split(","))
    wave_files = tuple(plan["original_source"]["files"])
    readonly = (*wave_files,*map(str,(INSIDE_PLAN,replay.LIBRARY,replay.ASSET,replay.LOCK,
                                      Path("/directed-program"),Path("/"),Path("/dev/shm"))))
    if (any(mounts[name][0] != "tmpfs" for name in (*wave_files,str(INSIDE_PLAN),"/directed-program",
                                                    str(replay.LIBRARY),str(replay.ASSET),str(replay.LOCK)))
            or any("ro" not in mounts[name][1] for name in readonly)
            or mounts["/directed-scratch"][0] != "tmpfs"
            or any(name.startswith(("/mnt/qnap01","/srv/bulk")) or value[0] in {"xfs","nfs","nfs4","cifs"}
                   for name,value in mounts.items())):
        raise ValueError("The namespace has outside or writable input mounts")
    checks = {}
    forbidden = ("/mnt/qnap01","/srv/bulk","/proc/1/root/srv/bulk",str(CAMPAIGN),
                 str(Path(wave_files[0]).parent/"iq-000006.ci16.zst"))
    for path in forbidden:
        try:
            fd = os.open(path,os.O_RDONLY | os.O_CLOEXEC)
        except OSError as error:
            if error.errno not in (errno.ENOENT,errno.EPERM,errno.EACCES):
                raise
            checks[path] = error.errno
        else:
            os.close(fd)
            raise ValueError(f"An unenrolled source path opened {path}")
    for family in (socket.AF_INET,socket.AF_INET6,socket.AF_UNIX):
        try:
            with socket.socket(family):
                raise ValueError("Socket creation escaped the syscall denial")
        except PermissionError as error:
            if error.errno != errno.EPERM:
                raise
    locked_description(0,replay.LOCK)
    return dict(cpu=sorted(expected_cpu),readonly_files=len(wave_files),socket_denied=True,
                denied_paths=checks,operative_inherited_lock=True,private_probe_lock=proof,
                mount_namespace=os.readlink("/proc/self/ns/mnt"),network_namespace=os.readlink("/proc/self/ns/net"))


def inner(proof):
    plan = replay.prefix.read(INSIDE_PLAN,PLAN_PIN)
    if replay.tag(Path(replay.__file__)) != plan["source_sha256"]:
        raise ValueError("The original directed verifier worker changed")
    evidence = isolation(plan,proof=proof)
    allowed = frozenset(plan["original_source"]["files"][:1] if proof else plan["original_source"]["files"])
    sys.addaudithook(lambda event,params: replay.forbid_source(event,params,allowed=allowed))
    if proof:
        import numpy as np
        from leo.storage.fast_scan import FastSegmentSource
        from leo.storage.short_window import ShortWindowReader  # noqa: F401
        from leo.scanner.fast_scan_analysis import VerifiedFastWindow  # noqa: F401
        from .directed_verifier_trial import Directed

        source = FastSegmentSource(dict(path=plan["original_source"]["recording"],
                                        manifest_digest=replay.prefix.MANIFEST_PIN),stop_sequence=replay.prefix.WINDOWS)
        if tuple(source.receiver_ids) != (0,1):
            raise ValueError("Unexpected physical receiver lane configuration")
        pulse = Directed(SimpleNamespace(lib=ctypes.CDLL(str(replay.LIBRARY))),np.fromfile(replay.ASSET,dtype="<f4"))
        pulse.close()
        result = dict(isolation=evidence,manifest=source.manifest_digest,raw_reads=0,native_calls=0)
    else:
        result = dict(admitted=True,plan_sha256=PLAN_PIN,isolation=evidence,**replay.take(plan))
    process = getrusage(RUSAGE_SELF)
    return result | dict(python_usage=dict(cpu_s=process.ru_utime+process.ru_stime,input_blocks=process.ru_inblock,
                         minor_faults=process.ru_minflt,major_faults=process.ru_majflt,peak_rss_kib=process.ru_maxrss))


def invoke(root,plan,fd,*,proof,cancel=None):
    before, start = getrusage(RUSAGE_CHILDREN),monotonic()
    cancelled = None
    with (root/"sockets.bpf").open("rb") as sc:
        modes = command(root,plan,3 if proof else 2,sc.fileno(),proof=proof)
        with subprocess.Popen(modes,stdin=fd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              pass_fds=(sc.fileno(),),text=True,start_new_session=True) as child:
            while True:
                remaining = TIMEOUT-(monotonic()-start)
                try:
                    if cancel is not None:
                        cancel()
                except (OSError,ValueError) as error:
                    cancelled = str(error)
                if cancelled is not None or remaining <= 0.:
                    try:
                        os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    stdout,stderr = child.communicate()
                    code = 125 if cancelled is not None else 124
                    break
                try:
                    stdout,stderr = child.communicate(timeout=min(remaining,.05) if cancel else remaining)
                    code = child.returncode
                    break
                except subprocess.TimeoutExpired:
                    continue
    after,end = getrusage(RUSAGE_CHILDREN),monotonic()
    clock = dict(exit_code=code,elapsed_s=end-start,wrapper_cpu_s=(after.ru_utime-before.ru_utime)+(after.ru_stime-before.ru_stime),
                 wrapper_input_blocks=after.ru_inblock-before.ru_inblock,
                 wrapper_minor_faults=after.ru_minflt-before.ru_minflt,wrapper_major_faults=after.ru_majflt-before.ru_majflt,
                 cancelled_reason=cancelled)
    return clock,json.loads(stdout) if code == 0 else None,stderr


def ready(root):
    from .held_cfo_features_capsule import sock_filter

    if root.parent != Path("/dev/shm") or os.sched_getaffinity(0) != {3}:
        raise ValueError("Prepare off-slot on CPU3 in a fresh private tmpfs root")
    plan = replay.prefix.read(FROZEN_PLAN,PLAN_PIN)
    if (replay.tag(Path(replay.__file__)) != plan["source_sha256"]
            or plan["original_source"] != replay.local_custody()):
        raise ValueError("The staged set must match the old candidate-only custody freeze")
    observations = resident(plan["original_source"]["files"])
    root.mkdir(mode=0o700)
    (root/"empty").mkdir()
    (root/"scratch").mkdir(mode=0o700)
    (root/"proof.lock").touch(exist_ok=False)
    assets = {"plan.json":(FROZEN_PLAN,PLAN_PIN),"verifier.so":(replay.LIBRARY,replay.LIBRARY_PIN),
              "pilot.f32":(replay.ASSET,replay.ASSET_PIN)}
    for name,(path,pin) in assets.items():
        (root/name).write_bytes((replay.prefix.pinned(path,pin)))
        (root/name).chmod(0o400)
    sources = {}
    for name in PROGRAM:
        source,target = ROOT/name,root/"program"/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(source.read_bytes())
        target.chmod(0o400)
        sources[name] = replay.tag(source)
    sock_filter(root/"sockets.bpf")
    with (root/"proof.lock").open("rb") as lease:
        fcntl.flock(lease,fcntl.LOCK_EX | fcntl.LOCK_NB)
        clock,evidence,error = invoke(root,plan,lease,proof=True)
    if evidence is None or evidence["isolation"]["mount_namespace"] == os.readlink("/proc/self/ns/mnt") or (
            evidence["isolation"]["network_namespace"] == os.readlink("/proc/self/ns/net")):
        raise ValueError(f"The no-waveform capsule failed: {clock} {error}")
    replay.prefix.write(root/"ready.json",dict(plan_pin=PLAN_PIN,source_files=sources,runtime=pins(),
                        residency=observations,filter_pin=replay.tag(root/"sockets.bpf"),proof=evidence,clock=clock))


def controller_idle(pid):
    process = Path("/proc")/str(pid)
    argv = (process/"cmdline").read_bytes().split(b"\0")
    if (not any(arg == os.fsencode(DRIVER) and argv[i+1] == b"run" for i,arg in enumerate(argv[:-1]))
            or b"--watch" not in argv or (process/"task"/str(pid)/"children").read_text().split()):
        raise ValueError("The original official retry controller must be live and idle")


def allowed_event(event,pid):
    path = CAMPAIGN/event["event"]
    if (path.parent != CAMPAIGN/"cases"/event["case"]/"events"
            or int(path.name.split("-",1)[0]) != event["unix_ns"]
            or replay.prefix.read(path,event["event_sha256"])["state"] != "deferred_storage_busy"):
        raise ValueError("A fresh original official storage deferral is required")
    controller_idle(pid)
    age = time_ns()-event["unix_ns"]
    if not 0 <= age <= FRESH_NS or (RETRY_NS-age)/1e9 <= TIMEOUT+2:
        raise ValueError("The official deferral no longer contains the complete capped launch")
    return age


def priority_rows():
    path = CAMPAIGN/"rows.jsonl"
    rows = [json.loads(line) for line in path.read_bytes().splitlines() if b'"DS30-0218"' in line]
    rows = [row for row in rows if row["case"] == "DS30-0218"]
    if len(rows) != 2 or {r["algorithm"] for r in rows} != {"installed","successor"}:
        raise ValueError("The official DS30-0218 priorities could not be verified")
    return {row["algorithm"]:row for row in rows}


def priority_clear():
    """Require the higher-priority official case to remain unstarted."""
    rows = priority_rows()
    if ((CAMPAIGN/"cases/DS30-0218/pair.json").exists()
            or any(row["outcome"] != "pending" or row["admission_state"] != "pending"
                   or row["attempt"] is not None or row["verified_pair"] for row in rows.values())):
        raise ValueError("The priority DS30-0218 pair is underway or no longer pending")


def successor_unstarted(pid):
    controller_idle(pid)
    folder = CAMPAIGN/"cases"/PRIORITY
    if (folder/"successor").exists() or (folder/"pair.json").exists():
        raise ValueError("The priority DS30-0218 successor has started")


def priority_deferral(pid,event=None):
    successor_unstarted(pid)
    rows = priority_rows()
    installed, successor = rows["installed"], rows["successor"]
    folder = CAMPAIGN/"cases"/PRIORITY
    if (installed["outcome"] != "complete" or not installed["attempt"] or not installed["attempt_result_sha256"]
            or successor["outcome"] != "pending" or successor["admission_state"] != "deferred_storage_busy"
            or successor["attempt"] is not None or successor["attempt_result_sha256"] is not None
            or installed["verified_pair"] or successor["verified_pair"]):
        raise ValueError("DS30-0218 must have its installed arm complete and successor pending and deferred")
    attempt = CAMPAIGN/installed["attempt"]
    if not attempt.is_relative_to(folder/"installed") or not attempt.is_file():
        raise ValueError("DS30-0218's completed installed attempt lacks its official result")
    replay.prefix.read(attempt,installed["attempt_result_sha256"])
    if event is not None:
        events = sorted((folder/"events").glob("*.json"))
        if event["case"] != PRIORITY or not events or events[-1] != CAMPAIGN/event["event"]:
            raise ValueError("The event is not the latest official DS30-0218 deferral")
    return dict(installed=installed["attempt_result_sha256"],successor=successor["admission_state"])


def watch(root,pid,ready_pin,*,allow_code_io=False,priority_released=False,priority_gap=False):
    from .field_crossover_admission_watch import MOVED_TO,recent_deferral,replaced_export

    watch_path = root/("watch-0218-gap.json" if priority_gap else "watch.json")
    if (root.parent != Path("/dev/shm") or os.sched_getaffinity(0) != {3}
            or watch_path.exists() or (root/"intent.json").exists() or (priority_released and priority_gap)):
        raise ValueError("Use the unused preflight on CPU3")
    state = replay.prefix.read(root/"ready.json",ready_pin)
    plan = replay.prefix.read(root/"plan.json",PLAN_PIN)
    try:
        if priority_gap:
            priority_deferral(pid)
        elif not priority_released:
            priority_clear()
        if (state["plan_pin"] != PLAN_PIN or state["runtime"] != pins() or replay.tag(DRIVER) != DRIVER_PIN
                or state["filter_pin"] != replay.tag(root/"sockets.bpf")
                or any(replay.tag(ROOT/name) != pin or replay.tag(root/"program"/name) != pin
                       for name,pin in state["source_files"].items())
                or resident(plan["original_source"]["files"]) != state["residency"]):
            raise ValueError("The separately sealed capsule, runtime, or page-resident source changed")
    except (OSError,ValueError) as error:
        replay.prefix.write(watch_path,dict(admitted=False,reason=str(error)))
        return
    libc = ctypes.CDLL(None,use_errno=True)
    libc.inotify_add_watch.argtypes = (ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32)
    handle = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if handle < 0:
        raise OSError(ctypes.get_errno(),"inotify_init1")
    result = dict(admitted=False,reason="no-fresh-official-deferral")
    try:
        if libc.inotify_add_watch(handle,os.fsencode(CAMPAIGN),MOVED_TO) < 0:
            raise OSError(ctypes.get_errno(),"watch official ledger")
        since, deadline = time_ns(),monotonic()+WATCH_SECONDS
        while (remaining := deadline-monotonic()) > 0:
            changed,_,_ = select.select([handle],[],[],remaining)
            if not changed or not replaced_export(os.read(handle,65536)):
                continue
            event = recent_deferral(CAMPAIGN,since,time_ns())
            if event is None or time_ns()-event["unix_ns"] > FRESH_NS:
                continue
            if priority_gap and event["case"] != PRIORITY:
                continue
            result = admitted(root,plan,state,pid,event,allow_code_io=allow_code_io,
                              priority_released=priority_released,priority_gap=priority_gap)
            if result["admitted"]:
                result["lease_release_upper_unix_ns"] = time_ns()
                result["official_retry_no_earlier_than_ns"] = event["unix_ns"]+RETRY_NS
            break
    finally:
        os.close(handle)
    replay.prefix.write(watch_path,result)


def qualifications(clock,result,unchanged,*,allow_code_io):
    resident_source = (unchanged and clock["exit_code"] == 0 and clock["elapsed_s"] <= TIMEOUT
                       and result["isolation"]["operative_inherited_lock"] and not result["isolation"]["private_probe_lock"]
                       and result["post_staged_source_mode"] == "verified-tmpfs-only")
    zero_blocks = (not clock["wrapper_input_blocks"] and not result["python_usage"]["input_blocks"]
                   and not result["input_blocks"])
    return dict(resident_source=resident_source,strict_zero_process_input=resident_source and zero_blocks,
                qualified=resident_source and (allow_code_io or zero_blocks))


def admitted(root,plan,state,pid,event,*,allow_code_io=False,priority_released=False,priority_gap=False):
    with replay.LOCK.open("rb") as fd:
        try:
            fcntl.flock(fd,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return dict(admitted=False,reason="operative-lease-held",field_event=event)
        acquired = time_ns()
        try:
            if resident(plan["original_source"]["files"]) != state["residency"]:
                raise ValueError("The original files changed after the RAM-only proof")
            priority_state = None
            if priority_gap:
                priority_state = priority_deferral(pid,event)
            elif not priority_released:
                priority_clear()
            age = allowed_event(event,pid)
        except (OSError,ValueError) as error:
            return dict(admitted=False,reason=str(error),field_event=event)
        replay.prefix.write(root/"intent.json",dict(field_event=event,initial_age_ns=age,time_limit_s=TIMEOUT,
                            plan_pin=PLAN_PIN,source_sha256=plan["source_sha256"],
                            allow_root_runtime_io=allow_code_io,priority_release_received=priority_released,
                            priority_deferral_gap=priority_gap,priority_state=priority_state,
                            lease_acquired_unix_ns=acquired))
        cancel = (lambda: successor_unstarted(pid)) if priority_gap else None
        clock,result,error = invoke(root,plan,fd,proof=False,cancel=cancel)
        outcome = dict(admitted=True,clock=clock,field_event=event,stderr=error,priority_deferral_gap=priority_gap,
                       priority_release_received=priority_released,lease_acquired_unix_ns=acquired)
        if result is None:
            return outcome | dict(qualified=False,reason="capped-child-did-not-complete")
        try:
            unchanged = resident(plan["original_source"]["files"]) == state["residency"]
        except ValueError:
            unchanged = False
        result = result | dict(post_staged_source_mode="verified-tmpfs-only" if unchanged else "changed",
                               post_residency_unchanged=unchanged,capsule_clock=clock)
        gates = qualifications(clock,result,unchanged,allow_code_io=allow_code_io)
        result = result | dict(admitted=gates["qualified"],qualification=gates)
        replay.prefix.write(root/"waveforms.json",result)
        pin = replay.tag(root/"waveforms.json")
        return outcome | gates | dict(waveform_sha256=pin)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("ready","watch","proof","sweep"))
    parser.add_argument("--root",type=Path)
    parser.add_argument("--pid",type=int)
    parser.add_argument("--ready-pin")
    parser.add_argument("--allow-root-runtime-io",action="store_true")
    parser.add_argument("--priority-release-received",action="store_true")
    parser.add_argument("--priority-deferral-gap",action="store_true")
    args = parser.parse_args()
    if args.action in ("proof","sweep"):
        print(json.dumps(inner(args.action=="proof"),allow_nan=False))
    elif args.root is None:
        parser.error("A fresh private root is required")
    elif args.action == "ready":
        ready(args.root)
    elif args.pid is None or args.ready_pin is None:
        parser.error("A watch requires the exact official PID and ready receipt pin")
    else:
        watch(args.root,args.pid,args.ready_pin,allow_code_io=args.allow_root_runtime_io,
              priority_released=args.priority_release_received,priority_gap=args.priority_deferral_gap)
