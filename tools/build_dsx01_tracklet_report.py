"""Build tables and an exhaustive asset index for the DSX01 tracklet report.

This consumes frozen experiment results. It never reruns fitting or modifies
the underlying observations, numerical results, or figures.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_17_dsx01_alias_aware_tracklets"
TUNING = ROOT / "reports/2026_10_17_dsx01_full_data_tuning"
RECOVERY = ROOT / "reports/2026_10_17_dsx01_residual_review"
METHODS = ("em", "graph", "hough", "mht", "baseline")
LABELS = {
    "em": "EM",
    "graph": "Graph",
    "hough": "Hough",
    "mht": "Kalman/MHT",
    "baseline": "RANSAC reference",
}
BUNDLES = tuple(
    ROOT / "reports" / name
    for name in (
        "2026_10_16_dsx01_fast_association_losses",
        "2026_10_17_dsx01_four_methods",
        "2026_10_17_dsx01_random_holdout",
        "2026_10_17_dsx01_full_data_tuning",
        "2026_10_17_dsx01_residual_review",
    )
)


def read(path):
    return json.loads(path.read_text())


def relative(path):
    return Path(__import__("os").path.relpath(path, REPORT)).as_posix()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def markdown_table(rows):
    keys = list(rows[0])

    def clean(value):
        return str(value).replace("|", "/").replace("\n", " ")

    return "\n".join(
        [
            "| " + " | ".join(keys) + " |",
            "| " + " | ".join("---" for _ in keys) + " |",
            *("| " + " | ".join(clean(r[k]) for k in keys) + " |" for r in rows),
        ]
    )


def tables():
    result = {}
    initial = read(BUNDLES[1] / "summary.json")["methods"]
    result["initial-comparison"] = [
        {
            "Method": LABELS[r["method"]],
            "Tracks": r["tracks"],
            "Pieces": r["pieces"],
            "Associated": r["assigned"],
            "Associated %": f"{100 * r['assigned'] / 4797:.2f}",
            "Unassociated": r["unresolved"],
        }
        for r in initial
    ]
    with (RECOVERY / "track-plots/method-summary.csv").open() as stream:
        latest = {r["method"]: r for r in csv.DictReader(stream)}
    result["latest-results"] = [
        {
            "Method": LABELS[m],
            "Associated": latest[m]["associated"],
            "Associated %": f"{float(latest[m]['associated_percent']):.2f}",
            "Tracks": latest[m]["tracks"],
            "Mean points/track": f"{float(latest[m]['mean_points_per_track']):.2f}",
            "Mean duration s": f"{float(latest[m]['mean_track_duration_s']):.2f}",
            "Unassociated": 4797 - int(latest[m]["associated"]),
        }
        for m in METHODS
    ]
    tuned, trials, recovery, quality, synthetic = [], [], [], [], []
    for m in METHODS:
        selected = read(TUNING / m / "selected.json")
        search = read(TUNING / m / "search.json")
        cfg = selected["config"]
        tuned.append(
            {
                "Method": LABELS[m],
                "Trials": len(search),
                "Slope bound Hz/s": cfg["max_slope_hz_s"],
                "Track penalty": cfg["track_penalty"],
                "Knot penalty": cfg["breakpoint_penalty"],
                "Seed": cfg["random_seed"],
                "Tracks": selected["track_count"],
                "Associated": selected["assigned"],
                "Supported no structure": selected["residual_quality"]["no_structure_detected"][
                    "associated_points"
                ],
            }
        )
        for r in search:
            assert "failure" not in r
            trials.append(
                {
                    "Method": LABELS[m],
                    "Trial": r["name"],
                    "Slope bound Hz/s": r["config"]["max_slope_hz_s"],
                    "Track penalty": r["config"]["track_penalty"],
                    "Knot penalty": r["config"]["breakpoint_penalty"],
                    "Maximum degree": r["config"]["max_degree"],
                    "Maximum gap s": r["config"]["max_gap_s"],
                    "Seed": r["config"]["random_seed"],
                    "Tracks": r["track_count"],
                    "Associated": r["assigned"],
                    "Unassociated": r["unresolved"],
                    "Supported no structure": r["residual_quality"]["no_structure_detected"][
                        "associated_points"
                    ],
                }
            )
        strict = read(RECOVERY / m / "strict/results.json")
        sparse = read(RECOVERY / m / "support2/results.json")
        recovery.append(
            {
                "Method": LABELS[m],
                "Before recovery": selected["assigned"],
                "Original support": strict["assigned"],
                "Sparse support": sparse["assigned"],
                "Added strict": strict["assigned"] - selected["assigned"],
                "Added sparse total": sparse["assigned"] - selected["assigned"],
            }
        )
        q = sparse["residual_quality"]
        quality.append(
            {
                "Method": LABELS[m],
                "Supported tracks": q["no_structure_detected"]["tracks"],
                "Supported points": q["no_structure_detected"]["associated_points"],
                "Flagged tracks": q["structure_flagged"]["tracks"],
                "Flagged points": q["structure_flagged"]["associated_points"],
                "Short tracks": q["insufficient_support"]["tracks"],
                "Short points": q["insufficient_support"]["associated_points"],
            }
        )
        validation = read(TUNING / m / "selected-validation.json")
        for r in validation.get("synthetic_cases", validation.get("synthetic", [])):
            synthetic.append(
                {
                    "Method": LABELS[m],
                    "Case": r["case"],
                    "Tracks": r["tracks"],
                    "Assigned": r["assigned"],
                    "Signal coverage": r["signal_coverage"],
                    "Signal purity": r["assigned_signal_purity"],
                    "Clutter assigned": r["clutter_assigned"],
                    "Clutter observations": r["clutter_observations"],
                }
            )
    assert len(trials) == 49 and len(synthetic) == 50
    result.update(
        {
            "tuned-selection": tuned,
            "all-tuning-trials": trials,
            "residual-recovery": recovery,
            "latest-quality": quality,
            "selected-synthetic": synthetic,
        }
    )
    pairwise = read(TUNING / "pairwise/comparison.json")["pairwise"]
    result["pairwise-comparison"] = [
        {
            "Method A": LABELS[r["a"]],
            "Method B": LABELS[r["b"]],
            "Both associated": r["both_assigned"],
            "Only A": r["only_a"],
            "Only B": r["only_b"],
            "Point overlap %": f"{100 * r['assignment_jaccard']:.2f}",
            "Grouping F1 %": f"{100 * r['common_pair_f1']:.2f}",
            "Supported overlap %": f"{100 * r['supported_jaccard']:.2f}",
            "Curve difference RMS Hz": f"{r['prediction_difference_rms_hz']:.2f}",
        }
        for r in pairwise
    ]
    runtime = read(TUNING / "pairwise/runtime.json")["median_wall_s"]
    result["host-runtime"] = [
        {
            "Method": LABELS[m],
            "Median fit time s": f"{runtime[m]:.3f}",
            "Relative to Graph": f"{runtime[m] / runtime['graph']:.2f}",
        }
        for m in sorted(METHODS, key=runtime.get)
    ]
    holdout = read(BUNDLES[2] / "summary.json")["methods"]
    result["historical-holdout"] = [
        {
            "Method": LABELS[r["method"]],
            "Random predicted points": r["random_predicted_points"],
            "Random predicted %": f"{100 * r['random_prediction_fraction']:.2f}",
            "Interval predicted points": r["interval_predicted_points"],
            "Interval predicted %": f"{100 * r['interval_prediction_fraction']:.2f}",
        }
        for r in holdout
    ]
    result["reviewed-fragments"] = [
        {
            "Lane": f"RX{r['receiver']} CH{r['channel']}",
            "Points": r["points"],
            "Span s": f"{r['span_s']:.2f}",
            "Quadratic RMS Hz": f"{r['rms_hz']:.2f}",
            "Maximum residual Hz": f"{r['max_residual_hz']:.2f}",
            "Required by old floor": r["original_required_points"],
        }
        for r in read(RECOVERY / "reviewed-fragments.json")
    ]
    return result


def build():
    (REPORT / "tables").mkdir(parents=True, exist_ok=True)
    document = (REPORT / "REPORT.md").read_text()
    for name, rows in tables().items():
        table = markdown_table(rows)
        with (REPORT / "tables" / f"{name}.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (REPORT / "tables" / f"{name}.md").write_text(table + "\n")
        pattern = re.compile(rf"(<!-- table:{name} -->).*?(<!-- /table:{name} -->)", re.S)
        document = pattern.sub(
            lambda match, table=table: match[1] + "\n\n" + table + "\n\n" + match[2], document
        )
    (REPORT / "REPORT.md").write_text(document)
    assets = [
        p
        for bundle in BUNDLES
        for p in bundle.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    figures = sorted(p for p in assets if p.suffix == ".png")
    csvs = sorted(p for p in assets if p.suffix == ".csv")
    index = [
        "# DSX01 S01 complete figure and table inventory",
        "",
        "All saved study figures are included below with their PDF variants when present. "
        "Table links retain every exported observation and tuning trial. Historical figures "
        "retain their original policies; the report identifies which stage supports each claim.",
        "",
        "## Generated report tables",
        "",
    ]
    for p in sorted((REPORT / "tables").glob("*.csv")):
        index.append(f"- [{p.stem}](tables/{p.name}) · [Markdown](tables/{p.stem}.md)")
    index.extend(["", "## Figures", ""])
    for i, p in enumerate(figures, 1):
        link = relative(p)
        pdf = p.with_suffix(".pdf")
        index.extend(
            [
                f"### Figure {i} {p.parent.name} {p.stem}",
                "",
                f"![{p.parent.name} {p.stem}]({link})",
                "",
                f"Source: [{p.relative_to(ROOT)}]({link}). "
                + (f"[PDF]({relative(pdf)}). " if pdf.exists() else "")
                + "Frozen DSX01 observations; panel labels specify the population and stage. "
                "GLRT views use seconds and kHz; residual and RMS views use Hz; comparison "
                "plots show counts, fractions, or runtimes as labeled. These are fitted curve "
                "and sensitivity diagnostics, without spacecraft identity labels.",
                "",
            ]
        )
    index.extend(["## Exported tables", ""])
    for p in csvs:
        index.append(f"- [{p.relative_to(ROOT)}]({relative(p)})")
    (REPORT / "ASSETS.md").write_text("\n".join(index) + "\n")
    tracked_sources = [
        ROOT / "src/leo/analysis" / name
        for name in (
            "polynomial_tracklets.py",
            "em_tracklets.py",
            "graph_tracklets.py",
            "hough_tracklets.py",
            "mht_tracklets.py",
            "tracklet_fitting.py",
            "residual_tracklets.py",
        )
    ]
    manifest = {
        "scope": "DSX01 S01 study publication; every included evidence file is digest-bound",
        "figure_count_png": len(figures),
        "table_count_csv": len(csvs),
        "files": [
            {"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(assets + tracked_sources)
        ],
    }
    (REPORT / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def check():
    manifest = read(REPORT / "evidence-manifest.json")
    for record in manifest["files"]:
        p = ROOT / record["path"]
        assert p.stat().st_size == record["bytes"] and sha256(p) == record["sha256"], p
    for p in [REPORT / "REPORT.md", REPORT / "ASSETS.md", *(REPORT / "tables").glob("*.md")]:
        for link in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", p.read_text()):
            if not link.startswith(("http:", "https:", "#")):
                assert (p.parent / link.split("#")[0]).exists(), (p, link)
    assert not re.search(r"<!-- table:[^>]+ -->\s*<!-- /table:", (REPORT / "REPORT.md").read_text())
    print(
        f"Verified {len(manifest['files'])} evidence/source files, "
        f"{manifest['figure_count_png']} figures and {manifest['table_count_csv']} exported tables."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        build()
    check()


if __name__ == "__main__":
    main()
