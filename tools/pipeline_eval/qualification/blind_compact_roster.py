"""Freeze a recording-level comparison without using recorded positions or detector outputs."""

import hashlib
import itertools
import json
import sys
from pathlib import Path

from ..variants import v5_lean
from .full_v5_check import BULK, FROZEN, _load_case, _sha
from .reverse_glrt_reference import packed, read_bound
from .reverse_glrt_report import read
from .single_scan_roster import OUT as LAST

OUT = LAST.parent / "2026_11_20_blind_compact_receiver"
WORK = BULK / "leo-dev/gauss-blind-compact-20261120"
DS29 = BULK / "leo-dev/ds29-20261113/snapshot"
METHODS = ("original", "checked", "cancellation")
SALT = "gauss-compact-whole-recordings-v1/"


def select(rows, excluded, count=8):
    ordered = sorted(
        rows, key=lambda r: (hashlib.sha256((SALT + r["session_id"]).encode()).digest(), r["id"])
    )
    chosen = []
    sessions = {r["session_id"] for r in ordered if r["id"] in excluded}
    for r in ordered:
        if r["id"] in excluded or r["session_id"] in sessions:
            continue
        chosen.append(r)
        sessions.add(r["session_id"])
        if len(chosen) == count:
            return chosen
    raise ValueError("too few eligible independent recording sessions")


def seal(path, value):
    body = packed(value) + b"\n"
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError(f"existing frozen evidence differs at {path}")
    else:
        path.write_bytes(body)


def locator(path, sha):
    return dict(path=str(Path(path).relative_to(BULK)), sha256=sha.removeprefix("sha256:"))


def reserve():
    fresh = read(LAST / "fresh/manifest.json")
    last = read(LAST / "pair-holdout/manifest.json")
    excluded = set(fresh["excluded"]) | set(fresh["native_inputs"]) | set(last["native"])
    frozen = FROZEN / "inputs.jsonl"
    if _sha(frozen) != fresh["inventory_sha256"]:
        raise ValueError("DS26 input inventory changed")
    ds26 = [
        r
        for line in frozen.read_bytes().splitlines()
        if (r := json.loads(line))["panel"] == "DS26"
        and all(r.get(k) for k in ("native", "recording", "request"))
    ]
    inventory = read(DS29 / "inventory.json")
    raw_manifest = DS29 / "dataset-manifest.json"
    if _sha(raw_manifest) != inventory["dataset_manifest_sha256"].removeprefix("sha256:"):
        raise ValueError("DS29 recording manifest changed")
    raw = {
        r["dataset_label"]: r
        for r in read(raw_manifest)["members"]
        if r["recording_state"] == "complete"
        and r["sample_rate_hz"] == 10_000_000
        and r["raw_recording"]["segments"]
    }
    members = {
        r["dataset_label"]: r
        for r in inventory["members"]
        if r["availability"] == "available" and r["dataset_label"] in raw
    }
    ds29 = [dict(id=k, session_id=v["session_id"]) for k, v in members.items()]
    source = _load_case("DS29-0082")
    sample = read_bound(source["request"])
    config = dict(
        source=sample["source"],
        native_manifest=sample["native_manifest"],
        policies={"baseline": sample["policy"]},
        output=str(WORK / "baseline-bindings"),
        cohorts={
            "DS29": dict(
                template=read(DS29 / "template-request.json"),
                members=list(members.values()),
                config_sha256="sha256:" + inventory["config_sha256"].removeprefix("sha256:"),
                snapshot=str(DS29),
            )
        },
    )
    sys.path.insert(0, str(v5_lean.RUNNER))
    from evaluate_accuracy_repair import worker_request

    def request(ident):
        return worker_request(config, dict(dataset="DS29", case=ident, repetition=0), "baseline")

    control = request("DS29-0082")
    control["job"]["output_root"] = sample["job"]["output_root"]
    if control != sample:
        raise ValueError("expanded DS29 request builder differs from the archived benchmark")
    requests = WORK / "requests"
    requests.mkdir(parents=True, exist_ok=True)
    a, b = select(ds26, excluded), select(ds29, excluded)
    core_pairs = [(0, 1), (8, 9), (2, 3), (10, 11), (4, 5), (12, 13), (6, 7), (14, 15)]
    orders = list(itertools.permutations(METHODS))
    cases = []
    for i, (left, right) in enumerate(zip(a, b, strict=True)):
        ident = right["id"]
        member, rec = members[ident], raw[ident]
        req = request(ident)
        reqpath = requests / (ident + ".json")
        seal(reqpath, req)
        right = dict(
            **right,
            panel="DS29",
            run_id=member["run_id"],
            regions=source["regions"],
            native=locator(member["frozen_native_path"], member["input_sha256"]),
            request=locator(reqpath, _sha(reqpath)),
            recording=dict(
                window_count=rec["window_count"],
                segments=[
                    locator(v["path"], v["sha256"]) for v in rec["raw_recording"]["segments"]
                ],
            ),
        )
        for j, candidate in enumerate((left, right)):
            case = {
                k: candidate[k]
                for k in (
                    "id",
                    "panel",
                    "run_id",
                    "session_id",
                    "native",
                    "request",
                    "regions",
                    "recording",
                )
            }
            if read_bound(case["request"])["job"]["evaluation_reference"] is not None:
                raise ValueError("survey reference in inference request")
            cases.append(
                dict(case=case, cpu=core_pairs[i][j], order=orders[(i + 3 * j) % len(orders)])
            )
    if len({r["case"]["session_id"] for r in cases}) != len(cases):
        raise ValueError("one physical recording appears twice")
    OUT.mkdir(parents=True, exist_ok=True)
    seal(
        OUT / "roster.json",
        dict(
            protocol_sha256=_sha(OUT / "PROTOCOL.md"),
            salt=SALT,
            source_inventories={"DS26": _sha(frozen), "DS29": _sha(raw_manifest)},
            eligible_before_exclusion={"DS26": len(ds26), "DS29": len(ds29)},
            excluded=sorted(excluded),
            cases=cases,
        ),
    )
    print("Frozen", [(r["case"]["id"], r["cpu"]) for r in cases], flush=True)


if __name__ == "__main__":
    reserve()
