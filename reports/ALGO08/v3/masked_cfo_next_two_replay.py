"""Run the frozen 0218 saved replay on the two enrolled next-rank cases."""

import argparse
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import masked_cfo_0218_capsule as capsule  # noqa: E402
from masked_cfo_0218_capsule import held, saved, scoring, signed  # noqa: E402


CASES = ("DS30-0442", "DS30-0212")
PLAN_PIN = "5213dc72a3df2240b5a169ebcdbba9aee72c9d2959490c158d52004d295f00d7"
REFUSAL_PIN = "e5ba85a1056589cde2f34e54fa022654c0349803028a4e180e7272da7e8d4b87"
OBSERVER_PIN = "f6e912af1ed5e3fa4f82427569a195ca4b69110c839456cd0ca398363ea4b1c3"
RELEASE_SRC = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src")
DONORS = tuple(Path("/dev/shm")/name for name in ("leo-v3-0218-prospective01/stage", "leo-v3-cfo-epoch-0086-saved01"))
WORKER = Path(__file__).resolve()
BASE_STATUS = held.status
BASE_EXPERIMENT = held.experiment
BASE_FINISH = capsule.finish
BASE_COMMAND = capsule.command
BASE_MAKE_CELL = held.make_cell


def cases():
    bind = saved.document(HERE/"measurements/held-cfo-next-two.json", PLAN_PIN)
    rows = bind["cases"]
    if (bind["plan_sha256"] != "sha256:"+held.PLAN
            or [(row["case"], row["execution_rank"]) for row in rows] != list(zip(CASES, (66, 67), strict=True))):
        raise ValueError("The next two original execution ranks changed")
    return {row["case"]:row for row in rows}


def enrolled(campaign, row):
    plan = saved.document(campaign/"plan.json", held.PLAN)
    entries = {entry["case"]:entry for entry in plan["cases"]}
    order = [*plan["smoke"], *(case for case in entries if case not in plan["smoke"])]
    case = row["case"]
    if order[row["execution_rank"]-1] != case or any(entries[case][field] != row[field] for field in (
            "assigned_rank", "case_id", "raw_identity_sha256", "manifest_raw_authority_sha256", "window_count")):
        raise ValueError("The original accession or execution order changed")
    # The 0218 stage verifies the authenticated request; the accession is also
    # bound independently in the cohort plan, including on reopened 0442.
    return dict(entries[case], manifest_raw_authority_sha256=row["catalogue_custody"]["historical_request_raw_authority_sha256"])


def status(row, campaign=held.CAMPAIGN):
    with patch.multiple(held, CASE=row["case"], IDENTITY=row["raw_identity_sha256"],
                        enrollment=lambda root: enrolled(root,row)):
        return dict(BASE_STATUS(campaign), execution_rank=row["execution_rank"])


def field_authority(row, state, campaign=held.CAMPAIGN):
    if not state["verified_pair"]:
        raise ValueError("The official pair has not verified both acquisition rows")
    base = campaign/"cases"/row["case"]
    custody = row["catalogue_custody"]
    pair = saved.document(base/"pair.json", state["pair_sha256"])
    authority = saved.document(base/"authority.json", custody["authority_sha256"])
    request = saved.document(base/"input.json", custody["request_sha256"])
    if (pair["authority_sha256"] != custody["authority_sha256"] or request["authority"] != authority
            or request["authority_sha256"] != pair["authority_sha256"]
            or authority["raw_authority_sha256"] != custody["historical_request_raw_authority_sha256"]
            or authority["archive_sha256"] != custody["signed_archive_sha256"]
            or authority["causal_cutoff_utc_ns"] != custody["signed_cutoff_ns"]):
        raise ValueError("The actual field attempt does not bind the frozen request, roster and cutoff")
    return authority


