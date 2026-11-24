"""Verify both sealed field publications before joining the operator reference."""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from field_offer_translation import CASE, OFFER_PINS, RUNTIME, source_binding
from frozen_south_saved import digest, read
from frozen_south_saved_score import publication


REFERENCE = "reports/2026_11_21_ds30_full/reference-audit.json"
REFERENCE_SHA = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
ARMS = ("c0", "fitted_c")


def offset(center, point):
    east = (point[1] - center[1]) * 111.32 * math.cos(math.radians(center[0]))
    return east, (point[0] - center[0]) * 111


def read_clock(root, label):
    raw = (root / f"{label}.clock").read_text().splitlines()[-1]
    value = dict(item.split("=", 1) for item in raw.split())
    return {k: float(v) for k, v in value.items()} | {"exit_code": int((root / f"{label}.status").read_text())}


def score(root):
    bound = source_binding()
    from clean_saved_0169_trial import output_seal
    from tools import pipeline_eval

    research = RUNTIME.parents[2] / "tools/pipeline_eval"
    pipeline_eval.__path__.append(str(research))
    from tools.pipeline_eval.scoring import distance_km

    seal = root / "prediction-seal.json"
    if read(seal) != output_seal(root):
        raise ValueError("Both translated offers must match their pre-reference prediction seal")
    alternatives = {}
    for label in OFFER_PINS:
        clock = read_clock(root, label)
        if clock["exit_code"]:
            alternatives[label] = dict(clock=clock, failure=(root / f"{label}.stderr").read_text()[-2500:])
        else:
            alternatives[label] = publication(
                root / label, clock, f"{label}:integrated", read(bound.offers[label]), bound.authority,
                bound.recorded["native_sha256"], worker_name="field-translation-worker.json",
                expected_counts=bound.recorded["evidence"]["receipt"]["counts"],
            )
    source = RUNTIME.parents[2]
    reference = subprocess.check_output([
        "git", "-c", f"safe.directory={source}", "-C", str(source), "show", f"2d0ad2dfd:{REFERENCE}",
    ])
    if bound.batch.tagged_bytes(reference) != bound.batch.tagged(REFERENCE_SHA):
        raise ValueError("The operator reference audit changed")
    row, = (item for item in json.loads(reference)["cases"] if item["dataset_label"] == CASE)
    if not row["authority_eligible"] or not row["sealed_metadata_digests_verified"]:
        raise ValueError("Expected the prior authenticated operator reference")
    truth = [row["reference"][key] for key in ("latitude_deg", "longitude_deg")]
    original = bound.recorded["evidence"]
    original_arms = original["arms"]
    summary = {}
    for label in ("original", *OFFER_PINS):
        baseline = label == "original"
        alternative = None if baseline else alternatives[label]
        region = bound.original if baseline else read(bound.offers[label])
        clearance = region["width_km"]/2 - max(map(abs, offset(region["center"], truth)))
        offer_shift = offset(bound.original["center"], region["center"])[0]
        if not baseline and "failure" in alternative:
            summary[label] = dict(decision="failed", clearance_km=clearance, centre_shift_km=offer_shift,
                                  region=region, arms={name: None for name in ARMS})
            continue
        arms = original_arms if baseline else alternative["terminal"]["arms"]
        terminal = bound.recorded["outcome"] if baseline else alternative["receipt"]["decision"]
        samples = {}
        for name, values in arms.items():
            point = values["latlon"]
            start = original_arms[name]["latlon"]
            move = None if point is None else distance_km(start, point)
            displacement = None if point is None else offset(start, point)
            samples[name] = dict(latlon=point, error_km=distance_km(truth, point), conditional_rf_rms_hz=values.get("rf_rms_hz"),
                                 published_movement_km=move, east_north_movement_km=displacement,
                                 fraction_of_translation=None if baseline or move is None else move/abs(offer_shift),
                                 signed_east_fraction=None if baseline or move is None else displacement[0]/offer_shift,
                                 owners=None if baseline else len(alternative["ordered_owners"].get(name, ())))
        summary[label] = dict(decision=terminal, clearance_km=clearance, centre_shift_km=offer_shift, region=region,
                              arms=samples, figures=len(bound.recorded["figures"] if baseline else alternative["figures"]),
                              grid_points=bound.recorded["grid_points"] if baseline
                              else (0 if alternative["grid"] is None else alternative["grid"]["evaluated_points"]))
    evidence = dict(schema="ds30-original-offer-translation-v1", subject=CASE, waveform_reads=0,
                    source=bound.audit, seal_sha256=digest(seal), reference_sha256=REFERENCE_SHA,
                    summary=summary, original_control=original, alternatives=alternatives)
    bound.batch.write(root / "result.json", evidence)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
