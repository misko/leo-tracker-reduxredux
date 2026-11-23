"""Replay public v3 offers from signed detections and score local exterior evidence."""

import argparse
import gzip
import json
import runpy
from contextlib import ExitStack
from functools import partial
from hashlib import sha256
from math import cos, radians
from pathlib import Path
from tempfile import TemporaryDirectory
from time import process_time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
EARLIER = HERE.parent / "single-core-2x"
MEASUREMENTS = EARLIER / "measurements"
VARIANT = HERE.parents[2] / "tools/pipeline_eval/variants/experimental/geographic_jackknife.py"
SPEC = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
ENVELOPE = "94ed84e12dd7c809e21d185d2bb7f1ef1a13208d20835e2d20cafd8afc2e2890"
MIRRORS = "ee8f80ec6267e7fe333d05ac794775fb54bc349cd143022a55599bf2f9af4728"
ORIGINAL = "735553ef3b9287884f6473bfc78bd8740e45c23927c79c56d95b0ba53376bb4a"
KEY = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"
SAVED_OUTSIDE = {
    "north": "283375bbad24eee8a0871a7e878c906fd1471158e7ff070d913f9be8d1267dd7",
    "south": "5181abf1c8a36d45dfe140e8851f0a423b69ec69b8ca231a3f87bcc9fdcecca9",
}
SITES = {
    "north": (
        "0abe7b4514be674d9f5388e3",
        "9bf5dc4e3ef1e2df17f8d8184bca74f2ce9559a1e154401b9f6330f8e97feaeb",
    ),
    "south": (
        "6bd1f26bfa0bedfcf3f100f8",
        "48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0",
    ),
}
CASES = ("centered", "inside", "outside")


