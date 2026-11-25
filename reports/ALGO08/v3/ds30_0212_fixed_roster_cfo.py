"""Replay the authentic ordinary final fit and change only its signed CFO inputs."""

import argparse
from contextlib import contextmanager
from copy import copy
from importlib.util import module_from_spec, spec_from_file_location
import json
from math import asin, cos, radians, sin, sqrt
import os
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import masked_cfo_next_two_replay as replay  # noqa: E402
from masked_cfo_next_two_replay import capsule, saved  # noqa: E402


CASE = "DS30-0212"
ROOT = Path("/dev/shm/leo-v3-mask-cfo-next-two01/DS30-0212")
CLOSURE = "b7baaa38ae42e3014a8d91a6f777a4652d005c85bd03e08b905b272bec068ccf"
READBACK = "67762a27e92251bf01d9fe7a4e6e0c616f55e3cef7bc7970f02de85dd5c926db"
WORKER = Path(__file__).resolve()
PROTOCOL = HERE/"ds30-0212-fixed-roster-cfo-protocol.md"
FIXED = HERE.parents[3]/"fixed-residual-0218-scorer/reports/ALGO08/v3/masked_cfo_0218_fixed_residuals.py"
FIXED_SHA = "a9d100ea129cb2aa9b1e065d79a45709d1bd61150c9bf41364cb99cba846846a"
NAMED_SHA = "32b4f05449f6e4e0316d66b214a0564dfe4c14acfa413664e89333f40d8c1c2e"
LIMIT = 21
ARMS = ("c0", "fitted_c")


class Captured(BaseException):
    """The bound ordinary and CFO-only final fits are complete before publication."""


class DiagnosticFailure(BaseException):
    """A failed private control must bypass the live route's scientific fallback."""


def edit_basis():
    if saved.identifier(FIXED) != FIXED_SHA or 2 in os.sched_getaffinity(0):
        raise ValueError("Use the frozen residual readback outside the benchmark core")
    spec = spec_from_file_location("fixed_roster_edit_readback", FIXED)
    source = module_from_spec(spec)
    spec.loader.exec_module(source)
    pins = saved.document(ROOT/"verification-pins.json", CLOSURE)
    expected = saved.document(ROOT/"fixed-residual-readout.json", READBACK)
    with patch.object(source, "CASE", CASE):
        before, after = (source.read_cell(ROOT/mode, mode, pins[mode]) for mode in capsule.CELLS)
    native = before["native"]
    if native != after["native"] or before["terminal"]["region"] != after["terminal"]["region"]:
        raise ValueError("The sealed comparison changed native input or the original offer")
    edits = source.rederive(native, source.original_winners(native), after["scope"])
    if edits["digest"] != expected["edit_readback"]["digest"] or edits["changed"] != 153:
        raise ValueError("The exact 153 signed CFO changes failed to reproduce")
    path = ROOT/"ordinary/substituted/exact-named-raw-witness.json"
    witness = saved.document(path, before["run"]["witness"])
    risk = witness["ports"]["history_risk"]
    if (risk["choice"]["route"] != "lean" or risk["inference_calls"] != 1
            or risk["lean_attempts"][0]["named_survivor_fit"]["status"] != "accepted"
            or witness["source_sha256"]["reports/ALGO08/v3/named_survivor_fit.py"] != NAMED_SHA):
        raise ValueError("The published ordinary fit was not the enrolled signed numerical port")
    return dict(closure_sha256=CLOSURE, edits=edits["edits"], edit_sha256=edits["digest"],
        before_terminal=before["terminal"], corrected_terminal=after["terminal"],
        witness=risk["lean_final_fit"], owners=witness["evidence"]["owner_rows"],
        native_sha256=before["plan"]["original_native_sha256"], protocol_sha256=saved.identifier(PROTOCOL),
        original_plan_sha256=pins["ordinary"]["plan"], scorer_sha256=FIXED_SHA)


def altered_scan(scan, edits, period):
    shifted = copy(scan)
    tracks, changed, by_track = [], set(), {}
    for track in scan.tracks:
        values = np.asarray(track["values"])
        result = values.copy()
        ids = track["observation_ids"]
        if values.dtype != np.float64 or values.shape != (len(ids),):
            raise ValueError("Expected a complete frozen CFO row map")
        for i, oid in enumerate(ids):
            edit = edits.get(oid)
            if edit is None:
                continue
            old, new = edit["original_hz"], edit["updated_hz"]
            winding = round((float(values[i])-old)/period)
            if oid in changed or abs(float(values[i])-(old+winding*period)) > 1e-8:
                raise ValueError("An edited observation lost its unique ID or original Graph alias winding")
            result[i] = values[i] + (new-old)
            changed.add(oid)
        updated = dict(track, values=result)
        tracks.append(updated)
        by_track[id(track)] = updated
    shifted.tracks = tracks
    shifted.groups = [(name,[by_track[id(track)] for track in group]) for name,group in scan.groups]
    return shifted, changed


