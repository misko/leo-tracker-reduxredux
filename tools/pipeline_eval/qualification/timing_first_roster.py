"""Prospectively reserve stratified and uniform visits for a cold receiver trial."""

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

from .full_v5_check import _sha
from .reverse_glrt_reference import CASES, REPORT, digest, freeze_case, packed, select
from .reverse_glrt_report import read

OUT = REPORT.parent / "2026_11_20_timing_first_glrt"
LATER = ("DS29-0082", "DS29-0174", "DS29-0519")


def choose(rows, used):
    available = [r for r in rows if (r["case"], r["visit"]) not in used]
    stratified = select(available)
    taken = {r["visit"] for r in stratified}
    ranked = sorted(available, key=lambda r: digest(packed(["timing-first-uniform-v1", r["id"]])))
    uniform = []
    for r in ranked:
        if r["visit"] not in taken:
            uniform.append(r)
            taken.add(r["visit"])
        if len(uniform) == 10:
            break
    if len(stratified) != 10 or len(uniform) != 10:
        raise ValueError("incomplete nominal test panel")
    return [
        dict(**r, selection=kind)
        for entries, kind in ((stratified, "stratified"), (uniform, "uniform"))
        for r in entries
    ]


def reserve(out):
    manifest = read(REPORT / "manifest.json")
    prior = {}
    excluded = set()
    for sub in ("", "heldout", "replication", "quarter-holdout", "recovery"):
        r = REPORT / sub / "roster.json"
        if _sha(r) != read(r.parent / "manifest.json")["roster_sha256"]:
            raise ValueError("prior roster changed")
        prior[sub or "initial"] = _sha(r)
        excluded.update((v["case"], v["visit"]) for v in read(r))
    native = REPORT / "opportunities.jsonl.gz"
    if _sha(native) != manifest["opportunities_sha256"]:
        raise ValueError("past native opportunity inventory changed")
    pools = defaultdict(list)
    with gzip.open(native, "rt") as stream:
        for line in stream:
            r = json.loads(line)
            pools[r["case"]].append(r)
    later = {}
    for ident in LATER:
        later[ident], pools[ident] = freeze_case(ident)
    for section, recordings, descriptions in (
        ("fresh-ds26", CASES, manifest["cases"]),
        ("fresh-ds29", LATER, list(later.values())),
    ):
        folder = out / section
        folder.mkdir(parents=True, exist_ok=True)
        roster = [r for ident in recordings for r in choose(pools[ident], excluded)]
        raw = packed(roster) + b"\n"
        binding = dict(
            cases=descriptions,
            prior_rosters=prior,
            roster_sha256=digest(raw),
            protocol_sha256=_sha(OUT / "PROTOCOL.md"),
            selector_sha256=_sha(Path(__file__)),
            native_ds26_sha256=manifest["opportunities_sha256"],
        )
        for name, body in [("roster.json", raw), ("manifest.json", packed(binding) + b"\n")]:
            path = folder / name
            if path.exists() and path.read_bytes() != body:
                raise ValueError("prospective inputs changed")
            path.write_bytes(body)
        print(section, len(roster), binding["roster_sha256"], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, default=OUT)
    reserve(p.parse_args().report)
