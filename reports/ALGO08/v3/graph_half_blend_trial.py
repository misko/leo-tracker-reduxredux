"""One saved charted DS30-0049 proposal-only half-blend challenge."""

import argparse
import gzip
import json
import os
import runpy
import sys
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
from time import monotonic, sleep, time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from graph_half_blend import make_ledger, scoped_rank, verify_graph  # noqa: E402

CASE = "DS30-0049"
DONOR = Path("/srv/postgres-nvme/leo-ds30-research-worktrees/ds30-track-cfo-denoise"
             "/reports/ALGO08/v3/measurements")
PLAN = "track-cfo-denoise-development-plan.json.gz"
GRAPH = "track-cfo-denoise-0049-graph.json.gz"
PLAN_PIN = "53b74ecf735c731ddf2df5604715a205403d4c9256fd42b552bc166246d91c04"
GRAPH_PIN = "7f42ba562c06eb85d9c509b4dc03b3e287e0436ef0ce0802a5799cc306ae60bb"
SUPPORT = Path("/srv/postgres-nvme/leo-ds30-research-worktrees/accepted-confidence-observer"
               "/reports/ALGO08/v3")
READY_RUNTIME_PIN = "2bd9669f2b39815f1ef8ca8396723a4ea9720850fb5f4a2ebddb9fa0c55ecc43"
CONTROL = Path("/dev/shm/leo-v3-accepted-confidence-0049-run01/run")
CONTROL_PINS = {
    "observed.json": "c2a732fd27acdcd87cac5c27ab0b843c7cc73809ac2dd9a1e3cdcbe35e7a368d",
    "clock.json": "4714b8feecf6abd6ffa2cc52d2e4eeed9250fc3af2d0bac2ecb1bff9acc78e4f",
    "publication/exact-named-raw-witness.json":
        "5bffce0fb1e18a426f59f7240054909c32c4dc950623d285c98675bdfd57b4f2",
}
PINNED_RUNTIME = {
    "cold_finalist_race": "eeb7d1041f34fb7dbb805cb12eb93f66eba87e729e9cf695ff77811b51842fe7",
    "joint_publication": "3431764b4c6f888c4addb6b788f6e9f1715a76e1500fc047cb875959d0c24e01",
    "blind_joint_route": "f7a66aea7ed875f5de067a0125948cd51c91e329ac0ea4b4ab1b4da6db5d1ca6",
    "v5_core": "30e6f22ab4b49d03cf8536645cbdebb8fec2afa513f3cfa4a9f3163590a84407",
    "algo08_position": "cd5c728e7f81b675b796d69713ca66e601a54534bdbf1d606dc8ecf16c4c138c",
}
TRACKS_PIN = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
QUIET = Path("/tmp/leo-v3-ds30-paired-evaluation/reports/ALGO08/v3/guarded_stage_idle.py")
QUIET_PIN = "a4d2575cb5ec65014f6415ca61adf8423dd1c1ded84d56af06f38cb13b1b5c56"


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path, pin=None):
    body = path.read_bytes()
    if pin is not None and sha256(body).hexdigest()!=pin.removeprefix("sha256:"):
        raise ValueError(f"Changed pinned input {path}")
    return json.loads(gzip.decompress(body) if path.suffix==".gz" else body)


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",",":"), allow_nan=False)
        stream.write("\n")
    path.chmod(0o400)
    return sha(path)


def ready_runtime():
    expected = SUPPORT/"accepted_confidence_trial.py"
    if sha(expected)!=READY_RUNTIME_PIN:
        raise ValueError("The established positive-path runtime adapter differs")
    sys.path.insert(1,str(SUPPORT))
    import accepted_confidence_trial as base

    if Path(base.__file__).resolve()!=expected:
        raise ValueError("The saved positive runtime resolved outside its pinned source")
    return base


