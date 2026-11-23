"""Replay two early saved DS30-0402 stage cuts and diagnose the original fragment gates."""

import argparse
from functools import partial
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import numpy as np


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from fragment_gate_cross import factorial, fitted_fragment, local_gate, mask_influence, sections, state, state_terms
from owner_loss_0402 import ARCHIVED, ARCHIVED_SHA, ARMS, STAGED, clocks, invoke, now, request, named_gate_witness


TRACK_62735 = "SCAN-RX1-CH5-T004-RF11709687500.000000"
TRACK_62735_OTHER = "SCAN-RX1-CH5-T008-RF11709687500.000000"
TRACK_58377 = "SCAN-RX2-CH6-T003-RF11959687500.000000"
ARCHIVED_CUMULATIVE = Path("/dev/shm/leo-v3-owner-loss-0402-run01/candidate/owner-trace.json")
TRACE_SHA = "f73cb243599ed47b40b78ac6d990c381e46030463ce7537301c1b24a2185b645"
PROTOCOL = HERE / "fragment-cross-0402-protocol.md"


class StageCapture(BaseException):
    """Never let the protected stage cuts proceed to terminal or media publication."""


def capture_named(job, path):
    from leo.analysis.localization_v3 import family_cavity
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core, v5_screen_winner

    original_packet = algo08_position.prepare_packet
    original_infer, original_screen = v5_core.infer, v5_screen_winner.screen_nodes
    result = {}
    start = now()

    def infer(prepared, *args, **kwargs):
        result["prepared"] = prepared
        return original_infer(prepared, *args, **kwargs)

    def screen(scan, nodes, details):
        selection = original_screen(scan, nodes, details)
        result["screened_winner"] = details["winning_rank"]
        return selection

    def at_nomination(signed):
        result["to_cut"] = clocks(start)
        result["signed"] = signed
        with patch.object(algo08_position, "prepare_packet", partial(original_packet, include_grid=False)):
            packet = algo08_position.selected_packet(result.pop("prepared"), signed, None)
        result["owners"] = {arm: [[v["observation_id"], v["norad"], v["role"]] for v in packet["rows"][arm]]
                            for arm in ARMS}
        result["objective_replay"] = packet["objective_replay"]
        raise StageCapture()

    with (patch.object(v5_core, "infer", infer), patch.object(v5_screen_winner, "screen_nodes", screen),
          patch.object(family_cavity, "nominate_families", at_nomination)):
        try:
            invoke(job, "stock", path)
        except StageCapture:
            pass
    if not all(key in result for key in ("signed", "screened_winner", "owners")):
        raise ValueError("Named path failed to reach its original pre-nomination incumbent")
    result["through_witness"] = clocks(start)
    return result


def capture_cumulative(job, path):
    import blind_joint_finish as finish

    build, drop, pair, select = finish.build_at, finish.drop_failing, finish.finish_pair, finish.select_entries
    result, recent = dict(early=[]), {}
    start = now()

    def at_build(scan, node, keep, point, references, model):
        base, powers, means = build(scan, node, keep, point, references, model)
        recent.clear()
        recent.update(scan=scan, node=node, point=point, model=model, keep=base.keep, powers=powers,
                      means=means, problems={"c0": base}, entries=[])
        return base, powers, means

    def at_drop(keep, rows, slices, metrics):
        base = recent["problems"]["c0"]
        if rows is not base.rows or slices is not base.slices or not np.array_equal(keep, base.keep):
            raise ValueError("The cumulative gate does not match the immediately preceding causal build")
        result["early"].append(dict(recent, gates=metrics["tracks"]))
        return drop(keep, rows, slices, metrics)

    def at_selection(problem, point, metrics):
        entries = select(problem, point, metrics)
        phases = problem.state(point)["phases"]
        available = {row["norad"] for row in metrics["tracks"]
                     if row["compatible"] and abs(phases[row["candidate_index"]]) <= 15}
        result["predictive_families"] = sorted(available)
        return entries

    def at_pair(*args, **kwargs):
        selected, passing = pair(*args, **kwargs)
        result.update(pair=selected, pair_passed=bool(passing), to_cut=clocks(start))
        raise StageCapture()

    with (patch.object(finish, "build_at", at_build), patch.object(finish, "drop_failing", at_drop),
          patch.object(finish, "finish_pair", at_pair), patch.object(finish, "select_entries", at_selection)):
        try:
            invoke(job, "cumulative", path)
        except StageCapture:
            pass
    if len(result["early"]) != 2 or "pair" not in result or "predictive_families" not in result:
        raise ValueError("Cumulative path failed to reach the original intact pair")
    return result


