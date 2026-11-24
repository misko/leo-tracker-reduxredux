"""Compare the normal original guarded successor with its qualified Cairo renderer."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

import combined_successor_original as ordinary


CASE, TINY = ordinary.CASES
ENTRY = HERE/"combined_successor_cairo_entry.py"
ARCHIVE = Path("/dev/shm/leo-v3-combined-successor-original-02")
CAIRO_SCORE = Path("/dev/shm/leo-v3-history-risk-0016-cairo-score01.json")
CAIRO_PIN = "b340a594fadae0b871c42d31ac269efe2cfe0a34d26089038c739e4bb8822e39"
BASE_PINS = {
    CASE: "e9ddbc9e5dd5d95baa387925c713bfda595463cafade2ecea265a7f829fd8903",
    TINY: "10d3652ad96a6dcc2730d928693edac8f7df129abe6c325e5bc1f2997b066864",
}
ALLOWED_SOURCE_CHANGES = {str(ordinary.SCOPE/name) for name in ("legacy_block_raw_entry.py", "legacy_block_raw_score.py")}
# These historical adapters gained the residual-only/keep-Agg option. Their
# six-sheet branch and the separately pinned native drawing sources survived.
CURRENT_RENDERER_ADAPTERS = {
    "history_cairo_render.py": "84140a9e162665dae43d86bd06ac7dd7b85610089a0eb9ce498de8a844538cbe",
    "direct_residual_entry.py": "684ebef5763a3d26e45fae4cce941f7c87988b03d8e2f170a4867ce18bd2ddd0",
    "one_pass_web_png.py": "820717a79448adb6e6fef2c15fbcbb090c9b135e927bb7460fde17b474ecc114",
}
BASE_COMMAND = ordinary.command_for
MEASURED_SCORER_SHA = "0d4d435f93eb6d380edd9bd41a08428ea02f379c7e5fb30edc926c91dae34aa2"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def cairo_command(old, target):
    command = BASE_COMMAND(old, target)
    command[5] = str(ENTRY)
    command[command.index("--cairo-residual-layout")] = "--cairo-six-sheets"
    return command


def sources(prior):
    from history_cairo_render import SOURCES

    root = ordinary.ROOT
    inherited = {name: pin.removeprefix("sha256:") for name, pin in prior["admission"]["sources"].items()}
    bound = {name: digest(root/name) for name in inherited}
    if {name for name in bound if bound[name] != inherited[name]} != ALLOWED_SOURCE_CHANGES:
        raise ValueError("Only the explicit original-file renderer and its score port may change")
    extras = [*ordinary.EXTRA, *(ordinary.SCOPE/name for name in (
        *SOURCES, "combined-successor-cairo-protocol.md", Path(__file__).name, ENTRY.name))]
    return bound | {str(path): digest(root/path) for path in extras}


def references():
    from empty_bootstrap import checked
    from history_cairo_render import SOURCES
    from reports.ALGO08.v3.history_risk_0016_cairo import GATE, active_renderer, gate_document
    from publication_media_checks import image_comparison_fields

    base = {label: json.loads(checked(ARCHIVE/label/"result.json", pin)) for label, pin in BASE_PINS.items()}
    prior = json.loads(checked(CAIRO_SCORE, CAIRO_PIN))
    audited = gate_document(GATE)
    cairo, standard = (audited["runs"][mode]["scientific"] for mode in ("cairo", "standard"))
    ref, cur = prior["native"], base[CASE]["science"]
    archived_pins = {str(ordinary.SCOPE/name): cairo["source_sha256"][str(ordinary.SCOPE/name)] for name in SOURCES}
    sources_match = all(digest(HERE/name) == CURRENT_RENDERER_ADAPTERS.get(name, archived_pins[str(ordinary.SCOPE/name)])
                        for name in SOURCES)
    if (not all(item["qualified"] for item in base.values()) or not prior["qualified"]
            or not all(prior["checks"].values()) or not active_renderer(ref["route"])
            or archived_pins != prior["admission"]["renderer_sources"] or not sources_match
            or image_comparison_fields(ref["figures"]) != image_comparison_fields(cairo["evidence"]["images"])
            or ref["digest"] != cur["native_sha256"] or ref["owners"] != cur["ordered_owners"]
            or any(ref["science"][k] != cur["published"][k]
                   for k in ("arms", "owners", "scientific_digests", "raw_authority"))):
        raise ValueError("Require the same scientific packet and independently audited Cairo renderer")
    sample = image_comparison_fields(cur["images"])
    baseline = image_comparison_fields(standard["evidence"]["images"])
    expected = image_comparison_fields(ref["figures"])
    from leo.contracts.fast_scan_orbits import PLOT_NAMES

    if any(sample[name] != (baseline if name in PLOT_NAMES else expected)[name] for name in sample):
        raise ValueError("The current guarded renderer's existing Cairo components differ")
    return base, prior, audited["artists"]


def tiny_model(tiny):
    from exact_named_raw import publish_active, run
    from inspect import getsource
    from unified_short_bootstrap import run as unified

    proof, engine = tiny["receiver"], tiny["acquisition"]["acceleration"]["solver"]
    raw, handoff = getsource(unified), getsource(run)
    decision = raw.split("if reason is None:", maxsplit=1)[1]
    publisher = "terminal, research = publish("
    receiver = "terminal = withhold("
    if (tiny["decision"] != "withheld" or engine or tiny["witness"]["ports"] is not None
            or proof["scientific_imports_before"] or proof["scientific_imports_after"]
            or not proof["graph_proof"]["proven"] or proof["solver_source_sha256"] is not None
            or "raw.run(args, publisher=publish_active)" not in handoff
            or not decision.index(publisher) < decision.index("else:", decision.index(publisher)) < decision.index(receiver)
            or "history_cairo_render" not in getsource(publish_active)):
        raise ValueError("Require the exact archive-certified pre-render withholding")
    return dict(archived_scope=proof["route"], verified_handoffs=proof["verified_handoffs"], renderer_called=False,
                clock_assumption="Reuse the archived launch-through-exit clock including startup",
                scientific_imports_after=proof["scientific_imports_after"],
                previous_clock=tiny["process"], previous_sha256=BASE_PINS[TINY],
                proof_source_sha256={name: digest(HERE/name) for name in (
                    "unified_short_bootstrap.py", "exact_named_raw.py", "legacy_first_map_entry.py",
                    "legacy_block_raw_entry.py", ENTRY.name)})


def modeled_gates(process, base):
    from legacy_block_0107_score import speedup_gate

    return {metric: speedup_gate({case: base[case]["installed"][metric] for case in ordinary.CASES},
                                 {CASE: process[metric], TINY: base[TINY]["process"][metric]})
            for metric in ("elapsed_s", "cpu_s")}


def allowed_tiny(positive, process):
    return bool(positive.get("qualified") and process["exit_code"] == 0
                and positive["modeled_cohort_gates"]["elapsed_s"]["gates"]["1.6x"]["both"])


def renderer_gates(ports):
    from reports.ALGO08.v3.history_risk_0016_cairo import active_renderer

    return (active_renderer(ports)
            and ports.get("cairo_layout", {}).get("original_recording_title") ==
            "fast8-auto-20261113-112146-b04f5461-1-lower")


def require_renderer(ports):
    if not renderer_gates(ports):
        raise ValueError("The selected six-sheet renderer, title and eight verified files must execute")


def image_identity(current, expected):
    return dict(sha256=current["sha256"] == expected["sha256"],
                rgba_sha256=current["rgba_sha256"] == expected["rgba_sha256"],
                size=tuple(current["size"]) == tuple(expected["size"]))


def raster_evidence(target, before, current, original, expected):
    from leo.contracts.fast_scan_orbits import PLOT_NAMES
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from named_weak_visual import registered_orbits
    from PIL import Image
    import numpy as np

    baseline = FastStandardAnalysisStore(before)
    candidate = FastStandardAnalysisStore(target)
    run = current["receipt"]["run_id"]
    rows = {}
    for name, item in current["images"].items():
        old = original["images"][name]
        shapes = {}
        docs = [store.artifact(run, name, info["sha256"])
                for store, info in ((baseline, old), (candidate, item))]
        with Image.open(BytesIO(docs[0])) as a, Image.open(BytesIO(docs[1])) as b:
            same = (a.size, a.mode, a.info) == (b.size, b.mode, b.info)
            left, right = (image.convert("RGBA") for image in (a, b))
            matches = image_identity(item, expected[name])
            actual = sha256(right.tobytes()).hexdigest() == item["rgba_sha256"]
            layer = registered_orbits(a.convert("RGB"), b.convert("RGB"), require_match=False) if name in PLOT_NAMES else None
            passed = layer is None or all(value["fraction"] is None or min(value["fraction"]) >= .98
                                          for panel in layer["rows"] for value in panel.values())
            shapes.update(size=b.size, mode=b.mode, metadata=b.info, dimensions_metadata=same,
                          independent_expected=matches, decoded=actual, registration=layer, registration_passed=passed,
                          changed_pixel_fraction=float(np.any(np.asarray(left) != np.asarray(right), axis=2).mean()))
        rows[name] = shapes
    return rows


def score(root, label):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from legacy_block_raw_score import snapshot
    from legacy_verify_original_trial import inspect_once
    from publication_media_checks import verify_position_sidecars
    from visit_frame_raw_0016 import read

    folder = root/label
    if label == TINY:
        with patch.object(ordinary, "sources", sources), patch.object(ordinary, "allowed_tiny", allowed_tiny):
            ordinary.score(root, label)
        return
    start, log = (read(folder/name) for name in ("admission.json", "candidate-clock.json"))
    current_sources = sources(ordinary.previous())
    measured = current_sources | {str(ordinary.SCOPE/Path(__file__).name): MEASURED_SCORER_SHA}
    if (read(folder/"prediction-seal.json") != output_seal(folder) or start["command"] != log["command"]
            or start["sources"] not in (current_sources, measured) or "--cairo-six-sheets" not in log["command"]):
        raise ValueError("The direct guarded Cairo child differs from its sealed admission")
    base, tested, artists = references()
    modeled = tiny_model(base[TINY])
    process, former = log["clock"], base[CASE]
    result = dict(case=CASE, process=process, installed=former["installed"], verified_once=former["verified_once"],
                  original_guarded=former["process"], setup=start["setup"], sources=start["sources"],
                  renderer_reference_sha256=CAIRO_PIN, previous_sha256=BASE_PINS, mode="cairo-six-sheets",
                  admitted=start, startup=read(folder/"startup.json"), modeled_withhold=modeled,
                  positive_prediction_sha256="sha256:"+digest(folder/"prediction-seal.json"))
    if process["exit_code"]:
        write(folder/"result.json", result | dict(qualified=False, decision="failed"))
        return
    target, req = folder/"candidate", start["case_source"]["request"]
    witness = read(target/"exact-named-raw-witness.json")
    receiver = read(target/"unified-short-bootstrap.json")
    original = inspect_once(target, req, former["acquisition"])
    active = witness["ports"]
    outcome = receiver["receipt"]["decision"]
    if outcome != "complete" or not renderer_gates(active or {}):
        write(folder/"result.json", result | dict(qualified=False, decision=outcome, witness=witness,
                                                  receiver=receiver, acquisition=original))
        return
    current = snapshot(target, log, req, start["case_source"]["producer"], verify_renderer=require_renderer)
    previous = former["science"]
    controls = ("arms", "owners", "raw_authority", "scientific_digests")
    route = active["history_risk"]
    old_route = former["witness"]["ports"]["history_risk"]
    checks = dict(
        native=all(current[key] == previous[key] for key in ("native_sha256", "native_source", "ordered_owners")),
        science=all(current["published"][key] == previous["published"][key] for key in controls),
        all_owned_rf=all(arm["residual_rms_hz"] == former["witness"]["evidence"]["detail"]["arms"][name]["residual_rms_hz"]
                         for name, arm in witness["evidence"]["detail"]["arms"].items()),
        terminal=current["receipt"]["terminal_sha256"] == previous["receipt"]["terminal_sha256"],
        geographic=route["boundary_checks"] == old_route["boundary_checks"] and
        [fit["exterior"] for fit in route["lean_attempts"]] == [fit["exterior"] for fit in old_route["lean_attempts"]],
        resident=all(log[key] == former["admission"]["case_source"]["resident"]["waveform"]
                     for key in ("cache_before", "cache_after")),
        normal_lookahead=all(current["prefetch"][key] == previous["prefetch"][key]
                             for key in ("fallback", "hits", "hit_bytes", "submitted", "submitted_bytes")),
        original_custody=all(row["complete_encoded_auth"] for row in original["members"])
        and original["acceleration"]["artifacts"] == former["acquisition"]["acceleration"]["artifacts"],
        actual_grid=original["acceleration"]["solver"]["grid"]["projection"]["grids"] == 1,
        actual_live_guard=len(original["acceleration"]["solver"]["in_flight"]) == 1,
    )
    media = raster_evidence(target, ARCHIVE/CASE/"candidate", current, previous, tested["native"]["figures"])
    checks["all_eight_figures"] = len(media) == 8 and all(
        item["dimensions_metadata"] and item["decoded"] and item["registration_passed"]
        and all(item["independent_expected"].values()) for item in media.values())
    sides = verify_position_sidecars(ARCHIVE/CASE/"candidate", target, current["receipt"]["run_id"],
                                    previous["images"], current["images"]) if checks["science"] else None
    result.update(qualified=all(checks.values()) and sides is not None, checks=checks, decision="complete",
                  media=media, scientific_artist_reference=artists, sidecars=sides, science=current, witness=witness,
                  receiver=receiver, acquisition=original, modeled_cohort_gates=modeled_gates(process, base))
    result["positive_unlocks_tiny"] = allowed_tiny(result, process)
    write(folder/"result.json", result)


def launch(root, label):
    references()
    with (patch.object(ordinary, "sources", sources), patch.object(ordinary, "command_for", cairo_command),
          patch.object(ordinary, "allowed_tiny", allowed_tiny)):
        ordinary.launch(root, label)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("case", choices=ordinary.CASES)
    args = cli.parse_args()
    {"launch": launch, "score": score}[args.action](args.root, args.case)
