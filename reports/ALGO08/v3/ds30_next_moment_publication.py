"""Prepare the prospectively enrolled fast moment correction with the ordinary saved entry."""

import argparse
from contextlib import contextmanager
from dataclasses import replace
import os
from pathlib import Path
from shutil import copyfile
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

WORKER = Path(__file__).resolve()
sys.path.insert(0, str(WORKER.parent))

import ds30_next_moment_custody as custody  # noqa: E402
import ds30_0280_moment_position_transfer as transfer  # noqa: E402
import moment_preserving_fast_graph as fast  # noqa: E402
from ds30_0280_moment_position_transfer import capsule, held, moment, replay, saved, scoring, signed  # noqa: E402


COMPARISON = "measurements/moment-fast-graph-full-comparison.json"
COMPARISON_PIN = "b757315415ae137956362453b1329fde5047e5d1337861480e69dc433b662f84"


def elapsed(start):
    return dict(wall_ns=perf_counter_ns()-start[0], cpu_ns=process_time_ns()-start[1])


def started():
    return perf_counter_ns(), process_time_ns()


def experiment(*, probe):
    spec = moment.experiment(probe=probe)
    spec.stem = custody.STEM
    spec.source = WORKER.name
    spec.transfer_sources += (Path(custody.__file__).name, moment.WORKER.name, transfer.WORKER.name,
        "held_cfo_next_two.py", "moment_preserving_fast_graph.py", fast.PORT,
        "vector_graph_edges.py", "polynomial_fit_cache.py", COMPARISON)
    return spec


def registration():
    if (saved.protocol(experiment(probe=False)) != custody.PROTOCOL
            or saved.identifier(WORKER.parent/COMPARISON) != COMPARISON_PIN
            or saved.identifier(moment.PROJECTION) != moment.PROJECTION_PIN
            or saved.identifier(moment.RULE) != moment.RULE_PIN):
        raise ValueError("The prospective protocol or exact released formation sources changed")


def formed_features(native, config, feature, ordinary_graph, report):
    project = moment.projector(feature)
    start = started()
    proposals = feature.derive(native, config)
    masked_clock = elapsed(start)
    start = started()
    ordinary = ordinary_graph(native, config)
    graph_clock = elapsed(start)
    start = started()
    revised, proof = project(ordinary, proposals.edits)
    projection_clock = elapsed(start)
    if (set(revised) != set(proposals.edits) or proof["moments_valid"] is not True
            or proof["projected_cfo_sha256"] != signed.canonical(revised)):
        raise ValueError("The frozen projection changed support or lost its moment certificate")
    report.update(projection_source_sha256=moment.PROJECTION_PIN, projection=proof,
        source_half_blend_sha256=signed.canonical(proposals.edits),
        ordinary_graph=dict(tracks=len(ordinary["tracks"]), assigned=ordinary["graph_points"]),
        clocks=dict(held_odd_proposals=masked_clock, ordinary_graph=graph_clock, projection=projection_clock))
    return replace(proposals, edits={oid:dict(edit, updated_hz=revised[oid]) for oid,edit in proposals.edits.items()})


@contextmanager
def ports(run, row):
    with replay.ports(row), patch.object(held, "experiment", experiment), patch.multiple(
            capsule, WORKER=WORKER, ram_path=transfer.output_path,
            command=lambda *args, **kwargs:transfer.command(run, *args, **kwargs)):
        yield


@contextmanager
def correction(mode):
    if mode == "ordinary":
        yield
    else:
        with patch.object(moment, "formed_features", formed_features), fast.enabled(moment), transfer.optional_projection(mode):
            yield


def enrolled(ledger, pin):
    seal = saved.document(ledger, pin)
    selected, state = custody.selection_for(seal["ranks"])
    if (state != "enrolled" or selected != seal["selected"] or seal["state"] != state
            or seal["protocol_sha256"] != custody.PROTOCOL or seal["source_plan_sha256"] != "sha256:"+held.PLAN
            or seal["selector_sha256"] != "sha256:"+saved.identifier(Path(custody.__file__))
            or [row["execution_rank"] for row in seal["ranks"]] != list(custody.RANKS)):
        raise ValueError("Require one frozen eligible recording from the exact four-case custody review")
    return next(row for row in seal["ranks"] if row["case"] == selected)


