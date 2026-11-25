"""Verify sealed 0138 publications and the entire pair of standard grid maps."""

import argparse
from io import BytesIO
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from scipy.spatial import Delaunay

from . import profiled_grid_0138 as trial
from .grid_control_variate import LEVELS, contour_error, contour_samples, mesh_edges, modes

ARMS = ("c0", "fitted_c")


def without_image(document):
    return dict(document, binding={k: v for k, v in document["binding"].items() if k != "position_png_sha256"})


def compare_maps(stock, candidate):
    def layout(document):
        return {k: v for k, v in without_image(document).items() if k not in {"elapsed_seconds", "points"}}

    old, new = stock["points"], candidate["points"]
    if (layout(stock) != layout(candidate) or not stock["complete"] or not stock["matched_c_grid"]
            or len(old) != 179 or len(new) != 179):
        raise ValueError("Changed complete standard grid layout")
    for a, b in zip(old, new, strict=True):
        points = lambda row: {k: v for k, v in row.items() if k != "scores"}
        if points(a) != points(b) or a["scores"].keys() != b["scores"].keys():
            raise ValueError("Changed grid coordinate order, score coverage or failure")
    xy = np.asarray([(r["east_km"], r["north_km"]) for r in old])
    triangles = Delaunay(xy).simplices
    edges = mesh_edges(triangles)
    result = {}
    for arm in ARMS:
        a, b = (np.array([r["scores"].get(arm, np.nan) for r in items], dtype=float) for items in (old, new))
        finite = np.isfinite(a)
        if not finite.any() or not np.array_equal(finite, np.isfinite(b)):
            raise ValueError("Changed finite map domain")
        error = np.abs(a[finite]-b[finite])
        a, b = a-np.nanmin(a), b-np.nanmin(b)
        same_minima = np.array_equal(a == 0, b == 0)
        low = lambda values: {i for i in modes(values, edges) if values[i] <= LEVELS[-1]}
        contours = []
        for level in LEVELS:
            distance = contour_error(contour_samples(xy, a, level, triangles),
                                     contour_samples(xy, b, level, triangles))
            contours.append(dict(level=level, distance_km=distance,
                                 changed_nodes=int(np.count_nonzero((a <= level) != (b <= level)))))
        result[arm] = dict(max_abs=float(error.max()), rms=float(np.sqrt(np.mean(error**2))),
                           exact_scores=bool(np.all(error == 0)), same_minima=bool(same_minima),
                           same_low_modes=low(a) == low(b), contours=contours)
    return result


def qualified_map(result):
    return all(v["max_abs"] <= 0.005 and v["same_minima"] and v["same_low_modes"]
               and all(c["changed_nodes"] == 0 and c["distance_km"] is not None and c["distance_km"] <= .025
                       for c in v["contours"]) for v in result.values())


def position_image(store, verified):
    run = verified["worker"]["receipt"]["run_id"]
    pin = verified["products"]["images"]["position"]["sha256"]
    return store.artifact(run, "position", pin)


def compare_image(old, new):
    def decoded(contents):
        with Image.open(BytesIO(contents)) as image:
            return (image.mode, image.size, dict(image.info)), np.asarray(image.convert("RGBA"), dtype=np.int16)

    meta, a = decoded(old)
    after, b = decoded(new)
    if meta != after:
        raise ValueError("Changed position image mode, dimensions or metadata")
    diff = np.abs(a-b)
    return dict(encoded_equal=old == new, decoded_equal=not diff.any(),
                changed_fraction=float(np.any(diff != 0, axis=-1).mean()), mean_absolute_channel=float(diff.mean()))


def inspect(root, clock, request):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    output = root/"candidate"
    worker = trial.read(output/"worker.json")
    research = trial.read(output/"joint-research-receipt.json")
    receipt = worker["receipt"]
    store = FastStandardAnalysisStore(output)
    run = receipt["run_id"]
    terminal = trial.read(output/"fast-scan-automatic-work"/run/"terminal.json")
    packet, = (output/"fast-scan-automatic-work").glob("*/detections.json")
    detail, grid, path = store.detail(run), store.position_grid(run), store.position_path(run)
    figures = artifacts(output, receipt)
    if (clock["exit_code"] or not worker["no_waveform"] or worker["handoffs"] != 1
            or research["receipt"] != receipt or receipt["decision"] != "complete"
            or trial.digest(packet) != request["native_sha256"]
            or terminal["native_sha256"] != "sha256:"+request["native_sha256"]
            or receipt["session_id"] != request["session"] or detail["raw_authority"] != request["raw_authority"]
            or canonical_digest(terminal) != receipt["terminal_sha256"] or not grid["complete"]
            or grid["evaluated_points"] != 179 or not grid["matched_c_grid"]
            or any(doc["binding"]["position_png_sha256"] != figures["images"]["position"]["sha256"]
                   for doc in (grid, path))):
        raise ValueError("Expected the verified original packet, terminal and complete standard store")
    science = dict(raw_authority=detail["raw_authority"], arms=detail["arms"], scientific_digests={
                   "grid": canonical_digest({k: v for k, v in grid.items() if k != "elapsed_seconds"}),
                   "path": canonical_digest(path)})
    return dict(worker=worker, science=science, terminal=terminal, products=figures, sample=grid, path=path,
                rows=research["selected_rows"])


