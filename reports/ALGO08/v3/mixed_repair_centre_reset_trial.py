"""Seal or, with an explicit reviewed launch, exercise one saved mixed packet."""

import argparse
from contextlib import redirect_stdout
import ctypes
import fcntl
from hashlib import sha256
import json
from io import StringIO
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import runpy
import select
import signal
import subprocess
import sys
from time import perf_counter, process_time, time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mixed_repair_centre_reset import binding, eligible


CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
CASE = "DS30-0220"
CHARTED = Path("/tmp/leo-v3-integrated-original-batch")
BUILD = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
ACCEPTED = "complete"
TIMEOUT_S = 25
FRESH_NS = 2_000_000_000
WATCHER = Path("/srv/postgres-nvme/leo-ds30-research-worktrees/field-receiver-solver-cross/reports/ALGO08/v3/field_crossover_admission_watch.py")
WATCHER_SHA256 = "5a30d1cfcfa675db74f023a28ed0c026746c19784a8efa97ae757426e2ffd023"
LAZY_TOOLS = {
    "v5_orbit_domain.py": "14be68cd3af6906dbe0df64841e6a756e93caf234ad11b553bd1d8937fc2e18f",
    "algo08_blind_rank.py": "321df8d3771fd478543e7c161a4b1c7d1a84734c8c4a0ae2768ebdf1c9038831",
}
CONTROLS = {
    CASE: ("d307ff5f4a02fe144eb1547574728a46bf19b4365d971687c471adea65aa4755",
           "b8be7fef63a425d3fd15de1ca206f6ec40be65b96afa8d114fb0e8808c8a36eb",
           "7340a32a4722c7c03e122f2558b48fa0d98c53b36df9ff80506a136cd16980c0",
           "e72ccf4828795471e230547c50e806be6fc2a7d04ceb4b6b01e94358bf928fc6",
           "45253ba9c06057eb98d344b908cfd3ce5fa415958d7b91df9431cd66d6df874d"),
    "DS30-0086": ("407765fa47754cc99556143888b286e88f4674ab21836d3f437ac8af4c2ca439",
                  "5d775bbb9ff01ca9943c8001ed316cd2d65925da8348368452ddd8c0855ae084",
                  "0dfef18b5ce9a81b4c1df4f74ba7e27f135b400b3fdb96f78cddc3553d8c691f",
                  "6573ddcd116a7ec44da9d3d72711e45f67f0be059d65f65cf944a51f63611dcd",
                  "71b42b5c21f1f117981d18462f8fc4ccc883039e4cfdb9b2ed661380098a4bfd"),
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def verified(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Sealed input changed at {path}")
    return json.loads(data)


def save(path, value):
    with path.open("x") as output:
        json.dump(value, output, sort_keys=True, allow_nan=False, indent=2)
        output.write("\n")


def metadata(case):
    pair_pin, witness_pin, admission_pin, seal_pin, score_pin = CONTROLS[case]
    root = CAMPAIGN / "cases" / case
    pair = verified(root / "pair.json", pair_pin)
    installed, mixed = [verified(root / arm / "attempt-000001/result.json", pair["attempt_result_sha256"][arm])
                        for arm in ("installed", "successor")]
    charted = verified(root / "successor/attempt-000001/publication/exact-named-raw-witness.json", witness_pin)
    saved = Path(f"/dev/shm/leo-v3-field-receiver-solver-cross-{case[-4:]}-01")
    admission = verified(saved / "admission.json", admission_pin)
    seal = verified(saved / "prediction-seal.json", seal_pin)
    if digest(saved / "score.json") != score_pin:
        raise ValueError("Immutable four-cell score changed")
    worker = verified(saved / "cell/crossover-worker.json", seal["worker"])
    clock = verified(saved / "clock.json", seal["clock"])
    authority = mixed["raw_identity"]
    if (not pair["verified_pair"] or not pair["chronological"] or pair["generation"] != 1
            or installed["raw_identity"] != authority or seal["admission"] != "sha256:" + admission_pin
            or admission["case"] != case or admission["original_pair"] != pair["attempt_result_sha256"]
            or admission["original_raw"] != authority["raw_authority_sha256"]
            or admission["archive_sha256"] != authority["archive_sha256"]
            or admission["offer_sha256"] != authority["region_sha256"]
            or admission["native_sha256"] != mixed["native_sha256"]
            or charted["evidence"]["detail"]["input_sha256"] != mixed["native_sha256"]
            or worker["receipt"]["region"] != mixed["evidence"]["receipt"]["region"]
            or charted["evidence"]["detail"]["region"] != worker["receipt"]["region"]
            or worker["verified_handoffs"] != 1 or worker["waveform_reads"] != 0 or seal["waveform_reads"] != 0
            or clock["exit_code"] or len(mixed["figures"]) != 8 or mixed["grid_points"] != 179
            or any(value != ACCEPTED for value in (installed["outcome"], mixed["outcome"], worker["receipt"]["decision"]))):
        raise ValueError("Saved mixed crossover or original-file authority changed")
    trial, = charted["ports"]["history_risk"]["lean_attempts"]
    return installed, mixed, charted, trial, worker, clock, saved


def checked_lazy_tools():
    for name, pin in LAZY_TOOLS.items():
        path = HERE.parents[2] / "tools/pipeline_eval/variants" / name
        if digest(path) != pin or digest(CHARTED / "tools/pipeline_eval/variants" / name) != pin:
            raise ValueError(f"Source-relative positive dependency changed at {path}")
    return LAZY_TOOLS


def plan():
    installed, mixed, _, trial, _, _, saved = metadata(CASE)
    if not eligible(trial) or eligible(metadata("DS30-0086")[3]):
        raise ValueError("The frozen development and negative-control routes changed")
    source_paths = (Path(__file__), HERE / "mixed_repair_centre_reset.py",
                    HERE / "field_receiver_solver_cross.py", HERE / "field_installed_packet_saved.py",
                    HERE / "ds30_0049_saved_crossover.py", HERE / "ds30_0049_saved_crossover_score.py",
                    HERE / "mixed-repair-centre-reset-protocol.md")
    input_check = HERE / "measurements/mixed-repair-centre-reset-0220-inputs.json"
    proof = json.loads(input_check.read_bytes())
    if (proof["native_sha256"] != mixed["native_sha256"] or proof["archive_sha256"] != mixed["raw_identity"]["archive_sha256"]
            or proof["source_relative_tools"] != checked_lazy_tools() or not proof["positive_ports"]["solver_setup"]):
        raise ValueError("The recorded local input preflight does not match this trial")
    return dict(case=CASE, native_sha256=mixed["native_sha256"], raw_authority=mixed["raw_identity"],
                frozen_build_sha256=BUILD, sources={p.name: digest(p) for p in source_paths},
                input_preflight_sha256=digest(input_check),
                source_relative_tools=LAZY_TOOLS,
                existing_same_packet_controls=dict(charted=str(CAMPAIGN / "cases" / CASE / "successor/attempt-000001"),
                                                   installed=str(saved)),
                control_pins={case: pins for case, pins in CONTROLS.items()},
                eligibility={CASE: True, "DS30-0086": False}, condition="accepted repair and unqualified signed prior",
                raw_headroom_s=installed["elapsed_s"]/2 - mixed["elapsed_s"],
                timeout_s=TIMEOUT_S, freshness_ns=FRESH_NS, passive_window_s=600,
                deferral_watcher_sha256=WATCHER_SHA256, waveform_reads=0, reviewed_launch_required=True)


def launch_inputs():
    from field_receiver_solver_cross import deny_backing, preflight

    sys.addaudithook(deny_backing)
    sys.path[:0] = [str(CHARTED / "reports/ALGO08/v3"), str(CHARTED)]
    import empty_bootstrap as boot
    import integrated_original_batch as batch

    original = boot.load_runtime
    saved_runtime = []

    def capture():
        value = original()
        saved_runtime.append(value)
        return value

    with patch.object(boot, "load_runtime", capture):
        enrolled, spec, publication, args, handoff, _, paths, resident = preflight(CASE)
    (_, _, sources, _, _), = saved_runtime
    from legacy_first_map_acceleration import checked_artifacts

    book, artifacts, producer_cutoff = batch.load_build(CAMPAIGN / "frozen-build/build.json", BUILD)
    if producer_cutoff >= enrolled.authority["causal_cutoff_utc_ns"]:
        raise ValueError("Expected a strictly causal portable producer")
    portable, fast = (book["native"]["--" + flag] for flag in ("portable-orbit-index", "legacy-first-map-fast"))
    acceleration = checked_artifacts(Path(fast["path"]), fast["sha256"])
    args.archive_sha256 = enrolled.authority["archive_sha256"]
    args.history_risk_route = args.cairo_six_sheets = True
    args.cairo_residual_layout = False
    args.portable_orbit_index = Path(portable["path"])
    args.portable_orbit_index_sha256 = batch.tagged(portable["sha256"])
    args.portable_orbit_producer_sha256 = batch.tagged(book["portable_producer"]["sha256"])[7:]
    before = resident(paths)
    if before["unavailable"] or before["observed_members"] != before["members"] or before["cached_pages"] != before["observed_file_pages"]:
        raise ValueError("Charted saved challenge requires the existing fully resident causal catalogue")
    return enrolled, spec, publication, args, handoff, paths, resident, before, sources, acceleration, artifacts


def worker(root):
    enrolled, spec, publication, args, handoff, paths, resident, before, sources, acceleration, _ = launch_inputs()
    from ds30_0049_saved_crossover import charted
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.short_window import ShortWindowReader

    args.output = root / "cell"

    def deny(*args, **kwargs):
        raise ValueError("Only the original authenticated saved packet may be handed off")

    with (patch.object(FastSegmentSource, "windows", deny), patch.object(ShortWindowReader, "windows", deny),
          binding(enabled=True)):
        receipt, owners, audit = charted(publication, spec, sources, args, handoff, enrolled.authority,
                                         enrolled.inventory, acceleration)
    if handoff.calls != 1 or resident(paths) != before or receipt["region"] != enrolled.mix["evidence"]["receipt"]["region"]:
        raise ValueError("Saved handoff, residency or original region diverged")
    if receipt["decision"] == ACCEPTED and owners != enrolled.chart_m["evidence"]["owner_rows"]:
        raise ValueError("Published ordered ownership moved in the fixed-roster trial")
    save(args.output / "crossover-worker.json", dict(receipt=receipt, ordered_owners=owners, audit=audit,
                                                    verified_handoffs=1, waveform_reads=0))


def assert_gate(event):
    path = Path(event["event"])
    stamp = event["unix_ns"]
    if (path.parent != Path("cases") / event["case"] / "events" or path.is_absolute()
            or int(path.name.split("-", 1)[0]) != stamp
            or verified(CAMPAIGN / path, event["event_sha256"])["state"] != "deferred_storage_busy"
            or not 0 <= time_ns()-stamp <= FRESH_NS):
        raise ValueError("A newly attributable official storage deferral within two seconds is required")


def launch(root, approved_plan, approved_sha256, event):
    from field_receiver_solver_cross import LOCK, attrs

    host = attrs(expected_priority="idle")
    if verified(approved_plan, approved_sha256) != json.loads(json.dumps(plan())):
        raise ValueError("A reviewed current one-case plan is required")
    if not root.is_absolute() or not root.resolve().is_relative_to("/dev/shm"):
        raise ValueError("Expected a fresh owner-private path on tmpfs")
    assert_gate(event)
    with LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_gate(event)
        root.mkdir(mode=0o700)
        scratch = root / "scratch"
        scratch.mkdir()
        command = [sys.executable, "-IB", str(Path(__file__).resolve()), "worker", str(root),
                   str(approved_plan), approved_sha256, "--lease-fd", str(lease.fileno())]
        environment = os.environ | dict(TMPDIR=str(scratch), MPLCONFIGDIR=str(scratch), XDG_CACHE_HOME=str(scratch))
        with (root / "stdout").open("x") as stdout, (root / "stderr").open("x") as stderr:
            usage, start, wall = getrusage(RUSAGE_CHILDREN), time_ns(), perf_counter()
            if start-event["unix_ns"] > FRESH_NS:
                raise ValueError("The official deferral expired before child start")
            with subprocess.Popen(command, env=environment, stdout=stdout, stderr=stderr, start_new_session=True,
                                  pass_fds=(lease.fileno(),)) as child:
                try:
                    status = child.wait(TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                    status = 124
            elapsed, finish, after = perf_counter()-wall, time_ns(), getrusage(RUSAGE_CHILDREN)
        cpu = after.ru_utime + after.ru_stime - usage.ru_utime - usage.ru_stime
        save(root / "clock.json", dict(elapsed_s=elapsed, cpu_s=cpu, exit_code=status, started_ns=start, finished_ns=finish,
                                       official_deferral=event, deferral_age_ns=start-event["unix_ns"]))
    save(root / "prediction-seal.json", dict(plan_sha256=approved_sha256, clock_sha256=digest(root / "clock.json"),
                                             worker_sha256=None if status else digest(root / "cell/crossover-worker.json"),
                                             host=host))
    return status


def watch(root, approved_plan, approved_sha256, watch_output):
    if verified(approved_plan, approved_sha256) != json.loads(json.dumps(plan())) or digest(WATCHER) != WATCHER_SHA256:
        raise ValueError("The frozen trial plan or official event observer changed")
    observer = runpy.run_path(str(WATCHER))
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_add_watch.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32)
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "inotify_init1")
    try:
        if libc.inotify_add_watch(fd, os.fsencode(CAMPAIGN), observer["MOVED_TO"]) < 0:
            raise OSError(ctypes.get_errno(), "inotify_add_watch")
        watch_output.mkdir(mode=0o700)
        started, deadline = time_ns(), perf_counter()+600
        save(watch_output / "start.json", dict(started_ns=started, window_s=600, plan_sha256=approved_sha256))
        while (remaining := deadline-perf_counter()) > 0:
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable or not observer["replaced_export"](os.read(fd, 65536)):
                continue
            event = observer["recent_deferral"](CAMPAIGN, started, time_ns())
            if event is None or time_ns()-event["unix_ns"] > FRESH_NS:
                continue
            save(watch_output / "gate.json", dict(event=event, seen_ns=time_ns()))
            try:
                status = launch(root, approved_plan, approved_sha256, event)
                save(watch_output / "end.json", dict(attempts=1, status=status, finished_ns=time_ns()))
                return status
            except (ValueError, OSError) as error:
                save(watch_output / "end.json", dict(attempts=1, error=str(error), finished_ns=time_ns()))
                return 1
        save(watch_output / "end.json", dict(attempts=0, status="no_fresh_deferral", finished_ns=time_ns()))
        return 1
    finally:
        os.close(fd)


def verify(root):
    release = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
    sys.path[:0] = [str(release / "src"), str(release), str(CHARTED)]
    from ds30_0049_saved_crossover_score import publication

    _, mixed, charted, _, _, _, _ = metadata(CASE)
    seal = json.loads((root / "prediction-seal.json").read_bytes())
    clock = verified(root / "clock.json", seal["clock_sha256"])
    if clock["exit_code"]:
        raise ValueError("Saved challenge did not finish")
    verified(root / "cell/crossover-worker.json", seal["worker_sha256"])
    started = perf_counter(), process_time()
    observed = publication(root / "cell", mixed)
    if observed["owner_rows"] != charted["evidence"]["owner_rows"]:
        raise ValueError("Normal publication verification failed exact owner parity")
    save(root / "verification.json", dict(elapsed_s=perf_counter()-started[0], cpu_s=process_time()-started[1],
                                           terminal=observed["terminal"], receipt=observed["receipt"],
                                           figures=observed["figures"], raw_timing_credit=0))


def check_inputs(output):
    enrolled, spec, _, request, handoff, _, _, archive, _, _, artifacts = launch_inputs()
    from ds30_0049_saved_crossover import charted
    from combined_successor_raw_entry import smoke
    import legacy_first_map_acceleration as acceleration

    if not callable(charted):
        raise ValueError("The saved charted entry did not resolve")
    lazy = checked_lazy_tools()
    fast = [p for p in artifacts if p.name == "artifacts.json"]
    request.legacy_first_map_fast, = fast
    request.legacy_first_map_fast_sha256 = "sha256:" + digest(request.legacy_first_map_fast)
    request.output = output.with_suffix(".unused-publication")
    traced = StringIO()
    with binding(enabled=True), redirect_stdout(traced):
        smoke(request, acceleration)
        if handoff.calls:
            raise ValueError("Input check must precede publication")
    save(output, dict(native_sha256=enrolled.mix["native_sha256"], archive=archive,
                      archive_sha256=request.archive_sha256, charted_build_sha256=BUILD,
                      installed_spec_receiver_sha256=spec["detector_sha256"],
                      exact_local_artifacts=sorted(str(item) for item in artifacts), numerical_calls=0,
                      source_relative_tools=lazy, positive_ports=json.loads(traced.getvalue())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "inputs", "watch", "worker", "verify"))
    parser.add_argument("path", type=Path)
    parser.add_argument("approved_plan", type=Path, nargs="?")
    parser.add_argument("approved_sha256", nargs="?")
    parser.add_argument("--watch-output", type=Path)
    parser.add_argument("--lease-fd", type=int)
    args = parser.parse_args()
    if args.mode == "plan":
        save(args.path, plan())
    elif args.mode == "inputs":
        check_inputs(args.path)
    elif args.mode == "verify":
        verify(args.path)
    elif args.approved_plan is None or args.approved_sha256 is None:
        parser.error("The saved challenge requires a frozen reviewed plan and digest")
    elif args.mode == "watch":
        if args.watch_output is None:
            parser.error("The passive launch requires a fresh watch receipt path")
        return watch(args.path, args.approved_plan, args.approved_sha256, args.watch_output)
    else:
        from field_receiver_solver_cross import LOCK, attrs

        attrs(expected_priority="idle")
        if args.lease_fd is None or not os.path.samestat(os.fstat(args.lease_fd), LOCK.stat()):
            raise ValueError("Worker requires the inherited shared lease")
        if verified(args.approved_plan, args.approved_sha256) != json.loads(json.dumps(plan())):
            raise ValueError("Worker plan or source changed")
        worker(args.path)


if __name__ == "__main__":
    sys.exit(main())
