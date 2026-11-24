"""Compare the guarded ordinary cold route before and after the scout refusal fix."""

import argparse
from contextlib import contextmanager, nullcontext
from hashlib import sha256
from inspect import getsource, isfunction
import json
import os
from pathlib import Path
from statistics import median
import sys
from traceback import format_exc
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
STAGE = Path("/dev/shm/leo-v3-combined-successor-original-02/DS30-0016")
SEAL = "7bf45376aa6a05f1e46d541d8f04a6f6decb337b699141b7698743ac4ada6dce"
RESULT = "e9ddbc9e5dd5d95baa387925c713bfda595463cafade2ecea265a7f829fd8903"
NATIVE = "sha256:aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac"
ORDERS = (("ordinary", "fixed"), ("fixed", "ordinary"))
RANK_LINE = '    return [node for _, node in sorted(ranked, key=lambda entry: entry[0])]'


class ColdComplete(BaseException):
    """Terminate the saved launch at the original combined cold boundary."""


def checked(path, pin):
    from empty_bootstrap import checked as release_checked
    from exact_named_raw import staged_path

    return json.loads(release_checked(staged_path(path), pin.removeprefix("sha256:")))


def write(path, value):
    from leo.application.localization_v3_engine import _json_value

    with path.open("x") as out:
        json.dump(value, out, default=_json_value, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")


def forbid_raw(event, args):
    if event != "open" or not isinstance(args[0], (str, bytes)):
        return
    path = Path(os.path.abspath(os.fsdecode(args[0])))
    if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01") or path.name.endswith(".ci16.zst"):
        raise ValueError("The cold-stage diagnostic cannot read backing storage or waveform contents")


def find_rank(operation, filename):
    cell = None
    while operation.__name__ != "ranked_initial_nodes" or Path(operation.__code__.co_filename) != filename:
        candidates = [port for name, port in zip(operation.__code__.co_freevars, operation.__closure__ or (), strict=True)
                      if name in ("original", "rank") and isfunction(port.cell_contents)]
        if len(candidates) != 1:
            raise ValueError(f"Unsupported exact rank wrapper: {operation.__qualname__}")
        cell = candidates[0]
        operation = cell.cell_contents
    return cell, operation


@contextmanager
def rank_readout(operation, record):
    from empty_bootstrap import PAYLOAD
    from proof_global_rank import RANK_PIN

    filename = PAYLOAD/"tools/pipeline_eval/variants/v5_core.py"
    cell, original = find_rank(operation, filename)
    source = getsource(original)
    if sha256(filename.read_bytes()).hexdigest() != RANK_PIN or source.count(RANK_LINE) != 1:
        raise ValueError("Expected the installed stable cold-rank score and sort")
    replacement = ("    ordered = sorted(ranked, key=lambda entry: entry[0])\n"
                   "    _record(ordered)\n"
                   "    return [node for _, node in ordered]")
    scope = dict(original.__globals__, _record=record)
    exec(compile(source.replace(RANK_LINE, replacement), str(filename), "exec"), scope)
    emitted = scope[original.__name__]
    if cell is None:
        yield emitted
        return
    cell.cell_contents = emitted
    try:
        yield operation
    finally:
        cell.cell_contents = original


def strip_clocks(value):
    if isinstance(value, dict):
        return {key: strip_clocks(row) for key, row in value.items() if key not in ("cpu_ns", "elapsed_ns")}
    if isinstance(value, list):
        return [strip_clocks(row) for row in value]
    return value


def arm(refine, race, original, ready, prepared, region, bound, mode, label, base_inputs):
    import combined_successor as combined
    import nomination_handoff as nomination
    from leo.analysis.localization_v3.discovery import signature
    from single_rank_refusal import single_rank_refusal
    from two_centre_seeds import elapsed, now

    audit, passes = {}, []

    def scores(rows):
        passes.append([dict(score=float(score).hex(), signature=signature(node)) for score, node in rows])

    context = single_rank_refusal() if label == "fixed" else nullcontext()
    started = now()
    with context, rank_readout(ready.exact_rank, scores) as rank:
        handoff = combined.SuccessorHandoff(ready.core, ready.screens, rank, audit)
        if handoff.screen is None or handoff.scan is not None or handoff.nodes is not None:
            raise ValueError("The cold arm requires a fresh instrumented ordinary handoff")
        with patch.object(race, "refine", original):
            invoke = refine(race, handoff)
        setup = elapsed(started)
        started = now()
        selected, endpoint, reference, details = invoke(mode, prepared, region, bound)
        timed = elapsed(started)

    if (nomination.numerical_inputs(prepared).hex() != base_inputs or handoff.checkpoint is None
            or handoff.used or handoff.speculative or handoff.nodes is None or handoff.scan is None):
        raise ValueError("Expected fresh exact checkpoints over unchanged prepared geometry")
    checkpoint = handoff.consume(handoff.scan, handoff.nodes[:3])
    if checkpoint is None or not handoff.used:
        raise ValueError("The original checkpoint consume port refused the retained ordinary ranks")
    return dict(clock=timed, setup=setup, scopes=audit, calls=passes,
                region=dict(center=list(region.center), width_km=region.width_km),
                prepared_geometry_sha256=base_inputs, winner=signature(selected), endpoint=endpoint,
                reference=reference, finalist_evidence=strip_clocks(details), checkpoint=checkpoint,
                tracked_owner_signature=[signature(node) for node in handoff.nodes])


def fork_arm(path, *values):
    if len(tuple(Path("/proc/self/task").iterdir())) != 1:
        raise ValueError("Only a single-threaded prepared process may fork an isolated comparison arm")
    child = os.fork()
    if not child:
        status = 0
        try:
            write(path, arm(*values))
        except BaseException:
            path.with_suffix(".error").write_text(format_exc())
            status = 1
        finally:
            os._exit(status)
    _, status = os.waitpid(child, 0)
    if os.waitstatus_to_exitcode(status):
        raise ValueError(f"Cold child failed: {path.with_suffix('.error')}")
    return json.loads(path.read_bytes())


def compare(pairs, prior):
    historical = prior["lean_attempts"][0]["cold"]
    signatures = prior["two_centre_rank"]["finalist_signatures"]
    identity = None
    gains = []
    for pair in pairs:
        a, b = pair["ordinary"], pair["fixed"]
        numeric = {key: a[key] for key in ("region", "prepared_geometry_sha256", "winner", "endpoint", "reference",
                                          "finalist_evidence", "checkpoint", "tracked_owner_signature")}
        if (numeric != {key: b[key] for key in numeric} or (identity is not None and numeric != identity)
                or [row["signature"] for row in a["calls"][-1]] != signatures
                or a["finalist_evidence"] != strip_clocks(historical)):
            raise ValueError("Cold winner, finalists or checkpoints failed exact scientific parity")
        if (len(a["calls"]) != 2 or len(b["calls"]) != 1 or a["calls"][0] != a["calls"][1] or a["calls"][1] != b["calls"][0]
                or not b["scopes"]["two_centre_rank"].get("declined_before_centre_fits")
                or any(row["scopes"]["two_centre_rank"].get("fallback") != "no_supported_scout" for row in (a, b))
                or any(row["scopes"]["nomination_handoff"]["prefixes_captured"] != 2 or len(row["checkpoint"]) != 2 for row in (a, b))):
            raise ValueError("Expected one exact rank in the corrected arm and two in control")
        identity = numeric
        gains.append({key: a["clock"][key]-b["clock"][key] for key in a["clock"]})
    return dict(qualified=True, cold_delta_ns=gains, median_cold_saved_ns={key: median(row[key] for row in gains) for key in gains[0]})


def run(root):
    from empty_bootstrap import bind_native, load_runtime

    _, specification, _, publication, _ = load_runtime()
    from combined_successor_raw_entry import solver_ports
    from cumulative_grid_projection import saved_inventory_port
    from dense_geographic_trial import host
    import exact_named_raw as raw
    from legacy_first_map_acceleration import checked_artifacts
    from legacy_first_map_entry import parser
    from named_constrained_research import deny_waveform
    import nomination_handoff as nomination
    from unified_short_bootstrap import Handoff
    from leo.storage.fast_scan import FastSegmentSource
    from two_centre_seeds import elapsed, now

    sys.addaudithook(forbid_raw)
    stage_seal = checked(STAGE/"prediction-seal.json", SEAL)
    source = checked(STAGE/"result.json", RESULT)
    if source["case"] != "DS30-0016" or source["science"]["native_sha256"] != NATIVE or not source["qualified"]:
        raise ValueError("Expected the original measured combined DS30-0016 fix")
    admission = checked(STAGE/"admission.json", stage_seal["admission.json"])
    rel, = (p for p in stage_seal if p.endswith("/detections.json"))
    native = checked(STAGE/rel, NATIVE)
    inventory, = (STAGE/p for p in stage_seal if "/fast-scan-inputs/" in p)
    checked(inventory, stage_seal[str(inventory.relative_to(STAGE))])
    rel_witness = "candidate/exact-named-raw-witness.json"
    prior = checked(STAGE/rel_witness, stage_seal[rel_witness])["ports"]["history_risk"]
    argv = admission["command"]
    if Path(argv[5]).name != "combined_successor_raw_entry.py" or argv[6] != "--recording":
        raise ValueError("The archived admission must use the guarded original command")
    options = argv[6:]
    options[options.index("--output")+1] = str(root/"cold-input")
    args = parser().parse_args(options)
    request = admission["case_source"]["request"]
    raw.staged_path(args.archive)
    offer = checked(args.region, request["offer_sha256"])
    if (args.archive_sha256 != request["archive"]["snapshots_sha256"] or args.archive != Path(request["archive"]["root"])
            or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]):
        raise ValueError("The causal catalogue, offered region or cutoff differs from the signed control")
    identity = native["source"]
    receiver = native["provenance"]["detector_sha256"][7:]
    bind_native(native, request["session"], identity["input_manifest_sha256"], receiver, expected=NATIVE)
    handoff = Handoff(request["session"], identity["input_manifest_sha256"], receiver, native)
    if len(native["source"]["probes"]) != 1426 or native["provenance"]["window_count"] != 808:
        raise ValueError("The original signed opportunity support changed")
    saved = dict(recording=str(args.recording), saved_inventory=str(inventory), session=handoff.session,
                 inventory=handoff.inventory, receiver="native-20-8-held-history")
    book = checked_artifacts(args.legacy_first_map_fast, args.legacy_first_map_fast_sha256)
    raw.staged_path(root.parent)
    machine = host()
    root.mkdir()
    pairs, start, stage = [], now(), {}
    original_factory = nomination.capture_race

    def observe(race, ready):
        original = race.refine

        def test(mode, prepared, region, bound):
            if (mode != "race" or pairs or prepared["sky"]["metadata"]["cutoff_utc_ns"] != request["cutoff_utc_ns"]
                    or list(region.center) != offer["center"] or region.width_km != offer["width_km"]):
                raise ValueError("Expected one genuine prepared cold race at the signed cutoff")
            stage.update(preparation=elapsed(start), geometry=nomination.numerical_inputs(prepared).hex())
            for number, order in enumerate(ORDERS):
                pair = {}
                for label in order:
                    pair[label] = fork_arm(root/f"{number}-{label}.json", original_factory, race, original, ready,
                                           prepared, region, bound, mode, label, stage["geometry"])
                pairs.append(pair)
            raise ColdComplete

        return test

    try:
        with (patch.object(nomination, "capture_race", observe), patch.object(FastSegmentSource, "windows", deny_waveform),
              saved_inventory_port(saved), solver_ports(book, {})):
            raw.publish_active(args, publication, specification, handoff)
    except ColdComplete:
        if len(pairs) != len(ORDERS) or handoff.calls != 1:
            raise ValueError("One genuine signed handoff must prepare the full ordered comparison")
    else:
        raise ValueError("The trial continued beyond the cold race")
    if any((root/"cold-input").rglob("terminal.json")) or any((root/"cold-input").rglob("*.png")):
        raise ValueError("The measured cold stage must stop before a complete fit or figure")
    write(root/"result.json", dict(compare(pairs, prior), pairs=pairs, preparation=stage, orders=ORDERS,
          machine=machine, waveform_reads=0, case="DS30-0016", native_sha256=NATIVE, input_seal_sha256=SEAL,
          cutoff_utc_ns=request["cutoff_utc_ns"], offer=offer, archive=request["archive"],
          sources={name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
              Path(__file__).name, "single_rank_refusal.py", "single-rank-refusal-trial-protocol.md",
              "combined_successor.py", "two_centre_seeds.py", "nomination_handoff.py", "cold_finalist_race.py")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
