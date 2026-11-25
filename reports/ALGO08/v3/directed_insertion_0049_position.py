"""Admit and seal the single prepared all-accept saved publication."""

import argparse
import ctypes
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, RUSAGE_SELF, getrusage
import select
import signal
import subprocess
import sys
from time import monotonic, time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import directed_insertion_0049 as insertion  # noqa: E402
import held_shrink_0019_ram as ram  # noqa: E402


trial = insertion.trial
ROOT = Path("/dev/shm/leo-v3-directed-insertion-0049-02")
PROTOCOL = HERE/"ds30-0049-directed-position-protocol.md"
PLAN = "b3de48ab4d0fb6f49eea4c6b608fe89c29a1cb0989ff1fe3efd7a00aa9703fd3"
NATIVE = "98bdbeaef91c203e880865ba0d667eb8c5ca1608bdd8dc7e028ab49516411ffb"
SMOKE = "5d8aadf9b2d643d9ce16b20d5a5ebacdb4069ab0aabb454a14af0ab5fe922571"
RESULT = dict(case="DS30-0049",changed=10,refs=48,acquired=0,waveform_reads=0,solver_runs=0)
TIMEOUT = 15.
WATCH = 55.
READY = "position-ready-v2.json"


def paths():
    plan = trial.document(ROOT/"plan.json",PLAN)
    trial.document(ROOT/"derived-native.json",NATIVE)
    trial.document(HERE/"measurements/ds30-0049-directed-insertion-preflight.json",SMOKE)
    lock_stage = trial.document(trial.STAGE/"admission.json",trial.ADMISSION)
    authority = trial.document(trial.STAGE/"authority.json",lock_stage["authority_pin"])
    inventory = dict(authority=authority["archive_sha256"],offer=authority["region_sha256"],
                     cutoff=authority["causal_cutoff_utc_ns"])
    if (plan["original_archive"] != inventory["authority"] or plan["original_offer"] != inventory["offer"]
            or plan["original_saved_clock"]["wall_s"] != 6.36):
        raise ValueError("Need the exact original scientific authority and charged saved denominator")
    build = trial.document(trial.BUILD,trial.BUILD_PIN)
    inputs = {Path(v["path"]) for v in (*build["native"].values(),build["png"],build["portable_producer"])}
    index = build["native"]["--legacy-first-map-fast"]
    extra = trial.document(Path(index["path"]),index["sha256"])
    inputs |= {Path(extra[name]["path"]) for name in ("hasher","projection","template")}
    catalogue = trial.document(trial.STAGE/"catalogue.json")
    named = {name:entry["sha256"] for name,entry in catalogue.items()}
    if len(named) != 48 or insertion.signed.canonical(named) != authority["archive_sha256"]:
        raise ValueError("The directory does not describe the original causal catalogue")
    paths_by_name = {name:trial.STAGE/"tle/archive/space-track"/name for name in named}
    if any(Path(name).name != name or not name.endswith("-"+digest+".tle")
           or int(name.split("-",1)[0]) >= inventory["cutoff"] for name,digest in named.items()):
        raise ValueError("The signed catalogue includes a malformed or noncausal snapshot")
    inputs |= set(paths_by_name.values())
    inputs |= {trial.STAGE/name for name in ("authority.json","inventory.json","offer.json","catalogue.json","admission.json")}
    data = sorted(inputs | {ROOT/"plan.json",ROOT/"derived-native.json"})
    tmpfs = {os.statvfs(root).f_fsid for root in ("/dev/shm","/tmp")}
    if any(path.resolve(strict=True) != path or os.statvfs(path).f_fsid not in tmpfs for path in data):
        raise ValueError("Candidate and catalogue operands must be exact resident tmpfs files")
    trial.require_resident(data)
    if any(trial.identifier(path) != named[name] for name,path in paths_by_name.items()):
        raise ValueError("The resident causal bytes differ from the original authority")
    capacity = os.statvfs(ROOT)
    if capacity.f_bavail*capacity.f_frsize < 64*1024**2:
        raise ValueError("No 64 MiB headroom for private saved publication and scratch")
    sources = (HERE.parents[2],trial.CHARTED,trial.BUILD,ram.RELEASE,ram.PAYLOAD,
               (ram.RELEASE/"venv/bin/python").resolve(strict=True).parents[1],trial.LOCK,
               *(Path(name) for name in ("/usr","/etc/fonts","/etc/ld.so.cache","/etc/passwd","/etc/group",
                                         "/sys/devices/system/cpu")))
    return sorted(inputs),sources


