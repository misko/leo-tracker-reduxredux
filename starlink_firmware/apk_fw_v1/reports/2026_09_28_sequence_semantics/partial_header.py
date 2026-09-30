"""Separate repeatable layout from repeated changing bits in the UT header."""

import hashlib
import json
from pathlib import Path

import numpy as np
from phase_model import codebook
from rest_signal import SEED

OUT = Path(__file__).parent / "local"


def variable_mask(bits, valid, discovery=3):
    return valid[:discovery].all(axis=0) & (abs(bits[:discovery].sum(axis=0)) < discovery)


def correlation(x, good, lag):
    keep = good[:-lag] & good[lag:]
    a, b = x[:-lag][keep], x[lag:][keep]
    score = None
    if len(a) >= 20 and min(a.std(), b.std()) > 0:
        score = float(np.corrcoef(a, b)[0, 1])
    return dict(pairs=int(keep.sum()), correlation=score)


def local_word(z, start, symbol):
    """Fit two nonoverlapping 120-carrier segments independently, no codebook."""
    words, scores = [], []
    for first in [start, start + 120]:
        mapping = (np.arange(first, first + 120) - 16 * symbol) % 60
        values = z[first : first + 120]
        sums = np.bincount(mapping, weights=values.real, minlength=60)
        signs = np.where(sums >= 0, 1, -1)
        words.append("".join("1" if v > 0 else "0" for v in signs))
        scores.append(
            float(np.mean(values.real * signs[mapping]) / np.sqrt(np.mean(abs(values) ** 2)))
        )
    return dict(accepted=words[0] == words[1] and min(scores) > 0.9, word=words[0], scores=scores)


def main():
    path = OUT / "pilot_polarity.npz"
    archive = np.load(path)
    order = np.argsort(np.fft.fftfreq(1024)[archive["bins"]])
    z = archive["deviations"][:, :, :12][:, :, :, order]
    bits = np.where(z[:, 0].real >= 0, 1, -1)
    valid = (abs((z / np.maximum(abs(z), 1e-12)).real) > 0.9).all(axis=1)
    valid &= np.sign(z[:, 0].real) == np.sign(z[:, 1].real)
    mask = variable_mask(bits[:, :6], valid[:, :6])
    rows = []
    rng = np.random.default_rng(281006)
    for s in range(6):
        for a in [3, 5]:
            x = bits[a, s] * bits[a + 1, s]
            good = mask[s] & valid[a, s] & valid[a + 1, s]
            scores = {str(lag): correlation(x, good, lag) for lag in [1, 2, 3, 59, 60, 61, 120]}
            # Conditional null permutes only qualified changing positions. No
            # assumption that the predominantly fixed positions are random bits.
            null = []
            for _ in range(999):
                shuffled = x.copy()
                shuffled[good] = rng.permutation(shuffled[good])
                value = correlation(shuffled, good, 60)["correlation"]
                if value is not None:
                    null.append(value)
            observed = scores["60"]["correlation"]
            p = (
                (1 + sum(abs(v) >= abs(observed) for v in null)) / (len(null) + 1)
                if observed is not None
                else None
            )
            rows.append(
                dict(
                    symbol=s + 2,
                    frames=[250 + a, 251 + a],
                    discovery_variable_positions=int(mask[s].sum()),
                    lags=scores,
                    lag60_two_sided_shuffle_p=p,
                )
            )
    book = codebook([int(c) for c in SEED])
    accepted, attempts = [], 0
    for f in range(7):
        for s in range(12):
            for start in range(0, 765, 60):
                fit = local_word(z[f, 0, s], start, s + 2)
                attempts += 1
                if fit["accepted"]:
                    accepted.append(
                        dict(
                            frame=f + 250,
                            symbol=s + 2,
                            start=start,
                            **fit,
                            phase_index=book.index(fit["word"]) if fit["word"] in book else None,
                        )
                    )
    result = dict(
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        conditional_lags=rows,
        local_word_attempts=attempts,
        local_word_accepted=accepted,
        scope="Seven UT frames; fixed 240-carrier windows stride 60; each half fits all "
        "60 bits without a codebook. Lag evaluation uses frames 253/254 and 255/256, "
        "with changing positions selected only on 250..252.",
        limitations="Exploratory reuse of inspected data. Shuffle p values are "
        "descriptive, unadjusted, and do not prove independence or semantics. "
        "Failure does not exclude shorter, shifted, or differently encoded allocations.",
    )
    (OUT / "partial_header.json").write_text(json.dumps(result, indent=2) + "\n")
    print("local fits", attempts, "accepted", len(accepted))
    for row in rows:
        if row["symbol"] == 6:
            print(json.dumps(row))


if __name__ == "__main__":
    main()
