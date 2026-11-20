"""Freeze and transfer a signal-only retry rule against complete matched factors."""

import argparse
import gzip
import json
from hashlib import sha256
from itertools import product
from pathlib import Path

from ..__main__ import ROOT, encoded, save_json, write
from ..variants import retry_evidence as variant
from ..variants.selective_capture import visit_pairs
from . import selector_waveform
from . import single_pass_position as primary
from .capture_runtime import checked, read
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/retry-and-transfer/retry-evidence"
CASE1 = "DS26-0237"
CASE2 = "DS29-0082"
SPLIT = 3384
CONTROL = "time_spread"
SIGNAL = "signal_rule"
ALL = "all_retries"


def document(path, lock_name=None):
    if lock_name:
        lock = read(path.with_name(lock_name))
        checked(path, lock["files"][path.name])
    if path.suffix == ".gz":
        return json.loads(gzip.decompress(path.read_bytes()))
    return read(path)


def named(ident, visit):
    if ident == CASE1:
        return "development" if visit < SPLIT else "held"
    return "transfer"


def metadata(probe):
    return {k: v for k, v in probe.items() if k != "candidates"}


def positive(probe):
    return any(c[variant.GATE] for c in probe["candidates"])


def opportunities(first, conditional, before=None):
    for field in ("clock_anchor", "delivery_clocks", "last_sample_counter"):
        if first[field] != conditional[field]:
            raise ValueError("primary and conditional use different physical clocks")
    if first["provenance"]["excluded_windows"] != conditional["provenance"]["excluded_windows"]:
        raise ValueError("primary and conditional use different physical exclusions")
    for (v, a), (w, b) in zip(
        visit_pairs(first["source"]["probes"]),
        visit_pairs(conditional["source"]["probes"]),
        strict=True,
    ):
        if before is not None and v >= before:
            break
        if v != w or list(map(metadata, a)) != list(map(metadata, b)):
            raise ValueError("unmatched physical primary and conditional factors")
        hit = tuple(map(positive, a))
        if sum(hit) != 1:
            if a != b:
                raise ValueError("no-retry visit has different factors")
            continue
        failed_rx = int(hit[0])
        if a[1 - failed_rx] != b[1 - failed_rx]:
            raise ValueError("conditional retry changed the passing primary lane")
        yield dict(
            visit=v,
            rx=failed_rx,
            failed=a[failed_rx]["candidates"],
            peer=a[1 - failed_rx]["candidates"],
            rescue=positive(b[failed_rx]),
        )


def family():
    failed = [("failed_margin", v, None) for v in (0, 0.0025, 0.005, 0.010, 0.0125, 0.015, 0.020)]
    peer = [("peer_margin", v, None) for v in (0.05, 0.075, 0.10, 0.15, 0.20, 0.25, 0.30)]
    agreement = [("agreement", a, b) for a, b in ((2, 1000), (8, 5000), (32, 15000))]
    yield from (dict(operator="all", clauses=[p]) for p in failed + peer + agreement)
    for op, a, b in product(("all", "any"), failed, peer + agreement):
        yield dict(operator=op, clauses=[a, b])


def accepted(policy, row):
    return variant.passes(policy, row["failed"], row["peer"])


def choose(rows):
    table = []
    rescues = sum(r["rescue"] for r in rows)
    if not rows or not rescues:
        raise ValueError("empty predeclared development sample")
    for i, policy in enumerate(family()):
        selected = [r for r in rows if accepted(policy, r)]
        n, kept = len(selected), sum(r["rescue"] for r in selected)
        saving, retention = 1 - n / len(rows), kept / rescues
        table.append(
            dict(
                index=i,
                policy=policy,
                attempts=n,
                rescues=kept,
                saving=saving,
                retention=retention,
                qualified=saving >= 0.25 and retention >= 0.8,
            )
        )

    def rank(row):
        balance = min(row["saving"] / 0.25, row["retention"] / 0.8)
        return (
            row["qualified"],
            0 if row["qualified"] else balance,
            row["rescues"],
            -row["attempts"],
            -len(row["policy"]["clauses"]),
            -row["index"],
        )

    return max(table, key=rank), table


def development_inputs():
    return (primary.REPORT / "native.json.gz", selector_waveform.REPORT / "native.json.gz")


def freeze(work):
    if work.exists() or (REPORT / "policy-lock.json").exists():
        raise FileExistsError("retry policy is already frozen")
    sources = [
        *development_inputs(),
        REPORT / "PROTOCOL.md",
        Path(__file__),
        Path(variant.__file__),
    ]
    a, b = (document(p, "prediction-lock.json") for p in development_inputs())
    rows = list(opportunities(a, b, SPLIT))
    best, table = choose(rows)
    lock = dict(
        case=CASE1,
        held_start=SPLIT,
        development_attempts=len(rows),
        development_rescues=sum(r["rescue"] for r in rows),
        **best,
        sources={str(p): _sha(p) for p in sources},
    )
    work.mkdir()
    save_json(work / "policy-lock.json", lock)
    save_json(REPORT / "policy-lock.json", lock)
    save_json(REPORT / "development-ladder.json", table)
    print(json.dumps({k: v for k, v in lock.items() if k != "sources"}, indent=2))


