import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm
from selection import MODEL_NAMES, ROOT


def main():
    report = json.loads((ROOT / "comparison.json").read_text())
    selection = report["selection"]
    sessions = [selection["original_sample"], *selection["selected"]]
    lookup = {(row["model"], row["session_id"]): row for row in report["rows"]}
    errors = np.full((len(MODEL_NAMES), len(sessions)), np.nan)
    for model_index, model in enumerate(MODEL_NAMES):
        for session_index, session in enumerate(sessions):
            row = lookup[(model, session)]
            if row["success"] and row["reference_error_km"] is not None:
                errors[model_index, session_index] = max(row["reference_error_km"], 0.01)
    figure, axis = plt.subplots(figsize=(17, 9))
    palette = plt.get_cmap("viridis_r").copy()
    palette.set_bad("#dddddd")
    finite = errors[np.isfinite(errors)]
    maximum = max(10, float(np.max(finite))) if len(finite) else 10
    view = axis.imshow(errors, norm=LogNorm(vmin=0.1, vmax=maximum), cmap=palette, aspect="auto")
    for model_index, model in enumerate(MODEL_NAMES):
        for session_index, session in enumerate(sessions):
            row = lookup[(model, session)]
            if not row["attempted"]:
                label = "pending"
            elif not row["success"]:
                label = "failed"
            elif row["reference_error_km"] is None:
                label = "no ref"
            else:
                label = f"{row['reference_error_km']:.2f}"
            axis.text(
                session_index,
                model_index,
                label,
                ha="center",
                va="center",
                fontsize=7,
                color="black"
                if not np.isfinite(errors[model_index, session_index])
                or errors[model_index, session_index] > np.sqrt(0.1 * maximum)
                else "white",
            )
    axis.set_yticks(np.arange(len(MODEL_NAMES)), MODEL_NAMES)
    axis.set_xticks(
        np.arange(len(sessions)),
        ["original sample", *[sid[8:] for sid in sessions[1:]]],
        rotation=70,
        ha="right",
    )
    axis.axvline(0.5, color="black", linewidth=1.5)
    axis.set_title(
        "Single-scan localization comparison — reference error (km)\n"
        "Original sample + 16 frozen random DS11 scans; all-data, conditional candidate evidence"
    )
    figure.colorbar(view, ax=axis, label="Reference error (km, log color scale)")
    figure.tight_layout()
    figure.savefig(ROOT / "error-comparison.png", dpi=160)
    figure.savefig(ROOT / "error-comparison.svg")


if __name__ == "__main__":
    main()
