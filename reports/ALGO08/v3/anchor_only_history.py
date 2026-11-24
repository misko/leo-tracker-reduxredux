"""Replay causal anchor-only selection from already measured signed factors."""

import argparse
from collections import Counter, defaultdict, deque
import gzip
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path

from tools.pipeline_eval.variants.carrier_continuation import Continuation, votes


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
PINS = {
    "installed-0049.json": "0ab03aabf2e7dfc6cedc832fa4ab3482cbf9d3d6b12440aa2fc86ee1a5b17552",
    "mixed-0049.json": "bd08660bb1323230f3a7f8751507577816dc3ebab49de2edd05085dbdce16e81",
    "ds30-0049-receiver-factorial.json.gz": "4af8b73101dce9b71a06b38a10e2484ef04b74f42b5221cfec1e818d21ea3b58",
    "ds30-0049-saved-crossover.json.gz": "76ffa1841268d1f9dd8348a3549c8927655653abdcc804697b6a36f00aebf8ce",
    "ds30-0016-full-primary-transfer.json.gz": "ace7652af6fa0945f28dd161d1b16ecb293f0ca7c8bdf8340dfeff610c87fd9c",
    "late-pilot-rescue.json.gz": "2b725ccdb473948c2fdbd042a4029060912783f424b8d73c98db34e7537e5a50",
}
VOTE_SOURCE = "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee"
ARMS = ("c0", "fitted_c")


