"""Oracle postfit line cuts; reference GPS never flows back into blind fitting."""

import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import CASES, problem_for, reference_xy
from run_dsx01_clock_transfer import measurement_path
from run_dsx01_joint_marginal import OUTPUT

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run(*, variants=("robust",)):
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    output = {}
    for ax, case in zip(axes.ravel(), CASES, strict=False):
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        for variant in variants:
            path = (
                OUTPUT / "robust_empirical" / case / "empirical/endpoints.json"
                if variant == "robust_empirical"
                else OUTPUT / case / variant / "endpoints.json"
            )
            if not path.exists():
                continue
            fits = json.loads(path.read_text())["fits"]
            start, endpoint = reference_xy(), np.array(fits["c0"]["east_north_km"])
            length = float(np.linalg.norm(endpoint - start))
            steps = np.linspace(-0.5, 1.5, 21)
            coords = start + steps[:, None] * (endpoint - start)
            scores = {}
            for arm, fit in fits.items():
                p = problem_for(scan, fit, variant)
                values = []
                for point in coords:
                    x = np.array(fit["parameters"])
                    x[:2] = point
                    z = p.residual(x)
                    values.append(float(z @ z))
                scores[arm] = values
                values = np.array(values)
                ax.plot(steps * length, values - values.min(), label=f"{variant}/{arm}")
            output[case + "/" + variant] = dict(
                east_north_km=coords,
                signed_distance_from_GPS_km=steps * length,
                scores=scores,
                c0_blind_endpoint_at_distance_km=length,
                nuisance_hyperparameters_and_phase_reference_frozen=True,
                linear_modes_reintegrated_at_each_position=True,
                labels_fixed_from_blind_fit=True,
                diagnostic_not_geographic_probability=True,
            )
        ax.axvline(0, color="black", ls=":", label="GPS")
        ax.set(
            title=case,
            xlabel="Along GPS → blind c0 endpoint (km)",
            ylabel="Loss above section minimum",
        )
        ax.legend(fontsize=6)
    axes.ravel()[-1].axis("off")
    fig.tight_layout()
    fig.savefig(OUTPUT / "postfit_loss_sections.png", dpi=170)
    plt.close(fig)
    write(OUTPUT / "postfit_loss_sections.json", output)
    print(json.dumps(dict(sections=len(output), positions_per_section=21)), flush=True)


if __name__ == "__main__":
    run()