def anchor(problem, point):
    return dict(point=np.asarray(point), norads=[int(problem.scan.norads[j]) for j in problem.labels],
                phase=problem.reference.copy())


def build_pair(pair):
    from leo.analysis.localization_v3 import event_position

    scan, node, keep, powers, means, model, entries = (pair[key] for key in (
        "scan", "node", "keep", "powers", "means", "model", "entries"))
    problems, anchors = {}, {}
    for arm, row in pair["arms"].items():
        problem = event_position.make_event_problem(scan, node, keep, arm, row["phase_reference"], powers, means, model, [])
        event_position.attach_event_predictive(problem, entries, powers)
        event_position.cached(problem)
        problems[arm] = problem
        anchors[arm] = anchor(problem, row["endpoint_east_north_km"])
    return dict(pair, problems=problems, anchors=anchors)


def find_track(rows, component):
    row, = (value for value in rows if value["component"] == component)
    return row


def verify_gate(expected, observed, *, absolute_tolerance=1e-6):
    if any(expected[key] != observed[key] for key in ("points", "compatible", "aliases_changed")):
        raise ValueError(f"Recomputed {expected['component']} changes a saved gate decision")
    if any(abs(expected[key] - observed[key]) > absolute_tolerance for key in ("profile_bias_hz", "profile_rms_hz")):
        raise ValueError(f"Recomputed {expected['component']} changes a saved profile")
    a = expected["conditional_residual_gate"]
    b = observed["conditional_residual_gate"]
    if (a["compatible"] != b["compatible"] or any(abs(a[key] - b[key]) > absolute_tolerance for key in ("rms_hz", "mean_hz"))
            or any(abs(float(v) - float(b["diagnostics"][key])) > absolute_tolerance for key, v in a["diagnostics"].items())):
        raise ValueError(f"Recomputed {expected['component']} changes a saved conditional residual")


def predictive_readout(problem, point, entries, norad):
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from leo.analysis.research.retained_track_likelihood import profile

    prepared = problem.calculate(point)
    results = []
    for entry, sl in zip(entries, problem.linear_slices, strict=True):
        if entry["norad"] != norad:
            continue
        i = entry["track_index"]
        t = problem.scan.tracks[i]
        raw = prepared["linear_raw_prediction_residual_hz"][sl]
        terms = profile(raw, np.zeros(len(raw)), *problem.scan.white[i], bias_sigma=300.)
        diag = batch_noise_screen(terms["innovations"], t["times"])
        minimum = float(prepared["linear_elevation"][sl].min())
        results.append(dict(
            component=entry["component"], observation_ids=entry["observation_ids"],
            points=len(raw), same_signed_alias=int(terms["alias"][0]) == 0, entry_alias=int(entry["alias"]),
            rms_hz=float(terms["rms"][0]), bias_hz=float(terms["bias"][0]), minimum_elevation_deg=minimum,
            diagnostics={key: value[0] for key, value in diag.items()},
            compatible=bool(terms["rms"][0] <= 450 and abs(terms["bias"][0]) <= 3000
                            and int(terms["alias"][0]) == 0 and diag["noise_screen_pass"][0] and minimum >= 0),
        ))
    return results


def compare_named_capture(named, old):
    baseline = old["runs"]["stock"]
    witness = named_gate_witness(old)
    if (witness["cavity_accepted"] or named["owners"] != baseline["selected_rows"]
            or named["screened_winner"] != baseline["science"]["receipt"]["screened_nomination"]["winning_rank"]):
        raise ValueError("The early named incumbent does not equal the saved standard owner rows")
    for arm in ARMS:
        row = named["signed"]["arms"][arm]
        reported = baseline["terminal"]["arms"][arm]
        if (not np.allclose(row["endpoint_latlon"], reported["latlon"], rtol=0, atol=1e-10)
                or abs(row["RMS_hz"] - reported["rf_rms_hz"]) > 1e-8):
            raise ValueError("Named pre-cavity did not reproduce the saved terminal")
    return dict(positions_and_rf_identical=True, ordered_owners_identical=True, archived_cavity_adopted=False,
                screened_rank=named["screened_winner"], objective_replay=named["objective_replay"])