def operands(root):
    base = ready_runtime()
    custody, handoff, args, spec, publication, acceleration, fast, inventory = base.runtime(root)
    import blind_joint_route
    import cold_finalist_race
    import empty_bootstrap as boot
    import joint_publication
    from leo.analysis.localization_v3 import position, tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    modules = (cold_finalist_race,joint_publication,blind_joint_route,v5_core,algo08_position)
    hashes = {m.__name__.split(".")[-1]: sha(Path(m.__file__)) for m in modules}
    if hashes!=PINNED_RUNTIME or Path(algo08_position.__file__).resolve()!=boot.PAYLOAD/"tools/algo08_position.py":
        raise ValueError("Expected the pinned normal rank, raw finalist and publication ports")
    config = TrackConfig(**read(boot.RELEASE/"assets/tracks.json",TRACKS_PIN)["config"])
    plan = read(DONOR/PLAN, PLAN_PIN)["cases"][CASE]
    ledger = read(DONOR/GRAPH, GRAPH_PIN)
    if ledger["prediction_sha256"]!=PLAN_PIN or ledger["configuration_sha256"]!=TRACKS_PIN:
        raise ValueError("Expected the original candidate-only Graph registration")
    packet = handoff.native
    session = packet["source"]["session_id"]
    native = {}
    for probe in packet["source"]["probes"]:
        values = probe["candidates"]
        if not values:
            continue
        radio, counter = probe["receiver_id"], probe["valid_start_counter"]
        oid = "sha256:"+sha256(f"{session}:{radio}:{counter}".encode()).hexdigest()
        if oid in native or len(values)!=1 or not values[0]["passed_fractional_margin_gate"]:
            raise ValueError("Materialized candidate must match original strongest signed probes")
        native[oid] = dict(receiver_id=radio, sample_counter=counter, edge=probe["edge"],
                           channel=probe["channel"], actual_rf_hz=probe["actual_rf_hz"],
                           measured_signed_cfo_hz=values[0]["fractional_tracking_cfo_hz"])
    rows, changes = make_ledger(plan,ledger,native,"sha256:"+custody["native"])
    period = config.alias_spacing_hz
    for row in rows.values():
        if (row["graph_lifted_cfo_hz"] !=
            row["measured_signed_cfo_hz"] + row["graph_alias_lift"]*period):
            raise ValueError("The authenticated Graph lift and signed CFO disagree")
    return (custody, handoff, args, spec, publication, acceleration, fast, inventory,
            cold_finalist_race, v5_core, position.NormalPosition, algo08_position, rows,
            changes, native, period, config, tracks)


def registration(custody, rows, changes, native):
    return dict(case=CASE, protocol=sha(HERE/"graph-half-blend-protocol.md"), base=custody,
                runner=sha(Path(__file__)), adapter=sha(HERE/"graph_half_blend.py"),
                plan=PLAN_PIN, graph=GRAPH_PIN, runtime=PINNED_RUNTIME, controls=CONTROL_PINS,
                signed_observations=len(native), graph_rows=len(rows), changes=len(changes))


def preflight(output):
    (custody, handoff, args, _, _, acceleration, _, _, _, _, _, _, rows, changes,
     native, _, config, tracks) = operands(output.parent)
    import exact_named_raw as raw
    from combined_successor_raw_entry import smoke

    observed = read(CONTROL/"observed.json",CONTROL_PINS["observed.json"])
    clock = read(CONTROL/"clock.json",CONTROL_PINS["clock.json"])
    witness = read(CONTROL/"publication/exact-named-raw-witness.json",
                   CONTROL_PINS["publication/exact-named-raw-witness.json"])
    if (observed["input"]!=custody["native"] or observed["handoffs"]!=1 or clock["exit"]
            or witness["ports"]["history_risk"]["lean_attempts"][0]["decision"]!="complete"
            or observed["receipt"]["decision"]!="complete"):
        raise ValueError("The pre-existing accepted ordinary control differs")
    prep = tracks.prepare_tracks(handoff.native, config)
    verify_graph(prep["tracks"],rows)
    raw.request_from_handoff(args, handoff)
    args.output = output.with_suffix(".unused-publication")
    stream = StringIO()
    with redirect_stdout(stream):
        smoke(args, acceleration)
    positive = json.loads(stream.getvalue())
    if handoff.calls or args.output.exists() or not positive["solver_setup"]:
        raise ValueError("Preflight must leave the full position route untouched")
    print(write(output, dict(registration=registration(custody,rows,changes,native),
                             positive=positive, solver_calls=0, waveform_reads=0)))


