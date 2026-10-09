"""Persisted-stage descriptions; no fitting or reference-guided operational choice."""

import hashlib
import json
import math
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior

HERE = Path(__file__).resolve().parent
STAGES = ("B3", "B4", "B4W", "B5", "C6", "B7")
ARMS = ("fitted-c", "zero-c")


def main():
    source = HERE / "published-v3.json"
    document = json.loads(source.read_text())["manifest"]["document"]
    assert document["session_id"] == "scan-fw-ac11ac00c0676d1b"
    prior = RegionalPrior(
        latitude_deg=document["prior_latitude_deg"],
        longitude_deg=document["prior_longitude_deg"],
        radius_km=document["prior_radius_km"],
    )
    reference = document["reference_latitude_deg"], document["reference_longitude_deg"]

    def error_km(position):
        latitude, longitude = coordinates(prior, position)
        lat, lon, ref_lat, ref_lon = map(math.radians, (latitude, longitude, *reference))
        haversine = (
            math.sin((lat - ref_lat) / 2) ** 2
            + math.cos(lat) * math.cos(ref_lat) * math.sin((lon - ref_lon) / 2) ** 2
        )
        return 2 * 6371.0088 * math.asin(math.sqrt(min(1, max(0, haversine))))

    rows = []
    for stage in STAGES:
        for arm in ARMS:
            fit = document["diagnostics"]["b7"]["attempts"][stage][arm]
            vector = np.asarray(fit["vector"])
            state = fit["joint_state"]
            count = len(vector) - 7
            rows.append(
                dict(
                    stage=stage,
                    arm=arm,
                    error_km=error_km(vector[:2]),
                    satellite_count=count,
                    signal_windows=fit["signal_windows"],
                    posterior_rms_hz=fit["posterior_rms_hz"],
                    objective=fit["objective"],
                    stationarity=fit["stationarity"],
                    converged=fit["converged"],
                    elapsed_s=fit["elapsed_s"],
                    evaluations=fit["evaluations"],
                    timing_penalty=state["timing_penalty"],
                    nuisance_penalty=state["nuisance_penalty"],
                    likelihood_nll=state["likelihood_nll"],
                    common_timing_s=vector[7],
                    relative_timing_rms_s=float(np.linalg.norm(vector[8:]) / np.sqrt(count)),
                )
            )
    for arm in ARMS:
        selected = next(a["selected"] for a in document["methods"][0]["arms"] if a["name"] == arm)
        endpoint = next(r for r in rows if r["stage"] == "B7" and r["arm"] == arm)
        np.testing.assert_allclose(
            endpoint["error_km"], selected["horizontal_error_m"] / 1000, atol=1e-9, rtol=0
        )
    summary = dict(
        session_id=document["session_id"],
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        scope="Persisted fits only; reference coordinates used solely for post-fit evaluation",
        stages=rows,
        removed_satellites=document["diagnostics"]["b7"]["attempts"]["removed_satellites"],
    )
    (HERE / "stage-audit.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        for ax, key, label in zip(
            axes,
            ["error_km", "signal_windows", "timing_penalty"],
            [
                "Post-fit position error (km)",
                "Posterior signal-window mass",
                "Timing prior penalty",
            ],
            strict=True,
        ):
            ax.plot(STAGES, [r[key] for r in arm_rows], marker="o", label=arm)
            ax.axvline(0.5, color="gray", linestyle="--", linewidth=0.7)
            ax.set(ylabel=label)
    axes[0].legend()
    fig.suptitle("ac11 persisted stages: dashed line marks 41 → 16 satellite bank pruning")
    fig.savefig(HERE / "stage-audit.png", dpi=170)
    plt.close(fig)
    lines = [
        "# ac11 stage audit: converged fits in an upstream wrong region",
        "",
        "Persisted V3 `scan-fw-ac11ac00c0676d1b` completes both B7 arms. Fitted-c "
        "error is 55.685 km and c0 is 53.945 km. Both satisfy the independent 0.001 gate; "
        "this is a localization failure, not a final optimizer/convergence failure.",
        "",
        "Reference coordinates are used only to evaluate already persisted stage positions. "
        "No new fit, seed, bank or operational winner is chosen by this audit.",
        "",
        "![Persisted position, support and timing penalties](stage-audit.png)",
        "",
        "| Stage | Arm | Error km | Satellites | Signal mass | RMS Hz | "
        "Timing prior | Stationarity |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['stage']} | {r['arm']} | {r['error_km']:.3f} | {r['satellite_count']} | "
            f"{r['signal_windows']:.2f} | {r['posterior_rms_hz']:.2f} | "
            f"{r['timing_penalty']:.3f} | {r['stationarity']:.6g} |"
        )
    lines += [
        "",
        "## What precedes the joint stages",
        "",
        "All three ordinary region passes record a calibration prefit failure for "
        "`point:-47.5:-62.5`. Both final arms originate from the sep50 region's "
        "`point:-72.5:-137.5`. The joint ladder therefore begins inside that selected "
        "regional hypothesis; it does not revisit discarded/failed regions. The separate "
        "regional prefit replay isolates this earlier exclusion. Stage diagnostics alone "
        "do not prove that a discarded region would have produced a better final position.",
        "",
        "## B3 to B4: large support loss, not a comparable-score decision",
        "",
        "Production `reduce_bank` deletes satellites whose fitted relative timing magnitude "
        "exceeds 5 s, then projects the retained total timing shifts into a smaller zero-sum "
        "basis. Here it removes 25/41 satellites (61.0%). Fitted posterior signal mass drops "
        "2672.94→1019.85 (61.8%) and c0 drops 2530.06→944.79 (62.7%). Timing penalties fall "
        "351.362→11.087 and342.130→9.962, partly because the high-timing candidates are "
        "removed. This is not evidence that those candidates' timing errors were corrected.",
        "",
        "The bank change alters mixture candidates and clutter/visibility terms, so "
        "B3/B4 objectives and posterior RMS are not controlled same-model comparisons. "
        "The objective increase 39830→45121 does not mean an optimizer converged to a "
        "worse point under one unchanged function. B4 is accepted because it independently "
        "qualifies within its own changed model, as prescribed by B7.",
        "",
        "The actual fitted-c position error improves 59.468→55.163 km at pruning, and c0 "
        "improves 57.806→52.608 km. Therefore this receipt **does not establish pruning as a "
        "position-error amplifier**. It establishes substantial evidence/support loss in "
        "an already wrong region, potentially reducing recovery information. Proving a "
        "causal accuracy effect requires an unpruned/pruned same-start controlled replay.",
        "",
        "## Later stages cannot undo the regional exclusion",
        "",
        "B4W relaxes the existing clock prior, B5 adds RF-time flexibility, and B7 adds "
        "satellite slope flexibility; all remain independently stationary near the same "
        "bad regional solution. Fitted-c B5→B7 changes position error 55.756→55.685 km "
        "(about 71 m), and c0 C6→B7 changes 55.103→53.945 km (about 1.16 km). These are "
        "small changes relative to the 54–56 km failure; further frequency flexibility "
        "does not recover a missing regional hypothesis in this persisted run.",
        "",
        "The B3 relative timing RMS is approximately 8.28 s fitted and 8.17 s c0. Thus the "
        "existing inference-only timing-strain concept would flag this case without "
        "reference error. A uniform bounded retry of a failed retained regional prefit "
        "is the more direct cause-oriented test; final-function extra time is not "
        "motivated by these strongly qualified B7 endpoints.",
        "",
        "[Per-stage values, provenance and removed IDs](stage-audit.json). "
        "No deployment change or new RF collection occurred.",
    ]
    (HERE / "STAGE_AUDIT.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
