"""Score sealed phase allocation against both the complete grid and the archive."""

import gzip
import json
from collections import defaultdict
from statistics import median

from ..__main__ import save_json
from . import full_v5_check as full
from . import phase_scout_trials as trial

OUT = trial.REPORT
ALL = (1 << 21) - 1
N = round(trial.RATE / 750)


def load(seal, raw):
    lock = json.loads((OUT / seal).read_bytes())
    for filename, digest in lock["files"].items():
        assert full._sha(OUT / filename) == digest
    return list(map(json.loads, gzip.decompress((OUT / raw).read_bytes()).splitlines()))


def masks(scout):
    result = {}
    for row in scout:
        for e in range(max(0, row["epoch"] - 1), min(N, row["epoch"] + 2)):
            key = row["receiver"], e
            result[key] = result.get(key, 0) | row["mask"]
    return result


def support(epoch):
    return sum(
        round(f * trial.RATE / 750) + epoch + round((3 + 26 * s) * trial.RATE * 4.4e-6)
        <= trial.RATE // 50
        for f in range(16)
        for s in range(12)
    )


def allocation(scout, raw):
    cells = masks(scout)
    evaluation = sum(mask.bit_count() * support(e) for (_, e), mask in cells.items())
    baseline = sum(21 * support(e) for _, e in cells)
    stock = raw["payloads"]["stock"]["rows"]
    winners, lost = [], []
    for row in stock:
        rx = row["receiver_id"]
        valid = [
            c
            for c in row["candidates"]
            if c["fractional_epoch"]["status"] == "complete"
            and c["fractional_epoch"]["margin"] >= full.MARGIN_GATE
        ]
        if valid:
            key = max(valid, key=lambda c: c["fractional_epoch"]["margin"])
            winners.append((rx, key["coarse_epoch"], key["coarse_bin"]))
        for c in row["candidates"]:
            e, b = c["coarse_epoch"], c["coarse_bin"]
            if not cells.get((rx, e), ALL) & (1 << b):
                lost.append((rx, e, b))
    return dict(
        centers=len(scout),
        restricted=sum(c["mask"] != ALL for c in scout),
        compared_cells=len(cells) * 21,
        evaluated_cells=sum(mask.bit_count() for mask in cells.values()),
        compared_symbol_bins=baseline,
        evaluated_symbol_bins=evaluation,
        stock_retained_coarse=sum(len(r["candidates"]) for r in stock),
        lost_stock_coarse=lost,
        stock_winners=len(winners),
        lost_stock_winners=[key for key in winners if key in lost],
    )


def native_as_probe(row):
    return [
        candidate
        for i, c in enumerate(row["candidates"])
        if (candidate := full._from_native(i, c)) is not None
    ]


def archive():
    out = {}
    for ident in trial.CASES:
        case = full._load_case(ident)
        path = full.BULK / case["native"]["path"]
        digest = full._sha(path)
        if digest != case["native"]["sha256"]:
            raise ValueError("capture-era GLRT digest changed")
        native = json.loads(path.read_bytes())
        assert native["source"]["session_id"] == case["session_id"]
        out[ident] = (
            digest,
            {
                (r["visit_index"], r["receiver_id"]): r["candidates"]
                for r in native["source"]["probes"]
            },
        )
    return out


def winner(candidates):
    return sorted(
        (c for c in candidates if c["passed_fractional_margin_gate"]),
        key=lambda c: (-c["fractional_margin"], c["candidate_rank"]),
    )[:1]


def main():
    rows = load("prediction-lock.json", "predictions.jsonl.gz")
    alt = load("coherent-lock.json", "coherent-diagnostic.jsonl.gz")
    old = archive()
    records = []
    for reference, alternate in zip(rows, alt, strict=True):
        ident = reference["id"]
        assert all(reference.get(k) == alternate.get(k) for k in ("id", "visit", "iq_sha256"))
        primary = allocation(reference["scout"], reference)
        coherent = allocation(alternate["scout"], reference)
        timing = {
            mode: dict(
                detector_ms=median(t["detector_cpu_ms"] for t in traces),
                coarse_ms=median(sum(row["coarse"] for row in t["rows"]) for t in traces),
            )
            for mode, traces in reference["timings"].items()
        }
        record = dict(
            id=ident,
            visit=reference.get("visit"),
            condition=reference["condition"],
            iq_sha256=reference["iq_sha256"],
            exact_payload=reference["exact"],
            primary=primary,
            coherent=coherent,
            prototype_cpu_ms=1000 * alternate["prototype_cpu_s"],
            timings=timing,
            archive={},
            plants={},
        )
        for mode, result in reference["payloads"].items():
            for row in result["rows"]:
                rx = row["receiver_id"]
                candidates = native_as_probe(row)
                if ident in old:
                    digest, probes = old[ident]
                    assert digest == reference["native_sha256"]
                    archived = probes.get((reference["visit"], rx), [])
                    comp = full.compare_probes(
                        {"candidates": archived}, {"candidates": candidates}, trial.RATE
                    )
                    winning = full.compare_probes(
                        {"candidates": winner(archived)},
                        {"candidates": candidates},
                        trial.RATE,
                    )
                    record["archive"].setdefault(mode, []).append(
                        dict(
                            receiver=rx,
                            available=(reference["visit"], rx) in probes,
                            archived_positives=comp["production_positive"],
                            modern_positives=comp["native_positive"],
                            matched_positives=len(comp["positive_matches"]),
                            archived_winners=winning["production_positive"],
                            matched_winners=len(winning["positive_matches"]),
                        )
                    )
                elif reference["condition"] != "null":
                    matches = [
                        c["fractional_tracking_cfo_hz"] - reference["plant_hz"]
                        for c in candidates
                        if c["passed_fractional_margin_gate"]
                        and abs(
                            c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"] - 735
                        )
                        <= 2
                        and abs(c["fractional_tracking_cfo_hz"] - reference["plant_hz"]) <= 1000
                    ]
                    record["plants"].setdefault(mode, []).append(
                        dict(receiver=rx, match=bool(matches))
                    )
                else:
                    record["plants"].setdefault(mode, []).append(
                        dict(
                            receiver=rx,
                            positives=sum(c["passed_fractional_margin_gate"] for c in candidates),
                        )
                    )
        records.append(record)
    groups = defaultdict(list)
    for record in records:
        groups[record["condition"]].append(record)
    summaries = {}
    for name, group in groups.items():
        stats = dict(
            windows=len(group),
            exact_payloads=sum(r["exact_payload"] for r in group),
            median_prototype_cpu_ms=median(r["prototype_cpu_ms"] for r in group),
        )
        for name2 in ("primary", "coherent"):
            stats[name2] = {
                k: sum(r[name2][k] for r in group)
                for k in (
                    "centers",
                    "restricted",
                    "compared_cells",
                    "evaluated_cells",
                    "compared_symbol_bins",
                    "evaluated_symbol_bins",
                    "stock_retained_coarse",
                    "stock_winners",
                )
            }
            stats[name2].update(
                {
                    k: sum(len(r[name2][k]) for r in group)
                    for k in (
                        "lost_stock_coarse",
                        "lost_stock_winners",
                    )
                }
            )
        stats["timings"] = {
            m: {k: median(r["timings"][m][k] for r in group) for k in ("detector_ms", "coarse_ms")}
            for m in trial.MODES
        }
        summaries[name] = stats
    save_json(OUT / "scores.json", dict(groups=summaries, records=records))


if __name__ == "__main__":
    main()
