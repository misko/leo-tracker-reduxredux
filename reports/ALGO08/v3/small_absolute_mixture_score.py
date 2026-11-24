"""Compare the sealed proposals with same-input control scopes and positions."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BASES = {
    "physical": ("/dev/shm/leo-v3-raw-0016-best-results-01/candidate",
                 "81ae6f59cdcafaa11207a9fb326c6186d1a64a7d612b599238014b90d6fe8d6d"),
    "north": ("/dev/shm/leo-v3-north-cfo-contrasts-01/unrefined-full",
              "f9ed20a7c229fbb08042c3148f117882e45664514eea9ba5cf235a4d6f6c7298"),
}


def rms(rows):
    from math import sqrt

    count = sum(len(row["ids"]) for row in rows)
    return None if not count else sqrt(sum(len(row["ids"])*row["rms_hz"]**2 for row in rows)/count)


def compare(output, receipt):
    from centre_oracle_step_score import PINS, controls
    from doppler_difference_trial import checked
    from tools.pipeline_eval.scoring import distance_km

    blind = {}
    for case in BASES:
        body = (output/f"{case}.json").read_bytes()
        run = json.loads(body)
        if (run["case"] != case or run["original_waveform_reads"] or any(
                sha256((HERE/name).read_bytes()).hexdigest() != pin for name, pin in run["sources"].items())):
            raise ValueError("Expected a sealed numerical proposal from the frozen runner")
        blind[case] = dict(run, blind_sha256=sha256(body).hexdigest(), telemetry=(output/f"{case}.time").read_text().splitlines())
    refs = controls()
    result = {}
    for case, run in blind.items():
        root, control_pin = BASES[case]
        folder = Path(root)
        original = json.loads(checked(folder/"joint-research-receipt.json", control_pin))
        packet, = (folder/"fast-scan-automatic-work").glob("*/detections.json")
        checked(packet, run["native_sha256"])
        reference, named = refs[case]
        route = original["route_details"]
        limit = route["candidate_pre_evidence_clocks"]["cpu_s"]+route["signed_total_clocks"]["cpu_s"]
        paid = run["mixture_wall_scope_cpu_ns"]/1e9
        measures = {}
        common = []
        for arm, arm_result in run["arms"].items():
            before = {oid: (norad, role) for oid, norad, role in original["selected_rows"][arm]}
            chosen = [row for row in arm_result["tracks"] if row["retained"]]
            after = {oid: (row["norad"], "conditional" if row["curved"] else "predictive")
                     for row in chosen for oid in row["ids"]}
            correct = sum(before.get(oid) == after[oid] for oid in after)
            error = distance_km(reference, arm_result["latlon"])
            named_error = distance_km(reference, named[arm]["latlon"])
            tests = dict(accuracy=error <= named_error + .25, coverage=correct >= .8*len(before),
                         interior=not arm_result["face"], cost=paid < limit)
            measures[arm] = dict(named_error_km=named_error, proposed_error_km=error, original_same_input_owner_count=len(before),
                                 exact_owner_and_role_count=correct, proposed_coverage_fraction=correct/len(before),
                                 common_observation_count=len(set(before)&set(after)), gates=tests,
                                 passed=all(tests.values()))
            common.append({(row["component"], row["norad"], row["alias"], tuple(row["ids"])): row for row in chosen})
        overlap = common[0].keys() & common[1].keys()
        result[case] = dict(run, scores=measures, exact_control_sha256=control_pin,
                            control_replaced_proposal_and_signed_cpu_s=limit, novel_paid_scope_cpu_s=paid,
                            matched_calibration_support=dict(points=sum(len(k[3]) for k in overlap),
                                rf_rms_hz={arm: rms([tab[k] for k in sorted(overlap)])
                                           for arm, tab in zip(run["arms"], common, strict=True)}))
    paired = all(arm["passed"] for run in result.values() for arm in run["scores"].values())
    body = (json.dumps(dict(cases=result, eligible_for_paired_publications=paired, reference_pins=PINS,
                            original_waveform_reads=0, new_publications=0), indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
    with receipt.open("xb") as stream:
        stream.write(gzip.compress(body, mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("receipt", type=Path)
    compare(**vars(parser.parse_args()))
