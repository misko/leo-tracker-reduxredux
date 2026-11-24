"""Seal saved 8 and 12 ms publications, then score both calibration arms."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from aperture_route_screen import archived
from eight_ms_held_fit import MEASUREMENTS, ORDER, RECEIPT, admit_omitted
from preloaded_saved_worker import read, write


ARCHIVED_WEAK = "8d2cc09632fc3fb617e22b511a7db4a6e86d0fe49fd4f5f7135ca6143d1b449e"
ARCHIVED_NORTH = "3b39eb1bcb201d3b53a73a85345934a4dc6b524b9bd3386c6feb7402c803fe3c"
CALIBRATIONS = ("c0", "fitted_c")


def verify(root, mode):
    from leo.contracts.algo08_region import Algo08Region
    from preloaded_saved_score import science
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence

    measured = read(root.with_name(root.name+"-clock.json"))
    clock = measured["clock"]
    output = root/"published"
    written, identity = read(output/RECEIPT), read(root/"request.json")
    receipt = written["receipt"]
    detector_packet = native_file(output)
    if (clock["exit_code"] or written["waveform_calls"] or written["handoffs"] != 1 or not written["staged_inventory"]
            or "sha256:"+sha256(detector_packet.read_bytes()).hexdigest() != identity["native_sha256"]
            or Algo08Region.parse(identity["original_offer"]).document() != receipt["region"]
            or identity["session"] != receipt["session_id"] or receipt["window_count"] != identity["issued"]):
        raise ValueError("The matched saved request did not reach its original bound terminal")
    if receipt["decision"] == "complete":
        scientific = science(output, receipt, clock, identity)
    else:
        verified = evidence(output, receipt, clock["started_unix_ns"], read_only=True)
        if verified["raw_authority"] != identity["authority"] or not verified["reason"]:
            raise ValueError("The withheld decision is not bound to the original input")
        scientific = dict(arms=verified["arms"], reason=verified["reason"], images={})
    selector = read(root/"selector.json") if mode == "history8" else None
    if selector is not None and (selector["native_sha256"] != identity["native_sha256"] or selector["refinement_calls"]):
        raise ValueError("The saved 8 ms route must contain its native CFOs without a new tail")
    key = receipt["run_id"]
    terminal = read(output/"fast-scan-automatic-work"/key/"terminal.json")
    if terminal["native_sha256"] != identity["native_sha256"]:
        raise ValueError("Terminal detector digest does not match the saved input")
    return dict(identity=identity, publication=written, measured=measured, science=scientific,
                detector=str(detector_packet), selector=selector)


def pair_invariants(pair):
    identities = [row["identity"] for row in pair.values()]
    boundaries = ("recording", "archive", "session", "inventory", "authority", "cutoff_utc_ns", "issued", "offer_sha256", "flags")
    if any(identities[0][key] != identities[1][key] for key in boundaries):
        raise ValueError("Receiver policies did not use the same case, causal archive and solver options")


def seal(root, offer):
    from empty_bootstrap import checked

    binding = read(root/"binding.json")
    for name, digest in binding["sources"].items():
        checked(HERE/name, digest)
    cases = tuple(ORDER) if offer == "containing" else (admit_omitted(root),)
    runs = {}
    for case in cases:
        pair = {mode: verify(root/offer/f"{case}-{mode}", mode) for mode in ORDER[case]}
        pair_invariants(pair)
        runs[case] = pair
    if offer == "omitted":
        prior = read(root/"containing-seal.json")["runs"][case]
        for mode in ORDER[case]:
            if prior[mode]["identity"]["native_sha256"] != pair[mode]["identity"]["native_sha256"]:
                raise ValueError("Omitted offer must consume exactly the containing detector packet")
    write(root/(offer+"-seal.json"), dict(runs=runs, binding_sha256=sha256((root/"binding.json").read_bytes()).hexdigest()))


def geographic_reference(case):
    from empty_bootstrap import checked

    if case == "weak":
        from triage_bounds import REFERENCE, REFERENCE_SHA256

        rows = json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
        (survey,) = (row["reference"] for row in rows if row["dataset_label"] == "DS30-0016" and row["authority_eligible"])
        return [survey[field] for field in ("latitude_deg", "longitude_deg")], REFERENCE_SHA256
    from north_interlaced_raw import NORTH, TRUTH_SHA

    rows = json.loads(checked(HERE.parent/"regional-release/scoring-key.json", TRUTH_SHA))["answers"].values()
    (truth,) = {tuple(row["truth"]) for row in rows if row["recording"] == NORTH}
    return truth, TRUTH_SHA


def owner_differences(left, right):
    a = {obs: (family, role) for obs, family, role in left}
    b = {obs: (family, role) for obs, family, role in right}
    shared = set(a) & set(b)
    return dict(shared=len(shared), original_only=len(set(a)-shared), candidate_only=len(set(b)-shared),
                family_changes=sum(a[k][0] != b[k][0] for k in shared), role_changes=sum(a[k][1] != b[k][1] for k in shared))


def charges(case, selector):
    from empty_bootstrap import checked

    previous = archived(f"eight-ms-{'physical' if case == 'weak' else 'north'}.json")["runs"]
    shortwork = {arm: previous[arm]["native"]["native_cpu_ns"]["short_primary"]/1e9 for arm in ("8ms", "12ms")}
    if case == "weak":
        value = json.loads(gzip.decompress(checked(MEASUREMENTS/"continued-cfo.json.gz", ARCHIVED_WEAK)))["prices"]["weak"]
        anchor_calls = value["counts"]["short_positives"]
        tail_cpu = value["original_all_paid_refinement_cpu_ns"]/1e9
    else:
        value = json.loads(gzip.decompress(checked(MEASUREMENTS/"continued-cfo-north.json.gz", ARCHIVED_NORTH)))["sealed"]["raw"]
        tail_cpu = value["receiver_audit"]["native"]["cfo_refinement"]["cpu_ns"]/1e9
        anchor_calls = value["held_anchor_route"]["refinement_attempts"]
    paid = selector["would_refine"]
    return dict(saved_cfo_calls=0, hypothetical_8ms_tail_calls=paid,
                unique_stereo_tail_visits=selector["would_refine_stereo_visits"], original_12ms_tail_calls=anchor_calls,
                original_12ms_tail_cpu_s=tail_cpu, projected_extra_8ms_tail_cpu_s=tail_cpu*paid/anchor_calls,
                archived_primary_cpu_s=shortwork, gross_short_primary_delta_s=shortwork["12ms"]-shortwork["8ms"])


def eligible(original, candidate):
    return (original["status"] == candidate["status"] == "fix"
            and candidate["elapsed_s"] < original["elapsed_s"]
            and all(candidate["arms"][arm]["error_km"] <= original["arms"][arm]["error_km"] for arm in CALIBRATIONS))


def score(root, offer):
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    frozen = root/(offer+"-seal.json")
    cases = {}
    for case, pair in read(frozen)["runs"].items():
        truth, reference = geographic_reference(case)
        offer_doc = pair["history8"]["identity"]["original_offer"]
        clearance = face_clearance_km(offer_doc, truth)
        if (clearance > 0) != (offer == "containing"):
            raise ValueError("The filed region intent and independent geographic score disagree")
        result = {}
        for mode, run in pair.items():
            science = run["science"]
            clock = run["measured"]["clock"]
            fixed = run["publication"]["receipt"]["decision"] == "complete"
            result[mode] = dict(status=("fix" if clearance > 0 else "false_fix") if fixed else "withheld",
                                elapsed_s=clock["elapsed_s"], cpu_s=clock["cpu_s"], arms={arm: {
                                    "error_km": distance_km(truth, value["latlon"]) if value["latlon"] else None,
                                    "rf_rms_hz": value.get("rf_rms_hz"), "position": value["latlon"]}
                                    for arm, value in science["arms"].items()})
        a, b = result["continued12"], result["history8"]
        first, second = (pair[mode]["science"].get("roles", {}) for mode in ("continued12", "history8"))
        owners = {arm: owner_differences(first.get(arm, []), second.get(arm, [])) for arm in CALIBRATIONS}
        cases[case] = dict(results=result, owner_changes=owners,
                           eligible_omitted=offer == "containing" and eligible(a, b),
                           truth_face_km=clearance, reference_sha256=reference,
                           tail_charges=charges(case, pair["history8"]["selector"]))
    write(root/(offer+"-score.json"), dict(sealed_sha256=sha256(frozen.read_bytes()).hexdigest(), cases=cases))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("offer", choices=("containing", "omitted"))
    args = parser.parse_args()
    dict(seal=seal, score=score)[args.action](args.root, args.offer)
