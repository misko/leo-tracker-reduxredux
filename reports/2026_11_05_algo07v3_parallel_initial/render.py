"""Verify and summarize the external independent-arm concurrency experiment."""

import argparse
import hashlib
import inspect
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(root):
    import probe_algo07v3_parallel_initial as probe

    from leo.analysis.localization_v3 import initial_search

    destination = Path(__file__).resolve().parent
    checkout = destination.parents[1]
    source = root / "comparison.json"
    data = json.loads(source.read_bytes())
    assert data["complete"] and data["exact"]
    assert data["tool_sha256"] == sha(checkout / "tools/probe_algo07v3_parallel_initial.py")
    assert (
        data["source_sha256"]
        == hashlib.sha256(inspect.getsource(initial_search.initial_search).encode()).hexdigest()
    )
    _, _, _, candidate = probe.transformed_function(initial_search, probe.parallel_pair)
    assert data["candidate_source_sha256"] == hashlib.sha256(candidate.encode()).hexdigest()
    rows = data["rows"]
    assert [r["side"] for r in rows] == ["serial", "parallel", "parallel", "serial"]
    assert all(r["exact"] and r["snapshot"] == rows[0]["snapshot"] for r in rows)
    for row in rows:
        if row["side"] == "parallel":
            assert len(row["pairs"]) == 3
            for pair in row["pairs"]:
                assert [r["arm"] for r in pair["workers"]] == ["c0", "fitted_c"]
                assert [r["cpu"] for r in pair["workers"]] == [[0], [1]]
                assert len({r["pid"] for r in pair["workers"]}) == 2
    full_path = root / "full/comparison.json"
    full = json.loads(full_path.read_bytes())
    assert full["complete"] and full["exact"] and full["scientific_snapshot_exact"]
    assert all(full["figure_checks"].values()) and len(full["figure_checks"]) == 8
    assert full["source_sha256"] == data["source_sha256"]
    assert full["candidate_source_sha256"] == data["candidate_source_sha256"]
    assert full["experiment_sha256"] == data["tool_sha256"]
    assert full["tool_sha256"] == sha(checkout / "tools/probe_algo07v3_parallel_engine.py")
    assert full["actual_sha256"] == sha(root / "full/native/result.json")
    result = json.loads((root / "full/native/result.json").read_bytes())
    assert result["presentation"]["grid_complete"]
    assert result["presentation"]["grid_points"] == 179
    for name, expected in result["presentation"]["products"].items():
        assert sha(root / "full/native" / (name + ".png")) == expected
    means = {
        side: sum(r["seconds"] for r in rows if r["side"] == side) / 2
        for side in ("serial", "parallel")
    }
    summary = dict(
        exact=True,
        initial_stage_mean_seconds=means,
        observed_stage_ratio=means["serial"] / means["parallel"],
        observed_stage_reduction_percent=100 * (1 - means["parallel"] / means["serial"]),
        rows=[{k: v for k, v in row.items() if k != "snapshot"} for row in rows],
        stage_snapshot_sha256=hashlib.sha256(
            json.dumps(rows[0]["snapshot"], sort_keys=True).encode()
        ).hexdigest(),
        original_evidence_sha256=sha(source),
        source_bindings={k: v for k, v in data.items() if k.endswith("sha256")},
        native_to_png_exact=True,
        full_comparison_sha256=sha(full_path),
        pipeline_speedup=None,
        runtime_enabled=False,
        production_modified=False,
        isolated_process_evidence=False,
        scope="One scan, initial-stage ABBA plus full native-to-PNG numerical replay",
    )
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (destination / "full-comparison.json").write_bytes(full_path.read_bytes())
    (destination / "full-timing.json").write_bytes(
        (root / "full/native/result.receipt.json").read_bytes()
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 4.5))
    fig.subplots_adjust(bottom=0.25, top=0.83)
    bars = ax.bar(
        range(4), [r["seconds"] for r in rows], color=["#888888", "#3465a4", "#3465a4", "#888888"]
    )
    ax.bar_label(bars, fmt="%.2f s", padding=4)
    ax.set(
        xticks=range(4),
        xticklabels=["Serial A1", "Parallel B1", "Parallel B2", "Serial A2"],
        ylabel="Initial-search wall time (seconds)",
        ylim=(0, 47),
    )
    ax.set_title(
        "DS26-0002 · concurrent independent calibration arms\n"
        "Complete stage outputs and branch callbacks match exactly"
    )
    fig.text(
        0.5,
        0.04,
        f"Stage means: {means['serial']:.2f} → {means['parallel']:.2f} s · "
        f"{summary['observed_stage_reduction_percent']:.1f}% less wall time\n"
        "Two performance cores versus one; shared host. Not a complete-pipeline speedup.",
        ha="center",
        fontsize=10,
    )
    fig.savefig(destination / "initial-stage.png", dpi=150)
    plt.close(fig)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in ("rows", "source_bindings")}, indent=2
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    render(parser.parse_args().root)
