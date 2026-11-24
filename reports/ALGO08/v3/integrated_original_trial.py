"""Time and score the frozen integrated original-file development controls."""

import argparse
from pathlib import Path
from unittest.mock import patch

import combined_successor_cairo_trial as cairo
import combined_successor_original as ordinary
from integrated_original_entry import HELD_SHA, PNG_LIBRARY, PNG_SHA, SPARSE_LIBRARY


CASE, TINY = ordinary.CASES
HERE = ordinary.HERE
BASE = Path("/dev/shm/leo-v3-combined-successor-cairo-01")/CASE
BASE_PIN = "b47d6753614a20feb577bb2246eabf21a94b027a46d8a928cb014874aa1960d7"
THRESHOLD = 1.568
CHANGED = {
    "combined_successor_cairo_trial.py", "combined_successor_original.py", "legacy_fused_map.py",
    "unified_short_bootstrap.py",
}
EXTRA = (
    Path(__file__).name, "integrated_original_entry.py", "integrated-original-protocol.md",
    "eight_ms_native_receiver.py", "eight_ms_held_fit.py", "full_short_run.py", "verified_rgba.py",
    "verified_rgba_rows.c", "verified_png_reads.py", "single_rank_refusal.py",
)


def baseline():
    from visit_frame_raw_0016 import checked

    return checked(BASE/"result.json", BASE_PIN)


def sources(_prior):
    expected = baseline()["sources"]
    current = {name: cairo.digest(ordinary.ROOT/name) for name in expected}
    allowed = {str(ordinary.SCOPE/name) for name in CHANGED}
    if {name for name in expected if expected[name] != current[name]} != allowed:
        raise ValueError("The integrated worker differs from the frozen six-Cairo source scope")
    return current | {str(ordinary.SCOPE/name): cairo.digest(HERE/name) for name in EXTRA}


def command(old, output):
    argv = cairo.cairo_command(old, output)
    argv[5] = str(HERE/"integrated_original_entry.py")
    argv[argv.index("--short-binary")+1] = str(SPARSE_LIBRARY)
    return [*argv, "--sparse8-primary"]


def gates(process, tiny, baseline_clocks):
    from legacy_block_0107_score import speedup_gate

    return {key: speedup_gate({name: clock[key] for name, clock in baseline_clocks.items()},
                              {CASE: process[key], TINY: tiny[key]})
            for key in ("elapsed_s", "cpu_s")}


def allowed_tiny(positive, process):
    return (positive.get("qualified") and process["exit_code"] == 0
            and positive["modeled_cohort_gates"]["elapsed_s"]["summed_speedup"] >= THRESHOLD)


def launch(root, label, first):
    from empty_bootstrap import checked
    from full_short_run import SPARSE_EIGHT_MS_SHA
    from visit_frame_raw_0016 import read

    cairo.references()
    checked(PNG_LIBRARY, PNG_SHA)
    positive = None
    if first is not None:
        receipts = {n: read(first/n/"result.json") for n in ordinary.CASES}
        if (not all(r["qualified"] for r in receipts.values())
                or receipts[TINY]["actual_cohort_gates"]["elapsed_s"]["summed_speedup"] < THRESHOLD):
            raise ValueError("The first qualified measured pair did not authorize a reversal")
        if label == CASE and not (root.with_name(root.name+"-tiny")/TINY/"result.json").is_file():
            raise ValueError("The repetition must be withholding first")
        positive = first/CASE
    with (patch.object(ordinary, "sources", sources), patch.object(ordinary, "command_for", command),
          patch.object(ordinary, "allowed_tiny", allowed_tiny)):
        ordinary.launch(root, label, short_pin=SPARSE_EIGHT_MS_SHA, positive_reference=positive)


def native(target, receipt):
    from visit_frame_raw_0016 import checked

    path, = target.glob("fast-scan-automatic-work/*/detections.json")
    return checked(path, receipt["native_sha256"])


