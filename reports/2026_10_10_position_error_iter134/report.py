"""Verify explicit successor and report measurement changes, never ground truth."""

import gzip
import hashlib
import json
import tarfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / "2026_10_09_position_error_iter128"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_successor(plan, result, rows, metadata, old_rows):
    ids = [row["window_id"] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(metadata["window_ids"]):
        raise ValueError("original membership differs")
    if result["metadata_sha256"] != plan["member"]["metadata_sha256"]:
        raise ValueError("metadata identity differs")
    lookup = {row["window_id"]: row for row in rows}
    repeated = 0
    for old in old_rows:
        if old["status"] != "complete":
            continue
        new = lookup[old["window_id"]]
        if new["status"] != "complete":
            raise ValueError("previously passing observation now fails")
        old_value = {k: v for k, v in old["result"].items() if k != "elapsed_s"}
        new_value = {k: v for k, v in new["result"].items() if k != "elapsed_s"}
        if old_value != new_value:
            raise ValueError("previously successful numerical outputs changed")
        repeated += 1
    failures = [row for row in rows if row["status"] != "complete"]
    return {
        "rows": len(rows),
        "previous_successes_exactly_reproduced": repeated,
        "failures": failures,
        "complete_parity": not failures,
    }


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    for name, expected in plan["source_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"frozen source/input changed: {name}")
    result = json.loads((HERE / "results/result.json").read_text())
    row_path = HERE / "results/rows.jsonl"
    if result["protocol_sha256"] != sha(HERE / "protocol.json") or result["rows_sha256"] != sha(
        row_path
    ):
        raise ValueError("terminal digest mismatch")
    rows = [json.loads(line) for line in row_path.read_text().splitlines()]
    metadata = json.loads((ROOT / plan["member"]["metadata_path"]).read_text())
    old_rows = [
        json.loads(line) for line in (OLD / "results/DS18-029/rows.jsonl").read_text().splitlines()
    ]
    integrity = verify_successor(plan, result, rows, metadata, old_rows)
    values = {
        name: np.array(
            [r["result"]["changes"][name]["circular_hz"] for r in rows if r["status"] == "complete"]
        )
        for name in ("logparabola", "newton")
    }
    stats = {
        name: {
            "rms_change_hz": float(np.sqrt(np.mean(a * a))),
            "median_abs_change_hz": float(np.median(abs(a))),
            "p95_abs_change_hz": float(np.percentile(abs(a), 95)),
        }
        for name, a in values.items()
        if len(a)
    }
    old_result = json.loads((OLD / "results/DS18-029/result.json").read_text())
    integrity.update(
        protocol_sha256=sha(HERE / "protocol.json"),
        result_sha256=sha(HERE / "results/result.json"),
        rows_sha256=sha(row_path),
        source_files_verified=len(plan["source_sha256"]),
        elapsed_s=result["elapsed_s"],
        original_failed_attempt_elapsed_s=old_result["elapsed_s"],
        circular_changes=stats,
    )
    (HERE / "verification.json").write_text(json.dumps(integrity, indent=2) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4))
    for name, a in values.items():
        ax.hist(a, bins=np.linspace(-225, 225, 61), histtype="step", label=name)
    ax.set(
        xlabel="Circular CFO change from original (Hz)",
        ylabel="Observations",
        title="DS18-029: corrected visit mapping, unchanged refiners",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "changes.png", dpi=160)

    files = [HERE / "results" / name for name in ("started.json", "rows.jsonl", "result.json")]
    archive_path = HERE / "results.tar.gz"
    with (
        archive_path.open("xb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as archive,
    ):
        for path in files:
            info = tarfile.TarInfo(str(path.relative_to(HERE)))
            info.size, info.mode = path.stat().st_size, 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    manifest = {
        str(path.relative_to(HERE)): {"sha256": sha(path), "bytes": path.stat().st_size}
        for path in files
    }
    found = set()
    with tarfile.open(archive_path, "r|gz") as archive:
        for info in archive:
            if info.name not in manifest or info.name in found or not info.isfile():
                raise ValueError("unexpected archive member")
            found.add(info.name)
            if (
                hashlib.sha256(archive.extractfile(info).read()).hexdigest()
                != manifest[info.name]["sha256"]
            ):
                raise ValueError("archive content differs")
    if found != set(manifest):
        raise ValueError("archive membership differs")
    (HERE / "RESULT_ARCHIVE.json").write_text(
        json.dumps(
            {
                "archive": archive_path.name,
                "sha256": sha(archive_path),
                "bytes": archive_path.stat().st_size,
                "files": manifest,
                "verification": "all extracted digests checked; originals retained",
            },
            indent=2,
        )
        + "\n"
    )
    lines = [
        "# Explicit sparse-visit replay result",
        "",
        f"All {len(rows)} original DS18-029 observations were retained; "
        f"{len(rows) - len(integrity['failures'])} passed parity and "
        f"{len(integrity['failures'])} failed. The "
        f"{integrity['previous_successes_exactly_reproduced']} previously successful observations "
        "reproduced every numerical output exactly (excluding elapsed time).",
        "",
        "The only change is event-ID→reader-ordinal translation. "
        "Original128 failures remain published. "
        f"This successor took {result['elapsed_s']:.3f}s; the failed128 attempt cost "
        f"{old_result['elapsed_s']:.3f}s, retained separately. "
        f"All {len(plan['source_sha256'])} frozen source/input hashes verify.",
        "",
        "![Measurement changes](changes.png)",
        "",
        "| Refiner | RMS change Hz | Median absolute Hz | p95 absolute Hz |",
        "|---|---:|---:|---:|",
    ]
    for name, s in stats.items():
        lines.append(
            f"| {name} | {s['rms_change_hz']:.3f} | {s['median_abs_change_hz']:.3f} "
            f"| {s['p95_abs_change_hz']:.3f} |"
        )
    lines += [
        "",
        "These are circular measurement changes, not frequency errors or demonstrated "
        "localization gains. No observation admission, acquisition, model prior or position "
        "fit changed. A later matched positioning experiment must explicitly bind128's "
        "other eleven members plus this successor, retaining the original failure/cost lineage.",
        "",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