def owners(record):
    rows = {}
    for arm, witness in record["arms"].items():
        support = [(oid, item["norad"], role) for field,role in (("curves","conditional"),("predictive","predictive"))
                   for item in witness[field].values() for oid in item["ids"]]
        joined = {oid:(norad,role) for oid,norad,role in support}
        if len(joined) != len(support):
            raise ValueError("The enrolled final likelihood owns the same observation twice")
        rows[arm] = joined
    return rows


def meters(a, b):
    x, y, z, q = map(radians, (*a,*b))
    angular = sin((z-x)/2)**2 + cos(x)*cos(z)*sin((q-y)/2)**2
    return 2 * 6371008.8 * asin(min(1., sqrt(angular)))


def refit(original, candidate, means, basis, *, publish_control=None):
    from leo.analysis.localization_v3.history_policy import pair_passes
    from leo.analysis.research.retained_track_likelihood import PERIOD
    from leo.application.localization_v3_engine import _json_value

    def plain(value):
        return json.loads(json.dumps(value, default=_json_value, allow_nan=False))

    control_clock, control_witness = {}, {}
    control = original(candidate, means, control_clock, control_witness)
    if (plain(control_witness) != basis["witness"] or not pair_passes(control, include_linear=True,
            half_width_km=candidate["scan"].search_region.half_width_km)):
        raise ValueError("Ordinary reassociated likelihood or complete selected endpoint did not reproduce exactly")
    expected = {arm:{oid:(norad,role) for oid,norad,role in rows} for arm,rows in basis["owners"].items()}
    if owners(control_witness) != expected or any(
            plain(control[arm]["endpoint_latlon"]) != basis["before_terminal"]["arms"][arm]["latlon"] for arm in ARMS):
        raise ValueError("The ordinary live named fit did not equal the published owners and endpoint")
    if publish_control is not None:
        publish_control(dict(exact_witness=True, exact_endpoint=True, paired_gate=True,
                             owners={arm:len(rows) for arm,rows in expected.items()}, timing=control_clock))
    scan, changed = altered_scan(candidate["scan"], basis["edits"], PERIOD)
    if any(not (set(rows) & basis["edits"].keys()) <= changed for rows in expected.values()):
        raise ValueError("A published edited owner failed to receive the frozen CFO change")
    fitted_clock, fitted_witness = {}, {}
    fitted = original(dict(candidate,scan=scan), means, fitted_clock, fitted_witness)
    if owners(fitted_witness) != expected:
        raise ValueError("The perturbed refit changed its frozen likelihood support")
    return plain(dict(control=control_witness, fitted=fitted_witness, control_clock=control_clock,
        fitted_clock=fitted_clock, fit_gate=bool(pair_passes(fitted, include_linear=True,
            half_width_km=scan.search_region.half_width_km)), edited_winners=len(basis["edits"]),
        mapped_track_edits=len(changed), edited_active_owners={arm:len(changed & rows.keys()) for arm,rows in expected.items()},
        displacement={arm:dict(from_ordinary_m=meters(control[arm]["endpoint_latlon"],fitted[arm]["endpoint_latlon"]),
            from_rebuilt_corrected_m=meters(basis["corrected_terminal"]["arms"][arm]["latlon"],fitted[arm]["endpoint_latlon"]))
            for arm in ARMS}))


@contextmanager
def ports():
    row = replay.cases()[CASE]

    def command(*args, **kwargs):
        argv = replay.command(*args, **kwargs)
        i = argv.index("--remount-ro")
        path = str(args[0]/"basis.json")
        return [*argv[:i], "--ro-bind", path, path, *argv[i:]]

    with replay.ports(row), patch.multiple(capsule, WORKER=WORKER, TIMEOUT=LIMIT, command=command, finish=finish):
        yield


def prepare(root):
    if root.parent != Path("/dev/shm") or root.resolve() != root or root.exists():
        raise ValueError("Use a fresh direct staging root")
    basis = edit_basis()
    original = saved.document(ROOT/"ordinary/plan.json", basis["original_plan_sha256"])
    stage, cell = root/"stage", root/"ordinary"
    root.mkdir(mode=0o700)
    cell.mkdir(mode=0o700)
    for name in ("derived-native.json", "admission.json"):
        os.link(ROOT/"ordinary"/name, cell/name)
    source = Path(original["stage"])
    (stage/"tle/archive/space-track").mkdir(parents=True)
    for name in (*capsule.STAGE_FILES, *("tle/archive/space-track/"+name for name in saved.document(source/"catalogue.json"))):
        os.link(source/name,stage/name)
    basis_pin = saved.write(cell/"basis.json",basis)
    pin = saved.write(cell/"plan.json", dict(original,stage=str(stage),diagnostic_basis_sha256=basis_pin))
    with ports():
        ready = capsule.preflight(cell,pin,"ordinary",replay.OBSERVER_PIN)
    return saved.write(root/"diagnostic-ready.json",dict(basis=basis_pin,plan=pin,capsule_ready=ready,
        protocol_sha256=saved.identifier(PROTOCOL),source_sha256=saved.identifier(WORKER),max_child_s=LIMIT))


