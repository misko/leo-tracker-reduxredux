"""Select imaginary-sign sequence candidates on discovery carriers only."""

import hashlib
import json
from pathlib import Path

import numpy as np
from phase_lfsr import extend
from region_phase_audit import WORDS
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent
PN_SEED = [0, 1, 0, 0, 1, 1, 1, 0, 1, 1, 0, 1, 0, 0, 1]


def select_candidate(candidates, observed, valid, split=120):
    scores = candidates[:, :split].astype(np.int32) @ (
        observed[:split].astype(np.int32) * valid[:split]
    )
    chosen = int(np.argmax(abs(scores)))
    polarity = 1 if scores[chosen] >= 0 else -1
    prediction = polarity * candidates[chosen]
    counts, errors, baseline = [], [], []
    for region in (slice(None, split), slice(split, None)):
        a, b = observed[region][valid[region]], prediction[region][valid[region]]
        counts.append(int(a.size))
        errors.append(int((a != b).sum()))
        baseline.append(
            float(np.mean(a == 1) * np.mean(b == 1) + np.mean(a == -1) * np.mean(b == -1))
        )
    return dict(
        candidate=chosen,
        polarity=polarity,
        support=counts,
        errors=errors,
        marginal_agreement=baseline,
    )


def main():
    source = BASE / "local/full-reference-0-12.npz"
    boundary_path = BASE / "local/tail_axis_boundary.json"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    physical = np.array([k for k in np.argsort(np.fft.fftfreq(1024)) if 2 <= k < 1022])
    keep = ~np.isin(physical, np.r_[488:496, 528:536])
    bins, indices = physical[keep], np.flatnonzero(keep)
    symbols = np.load(source)["symbols"]
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = symbols[:, 1:][:, :, bins] * np.exp(-0.5j * np.pi * template[bins, 1:].T)
    cyclic = np.concatenate(
        [WORDS[:, (np.arange(240) + offset) % 60] for offset in range(60)]
    ).astype(np.int8)
    pn = 1 - 2 * extend(np.array(PN_SEED), 32767).astype(np.int8)
    pn_candidates = pn[(np.arange(32767)[:, None] + indices[None, -240:]) % 32767]
    rows = []
    for boundary in json.loads(boundary_path.read_text())["rows"]:
        if boundary["allowed_errors"] or boundary["residue"] == 0:
            continue
        frame = boundary["frame"]
        symbol = boundary["boundary"] // 1004 + 1
        values = z[frame, symbol - 2, -240:]
        valid = np.isfinite(values) & (abs(values.imag) > 0.05) & (abs(values.real) > 0.05)
        q = np.where(values.imag >= 0, 1, -1)
        i = np.where(values.real >= 0, 1, -1)
        for transform, observed in (("Q_sign", q), ("I_sign_times_Q_sign", i * q)):
            for family, candidates in (("cyclic_60", cyclic), ("pn_32767", pn_candidates)):
                fit = select_candidate(candidates, observed, valid)
                rows.append(
                    dict(
                        frame=frame,
                        symbol=symbol,
                        transform=transform,
                        family=family,
                        candidate_count=len(candidates),
                        **fit,
                    )
                )
    result = dict(
        rows=rows,
        split=120,
        window=240,
        pn_seed=PN_SEED,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, boundary_path, template_path)
        },
        limitation="Previously examined recording, exploratory frame/window choice. "
        "Candidate and polarity chosen on first 120 carriers only; remaining 120 "
        "are evaluation. No verified QAM bit labels, independent acquisition, "
        "or claim that these two sequence families exhaust possible scramblers.",
    )
    (BASE / "local/qam_imaginary_probe.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        print(row["frame"], row["transform"], row["family"], row["errors"], row["support"])


if __name__ == "__main__":
    main()
