"""Illustrate only the synthetic same-satellite component, not recording accuracy."""

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    x = np.linspace(-3, 3, 201)
    a, b = np.meshgrid(x, x)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    for ax, rho in zip(axes[:2], (0, 0.25), strict=True):
        density = np.exp(-(a * a - 2 * rho * a * b + b * b) / (2 * (1 - rho * rho)))
        density /= 2 * np.pi * np.sqrt(1 - rho * rho)
        ax.contour(a, b, density, levels=[0.002, 0.01, 0.04, 0.08, 0.12], colors="tab:blue")
        ax.set(
            title=f"Same-satellite density: rho={rho}",
            xlabel="First residual / sigma",
            ylabel="Second residual / sigma",
            aspect="equal",
        )
        ax.grid(alpha=0.2)
    rho = 0.25
    for sign, label in ((1, "Same-sign residuals"), (-1, "Opposite-sign residuals")):
        # Candidate minus independent NLL, including the determinant constant.
        change = (
            0.5 * np.log(1 - rho * rho)
            + (2 * x * x - 2 * rho * sign * x * x) / (2 * (1 - rho * rho))
            - x * x
        )
        axes[2].plot(x, change, label=label)
    axes[2].axhline(0, color="black", linewidth=0.5)
    axes[2].set(
        title="Component NLL change",
        xlabel="Residual / sigma",
        ylabel="Correlated minus independent",
    )
    axes[2].legend(fontsize=8)
    axes[2].grid(alpha=0.2)
    fig.suptitle("Synthetic emission only; full model retains other labels and clutter")
    fig.savefig(Path(__file__).with_name("synthetic_component.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
