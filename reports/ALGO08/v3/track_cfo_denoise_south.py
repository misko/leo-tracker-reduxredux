"""Transfer the already frozen CFO blend to the original South history packet."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from .track_cfo_denoise import DATA, HERE, STREAM, describe, graph_pins, paired_rows, proposed_offsets, saved_only, signed
from .ds30_paired_inputs import digest


FREEZE = "be4d89302c90b2eee19ff930e4485de7ea22b0ef04e1ba216bf9734e47c4ddd1"
NAMED = Path("/tmp/leo-v3-integrated-south-controls/south-result.json")
NAMED_SHA = "e0ac0972934671d6536daed5ba64de4cf21f2d695bc51893c0720a08a7fef903"
SAVED_GRAPH = Path("/tmp/leo-v3-frozen-south-saved-01/containing-integrated/exact-named-raw-witness.json")
SAVED_GRAPH_SHA = "471f8a3caf27c472a0c8758eeab12af5b963070561edc1bfd0ec7b3adc5e373e"


def candidate():
    freeze = signed.document(DATA / "frozen-build-geography.json", FREEZE)
    history = freeze["south_existing_raw"]
    saved = freeze["proposed_saved_pair"]
    record = saved["packets"]["integrated"]
    path = Path(record["path"])
    origin = path.parents[3]
    seal = signed.document(origin / "prediction-seal.json", history["containing_prediction_seal_sha256"])
    bootstrap = "candidate/unified-short-bootstrap.json"
    selector = "candidate-held-anchor-route.json"
    raw = signed.document(origin / bootstrap, seal[bootstrap])
    held = signed.document(origin / selector, seal[selector])
    native = signed.read_native(path.parent, record["sha256"], path=path)
    source = native["source"]
    recipe = held["receiver_recipe"]
    opportunities = signed.opportunities(native)
    calls = Counter("short_primary" if row["short"] else "full" for row in opportunities.values())
    if (raw["held_anchor_route"] != held or raw["requested_offer_sha256"] != history["containing_offer_sha256"]
            or raw["native_sha256"] != "sha256:"+record["sha256"] or held["native_sha256"] != raw["native_sha256"]
            or signed.canonical(recipe) != native["provenance"]["detector_sha256"]
            or recipe["installed_sha256"] != signed.FULL or recipe["shortened_sha256"] != signed.SPARSE
            or recipe["aperture_samples"] != [200_000,80_000] or recipe["streams"] != list(STREAM[:3])
            or recipe["rule"] != ["full"] + ["short_primary"]*7
            or held["choice"]["route"] != "history" or held["refinement_calls"]
            or source["session_id"] != saved["session_id"]
            or source["input_manifest_sha256"] != "sha256:"+saved["inventory_sha256"]
            or source["raw_recording_authority_digest"] != "sha256:"+saved["raw_authority_sha256"]
            or len(source["probes"]) != 2_400 or raw["receiver_audit"]["native"]["native_calls"] != dict(calls)
            or held["selected"] != 456 or sum(len(p["candidates"]) for p in source["probes"]) != 456):
        raise ValueError("South does not supply the frozen signed 20/8 selected history packet")
    return saved, native, opportunities, raw["native_sha256"]


def predict():
    graph_pins()
    _, native, opportunities, sha = candidate()
    _, pieces, scope = signed.graph(native, opportunities)
    kept, changes, audit = proposed_offsets(pieces)
    return dict(case="South", route="history", candidate_native_sha256=sha, graph=scope,
                all_unambiguous_graph_shorts=kept, proposals=changes, eligibility=audit,
                protocol_sha256=digest((HERE / "track-cfo-denoise-south-protocol.md").read_bytes()))


def score(path, pin):
    plan = signed.document(path, pin)
    saved, mixed, opportunities, sha = candidate()
    witness = signed.document(SAVED_GRAPH, SAVED_GRAPH_SHA)
    recorded_graph = witness["ports"]["graph"]["graph"]
    if (plan["candidate_native_sha256"] != sha or witness["evidence"]["detail"]["input_sha256"] != sha
            or any(plan["graph"][key] != recorded_graph[key] for key in ("assigned", "tracks"))):
        raise ValueError("The South Graph differs from the original unretimed containing witness")
    original = saved["packets"]["installed"]
    control = signed.document(NAMED, NAMED_SHA)
    if (control["qualified"] is not True or control["named"]["native_sha256"] != "sha256:"+original["sha256"]
            or control["named"]["verified"]["raw_authority"] != "sha256:"+saved["raw_authority_sha256"]):
        raise ValueError("The archived installed measurements do not bind this South acquisition")
    source_path = Path(original["path"])
    native = signed.read_native(source_path.parent, original["sha256"], path=source_path)
    stock = signed.opportunities(native)
    signed.bind_pair(native, mixed, stock, opportunities)
    errors, coverage = paired_rows(stock, opportunities, plan)
    return dict(case=plan["case"], route=plan["route"], prediction_sha256=pin, graph=plan["graph"],
                n_proposals=len(plan["proposals"]), coverage=coverage, metrics=describe(errors),
                installed_native_sha256=original["sha256"], candidate_native_sha256=sha, graph_witness_sha256=SAVED_GRAPH_SHA)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("predict")
    compare = sub.add_parser("score")
    compare.add_argument("prediction", type=Path)
    compare.add_argument("sha256")
    args = parser.parse_args()
    sys.addaudithook(lambda event, values: saved_only(event, values, prediction=args.mode == "predict"))
    result = predict() if args.mode == "predict" else score(args.prediction, args.sha256)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