def direct_pressure(*, continuous):
    if sha(QUIET)!=QUIET_PIN:
        raise ValueError("The original quiet guard changed")
    scope = runpy.run_path(str(QUIET))
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        _,_,device,_,name,*_ = line.split()
        if name in ("/srv/bulk","/srv/postgres-nvme"):
            mounts[name] = Path(f"/sys/dev/block/{device}/stat")
    if mounts.keys()!={"/srv/bulk","/srv/postgres-nvme"}:
        raise ValueError("The enrolled storage devices changed")
    guards = {name:scope["QuietInterval"]() for name in mounts}
    deadline = monotonic()+1.35
    while monotonic()<deadline:
        ready, audit = [], {}
        for name,file in mounts.items():
            state = scope["sample"](file,monotonic)
            guard = guards[name]
            ready.append(guard.observe(state))
            if (guard.since is None or guard.queue_mean is not None and (
                    not 0<=guard.queue_mean<=scope["QUEUE_LIMIT"]
                    or not 0<=guard.current_full<scope["FULL_LIMIT"])):
                raise ValueError(f"Fresh official deferral remains nonquiet on {name}")
            audit[name] = dict(full_avg10=state.full_avg10, in_flight=state.in_flight,
                               weighted_queue=guard.queue_mean, interval_full=guard.current_full)
        if not continuous or all(ready):
            return audit
        sleep(scope["POLL_S"])
    raise ValueError("No immediate continuous quiet interval after the fresh official deferral")


def watch(root, proof, pin):
    base = ready_runtime()
    import second_curve_gate_trial as admission

    if sha(Path(admission.__file__))!=base.PRIOR_WATCH:
        raise ValueError("The existing nonblocking deferral observer changed")
    launch = admission.launch

    def checked_launch(*args):
        write(root/"quiet.json",direct_pressure(continuous=True))
        return launch(*args)

    with (patch.object(admission,"__file__",__file__),
          patch.object(admission,"launch",checked_launch)):
        return admission.watch(CASE,root,proof,pin)


def worker(root, proof, pin, fd):
    expected = read(proof,pin)
    base = ready_runtime()
    import second_curve_gate_trial as admission

    if not os.path.samestat(os.fstat(fd),admission.LOCK.stat()):
        raise ValueError("The lease is not the original shared Gauss descriptor")
    pressure = direct_pressure(continuous=False)
    (custody, handoff, args, spec, publication, _, fast, inventory, cold, v5, normal,
     evidence, rows, changes, native, period, _, _) = operands(root)
    if expected["registration"]!=registration(custody,rows,changes,native):
        raise ValueError("Source, native or resident operands changed after preflight")
    import exact_named_raw as raw
    from combined_successor_raw_entry import solver_ports
    from integrated_original_entry import positive_ports
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from leo.storage.short_window import ShortWindowReader

    def deny(*_a,**_k):
        raise RuntimeError("Saved proposal challenge has no waveform operation")

    audit, ports = {}, {}
    write(root/"stage-start.json", dict(started_ns=time_ns(),pressure=pressure,ready_pin=pin))
    try:
        with (patch.object(FastScanStore,"inventory",inventory),
              patch.object(FastSegmentSource,"windows",deny),
              patch.object(ShortWindowReader,"windows",deny),
              scoped_rank(cold,v5,normal,evidence,rows,native,changes,period,audit),
              positive_ports(solver_ports,fast,ports)):
            receipt, witness = raw.publish_active(args,publication,spec,handoff)
    finally:
        write(root/"proposal-trace.json",audit)
    if (handoff.calls!=1 or audit.get("cold_calls")!=1 or
            audit["evidence_calls"]!=int(receipt["decision"]=="complete")):
        raise ValueError("No complete normal-entry proposal and original-evidence traversal")
    published, = args.output.glob("fast-scan-automatic-work/*/detections.json")
    if sha(published)!=custody["native"]:
        raise ValueError("The ordinary publication rewrote the native measurements")
    print(write(root/"prediction.json",dict(
        case=CASE, receipt=receipt, native_sha256=custody["native"], handoffs=handoff.calls,
        trace_sha256=sha(root/"proposal-trace.json"), ready_sha256=pin,
        witness_sha256=sha(args.output/"exact-named-raw-witness.json"),
        source_sha256=witness["source_sha256"], waveform_reads=0, survey_reads=0,
    )))


if __name__=="__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode",choices=("preflight","watch","worker"))
    cli.add_argument("case",choices=(CASE,))
    cli.add_argument("output",type=Path)
    cli.add_argument("proof",type=Path,nargs="?")
    cli.add_argument("pin",nargs="?")
    cli.add_argument("--lease-fd",type=int)
    args = cli.parse_args()
    if args.mode=="preflight":
        preflight(args.output)
    elif args.mode=="watch":
        sys.exit(watch(args.output,args.proof,args.pin))
    else:
        worker(args.output,args.proof,args.pin,args.lease_fd)
