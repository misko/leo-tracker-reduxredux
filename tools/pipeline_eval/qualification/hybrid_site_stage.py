"""Publish the existing hybrid-site detector figure for gallery discovery."""

import argparse
from pathlib import Path

from ..__main__ import save_json
from .hybrid_site_trial import REPORT, stock
from .prefix_figures import csv_file

IMAGE = "detector-evidence.png"
TABLE = "detector-evidence.csv"
DESCRIPTOR = "stage-figure.json"
SEAL = "stage-lock.json"


def rows(scores):
    backgrounds = scores["detector"]["backgrounds"]
    cohorts = (
        ("planted", "winner_hits", "planted_probes", ("hybrid", "gaussian")),
        (
            "dark",
            "no_emission_gate_positives",
            "no_emission_probes",
            ("hybrid", "gaussian", "donor-only"),
        ),
    )
    return [
        dict(
            probe_group=group,
            background=background,
            metric=metric,
            count=backgrounds[background]["counts"][metric],
            receiver_probes=backgrounds[background]["counts"][denominator],
        )
        for group, metric, denominator, order in cohorts
        for background in order
    ]


def publish(out):
    scoring = stock.sealed(out, "score-lock.json")
    figure = stock.sealed(out, "published-evidence.json")
    if "scores.json" not in scoring["files"] or IMAGE not in figure["files"]:
        raise ValueError("stage chart needs the original score and image seals")
    csv_file(out / TABLE, rows(stock.read(out / "scores.json")))
    save_json(
        out / DESCRIPTOR,
        dict(
            version=1,
            id="hybrid-site-detector-backgrounds",
            title="Stock wide GLRT on matched dual CI16 waveform backgrounds",
            sample="768 matched dual visits and 1,536 receiver probes per background",
            boundary="Simulated Qin with archived IQ or matched Gaussian noise → stock wide GLRT",
            note=(
                "The planted panels require a phase/CFO match to the injected waveform. "
                "Dark probes count any gate winner, including real donor signals."
            ),
            seal=SEAL,
            image=IMAGE,
            csv=TABLE,
        ),
    )
    sources = (
        TABLE,
        IMAGE,
        DESCRIPTOR,
        "score-lock.json",
        "scores.json",
        "published-evidence.json",
    )
    save_json(
        out / SEAL,
        dict(
            files={name: stock.digest(out / name) for name in sources},
            generator_sha256=stock.digest(Path(__file__)),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT)
    publish(parser.parse_args().out)


if __name__ == "__main__":
    main()
