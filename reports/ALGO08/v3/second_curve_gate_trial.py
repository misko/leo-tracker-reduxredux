"""Observe the original charted second curve gate on one authenticated saved packet."""

import argparse
from contextlib import redirect_stdout
import ctypes
import fcntl
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import resource
import runpy
import select
import signal
import subprocess
import sys
from time import monotonic, process_time, time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pre_screen_owner_readout import CASES, inputs, signature
from second_curve_gate_trace import ReachedSecondGate, binding


CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
HISTORICAL_ADAPTER = Path("/srv/postgres-nvme/leo-ds30-research-worktrees/0220-mixed-repair-divergence/reports/ALGO08/v3")
WATCHER = Path("/srv/postgres-nvme/leo-ds30-research-worktrees/field-receiver-solver-cross/reports/ALGO08/v3/field_crossover_admission_watch.py")
OFFICIAL = Path("/tmp/leo-v3-ds30-paired-evaluation/reports/ALGO08/v3/ds30_paired_evaluation.py")
ADAPTER_PIN = "b1e39c7c3baf0281c6213b4c641f32ffc5c8a5989786923beabe434f8b69da34"
WATCHER_PIN = "5a30d1cfcfa675db74f023a28ed0c026746c19784a8efa97ae757426e2ffd023"
OFFICIAL_PIN = "26b996e90e7ad4c467c551426a69e048d6078cf3c8087c741f9eef3c10f7df31"
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
WINDOW_S = 90
TIMEOUT_S = 18
FRESH_NS = 2_000_000_000
CASES_ORDER = ("DS30-0220", "DS30-0086")


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as out:
        json.dump(value,out,sort_keys=True,allow_nan=False,indent=2)
        out.write("\n")


def old_adapter():
    path = HISTORICAL_ADAPTER/"mixed_repair_centre_reset_trial.py"
    if sha(path)!=ADAPTER_PIN:
        raise ValueError("The no-solve-confirmed saved adapter changed")
    sys.path.insert(1,str(HISTORICAL_ADAPTER))
    import mixed_repair_centre_reset_trial as adapter
    if Path(adapter.__file__).resolve()!=path:
        raise ValueError("Historical saved adapter imported from the wrong tree")
    return adapter


def load(case, adapter):
    started = monotonic(), process_time()
    with patch.object(adapter,"CASE",case):
        state = adapter.launch_inputs()
    stage, spec, publication, args, handoff, paths, resident, before, sources, acceleration, artifacts = state
    charted = adapter.charted_adapter()
    manifest = adapter.assert_witness_sources(stage.chart_m["source_sha256"])
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.short_window import ShortWindowReader
    import blind_joint_finish as finish

    if (stage.mix["native_sha256"]!="sha256:"+CASES[case]["native"] or handoff.calls
            or not paths or before["cached_pages"]!=before["observed_file_pages"]):
        raise ValueError("Saved mixed handoff or resident-only archive changed")
    return stage,spec,publication,args,handoff,paths,resident,before,sources,acceleration,artifacts,charted,manifest,finish,(
        FastSegmentSource,ShortWindowReader),dict(wall_s=monotonic()-started[0],cpu_s=process_time()-started[1])


def snapshot(trace):
    before, after = {}, {}
    for row in trace["tracks"]:
        value = row["norad"],row["role"]
        for key in row["observation_ids"]:
            if key in before:
                raise ValueError("Duplicate gate owner")
            before[key] = value
            if row["compatible"]:
                after[key] = value
    return dict(input=signature(before),output=signature(after),n_input=len(before),n_output=len(after))


