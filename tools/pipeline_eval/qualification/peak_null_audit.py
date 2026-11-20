"""Audit score semantics and conditional controls without opening position outcomes."""

import gzip
import json
from collections import defaultdict
from math import ceil, log
from pathlib import Path
from random import Random

from ..__main__ import save_json
from ..scoring import distribution
from ..variants import peak_null
from .input_factor_bridge import BULK, _load_case, _sha, check, read
from .peak_null_trial import DEVELOPMENT, REPORT, SCREEN, SOURCE

AUDIT = SCREEN / "streamlined/whole-pair"
DRAW_SEED, DRAW_VISITS, DRAW_SLOTS = 94736, 2048, 8
PLANTED_EXCESS = 3 * peak_null.ORIGINAL_GATE
FOLD_HZ = 1 / 4.4e-6


def lane_scores(document):
    rows = defaultdict(list)
    for probe in document["source"]["probes"]:
        peaks = probe["candidates"]
        for candidate in peaks:
            peak_null.check_peak(candidate)
        if peaks:
            rows[peak_null.lane_key(probe)].append(peaks)
    return rows


def effective_exported_slots(rows):
    peaks = [p["fractional_control_score"] for group in rows for p in group]
    maxima = sorted(max(p["fractional_control_score"] for p in group) for group in rows)
    q95 = maxima[ceil(0.95 * len(maxima)) - 1]
    f_max = sum(s <= q95 for s in maxima) / len(maxima)
    f_candidate = sum(s <= q95 for s in peaks) / len(peaks)
    return dict(
        probes=len(rows),
        q95=q95,
        native_candidates_per_probe=len(peaks) / len(rows),
        effective_exported_slots_at_q95=log(f_max) / log(f_candidate)
        if 0 < f_max < 1 and 0 < f_candidate < 1
        else None,
    )


def summarize(document):
    lanes = lane_scores(document)
    summaries = {repr(key): effective_exported_slots(group) for key, group in lanes.items()}
    peaks = [peak for group in lanes.values() for probe in group for peak in probe]
    return dict(
        candidates=len(peaks),
        passing=sum(peak["passed_fractional_margin_gate"] for peak in peaks),
        exact=distribution(p["fractional_exact_score"] for p in peaks),
        rolled=distribution(p["fractional_control_score"] for p in peaks),
        lane_q95=distribution(v["q95"] for v in summaries.values()),
        effective_exported_slots_at_q95=distribution(
            v["effective_exported_slots_at_q95"] for v in summaries.values()
        ),
        lanes=summaries,
    )


def synthetic_probe(visit, exact, rolled):
    candidates = []
    for i, (a, b) in enumerate(zip(exact, rolled, strict=True)):
        margin = a - b
        candidates.append(
            dict(
                candidate_rank=i,
                fractional_exact_score=a,
                fractional_control_score=b,
                fractional_margin=margin,
                passed_fractional_margin_gate=margin >= peak_null.ORIGINAL_GATE,
                integer_epoch_sample=i,
                fractional_epoch_offset_samples=0.0,
                fractional_tracking_cfo_hz=float(i * 1000),
            )
        )
    return dict(
        visit_index=visit,
        receiver_id=0,
        channel=1,
        actual_rf_hz=11.5e9,
        edge="lower",
        candidates=candidates,
    )


def synthetic_controls(pool, n=DRAW_VISITS):
    """Adapter checks with score-level exchangeability and explicit planted rank."""
    rnd = Random(DRAW_SEED)
    documents = {key: {"source": {"probes": []}} for key in ("zero", "exchangeable", "planted")}
    planted = []
    for visit in range(n):
        exact = rnd.choices(pool, k=DRAW_SLOTS)
        rolled = rnd.choices(pool, k=DRAW_SLOTS)
        planted_rank = rnd.randrange(DRAW_SLOTS)
        stronger = exact.copy()
        stronger[planted_rank] = rolled[planted_rank] + PLANTED_EXCESS
        planted.append(planted_rank)
        for key, values in (("zero", rolled), ("exchangeable", exact), ("planted", stronger)):
            documents[key]["source"]["probes"].append(synthetic_probe(visit, values, rolled))

    def winners(document):
        result = []
        for probe in document["source"]["probes"]:
            passing = [p for p in probe["candidates"] if p["passed_fractional_margin_gate"]]
            rank = max(passing, key=peak_null.native_rank)["candidate_rank"] if passing else None
            result.append(rank)
        return result

    result = {}
    for key, doc in documents.items():
        changed, counts, _, _ = peak_null.adjusted_document(doc)
        stock, adjusted = winners(doc), winners(changed)
        result[key] = dict(
            probes=n,
            stock_gate_positive=sum(v is not None for v in stock),
            adjusted_gate_positive=sum(v is not None for v in adjusted),
            winner_changes=counts["changed_winner"],
        )
        if key == "planted":
            result[key].update(
                planted_top1_stock=sum(a == b for a, b in zip(stock, planted, strict=True)),
                planted_top1_adjusted=sum(a == b for a, b in zip(adjusted, planted, strict=True)),
            )
    return result


