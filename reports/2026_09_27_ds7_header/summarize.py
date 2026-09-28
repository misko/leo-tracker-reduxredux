"""Persist exact candidate regions, input hashes, and a comparison figure."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    base = Path(__file__).parent
    out = base / "local"
    inventory = json.loads((out / "inventory.json").read_text())
    results = json.loads((out / "results.json").read_text())
    controls = json.loads((out / "ut-control.json").read_text())
    rows = []
    for export, result in zip(inventory["exports"], results, strict=True):
        c = export["candidate"]
        for trial in result["all_frame_header_scores"]:
            epoch = (
                c["integer_epoch_sample"]
                + c["fractional_epoch_offset_samples"]
                + trial["frame"] * 1e7 / 750
            )
            rows.append(
                dict(
                    session_id=export["session_id"],
                    visit=export["probe"]["visit_index"],
                    receiver=export["probe"]["receiver_id"],
                    frame=trial["frame"],
                    epoch_sample_in_excerpt=epoch,
                    header_candidate_start_sample=epoch + 88,
                    header_candidate_end_sample=epoch + 440,
                    header_candidate_bins="476-487;496-507",
                    pilot_bins="488-495",
                    pilot_first64_start_sample=epoch + 88,
                    pilot_first64_end_sample=epoch + 2904,
                    pilot_center_baseband_hz=c["fractional_tracking_cfo_hz"],
                    header_status="not_confirmed",
                    header_first8_score=trial["first8_mean"],
                )
            )
    with (out / "regions.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, ax = plt.subplots(figsize=(9, 4))
    for i, result in enumerate(results):
        ax.scatter(
            [i] * len(result["all_frame_header_scores"]),
            [x["first8_mean"] for x in result["all_frame_header_scores"]],
            color="tab:blue",
            alpha=0.6,
        )
    ax.scatter([4] * len(controls), [r["first8_mean"] for r in controls], color="tab:green")
    ax.scatter([5] * len(controls), [r["control_max_first8"] for r in controls], color="tab:orange")
    ax.set_xticks(
        range(6),
        [
            "DS7\n2022/RX0",
            "DS7\n1969/RX0",
            "DS7\n1989/RX0",
            "DS7\n1482/RX1",
            "UT 10 MHz\npositive control",
            "UT wrong\ntemplate max",
        ],
    )
    ax.set_ylabel("Mean BPSK-axis concentration, symbols 2–9")
    ax.set_ylim(0, 1)
    ax.set_title("Header structure: DS7 candidates do not reproduce the UT match")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out / "comparison.png", dpi=160)
    files = sorted(base.glob("*.py")) + sorted(out.glob("*.json")) + sorted(out.glob("*.npy"))
    files += [out / "demodulated.npz", out / "regions.csv", out / "comparison.png"]
    (out / "SHA256SUMS").write_text(
        "".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + str(p.relative_to(base)) + "\n"
            for p in files
        )
    )


if __name__ == "__main__":
    main()
