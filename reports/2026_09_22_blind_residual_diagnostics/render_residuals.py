"""Plot frozen dominant-candidate residuals without a reference location."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def render(source, output):
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest.get("truth_accessed") is not False:
        raise ValueError("truth-free residual export required")
    sessions = manifest["sessions"]
    fig, axes = plt.subplots(len(sessions), 2, figsize=(14, 3 * len(sessions)), squeeze=False)
    counts = []
    for index, session in enumerate(sessions):
        if Path(session["file"]).name != session["file"]:
            raise ValueError("unsafe shard name")
        raw = (source / session["file"]).read_bytes()
        if "sha256:" + hashlib.sha256(raw).hexdigest() != session["digest"]:
            raise ValueError("residual shard digest mismatch")
        document = json.loads(raw)
        tracks = [0, 0]
        observations = [0, 0]
        for episode in document["episodes"]:
            candidates = episode["candidate_support"]["candidates"]
            if not candidates:
                continue
            candidate = max(candidates, key=lambda c: c["soft_weight"])
            if candidate["soft_weight"] < .9:
                continue
            rows = candidate["rows"]
            receivers = {r["receiver_id"] for r in rows}
            if len(receivers) != 1 or not receivers <= {0, 1}:
                raise ValueError("expected one explicit RX0/RX1 path per episode")
            receiver = receivers.pop()
            tracks[receiver] += 1
            observations[receiver] += len(rows)
            ax = axes[index, receiver]
            for training, color in [(True, "tab:blue"), (False, "tab:orange")]:
                part = [r for r in rows if r["training"] is training]
                ax.scatter([r["time_s"] for r in part], [r["residual_hz"] for r in part],
                           s=6, alpha=.55, color=color)
        for receiver in (0, 1):
            ax = axes[index, receiver]
            ax.axhline(0, color="black", lw=.6)
            ax.set_title(f"{session['session_id']} · RX{receiver} · {tracks[receiver]} tracks")
            ax.set_xlabel("Time from scan reference (s)")
            ax.set_ylabel("Training-offset residual (Hz at 11.2 GHz)")
            ax.grid(alpha=.2)
        counts.append({"session_id": session["session_id"], "tracks_by_rx": tracks,
                       "observations_by_rx": observations})
    fig.suptitle("Frozen blind-fit residuals · top candidate weight ≥0.9\n"
                 "Blue: training; orange: held out · model weights are not verified identities")
    fig.tight_layout(rect=(0, 0, 1, .96))
    fig.savefig(output / "frozen-residuals.png", dpi=140)
    plt.close(fig)
    (output / "residual-plot-receipt.json").write_text(json.dumps({
        "export_manifest_digest": "sha256:" + hashlib.sha256(
            (source / "manifest.json").read_bytes()).hexdigest(),
        "selection": "top candidate frozen weight >=0.9, no residual-quality selection",
        "counts": counts,
        "truth_used": False,
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.source, args.output)
