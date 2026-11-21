"""Freeze location-independent raw opportunities for testing a second signed carrier."""

import argparse
from pathlib import Path

from .full_v5_check import _sha
from .reverse_glrt_reference import CASES, digest, freeze_case, packed
from .reverse_glrt_report import read
from .timing_first_roster import LATER
from .timing_first_roster import OUT as PREVIOUS
from .timing_first_trial import inventories

OUT = PREVIOUS.parent / "2026_11_20_two_carrier_glrt"
WORK = Path("/srv/bulk/leo-dev/ds26-two-carrier-20261120")


def select(rows, excluded, limit=10):
    chosen = []
    used = set(excluded)
    for row in sorted(rows, key=lambda r: digest(packed(["two-carrier-uniform-v1", r["id"]]))):
        visit = (row["case"], row["visit"])
        if visit not in used:
            used.add(visit)
            chosen.append(row)
            if len(chosen) == limit:
                return chosen
    raise ValueError("insufficient distinct unused visits in recording")


def reserve(out):
    excluded = set()
    prior = {}
    for name, folder in inventories(PREVIOUS).items():
        path = folder / "roster.json"
        prior[name] = _sha(path)
        if prior[name] != read(folder / "manifest.json")["roster_sha256"]:
            raise ValueError("prior raw roster changed")
        excluded.update((r["case"], r["visit"]) for r in read(path))
    if len(excluded) != 389:
        raise ValueError("previously scored visit inventory changed")
    cases, roster = [], []
    for ident in (*CASES, *LATER):
        case, pool = freeze_case(ident)
        cases.append(case)
        roster.extend(select(pool, excluded))
    body = packed(roster) + b"\n"
    folder = out / "prospective"
    folder.mkdir(exist_ok=True, parents=True)
    protocol = folder / "SELECTION-PROTOCOL.md"
    selector = folder / "frozen-selector.py.txt"
    for snapshot, source in ((protocol, out / "PROTOCOL.md"), (selector, Path(__file__))):
        if not snapshot.exists():
            snapshot.write_bytes(source.read_bytes())
    meta = dict(
        cases=cases,
        prior_rosters=prior,
        prior_visits=len(excluded),
        roster_sha256=digest(body),
        selector_sha256=_sha(selector),
        protocol_sha256=_sha(protocol),
    )
    for name, data in (("roster.json", body), ("manifest.json", packed(meta) + b"\n")):
        p = folder / name
        if p.exists():
            if p.read_bytes() != data:
                raise ValueError("prospective inputs changed")
        else:
            p.write_bytes(data)
    print(
        "Reserved", len(roster), "new visits before measurement", meta["roster_sha256"], flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=OUT)
    reserve(parser.parse_args().report)