def without_clocks(value):
    if isinstance(value, dict):
        return {k: without_clocks(v) for k, v in value.items() if k not in {"cpu_ns", "elapsed_ns", "cpu_s", "elapsed_s"}}
    if isinstance(value, list):
        return [without_clocks(v) for v in value]
    return value


def routes_agree(original, candidate):
    def decision(route):
        return dict(choice=without_clocks(route["choice"]), calls=route["inference_calls"],
                    attempts=[(a["decision"], without_clocks(a["exterior"])) for a in route["lean_attempts"]],
                    exterior=without_clocks(route["exterior_handoff"]))

    return decision(original) == decision(candidate)


def score(cell):
    sys.path[:0] = [str(trial.ARCHIVED/"reports/ALGO08/v3"), str(trial.RELEASE/"src"), str(trial.RELEASE),
                   str(trial.PAYLOAD), str(trial.ARCHIVED)]
    from exact_named_route_score import parity
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    root = trial.ROOT/cell
    request = trial.read(trial.checked(trial.STAGE/"request.json", trial.REQUEST_PIN))
    timed = trial.read(root/"clock.json")
    historical = trial.read(trial.checked(trial.HISTORICAL/"score.json", trial.HISTORICAL_SCORE_PIN))
    baseline = trial.HISTORICAL if cell == "ordinary" else trial.ROOT/"ordinary"
    control_clock = historical["clock"] if cell == "ordinary" else trial.read(baseline/"clock.json")
    stock, after = inspect(baseline, control_clock, request), inspect(root, timed, request)
    original_route, = trial.read(baseline/"risk-route.json")["solves"]
    candidate_route, = trial.read(root/"risk-route.json")["solves"]
    a, = original_route["lean_attempts"]
    b, = candidate_route["lean_attempts"]
    parity_result = parity(stock, after)
    routes_match = routes_agree(original_route, candidate_route)
    layout = compare_maps(stock["sample"], after["sample"])
    path = without_image(stock["path"]) == without_image(after["path"])
    unchanged = stock["products"]["images"].keys() == after["products"]["images"].keys() and all(
        stock["products"]["images"][k] == after["products"]["images"][k]
        for k in after["products"]["images"] if k != "position")
    image = compare_image(*(position_image(FastStandardAnalysisStore(p/"candidate"), v)
                            for p, v in ((baseline, stock), (root, after))))
    capture = trial.read(root/"callback-clocks.json")
    audit = trial.read(root/"grid-audit.json")
    capture_ok = (capture["clocks"]["calls"] == 356
                  and (capture["activity"].get("profiled_completed", 0) > 0 if cell == "profiled"
                       else not capture["activity"]))
    if cell == "ordinary":
        images_grid = image["encoded_equal"] and all(v["exact_scores"] for v in layout.values())
    else:
        images_grid = qualified_map(layout) and image["changed_fraction"] <= .01 and image["mean_absolute_channel"] <= .5
    accept = (all(v for k, v in parity_result.items() if k not in {"layout", "eight_pngs"}) and path and routes_match
              and unchanged and images_grid and capture_ok)
    answer = dict(accept=accept, clock_sha256=trial.digest(root/"clock.json"), cells=(str(baseline), str(root)),
                  clock=timed, control_clock=control_clock, historical_clock=historical["clock"],
                  parity=parity_result, route_equal=routes_match, ordinary_path_equal=path, seven_images_exact=unchanged,
                  routes={k: dict(choice=v["choice"]["route"], inference_calls=v["inference_calls"],
                                  attempts=[a["decision"] for a in v["lean_attempts"]])
                          for k, v in (("control", original_route), ("candidate", candidate_route))},
                  map=layout, position_image=image, callback=capture, grid_audit=audit,
                  evidence={"control": a["standard_evidence_clocks"], "candidate": b["standard_evidence_clocks"]},
                  fixed_and_fitted=after["terminal"]["arms"], owner_counts={k:len(v) for k,v in after["rows"].items()})
    trial.write(root/"verified.json", answer)
    return answer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cell", choices=trial.CELLS)
    arguments = parser.parse_args()
    sys.exit(0 if score(arguments.cell)["accept"] else 1)