def child(cell, pin, *, probe_only):
    if probe_only:
        with ports():
            return capsule.child(cell,pin,"ordinary",probe_only=True)
    plan = saved.document(cell/"plan.json",pin)
    proof = capsule.isolation(cell,Path(plan["stage"]),probe=False)
    sys.addaudithook(saved.deny_backing)
    saved.attrs(expected_priority="idle")
    basis = saved.document(cell/"basis.json",plan["diagnostic_basis_sha256"])
    if basis["closure_sha256"] != CLOSURE or basis["native_sha256"] != plan["original_native_sha256"]:
        raise ValueError("The fit diagnostic does not bind the frozen 0212 comparison")
    result = {}

    @contextmanager
    def observe(_native):
        import named_survivor_fit as named

        if saved.identifier(Path(named.__file__)) != NAMED_SHA:
            raise ValueError("The ordinary named fit port differs from the selected released route")
        original = named.fit_pair

        def capture(candidate, means, _audit, _witness):
            try:
                result.update(refit(original,candidate,means,basis,
                    publish_control=lambda record:saved.write(cell/"control-parity.json",record)))
            except Exception as error:
                saved.write(cell/"diagnostic-failure.json",dict(error=type(error).__name__, reason=str(error),
                            control_verified=(cell/"control-parity.json").exists()))
                raise DiagnosticFailure(str(error)) from error
            raise Captured

        with patch.object(named,"fit_pair",capture):
            yield

    try:
        saved.worker(cell,pin,replay.experiment(probe=False), lease_fd=0, original_control=True,
            enrollment=(CASE,Path(plan["stage"]),plan["admission_sha256"],plan["references"]),
            admission_path=cell/"admission.json", observation_scope=observe)
    except Captured:
        if not result or list((cell/"substituted").rglob("terminal.json")):
            raise ValueError("The scoped worker crossed the frozen fit boundary")
    else:
        raise ValueError("The enrolled ordinary final fit port was bypassed")
    return saved.write(cell/"fixed-roster-refit.json",dict(case=CASE,plan=pin,basis=plan["diagnostic_basis_sha256"],
        proof=proof,numerical=result, publication_calls=0,waveform_reads=0,survey_reads=0))


def finish(root, mode, pin, field_pair, _old):
    cell = root/mode
    result = cell/"fixed-roster-refit.json"
    clock = saved.document(cell/"clock.json")
    observed = saved.document(result)
    if clock["exit_code"] or observed["plan"] != pin or observed["publication_calls"]:
        raise ValueError("The scoped diagnostic did not close successfully")
    return saved.write(root/"fixed-roster-seal.json",dict(field_pair=field_pair,result=saved.identifier(result),
        clock=saved.identifier(cell/"clock.json"),resources=saved.identifier(cell/"worker-resource.txt"),
        control=saved.identifier(cell/"control-parity.json")))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode",choices=("prepare","watch","child"))
    cli.add_argument("root",type=Path)
    cli.add_argument("--pin")
    cli.add_argument("--driver-pid",type=int)
    cli.add_argument("--cell",choices=("ordinary",))
    cli.add_argument("--probe-only",action="store_true")
    args = cli.parse_args()
    if args.mode == "child" and args.pin and args.cell:
        result = child(args.root,args.pin,probe_only=args.probe_only)
    else:
        sys.addaudithook(saved.deny_backing)
        if args.mode == "prepare":
            result = prepare(args.root)
        elif args.mode == "watch" and args.pin and args.driver_pid:
            ready = saved.document(args.root/"diagnostic-ready.json",args.pin)
            if ready["source_sha256"] != saved.identifier(WORKER) or ready["protocol_sha256"] != saved.identifier(PROTOCOL):
                raise ValueError("The frozen fixed-roster diagnostic changed")
            with ports():
                result = capsule.watch(args.root,"ordinary",args.driver_pid,ready["capsule_ready"],None)
        else:
            cli.error("Require the sealed diagnostic and live driver for the single authorized slot")
    if isinstance(result,int):
        return result
    if result is not None:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
