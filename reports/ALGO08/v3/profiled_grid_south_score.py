"""Score the proof launch and archived stock control for each original South offer."""

import argparse
import json
import sys

from . import profiled_grid_0138_score as rules
from . import profiled_grid_south as south

POINTS = {"containing": 158, "omitted": 137}
CAPTURES = {"containing": 314, "omitted": 272}
SCORER_PIN = "f6ac0259f3f4b1cd75275803cdad43e2eeb50a06ab97b2941007c64e53bd88d7"


def readback(offer, area, archive_seal, clock):
    prior = south.prior
    freeze = prior.read(prior.checked(south.PLAN, south.PLAN_PIN))
    official = freeze["proposed_saved_pair"]
    sys.path.insert(0, str(south.RUNTIME / "reports/ALGO08/v3"))
    verifier = prior.module("_frozen_south_scoring", prior.checked(
        south.CORE.with_name("frozen_south_saved_score.py"), SCORER_PIN))
    authority = {key: official[key] for key in ("causal_cutoff_utc_ns", "session_id")}
    authority.update(window_count=official["issued_stereo_visits"],
                     raw_authority_sha256="sha256:" + official["raw_authority_sha256"],
                     archive_sha256="sha256:" + official["causal_archive_sha256"])
    mode = f"{offer}:integrated"
    stock = south.STOCK / mode.replace(":", "-")
    paths = {p: s for p, s in archive_seal.items() if p.startswith(stock.name + "/")}
    if not paths:
        raise ValueError("No ordinary publication in the archived closure")
    for relative, expected in paths.items():
        prior.checked(south.STOCK / relative, expected)
    offer_rec = official["offers"][offer]
    geometry = prior.read(prior.checked(south.PLAN.parent / offer_rec["path"], offer_rec["sha256"]))
    native = "sha256:" + official["packets"]["integrated"]["sha256"]
    stock_evidence = verifier.publication(
        stock, prior.read(stock.with_suffix(".clock.json")), mode, geometry, authority, native)
    proof_evidence = verifier.publication(area / "publication", clock, mode, geometry, authority, native)
    return stock_evidence, proof_evidence


def compare(offer, control, proof, activity):
    stock_grid, proof_grid = control["grid"], proof["grid"]
    grid = rules.compare_maps(stock_grid, proof_grid, expected_points=POINTS[offer])
    route = [item["charted_witness"]["history"] for item in (control, proof)]
    exterior = (rules.without_clocks(route[0]["boundary_checks"])
                == rules.without_clocks(route[1]["boundary_checks"]))
    evidence = {
        "terminal_equal": control["terminal"] == proof["terminal"],
        "owners_equal": control["ordered_owners"] == proof["ordered_owners"],
        "path_equal": rules.without_image(control["path"]) == rules.without_image(proof["path"]),
        "route_equal": rules.routes_agree(*route), "exterior_equal": exterior,
        "grid_pass": rules.qualified_map(grid), "points": POINTS[offer],
        "seven_images_equal": all(control["figures"][name] == proof["figures"][name]
                                   for name in control["figures"] if name != "position"),
        "expected_checked_calls": activity["clocks"].get("calls") == CAPTURES[offer],
        "activated": bool(activity["activity"].get("profiled_completed")),
    }
    return evidence, grid


def score(offer):
    prior = south.prior
    area = south.ROOT / offer
    clock = area / "clock.json"
    attempts = {p.name: prior.read(p) for p in area.glob("watch-*.json")}
    if not clock.exists():
        return {"offer": offer, "status": "no_numerical_launch", "watches": attempts}
    clock = prior.read(clock)
    result = {"offer": offer, "clock": clock, "watches": attempts,
              "status": "completed" if not clock["exit_code"] else clock["reason"]}
    if clock["exit_code"]:
        result["available_files"] = sorted(str(p.relative_to(area)) for p in area.rglob("*.json"))
        result["stderr"] = (area / "worker.stderr").read_text()[-3000:]
        result["accept"] = False
        return result
    seal = prior.read(prior.checked(south.STOCK / "prediction-seal.json", south.STOCK_SEAL))
    activity = prior.read(area / "callback-clocks.json")
    result["capture"] = activity
    try:
        before, after = readback(offer, area, seal, clock)
        evidence, grid = compare(offer, before, after, activity)
    except (ValueError, KeyError, OSError) as error:
        result.update(accept=False, verification_error=f"{type(error).__name__}: {error}")
        result["available_files"] = sorted(str(p.relative_to(area)) for p in area.rglob("*.json"))
        return result
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    ids = [r["receipt"]["run_id"] for r in (before, after)]
    files = (south.STOCK / f"{offer}-integrated", area / "publication")
    bodies = [FastStandardAnalysisStore(folder).artifact(run, "position")
              for folder, run in zip(files, ids, strict=True)]
    image = rules.compare_image(*bodies)
    guard, = after["charted_witness"]["history"]["boundary_checks"]
    result.update(accept=all(v for k, v in evidence.items() if k != "points")
                   and image["changed_fraction"] <= .01 and image["mean_absolute_channel"] <= .5,
                  verified=evidence, grid=grid, position_image=image, guard=rules.without_clocks(guard),
                  stock_terminal_sha256=before["receipt"]["terminal_sha256"],
                  proof_terminal_sha256=after["receipt"]["terminal_sha256"],
                  decision=after["receipt"]["decision"], arms=after["terminal"]["arms"],
                  posterior=after["receipt"]["posterior_grid_handoff"],
                  publication_products=after["figures"], scope="saved proof versus archived ordinary")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("offer", choices=south.OFFERS)
    parsed = parser.parse_args()
    print(json.dumps(score(parsed.offer), indent=2, sort_keys=True, allow_nan=False))