def read(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Pinned evidence differs: {path}")
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def strongest(factors):
    ranks = {factor["candidate_rank"] for factor in factors}
    if len(ranks) != len(factors) or not ranks <= {0, 1} or any(
            not factor["passed_fractional_margin_gate"] for factor in factors):
        raise ValueError("Expected a verifiable original native factor list")
    return max(factors, key=lambda f: (f["fractional_margin"], -f["candidate_rank"]), default=None)


def cfo(factor):
    return factor["fractional_tracking_cfo_hz"]


def opportunity(row):
    return dict(row, candidates=[])


def slot(row):
    return row["visit_index"], row["receiver_id"]


def stream(row):
    return row["edge"], row["channel"], row["actual_rf_hz"]


def decisions(rows):
    """Recover the actual per-RF stereo schedule from original admitted rows."""
    streams = Counter()
    last_visit = -1
    for visit, group in groupby(rows, key=lambda row: row["visit_index"]):
        pair = tuple(group)
        if visit <= last_visit or [row["receiver_id"] for row in pair] != [0, 1]:
            raise ValueError("Expected ordered original stereo opportunities")
        last_visit = visit
        key = stream(pair[0])
        if stream(pair[1]) != key or pair[1]["valid_start_counter"] != pair[0]["valid_start_counter"]:
            raise ValueError("Original stereo opportunity differs by radio")
        anchor = streams[key] % 8 == 0
        streams[key] += 1
        for row in pair:
            yield row, anchor


class AnchorHistory:
    """Independent same-lane history of paid strongest values and empty visits."""

    def __init__(self):
        self.history = defaultdict(lambda: deque(maxlen=12))

    def choose(self, row, anchor, alternatives=None):
        options = row["candidates"]
        if len(options) > 1:
            raise ValueError("Expected the unchanged mixed winner or empty lane")
        current = strongest(options)
        if alternatives is not None and (not anchor or strongest(alternatives) != current):
            raise ValueError("Paid full alternatives disagree with the original strongest factor")
        lane = row["receiver_id"], *stream(row)
        history = self.history[lane]
        now = row["valid_start_counter"]
        if history and now <= history[-1][0]:
            raise ValueError("Expected strictly increasing same-lane counters")
        recent = []
        choice = current
        support = []
        reason = "empty" if current is None else "short"
        if current is not None and anchor:
            recent = [t for t, values in history if 0 < now - t <= 80_000_000 and values]
            reason = "insufficient_history"
            if len(recent) >= 3 and now - recent[0] >= 4_000_000:
                score = votes(cfo(current), history, now)
                support.append(score)
                choice, reason = (current, "supported") if score >= 3 else (None, "rejected")
                if choice is None and alternatives is not None and len(alternatives) == 2:
                    other, = (factor for factor in alternatives if factor != current)
                    second = votes(cfo(other), history, now)
                    support.append(second)
                    if second >= 3 and second >= score + 2:
                        choice, reason = other, "paid_alternative"
        history.append((now, () if current is None else (cfo(current),)))
        return choice, reason, len(recent), support


def paired(stock, mixed):
    for key in ("session_id", "input_manifest_sha256", "raw_recording_authority_digest", "capture_start_utc_ns"):
        if stock["source"][key] != mixed["source"][key]:
            raise ValueError("Installed and mixed detector authority differ")
    for key in ("clock_anchor", "delivery_clocks", "last_sample_counter"):
        if stock[key] != mixed[key]:
            raise ValueError("Installed and mixed detector chronology differ")
    if stock["provenance"]["excluded_windows"] != mixed["provenance"]["excluded_windows"]:
        raise ValueError("Installed and mixed exclusions differ")
    full, short = (value["source"]["probes"] for value in (stock, mixed))
    for left, right in zip(full, short, strict=True):
        if opportunity(left) != opportunity(right) or len(left["candidates"]) > 1:
            raise ValueError("Paired original receiver opportunities differ")
    return full, short


def bind_native(raw, full, mixed):
    followers = defaultdict(Continuation)
    actual = {}
    for original, stock, (current, anchor) in zip(raw, full, decisions(mixed), strict=True):
        probe = original["opportunity"]
        if probe != opportunity(stock) or original["anchor"] != anchor:
            raise ValueError("Native alternatives do not align with original opportunities")
        modes = original["alternatives"]
        before_stock = modes["20-two"]
        _, chosen, _ = followers[probe["edge"]].select(dict(probe, candidates=before_stock))
        selected = [] if chosen is None else [before_stock[chosen]]
        candidate = strongest(modes["20-two" if anchor else "8-primary"])
        if stock["candidates"] != selected or current["candidates"] != ([] if candidate is None else [candidate]):
            raise ValueError("Both original receiver diagonals must agree exactly")
        if anchor:
            actual[slot(current)] = before_stock
    return actual


def plan(rows, alternatives=None):
    selector = AnchorHistory()
    result = []
    for row, anchor in decisions(rows):
        options = alternatives[slot(row)] if alternatives is not None and anchor else None
        factor, reason, recent, support = selector.choose(row, anchor, options)
        result.append(dict(slot=slot(row), anchor=anchor, selected=factor, reason=reason,
                           recent=recent, votes=support, measured_candidates=len(options) if options is not None else None))
    return result


def assess(full, mixed, sealed, session, installed_owners, mixed_owners):
    counts = Counter()
    changed = []
    for installed_row, mixed_row, choice in zip(full, mixed, sealed, strict=True):
        stock = strongest(installed_row["candidates"])
        original = strongest(mixed_row["candidates"])
        selected = choice["selected"]
        if slot(mixed_row) != choice["slot"]:
            raise ValueError("Sealed choices changed order")
        if not choice["anchor"]:
            if original != selected:
                raise ValueError("Anchor policy changed a short opportunity")
            continue
        oid = "sha256:" + sha256(f"{session}:{mixed_row['receiver_id']}:{mixed_row['valid_start_counter']}".encode()).hexdigest()
        counts.update(anchor_lanes=1, installed_positive=stock is not None, mixed_positive=original is not None,
                      after_positive=selected is not None, mixed_stock_exact_positive=stock is not None and stock == original,
                      changed_stock_exact_positive=stock is not None and stock == selected,
                      successor_only=stock is None and original is not None, lost_stock_positive=stock is not None and original is not None and selected is None,
                      displaced_stock_exact=stock is not None and stock == original and selected not in (None, stock),
                      restored_stock_exact=stock is not None and stock != original and stock == selected,
                      removed_successor_only=stock is None and original is not None and selected is None,
                      paid_alternative=choice["reason"] == "paid_alternative",
                      evaluated_positive_anchors=bool(choice["votes"]), vote_calls=len(choice["votes"]),
                      protected_by_sparse_history=choice["reason"] == "insufficient_history",
                      two_measured_alternatives=choice["measured_candidates"] == 2)
        if original != selected or stock is None and original is not None:
            owners_stock = [arm for arm in ARMS if oid in installed_owners[arm]]
            owners_mixed = [arm for arm in ARMS if oid in mixed_owners[arm]]
            if owners_stock and original != selected:
                counts["installed_owner_changed"] += 1
            if owners_mixed and stock is None:
                counts["successor_only_owned"] += 1
                counts["removed_successor_only_owned"] += selected is None
            changed.append(dict(choice, id=oid, counter=mixed_row["valid_start_counter"], stream=stream(mixed_row),
                                installed=stock, original=original, installed_owner_arms=owners_stock,
                                mixed_owner_arms=owners_mixed))
    return dict(lanes=len(sealed), admitted_stereo_visits=len(sealed)//2, counts=dict(counts), rows=changed)


def owner_sets(rows):
    return {arm: {row[0] for row in rows[arm]} for arm in ARMS}


def seal(rows):
    return sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def audit(installed_0049, mixed_0049):
    vote_path = HERE.parents[2] / "tools/pipeline_eval/variants/carrier_continuation.py"
    if sha256(vote_path.read_bytes()).hexdigest() != VOTE_SOURCE:
        raise ValueError("Released continuation source changed")
    archive = {name: read(MEASUREMENTS / name, pin) for name, pin in PINS.items() if name.endswith(".gz")}
    stock, mix = (read(path, PINS[name]) for path, name in [(installed_0049, "installed-0049.json"), (mixed_0049, "mixed-0049.json")])
    positions = archive["ds30-0049-saved-crossover.json.gz"]["ordered_owner_rows"]
    trial_0016 = archive["ds30-0016-full-primary-transfer.json.gz"]
    packets = trial_0016["detector_packets"]
    inputs = {
        "DS30-0049": (stock, mix, owner_sets(positions["installed-installed"]), owner_sets(positions["successor-successor"]),
                      archive["ds30-0049-receiver-factorial.json.gz"]["native-rows.json"]["document"], 384),
        "DS30-0016": (packets["installed"]["document"], packets["charted"]["document"],
                      owner_sets(trial_0016["installed_owners"]), owner_sets(trial_0016["charted_owners"]),
                      archive["late-pilot-rescue.json.gz"]["DS30-0016"]["long-receiver.json"]["document"], 808),
    }
    scopes = {}
    for case, (stock, mix, stock_owners, mixed_owners, raw, frontier) in inputs.items():
        # The runtime decisions use only the mixed packet and independently measured alternatives.
        mixed = mix["source"]["probes"]
        scoped_mixed = [r for r in mixed if r["visit_index"] < frontier]
        native = {slot(r["opportunity"]): r["alternatives"]["20-two"] for r in raw if r["anchor"]}
        selected = {"strongest_only": plan(mixed), "paid_alternatives": plan(scoped_mixed, native)}
        prediction = seal(selected)
        full, _ = paired(stock, mix)
        scoped_full = [r for r in full if r["visit_index"] < frontier]
        if bind_native(raw, scoped_full, scoped_mixed) != native:
            raise ValueError("Native predictions were sealed on a different scope")
        labels = mix["source"]["session_id"], stock_owners, mixed_owners
        control = assess(scoped_full, scoped_mixed, selected["strongest_only"][:len(scoped_full)], *labels)
        scopes[case] = dict(native_frontier_issued_visits=frontier, prediction_sha256=prediction, native_diagonals_exact=True,
                            strongest_only=assess(full, mixed, selected["strongest_only"], *labels),
                            strongest_only_native_scope=control,
                            paid_alternatives=assess(scoped_full, scoped_mixed, selected["paid_alternatives"], *labels))
    return dict(sources=PINS, vote_source=VOTE_SOURCE, no_original_reads=True, new_detector_calls=0, new_solver_calls=0, scopes=scopes)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("installed_0049", "mixed_0049", "output"):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    result = audit(args.installed_0049, args.mixed_0049)
    with args.output.open("x") as file:
        json.dump(result, file, sort_keys=True, separators=(",", ":"), allow_nan=False)
        file.write("\n")
