"""Verify and score the fresh North pair and its saved missing-region check."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def read(path):
    return json.loads(path.read_bytes())


def score(root):
    from eight_ms_held_score import geographic_reference, owner_differences
    from empty_bootstrap import load_runtime

    load_runtime()
    from leo.contracts.algo08_region import Algo08Region
    from tools import pipeline_eval
    from tools.pipeline_eval import qualification

    checkout = HERE.parents[2]/"tools/pipeline_eval"
    pipeline_eval.__path__.append(str(checkout))
    qualification.__path__.append(str(checkout/"qualification"))
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km
    from exact_named_raw import ARM_NAMES
    from exact_named_raw_transfer import ORDER, RAW_PACKET
    from raw_cfo_north_trial import STOCK_PACKET, native_file

    truth, reference = geographic_reference("north")
    binding = read(root/"binding.json")
    clocks, results = {label: read(root/f"{label}-clock.json") for label in ORDER}, {}
    if any(row["exit_code"] for row in clocks.values()):
        raise ValueError("Both complete raw launches and the separate omission must succeed")
    chosen, opportunities = {}, {}
    for label in ORDER:
        output = root/label
        witness = read(output/("named-raw-witness.json" if label == "named" else "exact-named-raw-witness.json"))
        details = witness["evidence"]["detail"]
        terminal, = output.glob("fast-scan-automatic-work/*/terminal.json")
        terminal = read(terminal)
        expected = STOCK_PACKET if label == "named" else RAW_PACKET
        raw = read(native_file(output))
        receipt = read(output/"unified-short-bootstrap.json") if label == "candidate" else None
        offer = root/"omitted-offer.json" if label == "north-far-saved" else Path(binding["request"]["inside_offer"])
        inside = label != "north-far-saved"
        if (details["input_sha256"] != expected or terminal["native_sha256"] != expected
                or details["session_id"] != binding["request"]["session"]
                or details["region"] != Algo08Region.parse(read(offer)).document()
                or set(terminal["arms"]) != set(ARM_NAMES)):
            raise ValueError("Scientific publication or input digests changed")
        clearance = face_clearance_km(details["region"], truth)
        if (clearance > 0) != inside:
            raise ValueError("The independently scored published region does not match the enrolled offer")
        if inside:
            if details["state"] != "complete" or witness["evidence"]["grid"] != 137:
                raise ValueError("Expected the original complete clipped North layout")
            chosen[label] = witness["evidence"]["owner_rows"]
        else:
            omission = read(output/"saved-omitted-witness.json")
            if (omission["raw_acquisitions"] != 0 or omission["handoffs"] != 1
                    or binding["original_omitted"]["status"] != "withheld"):
                raise ValueError("Expected a saved missing-region control on the archived named offer")
            if details["state"] == "withheld" and any(
                    file.suffix == ".png" or file.name in ("position-grid.json", "position-path.json")
                    for file in output.rglob("*") if file.is_file()):
                raise ValueError("The withheld publication must omit figures and sidecars")
        if receipt and (receipt["native_sha256"] != RAW_PACKET or receipt["raw_acquisitions"] != 1
                        or receipt["verified_handoffs"] != 1 or receipt["scientific_imports_before"]):
            raise ValueError("The raw receiver must perform exactly one authenticated traversal and handoff")
        factors = raw["source"]["probes"]
        opportunities[label] = [{key: value for key, value in row.items()
                                 if key not in ("candidates", "probe_start_ms", "edge")} for row in factors]
        evidence = dict(witness["evidence"], owner_rows={arm: len(rows) for arm, rows in
                        witness["evidence"]["owner_rows"].items()})
        if receipt:
            phases = receipt["phases"]
            raw_stages = dict(receiver=phases["authenticated_raw_acquisition"],
                              eof_selection=phases["held_anchor_route_selection"],
                              decision_publication=phases["decision_and_publication"])
        else:
            raw_stages = {}
        arms = {}
        for arm, value in terminal["arms"].items():
            position = value["latlon"]
            fit = details["arms"].get(arm, {})
            arms[arm] = dict(position=position, error_km=distance_km(truth, position) if position else None,
                             rf_rms_hz=fit.get("residual_rms_hz"))
        results[label] = dict(status=details["state"], reason=terminal["reason"], arms=arms, clearance_km=clearance,
                              native_sha256=expected, signed_factors=sum(len(row["candidates"]) for row in factors),
                              timings=witness["timing"], installed=witness["installed"], verification=witness["verification"],
                              raw_stages=raw_stages, evidence=evidence, port_audit=witness.get("ports"))
    if opportunities["named"] != opportunities["candidate"] or opportunities["candidate"] != opportunities["north-far-saved"]:
        raise ValueError("The two raw receivers must cover the same chronological opportunities")
    return dict(scenario="previously scored North simulation", frozen_reference_sha256=reference,
                binding_sha256=sha256((root/"binding.json").read_bytes()).hexdigest(),
                launch_order=ORDER, clocks=clocks, runs=results, original_opportunities=len(opportunities["named"]),
                owner_changes={arm: owner_differences(chosen["named"][arm], chosen["candidate"][arm]) for arm in ARM_NAMES},
                wall_ratio=clocks["named"]["elapsed_s"]/clocks["candidate"]["elapsed_s"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = score(args.root)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