def verified(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Saved input digest changed: {path}")
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def write(path, value):
    with path.open("x") as stream:
        print(json.dumps(value, sort_keys=True, indent=2, allow_nan=False), file=stream)


def public_inputs(site, case):
    saved = verified(MEASUREMENTS / "regional-doppler-envelope.json", ENVELOPE)["saved_pairs"]
    original = saved[f"{site}-containing"]["stock"]
    pair = Path(original["source_pair"])
    verified(pair, SITES[site][1])
    if case == "centered":
        offers = verified(MEASUREMENTS / "regional-reassignment.json.gz", ORIGINAL)
        offer = offers[f"{site}-containing"]["offer"]
    else:
        offers = verified(MEASUREMENTS / "region-mirrors.json.gz", MIRRORS)["sites"]
        offer = offers[site][case]["offer"]
    return original, pair, offer


def selected_likelihood(context, arm, problem):
    import numpy as np

    from leo.analysis.localization_v3 import recovery_inventory
    from leo.analysis.localization_v3.reassociation_context import objective

    if context["families"]:
        raise ValueError("The selected evidence is not the signed v3 curved/predictive model")
    curved = [(row["candidate_norad"], part)
              for row, part in zip(problem.rows, problem.slices, strict=True)]
    entries = context["entries"]
    groups = sorted(
        {norad for norad, part in curved if problem.keep[part].any()}
        | {entry["norad"] for entry in entries}
    )

    def rebuilt_loss(omit):
        keep = np.array(problem.keep, copy=True)
        for norad, part in curved:
            if norad == omit:
                keep[part] = False
        if not keep.any():
            return lambda _point: float("nan")
        reduced = recovery_inventory.make_event_problem(
            context["scan"], context["node"], keep, arm, problem.reference,
            context["powers"], context["means"], context["model"], [],
        )
        retained = [entry for entry in entries if entry["norad"] != omit]
        recovery_inventory.attach_event_predictive(reduced, retained, context["powers"])
        return partial(objective, reduced, context)

    return partial(objective, problem, context), rebuilt_loss, groups


def replay(site, case, path):
    from tools.pipeline_eval.variants.experimental import lean_startup

    original, pair, offer = public_inputs(site, case)
    frozen_replay = runpy.run_path(str(EARLIER / "regional_envelope_trial.py"))["run"]
    install = lean_startup.install
    gate = {}

    with TemporaryDirectory(dir=path.parent) as directory, ExitStack() as stack:
        alternate = Path(directory) / "offer.json"
        write(alternate, offer)

        def install_readout():
            install()
            from tools import algo08_position

            variant = runpy.run_path(str(VARIANT))
            prepare = algo08_position.prepare_packet

            def readout(context, owners, expected, *args, **kwargs):
                packet = prepare(context, owners, expected, *args, **kwargs)
                start = process_time()
                half_width = context["scan"].search_region.half_width_km
                arms = {
                    arm: variant["diagnose"](
                        *selected_likelihood(context, arm, problem), endpoint, half_width
                    )
                    for arm, (problem, endpoint) in context["problems"].items()
                }
                gate.update(cpu_s=process_time() - start, arms=arms,
                            state=variant["paired_state"](arms))
                return packet

            stack.enter_context(patch.object(algo08_position, "prepare_packet", readout))

        stack.enter_context(patch.object(lean_startup, "install", install_readout))
        result = frozen_replay(pair, path, mode="stock", alternate_offer=alternate)
    if (
        result["offer"] != offer or result["archive"] != original["archive"]
        or result["source_sha256"] != original["source_sha256"] or result["specification"] != SPEC
        or (case == "inside" and result["terminal"] != original["terminal"])
        or (result["terminal"]["status"] == "ok") != bool(gate)
    ):
        raise ValueError("The replay differs from the pinned signed build, inputs or inside result")
    write(path, dict(site=site, case=case, pair_sha256=SITES[site][1], offer=offer,
                     source_sha256=result["source_sha256"], archive=result["archive"],
                     solver_specification=SPEC, signed=result["terminal"],
                     regional_guard=result["regional_guard"], gate=gate, elapsed=result["elapsed"]))


def score_case(result, truth):
    from tools.pipeline_eval.scoring import ARMS, distance_km

    region = result["offer"]
    half = region["width_km"] / 2
    lat, lon = region["center"]
    east = (truth[1] - lon) * 111.32 * cos(radians(lat))
    north = (truth[0] - lat) * 111.
    faces = dict(west=half + east, east=half - east, south=half + north, north=half - north)
    face = min(faces, key=faces.get)
    signed, gate = result["signed"], result["gate"]
    for row in signed["arms"].values():
        row["horizontal_error_km"] = (
            distance_km(row["latlon"], truth) if row["latlon"] is not None else None
        )
    result.update(truth_clearance_km=faces[face], closest_truth_face=face,
                  stock_publish=signed["status"] == "ok")
    result["gate_publish"] = result["stock_publish"] and gate["state"] != "exterior"
    result["arm_publish"] = {
        arm: result["stock_publish"] and gate["arms"][arm]["state"] != "exterior"
        for arm in ARMS
    }
    return result


def require_saved_outside(site, result):
    digest = SAVED_OUTSIDE[site]
    archived = verified(MEASUREMENTS / f"exact-curved-lookahead-{site}-offers.json", digest)
    case = archived["results"][f"{site}-mirror-outside"]
    signed = result["signed"]
    if (
        archived["archive"] != result["archive"]
        or archived["native_sha256"] != result["source_sha256"]
        or archived["pair_sha256"] != result["pair_sha256"]
        or archived["specification"] != result["solver_specification"]
        or case["offer"] != result["offer"]
        or case["science"] != signed["evidence"]
        or any(case[key] != signed[key]
               for key in ("status", "reason", "arms", "owners", "associated", "orbit_policy"))
    ):
        raise ValueError("Close omission differs from the archived signed v3 solve")
    return digest


def score(directory, path):
    key = verified(HERE.parent / "regional-release/scoring-key.json", KEY)["answers"]
    truths = {row["recording"]: row["truth"] for row in key.values()}
    results = []
    for site, (recording, _) in SITES.items():
        for case in CASES:
            saved = directory / f"{site}-{case}.json"
            data = saved.read_bytes()
            row = json.loads(data)
            original, _, offer = public_inputs(site, case)
            if (
                (row["site"], row["case"], row["offer"]) != (site, case, offer)
                or row["source_sha256"] != original["source_sha256"]
                or row["archive"] != original["archive"]
                or row["solver_specification"] != SPEC
                or row["pair_sha256"] != SITES[site][1]
            ):
                raise ValueError(f"Scoring input differs from the pinned signed case: {saved}")
            row["inference_sha256"] = sha256(data).hexdigest()
            if case == "outside":
                row["archived_signed_sha256"] = require_saved_outside(site, row)
            elif case == "inside":
                if row["signed"] != original["terminal"]:
                    raise ValueError("Containing offer differs from the archived signed v3 solve")
                row["archived_signed_sha256"] = ENVELOPE
            results.append(score_case(row, truths[recording]))
    saved = verified(MEASUREMENTS / "regional-doppler-envelope.json", ENVELOPE)["saved_pairs"]
    far = saved["north-omitted"]["stock"]
    if far["terminal"]["reason"] != "both_receivers_support_far_exterior":
        raise ValueError("Expected the archived positive exterior control")
    results.append(score_case(dict(site="north", case="far", signed=far["terminal"], gate={},
                                  offer=far["offer"], source_sha256=far["source_sha256"],
                                  archive=far["archive"], solver_specification=far["specification"],
                                  regional_guard=far["regional_guard"], inference_sha256=ENVELOPE),
                              truths[SITES["north"][0]]))
    write(path, dict(scoring_key_sha256=KEY, results=results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("replay")
    run.add_argument("site", choices=SITES)
    run.add_argument("case", choices=CASES)
    run.add_argument("output", type=Path)
    evaluate = commands.add_parser("score")
    evaluate.add_argument("input", type=Path)
    evaluate.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "replay":
        replay(args.site, args.case, args.output)
    else:
        score(args.input, args.output)


if __name__ == "__main__":
    main()