def summarize_changes(document, changes):
    freq, epochs = [], []
    rate = document["source"]["sample_rate_hz"]
    frame = round(rate / 750)
    for row in changes:
        selected = document["source"]["probes"][row["probe_index"]]
        peaks = {p["candidate_rank"]: p for p in selected["candidates"]}
        before, after = (peaks[row[k]] for k in ("old_rank", "new_rank"))
        f = after["fractional_tracking_cfo_hz"] - before["fractional_tracking_cfo_hz"]
        freq.append(abs((f + FOLD_HZ / 2) % FOLD_HZ - FOLD_HZ / 2))
        phase = sum(
            after[k] - before[k]
            for k in (
                "integer_epoch_sample",
                "fractional_epoch_offset_samples",
            )
        )
        epochs.append(1e6 * abs((phase + frame / 2) % frame - frame / 2) / rate)
    return dict(
        wrapped_cfo_shift_hz=distribution(freq),
        wrapped_epoch_shift_us=distribution(epochs),
        same_1khz_and_point2us=sum(
            f <= 1000 and e <= 0.2 for f, e in zip(freq, epochs, strict=True)
        ),
        wrapped_cfo_above_1khz=sum(f > 1000 for f in freq),
    )


def publish():
    authority = AUDIT / "archive-authority.json.gz"
    check(authority, read(AUDIT / "archive-authority-lock.json")["files"][authority.name])
    inventory = json.loads(gzip.decompress(authority.read_bytes()))["cases"]
    wide_seal = read(SOURCE / "prediction-lock.json")
    changes_file = REPORT / "winner-changes.json.gz"
    changes = json.loads(gzip.decompress(changes_file.read_bytes()))
    summary, moved, nulls, digests = {}, {}, {}, {}
    for ident in sorted(changes):
        wide = SOURCE / "native" / f"{ident}.json.gz"
        digest = check(wide, wide_seal["files"][str(wide.relative_to(SOURCE))])
        doc = json.loads(gzip.decompress(wide.read_bytes()))
        moved[ident] = summarize_changes(doc, changes[ident])
        digests[ident] = {"wide_archive_sha256": digest}
        if ident in DEVELOPMENT:
            ordinary = inventory[ident]
            narrow = Path(ordinary["ordinary_factor_file"])
            frozen = _load_case(ident)["native"]
            capture = BULK / frozen["path"]
            digests[ident].update(
                narrow_sha256=check(narrow, ordinary["ordinary_factor_sha256"]),
                capture_era_sha256=check(capture, frozen["sha256"]),
            )
            summary[ident] = dict(
                wide=summarize(doc),
                narrow=summarize(read(narrow)),
                capture_era=summarize(read(capture)),
            )
            lane = max(lane_scores(doc).values(), key=len)
            pool = [p["fractional_control_score"] for group in lane for p in group]
            nulls[ident] = synthetic_controls(pool)
    save_json(
        REPORT / "pilot-semantics-audit.json",
        dict(
            source_sha256=_sha(Path(__file__)),
            inputs=digests,
            winner_changes_sha256=_sha(changes_file),
            actual_changes=moved,
            nominal_coarse_centers=dict(wide=21, narrow=11),
            score_and_effective_exported_cell_diagnostics=summary,
            simulation=dict(seed=DRAW_SEED, sites=0, plant_excess=PLANTED_EXCESS, results=nulls),
        ),
    )


if __name__ == "__main__":
    publish()
