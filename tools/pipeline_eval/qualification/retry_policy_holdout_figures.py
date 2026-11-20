"""Render measured stage counts and standard v2 position comparisons."""

import matplotlib
import numpy as np

from ..__main__ import save_json
from .capture_whole_results import MINIMAL, POS, generate
from .full_v5_check import _sha
from .retry_policy_holdout_results import CONTROL, FULL, LABELS, MISS, MODES, PRIMARY, TWO

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def render(output, support):
    by_mode = {r["policy"]: r for r in support}
    legend = dict(zip(MODES, LABELS, strict=True))
    x = np.arange(len(MODES))
    labels = (
        "Full\nconditional",
        "Primary\nonly",
        "2 s after\none failure",
        "0.8 s after\ntwo failures",
        "Matched\nhash control",
    )
    colors = ("#465981", "#a77f61", "#5d8e8a", "#256e66", "#a96552")
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), layout="constrained")
    for ax, field, title in zip(
        axes,
        ("attempts", "rescues"),
        ("Original retries executed", "Original rescues retained"),
        strict=True,
    ):
        y = [by_mode[mode][field] for mode in MODES]
        ax.bar(x, y, color=colors, width=0.72)
        ax.set_ylim(0, max(y) * 1.18)
        ax.set_xticks(x, labels)
        ax.set_title(title)
        ax.spines[["right", "top"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.2)
        for i, n in enumerate(y):
            ax.text(i, n + max(y) * 0.025, f"{n:,}", ha="center", fontsize=9)
    fig.suptitle("Causal retry policies on the independent DS26-0162 recording")
    for suffix in ("png", "pdf"):
        fig.savefig(output / f"stage.{suffix}", dpi=165)
    plt.close(fig)
    save_json(
        output / "stage-figure.json",
        dict(
            version=1,
            id="retry-policy-independent-holdout-stage",
            title="Causal retry policies on DS26-0162",
            image="stage.png",
            pdf="stage.pdf",
            csv="retry-counts.csv",
            sample="Complete DS26-0162 recording",
            seal="stage-lock.json",
            boundary="Matched primary and original conditional detector outcomes",
            note="The hash control matches attempt counts by physical receiver and RF.",
        ),
    )
    save_json(
        output / "stage-lock.json",
        dict(
            files={
                name: _sha(output / name)
                for name in ("stage.png", "stage.pdf", "stage-figure.json", "retry-counts.csv")
            }
        ),
    )
    charts = []
    for name, series, title in (
        ("causal", (TWO, FULL, MISS, PRIMARY), "Position under causal retry policies"),
        ("matched", (TWO, FULL, CONTROL, MISS), "Position against the physical-key hash control"),
    ):
        charts.append(
            dict(
                id="retry-policy-holdout-" + name,
                method=TWO,
                scope="roof",
                cases="sealed",
                title=title,
                seal="prediction-lock.json",
                caption="DS26-0162 kept the original region, causal catalogue and search budget. "
                "All included policy inputs are complete native factor streams.",
                provenance=["retry-counts.csv", "resources.json", "policy-lock.json"],
                series=[
                    dict(
                        key=key,
                        label=legend[mode],
                        file=POS,
                        value=mode,
                        native_field="paired_capture_sha256",
                        match=MINIMAL,
                    )
                    for key, mode in zip(
                        ("one", "stock", "all_visits", "one_native_factors"), series, strict=True
                    )
                ],
            )
        )
    save_json(output / "figures.json", dict(version=2, charts=charts))
    generate(output / "charts", evidence=output)
