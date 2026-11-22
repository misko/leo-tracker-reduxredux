"""Replay four public saved cases with a wider search and the original membership gate."""

import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess

from leo.analysis.localization_v3.region import SearchRegion
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest

from .covariance_transfer_trial import ARMS, RELEASE


WORKER = Path(__file__).with_name("covariance_transfer_trial.py").resolve()
CHECKOUT = WORKER.parents[3]
SCORING = WORKER.parents[1] / "regional-release/scoring-key.json"


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x") as stream:
        print(json.dumps(value, indent=2, allow_nan=False), file=stream)


def require_digest(path, digest):
    if sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f"Pinned source changed: {path}")


def expanded_offer(original):
    offer = Algo08Region.parse(original)
    return Algo08Region(offer.center, 2 * offer.width_km, offer.screen_center).document()


def clearance(offer, point):
    if (not isinstance(point, (list, tuple)) or len(point) != 2
            or any(not isinstance(value, (float, int)) or not math.isfinite(value) for value in point)):
        return None
    region = SearchRegion(tuple(offer["center"]), width_km=offer["width_km"])
    half = region.half_width_km
    low, high = region.latlon((-half, -half)), region.latlon((half, half))
    latitude, longitude = point
    scale = 111.32 * math.cos(math.radians(region.center[0]))
    return float(min(
        (latitude - low[0]) * 111.0, (high[0] - latitude) * 111.0,
        (longitude - low[1]) * scale, (high[1] - longitude) * scale,
    ))


def membership(result, original):
    margins = {arm: clearance(original, result.get("arms", {}).get(arm, {}).get("latlon"))
               for arm in ARMS}
    inside = {arm: margin is not None and margin >= 0 for arm, margin in margins.items()}
    publication = "unresolved"
    if result["status"] in ("ok", "withheld"):
        publication = "published" if result["status"] == "ok" and all(inside.values()) else "withheld"
    return dict(publication=publication, inside_original=inside, original_clearance_km=margins)


def run(plan_path, frozen, output):
    from tools.pipeline_eval.qualification.paired_publication import archive_identity, verify_sources

    plan = read(plan_path)
    cases = plan["cases"]
    if len(cases) != 4 or len({row["case"] for row in cases}) != 4:
        raise ValueError("Expected four distinct registered saved solves")
    spec_path = frozen / "spec.json"
    spec = read(spec_path)
    if canonical_digest(spec) != plan["candidate_specification_digest"]:
        raise ValueError("Expected the registered frozen solver")
    verify_sources(frozen / "reports/ALGO08/single-core-2x/run-candidate", spec["sources"])
    require_digest(WORKER, plan["worker_sha256"])
    for row in cases:
        source = Path(row["source_offer"])
        require_digest(source, row["source_offer_sha256"])
        original = Algo08Region.parse(read(source)).document()
        if original != row["original"] or expanded_offer(original) != row["expanded"]:
            raise ValueError("Offer differs from the registered geometry")
        require_digest(Path(row["native"]), row["native_sha256"])
        if archive_identity(Path(row["archive"]["root"])) != row["archive"]:
            raise ValueError("Causal archive differs from the registered archive")

    output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE",
                "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    env.update(PYTHONPATH=f"{frozen}:{RELEASE / 'src'}:{RELEASE}",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    command = [str(RELEASE / "venv/bin/python"), "-BPs", str(WORKER), "worker"]
    for row in cases:
        label = row["case"]
        offer = output / f"{label}-expanded.json"
        result = output / f"{label}-fit.json"
        write(offer, row["expanded"])
        paths = [row["native"], row["archive"]["root"], offer, result, spec_path]
        subprocess.run([*command, *map(str, paths)], env=env, check=True, timeout=110)
    for row in cases:
        if archive_identity(Path(row["archive"]["root"])) != row["archive"]:
            raise ValueError("Causal archive changed during the replay")


def score(plan_path, results, output):
    from tools.pipeline_eval.scoring import distance_km

    plan = read(plan_path)
    # Read every prediction before opening the public scoring references.
    predictions = [read(results / f"{row['case']}-fit.json") for row in plan["cases"]]
    require_digest(SCORING, plan["north_scoring_sha256"])
    north, = {tuple(value["truth"]) for value in read(SCORING)["answers"].values()
              if value["recording"] == plan["north_waveform"]}
    rows = []
    for case, result in zip(plan["cases"], predictions, strict=True):
        pin = case["baseline"]
        prior = CHECKOUT / pin["receipt"]
        require_digest(prior, pin["sha256"])
        row = read(prior)[pin["key"]][pin["index"]]
        original = case["original"]
        if pin["key"] == "rows":
            reference = row["reference_latlon"]
            baseline = row["builds"]["covariance"]
            offered = row["offer"]
        else:
            reference, baseline, offered = north, row["result"], row["region"]
        if original != offered or read(results / f"{case['case']}-expanded.json") != case["expanded"]:
            raise ValueError("Prediction or baseline used a different offer")
        fields = ("status", "reason", "orbit_policy", "arms", "owners", "associated", "regional_bound_guard")
        baseline, result = ({key: fit[key] for key in fields if key in fit} for fit in (baseline, result))
        for fit in (baseline, result):
            for arm in fit.get("arms", {}).values():
                arm["horizontal_error_km"] = distance_km(arm.get("latlon"), reference)
        truth_clearance = clearance(original, reference)
        rows.append(dict(
            case=case["case"], original=original, expanded=case["expanded"],
            native_sha256=case["native_sha256"], reference_latlon=reference,
            reference_clearance_km=truth_clearance, reference_inside_original=truth_clearance >= 0,
            reference_inside_expanded=clearance(case["expanded"], reference) >= 0,
            baseline=baseline, baseline_membership=membership(baseline, original),
            expanded_fit=result, decision=membership(result, original),
            owner_maps_match=(baseline.get("owners") == result.get("owners")),
            expanded_fit_sha256=sha256((results / f"{case['case']}-fit.json").read_bytes()).hexdigest(),
        ))
    write(output, dict(plan_sha256=sha256(plan_path.read_bytes()).hexdigest(),
                       candidate_specification_digest=plan["candidate_specification_digest"], cases=rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "score"))
    parser.add_argument("plan", type=Path)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    operation = run if args.action == "run" else score
    operation(args.plan, args.input, args.output)