def preflight(case, output):
    adapter = old_adapter()
    stage,spec,_,args,handoff,_,_,before,_,_,artifacts,_,manifest,finish,_,prepare = load(case,adapter)
    from combined_successor_raw_entry import smoke
    import legacy_first_map_acceleration as acceleration

    adapter.checked_lazy_tools()
    args.legacy_first_map_fast, = (p for p in artifacts if p.name=="artifacts.json")
    args.legacy_first_map_fast_sha256 = "sha256:"+sha(args.legacy_first_map_fast)
    args.output = output.with_suffix(".unused-publication")
    stdout = StringIO()
    with binding(finish,lambda row: (_ for _ in ()).throw(AssertionError(row)),record_reasons=True), redirect_stdout(stdout):
        smoke(args,acceleration)
    if handoff.calls or args.output.exists():
        raise ValueError("Stage preflight must exercise positive ports without inference")
    # Rebuild just the ordinary Graph track preparation and original discrete
    # charts. This expectation is sealed before opening the observation hook.
    _,_,_,replay = inputs(case,CASES[case])
    stages = replay["stages"]
    expected = {}
    for label,enter,exit in (("first","cold","first"),("after_salvage","before_second","second")):
        expected[label] = dict(input=signature(stages[enter]),output=signature(stages[exit]),
                               n_input=len(stages[enter]),n_output=len(stages[exit]))
    checks = dict(case=case,resident_archive=before,native_sha256=stage.mix["native_sha256"],
                  archive_sha256=stage.authority["archive_sha256"],offer_sha256=stage.authority["region_sha256"],
                  compatible_solver_sources=manifest,source_ready=json.loads(stdout.getvalue()),source_ready_cost=prepare,
                  physics_scope="released Graph and metadata only",installed_dso=spec["detector_sha256"],
                  expected_stage_masks=expected,waveform_reads=0,position_solver_calls=0)
    write(output,checks)


def saved_worker(case, root, proof, pin, fd):
    if sha(proof)!=pin or not os.path.samestat(os.fstat(fd),LOCK.stat()):
        raise ValueError("Expected approved stage, preflight and inherited shared lease")
    ready = json.loads(proof.read_bytes())
    adapter = old_adapter()
    stage,spec,publication,args,handoff,paths,resident,before,sources,acceleration,_,charted,manifest,finish,stores,prep = load(case,adapter)
    if (ready["case"]!=case or ready["native_sha256"]!=stage.mix["native_sha256"]
            or ready["archive_sha256"]!=stage.authority["archive_sha256"]
            or ready["offer_sha256"]!=stage.authority["region_sha256"]
            or ready["compatible_solver_sources"]!=manifest or ready["resident_archive"]!=before):
        raise ValueError("Original verified ready conditions changed")
    args.output = root/"partial-cell"
    seen, start = [], (monotonic(),process_time())
    from tools.pipeline_eval.variants import v5_core

    def deny(*args, **kwargs):
        raise RuntimeError("Stage-only trace cannot run an original acquisition or named fallback")

    def emit(row):
        label = row["screen"]
        if snapshot(row)!=ready["expected_stage_masks"][label]:
            raise RuntimeError("Original screen observation differs from its frozen discrete mask")
        seen.append(label)
        write(root/f"{label}.json",row)

    write(root/"stage-start.json",dict(numerical_entry=True,local_preparation=prep,started_unix_ns=time_ns()))
    try:
        with (patch.object(stores[0],"windows",deny),patch.object(stores[1],"windows",deny),
              patch.object(v5_core,"infer",deny),patch.object(finish,"finish_pair",deny),
              binding(finish,emit,stop_after_second=True,record_reasons=True)):
            charted(publication,spec,sources,args,handoff,stage.authority,stage.inventory,acceleration)
    except ReachedSecondGate:
        pass
    else:
        raise ValueError("Charted stage did not hit the required original second drop")
    if (seen!=["first","after_salvage"] or handoff.calls!=1 or resident(paths)!=before
            or list(args.output.rglob("terminal.json")) or list(args.output.rglob("*.png"))):
        raise ValueError("Stage-only exit did not preserve exact custody and no-finish policy")
    write(root/"stage-result.json",dict(case=case,native_sha256=ready["native_sha256"],prepared=prep,
        acquisition=0,finishing_fits=0,rendered=0,elapsed_s=monotonic()-start[0],cpu_s=process_time()-start[1],
        masks={label:sha(root/f"{label}.json") for label in seen},method="actual pinned second gate and early stop"))


def event_admits(event):
    path = CAMPAIGN/event["event"]
    if (path.parent!=CAMPAIGN/"cases"/event["case"]/"events"
            or "sha256:"+sha(path)!=event["event_sha256"]
            or json.loads(path.read_bytes())["state"]!="deferred_storage_busy"):
        raise ValueError("Expected a verified official storage deferral")
    if not 0 <= time_ns()-event["unix_ns"] <= FRESH_NS:
        raise ValueError("Official deferral too old to keep the 18-second termination cap clear of its 30-second poll")