def rebind_request(target, old_target, req, current, old, dimensions):
    from continued_cfo_trial import rebinding
    from empty_bootstrap import bind_native
    from full_short_run import SPARSE_EIGHT_MS_RECIPE_SHA, SPARSE_EIGHT_MS_SHA, checked_recipe
    from leo.contracts.digests import canonical_digest

    changed, reference = native(target, current), native(old_target, old)
    earlier, held = (e["held_anchor_route"] for e in (old, current))
    chosen = held["receiver_recipe"]
    recipe = checked_recipe(True, short_pin=SPARSE_EIGHT_MS_SHA)
    old_choice = earlier["receiver_recipe"]["held_native_8ms"]
    expected = dict(recipe, held_native_8ms=old_choice)
    probes = reference["source"]["probes"]
    factors = sum(len(row["candidates"]) for row in probes)
    parent = rebinding(reference, probes, recipe)
    predicted = rebinding(reference, probes, expected)
    final = canonical_digest(predicted)
    if (changed != predicted or chosen != expected or current["receiver_recipe"] != expected
            or canonical_digest(chosen) != "sha256:"+HELD_SHA
            or held["detector_recipe_sha256"] != current["detector_recipe_sha256"]
            or current["detector_recipe_sha256"] != "sha256:"+HELD_SHA
            or held["parent_detector_sha256"] != "sha256:"+SPARSE_EIGHT_MS_RECIPE_SHA
            or held["parent_native_sha256"] != canonical_digest(parent)
            or held["choice"] != earlier["choice"] or held["choice"]["route"] != "unfiltered"
            or held["observed"] != held["selected"] or held["selected"] != factors
            or held["refinement_calls"] != 0 or (len(probes), factors) != dimensions):
        raise ValueError("Sparse 8 ms did not reproduce every original signed factor and metadata field")
    bind_native(changed, req["session"], req["inventory"], HELD_SHA, expected=final)
    bind_native(reference, req["session"], req["inventory"], req["detector"][7:], expected=req["native"])
    return dict(req, detector="sha256:"+HELD_SHA, native=final)


def terminal(target, receipt):
    from visit_frame_raw_0016 import checked

    path = target/"fast-scan-automatic-work"/receipt["run_id"]/"terminal.json"
    return checked(path, receipt["terminal_sha256"])


def rekey_proof(proof, old_sha, actual_sha):
    """Change only the proven packet binding on an otherwise identical proof."""
    def bound(item):
        value = item.get("native_sha256")
        if value is None:
            return dict(item)
        if value != old_sha:
            raise ValueError("Unbound previous curvature proof")
        return dict(item, native_sha256=actual_sha)

    expected = bound(proof)
    if expected.get("curvature_extent") is not None:
        expected["curvature_extent"] = bound(expected["curvature_extent"])
    return expected


