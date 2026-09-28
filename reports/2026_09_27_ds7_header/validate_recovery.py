"""Export eight post-SSS soft symbols and validate without header phase fitting."""

import csv
import hashlib
import json

import matplotlib
import numpy as np
from analyze import OUT
from recover import BINS, references

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    out = OUT / "dual"
    inventory = json.loads((out / "inventory.json").read_text())
    rows = json.loads((out / "recovery.json").read_text())
    archive = np.load(out / "recovery-soft-symbols.npz")
    _, template, _ = references()
    zs = [archive[r["name"] + "_symbols"][:, :8] for r in rows]
    variances = [np.mean([d["pilot_holdout_evm"] ** 2 for d in r["diagnostics"]]) for r in rows]
    weights = 1 / np.array(variances)
    weights /= weights.sum()
    combined = sum(w * z for w, z in zip(weights, zs, strict=True))
    deviations = combined * template[BINS, 1:9].T.conj()
    rng = np.random.default_rng(20260927)
    validation = []
    for name, z in zip(["RX0", "RX1", "combined"], [*zs, combined], strict=True):
        unit = z / np.maximum(abs(z), 1e-20)
        matched = unit * template[BINS, 1:9].T.conj()
        per_frame = np.mean((matched**2).real, axis=(1, 2))
        # The physical BPSK axis is fixed to the SSS phase convention. There is
        # no phase rotation fitted against the desired header match.
        split = []
        for parity in [0, 1]:
            subset = unit[parity::2]
            exact = float(per_frame[parity::2].mean())
            controls = []
            for _ in range(1000):
                shifts = rng.integers(1, 300, size=len(BINS))
                wrong = template[
                    BINS[:, None], (np.arange(1, 9)[None, :] + shifts[:, None]) % 301
                ].T
                controls.append(float(np.mean(((subset * wrong.conj()) ** 2).real)))
            boot = rng.choice(per_frame[parity::2], size=(2000, len(subset)), replace=True).mean(
                axis=1
            )
            split.append(
                dict(
                    parity=parity,
                    frames=len(subset),
                    fixed_axis_statistic=exact,
                    wrong_template_max=max(controls),
                    randomization_tail_fraction=(1 + sum(v >= exact for v in controls)) / 1001,
                    frame_bootstrap_95_percent=np.quantile(boot, [0.025, 0.975]).tolist(),
                )
            )
        validation.append(
            dict(
                source=name,
                splits=split,
                by_symbol_fixed_axis=np.mean((matched**2).real, axis=(0, 2)).tolist(),
            )
        )
    agreement = float(
        np.mean(
            ((zs[0] * template[BINS, 1:9].T.conj()).real > 0)
            == ((zs[1] * template[BINS, 1:9].T.conj()).real > 0)
        )
    )
    np.savez_compressed(
        out / "post-sss-eight-symbols.npz",
        ofdm_symbols=np.arange(2, 10),
        subcarrier_indices=BINS,
        rx0=zs[0],
        rx1=zs[1],
        combined=combined,
        template_removed=deviations,
        provisional_sign=np.where(deviations.real >= 0, 1, -1),
        frame_epochs_rx0=rows[0]["corrected_frame_epochs_samples"],
        frame_epochs_rx1=rows[1]["corrected_frame_epochs_samples"],
        weights=weights,
    )
    with (out / "post-sss-eight-symbols.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "frame",
                "ofdm_symbol",
                "subcarrier",
                "I",
                "Q",
                "template_removed_I",
                "template_removed_Q",
                "provisional_sign",
            ]
        )
        for frame in range(len(combined)):
            for symbol in range(8):
                for column, bin_index in enumerate(BINS):
                    z, d = combined[frame, symbol, column], deviations[frame, symbol, column]
                    writer.writerow(
                        [
                            frame,
                            symbol + 2,
                            bin_index,
                            z.real,
                            z.imag,
                            d.real,
                            d.imag,
                            1 if d.real >= 0 else -1,
                        ]
                    )
    result = dict(
        scope="Eight in-band post-SSS soft OFDM symbols, not error-free decoded bits",
        session_id=inventory["exports"][0]["session_id"],
        visit=2022,
        frames=len(combined),
        ofdm_symbols=list(range(2, 10)),
        subcarriers=BINS.tolist(),
        validation=validation,
        receiver_sign_agreement=agreement,
        combining_weights=weights.tolist(),
        caveat="Split frame tests share pilot/SSS-only nuisance calibration. Receiver errors may "
        "be correlated. Control ranks are exploratory, not calibrated detection probabilities.",
    )
    (out / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7))
    for r in validation:
        axes[0].plot(np.arange(2, 10), r["by_symbol_fixed_axis"], "o-", label=r["source"])
    axes[0].axhline(0, color="grey", lw=0.8)
    axes[0].set(
        xlabel="OFDM symbol (SSS = 1)",
        ylabel="Fixed-axis BPSK template statistic",
        title="Eight consecutive post-SSS symbols · 89 frames",
        ylim=(-0.02, 0.3),
    )
    axes[0].legend()
    angle = np.angle(deviations).ravel()
    axes[1].hist(angle, bins=48, density=True, color="tab:blue", alpha=0.75)
    axes[1].axhline(1 / (2 * np.pi), color="grey", ls="--", label="uniform phase")
    axes[1].set(
        xlabel="Template-removed phase (radians)",
        ylabel="Density",
        title="Combined receivers · no header-fitted phase rotation",
    )
    axes[1].legend()
    fig.suptitle("DS7 recovery after pilot-derived timing-rate correction (~3.5 ppm)")
    fig.text(
        0.5,
        0.015,
        f"Soft recovery only: independent receiver sign agreement {agreement:.1%}; "
        "no FEC/CRC or decoded metadata.",
        ha="center",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    fig.savefig(out / "recovered-eight-symbols.png", dpi=160)
    sources = list(__import__("pathlib").Path(__file__).parent.glob("*.py"))
    artifacts = [
        out / "inventory.json",
        out / "recovery.json",
        out / "validation.json",
        out / "post-sss-eight-symbols.npz",
        out / "post-sss-eight-symbols.csv",
        out / "recovered-eight-symbols.png",
    ]
    (out / "RECOVERY-SHA256SUMS").write_text(
        "".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + str(p) + "\n"
            for p in sources + artifacts
        )
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
