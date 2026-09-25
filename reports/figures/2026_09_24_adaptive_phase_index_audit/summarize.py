"""Create audit tables and a compact perturbation figure from frozen replay output."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


OUT = Path(__file__).parent


def main() -> None:
    replay = json.loads((OUT / "raw-perturbation-results.json").read_text())
    frozen = []
    for path in sorted((OUT / "frozen-source").glob("visit-*.json")):
        row = json.loads(path.read_text())["document"]
        evidence = row.get("evidence", {})
        frozen.append(
            {
                "visit_index": row["visit_index"],
                "state": row["state"],
                "band_R": evidence.get("band_phase_resultant"),
                "tracked_coherence": evidence.get("tracked_coherence"),
                "wrong_time_coherence": evidence.get("wrong_time_coherence"),
                "pilot_held_rms_deg": evidence.get("pilot_held_rms_deg"),
            }
        )
    with (OUT / "frozen-visit-R.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(frozen[0]))
        writer.writeheader()
        writer.writerows(frozen)

    columns = ["visit_index", "channel", "edge", "kind", "case", "R", "failure"]
    compact = []
    for visit in replay["visits"]:
        for kind in ("broadband", "pilot"):
            for row in visit[kind]:
                compact.append(
                    {
                        "visit_index": visit["visit_index"],
                        "channel": visit["channel"],
                        "edge": visit["edge"],
                        "kind": kind,
                        "case": row["case"],
                        "R": row.get("band_R", row.get("pilot_R")),
                        "failure": row.get("failure"),
                    }
                )
    with (OUT / "raw-perturbation-R.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(compact)

    high = {569, 590}
    low = {324, 1677}
    summary: dict[str, object] = {
        "session_id": replay["session_id"],
        "sample_rate_hz": replay["sample_rate_hz"],
        "fft_bin_hz": replay["fft_bin_hz"],
        "frozen_visit_count": len(frozen),
        "frozen_supported_count": sum(row["state"] == "supported" for row in frozen),
        "frozen_band_R_gte_0_8_count": sum(
            (row["band_R"] or 0) >= 0.8 for row in frozen
        ),
        "representative_high_R_visits": sorted(high),
        "representative_low_R_visits": sorted(low),
        "raw_replay_visit_indices": [row["visit_index"] for row in replay["visits"]],
    }
    for kind in ("broadband", "pilot"):
        by_visit = {row["visit_index"]: {item["case"]: item.get("band_R", item.get("pilot_R")) for item in row[kind]} for row in replay["visits"]}
        summary[f"{kind}_low_R_best_tested_perturbation"] = {
            str(visit): max((value for value in rows.values() if value is not None), default=None)
            for visit, rows in by_visit.items()
            if visit in low
        }
    (OUT / "audit-summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    broad_cases = [
        "nominal",
        "cfo_minus_1_fft_bin",
        "cfo_plus_1_fft_bin",
        "response_bin_minus_1",
        "response_bin_plus_1",
        "rx_swap_consistent",
        "cfo_sign_reversed",
    ]
    pilot_cases = [
        "nominal",
        "frame_minus_1_sample",
        "frame_plus_1_sample",
        "symbol_plus_1",
        "symbol_plus_2",
        "authority_minus_1_fft_bin",
        "authority_plus_1_fft_bin",
        "rx_swap_consistent",
        "wrong_edge",
    ]
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=False, constrained_layout=True)
    for axis, kind, cases, title in zip(
        axes,
        ("broadband", "pilot"),
        (broad_cases, pilot_cases),
        ("Held-out broadband band-phase resultant", "Local pilot frame resultant (first paired probe)"),
        strict=True,
    ):
        points = {row["visit_index"]: {item["case"]: item.get("band_R", item.get("pilot_R")) for item in row[kind]} for row in replay["visits"]}
        x = np.arange(len(cases))
        for visit, values in points.items():
            y = np.asarray([values.get(case, np.nan) for case in cases], dtype=float)
            axis.plot(x, y, marker="o", label=f"visit {visit}" + (" high R" if visit in high else " low R"))
        axis.axhline(0.8, color="black", ls="--", lw=1, label="0.8 screen")
        axis.set_xticks(x, [case.replace("_", "\n") for case in cases], fontsize=8)
        axis.set_ylim(0, 1.05)
        axis.set_ylabel("resultant R")
        axis.set_title(title)
        axis.grid(alpha=0.25)
        axis.legend(ncol=3, fontsize=8, loc="lower left")
    fig.savefig(OUT / "raw-perturbation-resultants.png", dpi=180)


if __name__ == "__main__":
    main()