def score(root, label, first):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from legacy_block_0107_score import snapshot as withheld
    from legacy_block_raw_score import snapshot as complete
    from legacy_verify_original_trial import inspect_once
    from publication_media_checks import image_comparison_fields
    from visit_frame_raw_0016 import read

    base, _, _ = cairo.references()
    baseline_clocks = {n: v["installed"] for n, v in base.items()}
    reference = baseline() if label == CASE else base[label]
    old_target = (BASE if label == CASE else cairo.ARCHIVE/label)/"candidate"
    folder = root/label
    book, log, startup = (read(folder/n) for n in ("admission.json", "candidate-clock.json", "startup.json"))
    if (read(folder/"prediction-seal.json") != output_seal(folder) or book["command"] != log["command"]
            or book["sources"] != sources(None)):
        raise ValueError("Frozen invocation or original output seal changed")
    process = log["clock"]
    result = dict(case=label, process=process, qualified=False, installed=baseline_clocks[label],
                  six_cairo_or_guarded=reference["process"], sources=book["sources"], admission=book,
                  startup=startup, positive_prediction_sha256="sha256:"+cairo.digest(folder/"prediction-seal.json"),
                  previous_sha256=BASE_PIN if label == CASE else cairo.BASE_PINS[label],
                  png_library_sha256=PNG_SHA)
    if process["exit_code"]:
        write(folder/"result.json", result | dict(decision="failed"))
        return
    target = folder/"candidate"
    raw, witness = (read(target/n) for n in ("unified-short-bootstrap.json", "exact-named-raw-witness.json"))
    old = reference["receiver"]
    result.update(decision=raw["receipt"]["decision"], receiver=raw, witness=witness)
    expected_decision = "complete" if label == CASE else "withheld"
    if result["decision"] != expected_decision:
        write(folder/"result.json", result)
        return
    req = book["case_source"]["request"]
    acquisition = inspect_once(target, req, reference["acquisition"])
    rebased = rebind_request(target, old_target, req, raw, old, (1426, 506) if label == CASE else (54, 19))
    current, previous = (terminal(path, u["receipt"]) for path, u in ((target, raw), (old_target, old)))
    engine = acquisition["acceleration"]["solver"]
    controls = dict(
        terminal=current == dict(previous, native_sha256=rebased["native"]),
        custody=all(row["complete_encoded_auth"] for row in acquisition["members"])
        and acquisition["acceleration"]["artifacts"] == reference["acquisition"]["acceleration"]["artifacts"],
        residence=all(log[key] == book["case_source"]["resident"]["waveform"] for key in ("cache_before", "cache_after")),
        no_backing=book["raw_conditioning_bytes"] == 0,
        receiver_audit=all(raw["receiver_audit"]["native"][key] == old["receiver_audit"]["native"][key]
                           for key in ("factors", "installed_sha256", "native_calls", "rule", "streams", "visits")),
    )
    previous = reference["science"]
    if label == CASE:
        science = complete(target, log, rebased, book["case_source"]["producer"], verify_renderer=cairo.require_renderer)
        ports, earlier = (item["ports"] for item in (witness, reference["witness"]))
        route, old_route = (item["history_risk"] for item in (ports, earlier))
        rank = route["two_centre_rank"]
        png = engine["png_native"]
        controls.update(
            science=all(science["published"][key] == previous["published"][key]
                        for key in ("arms", "owners", "raw_authority", "scientific_digests")),
            ordered_owners=science["ordered_owners"] == previous["ordered_owners"],
            all_owned_rf=all(arm["residual_rms_hz"] == reference["witness"]["evidence"]["detail"]["arms"][n]["residual_rms_hz"]
                             for n, arm in witness["evidence"]["detail"]["arms"].items()),
            geographic=route["boundary_checks"] == old_route["boundary_checks"]
            and [f["exterior"] for f in route["lean_attempts"]] == [f["exterior"] for f in old_route["lean_attempts"]],
            original_lookahead=all(science["prefetch"][key] == previous["prefetch"][key]
                                   for key in ("fallback", "hits", "hit_bytes", "submitted", "submitted_bytes")),
            grid_and_path=engine["grid"]["projection"]["grids"] == 1 and science["positions"]["grid_points"] == 179
            and len(engine["in_flight"]) == 1,
            png=len(science["images"]) == 8 and image_comparison_fields(science["images"]) == image_comparison_fields(previous["images"])
            and {k: v for k, v in science["positions"].items() if k == "figures"} == {"figures": previous["positions"]["figures"]}
            and (png["native"], png["fallback"], ports["png"]["verified"], ports["png"]["reused"]) == (8, 0, 8, 8),
            rank=rank["declined_before_centre_fits"] and rank["paid_centres"] == 0 and "ordinary_retry" in rank,
        )
        result["modeled_cohort_gates"] = gates(process, base[TINY]["process"], baseline_clocks)
    else:
        science = withheld(target, process, rebased)
        controls.update(no_solver=not engine, genuine_proof=(
            science["graph_proof"] == rekey_proof(previous["graph_proof"], req["native"], rebased["native"])),
            withholding=all(science[key] == previous[key] for key in ("factors", "opportunities", "receiver_visits")))
    result.update(qualified=all(controls.values()), checks=controls, acquisition=acquisition, science=science,
                  rebound_request=rebased)
    if label == CASE:
        result["positive_unlocks_tiny"] = allowed_tiny(result, process)
        if first is not None:
            tiny = read(root.with_name(root.name+"-tiny")/TINY/"result.json")
            if tiny["qualified"] and result["qualified"]:
                result["actual_cohort_gates"] = gates(process, tiny["process"], baseline_clocks)
    elif first is None and result["qualified"]:
        pos = read(root/CASE/"result.json")
        result["actual_cohort_gates"] = gates(pos["process"], process, baseline_clocks)
    write(folder/"result.json", result)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("case", choices=ordinary.CASES)
    cli.add_argument("--first", type=Path, help="Sealed first pair for the single reversed repetition")
    args = cli.parse_args()
    {"launch": launch, "score": score}[args.action](args.root, args.case, args.first)
