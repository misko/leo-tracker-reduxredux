"""Prepare and verify the sealed DS30-0019 masked-CFO position sensitivity."""

import argparse
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
from time import time_ns
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

from graph_half_blend_trial import direct_pressure, ready_runtime  # noqa: E402
from joint_recovery_0049_direct import check_quiet, require_driver_idle  # noqa: E402
from joint_recovery_0049_wait import lease, run_child  # noqa: E402
from matched_donor_0049 import bind_derived  # noqa: E402
import matched_donor_0049_trial as trial  # noqa: E402
import signed_cfo_time_readout as signed  # noqa: E402
from sparse8_cfo_epoch_saved import AUTHORITY, CASE, NATIVE  # noqa: E402


ROOT = Path("/dev/shm/leo-v3-held-shrink-0019-02")
STAGE = Path("/dev/shm/leo-v3-cfo-epoch-0019-saved01")
FORECAST = "3e8881c463ff66d0f936e4ac4cfbe9f2589f5543a6e4a776081cffa2473ae99d"
SOURCE = "2ac33ded7301abb66c49661a4eb9e24c7fdc9582731d0bc66df383c1a9e1d279"
PREVIOUS = "ac8d1e2a7d35415e4d0e7c1541f888c5f136d2aa2976c48eaacdd1bdfe2ab1bf"
SCORE = "f921e11bf0314c18f757e688f305200f28d3ec3ffb2da2df0ed0b70ef7253b0d"
CATALOGUE = "956132c3f8110787e3683c525b72f084a2172c508b1efb14c011eae259a591eb"
PAIR = "5a5307be75290e5bed14cb42380e47cd9679030a327fdcce2fa1fd2f3c910719"
HERTZ = "fractional_tracking_cfo_hz"
EXPERIMENT = SimpleNamespace(
    stem="held-shrink-0019", source=Path(__file__).name, joint=True,
    ledger="edits", ledger_digest="edit_sha256", priority="idle",
    transfer_sources=("held_short_cfo_shrink.py", "odd_short_interpolation.py"),
)


def splice(native, eligible, *, schema="private-0019-held-cfo-shrink-v1"):
    original = signed.opportunities(native)
    if not eligible or not eligible.keys() <= original.keys():
        raise ValueError("The sealed CFO updates must use existing observations")
    probes, edits = [], []
    for oid, lane in original.items():
        row = lane["row"]
        if oid in eligible:
            factor = lane["factor"]
            expected = eligible[oid]
            if (not lane["short"] or factor is None or row["candidates"] != [factor]
                    or factor[HERTZ] != expected["original_hz"]):
                raise ValueError("A CFO replacement must belong to an original selected short factor")
            row = dict(row, candidates=[dict(factor, **{HERTZ: expected["updated_hz"]})])
            edits.append(dict(observation_id=oid, visit=row["visit_index"], counter=lane["counter"],
                              radio=lane["radio"], **expected))
        probes.append(row)
    recipe = dict(schema=schema, scope="saved CFO-only sensitivity",
                  sparse_native_sha256=signed.canonical(native), edit_sha256=signed.canonical(edits),
                  forecast_sha256=FORECAST, frozen_predictor_sha256=SOURCE,
                  retained_arrival=True, retained_native_support=True, ordinary_graph_rebuilt_on_execution=True)
    derived, audit = bind_derived(native, probes, recipe)
    observed = signed.opportunities(derived)
    signed.bind_pair(native, derived, original, observed)
    for oid, before in original.items():
        after = observed[oid]
        if oid in eligible:
            if {k:v for k,v in before["factor"].items() if k != HERTZ} != {
                k:v for k,v in after["factor"].items() if k != HERTZ
            }:
                raise ValueError("The handoff changed another observation field")
        elif after != before:
            raise ValueError("The handoff changed a non-enrolled observation")
    return derived, dict(audit, edits=edits, changed_by_radio=dict(Counter(str(row["radio"]) for row in edits)),
                         lanes=len(original), original_winners=sum(lane["factor"] is not None for lane in original.values()))


