"""Stage dedicated curvature-only cards using byte-identical sealed evidence."""

import json
from hashlib import sha256

from ..__main__ import ROOT, encoded, write

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-support/derivative-receiver"
METHOD = "polynomial_curvature_only"
SUFFIX = "-curvature-only"
TITLES = {
    "diagnostic": "Independent polynomial curvature on diagnostic roof recordings",
    "reserve": "Independent polynomial curvature on held roof recordings",
    "omitted": "Independent polynomial curvature with the true roof omitted",
    "simulated": "Independent polynomial curvature at two simulated sites",
    "field": "Independent polynomial curvature of measured StarLoc beacons",
}


def sealed(folder, file, expected):
    raw = (folder / file).read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError(f"{file} differs from its published digest")
    return raw


def preserve(path, raw):
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"{path.name} already has different content")
    else:
        write(path, raw)


def export(report=REPORT):
    target = report / "curvature-only"
    target.mkdir(exist_ok=True)
    original_digests = json.loads((report / "artifact-lock.json").read_bytes())["files"]
    descriptor = json.loads(sealed(report, "figures.json", original_digests["figures.json"]))
    cards = []
    for original in descriptor["charts"]:
        scope = original["id"].removeprefix("derivative_receiver-")
        name = original["seal"]
        prior = json.loads(sealed(report, name, original_digests[name]))
        (curvature,) = (row for row in original["series"] if row["value"] == METHOD)
        conditions = original.get("queries")
        assets = {*original["provenance"], curvature["file"]}
        if conditions:
            assets.add(conditions)
        files = {name: prior["files"][name] for name in sorted(assets)}
        for name, digest in files.items():
            preserve(target / name, sealed(report, name, digest))
        primary = dict(
            key="candidate" if conditions else "one",
            label="Independent polynomial curvature · publication",
            forced_label="Independent polynomial curvature · forced",
            file=curvature["file"],
            value=METHOD,
        )
        series = [primary]
        if scope in ("diagnostic", "reserve", "omitted"):
            # The slope feature was eligible in these cohorts. No such pairs supported field
            # or simulated output, where both modes have the same estimates.
            (differential,) = (row for row in original["series"] if row["value"] != METHOD)
            if differential["file"] != primary["file"]:
                raise ValueError("matched control uses an unexpected source file")
            control = dict(
                key="stock",
                label=differential["label"],
                file=differential["file"],
                value=differential["value"],
                match=curvature["match"],
            )
            if conditions:
                control["forced_label"] = differential["forced_label"]
            series.append(control)
        card = original | dict(
            id=original["id"] + SUFFIX,
            method=METHOD,
            title=TITLES[scope],
            seal=scope + SUFFIX + "-figure-lock.json",
            series=series,
        )
        preserve(target / card["seal"], encoded(dict(cases=prior["cases"], files=files)) + b"\n")
        cards.append(card)
    preserve(target / "figures.json", encoded(dict(version=1, charts=cards)) + b"\n")
    return tuple(card["id"] for card in cards)


if __name__ == "__main__":
    print("\n".join(export()))
