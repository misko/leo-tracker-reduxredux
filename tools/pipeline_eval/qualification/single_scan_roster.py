"""Reserve visits from entirely different recordings before acquisition or scoring."""

import argparse
import json
from pathlib import Path

from .full_v5_check import FROZEN, _sha
from .reverse_glrt_reference import CASES, digest, packed, read_bound
from .timing_first_roster import LATER
from .two_carrier_roster import OUT as PRIOR

OUT = PRIOR.parent / "2026_11_20_single_scan_glrt"
WORK = Path("/srv/bulk/leo-dev/ds26-single-scan-20261120")


def initial_driver(out, source):
    folder = out / "frozen"
    folder.mkdir(exist_ok=True, parents=True)
    path = folder / (source.name + ".txt")
    if not path.exists():
        path.write_bytes(source.read_bytes())
    return _sha(path)


def draw_cases(rows):
    prior = set((*CASES, *LATER))
    available = [
        r
        for r in rows
        if r["id"] not in prior and all(r.get(k) for k in ("recording", "request", "native"))
    ]
    ranked = sorted(
        available, key=lambda r: digest(("single-scan-fresh-recordings-v1/" + r["id"]).encode())
    )
    selected = []
    for prefix, count in (("DS26-", 5), ("DS29-", 3)):
        group = [r for r in ranked if r["id"].startswith(prefix)][:count]
        if len(group) != count:
            raise ValueError("insufficient unused recordings")
        selected.extend(group)
    return selected


def draw_visits(case, native, limit=16):
    if native["source"]["session_id"] != case["session_id"]:
        raise ValueError("recording and native session differ")
    probes = []
    seen = set()
    for p in native["source"]["probes"]:
        lane, counter = p["receiver_id"], p["valid_start_counter"]
        oid = "sha256:" + digest(f"{case['session_id']}:{lane}:{counter}".encode())
        if oid in seen:
            raise ValueError("duplicate hardware observation")
        seen.add(oid)
        probes.append((digest(("single-scan-fresh-visits-v1/" + oid).encode()), oid, p))
    used, selected = set(), []
    for _, oid, p in sorted(probes, key=lambda x: x[0]):
        if p["visit_index"] in used:
            continue
        used.add(p["visit_index"])
        accepted = (c for c in p["candidates"] if c["passed_fractional_margin_gate"])
        old = max(
            accepted, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None
        )
        selected.append(
            dict(
                case=case["id"],
                visit=p["visit_index"],
                id=oid,
                rx=p["receiver_id"],
                counter=p["valid_start_counter"],
                edge=p["edge"],
                channel=p["channel"],
                incumbent=old,
                old_pass=old is not None,
                stratum="uniform",
                owners=dict(c0=None, fitted_c=None),
                brackets=dict(c0=[], fitted_c=[]),
            )
        )
        if len(selected) == limit:
            return selected
    raise ValueError("insufficient distinct stereo visits")


def reserve(out):
    inventory = FROZEN / "inputs.jsonl"
    if (
        _sha(inventory)
        != json.loads((FROZEN / "provenance.json").read_bytes())["files"][inventory.name]
    ):
        raise ValueError("frozen recording inventory changed")
    cases = draw_cases([json.loads(line) for line in inventory.read_bytes().splitlines()])
    rows = [r for c in cases for r in draw_visits(c, read_bound(c["native"]))]
    body = packed(rows) + b"\n"
    meta = dict(
        inventory_sha256=_sha(inventory),
        selector_sha256=initial_driver(out, Path(__file__)),
        protocol_sha256=_sha(out / "PROTOCOL.md"),
        roster_sha256=digest(body),
        native_inputs={c["id"]: c["native"] for c in cases},
        excluded=[*CASES, *LATER],
    )
    dest = out / "fresh"
    dest.mkdir(parents=True, exist_ok=True)
    for name, data in (("roster.json", body), ("manifest.json", packed(meta) + b"\n")):
        path = dest / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f"frozen {name} changed")
        path.write_bytes(data)
    print("Reserved", len(rows), "visits in", [c["id"] for c in cases], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=OUT)
    reserve(parser.parse_args().report)