def resident():
    authority = trial.document(STAGE / "authority.json", AUTHORITY)
    records = trial.document(STAGE / "catalogue.json", CATALOGUE)
    archive = STAGE / "tle/archive/space-track"
    paths = [(archive/name).resolve(strict=True) for name in records]
    if len(paths) != 47 or any(not path.is_relative_to(archive) for path in paths):
        raise ValueError("Expected the exact 47 local causal snapshot paths")
    build = trial.document(trial.BUILD, trial.BUILD_PIN)
    index = Path(build["native"]["--portable-orbit-index"]["path"]).resolve(strict=True)
    operands = [STAGE/"authority.json", STAGE/"inventory.json", STAGE/"offer.json", STAGE/"native.json", index, *paths]
    if ROOT.exists():
        operands.append(ROOT/"derived-native.json")
    if any(not p.is_relative_to("/dev/shm") for p in operands):
        raise ValueError("No backing operand is enrolled")
    trial.require_resident(operands)
    return dict(resident_files=len(operands), causal_bodies=len(paths), archive=authority["archive_sha256"])


def comparator():
    seal = trial.document(STAGE/"prediction-seal.json", PREVIOUS)
    archive = trial.document(STAGE/"score.json", SCORE)
    ordinary = trial.document(STAGE/"ordinary-recovered.json", seal["products"]["ordinary"]["receipt_sha256"])
    clock = trial.document(STAGE/"ordinary-clock.json", seal["products"]["ordinary"]["clock_sha256"])
    if archive["seal_sha256"] != PREVIOUS or not all(archive["archived_reproduction"].values()):
        raise ValueError("Ordinary scientific publication must reproduce the original signed worker")
    return ordinary, clock, archive


def prepare():
    from reports.ALGO08.v3 import held_short_cfo_shrink as frozen

    sys.addaudithook(trial.deny_backing)
    if ROOT.exists() or signed.tag(Path(frozen.__file__).read_bytes()) != "sha256:"+SOURCE:
        raise ValueError("Expected new output and exact predictor source")
    authority = trial.document(STAGE/"authority.json", AUTHORITY)
    trial.document(STAGE/"offer.json", authority["region_sha256"])
    trial.document(STAGE/"inventory.json", authority["inventory_sha256"])
    native = trial.document(STAGE/"native.json", NATIVE)
    pair = trial.document(trial.CAMPAIGN/"cases"/CASE/"pair.json", PAIR)
    forecast = signed.document(HERE/"measurements/held-short-cfo-shrink-prediction.json.gz", FORECAST)
    held_case = forecast["cases"][CASE]
    masked, held, modes = frozen.odd.mask(native)
    if (held_case["native_sha256"] != "sha256:"+NATIVE
            or held_case["original_pair"] != signed.canonical(pair)
            or held_case["masked_sha256"] != signed.canonical(masked)
            or held_case["held_order_sha256"] != signed.canonical(list(held))
            or held_case["native_calls"] != modes):
        raise ValueError("Saved scan differs from the pre-masked held enrollment")
    eligible, gates = frozen.nominate_changes(held, signed.opportunities(native), held_case["forecasts"])
    if (eligible != held_case["eligible"] or gates != held_case["residual_gates"] or len(eligible) != 366
            or any(edit["original_hz"] == edit["updated_hz"] for edit in eligible.values())):
        raise ValueError("Frozen forecast and source do not reproduce all 366 exact changes")
    derived, change = splice(native, eligible)
    changed = {row["observation_id"]: row for row in change["edits"]}
    final = signed.opportunities(derived)
    if any(frozen.arrival_phase(final[k]["counter"], final[k]["factor"]) != row["arrival"]
           for k, row in changed.items()):
        raise ValueError("Derived packet changed frozen absolute arrival")
    cache = resident()
    ROOT.mkdir(mode=0o700)
    payload = ROOT/"derived-native.json"
    payload.write_bytes(json.dumps(derived, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                   separators=(",", ":")).encode())
    payload.chmod(0o400)
    trial.document(payload, change["derived_native_sha256"])
    admission_pin = trial.write(ROOT/"admission.json", dict(case=CASE, authority_pin=AUTHORITY, native_pin=NATIVE))
    print(trial.write(ROOT/"plan.json", dict(case=CASE, protocol=trial.protocol(EXPERIMENT),
        worker=trial.identifier(Path(trial.__file__)), sources=trial.source_pins(EXPERIMENT),
        original_native_sha256="sha256:"+NATIVE, original_archive=authority["archive_sha256"],
        installed_native_sha256=None, change=change, admission_sha256=admission_pin, cache=cache)))