def time_spread(visits, count, key):
    if count < 0 or count > len(visits):
        raise ValueError("invalid count-matched control budget")
    n = len(visits)
    chosen = []
    for i in range(count):
        lo, hi = i * n // count, (i + 1) * n // count
        index = int.from_bytes(sha256(encoded(["retry-evidence-v1", key, i])).digest(), "big")
        chosen.append(visits[lo + index % (hi - lo)])
    return chosen


def merged(ident, first, conditional, selected, method, binding):
    rows = []
    for (v, a), (_, b) in zip(
        visit_pairs(first["source"]["probes"]),
        visit_pairs(conditional["source"]["probes"]),
        strict=True,
    ):
        rows.extend(b if v in selected else a)
    source, provenance = first["source"], first["provenance"]
    digest = primary.base.recording.digest
    detector = digest([provenance["detector_sha256"], method, ident, binding])
    analysis = digest([source["analysis_manifest_sha256"], detector, rows])
    return dict(
        first,
        source=dict(source, probes=rows, analysis_manifest_sha256=analysis),
        provenance=dict(
            provenance,
            detector_sha256=detector,
            run_id="replay-" + analysis[7:39],
            scope="Complete matched native factors using " + method,
        ),
    )


def prepare(work, ident, first_path, conditional_path):
    plan = read(work / "policy-lock.json")
    checked(REPORT / "policy-lock.json", _sha(work / "policy-lock.json"))
    for path, digest in plan["sources"].items():
        checked(Path(path), digest)
    first, conditional = document(first_path), document(conditional_path)
    group = work / ident
    group.mkdir()
    candidates = list(opportunities(first, conditional))
    marks, summaries = {SIGNAL: set(), CONTROL: set()}, {}
    for split in ("development", "held") if ident == CASE1 else ("transfer",):
        rows = [r for r in candidates if named(ident, r["visit"]) == split]
        signal = [r["visit"] for r in rows if accepted(plan["policy"], r)]
        every = [r["visit"] for r in rows]
        control = time_spread(every, len(signal), [ident, split])
        marks[SIGNAL].update(signal)
        marks[CONTROL].update(control)
        summaries[split] = {}
        for name, ids in ((ALL, every), (SIGNAL, signal), (CONTROL, control)):
            ids = set(ids)
            summaries[split][name] = dict(
                attempts=len(ids),
                rescues=sum(r["rescue"] for r in rows if r["visit"] in ids),
                ids=sorted(ids),
            )
    if dict(
        visit_pairs(
            merged(
                ident,
                first,
                conditional,
                {x["visit"] for x in candidates},
                ALL,
                _sha(work / "policy-lock.json"),
            )["source"]["probes"]
        )
    ) != dict(visit_pairs(conditional["source"]["probes"])):
        raise ValueError("retry-on-every-opportunity stream did not reproduce conditional factors")
    for mode, chosen in marks.items():
        native = merged(ident, first, conditional, chosen, mode, _sha(work / "policy-lock.json"))
        write(group / f"{mode}.json", encoded(native) + b"\n")
    save_json(
        group / "selection.json",
        dict(
            case=ident,
            policy_sha256=_sha(work / "policy-lock.json"),
            sources={str(p): _sha(p) for p in (first_path, conditional_path)},
            splits=summaries,
            opportunities=[
                dict(
                    visit=r["visit"],
                    rx=r["rx"],
                    rescue=r["rescue"],
                    signal=r["visit"] in marks[SIGNAL],
                    time_spread=r["visit"] in marks[CONTROL],
                )
                for r in candidates
            ],
            factors={name: _sha(group / f"{name}.json") for name in marks},
        ),
    )
    print(
        ident,
        {s: {m: (v["attempts"], v["rescues"]) for m, v in d.items()} for s, d in summaries.items()},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "prepare"))
    parser.add_argument("work", type=Path)
    parser.add_argument("--case", choices=(CASE1, CASE2))
    parser.add_argument("--primary", type=Path)
    parser.add_argument("--conditional", type=Path)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.case == CASE1:
        prepare(args.work, CASE1, *development_inputs())
    elif args.case == CASE2 and args.primary and args.conditional:
        prepare(args.work, CASE2, args.primary, args.conditional)
    else:
        parser.error("supply a case and the two matched native factors for transfer")
