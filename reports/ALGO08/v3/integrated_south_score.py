"""Read back sealed South publications against the closest original controls."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from reports.ALGO08.v3.integrated_south import CONTROL_PIN, HERE, PRIOR


OMITTED = Path("/dev/shm/leo-v3-exact-named-south-omitted01")
OMITTED_PIN = "4666aaa078e6923f7a63bbcd8347e4c2207e02f949a91c45c95add035caea697"


def read(path):
    return json.loads(path.read_bytes())


def numerical(sidecar):
    bound = {key: value for key, value in sidecar["binding"].items()
             if key not in ("input_sha256", "terminal_sha256", "position_png_sha256")}
    return {key: value for key, value in sidecar.items() if key != "elapsed_seconds"} | {"binding": bound}


def image_fields(images):
    from publication_media_checks import image_comparison_fields

    return {name: dict(item, size=list(item["size"])) for name, item in image_comparison_fields(images).items()}


def original_members(audit, request, chunks):
    identity = {"session": request["session"], "inventory": request["inventory"],
                "windows": request["issued"], "raw_authority": request["authority"]}
    fields = {"chunk_index": "chunk_index", "member_sha256": "compressed_sha256", "index_sha256": "index_sha256",
              "raw_sha256": "uncompressed_sha256", "first_sequence": "first_sequence", "windows": "window_count",
              "encoded": "compressed_bytes", "decoded": "uncompressed_bytes"}
    return (audit["authority_mode"] == "verified-once" and audit["verified_source"] == identity
            and audit["finished_raw_authority"] == request["authority"] and len(audit["members"]) == len(chunks)
            and all(row["manifest_sha256"] == "sha256:" + request["manifest_sha256"]
                    and all(row[key] == chunk[field] for key, field in fields.items())
                    and "complete_encoded_auth" in row and not row["hash_prefix"]
                    for row, chunk in zip(audit["members"], chunks, strict=True)))


def score(root, after):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from continued_cfo_trial import rebinding
    from eight_ms_south_transfer import KEY_SHA
    from empty_bootstrap import bind_native, checked
    from full_short_run import SPARSE_EIGHT_MS_RECIPE_SHA
    from integrated_original_entry import HELD_SHA
    from joint_publication import artifacts
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_0016_best_score import position_sides
    from reports.ALGO08.v3.history_risk_0016_cairo import active_renderer
    from south_cfo_route import admissible
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    prediction = root / "prediction-seal.json"
    if read(prediction) != output_seal(root):
        raise ValueError("The clocked prediction changed before scoring")
    book, measured, startup = (read(root / name) for name in ("admission.json", "candidate-clock.json", "startup.json"))
    before, process = (measured[key] for key in ("cache_before", "clock"))
    post = read(after)
    req, mode = book["request"], book["mode"]
    if (measured["command"] != book["command"] or (post["recording"], post["inventory"]) != (req["recording"], req["inventory"])
            or (post["owner"], after.stat().st_uid) != (before["owner"], before["owner"])):
        raise ValueError("The sealed clock and passive residency must describe the assigned original")
    result = dict(mode=mode, admission=book, process=process, preflight=before, cache_after=post, startup=startup,
                  seal_sha256=sha256(prediction.read_bytes()).hexdigest(),
                  cache_after_sha256=sha256(after.read_bytes()).hexdigest(), qualified=False)
    if process["exit_code"]:
        write(root / "result.json", result | {"decision": "failed"})
        return

    control = json.loads(checked(PRIOR / "result.json", CONTROL_PIN))
    target = root / "candidate"
    raw, witness, acquisition = (read(target / name) for name in ("unified-short-bootstrap.json",
                                "exact-named-raw-witness.json", "legacy-original-acquisition.json"))
    receipt = raw["receipt"]
    prior_target = PRIOR / "candidate"
    (prior_packet,) = prior_target.glob("fast-scan-automatic-work/*/detections.json")
    old_native = read(prior_packet)
    bind_native(old_native, req["session"], req["inventory"], canonical_digest(control["candidate"]["native_recipe"])[7:],
                expected=control["candidate"]["native"])
    (packet,) = target.glob("fast-scan-automatic-work/*/detections.json")
    native = read(packet)
    held = raw["held_anchor_route"]
    bind_native(native, req["session"], req["inventory"], HELD_SHA, expected=raw["native_sha256"])
    published = evidence(target, receipt, process["started_unix_ns"], read_only=True)
    offer_sha = req["offer_sha256"][mode]
    offer = Algo08Region.parse(json.loads(checked(Path(req["offers"][mode]), offer_sha))).document()
    checks = dict(original=original_members(acquisition, req, book["chunks"]),
                  resident=admissible(post["residence"]["wave"]) and before["residence"]["causal"] == post["residence"]["causal"],
                  same_detector_rows=native == rebinding(old_native, old_native["source"]["probes"], raw["receiver_recipe"]),
                  held=held["choice"] == control["candidate"]["selector"] and held["refinement_calls"] == 0
                  and held["parent_detector_sha256"] == "sha256:" + SPARSE_EIGHT_MS_RECIPE_SHA,
                  original_scope=receipt["region"] == offer and receipt["window_count"] == req["issued"]
                  and receipt["counts"] == control["candidate"]["science"]["receipt"]["counts"]
                  and raw["clock_anchor"] == old_native["clock_anchor"]
                  and raw["causal_cutoff_utc_ns"] == req["cutoff_utc_ns"] and raw["requested_offer_sha256"] == offer_sha
                  and raw["archive_root"] == req["archive"]["root"] and raw["raw_acquisitions"] == raw["verified_handoffs"] == 1
                  and published["raw_authority"] == req["authority"] and not raw["scientific_imports_before"])
    reference_key = json.loads(checked(HERE.parent / "regional-release/scoring-key.json", KEY_SHA))
    truth, = {tuple(row["truth"]) for row in reference_key["answers"].values()
              if row["recording"] == Path(req["recording"]).name}
    clearance = face_clearance_km(offer, truth)
    geographic = {arm: dict(point, horizontal_error_km=distance_km(truth, point["latlon"]))
                  for arm, point in published["arms"].items()}
    images, sidecars = {}, {}
    if receipt["decision"] == "complete":
        media, inner = artifacts(target, receipt), witness["evidence"]
        store = FastStandardAnalysisStore(target)
        sidecars = position_sides(store, receipt, media, control["candidate"]["sidecars"]["grid_points"])
        images = image_fields(media["images"])
        png = acquisition["acceleration"]["solver"]["png_native"]
        checks["figures"] = (len(images) == 8 and images == image_fields(inner["images"])
                             and active_renderer(witness["ports"]) and (png["native"], png["fallback"]) == (8, 0)
                             and witness["ports"]["cairo_layout"]["original_recording_title"] == Path(req["recording"]).name)
        checks["owner_digests"] = all(canonical_digest({uid: sat for uid, sat, _ in rows}) == published["owners"][arm]
                                     for arm, rows in inner["owner_rows"].items())
    else:
        checks["withhold_products"] = not geographic and not any(target.rglob("*.png"))
    if mode == "containing":
        previous, run_id = control["candidate"], receipt["run_id"]
        old_store = FastStandardAnalysisStore(prior_target)
        old_id = previous["science"]["receipt"]["run_id"]
        checks["containing_fix"] = clearance > 0 and receipt["decision"] == "complete"
        if checks["containing_fix"]:
            checks["prior_positions_rf"] = geographic == control["containing"]["geographic"]["candidate"]
            checks["prior_ordered_owners"] = witness["evidence"]["owner_rows"] == control["ordered_owner_rows"]["candidate"]
            for kind in ("grid", "path"):
                old = getattr(old_store, "position_" + kind)(old_id)
                new = getattr(store, "position_" + kind)(run_id)
                checks["prior_" + kind] = numerical(old) == numerical(new)
        prior_arms, named_arms = (control["containing"]["geographic"][key] for key in ("candidate", "named"))
    else:
        omission = json.loads(checked(OMITTED / "result.json", OMITTED_PIN))
        if clearance >= 0 or omission["offer"] != offer:
            raise ValueError("The second transfer must use the exact prior near-omitted offer")
        prior_arms, named_arms = ({arm: row[key] for arm, row in omission["arms"].items()} for key in ("candidate", "named"))
    disposition = ("false_fix" if clearance < 0 else "fix") if receipt["decision"] == "complete" else "withheld"
    write(root / "result.json", result | dict(qualified=all(checks.values()), checks=checks, disposition=disposition,
          decision=receipt["decision"], geographic=geographic, truth_clearance_km=clearance, truth_sha256=KEY_SHA,
          prior_20_8=prior_arms, installed=named_arms, previous_clocks=control["clocks"], sidecars=sidecars,
          png_comparison_prior_containing=images == image_fields(control["candidate"]["media"]["images"]),
          images=images, published=published, receiver=raw, witness=witness, original=acquisition))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("after", type=Path)
    options = cli.parse_args()
    score(options.root, options.after)
