"""Audit a retrospective recording roster without selecting by fit outcome."""

import argparse
from dataclasses import dataclass

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from .full_v5_check import _sha

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "track-recovery/wide-roster"
STOCK_SHA = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"
LEGACY = {"DS26-0036", "DS26-0122", "DS26-0237", "DS29-0082", "DS29-0174", "DS29-0247"}


@dataclass(frozen=True)
class Study:
    path: str
    prefix: str
    branch: str
    prediction_sha: str

    @property
    def name(self):
        return self.path.rsplit("/", 1)[-1]

    @property
    def folder(self):
        return SCREEN / self.path


STUDIES = (
    Study(
        "receiver-core/full-stride",
        "wide-cfo-stride",
        "control",
        "42136b7b48d910bf416772d7c7eb9e127dafb0ee5f54089c58d94820a05a9872",
    ),
    Study(
        "track-recovery/exact-wide-iq",
        "exact-wide-iq",
        "control",
        "bb6c177e4d5aa5f814d50adfad6c853f8b870bb25770cda515275a2935438fff",
    ),
    Study(
        "acquisition-support/scout-full",
        "scout-centers",
        "control",
        "42d5e21eacaed581df00d9fd3be33035c707479b59bbc24eec72a6756c3b81fc",
    ),
    Study(
        "acquisition-support/fresh-waveform",
        "fresh_wide_four_full_iq",
        "wide",
        "b1477cd2320fc06ac118aafd956dba2140a328775881fbcc648e80e477557518",
    ),
    Study(
        "acquisition-support/deadline-repeat",
        "scout-deadline-repeat",
        "control",
        "376087bb676ed73004f86069293390c8e01e0f781e2d42be0ae418c176140a85",
    ),
    Study(
        "acquisition-support/radius-full",
        "scout-radius",
        "control",
        "d9ae07267f1c1fe827a75b48347fbe0a56b910daba22957863e41ab0f2015c5b",
    ),
    Study(
        "receiver-core/whole-winner",
        "whole_winner_stock",
        "stock",
        "5f28774b11855a135958c7abb8890b7d20356e83ab2711c6172c9bfed21064ba",
    ),
)


def primary_ids(sealed_rosters):
    chosen = {}
    for study in STUDIES[:3]:
        for ident in sorted(sealed_rosters[study.name]):
            chosen.setdefault(ident, study.name)
    return chosen


def declare(report):
    path = report / "roster-lock.json"
    if path.exists():
        raise FileExistsError("retrospective study roster is already declared")
    identities, rosters = {}, {}
    for study in STUDIES:
        folder = study.folder
        seal = whole_iq.read(
            whole_iq.checked(folder / "prediction-lock.json", study.prediction_sha)
        )
        source = whole_iq.read(
            whole_iq.checked(folder / "source-lock.json", seal["files"]["source-lock.json"])
        )
        cases = sorted(seal.get("cases", source["cases"]))
        if cases != sorted(source["cases"]):
            raise ValueError("study identity and frozen source roster disagree")
        rosters[study.name] = cases
        identities[study.name] = dict(
            cases=cases,
            path=study.path,
            branch=study.branch,
            prediction_sha256=study.prediction_sha,
            source_sha256=seal["files"]["source-lock.json"],
        )
    primary = primary_ids(rosters)
    if len(primary) != 12 or not primary.keys() >= LEGACY:
        raise ValueError("expected twelve recordings from the registered primary sources")
    save_json(
        path,
        dict(studies=identities, primary=primary, protocol_sha256=_sha(report / "PROTOCOL.md")),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=REPORT)
    declare(parser.parse_args().out)