def launch(case, root, proof, proof_pin, event):
    event_admits(event)
    with LOCK.open("rb") as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        event_admits(event)
        work = root/"run"
        work.mkdir(mode=0o700)
        scratch = work/"scratch"
        scratch.mkdir()
        wrapper = [sys.executable,"-IB",str(Path(__file__).resolve()),"worker",case,str(work),str(proof),proof_pin,
                   "--lease-fd",str(lease.fileno())]
        env = dict(os.environ,TMPDIR=str(scratch),MPLCONFIGDIR=str(scratch),XDG_CACHE_HOME=str(scratch))
        with (work/"stdout").open("x") as stdout, (work/"stderr").open("x") as stderr:
            began, age = monotonic(),time_ns()-event["unix_ns"]
            if age>FRESH_NS:
                raise ValueError("Official deferral expired before launch")
            prior = resource.getrusage(resource.RUSAGE_CHILDREN)
            with subprocess.Popen(wrapper,stdout=stdout,stderr=stderr,env=env,start_new_session=True,
                                  pass_fds=(lease.fileno(),)) as proc:
                try:
                    status = proc.wait(max(0,TIMEOUT_S-(monotonic()-began)))
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL)
                    proc.wait()
                    status = 124
            following = resource.getrusage(resource.RUSAGE_CHILDREN)
        write(work/"clock.json",dict(exit=status,wall_s=monotonic()-began,deferral_age_ns=age,
            cpu_s=following.ru_utime+following.ru_stime-prior.ru_utime-prior.ru_stime,
            stage_started=(work/"stage-start.json").is_file(),terminated_unix_ns=time_ns()))
        return status


def watch(case, root, proof, proof_pin):
    if sha(proof)!=proof_pin or sha(WATCHER)!=WATCHER_PIN or sha(OFFICIAL)!=OFFICIAL_PIN:
        raise ValueError("Stage preflight, observed deferral behavior or 30-second poll source changed")
    sys.path.insert(0,str(HISTORICAL_ADAPTER))
    from field_receiver_solver_cross import attrs

    host = attrs(expected_priority="idle")
    observer = runpy.run_path(str(WATCHER))
    libc = ctypes.CDLL(None,use_errno=True)
    libc.inotify_add_watch.argtypes = (ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32)
    fd = libc.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
    if fd<0:
        raise OSError(ctypes.get_errno(),"inotify_init1")
    try:
        if libc.inotify_add_watch(fd,os.fsencode(CAMPAIGN),observer["MOVED_TO"])<0:
            raise OSError(ctypes.get_errno(),"inotify_add_watch")
        root.mkdir(mode=0o700)
        started, deadline, exports = time_ns(),monotonic()+WINDOW_S,0
        write(root/"watch-start.json",dict(case=case,host=host,started_ns=started,window_s=WINDOW_S,ready_sha256=proof_pin))
        while (seconds := deadline-monotonic())>0:
            readable,_,_ = select.select([fd],[],[],seconds)
            if not readable or not observer["replaced_export"](os.read(fd,65536)):
                continue
            exports += 1
            event = observer["recent_deferral"](CAMPAIGN,started,time_ns())
            if event is None or time_ns()-event["unix_ns"]>FRESH_NS:
                continue
            write(root/"gate.json",event)
            try:
                status = launch(case,root,proof,proof_pin,event)
            except (OSError,ValueError) as error:
                write(root/"watch-end.json",dict(status="single_admission_declined",reason=str(error),exports=exports))
                return 3
            write(root/"watch-end.json",dict(status=status,exports=exports,attempts=1))
            return status
        write(root/"watch-end.json",dict(status="no_qualifying_storage_deferral",exports=exports,attempts=0))
        return 3
    finally:
        os.close(fd)


if __name__=="__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode",choices=("preflight","watch","worker"))
    cli.add_argument("case",choices=CASES_ORDER)
    cli.add_argument("output",type=Path)
    cli.add_argument("preflight",type=Path,nargs="?")
    cli.add_argument("pin",nargs="?")
    cli.add_argument("--lease-fd",type=int)
    args = cli.parse_args()
    if args.mode=="preflight":
        preflight(args.case,args.output)
    elif args.mode=="watch":
        sys.exit(watch(args.case,args.output,args.preflight,args.pin))
    else:
        saved_worker(args.case,args.output,args.preflight,args.pin,args.lease_fd)
