"""Compare the same header carriers in UT and DS7; do not infer field meaning."""

import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    root = Path(__file__).resolve().parents[2]
    out = Path(__file__).parent / "local"
    source = root / "reports/2026_09_27_ut_header/local/fullband/soft_deviations.npz"
    ut = np.load(source)
    metadata = json.loads(source.with_name("results.json").read_text())
    assert len(ut["subcarriers"]) == 1004
    bins = np.r_[476:488, 496:508]
    indices = [list(ut["subcarriers"]).index(k) for k in bins]
    z = ut["deviations"][:, 2, indices]
    observed = json.loads((out / "holdout-upper/recurring-words.json").read_text())
    # Select actual validation output, never the rejected frozen hypothesis.
    checks = observed["words"]
    patterns = [
        c["mean_sign_pattern"]
        for phase in checks
        for c in phase["validation"]
        if c["source"] == "combined"
    ]
    assert len(set(patterns)) == 1
    reference = np.array([int(b) for b in patterns[0]], dtype=bool)
    rows = []
    for frame, values in enumerate(z):
        signs = values.real > 0
        rows.append(
            dict(
                ut_frame_id=metadata["frames"][frame]["frame_id"],
                word="".join(str(int(b)) for b in signs),
                agreeing_bits=int(np.sum(signs == reference)),
                agreeing_bits_if_global_polarity_reversed=int(np.sum(signs != reference)),
                minimum_abs_real=float(np.min(abs(values.real))),
            )
        )
    result = dict(
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        ds7_source_sha256=hashlib.sha256(
            (out / "holdout-upper/recurring-words.json").read_bytes()
        ).hexdigest(),
        bins=bins.tolist(),
        ofdm_symbol=4,
        ds7_pattern=patterns[0],
        ut=rows,
        interpretation="Stable within each tested excerpt, different between UT and DS7. "
        "No satellite, beam, MCS, counter, or timing interpretation established.",
        limitation="UT uses blind per-symbol BPSK-axis alignment with global sign ambiguity. "
        "Both polarities are reported; no unknown bits are used to force a cross-capture match.",
    )
    (out / "ut-ds7-header-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
