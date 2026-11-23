"""Verify and score the single archived dense full-short raw publication."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_trial import ARMS, read, write
from dense_full_short_raw import COUNTS, GEOGRAPHIC_SHA, HERE, ISSUED, PAIR, PAIR_SHA, archived_case, checked
from full_short_physical_score import classified
from full_short_raw import GRAPH, RECIPE_SHA, recipe


OWNER_SHA = "9ab0632563cc2ceacd043569956ef7fa1dfb9e24f26de370df57b8a19681221f"


def probe_metadata(stock, candidate):
    return (len(stock) == len(candidate) == 2 * COUNTS["processed"]
            and all({k: v for k, v in left.items() if k != "candidates"} ==
                    {k: v for k, v in right.items() if k != "candidates"}
                    for left, right in zip(stock, candidate, strict=True)))


def score(output, destination):
    from aperture_score import PHYSICAL, distance_km
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from optimized_full_catalogue_trial import figures
    from signed_0374_transfer import owner_changes, verify_stock
    from survey_owner_diagnostic import exact_owners
    from tools.pipeline_eval.qualification.paired_publication import evidence

    pair = archived_case()
    control = pair["runs"]["baseline"]
    witness = control["witnesses"]
    binding, process = map(read, (output / "binding.json", output / "process.json"))
    if (process["status"] != 0 or binding["pair_sha256"] != PAIR_SHA or binding["archive"] != pair["archive"]
            or binding["inventory"] != witness["input_manifest_sha256"]
            or binding["authority"] != witness["raw_authority"]):
        raise ValueError("The single candidate must exit before scoring its original bound recording")
    for name, pin in binding["source_sha256"].items():
        checked(HERE / name, pin)
    root, archived = output / "publication", PAIR.parent / "baseline"
    publication_file, recipe_file = root / "joint-research-receipt.json", root / "full-short-recipe.json"
    result, config = map(read, (publication_file, recipe_file))
    receipt, raw = result["receipt"], config["receiver_audit"]
    current, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    prior, = (archived / "fast-scan-automatic-work").glob("*/detections.json")
    old, new = read(checked(prior, witness["detection_file_sha256"])), read(current)
    terminal_file = root / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json"
    terminal = read(terminal_file)
    stock_probes, candidate_probes = (row["source"]["probes"] for row in (old, new))
    native_sha = canonical_digest(new)
    raw_sha = witness["raw_authority"]
    analysis = canonical_digest(["cancellation", raw_sha, RECIPE_SHA, candidate_probes])
    candidate_assets = artifacts(root, receipt)
    archived_assets = artifacts(archived, control["receipt"])
    published = evidence(root, receipt, 0, read_only=True)
    archived_evidence = evidence(archived, control["receipt"], 0, read_only=True)
    published.pop("terminal_file_s")
    verify_stock(archived_evidence, control, archived_assets, archived_assets)
    for label, checked_png in archived_assets["images"].items():
        pin = witness["png_pixels"][label]
        if (checked_png["sha256"] != witness["pngs"][label]
                or checked_png["rgba_sha256"] != pin["rgba_sha256"]
                or checked_png["size"] != (pin["width"], pin["height"])):
            raise ValueError("Installed archived PNG witness changed")
    if (not probe_metadata(stock_probes, candidate_probes) or published["raw_authority"] != raw_sha
            or receipt["region"] != control["receipt"]["region"] or receipt["session_id"] != witness["session_id"]
            or receipt["counts"] != COUNTS or receipt["window_count"] != ISSUED
            or config["recipe"] != recipe() or config["graph"] != GRAPH or config["geographic_sha256"] != GEOGRAPHIC_SHA
            or config["saved_digest"] is not None or result["saved_handoff_manifest"] is not None
            or new["provenance"]["detector_sha256"] != "sha256:" + RECIPE_SHA
            or new["source"]["input_manifest_sha256"] != witness["input_manifest_sha256"]
            or old["clock_anchor"] != new["clock_anchor"] or old["delivery_clocks"] != new["delivery_clocks"]
            or old["provenance"]["excluded_windows"] != new["provenance"]["excluded_windows"]
            or not (new["source"]["analysis_manifest_sha256"] == raw["analysis_manifest"] == analysis)
            or new["source"]["raw_recording_authority_digest"] != raw_sha or raw["recording_authority"] != raw_sha
            or raw["issued"] != ISSUED or raw["detector_pin"] != RECIPE_SHA
            or terminal["native_sha256"] != native_sha
            or canonical_digest(candidate_assets) != canonical_digest(result["evidence"])):
        raise ValueError("Candidate raw authority, verified acquisition, recipe or published artifacts changed")
    independent = classified(candidate_probes)
    if (any(raw["native"].get(k) != v for k, v in independent.items()) or raw["selected"] != sum(independent["factors"].values())
            or result["solve"]["geographic_projector"].get("calls", 0) == 0
            or len(result["early_regional"]) != 1 or not result["optimized_full_catalogue"]):
        raise ValueError("The archived candidate did not execute the exact receiver, solver and geographic path")

    archive = HERE / "measurements/track-quadrature.json.gz"
    stock = json.loads(gzip.decompress(checked(archive, OWNER_SHA).read_bytes()))["runs"]["DS30-0008"]["stock"]
    if stock["identity"]["native_sha256"] != witness["detection_sha256"] or stock["owners"] != control["owners"]:
        raise ValueError("The installed owner witness refers to another complete detector packet")
    exact_owners(stock["selected_rows"], stock)
    meta = FastStandardAnalysisStore(root).detail(receipt["run_id"])
    grid_ok = receipt["decision"] == "complete" and result["solve"]["grid_complete"] and len(candidate_assets["images"]) == 8
    if receipt["decision"] == "complete":
        counts = {arm: meta["arms"][arm]["associated_points"] for arm in ARMS}
        exact_owners(result["selected_rows"], dict(owners=published["owners"], associated=counts))
        if any(v != sum(result["selected_roles"][arm].values()) for arm, v in counts.items()):
            raise ValueError("Published owner/role counts differ")
    else:
        counts = {}
    reference, = [x for x in read(PHYSICAL)["cases"] if x["dataset_label"] == "DS30-0008" and x["authority_eligible"]]
    truth = [reference["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    position = {mode: {arm: None if data["latlon"] is None else distance_km(data["latlon"], truth)
                       for arm, data in source["arms"].items()} for mode, source in (("stock", control), ("candidate", published))}
    deltas = {arm: None if position["candidate"][arm] is None else position["candidate"][arm]-position["stock"][arm]
              for arm in ARMS}
    pngs = figures(archived_assets["images"], candidate_assets["images"])
    clocks = {k: control[k] for k in ("elapsed_s", "cpu_s", "input_blocks", "output_blocks", "major_faults")}
    write(destination, dict(binding=binding, process=process, cache={name: read(output / f"cache-{name}.json")
                                                                    for name in ("before", "after")},
          baseline=dict(clocks=clocks, cache_before=pair["cache"]["arms"]["baseline"], receipt=control["receipt"],
                        authority=raw_sha, arms=control["arms"], owners=control["owners"], image_receipt=archived_assets,
                        owner_archive_sha256=OWNER_SHA), candidate=dict(result=result, receipt_directory=str(root),
                    verified=published, recipe=config, native_sha256=native_sha, native_file=str(current),
                    native_file_sha256=sha256(current.read_bytes()).hexdigest(), terminal_file=str(terminal_file),
                    terminal_sha256=receipt["terminal_sha256"], receipt_sha256=sha256(publication_file.read_bytes()).hexdigest(),
                    recipe_receipt_sha256=sha256(recipe_file.read_bytes()).hexdigest(), owner_counts=counts),
          comparison=dict(position_km=position, delta_km=deltas, grid_and_png_complete=grid_ok,
                    passes_250m=grid_ok and all(delta is not None and delta <= .25 for delta in deltas.values()),
                    owners=owner_changes(stock, result), images=pngs, exact_probe_metadata=True,
                    historical_wall_ratio=process["elapsed_s"]/clocks["elapsed_s"], historical_cpu_ratio=process["cpu_s"]/clocks["cpu_s"]),
          survey_sha256=sha256(PHYSICAL.read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "destination"):
        parser.add_argument(name, type=Path)
    score(**vars(parser.parse_args()))
