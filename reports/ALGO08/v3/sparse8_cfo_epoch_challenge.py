"""Reuse the verified 0049 ordinary control and measure one unchanged time correction."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sparse8_cfo_epoch_trial import ARMS, CAMPAIGN, HERE, document, geography, identifier, launch, write


CASE = "DS30-0049"
PAIR = "7514497ea681194487e8d85aecf2d739e996abf2b90566d446f81fe38875c36b"
ADMISSION = "ae8fe9afa9d040443219524d5f36992d6c383bffa378097664b3a5aca43ef293"
PARITY = "c1fd49b28d0a90370ecf056ac7c0bf90b01af094a9377bfff5c38db39da7b7f3"
WITNESS = "02d9a0273e0ed19bac1e531e09f8d4fca323f2c09db6e1aeb6c9798a161732ad"
CROSSOVER = Path("/tmp/leo-v3-0049-saved-cross-proof02")
PROTOCOL = HERE / "sparse8-cfo-epoch-transfer-protocol.md"


def ordinary(stage):
    admission = document(stage / "admission.json", ADMISSION)
    pair = document(CAMPAIGN / "cases" / CASE / "pair.json", PAIR)
    raw = CAMPAIGN / "cases" / CASE / "successor" / f"attempt-{pair['generation']:06d}"
    archived = document(raw / "result.json", pair["attempt_result_sha256"]["successor"])
    archived_witness = document(raw / "publication/exact-named-raw-witness.json", WITNESS)
    sub = "successor-successor"
    crossover = document(CROSSOVER / "final-evidence.json", PARITY)
    checks = crossover["raw_diagonal_equivalence"][sub]
    if len(checks) != 6 or not all(checks.values()):
        raise ValueError("Ordinary crossover scientific route did not reproduce the archived raw")
    worker = document(CROSSOVER / sub / "crossover-worker.json", crossover["owner_row_source_sha256"][sub])
    receipt = worker["receipt"]
    if (archived["outcome"] != "complete" or worker["waveform_reads"] or worker["verified_handoffs"] != 1
            or worker["ordered_owners"] != archived_witness["evidence"]["owner_rows"]
            or receipt["terminal_sha256"] != archived["evidence"]["receipt"]["terminal_sha256"]
            or worker["submitted_native_sha256"] != "sha256:"+admission["native_pin"]
            or archived["native_sha256"] != worker["submitted_native_sha256"]
            or archived["authority_sha256"] != "sha256:"+admission["authority_pin"]):
        raise ValueError("Archived ordinary scientific custody is inconsistent")
    terminal = document(CROSSOVER / sub / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json",
                        receipt["terminal_sha256"])
    return dict(terminal=terminal, witness=archived_witness, parity=checks, admission=admission,
                raw_clock=archived["process"], timed_saved_clock=crossover["cells"][sub]["clocks"])


def run(stage):
    control = ordinary(stage)
    products, config = launch(stage, "centroid", ADMISSION)
    seal = write(stage / "prediction-seal.json", dict(
        case=CASE, protocol_sha256=identifier(PROTOCOL), admission_sha256=ADMISSION,
        ordinary_parity_sha256=PARITY, ordinary_terminal_sha256=control["witness"]["evidence"]["detail"]["terminal_sha256"],
        host=config, products=products, surveys_in_worker=0,
        graph_family="same complete signed charted route, effective time before Graph"))
    print(seal)


def score(stage, pin):
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.scoring import distance_km

    seal = document(stage / "prediction-seal.json", pin)
    if (seal["case"] != CASE or seal["protocol_sha256"] != identifier(PROTOCOL)
            or seal["ordinary_parity_sha256"] != PARITY or seal["admission_sha256"] != ADMISSION):
        raise ValueError("Challenge forecast seal changed")
    ordinary_case = ordinary(stage)
    worker = document(stage / "centroid-receipt.json", seal["products"]["receipt_sha256"])
    clock = document(stage / "centroid-clock.json", seal["products"]["clock_sha256"])
    witness = document(stage / "centroid/exact-named-raw-witness.json", worker["witness_sha256"])
    out = worker["terminal"]
    p = stage / "centroid/fast-scan-automatic-work" / out["run_id"] / "terminal.json"
    terminal = document(p, out["terminal_sha256"])
    if (worker["acquisition_handoffs"] != 1 or worker["waveform_reads"] or clock["exit_code"]
            or terminal["native_sha256"] != ordinary_case["terminal"]["native_sha256"]):
        raise ValueError("Corrected publication did not use the verified saved input")
    baseline = ordinary_case["witness"]
    outcome = dict(case=CASE, seal=pin, corrected_clock=clock, ordinary_cached_clock=ordinary_case["timed_saved_clock"],
                   ordinary_raw_clock=ordinary_case["raw_clock"], graph_time=worker["graph_time"],
                   parity=ordinary_case["parity"], route={
                       mode: atom["solver_recipe"]["history_risk"] for mode,atom in
                       (("ordinary", baseline), ("corrected", witness))},
                   stop=out["decision"] != "complete")
    if not outcome["stop"]:
        evidence = witness["evidence"]
        if len(evidence["images"]) != 8 or evidence["grid"] != 179 or set(terminal["arms"]) != set(ARMS):
            raise ValueError("Expected both calibrated arms, matched grid and eight plots")
        reference = geography(CASE)
        arms = {}
        for arm in ARMS:
            a, b = (cell["arms"][arm] for cell in (ordinary_case["terminal"], terminal))
            e0, e1 = (1e3*distance_km(row["latlon"], reference) for row in (a, b))
            arms[arm] = dict(ordinary_error_m=e0, corrected_error_m=e1, change_m=e1-e0,
                             ordinary_rf_rms_hz=a["rf_rms_hz"], corrected_rf_rms_hz=b["rf_rms_hz"],
                             endpoint_shift_m=1e3*distance_km(a["latlon"], b["latlon"]),
                             owners=owner_delta(baseline["evidence"]["owner_rows"][arm], evidence["owner_rows"][arm]))
        outcome.update(arms=arms, stop=any(row["change_m"] > 250. for row in arms.values()),
                       figures=evidence["images"], grid=evidence["grid"])
    print(write(stage / "score.json", outcome))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("--score")
    args = parser.parse_args()
    if args.score:
        score(args.stage, args.score)
    else:
        run(args.stage)
