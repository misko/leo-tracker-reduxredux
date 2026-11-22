"""Refit both raw-pair solvers on the preregistered public north/south faces."""
import argparse
import json
from math import cos, radians, isclose
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.storage.fast_scan import immutable_json
from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
from tools.pipeline_eval.scoring import distance_km
from .replay_region_offers import replay


HERE = Path(__file__).resolve().parent
SPEC = "sha256:23fadeb79c76c343760dc3fb107f7dfb170b0ba4eec22a4dc3df244c2187cf24"


def offers(truth, sign):
    result = {}
    for label, north in (("inside", 12.4), ("outside", 12.6)):
        lat = truth[0] - sign * north / 111.0
        lon = truth[1] - sign * 5.0 / (111.32 * cos(radians(lat)))
        offer = Algo08Region((lat, lon), 25.).document()
        if not isclose(face_clearance_km(offer, truth), 12.5 - north, abs_tol=1e-9):
            raise ValueError("Constructed offer differs from its assigned clearance")
        result[label] = offer
    return result


def run(bench, output):
    frozen = bench / "integration-spectral-vectors-terminal-veto"
    output.mkdir()
    answers = json.loads((HERE.parent / "regional-release/scoring-key.json").read_bytes())["answers"]
    scored = {}
    for site, sign in (("north", 1), ("south", -1)):
        key = f"spectral-terminal-{site}-inside"
        pair = bench / key / "pair.json"
        if pair.read_bytes() != (HERE / "measurements" / f"{key}.json").read_bytes():
            raise ValueError("Raw-pair receipt differs from the archived publication")
        recording = Path(json.loads(pair.read_bytes())["recording"]).name
        truth, = {tuple(row["truth"]) for row in answers.values() if row["recording"] == recording}
        regions = offers(truth, sign)
        paths = []
        for label, region in regions.items():
            path = output / f"{site}-{label}.json"
            immutable_json(path, region)
            paths.append(path)
        for method in ("baseline", "candidate"):
            dest = output / f"{site}-{method}.json"
            replay(pair, frozen, SPEC, paths, dest, method=method)
            data = json.loads(dest.read_bytes())
            rows = {}
            for label, row in zip(("anchor", *regions), data["results"], strict=True):
                region, result = row["region"], row["result"]
                if label != "anchor" and region != regions[label]:
                    raise ValueError("Prediction region differs from its assignment")
                rows[label] = dict(region=region, truth_clearance_km=face_clearance_km(region, truth),
                                   status=result["status"], reason=result.get("reason"),
                                   arms=result["arms"], owners=result.get("owners"), associated=result.get("associated"),
                                   error_km={k: distance_km(v["latlon"], truth) for k, v in result["arms"].items()},
                                   solver_cpu_s=result["solver_cpu_s"])
            scored[f"{site}-{method}"] = {k: data[k] for k in ("pair_sha256", "native_sha256", "archive")}
            scored[f"{site}-{method}"]["offers"] = rows
    immutable_json(output / "scores.json", dict(specification=SPEC, sites=scored))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bench", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.bench, args.output)
