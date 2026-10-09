"""Illustrate synthetic identities; no recorded data or localization estimates."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    coordinate = np.linspace(-2, 2, 401)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for axis, signs, title in zip(
        axes,
        (np.array([-1, 1]), np.array([-1, -1, 1])),
        ("Balanced receivers: same minimum", "Unequal support: correction can help or hurt"),
        strict=True,
    ):
        measured = 2.0 * signs
        for amplitude, label, style in (
            (0.0, "No correction", "-"),
            (2.0, "Correct injected contrast", "--"),
            (4.0, "Overcorrected contrast", ":"),
        ):
            residual = measured[:, None] - coordinate[None, :] - amplitude * signs[:, None]
            loss = 0.5 * np.sum(residual**2, axis=0)
            # Subtract the continuous quadratic minimum; compare spatial shape,
            # not the arbitrary difference in differential residual loss.
            optimum = np.mean(measured - amplitude * signs)
            minimum = 0.5 * np.sum((measured - amplitude * signs - optimum) ** 2)
            axis.plot(coordinate, loss - minimum, style, label=label, linewidth=2)
        axis.axvline(0, color="black", alpha=0.4, linewidth=1)
        axis.set(title=title, xlabel="Synthetic common-frequency coordinate (Hz)")
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("Gaussian loss above each curve's minimum")
    axes[1].legend(fontsize=8)
    fig.suptitle("Synthetic geometry illustration — no measured position improvement")
    fig.savefig(Path(__file__).with_name("synthetic-geometry.png"), dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
