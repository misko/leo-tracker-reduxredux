"""Verify the one candidate publication and compare its cost with the sealed pair."""

import argparse
import json
from pathlib import Path
import sys

from reports.ALGO08.v3.ds30_0359_cairo_saved import BASE, JOB_PIN, PRIOR_PIN, PROTOCOL, READY, SCENE, digest, read


def speed(clocks, setup, seal_export):
    ratios = {}
    for metric in ("elapsed_s", "cpu_s"):
        named, ordinary, measured = (clocks[mode][metric] for mode in ("installed", "ordinary", "candidate"))
        charged = measured + setup[metric]
        ratios[metric] = dict(installed=named, ordinary=ordinary, candidate=measured, candidate_with_setup=charged,
                              child_saved_vs_ordinary=ordinary-measured, remaining_to_half=measured - named/2,
                              through_exit_speedup=named/measured, setup_charged_speedup=named/charged,
                              scene_export=seal_export[metric])
    return ratios


def image_match(original, current):
    return {name: {"sha256": item["sha256"] == current[name]["sha256"],
                   "rgba_sha256": item["rgba_sha256"] == current[name]["rgba_sha256"],
                   "size": tuple(item["size"]) == tuple(current[name]["size"])} for name, item in original.items()}


def score(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from empty_bootstrap import checked, clock, now
    from history_risk_cairo_physical import clean
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import inspect
    from publication_media_checks import verify_position_sidecars
    from reports.ALGO08.v3.ds30_0359_cairo_visual import evidence as visualize

    began = now()
    before = json.loads(checked(BASE / "result.json", PRIOR_PIN))
    admission, paid = read(root / "admission.json"), read(root / "routed/clock.json")
    seal = root / "prediction-seal.json"
    if read(seal) != output_seal(root) or admission["protocol_sha256"] != digest(PROTOCOL):
        raise ValueError("The original paid candidate predictions changed")
    clocks = dict(installed=before["jobs"]["installed"]["clock"], ordinary=before["jobs"]["routed"]["clock"], candidate=paid)
    result = dict(case="DS30-0359", prior_case_exposure=True, new_candidate_children=1, original_reads=0,
                  candidate_prediction_sha256=digest(seal), admission=admission, clocks=clocks, qualified=False)
    if paid["exit_code"]:
        write(root / "result.json", result | {"status": "worker_failed"})
        return

    bound, req = load_job(READY / "job.json", JOB_PIN)
    directory = root / "routed/candidate"
    old = before["jobs"]["routed"]["publication"]
    prior_installed = before["jobs"]["installed"]["publication"]
    receipt = read(directory / "worker.json")["receipt"]
    published = inspect(directory, "0359-cairo", receipt, paid, req, native_sha=req["native_sha256"],
                        windows=bound["issued"], admitted=bound["admitted"], audit_name="worker.json")
    baseline_ports = before["candidate_traces"]["ports"]
    ports = read(directory / "ports.json")
    layout = read(root / "routed/render-usage.json")
    native = read(root / "publication-ports.json")
    run = receipt["run_id"]
    images = old["figures"], published["figures"]
    scopes = BASE / "routed/candidate", directory
    try:
        sidecars = verify_position_sidecars(*scopes, run, *images)
    except ValueError as error:
        sidecars = {"error": str(error)}
    same = image_match(*images)
    visual_names = {name for name in same if name.endswith(("-all", "-unassociated"))}
    checks = dict(
        exact_terminal=published["terminal"] == old["terminal"] == prior_installed["terminal"],
        exact_arms=published["science"]["arms"] == old["science"]["arms"] == prior_installed["science"]["arms"],
        exact_ordered_owners=published["selected_rows"] == old["selected_rows"] == prior_installed["selected_rows"]
        and all(len(rows) == 3640 for rows in published["selected_rows"].values()),
        exact_graph=clean(ports["graph"]) == clean(baseline_ports["graph"])
        and published["worker"]["graph_proof"] == old["worker"]["graph_proof"],
        complete_grid_and_path=set(sidecars) == {"grid", "path"} and published["sidecars"] == old["sidecars"],
        unchanged_pngs=len(same) == 8 and len(visual_names) == 4 and all(all(same[name].values()) for name in same.keys()-visual_names),
        six_cairo=(layout.get("native_orbit_figures"), layout.get("native_residual_figures"),
                   layout.get("position_figures"), layout.get("track_figures")) == (4, 2, 1, 1)
        and not any("fallback" in key for key in layout),
        native_png=(native["native_png"]["native"], native["native_png"]["fallback"], ports["png"]["verified"],
                    ports["png"]["reused"], ports["png"]["fallbacks"]) == (8, 0, 8, 8, 0),
    )
    orbit = {"qualified": False, "reason": "The candidate used an ordinary orbit fallback"}
    if native["live_orbit_calls"] == 1 and checks["six_cairo"]:
        capture = root / SCENE
        try:
            orbit = visualize(capture, tuple(FastStandardAnalysisStore(path) for path in scopes), run, images)
        except (ValueError, KeyError) as error:
            orbit = {"qualified": False, "reason": str(error)}
    checks["visual"] = orbit["qualified"]
    additional = {metric: admission["setup"][metric] + admission["smoke"]["clock"][metric]
                  for metric in ("elapsed_s", "cpu_s")}
    paid_trace = read(directory / "joint-research-receipt.json")
    write(root / "result.json", result | dict(qualified=all(checks.values()), checks=checks, publication=published,
          setup=additional, time=speed(clocks, additional, native["scene_export"]), same_png=same, visual=orbit,
          graphics=layout, png_native=native, png_cache=ports["png"], graph=ports["graph"], sidecars=sidecars,
          base_geographic=before["geographic"], readback=clock(began), prior_clocks=before["publication_clocks"],
          publication_timing={k: paid_trace[k] for k in ("publication_cpu_s", "publication_elapsed_s", "solve")},
          actual_route=read(root / "routed/risk-route.json"), grid=read(root / "routed/combined-grid.json")))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