def prepare(run, ledger, ledger_pin):
    registration()
    row = enrolled(ledger, ledger_pin)
    state = replay.status(row)
    if not state["verified_pair"]:
        raise ValueError("The enrolled recording is waiting for its verified official pair")
    if run.exists() or run.parent != Path("/tmp") or run.resolve() != run:
        raise ValueError("Require fresh direct /tmp tmpfs output")
    start = started()
    sys.path.insert(0, str(replay.RELEASE_SRC))
    authority = replay.field_authority(row, state)
    source = held.CAMPAIGN/"cases"/row["case"]
    pair = saved.document(source/"pair.json", state["pair_sha256"])
    request = saved.document(source/"input.json", row["catalogue_custody"]["request_sha256"])
    offer = held.authenticated_offer(held.CAMPAIGN, authority, request)
    result_path = source/"successor"/f"attempt-{pair['generation']:06d}"/"result.json"
    result = saved.document(result_path, pair["attempt_result_sha256"]["successor"])
    if result["raw_identity"] != authority or result["process"]["exit_code"]:
        raise ValueError("The enrolled official successor has no exit-zero authenticated handoff")
    publication = result_path.parent/"publication"
    native, = (publication/"fast-scan-automatic-work").glob("*/detections.json")
    inventory = publication/"fast-scan-inputs"/(authority["session_id"]+".json")
    roster = row["resident_roster"]
    view = {name:item["sha256"] for name,item in roster.items()}
    if (signed.canonical(view) != authority["archive_sha256"] or
            any(name != Path(item["path"]).name or not any(Path(item["path"]).parent == stage/custody.STAGE_PART
                for stage in custody.STAGES) for name,item in roster.items())):
        raise ValueError("The sealed roster and source locations must bind the exact recorded request")
    donors, _ = custody.documented_donors()
    if any(Path(item["path"]) not in donors.get(name, ()) for name,item in roster.items()):
        raise ValueError("A sealed donor path has changed or left private tmpfs")
    start_preload = started()
    saved.require_resident([native, inventory, *(Path(item["path"]) for item in roster.values())])
    first_preload = elapsed(start_preload)
    packet = saved.document(native, result["native_sha256"])
    held.checked_schedule(publication, packet)
    saved.document(inventory, authority["inventory_sha256"])
    witness = publication/"exact-named-raw-witness.json"
    witness_pin = saved.identifier(witness) if witness.is_file() else None
    original = dict(execution_rank=row["execution_rank"], enrollment_sha256=ledger_pin,
        raw_attempt_sha256=pair["attempt_result_sha256"]["successor"],
        verified_field_pair_sha256=state["pair_sha256"].removeprefix("sha256:"),
        raw_outcome=result["outcome"], original_witness=witness_pin)
    root, stage = run/"field", run/"field/stage"
    size = sum(item["bytes"] for item in roster.values())
    fs = os.statvfs("/tmp")
    if fs.f_bavail*fs.f_frsize < size+128*1024**2 or fs.f_favail < 512:
        raise ValueError("Insufficient private tmpfs space for the matched outputs")
    run.mkdir(mode=0o700)
    transfer.mount_root(run).mkdir(mode=0o700)
    pool = stage/custody.STAGE_PART
    pool.mkdir(parents=True)
    for name,item in roster.items():
        out = pool/name
        copyfile(item["path"], out)
        out.chmod(0o400)
        if out.stat().st_size != item["bytes"] or saved.identifier(out) != item["sha256"]:
            raise ValueError("A resident donor copy differs from the signed historical body")
    (stage/"offer.json").write_bytes(offer)
    copyfile(inventory, stage/"inventory.json")
    copyfile(source/"authority.json", stage/"authority.json")
    saved.write(stage/"catalogue.json", view)
    provenance = dict(row=row, original=original, initial_residency=first_preload,
        archive_copy_bytes=size, shared_stage_clock=elapsed(start), waveform_reads=0, backing_archive_reads=0)
    plans, readiness, preload = {}, {}, {}
    with ports(run, row):
        for mode in capsule.CELLS:
            cell = root/mode
            start = started()
            plans[mode] = replay.BASE_MAKE_CELL(cell, stage, row["case"], native, result["native_sha256"],
                authority, len(view), enabled=mode=="corrected", probe=False, original=original)
            readiness[mode] = capsule.preflight(cell, plans[mode], mode, replay.OBSERVER_PIN)
            preload[mode] = elapsed(start)
    return saved.write(run/"next-moment-ready.json", dict(provenance, plans=plans, readiness=readiness,
        preflight_by_role=preload))


