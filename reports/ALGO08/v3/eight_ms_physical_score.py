"""Verify and score the frozen DS30-0016 aperture pair after both launches."""

import argparse
from collections import Counter
import json
from pathlib import Path

from aperture_score import PHYSICAL, distance_km
from aperture_trial import ARMS, archive_identity, read, write
from dense_full_short_raw import checked
from full_short_physical import ADMITTED, ISSUED
from full_short_physical_score import classified
from full_short_run import EIGHT_MS_RECIPE_SHA, GEOGRAPHIC_SHA, RECIPE_SHA, checked_recipe
from joint_publication import artifacts
from leo.contracts.digests import canonical_digest
from leo.presentation.localization_v3 import owner_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from short_primary_epoch_audit import good_match, paired_probes
from signed_0374_transfer import owner_changes
from tools.pipeline_eval.qualification.paired_publication import evidence
from weak_combined_raw import HERE


ORDER = ("12ms", "8ms")
REFERENCE_SHA = "a704861e37e40e7364fbf97bcb74e98bb9c701ca474c12821e8ed7df86cab233"
SURVEY_SHA = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"


def quality(candidate, controls, *, complete):
    delta = {name: {arm: None if candidate[arm] is None else candidate[arm] - errors[arm]
                    for arm in ARMS} for name, errors in controls.items()}
    return dict(delta_km=delta, passes=complete and all(
        value is not None and value <= .25 for arms in delta.values() for value in arms.values()))


def read_run(root, name, binding, truth, *, counts, grid_points, regional_pin=None):
    out = root / name
    clock = read(root / f"{name}-clock.json")
    cache = read(root / f"{name}-before.json") if regional_pin is None else None
    proof = read(out / "joint-research-receipt.json")
    seal = read(out / "full-short-recipe.json")
    packet, = (out / "fast-scan-automatic-work").glob("*/detections.json")
    native = read(packet)
    source, receipt, audit = native["source"], proof["receipt"], seal["receiver_audit"]
    pin = EIGHT_MS_RECIPE_SHA if name == "8ms" else RECIPE_SHA
    observed = evidence(out, receipt, 0, read_only=True)
    publication = json.loads(json.dumps(artifacts(out, receipt)))
    native_hash = canonical_digest(native)
    analysis = canonical_digest(["cancellation", observed["raw_authority"], pin, source["probes"]])
    schedule = classified(source["probes"])
    terminal = FastScanStore(out).automatic_workspace(receipt["run_id"], create=False) / "terminal.json"
    request = binding["request"]
    complete = receipt["decision"] == "complete"
    issued = counts["processed"] + counts["invalid_capture"]
    if cache is not None and (cache["unavailable"] or cache["members"] != cache["observed_members"]
                              or cache["cached_pages"] != cache["observed_file_pages"]):
        raise ValueError(f"{name} began without fully resident disk input")
    if (clock["status"] != 0
            or proof["saved_digest"] is not None or proof["saved_handoff_manifest"] is not None
            or receipt["session_id"] != request["session"] or receipt["region"] != request["offered_region"]
            or receipt["window_count"] != issued or audit["issued"] != issued or receipt["counts"] != counts
            or len(source["probes"]) != 2 * counts["processed"] or not source["qualified"]
            or not (observed["raw_authority"] == source["raw_recording_authority_digest"] == audit["recording_authority"]
                    == request["raw_authority"])
            or not source["input_manifest_sha256"] == audit["input_manifest"] == binding["inventory"]
            or not source["analysis_manifest_sha256"] == audit["analysis_manifest"] == analysis
            or read(terminal)["native_sha256"] != native_hash
            or native["provenance"]["detector_sha256"] != "sha256:" + pin or audit["detector_pin"] != pin
            or seal["recipe"] != checked_recipe(name == "8ms") or seal["graph"] != "installed"
            or seal["geographic_sha256"] != GEOGRAPHIC_SHA or not proof["optimized_full_catalogue"]
            or seal.get("regional_track_sha256") != regional_pin
            or not seal["reuse_cold_track_rows"] or not seal["reuse_grid_phase_states"]
            or publication != proof["evidence"]
            or any(audit["native"][key] != value for key, value in schedule.items())
            or audit["selected"] != sum(schedule["factors"].values())):
        raise ValueError(f"{name} did not reproduce the frozen raw/solver contract")
    grid = FastStandardAnalysisStore(out).position_grid(receipt["run_id"]) if complete else None
    if complete and (not grid["complete"] or grid["evaluated_points"] != grid_points or len(publication["images"]) != 8
                     or proof["solve"]["geographic_projector"]["calls"] <= 0):
        raise ValueError(f"{name} published incomplete localization evidence")
    if complete:
        for arm, rows in proof["selected_rows"].items():
            owners = {oid: sat for oid, sat, _ in rows}
            if len(owners) != len(rows) or owner_digest(owners) != observed["owners"][arm]:
                raise ValueError(f"{name} observation owners differ from the standard publication")
    errors = {arm: None if row["latlon"] is None else distance_km(row["latlon"], truth)
              for arm, row in observed["arms"].items()}
    return dict(process=clock, cache=cache, decision=receipt["decision"], reason=observed["reason"],
                counts=receipt["counts"], output_root=str(out), run_id=receipt["run_id"],
                terminal_sha256=receipt["terminal_sha256"], native_sha256=native_hash,
                grid_points=grid["evaluated_points"] if grid else 0,
                scientific_digests=observed["scientific_digests"], owner_sha256=observed["owners"],
                roles=proof["selected_roles"], arms=observed["arms"], errors_km=errors, publication=publication,
                acquisition=audit["acquire"], native=audit["native"], solve=proof["solve"],
                publication_cpu_s=proof["publication_cpu_s"], publication_elapsed_s=proof["publication_elapsed_s"]), native, proof