def refusal(row, state):
    receipt = saved.document(HERE/"measurements/0442-cache-custody.json", REFUSAL_PIN)
    if (receipt["case"] != row["case"] or receipt["execution_rank"] != row["execution_rank"]
            or receipt["decision"] != "deferred_first_reference_not_resident"
            or "sha256:"+receipt["field_receipts"]["pair_sha256"] != state["pair_sha256"]
            or receipt["catalogue"]["archive_sha256"] != row["catalogue_custody"]["signed_archive_sha256"]
            or receipt["first_reference"]["privileged_passive_resident_bytes"] != 0
            or receipt["nowait_payload_attempts"] or receipt["body_payload_bytes_read"]
            or receipt["stage_created"] or receipt["solver_children"] or receipt["survey_opened"]):
        raise ValueError("The preregistered cache-only custody refusal is not established")
    return dict(decision="custody_refused", field_pair=state["pair_sha256"], refusal_sha256=REFUSAL_PIN,
                accession_raw_sha256=row["manifest_raw_authority_sha256"],
                requested_raw_sha256=row["catalogue_custody"]["historical_request_raw_authority_sha256"])


def experiment(*, probe):
    if probe:
        return BASE_EXPERIMENT(probe=True)
    item = BASE_EXPERIMENT(probe=False)
    item.stem = "held-cfo-next-two"
    item.source = WORKER.name
    item.transfer_sources += ("masked_cfo_0218.py", "masked_cfo_0218_capsule.py", "masked_cfo_0218_owner_residuals.py")
    return item


def command(*args, proof_only=False, **kwargs):
    argv = BASE_COMMAND(*args, proof_only=proof_only, **kwargs)
    index = argv.index("--") + 1
    resource = args[0]/("preflight-resource.txt" if proof_only else "worker-resource.txt")
    argv[index:index] = ["/usr/bin/time", "-q", "-f", "%U %S %M %I %O", "-o", str(resource)]
    return argv


class VerifiedBeforeSurvey(RuntimeError):
    """The unchanged verifier reached the held-survey join boundary."""


def finish(root, mode, pin, field_pair, ordinary):
    if mode == "ordinary":
        return BASE_FINISH(root, mode, pin, field_pair, ordinary)

    def stop(_case):
        raise VerifiedBeforeSurvey

    with patch.object(scoring, "geography", stop):
        try:
            BASE_FINISH(root, mode, pin, field_pair, ordinary)
        except VerifiedBeforeSurvey:
            closure = saved.identifier(root/"verification-pins.json")
        else:
            raise ValueError("The matched scientific verifier did not reach the held survey boundary")
    return saved.write(root/"pair-verified-before-survey.json", dict(field_pair=field_pair, closure_sha256=closure,
        resources={mode:saved.identifier(root/mode/"worker-resource.txt") for mode in capsule.CELLS}))


@contextmanager
def ports(row):
    def make_cell(*args, original=None, **kwargs):
        original = dict(original, panel_sha256=PLAN_PIN, execution_rank=row["execution_rank"],
            accession_raw_sha256=row["manifest_raw_authority_sha256"],
            requested_raw_sha256=row["catalogue_custody"]["historical_request_raw_authority_sha256"])
        return BASE_MAKE_CELL(*args, original=original, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.multiple(held, CASE=row["case"], IDENTITY=row["raw_identity_sha256"],
            status=lambda: status(row), enrollment=lambda campaign: enrolled(campaign,row), DONORS=DONORS,
            make_cell=make_cell, experiment=experiment))
        stack.enter_context(patch.multiple(scoring, CASE=row["case"], status=lambda: status(row)))
        stack.enter_context(patch.multiple(capsule, WORKER=WORKER, command=command, finish=finish))
        yield


def prepare(root, row):
    if row["case"] == CASES[0]:
        raise ValueError("0442 has a sealed cache-only custody refusal and cannot stage")
    state = status(row)
    authority = field_authority(row, state)
    filenames = row["catalogue_custody"]["exact_archive_names"]
    files = held.private_files(DONORS)
    if len(filenames) != 50 or not set(filenames) <= files.keys():
        raise ValueError("The complete 50-name recipient roster is not staged in the enrolled donor roots")
    files = {name:files[name] for name in filenames}
    held.causal_view(files, authority["causal_cutoff_utc_ns"], authority["archive_sha256"], set(filenames))
    sys.path.append(str(RELEASE_SRC))
    with ports(row), patch.object(held, "private_files", lambda _: files):
        plans = held.prepare_field(root)
        readiness = {mode:capsule.preflight(root/mode,pin,mode,OBSERVER_PIN) for mode,pin in plans.items()}
    return saved.write(root/"panel-readiness.json", dict(case=row["case"], field_pair=state["pair_sha256"],
        enrollment_sha256=PLAN_PIN, plans=plans, readiness=readiness, bodies=len(files)))


