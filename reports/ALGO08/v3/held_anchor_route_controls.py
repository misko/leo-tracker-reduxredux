"""Verify the opt-in selection against already sealed genuine receiver packets."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
CONTROLS = {
    "north": (Path("/dev/shm/leo-eight-ms-north/12ms"),
              "2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427",
              "9d9273756700f7318722bfbf0d8ece36be9991fc0184cefca7c696a919aacc44", "history",
              Path("/var/tmp/leo-north-short-causal-raw-nov23/containing"),
              "a03fefaf84057a282a0868ae8a52d34099f530dcf69220360147389e110523c3"),
    "DS30-0016": (Path("/dev/shm/leo-eight-ms-DS30-0016-warm/12ms"),
                  "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589",
                  "70594e676776ac7f1a12464865f7118c05b0126b236a2bed73616c0b8407ac1a", "unfiltered",
                  Path("/dev/shm/leo-eight-ms-DS30-0016-warm/12ms"),
                  "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"),
}


def document(root, digest):
    from empty_bootstrap import checked

    path, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    return path, json.loads(checked(path, digest))


def verified_original(root, detection_pin, recipe_pin):
    from empty_bootstrap import checked
    from full_short_run import RECIPE_SHA, checked_recipe
    from mixed_aperture_receiver import FULL_RULE

    path, native = document(root, detection_pin)
    source = native["source"]
    receipt = json.loads(checked(root / "full-short-recipe.json", recipe_pin))
    audit = receipt["receiver_audit"]
    dsos = audit["native"]
    if (receipt["saved_digest"] is not None or receipt["recipe"] != checked_recipe()
            or audit["detector_pin"] != RECIPE_SHA or audit["analysis_manifest"] != source["analysis_manifest_sha256"]
            or audit["recording_authority"] != source["raw_recording_authority_digest"]
            or audit["input_manifest"] != source["input_manifest_sha256"]
            or audit["selected"] != sum(len(row["candidates"]) for row in source["probes"])
            or dsos["rule"] != list(FULL_RULE) or set(dsos["native_calls"]) != {"full", "short_primary"}
            or sum(dsos["native_calls"].values()) != len(source["probes"])):
        raise ValueError("The saved data must bind the genuine full-coverage 20/12 ms acquisition")
    return path, native, receipt["recipe"]


def validate(output):
    from empty_bootstrap import SCIENTIFIC_IMPORTS, load_runtime
    from dense_geographic_trial import host
    from held_anchor_route_publication import prepare

    machine = host()
    load_runtime()
    output.mkdir()
    controls = {}
    for name, (folder, digest, recipe_pin, route, selected_root, chosen) in CONTROLS.items():
        _, packet, recipe = verified_original(folder, digest, recipe_pin)
        source = packet["source"]
        point = output / f"{name}-decision.json"
        selected, _, identity, receipt = prepare(packet, recipe, source["session_id"], source["input_manifest_sha256"], point)
        _, published = document(selected_root, chosen)
        if (receipt["choice"]["route"] != route or receipt["selected_native_sha256"] != "sha256:"+chosen
                or selected != published or published["provenance"]["detector_sha256"] != "sha256:"+identity):
            raise ValueError(f"Frozen {name} choice or chosen native bytes differ")
        controls[name] = dict(receipt=receipt, decision_file_sha256=sha256(point.read_bytes()).hexdigest(),
                              previous_chosen_verified=True, factors=sum(len(row["candidates"]) for row in selected["source"]["probes"]))
    loaded = [name for name in SCIENTIFIC_IMPORTS if name in sys.modules]
    if loaded:
        raise ValueError(f"Selection imports scientific modules before publication ({loaded})")
    result = dict(machine=machine, controls=controls, scientific_imports=loaded, waveform_calls=0, publications=0)
    with (output / "controls.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    validate(parser.parse_args().output)
