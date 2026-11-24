"""Screen complete-cycle short omissions before running a saved position fit."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

HERE = Path(__file__).resolve().parent


def keep_slot(index):
    cycle, slot = divmod(index, 8)
    return slot == 0 or cycle % 3 != 2


def project(original, recipe):
    from continued_cfo_trial import rebinding
    from tools.pipeline_eval.variants.capture_bursts import visit_pairs
    from whole_stereo_blocks import inventories

    inventories(original)
    counters = Counter()
    kept, omitted = Counter(), Counter()
    visits, rows = [], []
    for visit, pair in visit_pairs(original["source"]["probes"]):
        stream = tuple(pair[0][k] for k in ("edge", "channel", "actual_rf_hz"))
        index = counters[stream]
        counters[stream] += 1
        mode = "short_primary" if index % 8 else "full"
        if keep_slot(index):
            kept[mode] += 2
            rows.extend(pair)
        else:
            omitted[mode] += 2
            visits.append(visit)
            rows.extend(dict(row, candidates=[]) for row in pair)
    policy = dict(recipe, whole_cycle_stereo=dict(implementation_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  parent=original["provenance"]["detector_sha256"], rule="Keep anchors and every short visit in cycles 0,1 modulo 3 per RF/channel/edge"))
    return rebinding(original, rows, policy), policy, dict(paid_native_lanes=dict(kept), skipped_native_lanes=dict(omitted),
                                                        skipped_stereo_visits=visits)


def run(case, root):
    from anchor_exposure import PINS, packet
    from eight_ms_held_fit import RECEIVER_RECIPE_PINS, select
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from whole_stereo_blocks import load_checked
    from whole_stereo_8ms import EIGHT_RAW, SAVED_SEAL, SAVED_PIN, coverage, price

    source, pin = PINS["DS30-0016" if case == "weak" else case]["8ms"]
    original = packet(source, pin)
    meta = load_checked(Path(source) / "full-short-recipe.json", RECEIVER_RECIPE_PINS[case])
    control = load_checked(SAVED_SEAL, SAVED_PIN)["runs"][case]["history8"]
    full, full_witness = select(original, meta["recipe"])
    if canonical_digest(full) != control["identity"]["native_sha256"]:
        raise ValueError("Original all-visit history disagrees with the published 8 ms packet")
    root.mkdir()
    start = process_time()
    paid, rule, schedule = project(original, meta["recipe"])
    selected, witness = select(paid, rule)
    native_path = root / "detections.json"
    immutable_json(native_path, selected)
    if "sha256:" + sha256(native_path.read_bytes()).hexdigest() != witness["native_sha256"]:
        raise ValueError("Saved handoff failed readback")
    charged = process_time() - start
    audit = (load_checked(HERE/"measurements/eight-ms-native-live.json.gz", EIGHT_RAW)["scientific_seal"]["raw"]["receiver_audit"]
             if case == "north" else meta["receiver_audit"])
    cost = price(audit, schedule, charged)
    stats = coverage(original, paid, full, selected, schedule["skipped_stereo_visits"])
    plan = dict(case=case, identity=control["identity"], original_sha256=pin, schedule=schedule, full_witness=full_witness,
                masked_witness=witness, cost=cost, actual_selected_coverage=stats,
                admit=witness["choice"]["route"] == full_witness["choice"]["route"] and cost["modeled_incremental_after_planning_cpu_s"] > 0)
    (root/"plan.json").write_text(json.dumps(plan, sort_keys=True, indent=2))
    return {k: plan[k] for k in ("case", "cost", "admit")} | dict(route=witness["choice"], selected=witness["selected"])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    args.root.mkdir()
    print(json.dumps([run(case, args.root/case) for case in ("north", "weak")], indent=2))
