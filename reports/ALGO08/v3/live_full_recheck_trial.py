"""Launch or review one full resident physical raw transfer of the frozen recheck."""

import argparse
import gzip
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

import full_short_run
import integrated_original_trial as original
from live_full_recheck import FIELD, SOURCES


BASE = Path("/dev/shm/leo-v3-integrated-original-02") / original.CASE
ARCHIVED = "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff"
STOCK = "e852ffcf8b887e7cab66bcb5f8ad4911caaaa9398264d3b5f351b02862b17850"
EXTRA = (*SOURCES, Path(__file__).name, "live-full-recheck-protocol.md")


def sources(prior):
    return original.sources(prior) | {
        str(original.ordinary.SCOPE / name): original.cairo.digest(HERE / name) for name in EXTRA
    }


def command(previous, output):
    return [*original.command(previous, output), "--selective-full-20ms-recheck"]


def controls():
    from empty_bootstrap import checked

    def load(name, sha):
        return json.loads(gzip.decompress(checked(HERE / "measurements" / name, sha)))

    archive = load("integrated-original.json.gz", ARCHIVED)
    candidates = {order: run[original.CASE]["result"]["document"] for order, run in archive["runs"].items()}
    stock = load("stock-raw-repeat-0016.json.gz", STOCK)
    if (set(candidates) != {"positive_first", "withholding_first"}
            or not all(row["qualified"] and row["process"]["exit_code"] == 0 for row in candidates.values())
            or not stock["qualified"] or stock["stock"]["process"]["clock"]["exit_code"]):
        raise ValueError("The exact independent timing references did not qualify")
    return candidates, stock


def launch(root):
    from empty_bootstrap import checked
    from integrated_original_entry import PNG_LIBRARY, PNG_SHA

    controls()
    original.cairo.references()
    checked(PNG_LIBRARY, PNG_SHA)
    with (patch.object(original.ordinary, "sources", sources), patch.object(original.ordinary, "command_for", command)):
        original.ordinary.launch(root, original.CASE, short_pin=full_short_run.SPARSE_EIGHT_MS_SHA)


def replay(reference, current, native):
    from anchor_exposure import bind, enroll
    from continued_cfo_trial import rebinding
    from leo.contracts.digests import canonical_digest
    from selective_full_recheck import lane, replace, shortlist
    from tools.pipeline_eval.variants.carrier_continuation import Continuation

    bind(reference, native)
    rows = reference["source"]["probes"]
    events = list(enroll(reference))
    expected, decisions = shortlist(rows, events, Continuation())
    wanted = [row for row in decisions if row["selected"]]
    receipt = current[FIELD]
    actual = receipt["calls"]
    previous = {lane(row): row for row in rows}
    if (json.loads(json.dumps(wanted)) != [item["decision"] for item in actual]
            or expected != {tuple(item["decision"]["lane"]) for item in actual}
            or any(item["base"] != previous[tuple(item["decision"]["lane"])] for item in actual)
            or any(receipt[name] for name in ("extra_ci16_retained_bytes", "extra_native_contexts",
                                             "additional_recording_traversals"))):
        raise ValueError("Live nomination did not match the complete frozen-rule replay")
    measured = {tuple(item["decision"]["lane"]): item["replacement"]["full_candidates"] for item in actual}
    replacements, proof = replace(rows, measured, Continuation())
    if json.loads(json.dumps(proof)) != [item["replacement"] for item in actual]:
        raise ValueError("Live measurement selection did not reproduce the original temporal rule")
    held = current["held_anchor_route"]
    parent = {key: val for key, val in held["receiver_recipe"].items() if key != "held_native_8ms"}
    preheld = rebinding(reference, replacements, parent)
    if canonical_digest(preheld) != held["parent_native_sha256"]:
        raise ValueError("Independent live recheck replay did not reproduce all pre-held typed factors")
    from eight_ms_held_fit import select

    projected, witness = select(preheld, parent)
    final = rebinding(projected, projected["source"]["probes"], held["receiver_recipe"])
    if (final != native or witness["choice"] != held["choice"] or canonical_digest(final) != current["native_sha256"]
            or current["detector_recipe_sha256"] != canonical_digest(held["receiver_recipe"])):
        raise ValueError("The same frozen held selection did not reproduce the entire published packet")
    return dict(typed_outputs=True, whole_record_held_selection=held["choice"],
                nominated_lanes=len(actual), original_factors=sum(len(row["candidates"]) for row in rows),
                candidates_full=sum(len(rows) for rows in measured.values()),
                replacement_nonempty=sum(bool(row["chosen"]) for row in proof),
                published_factors=held["selected"], preheld_factors=held["observed"])