def score(root):
    old = read(checked(HERE / "measurements/weak-combined-raw.json", REFERENCE_SHA))
    binding = read(root / "binding.json")
    if (binding["order"] != list(ORDER) or binding["request"] != old["binding"]["request"]
            or binding["inventory"] != old["binding"]["inventory"]
            or archive_identity(Path(binding["request"]["archive"]["root"])) != binding["request"]["archive"]):
        raise ValueError("Pair differs from the archived physical assignment")
    survey, = [row["reference"] for row in read(checked(PHYSICAL, SURVEY_SHA))["cases"]
               if row["dataset_label"] == "DS30-0016" and row["authority_eligible"]]
    truth = [survey[key] for key in ("latitude_deg", "longitude_deg")]
    expected = old["runs"]["candidate"]
    counts = dict(processed=ADMITTED, invalid_capture=ISSUED-ADMITTED, skipped_fast_score=0)
    before, left, control = read_run(root, "12ms", binding, truth, counts=counts, grid_points=179)
    after, right, trial = read_run(root, "8ms", binding, truth, counts=counts, grid_points=179)
    if (before["decision"] != "complete" or any(before[key] != expected[key] for key in
            ("arms", "errors_km", "native_sha256", "terminal_sha256", "scientific_digests"))
            or before["owner_sha256"] != expected["owners"] or before["publication"]["images"] != expected["images"]
            or before["cache"]["observed_file_pages"] != after["cache"]["observed_file_pages"]):
        raise ValueError("Fresh 12 ms output or paired cache residency differs from the reference")
    position = quality(after["errors_km"], {"12ms": before["errors_km"], "v3": old["runs"]["stock"]["errors_km"]},
                       complete=after["decision"] == "complete")
    prime = root / "cache-prime-clock.json"
    return dict(case="DS30-0016", survey_sha256=SURVEY_SHA, survey=truth, original_pair_sha256=REFERENCE_SHA,
                binding=binding, initial_cache=read(root / "initial-cache.json"), cache_prime=read(prime) if prime.exists() else None,
                runs={"8ms": after, "12ms": before, "v3": old["runs"]["stock"]}, position=position,
                **comparison(left, right, control, trial))


def comparison(left, right, control, trial):
    factor_counts = {mode: Counter() for mode in ("full", "short_primary")}
    owner_ids = {arm: {row[0] for row in rows} for arm, rows in control["selected_rows"].items()}
    owner_support = {arm: Counter() for arm in ARMS}
    for oid, _, a, b, short in paired_probes(left, right):
        if not short and a != b:
            raise ValueError("A full anchor factor changed")
        matched = good_match(a, b) if short else a is not None
        counts = factor_counts["short_primary" if short else "full"]
        counts.update(opportunities=1, selected_12ms=int(a is not None), selected_8ms=int(b is not None),
                      shared=int(a is not None and b is not None), within_tolerance=int(matched))
        for arm, ids in owner_ids.items():
            if oid in ids:
                owner_support[arm].update(original=1, selected_8ms=int(b is not None), within_tolerance=int(matched))
    return dict(factors=factor_counts, owner_changes=owner_changes(control, trial),
                twelve_ms_owner_measurement_support=owner_support)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write(args.output, score(args.root))
