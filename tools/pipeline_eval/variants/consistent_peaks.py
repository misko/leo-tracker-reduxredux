"""Withhold higher-ranked alternatives only on mutually supported four-anchor conflicts."""

from collections import Counter, defaultdict
from dataclasses import dataclass

from .coherent_peak_filter import (
    MAX_CFO_RATE_HZ_S,
    MAX_GAP_S,
    Peak,
    continuation,
    step,
)

METHOD = "consistent_peaks"
GATE = "passed_fractional_margin_gate"
CFO = "fractional_tracking_cfo_hz"
CFO_RESIDUAL_HZ = 1000.0


def priority(candidate):
    return candidate["fractional_margin"], -candidate["candidate_rank"]


def reverse(peak):
    return Peak(peak.visit, -peak.counter, -peak.epoch, peak.cfo_hz)


def absolute_step(a, b, rate):
    motion = step(a, b, rate)
    if motion is None or abs(b.cfo_hz - a.cfo_hz) > MAX_CFO_RATE_HZ_S * motion[0]:
        return None
    return motion


def supports(a, b, p, advance, rate, rf, duration):
    if advance is None or absolute_step(b, p, rate) is None:
        return False
    predicted = b.cfo_hz + (b.cfo_hz - a.cfo_hz) * (p.counter - b.counter) / (b.counter - a.counter)
    return abs(p.cfo_hz - predicted) <= CFO_RESIDUAL_HZ and continuation(
        b, advance, p, rate, rf, duration
    )


@dataclass(frozen=True, slots=True)
class Observed:
    index: int
    probe: dict
    counter: int
    correction: float
    winner: int | None
    positives: tuple

    def peak(self, index):
        original = Peak.from_candidate(self.probe, self.counter, self.probe["candidates"][index])
        return Peak(
            original.visit, original.counter, original.epoch, original.cfo_hz + self.correction
        )


def gather(source):
    lanes = defaultdict(list)
    rate = source["sample_rate_hz"]
    for index, p in enumerate(source["probes"]):
        lane = (p["receiver_id"], p["channel"], p["edge"])
        history = lanes[lane]
        delta, res = divmod(p["probe_start_ms"] * rate, 1000)
        start = p["valid_start_counter"] + delta
        if res or type(start) is not int or (history and history[-1].counter >= start):
            raise ValueError("Lane clocks must increase in exact ADC samples")
        rf = p["actual_rf_hz"]
        initial = history[0].probe["actual_rf_hz"] if history else rf
        positives = tuple(i for i, c in enumerate(p["candidates"]) if c[GATE] is True)
        winner = max(positives, key=lambda i: priority(p["candidates"][i]), default=None)
        history.append(Observed(index, p, start, rf - initial, winner, positives))
    return lanes


def select(document):
    source = document["source"]
    rate = source["sample_rate_hz"]
    duration = source["probe_ms"] / 1000
    if (rate, duration) != (10_000_000, 0.020):
        raise ValueError("Batch policy requires the frozen dual-RX 20 ms geometry")
    edits = []
    counts = Counter(probes=len(source["probes"]))
    for batch in gather(source).values():
        counts["positive"] += sum(b.winner is not None for b in batch)
        counts["ambiguous"] += sum(len(b.positives) > 1 for b in batch)
        for j in range(2, len(batch) - 2):
            a, b, m, c, d = batch[j - 2 : j + 3]
            if len(m.positives) <= 1:
                continue
            if d.counter - a.counter > rate * MAX_GAP_S or any(
                e.winner is None for e in (a, b, c, d)
            ):
                counts["incomplete_anchors"] += 1
                continue
            la, lb = a.peak(a.winner), b.peak(b.winner)
            ra, rb = reverse(d.peak(d.winner)), reverse(c.peak(c.winner))
            left = absolute_step(la, lb, rate)
            right = absolute_step(ra, rb, rate)
            if left is None or right is None:
                counts["inconsistent_anchors"] += 1
                continue
            counts["forecast_opportunity"] += 1
            rf = m.probe["actual_rf_hz"]
            current = m.peak(m.winner)
            if supports(la, lb, current, left, rate, rf, duration) or supports(
                ra, rb, reverse(current), right, rate, rf, duration
            ):
                counts["winner_supported"] += 1
                continue
            ok = []
            for i in m.positives:
                if i == m.winner:
                    continue
                proposed = m.peak(i)
                if supports(la, lb, proposed, left, rate, rf, duration) and supports(
                    ra, rb, reverse(proposed), right, rate, rf, duration
                ):
                    ok.append(i)
            if len(ok) != 1:
                counts["ambiguous_alternate" if ok else "no_alternate"] += 1
                continue
            selected = ok[0]
            candidates = m.probe["candidates"]
            removed = [
                i for i in m.positives if priority(candidates[i]) > priority(candidates[selected])
            ]
            edits.append(
                dict(
                    index=m.index,
                    visit=m.probe["visit_index"],
                    receiver=m.probe["receiver_id"],
                    old_winner=m.winner,
                    new_winner=selected,
                    removed=removed,
                    anchors=[e.probe["visit_index"] for e in (a, b, c, d)],
                    future_samples=d.counter - m.counter,
                )
            )
            counts["withheld_candidates"] += len(removed)
    counts["changed_winners"] = len(edits)
    return sorted(edits, key=lambda r: r["index"]), dict(counts)


def apply(document, edits, lineage):
    probes = document["source"]["probes"].copy()
    indices = set()
    for edit in edits:
        i = edit["index"]
        if i in indices:
            raise ValueError("Conflicting edits on one native probe")
        indices.add(i)
        p = probes[i]
        if (p["visit_index"], p["receiver_id"]) != (edit["visit"], edit["receiver"]):
            raise ValueError("Edited probe identity changed")
        old = p["candidates"]
        new = [c for j, c in enumerate(old) if j not in edit["removed"]]
        winners = [c for c in new if c[GATE] is True]
        if max(winners, key=priority) != old[edit["new_winner"]]:
            raise ValueError("Offered sequence does not preserve the existing native winner rule")
        probes[i] = dict(p, candidates=new)
    if not edits:
        return document
    return dict(
        document,
        source=dict(
            document["source"],
            probes=probes,
            analysis_manifest_sha256=lineage,
        ),
        provenance=dict(
            document["provenance"],
            run_id="consistent-peaks-" + lineage[7:25],
            scope="Complete four-region factors with batch native winner vetoes",
        ),
    )
