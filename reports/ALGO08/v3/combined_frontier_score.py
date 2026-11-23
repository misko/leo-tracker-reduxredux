"""Score the paid original-input pair after the two processes exit."""

import argparse
import json
from pathlib import Path

from aperture_score import PHYSICAL, distance_km
from aperture_trial import ARMS, read
from combined_frontier_run import BLOCK_SHA, HERE, PREFETCH_FILES, verify
from joint_publication import artifacts
from leo.contracts.digests import canonical_digest
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.pipeline_eval.qualification.paired_publication import evidence
from weak_combined_score import decision


def verify_callbacks(ingress, regional):
    if (ingress["submitted"] < 1 or ingress["hits"] < 1 or ingress["hit_bytes"] <= 0
            or regional["block_calls"] < 1 or regional["block_positions"] != regional["block_calls"] * 4
            or regional["consumed"] != regional["block_positions"] + regional["scalar_positions"]):
        raise ValueError("The expected prefetch and guaranteed block paths did not execute")


def score(root):
    frozen = HERE / "measurements/weak-combined-raw.json"
    verify(frozen, "a704861e37e40e7364fbf97bcb74e98bb9c701ca474c12821e8ed7df86cab233")
    archived = read(frozen)
    binding = read(root / "binding.json")
    if binding["inventory"] != archived["binding"]["inventory"] or binding["request"] != archived["binding"]["request"]:
        raise ValueError("Released source or offer differs from the enrolled DS30-0016 pair")
    research = read(root / "candidate/joint-research-receipt.json")
    composition = read(root / "candidate/combined-frontier.json")
    if composition["block_sha256"] != BLOCK_SHA or composition["prefetch_sources"] != PREFETCH_FILES:
        raise ValueError("Composition differs from the enrolled build")
    proof = research["solve"]["geographic_projector"]
    verify_callbacks(composition["prefetch"], proof)
    rows, opportunities = {}, []
    survey, = [row["reference"] for row in read(PHYSICAL)["cases"] if row["dataset_label"] == "DS30-0016"
               and row["authority_eligible"]]
    truth = [survey[k] for k in ("latitude_deg", "longitude_deg")]
    for arm in ("stock", "candidate"):
        folder = root / arm
        original = archived["runs"][arm]
        clock = read(root / f"{arm}-clock.json")
        receipt = (json.loads((root / "stock-stdout").read_text().splitlines()[-1]) if arm == "stock"
                   else research["receipt"])
        observed = evidence(folder, receipt, 0, read_only=True)
        figures = artifacts(folder, receipt)["images"]
        grid = FastStandardAnalysisStore(folder).position_grid(receipt["run_id"])
        native_path, = (folder / "fast-scan-automatic-work").glob("*/detections.json")
        native = read(native_path)
        opportunities.append(canonical_digest([{k: v for k, v in row.items() if k != "candidates"}
                                                for row in native["source"]["probes"]]))
        checks = dict(raw=observed["raw_authority"] == binding["request"]["raw_authority"],
                      region=receipt["region"] == binding["request"]["offered_region"],
                      detector=canonical_digest(native) == original["native_sha256"],
                      terminal=receipt["terminal_sha256"] == original["terminal_sha256"],
                      arms=observed["arms"] == original["arms"], owners=observed["owners"] == original["owners"],
                      grid_and_path=observed["scientific_digests"] == original["scientific_digests"],
                      complete_grid=grid["complete"] and grid["evaluated_points"] == 179,
                      all_images=canonical_digest(figures) == canonical_digest(original["images"]) and len(figures) == 8,
                      counts=receipt["counts"] == original["counts"], exit=clock["status"] == 0)
        if not all(checks.values()):
            raise ValueError(f"{arm} science or source differs: {checks}")
        errors = {name: distance_km(observed["arms"][name]["latlon"], truth) for name in ARMS}
        rows[arm] = dict(checks=checks, clock=clock, cache=read(root / f"{arm}-before.json"), arms=observed["arms"],
                         errors_km=errors, images=figures, terminal=receipt["terminal_sha256"], counts=receipt["counts"])
    if opportunities[0] != opportunities[1]:
        raise ValueError("The receiver opportunities differ between builds")
    return dict(runs=rows, composition=composition, solve=research["solve"], opportunities=opportunities[0],
                receiver=read(root / "candidate/full-short-recipe.json")["receiver_audit"],
                binding=binding, decision=decision(rows["stock"]["clock"]["elapsed_s"],
                rows["candidate"]["clock"]["elapsed_s"], {k: v["errors_km"] for k, v in rows.items()}, complete=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    print(json.dumps(score(parser.parse_args().root), indent=2, allow_nan=False))
