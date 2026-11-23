"""Score the sealed published-map estimates on their original development references."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from aperture_trial import ARMS, read, write
from geographic_peak import HERE, MAPS, MAPS_PIN, OFFERS, file_sha, frozen_json


MEASUREMENTS = HERE / "measurements"
ARCHIVED = HERE.parent / "single-core-2x/measurements"
KEY = HERE.parent / "regional-release/scoring-key.json"
KEY_PIN = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"
INDIA_TREE = "e7d513fc8e745d48f9dce3974ba19443b889c649"
INDIA_TRUTH_PIN = "683e5739e28fc4f9d444f6debf768966175d5acf33e9477b8643e8642a6f42f5"
INDIA_PIN = "3879605a5b35d2bbb9e714cb9bd5ce1f40cb28d43ec6443ff6772879e3641913"
MIRRORS_PIN = "ee8f80ec6267e7fe333d05ac794775fb54bc349cd143022a55599bf2f9af4728"
EDGE_PIN = "da410c13c061713d1c9a482ac54f81bdaef2ecb886d56440be568f3f28615a28"
JACKKNIFE_PIN = "f811b67eb0c90cdf8f64090a7a42232d161af4cccf12a065536eb618e9dcc536"
RECORDINGS = dict(north="0abe7b4514be674d9f5388e3", south="6bd1f26bfa0bedfcf3f100f8")
EVIDENCE = ("points", "catalogue_orbits", "potentially_visible_orbits", "track_count", "graph_points",
            "original_points", "receiver_points", "snapshots")


def public_india(name):
    return subprocess.check_output(["git", "show", f"{INDIA_TREE}:{name}"], cwd=HERE)


def references():
    offered = frozen_json(KEY, KEY_PIN)["answers"]
    result = {}
    for site, recording in RECORDINGS.items():
        result[site], = {tuple(row["truth"]) for row in offered.values() if row["recording"] == recording}
    released = public_india("truth-after-lock.json.gz")
    locked = json.loads(public_india("score-lock.json"))["files"]["truth-after-lock.json.gz"]
    if locked != INDIA_TRUTH_PIN or sha256(released).hexdigest() != INDIA_TRUTH_PIN:
        raise ValueError("The public India location reference changed")
    result["india"] = json.loads(gzip.decompress(released))["scene"]["coordinate"]
    return result


def summarize_position(point, width, truth):
    from tools.pipeline_eval.scoring import distance_km

    if point is None:
        return None
    clearance = width / 2 - max(map(abs, point["xy_km"]))
    return dict(**point, clearance_km=clearance, contained=clearance >= 0.,
                horizontal_error_km=distance_km(point["latlon"], truth))


def calibration(arms, truth, offer):
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    scored = {}
    for arm in ARMS:
        data = arms[arm]
        point = data.get("latlon")
        scored[arm] = dict(latlon=point, rf_rms_hz=data.get("rf_rms_hz"),
                           clearance_km=None if point is None else face_clearance_km(offer, point),
                           horizontal_error_km=None if point is None else distance_km(point, truth))
    return scored


def pinned_proposals(path):
    sealed = read(path)
    if (sealed["input_sha256"] != MAPS_PIN or set(sealed["sites"]) != set(OFFERS)
            or any(file_sha(HERE / name) != pin for name, pin in sealed["source_sha256"].items())):
        raise ValueError("Expected the frozen solver-independent location estimates")
    return sealed


def validate_evidence(estimate, frozen, original, native_sha):
    from leo.contracts.digests import canonical_digest

    evidence = {key: original[key] for key in EVIDENCE}
    if (any(row["offer"] != original["offer"] for row in (estimate, frozen))
            or original["native_sha256"] != native_sha or frozen["points"] != evidence["points"]
            or estimate["full_score_sha256"] != frozen["full_score_sha256"]
            or canonical_digest(evidence) != estimate["full_score_sha256"]):
        raise ValueError("The proposal differs from the original ordered coordinates or scored native evidence")


def score(estimate_path, summary_path, full_path):
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km

    estimated = pinned_proposals(estimate_path)
    archive = frozen_json(MAPS, MAPS_PIN)["sites"]
    india = frozen_json(MEASUREMENTS / "india-regional-diagnostic.json.gz", INDIA_PIN)["runs"]
    mirrors = frozen_json(ARCHIVED / "region-mirrors.json.gz", MIRRORS_PIN)
    edge = frozen_json(ARCHIVED / "edge-solvers.json.gz", EDGE_PIN)
    signed = frozen_json(MEASUREMENTS / "geographic-jackknife.json", JACKKNIFE_PIN)
    if signed["scoring_key_sha256"] != KEY_PIN:
        raise ValueError("The same-offer published fits use a different reference key")
    truth = references()

    records, count = {}, {name: Counter() for name in ("discrete", "interpolated_only", "interpolated_with_fallback")}
    for site, cases in OFFERS.items():
        data = estimated["sites"][site]
        frozen = archive[site]
        site_native = data["native_sha256"]
        if frozen["native_sha256"] != site_native or set(data["offers"]) != set(cases):
            raise ValueError("Expected one original detector packet with exactly two public offers per site")
        for name in cases:
            row = data["offers"][name]
            old = frozen["offers"][name]
            prior = {}
            if site == "india":
                matched = india[name]["stock"]
                native, offer = (matched["identity"][key] for key in ("document_sha256", "offer"))
                original = dict(matched["full_diagnostic"], offer=offer, native_sha256=native)
                for route, record in india[name].items():
                    if record["identity"]["document_sha256"] != site_native or record["identity"]["offer"] != offer:
                        raise ValueError("India fitted position cannot be matched to its regional score map")
                    prior["v3_" + route] = dict(status=record["status"], same_packet=True, arms=calibration(record["arms"], truth[site], offer))
            else:
                original = mirrors["sites"][site][name]
                offer = original["offer"]
                if name == "inside" or site == "north":
                    exact = edge[f"{site}-solver.json"] if name == "inside" else mirrors["north_stock_position"]
                    if exact["region"] != offer or exact["native_sha256"] != site_native:
                        raise ValueError("An exact-packet original position cannot be matched to the score map")
                    prior["original_same_packet"] = dict(status=exact["decision"]["status"], same_packet=True,
                                                         arms=calibration(exact["decision"]["arms"], truth[site], offer))
                same_offer, = [r for r in signed["results"] if r["site"] == site and r["case"] == name and r["offer"] == offer]
                prior["published_v3_same_waveform"] = dict(status=same_offer["signed"]["status"],
                    same_packet=same_offer["source_sha256"].removeprefix("sha256:") == site_native,
                    native_sha256=same_offer["source_sha256"], arms=calibration(same_offer["signed"]["arms"], truth[site], offer))
            validate_evidence(row, old, original, site_native)
            clearance = face_clearance_km(offer, truth[site])
            contains = clearance >= 0.
            if contains != (name in ("matched-tile", "inside")):
                raise ValueError("The published inside or omitted offer no longer matches its reference")
            discrete, fitted = (summarize_position(row[k], offer["width_km"], truth[site]) for k in ("discrete", "interpolated"))
            for label, estimate in zip(count, (discrete, fitted, discrete if fitted is None else fitted), strict=True):
                if estimate is None:
                    count[label]["abstained"] += 1
                elif estimate["contained"]:
                    count[label]["correctly_inside" if contains else "missed_omission"] += 1
                else:
                    count[label]["false_exterior" if contains else "correctly_exterior"] += 1
            score_delta = None if fitted is None else fitted["horizontal_error_km"] - discrete["horizontal_error_km"]
            records[f"{site}-{name}"] = dict(site=site, name=name, offer=offer, native_sha256=site_native,
                truth_clearance_km=clearance, truth_contained=contains, discrete=discrete, interpolated=fitted,
                interpolation_status=row["status"], error_delta_km=score_delta, own_reference_clock=row["interpolation"],
                original_terminal=row["original_terminal"], extra_score_evaluations=row["additional_scores"],
                full_score_clock=row["full_probe_clock"], archived_calibration=prior)
    results = dict(offers=records, verdicts={key: dict(value) for key, value in count.items()},
                   estimate_sha256=file_sha(estimate_path), score_archive_sha256=MAPS_PIN,
                   source_sha256=dict(public_north_south=KEY_PIN, public_india_truth=INDIA_TRUTH_PIN,
                                      original_india_comparison=INDIA_PIN, original_mirror_comparison=MIRRORS_PIN,
                                      same_packet_edge_comparison=EDGE_PIN, same_offer_v3_comparison=JACKKNIFE_PIN))
    write(summary_path, results)
    with full_path.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(summary=results, estimates=estimated), separators=(",", ":"),
                                              allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("estimate_path", "summary_path", "full_path"):
        cli.add_argument(name, type=Path)
    score(**vars(cli.parse_args()))