def comparable_support(full, subset):
    missing = set(full) - set(subset)
    if len(missing) != 1 or [oid for oid in full if oid not in missing] != subset:
        raise ValueError("The intended 61/62 comparison requires exact original ordering and one extra observation")
    return missing.pop()


def compare(named, cumulative, historical_trace):
    begin = now()
    if cumulative["pair_passed"] != historical_trace["pre_repair"][0]["passed"]:
        raise ValueError("The original intact paired decision changed")
    fixed = build_pair(named["signed"])
    intact = build_pair(cumulative["pair"])
    first, early = cumulative["early"]
    parity = []
    for k, (frame, keys) in enumerate(((first, (TRACK_62735, TRACK_62735_OTHER, TRACK_58377)),
                                       (early, (TRACK_62735, TRACK_58377)))):
        readouts = state(frame["problems"]["c0"], frame["point"], set(keys))
        for component in keys:
            saved = find_track(historical_trace["curved_gates"][k]["rows"], component)
            seen = find_track(frame["gates"], component)
            if seen["observation_ids"] != saved["observation_ids"]:
                raise ValueError("Different historical early curved support")
            data = readouts[component]
            gate = local_gate(data, seen["observation_ids"])
            verify_gate(seen, gate)
            verify_gate(saved, gate)
            parity.append(dict(stage=k+1, component=component, gate=gate, parameters=fitted_fragment(data, seen["observation_ids"])))
    data = {}
    predict = {}
    for arm in ARMS:
        a, b = fixed["anchors"][arm], intact["anchors"][arm]
        named_problem, intact_problem = fixed["problems"][arm], intact["problems"][arm]
        n = state(named_problem, a["point"], {TRACK_62735, TRACK_58377})
        c = state(intact_problem, b["point"], {TRACK_58377})
        early_fragment = state(early["problems"]["c0"], early["point"], {TRACK_62735})[TRACK_62735]
        named_rows = {name: find_track(fixed["arms"][arm]["gates"]["tracks"], name)
                      for name in (TRACK_62735, TRACK_58377)}
        candidate_row = find_track(intact["arms"][arm]["gates"]["tracks"], TRACK_58377)
        reference_58377 = find_track(historical_trace["pre_repair"][0]["arms"][arm]["curved"], TRACK_58377)
        observed = candidate_row["observation_ids"]
        selected = named_rows[TRACK_58377]["observation_ids"]
        extra_id = comparable_support(observed, selected)
        if observed != reference_58377["observation_ids"]:
            raise ValueError("Cumulative pre-repair support differs from the independent archived stage")
        gate_candidate = local_gate(c[TRACK_58377], observed)
        verify_gate(candidate_row, gate_candidate)
        verify_gate(reference_58377, gate_candidate)
        for name, expected in named_rows.items():
            verify_gate(expected, local_gate(n[name], expected["observation_ids"]))

        elected = named_rows[TRACK_62735]["observation_ids"]
        if elected != find_track(early["gates"], TRACK_62735)["observation_ids"]:
            raise ValueError("62735's named and cumulative early tracks differ in exact support")
        anchors = dict(named=a, cumulative=b)
        curve62735 = factorial(dict(named=fixed, cumulative=early), anchors, arm, TRACK_62735, elected)
        curve58377 = factorial(dict(named=fixed, cumulative=intact), anchors, arm, TRACK_58377, selected)
        influence = mask_influence(c[TRACK_58377], observed)
        excluded, = (row for row in influence if row["removed"] == extra_id)
        data[arm] = dict(
            named_position=a["point"], candidate_position=b["point"],
            early_cumulative_position=early["point"], named_model=fixed["model"], intact_model=intact["model"],
            early_cumulative_model=early["model"],
            curved_62735=dict(
                named=local_gate(n[TRACK_62735], elected), original_second_gate_c0=local_gate(early_fragment, elected),
                factorial=curve62735,
                endpoint_rerender_terms=state_terms(early_fragment, n[TRACK_62735], elected) if arm == "c0" else None),
            curved_58377=dict(
                named=local_gate(n[TRACK_58377], selected), candidate_all_62=gate_candidate,
                candidate_named_61_same_state=local_gate(c[TRACK_58377], selected),
                named_all_62_same_state=local_gate(n[TRACK_58377], observed),
                factorial=curve58377, endpoint_rerender_terms=state_terms(c[TRACK_58377], n[TRACK_58377], selected),
                mask_influence=dict(extra=excluded, extra_rank=influence.index(excluded)+1,
                                    passing=sum(row["passed"] for row in influence), strongest=influence[:3])),
        )
        values = predictive_readout(named_problem, a["point"], fixed["entries"], 62735)
        originals = [row for row in fixed["arms"][arm]["linear_gates"] if row["norad"] == 62735]
        if ([(row["observation_ids"], row["compatible"]) for row in values]
                != [(row["observation_ids"], row["compatible"]) for row in originals]
                or sorted(row["points"] for row in values) != [15, 17]):
            raise ValueError("Named predictive evidence does not match the exact two lost fragments")
        predict[arm] = values
    if (62735 in cumulative["predictive_families"]
            or cumulative["predictive_families"] != historical_trace["predictive"][0]["available"]):
        raise ValueError("The actual cumulative predictive gate family availability changed")
    return dict(arms=data, early_gate_readouts=parity, named_predictive_62735=predict,
                cumulative_predictive_62735_eligible=False, diagnostics=clocks(begin))


