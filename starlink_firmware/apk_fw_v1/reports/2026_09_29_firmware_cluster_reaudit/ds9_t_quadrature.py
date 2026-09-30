"""Fixed known-T sign coupling to DS9 early quadrature; no state or lag search."""

import json
from collections import Counter

import numpy as np
from ds9_leakage_transfer import BASE, OLD, load_correction, source

SEED = "010010100010010010001000000000001000100000101000001010100010"


def signs(states, bins, symbols):
    seed = np.array(list(map(int, SEED)))
    words = np.array([2 * (1 ^ seed ^ np.roll(seed, -k)) - 1 for k in range(60)])
    physical = [int(k) for k in np.argsort(np.fft.fftfreq(1024))
                if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)]
    slots = (np.array([physical.index(int(b)) for b in bins])[None, :]
             - 16 * np.array(symbols)[:, None]) % 60
    return words[np.array(states)[:, None, None], slots[None]]


def predict(train_x, train_y, test_x):
    mx, my = train_x.mean(axis=0), train_y.mean(axis=0)
    x, y = train_x - mx, train_y - my
    slope = (x * y).sum(axis=0) / np.maximum((x * x).sum(axis=0), 1e-20)
    return my + slope * (test_x - mx), my


def reductions(y, prediction, baseline):
    denominator = np.sum((y - baseline) ** 2)
    if denominator <= 0:
        raise ValueError("Constant held target")
    return np.array([1 - np.sum((y - np.roll(prediction, k, axis=0)) ** 2) / denominator
                     for k in range(len(y))])


def main():
    receipt_path = BASE / "local/ds9-leakage-transfer.json"
    receipt = json.loads(receipt_path.read_text())
    correct = load_correction()
    visits = []
    for visit in receipt["visits"]:
        tag = visit["visit"]
        path = OLD / ("ds9_word_audit.json" if tag == "middle" else "ds9_last_word_audit.json")
        states = {}
        for row in json.loads(path.read_text())["rows"]:
            if row["accepted"] and row["phase"] is not None and row["last_symbol"] < 242:
                assert states.get(row["frame"], row["phase"]) == row["phase"]
                states[row["frame"]] = row["phase"]
        train, held = visit["discovery_frames"], visit["evaluation_frames"]
        counts = Counter(states[f] for f in train)
        supported = [f for f in held if counts[states[f]] >= 2]
        cache = OLD / f"DS9-{tag}-soft.npz"
        assert source(cache) == visit["source"]
        controls, rows, tail_controls = [], [], []
        with np.load(cache) as data:
            bins = data["bins0"]
            assert np.array_equal(bins, data["bins1"])
            tx, hx = [signs([states[f] for f in frames], bins, range(2, 8))
                      for frames in (train, held)]
            for rx in (0, 1):
                tail_tx, tail_hx = [signs([states[f] for f in frames], bins, range(272, 302))
                                    for frames in (train, held)]
                tail_prediction, tail_baseline = predict(
                    tail_tx, data[f"z{rx}"][train, 270:300].real, tail_hx)
                tail_scores = reductions(data[f"z{rx}"][held, 270:300].real,
                                         tail_prediction, tail_baseline)
                tail_controls.append(dict(receiver=rx, symbols=[272, 301],
                                          held_mse_reduction=float(tail_scores[0])))
                tr, he = [data[f"z{rx}"][frames, :6].astype(np.complex128)
                          for frames in (train, held)]
                tr_axes, he_axes = correct(tr, tr), correct(tr, he)
                for name, axis in (("Q", 1), ("Q_after_I_regression", 2)):
                    prediction, baseline = predict(tx, tr_axes[axis], hx)
                    for lo, hi in [(0, 6), *[(i, i + 1) for i in range(6)]]:
                        scores = reductions(he_axes[axis][:, lo:hi], prediction[:, lo:hi],
                                            baseline[lo:hi])
                        controls.append(scores)
                        rows.append(dict(receiver=rx, component=name, symbols=[lo + 2, hi + 1],
                                         held_mse_reduction=float(scores[0])))
        # Same rotation for every coordinate/receiver/model within an excerpt.
        maxima = np.array(controls).max(axis=0)
        for row in rows:
            row["two_excerpt_family_rank"] = min(1., 2 * float(np.mean(
                maxima >= row["held_mse_reduction"] - 1e-12)))
        visits.append(dict(visit=tag, source=source(cache), state_source=source(path),
                           discovery_frames=train, evaluation_frames=held,
                           states_train=[states[f] for f in train],
                           states_held=[states[f] for f in held],
                           categorical_supported_frames=supported, rows=rows,
                           known_tail_positive_controls=tail_controls))
    output = dict(visits=visits, source=source(receipt_path),
                  method=source(BASE / "ds9_t_quadrature.py"),
                  limitation="Fixed known-T mapping only, no phase/polarity/lag scan. "
                  "Coordinate offset and slope fit discovery frames separately per RX. "
                  "Positive held MSE reduction against discovery-mean baseline is required "
                  "before considering cyclic rank. Max over 28 assays per excerpt, two-excerpt "
                  "Bonferroni. Previously examined reserved frames, irregular frame gaps, "
                  "and paired state selection limit inference. Negative result does not "
                  "exclude arbitrary nonlinear state coupling or unknown scrambling.")
    (BASE / "local/ds9-t-quadrature.json").write_text(json.dumps(output, indent=2) + "\n")
    for v in visits:
        print(v["visit"], "categorical support", len(v["categorical_supported_frames"]),
              [(r["receiver"], r["component"], round(r["held_mse_reduction"], 5),
                r["two_excerpt_family_rank"]) for r in v["rows"] if r["symbols"] == [2, 7]])
        print("Known-tail controls", v["known_tail_positive_controls"])


if __name__ == "__main__":
    main()