def score(panel, rows, closure_pin):
    refused = rows[CASES[0]]
    state = status(refused)
    field_authority(refused, state)
    refused_cell = refusal(refused, state)
    row = rows[CASES[1]]
    root = panel/row["case"]
    closure = saved.document(root/"pair-verified-before-survey.json", closure_pin)
    state = status(row)
    field_authority(row, state)
    if closure["field_pair"] != state["pair_sha256"]:
        raise ValueError("The paired replay no longer matches the original verified case")
    pins = saved.document(root/"verification-pins.json", closure["closure_sha256"])
    with ports(row):
        scoring.verify(root,pins)
    return saved.write(panel/"panel-score.json", {CASES[0]:refused_cell, row["case"]:dict(
        decision="scored", replay_closure_sha256=closure["closure_sha256"],
        verified_before_survey_sha256=closure_pin, score_sha256=saved.identifier(root/"score.json"))})


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("operation", choices=("status", "probe", "prepare", "watch", "score", "child"))
    cli.add_argument("root", type=Path, nargs="?")
    cli.add_argument("--case", choices=CASES)
    cli.add_argument("--cell", choices=(*capsule.CELLS, "probe"))
    cli.add_argument("--pin")
    cli.add_argument("--ordinary-gate-pin")
    cli.add_argument("--driver-pid", type=int)
    cli.add_argument("--probe-only", action="store_true")
    args = cli.parse_args()
    rows = cases()
    if args.operation == "status":
        states = {case:status(row) for case,row in rows.items()}
        print(json.dumps(dict(states, refusal=refusal(rows[CASES[0]],states[CASES[0]])), sort_keys=True))
        return 0
    if args.root is None or args.root.resolve() != args.root or not args.root.is_relative_to("/dev/shm"):
        cli.error("Use a direct private tmpfs root")
    if args.operation == "child" and args.pin and args.cell:
        plan = saved.document(args.root/"plan.json", args.pin)
        if plan["case"] == "DS30-0019" and plan["probe"] and args.cell == "probe" and args.probe_only:
            capsule.child(args.root,args.pin,args.cell,probe_only=True)
        else:
            if plan["case"] == CASES[0]:
                raise ValueError("The admitted panel has a sealed 0442 custody refusal")
            with ports(rows[plan["case"]]):
                capsule.child(args.root,args.pin,args.cell,probe_only=args.probe_only)
        return 0
    sys.addaudithook(saved.deny_backing)
    if args.operation == "probe":
        args.root.mkdir(mode=0o700)
        root = args.root/"probe"
        with patch.multiple(capsule, WORKER=WORKER, command=command):
            print(capsule.preflight(root,held.prepare_probe(root),"probe",OBSERVER_PIN))
        return 0
    if args.operation == "score" and args.pin:
        print(score(args.root,rows,args.pin))
        return 0
    if args.case is None:
        cli.error("Require an enrolled case")
    row = rows[args.case]
    root = args.root/args.case
    if args.operation == "prepare":
        field_authority(row,status(row))
        if args.case == CASES[0]:
            print(json.dumps(refusal(row,status(row))))
            return 3
        args.root.mkdir(mode=0o700,exist_ok=True)
        print(prepare(root,row))
        return 0
    if args.operation == "watch" and args.cell in capsule.CELLS and args.pin and args.driver_pid:
        if args.case == CASES[0]:
            raise ValueError("The 0442 custody refusal bars a numerical launch")
        with ports(row):
            result = capsule.watch(root,args.cell,args.driver_pid,args.pin,args.ordinary_gate_pin)
        if isinstance(result,int):
            return result
        print(result)
        return 0
    cli.error("Require the signed readiness, role and official driver for an authorized watch")


if __name__ == "__main__":
    sys.exit(main())