def score(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from legacy_block_raw_score import snapshot
    from legacy_verify_original_trial import inspect_once
    from raw_0016_best_score import STOCK_OWNERS, STOCK_OWNERS_SHA
    from prospective_0316_solver import owner_delta
    from triage_bounds import calibration_comparison
    from visit_frame_raw_0016 import checked, read

    candidates, stock = controls()
    folder = root / original.CASE
    book, log, startup = (read(folder / name) for name in ("admission.json", "candidate-clock.json", "startup.json"))
    if (read(folder/"prediction-seal.json") != output_seal(folder) or book["command"] != log["command"]
            or book["sources"] != sources(None)):
        raise ValueError("Measured source, argv or sealed output changed")
    comparisons = {name: old["process"] for name, old in candidates.items()}
    comparisons["fresh_installed"] = stock["stock"]["process"]["clock"]
    comparisons["archived_installed"] = candidates["positive_first"]["installed"]
    process = log["clock"]
    result = dict(qualified=False, case=original.CASE, process=process, setup=book["setup"], startup=startup,
                  sources=book["sources"], process_reference=comparisons,
                  original_references=dict(integrated_sha256=ARCHIVED, fresh_installed_sha256=STOCK))
    if process["exit_code"]:
        write(folder/"result.json", result | dict(decision="failed", stderr=log.get("stderr")))
        return
    candidate = folder/"candidate"
    receiver, witness = (read(candidate/name) for name in ("unified-short-bootstrap.json", "exact-named-raw-witness.json"))
    sealed = candidates["positive_first"]
    old_native = original.native(BASE/"candidate", sealed["receiver"])
    native = original.native(candidate, receiver)
    req = book["case_source"]["request"]
    acquisition = inspect_once(candidate, req, sealed["acquisition"])
    previous_source = sealed["admission"]["case_source"]
    if (req != previous_source["request"] or acquisition["acceleration"]["artifacts"] != sealed["acquisition"]["acceleration"]["artifacts"]
            or book["raw_conditioning_bytes"] or not all(m["complete_encoded_auth"] for m in acquisition["members"])):
        raise ValueError("The measured authenticated raw scope or causal solver artifacts differ")
    recheck = replay(old_native, receiver, native)
    result.update(receiver=receiver, acquisition=acquisition, witness=witness, recheck=recheck,
                  decision=receiver["receipt"]["decision"],
                  speeds={name: {key: then[key]/process[key] for key in ("elapsed_s", "cpu_s")}
                          for name, then in comparisons.items()})
    if result["decision"] != "complete":
        write(folder/"result.json", result)
        return
    rebound = dict(req, detector=receiver["detector_recipe_sha256"], native=receiver["native_sha256"])
    science = snapshot(candidate, log, rebound, book["case_source"]["producer"],
                       verify_renderer=original.cairo.require_renderer)
    engine = acquisition["acceleration"]["solver"]
    png = engine["png_native"]
    if (engine["grid"]["projection"]["grids"] != 1 or science["positions"]["grid_points"] != 179
            or len(engine["in_flight"]) != 1 or (png["native"], png["fallback"], witness["ports"]["png"]["verified"],
                                                 witness["ports"]["png"]["reused"]) != (8, 0, 8, 8)):
        raise ValueError("Standard eagerly verified grid, path or eight PNGs were bypassed")
    fresh = stock["stock"]
    named_rows = checked(STOCK_OWNERS, STOCK_OWNERS_SHA)
    if named_rows["receipt"]["terminal_sha256"] != fresh["science"]["receipt"]["terminal_sha256"]:
        raise ValueError("The fresh installed receipt cannot bind the archived ordered owners")
    from leo.contracts.digests import canonical_digest

    old_science = sealed["science"]["published"]
    published = science["published"]
    result.update(qualified=True, science=science, geographic=calibration_comparison(
        dict(recheck=published, original_integrated=old_science, fresh_installed=fresh["science"]), original.CASE),
        owner_deltas={name: {arm: owner_delta(rows[arm], science["ordered_owners"][arm]) for arm in ("c0", "fitted_c")}
                      for name, rows in (("original_integrated", sealed["science"]["ordered_owners"]),
                                         ("fresh_installed", named_rows["selected_rows"]))},
        installed_owner_digests={arm: canonical_digest({o: n for o, n, _ in rows})
                                 for arm, rows in named_rows["selected_rows"].items()},
        reference_rf_all_owners=dict(installed=fresh["all_owned_rf_rms_hz"],
                                     integrated={arm: row["residual_rms_hz"]
                                                 for arm, row in sealed["witness"]["evidence"]["detail"]["arms"].items()}))
    if result["installed_owner_digests"] != fresh["science"]["owners"]:
        raise ValueError("Archived named rows do not match the fresh verified installed owner binding")
    write(folder/"result.json", result)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("operation", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"launch": launch, "score": score}[args.operation](args.root)
