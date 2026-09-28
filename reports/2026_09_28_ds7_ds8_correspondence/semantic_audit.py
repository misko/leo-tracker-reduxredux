"""Restricted, falsifiable semantic/code-model checks; no guessed field labels."""

import csv
import hashlib
import json
from collections import defaultdict
from functools import reduce
from pathlib import Path

BASE = Path(__file__).parent


def polynomial_gcd(a, b):
    """Binary polynomial GCD, coefficient of x**i stored in bit i."""
    while b:
        remainder = a
        while remainder and remainder.bit_length() >= b.bit_length():
            remainder ^= b << (remainder.bit_length() - b.bit_length())
        a, b = b, remainder
    return a


def counter_matches(rows, start, width, reverse=False, invert=False):
    groups = defaultdict(list)
    for row in rows:
        s = row["word"][start : start + width]
        value = int(s[::-1] if reverse else s, 2)
        if invert:
            value ^= (1 << width) - 1
        groups[row["group"]].append((row["frame"], value))
    hits = total = 0
    for values in groups.values():
        values.sort()
        for (a, x), (b, y) in zip(values, values[1:], strict=False):
            total += 1
            hits += ((y - x) % (1 << width)) == ((b - a) % (1 << width))
    return hits, total


def main():
    sources = [BASE / "local/decoded-bits.csv"]
    rows = [
        dict(
            group=r["group"],
            frame=int(r["frame"]),
            word=r["raw_bits"],
            identity=r["norad_id"] or None,
            source="original",
        )
        for r in csv.DictReader(sources[0].open())
    ]
    for path in sorted((BASE / "local/rate-validation/native").glob("*/native-results.json")):
        sources.append(path)
        result = json.loads(path.read_text())
        rows.extend(
            dict(
                group=result["group"],
                frame=r["frame"],
                word=r["rx0_word"],
                identity=None,
                source="native",
            )
            for r in result["results"]
            if r["full_word_candidate"]
        )
    assert all(len(r["word"]) == 60 and set(r["word"]) <= {"0", "1"} for r in rows)
    constraints = {}
    for source in ["original", "native"]:
        words = [r["word"] for r in rows if r["source"] == source]
        constraints[source] = dict(
            observations=len(words),
            distinct_words=len(set(words)),
            odd_parity_words=sum(w.count("1") % 2 for w in words),
            cyclic_generator_gcd=reduce(polynomial_gcd, [int(w, 2) for w in words], (1 << 60) | 1),
        )
    # Restricted raw, contiguous, binary per-frame counter. No arbitrary
    # interleavers, nonlinear transforms, or semantic labels fitted here.
    best = None
    exact = []
    for width in range(2, 33):
        for start in range(61 - width):
            for reverse in [False, True]:
                for invert in [False, True]:
                    hit, total = counter_matches(rows, start, width, reverse, invert)
                    trial = dict(
                        start=start,
                        width=width,
                        reverse=reverse,
                        invert=invert,
                        matches=hit,
                        transitions=total,
                    )
                    if best is None or hit > best["matches"]:
                        best = trial
                    if total and hit == total:
                        exact.append(trial)
    by_id = defaultdict(list)
    for row in rows:
        if row["identity"]:
            by_id[row["identity"]].append(row["word"])
    invariant = {
        key: [i for i in range(60) if len({w[i] for w in words}) == 1]
        for key, words in by_id.items()
    }
    common_fixed = sorted(set.intersection(*(set(v) for v in invariant.values())))
    output = dict(
        input_sha256={
            str(p.relative_to(BASE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        },
        constraints=constraints,
        counter_exact_candidates=exact,
        counter_best_exploratory=best,
        identity_observations={key: len(value) for key, value in by_id.items()},
        invariant_positions_by_identity=invariant,
        positions_fixed_within_every_identity=common_fixed,
        limitations=[
            "Repeated observations and rotation-related words are dependent.",
            "Parity/generator arithmetic describes recovered words, "
            "not verified transmitter fields.",
            "GCD 3 means x+1 only: excludes a stronger common ordinary length-60 "
            "binary cyclic generator, not arbitrary FEC.",
            "Counter scan is exploratory; best score is not a discovery or held-out validation.",
            "Only raw contiguous unsigned counters advancing one per RF frame "
            "were tested, both bit directions and polarities.",
            "Fixed-bit ID test assumes aligned systematic uncoded positions "
            "and conditional orbital labels.",
            "Native words have no satellite labels assigned by this audit.",
        ],
    )
    path = BASE / "local/semantic-audit.json"
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "input_sha256"}, indent=2))


if __name__ == "__main__":
    main()