def command(layout,*,smoke):
    with (patch.object(ram,"ROOT",ROOT),patch.object(ram,"OUTPUT",ROOT),
          patch.object(ram.saved,"ROOT",ROOT),patch.object(ram,"ARTIFACTS",("plan.json","derived-native.json"))):
        bind = ram.command(layout,"unused")
    cpu = "3" if smoke else "2"
    return ["/usr/bin/taskset","-c",cpu,*bind[:bind.index("--")+1],str(ram.RELEASE/"venv/bin/python"),
            "-IB",str(Path(__file__).resolve()),"smoke-child" if smoke else "paid-child"]


def isolated(*,smoke):
    ram.network_off()
    with patch.object(ram.saved,"ROOT",ROOT),patch.object(ram.saved,"STAGE",trial.STAGE):
        proof = ram.isolation_probe()
    descriptor = ROOT/"plan.json" if smoke else trial.LOCK
    if not os.path.samestat(os.fstat(0),descriptor.stat()):
        raise ValueError("The saved capsule did not inherit the required immutable descriptor")
    expected_cpu = {3} if smoke else {2}
    if os.sched_getaffinity(0) != expected_cpu or os.getpriority(os.PRIO_PROCESS,0) != 15:
        raise ValueError("Unexpected saved worker affinity or priority")
    print(json.dumps(proof,sort_keys=True),flush=True)
    trial.worker(ROOT,PLAN,insertion.EXPERIMENT,smoke=smoke,lease_fd=None if smoke else 0)
    if not smoke:
        usage = getrusage(RUSAGE_SELF)
        trial.write(ROOT/"process-usage.json",dict(cpu_s=usage.ru_utime+usage.ru_stime,
                    input_blocks=usage.ru_inblock,major_faults=usage.ru_majflt,minor_faults=usage.ru_minflt,
                    peak_rss_kib=usage.ru_maxrss))


def ready():
    cue = ROOT/READY
    if cue.exists() or (ROOT/"position-intent.json").exists():
        raise ValueError("This prepared position cell already has a readiness decision")
    for name in ("scratch","shm-root"):
        path = ROOT/name
        path.mkdir(mode=0o700,exist_ok=True)
        if path.is_symlink():
            raise ValueError("Expected a direct private scratch directory")
    alias = ROOT/"backing-alias"
    if not alias.is_symlink():
        alias.symlink_to("/srv/bulk",target_is_directory=True)
    if alias.readlink() != Path("/srv/bulk"):
        raise ValueError("The outside-source denial probe changed")
    layout = paths()
    with (ROOT/"plan.json").open("rb") as descriptor:
        result = subprocess.run(command(layout,smoke=True),capture_output=True,text=True,timeout=8,
                                check=False,stdin=descriptor)
    if result.returncode:
        raise ValueError(result.stderr)
    proof,smoke = map(json.loads,result.stdout.splitlines())
    if (any(proof[f"{name}_namespace"] == os.readlink(f"/proc/self/ns/{ns}")
            for name,ns in (("network","net"),("mount","mnt"))) or smoke != RESULT):
        raise ValueError("The exact saved-worker no-solve capsule did not verify")
    print(trial.write(cue,dict(plan=PLAN,native=NATIVE,preflight=SMOKE,proof=proof,smoke=smoke,
                         protocol=trial.identifier(PROTOCOL),launcher=trial.identifier(Path(__file__)),
                         inputs=list(map(str,layout[0])),sources=list(map(str,layout[1])),cap_s=TIMEOUT)))


def charge(layout,fd,event,age,acquired):
    intent = trial.write(ROOT/"position-intent.json",dict(plan=PLAN,event=event,initial_age_ns=age,
                                 lease_acquired_unix_ns=acquired,timeout_s=TIMEOUT))
    before, began = getrusage(RUSAGE_CHILDREN),monotonic()
    with (ROOT/"worker.stdout").open("xb") as stdout,(ROOT/"worker.stderr").open("xb") as stderr:
        with subprocess.Popen(command(layout,smoke=False),stdout=stdout,stderr=stderr,
                              stdin=fd,start_new_session=True) as child:
            try:
                status = child.wait(max(0.,TIMEOUT-(monotonic()-began)))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL)
                child.wait()
                status = 124
    elapsed = monotonic()-began
    after = getrusage(RUSAGE_CHILDREN)
    usage = trial.document(ROOT/"process-usage.json") if status == 0 else None
    wrapper = dict(cpu_s=(after.ru_stime+after.ru_utime)-(before.ru_stime+before.ru_utime),
                   input_blocks=after.ru_inblock-before.ru_inblock,major_faults=after.ru_majflt-before.ru_majflt)
    clock = trial.write(ROOT/"clock.json",dict(elapsed_s=elapsed,exit_code=status,python=usage,wrapper=wrapper,
                  cpu_s=None if usage is None else usage["cpu_s"],intent=intent,
                  scope="namespace launch through saved publication and process exit"))
    return dict(decision="worker-exited" if status == 0 else "worker-failed",child_started=True,
                clock=clock,exit_code=status,capped_s=TIMEOUT)


