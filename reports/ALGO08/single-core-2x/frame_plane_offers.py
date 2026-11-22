"""Move a public search offer with its raw receiver output held fixed."""

import argparse
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification.paired_publication import archive_identity
from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
from tools.pipeline_eval.scoring import distance_km

from .regional_exterior_veto_trial import PINS, saved_offers
from .residual_attribution_trial import saved_native
from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import KEYS, evidence_digests, solve, write


def shifted_offers(site, original, offers):
    if site not in ("north", "south"):
        raise ValueError("Expected a public northern or southern development site")
    if Algo08Region.parse(original) != Algo08Region.parse(offers[f"{site}-edge"]["offer"]):
        raise ValueError("Recorded search and screening regions differ from the public near-inside offer")
    return {name: offers[name]["offer"] for name in (f"{site}-mirror-outside", f"{site}-far")}


def run(pair_path, bundle, scoring_key, site="north"):
    pair = read(pair_path)
    spec = pair["candidate_specification_digest"]
    require_spec(bundle, spec)
    if pair["candidate_specification"] != read(bundle / "spec.json"):
        raise ValueError("Saved publication uses another solver or receiver")
    native = saved_native(pair_path, "candidate", pair["runs"]["candidate"])
    archive = Path(pair["archive"]["root"])
    original = pair["runs"]["candidate"]["receipt"]["region"]
    offers = shifted_offers(site, original, saved_offers())
    if archive_identity(archive) != pair["archive"]:
        raise ValueError("Orbit catalogue differs from the raw publication")
    results = {}
    for name, offer in offers.items():
        result = solve(bundle, native, offer, archive)
        results[name] = {k: result.get(k) for k in (*KEYS, "solver_cpu_s", "solver_wall_s")}
        results[name].update(offer=offer, science=evidence_digests(result))
    if archive_identity(archive) != pair["archive"]:
        raise ValueError("Orbit catalogue changed during replay")
    recording = Path(pair["recording"]).name
    truths = {tuple(r["truth"]) for r in read(scoring_key)["answers"].values()
              if r["recording"] == recording}
    if len(truths) != 1:
        raise ValueError("Expected one released receiver reference")
    truth, = truths
    for row in results.values():
        row["truth_clearance_km"] = face_clearance_km(row["offer"], truth)
        row["error_km"] = {arm: distance_km(v["latlon"], truth) for arm, v in row["arms"].items()}
    return dict(pair_sha256=digest(pair_path), specification=spec, archive=pair["archive"],
                offer_sources=PINS, native_sha256=canonical_digest(native), results=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("pair", "bundle", "key", "output"):
        parser.add_argument(key, type=Path)
    parser.add_argument("--site", choices=("north", "south"), default="north")
    args = parser.parse_args()
    write(args.output, run(args.pair, args.bundle, args.key, args.site))
