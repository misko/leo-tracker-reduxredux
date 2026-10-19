"""Pair completed conditional maps with independently initialized restart plots.

This is reporting only. Missing restart data remain explicitly pending, and
the archived scientific figures are never modified.
"""

import hashlib
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "reports/2026_10_18_dsx01_clean_region"


def relative(path, directory):
    return Path(os.path.relpath(path, directory)).as_posix()


def paired_figure(original, restarted, destination, title):
    figure, axes = plt.subplots(2, 1, figsize=(13, 12.5), layout="constrained")
    for axis, path, label in zip(
        axes,
        (original, restarted),
        (
            "Original: conditional loss and downhill directions",
            "New: independent-start paths and endpoints",
        ),
        strict=True,
    ):
        axis.imshow(plt.imread(path))
        axis.set_axis_off()
        axis.set_title(label, fontsize=11, loc="left")
    figure.suptitle(title, fontsize=12)
    figure.savefig(destination, dpi=155)
    plt.close(figure)


def generate(output, original_root=ORIGINAL):
    output, original_root = Path(output).resolve(), Path(original_root).resolve()
    protocol_path = output / "protocol.json"
    if not protocol_path.exists():
        return dict(methods=0, comparisons=0)
    protocol = json.loads(protocol_path.read_text())
    rows_path = output / "restart_summary.json"
    rows = json.loads(rows_path.read_text()) if rows_path.exists() else []
    methods, cases = protocol.get("methods", []), protocol.get("cases", [])
    expected = len(protocol.get("starts", []))
    directory = output / "comparisons"
    directory.mkdir(exist_ok=True)
    cache_path = directory / "figure_bindings.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    new_cache, index, comparisons = {}, [], 0
    summary = []
    for case in cases:
        case_dir = directory / case
        case_dir.mkdir(exist_ok=True)
        table = [
            f"# {case}: original and independent-start maps\n",
            "Each linked page shows the original conditional loss map and the new "
            "independent-start plot, with c = 0 and fitted c in both. "
            "Pending results are not drawn as completed runs.\n",
            "| Algorithm / configuration | c = 0 starts | Fitted-c starts | Status |",
            "| --- | ---: | ---: | --- |",
        ]
        for method in methods:
            original = original_root / case / "surfaces" / method / "loss_gradient.png"
            restarted = output / case / method / "restart_basins.png"
            final_loss = output / case / method / "restart_loss.png"
            selected = [r for r in rows if r["case"] == case and r["method"] == method]
            counts = {
                arm: len({str(r["start_id"]) for r in selected if r["arm"] == arm})
                for arm in ("c0", "fitted_c")
            }
            ready = bool(selected) and restarted.exists()
            status = (
                "complete" if expected and min(counts.values()) == expected
                else "partial" if ready else "pending"
            )
            title = (
                f"{case}: {method} — {status}; "
                f"c = 0 {counts['c0']}/{expected}, fitted c {counts['fitted_c']}/{expected} starts"
            )
            text = [f"# {title}\n"]
            if original.exists():
                text.extend([
                    "## Original 10 km conditional loss map\n",
                    "Satellite identities and aliases are fixed during the position sweep.\n",
                    f"![Original conditional map]({relative(original, case_dir)})\n",
                ])
            else:
                text.append("Original map unavailable.\n")
            text.append("## New 10 km independent-start map\n")
            if ready:
                text.extend([
                    "Satellite discovery and calibration restart independently at each shown "
                    "starting position; association is refreshed between fitting rounds. "
                    "These are start-to-endpoint samples, not a probability or loss surface.\n",
                    f"![New independent-start map]({relative(restarted, case_dir)})\n",
                ])
                if final_loss.exists():
                    text.append(
                        f"[New plot colored by final loss]({relative(final_loss, case_dir)})\n"
                    )
            else:
                text.append(
                    "**Pending:** no completed restart figure is available "
                    "for this configuration yet.\n"
                )
            (case_dir / f"{method}.md").write_text("\n".join(text))
            table.append(
                f"| [{method}]({method}.md) | {counts['c0']}/{expected} | "
                f"{counts['fitted_c']}/{expected} | {status} |"
            )
            if ready and original.exists():
                key = f"{case}/{method}"
                digest = hashlib.sha256(
                    original.read_bytes() + restarted.read_bytes() + title.encode()
                    + Path(__file__).read_bytes()
                ).hexdigest()
                paired = case_dir / f"{method}.png"
                if cache.get(key) != digest or not paired.exists():
                    paired_figure(original, restarted, paired, title)
                new_cache[key] = digest
                comparisons += 1
            summary.append(dict(case=case, method=method, status=status, counts=counts))
        (case_dir / "README.md").write_text("\n".join(table) + "\n")
        index.append(f"- [{case}: all {len(methods)} configurations]({case}/README.md)")
    (directory / "README.md").write_text(
        "# Original and independent-start 10 km plots\n\n"
        "Both plot types use the same regional center (37.906°, −122.545°), "
        "10 km plotting radius, and 25 × 25 km localization bounds. "
        "Every figure shows c = 0 and fitted c. GPS markers are post-fit evaluation only.\n\n"
        "**Original:** conditional position loss with a selected satellite/alias hypothesis. "
        "**New:** separate discovery, association, calibration, and localization from each "
        "starting position, using cached GLRT measurements and graph tracks. "
        "The new plots are convergence samples; their colors are not probabilities. "
        "Restart counts indicate exactly what has completed; partial and pending entries "
        "will update as the numerical campaign advances.\n\n"
        + "\n".join(index) + "\n"
    )
    cache_path.write_text(json.dumps(new_cache, indent=2) + "\n")
    (directory / "availability.json").write_text(json.dumps(summary, indent=2) + "\n")
    return dict(methods=len(methods), comparisons=comparisons, entries=len(summary))