def admission(layout,event,pid):
    from reports.ALGO08.v3.directed_replay_0049_ram import allowed_event,RETRY_NS

    from contextlib import ExitStack
    with ExitStack() as stack:
        try:
            fd = stack.enter_context(ram.lease())
        except BlockingIOError:
            return dict(decision="shared-lock-held",child_started=False)
        acquired = time_ns()
        try:
            trial.require_resident([*layout[0],ROOT/"plan.json",ROOT/"derived-native.json"])
            age = allowed_event(event,pid)
            if (RETRY_NS-age)/1e9 < TIMEOUT+3:
                raise ValueError("No complete slot before the official retry")
        except (OSError,ValueError) as error:
            return dict(decision="prelaunch-refused",reason=str(error),child_started=False)
        result = charge(layout,fd,event,age,acquired)
    finished = time_ns()
    return result | dict(field_event=event,lease_release_upper_unix_ns=finished,
                         retry_no_earlier_than_ns=event["unix_ns"]+RETRY_NS)


def watch(pid,pin):
    from reports.ALGO08.v3.directed_replay_0049_ram import CAMPAIGN,DRIVER,DRIVER_PIN,FRESH_NS
    from field_crossover_admission_watch import MOVED_TO,recent_deferral,replaced_export

    if (ROOT/"position-watch.json").exists() or (ROOT/"position-intent.json").exists():
        raise ValueError("The one authorized saved position watch has already been used")
    proof = trial.document(ROOT/READY,pin)
    layout = paths()
    if (proof["launcher"] != trial.identifier(Path(__file__)) or proof["protocol"] != trial.identifier(PROTOCOL)
            or trial.identifier(DRIVER) != DRIVER_PIN or proof["inputs"] != list(map(str,layout[0]))
            or proof["sources"] != list(map(str,layout[1])) or proof["cap_s"] != TIMEOUT
            or proof["plan"] != PLAN or proof["native"] != NATIVE or proof["smoke"] != RESULT):
        raise ValueError("The authorized watch requires the unchanged protected saved worker")
    libc = ctypes.CDLL(None,use_errno=True)
    libc.inotify_add_watch.argtypes = (ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32)
    notice = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if notice < 0:
        raise OSError(ctypes.get_errno(),"inotify initialization")
    result = dict(decision="no-fresh-deferral",child_started=False)
    try:
        if libc.inotify_add_watch(notice,os.fsencode(CAMPAIGN),MOVED_TO) < 0:
            raise OSError(ctypes.get_errno(),"observe official export")
        since, deadline = time_ns(),monotonic()+WATCH
        while (left := deadline-monotonic()) > 0.:
            seen,_,_ = select.select([notice],[],[],left)
            if not seen or not replaced_export(os.read(notice,65536)):
                continue
            event = recent_deferral(CAMPAIGN,since,time_ns())
            if event is not None and time_ns()-event["unix_ns"] <= FRESH_NS:
                result = admission(layout,event,pid)
                break
    finally:
        os.close(notice)
    if result["decision"] == "worker-exited":
        result["seal"] = trial.write(ROOT/"prediction-seal.json",dict(plan_sha256=PLAN,
                            protocol=trial.protocol(insertion.EXPERIMENT),clock=result["clock"],
                            receipt=trial.identifier(ROOT/"receipt.json"),launch_protocol=trial.identifier(PROTOCOL)))
    print(trial.write(ROOT/"position-watch.json",result | dict(ready_pin=pin)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("ready","watch","smoke-child","paid-child","score"))
    parser.add_argument("--pid",type=int)
    parser.add_argument("--pin")
    args = parser.parse_args()
    if args.action.endswith("-child"):
        isolated(smoke=args.action == "smoke-child")
    elif args.action == "ready":
        ready()
    elif args.action == "watch" and args.pid is not None and args.pin is not None:
        watch(args.pid,args.pin)
    elif args.action == "score" and args.pin is not None:
        trial.score(ROOT,args.pin,insertion.EXPERIMENT)
    else:
        parser.error("The sealed readiness/admission pin and live official PID are required")
