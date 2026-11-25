"""Run the optional rank-68 paired saved position transfer after its frozen RF screen."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
from shutil import copyfile
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ds30_0212_moment_preserving_publication as moment  # noqa: E402
from ds30_0212_moment_preserving_publication import capsule, graph_overlay, held, replay, saved, scoring, signed  # noqa: E402


CASE = "DS30-0280"
CUSTODY_PIN = "3788c68a00b5f9ee28fee85fc498f06380ff9d1468db2a64995896cad425b48d"
PROTOCOL = HERE/"ds30-0280-moment-position-transfer-protocol.md"
PROTOCOL_PIN = "aa22673cb9993f1dfec58f60c5ea77239a972cdf6335d0de5c71dc3ea8566d2a"
WORKER = Path(__file__).resolve()
BASE_PATH = capsule.ram_path


def custody():
    row = saved.document(HERE/"measurements/ds30-0280-moment-position-custody.json",CUSTODY_PIN)
    if saved.identifier(PROTOCOL) != PROTOCOL_PIN or row["case"] != CASE or row["rank"] != 68:
        raise ValueError("The prospective position enrollment changed")
    return row


def enrollment():
    row = custody()
    # Public status binds these exact metadata fields against the campaign
    # plan. In the isolated child no campaign file needs to be visible.
    return dict(case=CASE,case_id="fast8-auto-20261117-221747-9614b618-1-upper-18696a63115d",
        window_count=6774,assigned_rank=row["assigned_rank"],execution_rank=68,
        raw_identity_sha256=row["physical_identity_sha256"],manifest_raw_authority_sha256=row["accession_raw_sha256"],
        catalogue_custody=dict(authority_sha256=row["authority_sha256"],
        request_sha256=row["request_sha256"],historical_request_raw_authority_sha256=row["requested_raw_sha256"],
        signed_archive_sha256=row["archive_sha256"],signed_cutoff_ns=row["cutoff_utc_ns"]))


def rf_admission(report, candidate, candidate_pin, pair_pin):
    if (report["case"] != CASE or report["execution_rank"] != 68 or report["candidate"] != candidate
            or report["development_sha256"] != moment.DEVELOPMENT or report["candidate_seal_sha256"] != candidate_pin
            or candidate["case"] != CASE or candidate["rank"] != 68
            or candidate["pair_sha256"].removeprefix("sha256:") != pair_pin.removeprefix("sha256:")
            or candidate["rule_sha256"] != moment.PROJECTION_PIN
            or candidate["enrollment_sha256"].removeprefix("sha256:") != held.PLAN
            or any(report[k] for k in ("waveform_reads","archive_reads","survey_reads","receiver_runs","solver_runs"))):
        raise ValueError("The independently sealed RF diagnostic does not bind this exact original pair and rule")
    prior, new = report["previous_half_blend"], report["moment_preserving"]
    if any(prior[key] != new[key] for key in ("eligible","scored","installed_empty","original")):
        raise ValueError("The RF comparison changed its original measured opportunities")
    strict = new["windows"]["250Hz_2samples"]
    if (not candidate["projected"]["moments_valid"] or candidate["projected"]["surviving_edits"] <= 0
            or strict["joint_after"] < strict["joint_before"]):
        raise ValueError("The frozen RF or nonzero-edit admission declined the position transfer")
    return dict(strict_original=strict["joint_before"],strict_projected=strict["joint_after"],
                eligible=new["eligible"],scored=new["scored"],installed_empty=new["installed_empty"])


def mount_root(run):
    return Path("/dev/shm")/("."+run.name+"-native-mount")


def command(run, *args, **kwargs):
    argv = replay.command(*args, **kwargs)
    destination = argv.index("/dev/shm")
    if argv[destination-2:destination] != ["--bind",str(args[0]/"capsule-shm-root")]:
        raise ValueError("The capsule's native tmpfs mount port changed")
    # Writable publication goes to /tmp; pinned installed native operands
    # still see the true /dev/shm device in this isolated mount namespace.
    argv[destination-1] = str(mount_root(run))
    return argv


def output_path(path, *, cell=False):
    checked = BASE_PATH(path)
    if cell and (not path.is_relative_to("/tmp") or path.resolve() != path):
        raise ValueError("Both position cells need the same direct separate /tmp tmpfs")
    return checked


def experiment(*, probe):
    obj = moment.experiment(probe=probe)
    obj.stem = "ds30-0280-moment-position-transfer"
    obj.source = WORKER.name
    obj.transfer_sources += (moment.WORKER.name, "measurements/ds30-0280-moment-position-custody.json")
    return obj


def prediction_book(candidate):
    book = moment.development()
    proof = candidate["projected"]
    case = dict(proof,binding=dict(ordinary_native_sha256=candidate["mixed_native_sha256"],
        edits_sha256=candidate["prior_edits_sha256"]),graph=candidate["graph"])
    return dict(book,cases={CASE:case})


@contextmanager
def ports(run, row, candidate):
    book = prediction_book(candidate)

    def make_cell(*args, original=None, **kwargs):
        original = dict(original,execution_rank=68,custody_sha256=CUSTODY_PIN,
            accession_raw_sha256=row["manifest_raw_authority_sha256"],
            requested_raw_sha256=row["catalogue_custody"]["historical_request_raw_authority_sha256"])
        initial = replay.BASE_MAKE_CELL(*args,original=original,**kwargs)
        root = args[0]
        plan = saved.document(root/"plan.json",initial)
        # The public handoff uses the same sealed native packet; its plan now
        # also identifies the independent candidate-only RF support receipt.
        plan.update(moment_candidate=candidate)
        return saved.write(root/"rank68-plan.json",plan)

    with replay.ports(row), patch.multiple(held, experiment=experiment,make_cell=make_cell), patch.multiple(
            moment, CASE=CASE, development=lambda:book), patch.multiple(capsule,WORKER=WORKER,
            TIMEOUT=moment.LIMIT,ram_path=output_path,command=lambda *a,**k:command(run,*a,**k)):
        yield


def stage_bodies(run, authority):
    ledger = custody()
    sources = {name:Path(meta["source"]) for name,meta in ledger["roster"].items()}
    if sum(meta["bytes"] for meta in ledger["roster"].values()) != 83_978_791 or len(sources) != 47:
        raise ValueError("The exact signed 47-body copy ceiling changed")
    saved.require_resident([BASE_PATH(source) for source in sources.values()])
    out = run/"resident-copy"
    out.mkdir(mode=0o700)
    for name,src in sources.items():
        expected = ledger["roster"][name]
        if src.stat().st_size != expected["bytes"] or saved.identifier(src) != expected["sha256"]:
            raise ValueError("An already resident source differs from its signed identity")
        target = out/name
        copyfile(src,target)
        target.chmod(0o400)
    bodies = {name:out/name for name in sources}
    held.causal_view(bodies,authority["causal_cutoff_utc_ns"],authority["archive_sha256"],set(bodies))
    return bodies


def prepare(run, report_path, report_pin, candidate_path, candidate_pin):
    if run.parent != Path("/tmp") or run.resolve() != run or run.exists():
        raise ValueError("Use a fresh direct /tmp tmpfs directory")
    row = enrollment()
    state = replay.status(row)
    authority = replay.field_authority(row,state)
    report = saved.document(report_path,report_pin)
    candidate = saved.document(candidate_path,candidate_pin)
    gate = rf_admission(report,candidate,candidate_pin,state["pair_sha256"])
    space = os.statvfs("/tmp")
    if space.f_favail < 512 or space.f_bavail*space.f_frsize < 160*1024**2:
        raise ValueError("The alternate tmpfs lacks space or inodes for the two observed publication shapes")
    sys.path.append(str(replay.RELEASE_SRC))
    run.mkdir(mode=0o700)
    mount_root(run).mkdir(mode=0o700)
    bodies = stage_bodies(run,authority)
    root = run/"field"
    with ports(run,row,candidate), patch.object(held,"private_files",lambda _:bodies):
        prepared = held.prepare_field(root)
        plans = {}
        for mode,pin in prepared.items():
            cell = root/mode
            saved.document(cell/"rank68-plan.json",pin)
            (cell/"rank68-plan.json").replace(cell/"plan.json")
            plans[mode] = pin
            saved.document(cell/"derived-native.json",candidate["mixed_native_sha256"])
        readiness = {mode:capsule.preflight(root/mode,pin,mode,replay.OBSERVER_PIN) for mode,pin in plans.items()}
    return saved.write(run/"rank68-readiness.json",dict(state=state["pair_sha256"],custody=CUSTODY_PIN,
        rf_report=report_pin,candidate_seal=candidate_pin,rf_counts=gate,plans=plans,readiness=readiness,
        output_filesystem="separate /tmp tmpfs",resident_archive_copy_bytes=83_978_791,
        bytes_free=space.f_bavail*space.f_frsize,inodes_free=space.f_favail))


@contextmanager
def optional_projection(mode):
    original = graph_overlay.attach
    if mode == "ordinary":
        yield
    else:
        with patch.object(graph_overlay,"attach",lambda native,audit,probe=False:
                moment.attach_projected(original,native,audit,probe=probe)):
            yield


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode",choices=("status","prepare","watch","child","score"))
    cli.add_argument("root",type=Path,nargs="?")
    cli.add_argument("--pin")
    cli.add_argument("--cell",choices=capsule.CELLS)
    cli.add_argument("--driver-pid",type=int)
    cli.add_argument("--ordinary-gate-pin")
    cli.add_argument("--probe-only",action="store_true")
    cli.add_argument("--rf-report",type=Path)
    cli.add_argument("--candidate",type=Path)
    cli.add_argument("--candidate-pin")
    args = cli.parse_args()
    row = enrollment()
    if args.mode == "status":
        print(json.dumps(replay.status(row)))
        return 0
    if args.root is None or not args.root.is_relative_to("/tmp") or args.root.resolve() != args.root:
        cli.error("Require the private alternate tmpfs root")
    if args.mode == "child" and args.pin and args.cell:
        plan = saved.document(args.root/"plan.json",args.pin)
        with ports(args.root.parents[1],row,plan["moment_candidate"]), optional_projection(args.cell):
            capsule.child(args.root,args.pin,args.cell,probe_only=args.probe_only)
        return 0
    sys.addaudithook(saved.deny_backing)
    root = args.root/"field"
    if args.mode == "prepare" and args.pin and args.rf_report and args.candidate and args.candidate_pin:
        out = prepare(args.root,args.rf_report,args.pin,args.candidate,args.candidate_pin)
    elif args.mode == "watch" and args.pin and args.cell and args.driver_pid:
        ready = saved.document(args.root/"rank68-readiness.json",args.pin)
        plan = saved.document(root/args.cell/"plan.json",ready["plans"][args.cell])
        with ports(args.root,row,plan["moment_candidate"]):
            out = capsule.watch(root,args.cell,args.driver_pid,ready["readiness"][args.cell],args.ordinary_gate_pin)
    elif args.mode == "score" and args.pin:
        closed = saved.document(root/"pair-verified-before-survey.json",args.pin)
        pins = saved.document(root/"verification-pins.json",closed["closure_sha256"])
        plan = saved.document(root/"corrected/plan.json",pins["corrected"]["plan"])
        with ports(args.root,row,plan["moment_candidate"]):
            return scoring.verify(root,pins)
    else:
        cli.error("Require the sealed RF inputs, role readiness, or scientific closure for the chosen mode")
    if isinstance(out,int):
        return out
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
