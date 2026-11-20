"""Run the unchanged partner-on-hit rule on the disjoint remainder of the roof roster."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import fresh_replay
from . import one_lane_roster_results as one_results
from . import partner_on_hit_trial as trial
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .phase_support_results import pack
from .whole_pressure_trial import rows_from

REPORT = trial.fixed.SCREEN / "antenna-confirmation/partner-holdout"
PINS = (6, 7, 8, 9)
DISCOVERY_PIN = "4276d803b7c8393f76c42624265ac4682e66aa0cf2123094a0761013698dbda0"
METHOD = trial.METHOD
read = whole_iq.read


def split(eligible, discovery):
    prior, full = set(discovery), set(eligible)
    if len(eligible) != 22 or len(full) != 22 or len(discovery) != 8 or len(prior) != 8:
        raise ValueError("the prospective split requires 22 unique eligible and eight prior cases")
    if not prior <= full:
        raise ValueError("discovery must be entirely contained in the frozen source roster")
    return sorted(full - prior), sorted(full)


def authority():
    parents, positions, audits, release = trial.controls()
    groups, _, _, extensions, verified = trial.one.inventory()
    if release != verified:
        raise ValueError("both panels must use the original identical scientific installation")
    past = sealed(trial.REPORT, "prediction-lock.json", DISCOVERY_PIN)
    if past["cases"] != list(trial.CASES):
        raise ValueError("the eight original diagnostic recordings changed")
    holdout, pooled = split(groups["all"], past["cases"])
    archive = rows_from(trial.fixed.member(trial.REPORT, past, "predictions.jsonl.gz"))
    if len(archive) != len(trial.CASES) or {r["id"] for r in archive} != set(trial.CASES):
        raise ValueError("the original terminal roster changed")
    proof = read(trial.fixed.member(trial.REPORT, past, "packet-audit.json"))
    positions[trial.fixed.FOUR] = one_results.released_stock(groups)
    for ident in pooled:
        first, other, stock = (
            positions[k][ident] for k in (trial.one.METHOD, trial.miss.METHOD, trial.fixed.FOUR)
        )
        trial.fixed.same_capture(first, stock)
        trial.fixed.same_capture(other, stock)
    parents["discovery_partner_on_hit"] = DISCOVERY_PIN
    parents["fresh_fixed_four"] = _sha(trial.one.FRESH / "prediction-lock.json")
    return holdout, pooled, parents, positions, audits, release, extensions, archive, proof


def binding_context(ident, extensions):
    return fresh_replay.patched_case(extensions[ident]) if ident in extensions else nullcontext()


def source_hashes():
    discovery = read(trial.REPORT / "plan.json")
    hashes = {
        str(p.relative_to(ROOT)): _sha(p)
        for p in (Path(__file__), Path(one_results.__file__), REPORT / "PROTOCOL.md")
    }
    for name, digest in discovery["sources"].items():
        whole_iq.checked(ROOT / name, digest)
        hashes[name] = digest
    return hashes


def run(work):
    if (REPORT / "plan.json").exists():
        raise FileExistsError("the disjoint holdout schedule is already frozen")
    holdout, pooled, parents, positions, audits, release, extensions, discovery, proof = authority()
    work.mkdir(exist_ok=False)
    sources = source_hashes()
    schedule = []
    for i, ident in enumerate(holdout):
        with binding_context(ident, extensions):
            row, proof[ident] = trial.stage(
                work, ident, PINS[i % len(PINS)], positions, audits, release
            )
        row.update(
            one_lane_native_sha256=proof[ident]["one_lane_native_sha256"],
            second_on_miss_native_sha256=proof[ident]["second_on_miss_native_sha256"],
        )
        schedule.append(row)
    save_json(REPORT / "packet-audit.json", proof)
    save_json(
        REPORT / "plan.json",
        dict(
            cases=holdout,
            discovery=list(trial.CASES),
            pooled=pooled,
            schedule=schedule,
            parents=parents,
            sources=sources,
            limit_s=trial.service.LIMIT,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            packet_audit_sha256=_sha(REPORT / "packet-audit.json"),
            **release,
        ),
    )
    print("frozen", len(schedule), "new cases", _sha(REPORT / "plan.json"), flush=True)

    def lane(cpu):
        return [trial.service.service(work, r) for r in schedule if r["cpu"] == cpu]

    with ThreadPoolExecutor(len(PINS)) as pool:
        fresh = sorted((r for group in pool.map(lane, PINS) for r in group), key=lambda r: r["id"])
    pack(REPORT / "holdout-predictions.jsonl.gz", fresh)
    pack(REPORT / "positions.jsonl.gz", sorted(discovery + fresh, key=lambda r: r["id"]))
    members = (
        "plan.json",
        "packet-audit.json",
        "holdout-predictions.jsonl.gz",
        "positions.jsonl.gz",
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(cases=pooled, holdout=holdout, files={n: _sha(REPORT / n) for n in members}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
