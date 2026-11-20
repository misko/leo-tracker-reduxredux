"""Generate scorer-only location labels and independent near-edge roof offers."""

import argparse
from hashlib import sha256
from pathlib import Path

import numpy as np
from scipy.optimize import root

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..__main__ import encoded, save_json
from ..variants.projected_fit import Region
from . import native_clock_full as clock

REPORT = clock.REPORT.parent.parent / "refinement/boundary-roof"
WORK = clock.WORK.with_name("boundary-roof")
SEED = "roof-face-v1:"
CONDITIONS = ("original", "near-inside", "near-outside", "six-outside")
FACES = ("east", "west", "north", "south")
NORMALS = np.array(((1, 0), (-1, 0), (0, 1), (0, -1)))
phase = clock.phase


def keyed(purpose, key):
    return sha256(f"{SEED}{purpose}:{key}".encode()).hexdigest()


def fraction(digest):
    return int(digest[:13], 16) / 16**13


def roster(plan):
    prior = phase._read(clock.PREPARED / "source-lock.json")["cases"]
    joint = phase._read(clock.base.REPORT / "roster.json")["cases"]
    dev = {i for values in prior.values() for i in values} | {q["recording"] for q in joint}
    recorded = [q["recording"] for q in plan["cases"] if q["cohort"] == "roof"]
    arms = {}
    for prefix in ("DS26", "DS29"):
        arms[prefix] = sorted(
            (i for i in recorded if i.startswith(prefix + "-")),
            key=lambda i: (i in dev, keyed("roster", i)),
        )[:8]
    if any(len(ids) != 8 for ids in arms.values()):
        raise ValueError("the exact DS26 and DS29 recordings are required")
    return dict(
        primary=arms["DS26"][:5] + arms["DS29"][:5], reserve=arms["DS26"][5:] + arms["DS29"][5:]
    )


def tangent(point, center):
    origin = geodetic_to_ecef_km(*center, 0)
    frame = ecef_to_enu_matrix(*center)
    delta = geodetic_to_ecef_km(*point, 0) - origin
    up = ecef_to_enu_matrix(*point)[2]
    return frame[:2] @ (delta - up * ((frame[2] @ delta) / (frame[2] @ up)))


def build_offers(ident, truth, original):
    angle = int(keyed("face", ident)[:2], 16) % 4
    normal = NORMALS[angle]
    perpendicular = np.array((-normal[1], normal[0]))
    distance = 1 + fraction(keyed("distance", ident))
    along = 8 * fraction(keyed("along", ident)) - 4
    surface = Region("", truth, geodetic_to_ecef_km(*truth, 0), ecef_to_enu_matrix(*truth))
    for condition, requested in zip(CONDITIONS, (None, distance, -distance, -6.0), strict=True):
        tile = dict(original, id=keyed("tile", ident + ":" + condition)[:20], width_km=25.0)
        face = None
        if requested is not None:
            target = (12.5 - requested) * normal + along * perpendicular

            def mismatch(x, target=target):
                return tangent(truth, surface.site(x)[1]) - target

            result = root(mismatch, -target)
            if np.max(np.abs(mismatch(result.x))) > 1e-6:
                raise ValueError("could not create the requested tangent-plane offer")
            tile["center"] = surface.site(result.x)[1]
            face = FACES[angle]
        margin = float(12.5 - np.max(np.abs(tangent(truth, tile["center"]))))
        if requested is not None and abs(requested - margin) > 1e-6:
            raise ValueError("generated square is inconsistent with its target margin")
        yield (
            tile,
            dict(
                id=keyed("query", ident + ":" + condition)[:20],
                recording=ident,
                condition=condition,
                truth=truth,
                face=face,
                requested_margin_km=requested,
                true_margin_km=margin,
            ),
        )


def generate(work, bundle, cohort):
    original, _ = clock.prepare(bundle)
    ids = roster(original)
    originals = {q["recording"]: q for q in original["cases"] if q["cohort"] == "roof"}
    truth = {
        r["id"]: r["truth"]
        for panel in ("ds26-common127", "roof16")
        for r in phase.corpus.references(panel)
    }
    rows, labels = [], []
    for ident in ids[cohort]:
        source = originals[ident]["packet"]
        for tile, label in build_offers(ident, truth[ident], source["offer"]):
            packet = dict(source, offer=tile)
            labels.append(dict(label, tile=tile, input_sha256=phase.corpus._sha(encoded(packet))))
            rows.append(dict(id=label["id"], recording=ident, cohort=cohort, packet=packet))
    rows.sort(key=lambda q: keyed("order", q["id"]))
    work.mkdir(parents=True, exist_ok=False)
    save_json(work / "evaluator.json", dict(cohort=cohort, reserved_ids=ids, labels=labels))
    save_json(
        work / "requests.json",
        dict(
            cohort=cohort,
            cases=rows,
            source=original["source"],
            evaluator_sha256=phase.digest(work / "evaluator.json"),
            clock_plan_sha256=phase.digest(clock.REPORT / "plan.json"),
            protocol_sha256=phase.digest(REPORT / "PROTOCOL.md"),
            generator_sha256=phase.digest(Path(__file__)),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort", choices=("primary", "reserve"))
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--bundle", type=Path, default=clock.base.BUNDLE)
    args = parser.parse_args()
    generate(args.work / args.cohort, args.bundle, args.cohort)


if __name__ == "__main__":
    main()
