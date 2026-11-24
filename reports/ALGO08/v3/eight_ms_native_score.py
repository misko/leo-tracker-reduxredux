"""Check signed 8 ms parity, receiver spend and the paired-calibration publication."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from eight_ms_native_live import ORDER, PHYSICAL, PHYSICAL_NATIVE, PRIOR_GUARDED, PRIOR_GUARDED_NATIVE, PRIOR_GUARDED_RECEIPT
from empty_bootstrap import checked
from preloaded_saved_worker import read, write


SAVED_NORTH = Path("/dev/shm/leo-v3-eight-ms-held-fit-result01/containing-seal.json")
SAVED_NORTH_SHA = "954fea001cd8591559f471a5d5b28e1725f2935b80ebe8700da8f0b78b5cf0df"
NORTH_ORIGINAL = "sha256:a2eaf86c99145cc70b7040cf6e81c9fb0bc5e2e00b752223f5365de6818b8c49"
COMBINED_SHA = "7a30fd17def1e35b70c56178fcefed5434278d542503fbe750ac46d4aee48025"
OMITTED_12MS_SHA = "d7bcd8decc51cf524cf2b48916f4058d4f4efc13716ae5708cb3771c80cc8073"
ARMS = ("c0", "fitted_c")


def native_cpu(scope):
    native = scope["acquisition"]["native"]
    return sum(native["native_cpu_ns"].values()) + native.get("cfo_refinement", {}).get("cpu_ns", 0)


def admitted(left, right):
    return (left["acquisition"]["acquire"]["cpu_ns"] < right["acquisition"]["acquire"]["cpu_ns"]
            and native_cpu(left) < native_cpu(right))


def unchanged_history(original, candidate, selector):
    from anchor_holds import history_rows

    route = selector["choice"]["route"]
    if route not in ("history", "unfiltered") or selector["refinement_calls"]:
        raise ValueError("Only a frozen 8 ms history route with zero later CFO calls can publish")
    expected = history_rows(original) if route == "history" else original
    if candidate != expected:
        raise ValueError("The 8 ms route changed a signed measurement or its chronological eligibility")


def prefix_score(root):
    from continued_cfo_first_0016_score import align
    from full_short_run import EIGHT_MS_SHA
    from leo.contracts.digests import canonical_digest
    from raw_cfo_north_trial import native_file

    binding = read(root/"binding.json")
    for name, pin in binding["sources"].items():
        checked(HERE/name, pin)
    old = json.loads(checked(PRIOR_GUARDED/"scope-receipt.json", PRIOR_GUARDED_RECEIPT))
    archived = json.loads(checked(native_file(PHYSICAL), PHYSICAL_NATIVE))
    runs, packets = {}, {}
    for mode in ORDER:
        path = root/mode
        scope, measured = read(path/"scope-receipt.json"), read(root/(mode+"-clock.json"))
        pin = scope["native_sha256"][7:]
        packets[mode] = json.loads(checked(path/"detections.json", pin))
        if (scope["position_runs"] or scope["mode"] != mode or measured["clock"]["exit_code"] or
                any(snapshot["unavailable"] or snapshot["cached_pages"] != snapshot["observed_file_pages"]
                    for snapshot in (measured["before"], measured["after"]))):
            raise ValueError("Both bounded fresh receiver clocks must complete on resident source")
        if scope["iq"] != old["iq"] or scope["opened"] != old["opened"]:
            raise ValueError("The staged prefix member and 64 original decoded hashes changed")
        runs[mode] = dict(scope, clock=measured, native_total_cpu_ns=native_cpu(scope))
    current, guarded = (runs[mode] for mode in ORDER)
    if (guarded["native_sha256"] != "sha256:"+PRIOR_GUARDED_NATIVE or any(
            guarded[key] != old[key] for key in ("held_choice", "original_probes", "acquired_probes", "paid"))):
        raise ValueError("The current guarded control differs scientifically from the archived exact prefix")
    live = packets["history8"]
    expected = align(live, archived)
    witness = current["held_choice"]
    counts = current["acquisition"]["native"]
    if (current["original_probes"] != expected or current["acquired_probes"] != expected or current["paid"]
            or counts["short_primary_sha256"] != EIGHT_MS_SHA or "cfo_refinement" in counts
            or counts["native_calls"] != guarded["acquisition"]["native"]["native_calls"]
            or witness["native_sha256"] != canonical_digest(live)):
        raise ValueError("The live complete native 8 ms prefix failed exact archived parity or aperture separation")
    unchanged_history(expected, live["source"]["probes"], witness)
    result = dict(binding=binding, runs=runs, original_physical_native_sha256=PHYSICAL_NATIVE,
                  guarded_reference_sha256=PRIOR_GUARDED_RECEIPT,
                  exact_original_8ms_probes=len(expected), admit_north=admitted(current, guarded),
                  native_cpu_saved_s=(native_cpu(guarded)-native_cpu(current))/1e9,
                  acquisition_cpu_saved_s=(guarded["acquisition"]["acquire"]["cpu_ns"]-
                                            current["acquisition"]["acquire"]["cpu_ns"])/1e9)
    path = root/"result.json"
    if path.exists():
        if read(path) != result:
            raise ValueError("The scored prefix changed after its first seal")
    else:
        write(path, result)
    return result


def same_images(actual, archived):
    def checked_images(images):
        return {name: dict(item, size=list(item["size"])) for name, item in images.items()}

    return checked_images(actual) == checked_images(archived)


def verify_figures(root):
    seal = root/"science-seal.json"
    saved = read(seal)
    observed, expected = (saved[case]["images"] for case in ("science", "science_baseline"))
    if len(observed) != 8 or not same_images(observed, expected):
        raise ValueError("A signed figure differs from its saved publication")
    write(root/"figure-parity.json", dict(seal_sha256=sha256(seal.read_bytes()).hexdigest(), images=observed,
                                         all_eight_encoded_decoded_and_dimensions_match=True))


def north_seal(root):
    from eight_ms_held_score import owner_differences
    from full_short_run import EIGHT_MS_SHA
    from joint_held_north_raw import check_handoff, references, require_resident
    from north_held_anchor_pair import publication_evidence
    from preloaded_saved_score import science
    from raw_cfo_north_trial import native_file

    binding = read(root/"binding.json")
    for name, pin in binding["source_sha256"].items():
        checked(HERE/name, pin)
    request, assignment = binding["request"], binding["assignment"]
    before, after = (read(root/f"cache-{point}.json") for point in ("before", "after"))
    for snapshot in (before, after):
        for row in snapshot.values():
            require_resident(row)
    clock = read(root/"clock.json")
    case = root/"containing"
    raw = read(case/"unified-short-bootstrap.json")
    research = read(case/"joint-research-receipt.json")
    candidate = publication_evidence(case, raw["receipt"], clock, assignment)
    native = json.loads(checked(native_file(case), raw["native_sha256"][7:]))
    check_handoff(raw, research, native, candidate, request)
    original_saved = json.loads(checked(SAVED_NORTH, SAVED_NORTH_SHA))["runs"]["north"]
    old = original_saved["history8"]
    expected_selector = old["selector"]
    witness = raw["held_anchor_route"]
    counts = raw["receiver_audit"]["native"]
    if (witness["parent_native_sha256"] != NORTH_ORIGINAL or raw["native_sha256"] != old["identity"]["native_sha256"]
            or {k:v for k,v in witness.items() if k != "selector"} != {
                k:v for k,v in expected_selector.items() if k != "selector"}
            or witness["refinement_calls"] or witness["choice"]["route"] != "history"
            or counts["short_primary_sha256"] != EIGHT_MS_SHA or "cfo_refinement" in counts):
        raise ValueError("Complete live 8 ms parent/selected packet or zero-tail provenance did not reproduce")
    archived_selection = Path(old["detector"])
    checked(archived_selection, raw["native_sha256"][7:])
    actual = science(case, raw["receipt"], clock, old["identity"])
    fields = ("terminal", "arms", "roles", "grid_and_path", "grid_points", "images", "named_finish")
    agreement = {key: actual[key] == old["science"][key] for key in fields}
    agreement["images"] = same_images(actual["images"], old["science"]["images"])
    rank, orbit = (read(root/name) for name in ("catalogue-block-rank.json", "orbits-indexed.json"))
    transfer, = orbit["transfers"]
    if (not rank["requested"] or not rank["counts"]["compact_calls"] or transfer["compatibility"]["fallback"]
            or transfer["loading"]["fallback"] or not transfer["counts"]["sidecar_hit_bodies"]):
        raise ValueError("The ordinary combined raw build did not exercise both promised options")
    combined = json.loads(gzip.decompress(checked(HERE/"measurements/combined-raw-north.json.gz", COMBINED_SHA)))
    _, historical = references()
    prior = combined["candidate"]
    owners = {arm: owner_differences(original_saved["continued12"]["science"]["roles"][arm], actual["roles"][arm])
              for arm in ARMS}
    save = dict(scope="original North containing through exit", clock=clock, raw=raw, rank=rank, orbit=orbit,
                cache_before=before, cache_after=after, request=request, saved_agreement=agreement, science=actual,
                science_baseline=old["science"], owners_vs_guarded12=owners, solve=research["solve"],
                early=research["early_regional"], route=research["route_details"],
                historical=dict(combined=dict(clock=prior["clock"], phases=prior["phases"], score=prior["score"]),
                                named=historical["stock"]["clock"]),
                verified_authority=candidate["verified"]["raw_authority"], saved_reference_sha256=SAVED_NORTH_SHA)
    write(root/"science-seal.json", save)


def outcome(arms, offer, truth):
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    return {arm: None if not row.get("latlon") else dict(error_m=1000*distance_km(row["latlon"], truth),
                face_km=face_clearance_km(offer, row["latlon"]), **row) for arm, row in arms.items()}


def north_score(root):
    from eight_ms_held_score import geographic_reference

    seal = root/"science-seal.json"
    result = read(seal)
    truth, pin = geographic_reference("north")
    success = result["science"]
    endpoint = outcome(success["arms"], success["identity"]["original_offer"], truth)
    historical = result["historical"]["combined"]["score"]["outcomes"]
    admitted = all(result["saved_agreement"][field] for field in ("arms", "roles", "grid_points", "named_finish"))
    write(root/"score.json", dict(science_seal_sha256=sha256(seal.read_bytes()).hexdigest(), scoring_reference_sha256=pin,
          outcomes=dict(live_8ms=endpoint, guarded_12ms=historical["continued"], installed_v3=historical["named"]),
          admit_omitted=admitted, fixed_error_change_from_v3_m=endpoint["c0"]["error_m"]-historical["named"]["c0"]["error_m"]))


def omitted_score(root):
    from continued_cfo_north_mirror import MIRROR, MIRROR_SHA
    from eight_ms_held_score import geographic_reference
    from preloaded_saved_score import science
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km

    archived = HERE/"measurements/continued-cfo-north-mirror.json.gz"
    earlier = json.loads(gzip.decompress(checked(archived, OMITTED_12MS_SHA)))
    bound = read(root/"omitted-binding.json")
    clock = read(root/"omitted-clock.json")
    activation = read(root/"omitted-execution.json")
    transfer, = activation["orbit"]["transfers"]
    if (activation["rank_status"] != "compacted" or not activation["rank"]["counts"]["compact_calls"]
            or transfer["compatibility"]["fallback"] or transfer["loading"]["fallback"]
            or not transfer["counts"]["sidecar_hit_bodies"]):
        raise ValueError("The omitted replay must exercise the same portable and block solver options")
    target = root/"omitted"
    published = read(target/"eight-ms-omitted.json")
    native = bound["native_sha256"]
    checked(native_file(target), native[7:])
    receipt = published["receipt"]
    identity = read(root/"science-seal.json")["science"]["identity"] | {
        "original_offer": json.loads(checked(MIRROR, MIRROR_SHA)), "offer_sha256": MIRROR_SHA}
    verified = evidence(target, receipt, clock["started_unix_ns"], read_only=True)
    if (clock["exit_code"] or published["waveform_calls"] or published["handoffs"] != 1
            or published["native_sha256"] != native or not published["staged_inventory"]
            or verified["raw_authority"] != identity["authority"] or receipt["region"] != identity["original_offer"]):
        raise ValueError("The exact sealed native packet and original omitted offer must reach the standard terminal")
    full = receipt["decision"] == "complete"
    scientific = science(target, receipt, clock, identity) if full else None
    truth, pin = geographic_reference("north")
    clearance = face_clearance_km(receipt["region"], truth)
    if abs(clearance+0.1) > 0.001:
        raise ValueError("The fixed mirror offer must omit reference by 100 m")
    write(root/"omitted-score.json", dict(published=published, decision=receipt["decision"], clock=clock,
          reason=verified["reason"], truth_face_km=clearance, score=outcome(verified["arms"], receipt["region"], truth),
          execution=activation, science=scientific, false_fix=full, earlier=earlier["score"],
          score_source_sha256=pin, earlier_sha256=OMITTED_12MS_SHA))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prefix", "seal", "score", "figures", "omitted"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    actions = dict(prefix=prefix_score, seal=north_seal, score=north_score, figures=verify_figures, omitted=omitted_score)
    actions[args.action](args.root)
