"""Run the frozen one-fit salvage on two previously staged signed physical packets."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from prospective_0316_solver import ARMS, SOURCE_PINS, inspect, owner_delta, verify_sources, worker
from prospective_small_physical import checked


HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "provisional-salvage-protocol.md"
SOURCE = "fc54ba9792ad726c6322b3ebc15d25d835e934a5"
PINS = SOURCE_PINS | {
    "unified_short_bootstrap.py": "eb17619ddf68f88846290523dfdd2b001aa9fea408b9a601f5555d65904a0bf3",
    "joint_publication.py": "9df6978f279577f972460a6b752511df9bf4c511e74d072ce4ff23ebd39ac5f7",
    "blind_joint_finish.py": "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708",
    "provisional_salvage.py": "69dc94c6645f4b97cb6cadf79d7d0fc57a54138fc30cec176a4b5ab4729517af",
    "blind_joint_route.py": "f7a66aea7ed875f5de067a0125948cd51c91e329ac0ea4b4ab1b4da6db5d1ca6",
    "blind_joint_repair.py": "f89e80dd65606b065e4c8097d0d3204362993e070dc7dd3f2c2590dc2c32b2a0",
    "certified_salvage.py": "7ccb39db8f2f4a278b2c7b1977866e3d731601de7d759adb5541e88692917f09",
    "lighter_joint_estimator.py": "6692c234ab897ec62057b1472ed25b47392345a84d7fa5730190bbfdd27086b8",
}
ENROLLMENT = {
    "DS30-0160": dict(windows=3691, admitted=2354,
                      native_sha="1c56c47f871933cdc1887e41d79d2b28da0624b3104d2e5b05d0957c488bd4b5",
                      request_sha="c3b6e328f03f79e9d0b0989fabb3ab246394a03c98dd2ca7c2ca4f3a608e3d2e",
                      cumulative_sha="050b3983b0ac83d25ec5eb964d4df97d083c5bdec7810eb27fe7008737126bc5"),
    "DS30-0316": dict(windows=3042, admitted=2702,
                      native_sha="6bbbb2575df6a203dd0d183a3ad8390110fbac778504803e275b7493b8422bed",
                      request_sha="e1e3d9cd482bc4b8837f782c329702472b60e34eba8616616b5ec20ef759b739",
                      cumulative_sha="39be27ab7fee47b6db239207e23bcf7a53d99e1ea65fe269dd607ef0c3958b1a"),
}
AUDIT_NAME = "provisional-salvage-worker.json"


def pin_paths(case):
    return Path(f"/dev/shm/leo-v3-saved-{case[-4:]}-pair-01")


def settings(case):
    return {name: ENROLLMENT[case][name] for name in ("windows", "admitted", "native_sha")} | {"audit_name": AUDIT_NAME}


def saved_request(case):
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    start = pin_paths(case)
    job = json.loads(checked(start / "request.json", ENROLLMENT[case]["request_sha"]))
    inventory = start / "stock/fast-scan-inputs" / f"{job['session']}.json"
    archive = Path(job["local_archive"]["root"])
    local = [inventory, archive, Path(job["native_file"]), Path(job["offer_file"]),
             *(Path(path) for path in job["local_libraries"].values())]
    if (any(not path.resolve(strict=True).is_relative_to(start) for path in local)
            or archive_identity(archive)["snapshots_sha256"] != job["original_archive"]["snapshots_sha256"]):
        raise ValueError("Use only the case's already staged pinned causal inputs")
    job["manifests"] = [[name if Path(name).name == "manifest.json" else str(Path(name) / "manifest.json"), pin]
                        for name, pin in job["manifests"]]
    return job, inventory


def candidate_worker(case, request, inventory, output, *, runtime=None):
    import unified_short_bootstrap as active

    publish = active.publish_active

    def opted_in(*args, **kwargs):
        import blind_joint_finish
        from provisional_salvage import refine

        paid = False

        def one_refit(*args, **kwargs):
            nonlocal paid
            audit = args[-1]
            if paid:
                audit.update(status="untouched", reason="single_refit_budget_already_used", fit_calls=0)
                return None
            result = refine(*args, **kwargs)
            paid = bool(audit["fit_calls"])
            return result

        with patch.object(blind_joint_finish, "propose", partial(blind_joint_finish.propose, rescue=one_refit)):
            return publish(*args, **kwargs)

    with patch.object(active, "publish_active", opted_in):
        worker(request, "cumulative", output, source_pins=PINS, inventory_file=inventory,
               **(settings(case) if runtime is None else runtime))


def run(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    verify_sources(checked, PINS)
    root.mkdir()
    (root / "tmp").mkdir()
    jobs = {case: saved_request(case) for case in ENROLLMENT}
    commands = {}
    for case, (request, inventory) in jobs.items():
        job = root / f"{case}-request.json"
        write(job, request)
        env = environment(pin_paths(case))
        env["TMPDIR"] = str(root / "tmp")
        commands[case] = ([RELEASE / "venv/bin/python", "-IB", __file__, "worker", case, job, inventory, root / case], env)
    for case, (command, env) in commands.items():
        clock = measure(command, env, root / case)
        write(root / f"{case}-clock.json", dict(timing=clock, command=list(map(str, command))))
    write(root / "run.json", dict(machine=machine, enrollment=ENROLLMENT, source_sha256=PINS, base=SOURCE,
                                 protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),
                                 driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


def historical(case):
    source = pin_paths(case)
    if case == "DS30-0160":
        old = json.loads(checked(Path("/dev/shm/leo-v3-saved-0160-audit.json"),
                                 "80c0658736c7e94ecdbbc56839171ccb10a0fa74880266f29c6dca8a61229038"))
        fixed = json.loads(checked(Path("/dev/shm/leo-v3-saved-0160-confirm-01/result.json"), ENROLLMENT[case]["cumulative_sha"]))
        return old["runs"]["stock"], fixed["candidate"]
    old = json.loads(checked(source / "result.json", ENROLLMENT[case]["cumulative_sha"]))
    return old["runs"]["stock"], old["runs"]["cumulative"]


def evaluate(root, output):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    reference = json.loads(checked(REFERENCE, REFERENCE_SHA256))
    observations = {}
    for case in ENROLLMENT:
        clock = read(root / f"{case}-clock.json")["timing"]
        if clock["exit_code"]:
            observations[case] = dict(process=clock)
            continue
        work = root / case
        candidate = inspect(work, "cumulative", read(work / AUDIT_NAME)["receipt"], clock,
                            read(root / f"{case}-request.json"), **settings(case))
        audited = read(work / "joint-research-receipt.json")
        route = audited["route_details"] or {}
        stock, cumulative = historical(case)
        ref, = (row["reference"] for row in reference["cases"] if row["dataset_label"] == case
                and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
        truth = [ref[key] for key in ("latitude_deg", "longitude_deg")]
        comparative = {}
        for name, result in (("named", stock), ("cumulative", cumulative), ("provisional", candidate)):
            comparative[name] = dict(horizontal_error_km={arm: distance_km(truth, value["latlon"]) if value["latlon"] else None
                                                          for arm, value in result["terminal"]["arms"].items()},
                                     rf_rms_hz={arm: value.get("rf_rms_hz") for arm, value in result["terminal"]["arms"].items()},
                                     solve_cpu_s=result["worker"]["solve"]["cpu_s"], process=result["process"],
                                     terminal=result["terminal"], owner_digests=result["science"]["owners"])
        owners = {arm: owner_delta(cumulative["selected_rows"][arm], candidate["selected_rows"].get(arm, [])) for arm in ARMS}
        if not route.get("provisional_salvage", {}).get("fit_calls") == 1:
            raise ValueError(f"Predeclared case did not reach the frozen trigger: {case}")
        observations[case] = dict(worker=candidate, research=audited, comparative=comparative, owners_vs_cumulative=owners)
    write(output, dict(run=read(root / "run.json"), no_waveform=True, reference_sha256=REFERENCE_SHA256, cases=observations))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    launch = commands.add_parser("run")
    launch.add_argument("root", type=Path)
    audit = commands.add_parser("evaluate")
    audit.add_argument("root", type=Path)
    audit.add_argument("output", type=Path)
    child = commands.add_parser("worker")
    child.add_argument("case", choices=ENROLLMENT)
    for name in ("request", "inventory", "output"):
        child.add_argument(name, type=Path)
    args = cli.parse_args()
    if args.command == "run":
        run(args.root)
    elif args.command == "evaluate":
        evaluate(args.root, args.output)
    else:
        candidate_worker(args.case, args.request, args.inventory, args.output)
