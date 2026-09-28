"""Diagnose the fixed 498/503 candidate using other carriers' common phase."""

import hashlib
import json
from pathlib import Path

import numpy as np
from local_header_relations import correlation, normalized

BASE = Path(__file__).parent


def unit(z):
    return z / np.maximum(abs(z), 1e-20)


def correct(z, bins, train):
    targets = [int(np.flatnonzero(bins == b)[0]) for b in (498, 503)]
    means = unit(z[train]).mean(axis=0)
    references = (abs(means) >= 0.5) & ~np.isin(bins, [498, 503])
    if references.sum() < 3:
        return None
    # Fixed discovery mean phase removes carrier-specific offsets. Neither target
    # contributes to selection or the per-frame nuisance-phase estimate.
    phase_vector = (unit(z[:, references]) * unit(means[references]).conj()).mean(axis=1)
    corrected = z[:, targets] * np.exp(-1j * np.angle(phase_vector[:, None]))
    return corrected, phase_vector, bins[references]


def describe(z):
    a, b = z.T
    p, q = (a.real >= 0).mean(), (b.real >= 0).mean()
    return dict(
        soft_correlation=correlation(normalized(a), normalized(b)),
        sign_agreement=float(np.mean((a.real >= 0) == (b.real >= 0))),
        positive_fractions=[float(p), float(q)],
        marginal_baseline=float(p * q + (1 - p) * (1 - q)),
        relative_phase_coherence=float(abs(np.mean(unit(a) * unit(b).conj()))),
    )


def main():
    audit = json.loads((BASE / "local/local_header_recovery.json").read_text())
    rows = []
    for item in audit["rows"]:
        if item["signal"] not in ("S13", "S22", "S23"):
            continue
        path = BASE / "local" / f"{item['signal']}-soft.npz"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        data = np.load(path)
        train, held = item["discovery_frames"], item["evaluation_frames"]
        for rx in range(2):
            bins, z = data[f"bins{rx}"], data[f"z{rx}"][:, 0]
            result = correct(z, bins, train)
            row = dict(
                signal=item["signal"],
                receiver=rx,
                source_sha256=item["sha256"],
                discovery_frames=train,
                evaluation_frames=held,
            )
            if result is not None:
                corrected, vector, references = result
                indices = [int(np.flatnonzero(bins == b)[0]) for b in (498, 503)]
                row.update(
                    reference_bins=references.tolist(),
                    phase_concentration=float(abs(unit(vector[held]).mean())),
                    reference_vector_mean_magnitude=float(abs(vector[held]).mean()),
                    before=describe(z[held][:, indices]),
                    after=describe(corrected[held]),
                )
            rows.append(row)
            print(json.dumps(row))
    output = dict(
        rows=rows,
        limitation="Exploratory nuisance-phase diagnostic. Reference "
        "carriers are selected by discovery coherence, not independently known "
        "bits. Removing their common phase can remove real shared modulation. "
        "This is not a validated calibration or a bit decoder.",
    )
    (BASE / "local/header_common_phase.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
