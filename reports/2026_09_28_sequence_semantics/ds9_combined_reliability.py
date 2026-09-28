"""Measure carrier errors and frozen amplitude gates on combined sequence signs."""

import hashlib
import json
from pathlib import Path

import numpy as np
from region_phase_audit import WORDS

BASE = Path(__file__).parent


def gate_result(values, expected, threshold, carrier_mask):
    keep = (abs(values.real) >= threshold) & carrier_mask[None, None, :]
    count = int(keep.sum())
    errors = int((((values.real >= 0) != (expected >= 0)) & keep).sum())
    return dict(count=count, errors=errors, disagreement=None if not count else errors / count)


def main():
    physical = [
        int(k)
        for k in np.argsort(np.fft.fftfreq(1024))
        if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
    ]
    compact = {b: i for i, b in enumerate(physical)}
    datasets, hashes = {}, {}
    for tag in ("middle", "last"):
        source = BASE / f"local/DS9-{tag}-soft.npz"
        wp = BASE / (
            "local/ds9_word_audit.json" if tag == "middle" else "local/ds9_last_word_audit.json"
        )
        a = np.load(source)
        assert np.array_equal(a["bins0"], a["bins1"])
        phase = {}
        for r in json.loads(wp.read_text())["rows"]:
            if r["accepted"] and r["phase"] is not None and r["last_symbol"] < 242:
                assert r["frame"] not in phase or phase[r["frame"]] == r["phase"]
                phase[r["frame"]] = r["phase"]
        frames = sorted(phase)
        split = len(frames) // 2
        values = (a["z0"][frames, 240:300] + a["z1"][frames, 240:300]) / 2
        slots = (
            np.array([compact[int(b)] for b in a["bins0"]])[None, :]
            - 16 * np.arange(242, 302)[:, None]
        ) % 60
        expected = WORDS[np.array([phase[f] for f in frames])[:, None, None], slots[None]]
        train, held = values[:split, :30], values[split:, 30:]
        train_truth, held_truth = expected[:split, :30], expected[split:, 30:]
        train_error = ((train.real >= 0) != (train_truth >= 0)).mean(axis=(0, 1))
        keep = np.ones(len(a["bins0"]), bool)
        keep[np.argsort(train_error, kind="stable")[-6:]] = False
        thresholds = {
            str(q): float(np.quantile(abs(train.real), q)) for q in (0, 0.5, 0.75, 0.9, 0.95)
        }
        datasets[tag] = dict(
            values=held,
            expected=held_truth,
            bins=a["bins0"],
            keep=keep,
            thresholds=thresholds,
            train_errors=train_error.tolist(),
            held_errors=((held.real >= 0) != (held_truth >= 0)).mean(axis=(0, 1)).tolist(),
            discovery_frames=frames[:split],
            evaluation_frames=frames[split:],
        )
        for p in (source, wp):
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    assert np.array_equal(datasets["middle"]["bins"], datasets["last"]["bins"])
    rows = []
    for target, d in datasets.items():
        for fit_tag, model in datasets.items():
            gates = []
            for quantile, threshold in model["thresholds"].items():
                gates.append(
                    dict(
                        quantile=float(quantile),
                        threshold=threshold,
                        all_carriers=gate_result(
                            d["values"], d["expected"], threshold, np.ones(len(d["bins"]), bool)
                        ),
                        selected_carriers=gate_result(
                            d["values"], d["expected"], threshold, model["keep"]
                        ),
                    )
                )
            rows.append(
                dict(
                    target=target,
                    fit_visit=fit_tag,
                    dropped_bins=model["bins"][~model["keep"]].tolist(),
                    gates=gates,
                )
            )
    output = dict(
        rows=rows,
        per_visit={
            tag: {
                k: (v.tolist() if isinstance(v, np.ndarray) else v)
                for k, v in d.items()
                if k not in ("values", "expected")
            }
            for tag, d in datasets.items()
        },
        input_sha256=hashes,
        limitation="Thresholds and worst6carriers chosen only "
        "first22frames symbols242–271; evaluate last23frames symbols272–301. "
        "Quantiles prespecified. Frozen cross-visit transfer also reported. "
        "Disagreement against inferred sequence, not independently verified BER "
        "or demonstrated header reliability. No raw/native data changed.",
    )
    (BASE / "local/ds9_combined_reliability.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