def isolated_child(cell, pin, mode, *, probe_only):
    plan = saved.document(cell/"plan.json", pin)
    row = dict(case=plan["case"], raw_identity_sha256=None)
    archive = Path(plan["stage"])/"tle"
    if probe_only:
        view = saved.document(archive.parent/"catalogue.json")
        pool = archive/"archive/space-track"
        device = archive.stat().st_dev
        if (set(view) != {path.name for path in pool.iterdir()} or any(
                (pool/name).stat().st_dev != device or (pool/name).resolve() != pool/name for name in view)):
            raise ValueError("The isolated real archive root and bodies must share the declared tmpfs device")
    with ports(cell.parents[1], row), correction(mode):
        capsule.child(cell, pin, mode, probe_only=probe_only)


def watch(run, ready, mode, driver, gate):
    checks = []
    original = saved.require_resident

    def residency(paths):
        start = started()
        try:
            original(paths)
        finally:
            checks.append(dict(elapsed(start), files=len(paths)))

    root = run/"field"
    result = None
    try:
        with ports(run, ready["row"]), patch.object(saved, "require_resident", residency):
            result = capsule.watch(root, mode, driver, ready["readiness"][mode], gate)
    finally:
        saved.write(root/mode/f"preload-{perf_counter_ns()}.json", dict(checks=checks, disposition=result))
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("prepare", "watch", "child", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--pin", required=True)
    cli.add_argument("--ready-pin")
    cli.add_argument("--enrollment", type=Path)
    cli.add_argument("--cell", choices=capsule.CELLS)
    cli.add_argument("--driver-pid", type=int)
    cli.add_argument("--ordinary-gate-pin")
    cli.add_argument("--probe-only", action="store_true")
    args = cli.parse_args()
    if not args.root.is_relative_to("/tmp") or args.root.resolve() != args.root:
        cli.error("Require the private direct tmpfs root")
    registration()
    if args.mode == "child" and args.cell:
        isolated_child(args.root, args.pin, args.cell, probe_only=args.probe_only)
        return 0
    sys.addaudithook(saved.deny_backing)
    if args.mode == "prepare" and args.enrollment:
        out = prepare(args.root, args.enrollment, args.pin)
    elif args.mode == "watch" and args.cell and args.driver_pid:
        ready = saved.document(args.root/"next-moment-ready.json", args.pin)
        out = watch(args.root, ready, args.cell, args.driver_pid, args.ordinary_gate_pin)
    elif args.mode == "score" and args.ready_pin:
        ready = saved.document(args.root/"next-moment-ready.json", args.ready_pin)
        root = args.root/"field"
        closed = saved.document(root/"pair-verified-before-survey.json", args.pin)
        if closed["field_pair"].removeprefix("sha256:") != ready["original"]["verified_field_pair_sha256"]:
            raise ValueError("The two sealed publications differ from the prepared field pair")
        with ports(args.root, ready["row"]):
            return scoring.verify(root, saved.document(root/"verification-pins.json", closed["closure_sha256"]))
    else:
        cli.error("Provide the selected enrollment, ready role or paired closure")
    if isinstance(out, int):
        return out
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