def run(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    from dense_geographic_trial import host

    machine = host()
    runtime = boot.load_runtime()
    job, req = request()
    root.mkdir()
    with patch.object(boot, "load_runtime", return_value=runtime):
        named = capture_named(job, root / "named-incomplete")
        cumulative = capture_cumulative(job, root / "cumulative-incomplete")
    # No archived owner choice or old fit is loaded before the two actual captures.
    history = json.loads(gzip.decompress(boot.checked(ARCHIVED, ARCHIVED_SHA)))
    historical_trace = json.loads(boot.checked(ARCHIVED_CUMULATIVE, TRACE_SHA))
    named_parity = compare_named_capture(named, history)
    write(root / "cuts.json", dict(named=named["to_cut"], cumulative=cumulative["to_cut"], named_parity=named_parity))
    from tools.pipeline_eval.variants import orbit_projector, v5_direct_cavity

    projector = orbit_projector.Projector(boot.RELEASE / "assets/projector.so")
    with v5_direct_cavity.numerical_bindings(projector):
        measured = compare(named, cumulative, historical_trace)
    if list(root.glob("*-incomplete/**/terminal.json")) or list(root.glob("*-incomplete/**/*.png")):
        raise ValueError("A stage-cut diagnostic must never publish terminal products")
    write(root / "cross.json", dict(
        machine=machine, native_sha256=req["native_sha256"], cutoff_utc_ns=req["causal_cutoff_utc_ns"],
        archive=req["local_archive"]["snapshots_sha256"], region_file_sha256=req["offer_sha256"],
        previous_named_and_cumulative_sha256=ARCHIVED_SHA, archived_cumulative_gate_sha256=TRACE_SHA,
        protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),
        implementation={name: sha256((HERE / name).read_bytes()).hexdigest()
                        for name in (Path(__file__).name, "fragment_gate_cross.py")},
        named_capture=named["to_cut"], named_with_owner_witness=named["through_witness"],
        cumulative_capture=cumulative["to_cut"], original_named_parity=named_parity, **measured,
    ))


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use a fresh private tmpfs parent")
    root.mkdir()
    env = environment(STAGED)
    env["TMPDIR"] = str(root)
    command = [RELEASE / "venv/bin/python", "-IB", __file__, "run", root / "diagnostic"]
    timing = measure(command, env, root / "diagnostic")
    write(root / "exit.json", dict(timing=timing, command=list(map(str, command))))
    if timing["exit_code"]:
        raise RuntimeError("Saved crossed diagnostic failed. Its original clock and stderr were sealed.")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "run"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    globals()[args.action](args.root)
