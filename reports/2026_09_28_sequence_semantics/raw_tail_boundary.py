"""Evaluate the fixed boundary/phase rule using locally demodulated raw IQ."""

import hashlib
import json
from pathlib import Path

import numpy as np
from region_phase_audit import fit_halves
from soft_tail_boundary import power_boundary

BASE = Path(__file__).parent


def eligible_transition(before, after):
    return before > 0.3 and after < 0.1


def main():
    source = BASE / "local/pilot_polarity.npz"
    provenance = BASE / "local/pilot_polarity.json"
    archive = np.load(source)
    order = np.argsort(np.fft.fftfreq(1024)[archive["bins"]])
    z = archive["deviations"][:, :, :, order]
    labels = [r["frame"] for r in json.loads(provenance.read_text())["checks"]]
    rows = []
    for frame, label in enumerate(labels):
        for edge in range(2):
            values = z[frame, edge]
            estimate = power_boundary(values[-6:].ravel(), flank=502)
            row = dict(
                frame=label,
                edge=edge,
                before_mean=estimate["before_mean"],
                after_mean=estimate["after_mean"],
            )
            row["eligible"] = eligible_transition(row["before_mean"], row["after_mean"])
            if row["eligible"]:
                boundary = 294 * 1004 + estimate["offset"]
                final = values[-1]
                valid = abs(final.imag) / np.maximum(abs(final), 1e-20) < 0.4
                valid &= np.arange(1004) + 299 * 1004 >= boundary
                fit = fit_halves(np.where(final.real >= 0, 1, -1), valid, 301)
                row.update(
                    boundary=boundary,
                    predicted_phase=(-boundary) % 60,
                    fitted_phase=fit["phase"],
                    fit=fit,
                    residue=(boundary + fit["phase"]) % 60,
                )
            rows.append(row)
    result = dict(
        rows=rows,
        boundary_flank=502,
        final_symbols=6,
        eligibility="Before mean quadrature fraction >0.3 and after <0.1; "
        "no phase is fitted for ineligible windows.",
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, provenance)
        },
        limitation="Raw-IQ-derived soft estimates; same public acquisition as "
        "reference data, different frames/processing. Both edges share SSS "
        "channel and timing estimates. Exploratory eligibility/window choices. "
        "Not independent acquisitions, FEC verification, or a semantic header decode.",
    )
    (BASE / "local/raw_tail_boundary.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