def run_worker(pin, *, smoke=False, fd=None):
    plan = trial.document(ROOT/"plan.json", pin)
    trial.worker(ROOT, pin, EXPERIMENT, smoke=smoke, lease_fd=fd,
                 enrollment=(CASE, STAGE, plan["admission_sha256"], 47), admission_path=ROOT/"admission.json")


def preflight(pin):
    plan = trial.document(ROOT/"plan.json", pin)
    stream = StringIO()
    with redirect_stdout(stream):
        run_worker(pin, smoke=True)
    smoke = json.loads(stream.getvalue())
    if smoke != dict(case=CASE, changed=366, refs=47, acquired=0, waveform_reads=0, solver_runs=0):
        raise ValueError("Expected a positive-path no-solve smoke")
    _, clock, _ = comparator()
    print(trial.write(ROOT/"ready.json", dict(case=CASE, plan_sha256=pin, input=plan["change"]["derived_native_sha256"],
        smoke=smoke, cache=resident(), original_science_seal=PREVIOUS,
        archived_ordinary_clock={k:clock[k] for k in ("elapsed_s", "cpu_s", "exit_code")})))


def watch(pid, pin, ready_pin):
    machine = trial.attrs(expected_priority="idle")
    ready = trial.document(ROOT/"ready.json", ready_pin)
    if ready["plan_sha256"] != pin or ready["smoke"]["solver_runs"]:
        raise ValueError("Require the sealed no-solve transfer preflight")
    binding = dict(driver=Path(__file__).resolve(), plan_pin=pin,
                   protocol=trial.protocol(EXPERIMENT), budget=24, flags=[])
    runtime = ready_runtime()
    import second_curve_gate_trial as admission

    if trial.identifier(Path(admission.__file__)) != runtime.PRIOR_WATCH:
        raise ValueError("Ordinary field deferral guard changed")

    def admit(case, root, proof, proof_pin, event):
        if case != CASE or root != ROOT/"admission-watch" or proof != ROOT/"ready.json" or proof_pin != ready_pin:
            raise ValueError("Unexpected frozen watch scope")
        admission.event_admits(event)
        require_driver_idle(pid)
        quiet = check_quiet()
        with lease() as fd:
            admission.event_admits(event)
            require_driver_idle(pid)
            cache = resident()
            on_lease = direct_pressure(continuous=False)
            require_driver_idle(pid)
            admission.event_admits(event)
            return run_child(ROOT, fd, dict(event=event, quiet=quiet, quiet_after_lease=on_lease, cache=cache,
                                          driver_pid=pid, admitted_unix_ns=time_ns()),
                             machine, binding=binding)["exit_code"]

    with (patch.object(admission, "WINDOW_S", 180), patch.object(admission, "launch", admit)):
        return admission.watch(CASE, ROOT/"admission-watch", ROOT/"ready.json", ready_pin)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "preflight", "check-control", "watch", "worker", "score"))
    parser.add_argument("root", type=Path, nargs="?", default=ROOT)
    parser.add_argument("--pin")
    parser.add_argument("--ready")
    parser.add_argument("--driver-pid", type=int)
    parser.add_argument("--lease-fd", type=int)
    args = parser.parse_args()
    if args.root != ROOT:
        parser.error("Require the one frozen output")
    if args.action == "prepare":
        prepare()
    elif args.action == "preflight":
        preflight(args.pin)
    elif args.action == "check-control":
        from held_shrink_0019_score import check_control
        check_control()
    elif args.action == "watch":
        sys.exit(watch(args.driver_pid, args.pin, args.ready))
    elif args.action == "worker":
        trial.attrs(expected_priority="idle")
        run_worker(args.pin, fd=args.lease_fd)
    else:
        from held_shrink_0019_score import score
        score(args.pin)
