"""Compare sealed blind Doppler proposals with the original development references."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from unordered_doppler_trial import CASES, HERE


NORTH_KEY = HERE.parent / "regional-release/scoring-key.json"
NORTH_KEY_PIN = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"
NORTH_ID = "0abe7b4514be674d9f5388e3"
PHYSICAL = "903333eb790009a125088b645a543f15789bb6bc:reports/2026_11_21_ds30_full/reference-audit.json"
PHYSICAL_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
ARC = HERE / "measurements/arc-doppler-start.json.gz"
ARC_PIN = "e4bc65d8db839fd7e0109c317f5cbc5a51db8dd9d643f65f95a5fdb542391a86"
EXPECTED = ("inside", "inside", "exterior", "exterior")


def digest(blob):
    return sha256(blob).hexdigest()


def checked(data, pin):
    if digest(data) != pin:
        raise ValueError("Reference or original receipt differs from the frozen published version")
    return data


def original_references():
    repo_truth = subprocess.check_output(["git", "show", PHYSICAL], cwd=HERE)
    physical, = [case for case in json.loads(checked(repo_truth, PHYSICAL_PIN))["cases"]
                 if case["dataset_label"] == "DS30-0016" and case["authority_eligible"]]
    north, = {tuple(row["truth"]) for row in json.loads(checked(
        NORTH_KEY.read_bytes(), NORTH_KEY_PIN))["answers"].values() if row["recording"] == NORTH_ID}
    row = physical["reference"]
    return (row["latitude_deg"], row["longitude_deg"]), north


def rank(points, method, truth, stock, receivers):
    from tools.pipeline_eval.scoring import distance_km

    order = sorted(range(len(points)), key=lambda i: points[i][method + "_loss"])
    best = points[order[0]]
    inside = next(points[i] for i in order if points[i]["side"] == "inside")
    outside = next(points[i] for i in order if points[i]["side"] == "exterior")
    gain = inside[method + "_loss"] - outside[method + "_loss"]
    signed = {row["track"]: (row["norad"], row["alias"]) for row in best[method] if row is not None}
    return dict(
        rank=order, xy_km=best["xy_km"], latlon=best["latlon"], loss=best[method + "_loss"],
        error_km=distance_km(truth, best["latlon"]),
        side="inside" if gain < 0 else "exterior" if gain > 0 else "tie",
        exterior_gain=gain, paired=len(best["pairs"]) if method == "joint" else 0,
        matched=len(signed), matched_receiver_support=sorted({receivers[key] for key in signed}),
        exact_original_owner_alias_matches=(sum(stock.get(k) == v for k, v in signed.items())
                                             if stock else None),
    )


def score(directory, output, full):
    docs = {}
    pins = {}
    for case in CASES:
        blob = (directory / f"{case}.json").read_bytes()
        row = json.loads(blob)
        if row["case"] != case or len(row["points"]) != 33 or any(
                digest((HERE / name).read_bytes()) != pin for name, pin in row["pins"].items()):
            raise ValueError("Sealed probes came from different code or a changed roster")
        docs[case] = row
        pins[case] = digest(blob)
    if len({(docs[case]["binding"]["native_sha256"], docs[case]["cutoff_utc_ns"],
             docs[case]["binding"]["archive"]["snapshots_sha256"]) for case in CASES[1:]}) != 1:
        raise ValueError("All three North offers require the same detector and causal cutoff")
    weak, north = original_references()
    prior = json.loads(gzip.decompress(checked(ARC.read_bytes(), ARC_PIN)))["cases"]
    rows = {}
    for case, side in zip(CASES, EXPECTED, strict=True):
        document = docs[case]
        truth = weak if case == "weak" else north
        former = prior["weak" if case == "weak" else "north"]["receipt"]
        if document["binding"]["native_sha256"] != former["input"]["native_sha256"]:
            raise ValueError("The original full-data cold control used a different signed packet")
        containing = side == "inside"
        stock = {x[0]: tuple(x[2:]) for x in former["original_branch"]["selected_signature"]}
        args = truth, stock if containing else {}, {arc["track"]: arc["receiver"] for arc in document["arcs"]}
        independent = rank(document["points"], "independent", *args)
        coupled = rank(document["points"], "joint", *args)
        scout_seconds = document["clocks_ns"]["total"] / 1e9
        fallback_seconds = former["clocks"]["original_cold"]["cpu_s"] if containing else None
        rows[case] = dict(
            input=document["binding"], expected_side=side,
            independent=independent, joint=coupled,
            same_top_coordinate=independent["xy_km"] == coupled["xy_km"],
            eligible_pairs=len(document["eligible_pairs"]), arc_count=len(document["arcs"]),
            sampled_times=document["sampled_times"], catalogue=document["catalogue"],
            clocks_ns=document["clocks_ns"], common_preparation_cpu_ns=document["preparation_cpu_ns"],
            original_cold_cpu_s=fallback_seconds,
            hypothetical_fallback_with_scout_cpu_s=(
                fallback_seconds + scout_seconds if fallback_seconds is not None else None),
        )
    gate = all(row["joint"]["side"] == row["expected_side"] and (
        row["joint"]["error_km"] < row["independent"]["error_km"] or row["expected_side"] == "exterior"
    ) for row in rows.values())
    receipt = dict(cases=rows, passed=gate, blind_sha256=pins,
                   sources=dict(physical=PHYSICAL_PIN, north=NORTH_KEY_PIN, arc=ARC_PIN,
                                scorer=digest(Path(__file__).read_bytes())),
                   position_fits=0, waveform_reads=0, completed_offers=len(rows))
    summary = (json.dumps(receipt, allow_nan=False, indent=2, sort_keys=True) + "\n").encode()
    archive = (json.dumps(dict(receipt=receipt, blind=docs), allow_nan=False,
                          separators=(",", ":"), sort_keys=True) + "\n").encode()
    with output.open("xb") as stream:
        stream.write(summary)
    with full.open("xb") as stream:
        stream.write(gzip.compress(archive, mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("directory", "output", "full"):
        parser.add_argument(argument, type=Path)
    score(**vars(parser.parse_args()))
