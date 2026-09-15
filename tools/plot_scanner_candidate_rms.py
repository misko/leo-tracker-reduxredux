"""Plot retained training-ranked TLE candidates without rescoring or identity claims."""

import argparse
import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot_rows(track):
    """Preserve the frozen training ranking; never manufacture missing ranks."""
    return track["fields"]["0"].get("top_training", [])[:10]


def render(root):
    destination = root / "rms-plots"
    destination.mkdir(exist_ok=True)
    inventory = []
    records = sorted(
        (json.loads(gzip.decompress(p.read_bytes())) for p in root.glob("scan-hop-*.json.gz")),
        key=lambda r: r["capture_start_utc"],
    )
    for record in records:
        sid = record["session_id"]
        tracks = [t for t in record["screen"]["tracks"] if plot_rows(t)]
        links = []
        for offset in range(0, len(tracks), 6):
            group = tracks[offset : offset + 6]
            fig, axes = plt.subplots(3, 2, figsize=(14, 12), squeeze=False)
            for ax in axes.flat:
                ax.set_visible(False)
            for ax, track in zip(axes.flat, group, strict=False):
                ax.set_visible(True)
                candidates = plot_rows(track)
                x = np.arange(1, len(candidates) + 1)
                ax.plot(
                    x,
                    [c["training_rms_hz"] for c in candidates],
                    "o-",
                    color="#2166ac",
                    label="Training RMS",
                    linewidth=1.5,
                )
                ax.plot(
                    x,
                    [c["heldout_rms_hz"] for c in candidates],
                    "s--",
                    color="#d95f02",
                    label="Held-out RMS",
                    linewidth=1.5,
                )
                ax.set_xticks(
                    x, [f"{i}\n{c['catalog_number']}" for i, c in zip(x, candidates, strict=True)]
                )
                ax.set_xlabel("Training rank / NORAD")
                ax.set_ylabel("RMS (Hz; log scale above 1 Hz)")
                ax.set_yscale("symlog", linthresh=1)
                values = [
                    c[key] for c in candidates for key in ("training_rms_hz", "heldout_rms_hz")
                ]
                ax.set_ylim(max(0, min(values) * 0.6), max(1, max(values) * 1.8))
                ax.grid(axis="y", alpha=0.2)
                ax.spines[["top", "right"]].set_visible(False)
                ax.legend(fontsize=8)
                field = track["fields"]["0"]
                ax.set_title(
                    f"CH{track['channel']} {track['edge']} · "
                    f"{track['time_s'][0]:.1f}–{track['time_s'][-1]:.1f} s\n"
                    f"{len(candidates)} retained / {field['candidate_count']} scored; "
                    f"leader held-out rank {field['winner_heldout_rank']}",
                    fontsize=10,
                    loc="left",
                )
            name = f"{sid}-{offset // 6 + 1:02d}.png"
            fig.suptitle(
                f"{sid} · {record['capture_start_utc']}\n"
                "Candidate RMS by training rank · lower is better · no identity claim",
                fontsize=13,
            )
            fig.tight_layout(rect=(0, 0, 1, 0.95), h_pad=2.5)
            fig.savefig(destination / name, dpi=110)
            plt.close(fig)
            links.append(
                f"![Candidate RMS, tracks {offset + 1}–{offset + len(group)}](rms-plots/{name})"
            )
            inventory.append(
                {
                    "file": name,
                    "session_id": sid,
                    "tracklet_ids": [t["tracklet_id"] for t in group],
                    "candidate_counts": [len(plot_rows(t)) for t in group],
                }
            )
        page = root / (sid + "-rms.md")
        page.write_text(
            f"# Ranked candidate RMS: {sid}\n\n"
            f"[Full satellite names, RMS tables and gains]({sid}-candidates.md).\n\n"
            "Each panel is one track, with at most ten training-ranked satellite candidates. "
            "This archive retained five per ranking, so five are shown. Both curves use "
            "the same satellites in training order; held-out RMS is not resorted. "
            "The leader's held-out rank is measured against the full scored population. "
            "Axes are logarithmic above 1 Hz and linear near zero; panel scales vary. "
            "A low RMS alone does not establish satellite identity.\n\n" + "\n\n".join(links) + "\n"
        )
        comparison = root / (sid + "-candidates.md")
        body = comparison.read_text()
        link = f"[Ranked RMS plots for every track]({sid}-rms.md)."
        if link not in body:
            title, rest = body.split("\n", 1)
            comparison.write_text(title + "\n\n" + link + "\n" + rest)
    (destination / "manifest.json").write_text(json.dumps(inventory, indent=2) + "\n")
    (destination / "README.md").write_text(
        "# Ranked satellite RMS plots\n\n"
        "Training and held-out RMS for every eligible track, with at most ten hits per track. "
        "The archived ranking contains five hits, so five are plotted.\n\n"
        "| UTC recording start | Recording plots |\n|---|---|\n"
        + "\n".join(
            f"| {r['capture_start_utc']} | [{r['session_id']}](../{r['session_id']}-rms.md) |"
            for r in records
        )
        + "\n"
    )
    print(
        f"Rendered {len(inventory)} PNGs for "
        f"{sum(len(r['tracklet_ids']) for r in inventory)} tracks"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if root == Path("/mnt/qnap01") or Path("/mnt/qnap01") in root.parents:
        parser.error("QNAP is read-only")
    render(root)
