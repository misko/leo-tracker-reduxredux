"""Report the two exploratory inspections without promoting their identities."""
# ruff: noqa: E501 -- Generated Markdown tables and prose.

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
data = json.loads((HERE / "inspection.json").read_text())
launch = json.loads((HERE / "launch.json").read_text())
assert int((HERE / "exit-code.txt").read_text()) == 0
assert (
    hashlib.sha256((HERE / "inspect_tracks.py").read_bytes()).hexdigest() == launch["source_sha256"]
)
assert len(data["targets"]) == 2 and data["denominator_tracks"] == 1460
assert sum(r["tracks"] for r in data["groups"]) == 1460
for name, value in data["input_sha256"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value, name
group = next(
    r for r in data["groups"] if (r["receiver_id"], r["channel"], r["rf_hz"]) == (0, 1, 10710000000)
)
assert group["tracks"] == 95
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
for i, target in enumerate(data["targets"]):
    assert target["replay_passed"] and target["strictly_increasing_times"]
    t = np.array(target["times_s"])
    t = t - t[0]
    mask = np.array(target["training_mask"], dtype=bool)
    y = np.array(target["observed_contrasts_hz"]) / 1000
    predicted = np.array(target["MAP_predicted_contrasts_hz"]) / 1000
    angles = np.array(target["MAP_angles_deg"])
    winner = target["candidates"][0]
    assert abs(winner["training_max_angle_deg"] - max(angles[mask])) < 1e-10
    assert abs(winner["held_max_angle_deg"] - max(angles[~mask])) < 1e-10
    axes[i, 0].plot(t, predicted, label="Dominant candidate")
    axes[i, 0].scatter(t[mask], y[mask], s=20, label="Training")
    axes[i, 0].scatter(
        t[~mask], y[~mask], facecolors="none", edgecolors="black", s=30, label="Held"
    )
    axes[i, 0].set_ylabel("Frequency relative to first training value (kHz)")
    axes[i, 1].plot(t, angles, label="Dominant candidate boresight angle")
    for width in (40, 50):
        axes[i, 1].axhline(
            width, linestyle="--", color="gray", linewidth=1, label=f"{width}° half-angle"
        )
    axes[i, 1].scatter(t[mask], angles[mask], s=20)
    axes[i, 1].scatter(t[~mask], angles[~mask], facecolors="none", edgecolors="black", s=30)
    axes[i, 1].set_ylabel("Angle from nominal RX0 axis (degrees)")
    axes[i, 1].set_ylim(35, 55)
    for ax in axes[i]:
        ax.set_title(f"{target['panel']}: {winner['name']} hypothesis")
        ax.set_xlabel("Seconds from first track observation")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
fig.suptitle("Two 40° conflicts at unchanged no-cone fits; candidate identities unverified")
fig.tight_layout()
for suffix in ("png", "svg"):
    fig.savefig(HERE / f"target-curves.{suffix}", dpi=160)
plt.close(fig)
lines = [
    "# RX0 tracks excluded by a 40-degree cone",
    "",
    "Both whole-domain 40° exclusions have orderly exported timestamps and strong frequency-model support. "
    "Their dominant retained hypotheses fit the frequency changes after eliminating a free constant offset, "
    "but lie outside the assumed RX0 cone at the existing fit. This identifies a disagreement between "
    "frequency evidence and the assumed visibility boundary; it does not identify which assumption is wrong.",
    "",
    "The two tracks were selected because of the previous geometric exclusion. This is post-hoc inspection, "
    "not an independent performance sample. No location, timing, candidate bank or model was refitted.",
    "",
    "| Quantity | DS9 early eight | DS9 late eight |",
    "|---|---:|---:|",
]
a, b = data["targets"]
for title, key, fmt in (
    ("Observations", "observations", "d"),
    ("Training / held", None, None),
    ("Track span (s)", "span_s", ".3f"),
    ("Training frequency slope (Hz/s)", "training_slope_hz_s", ".1f"),
    ("Model signal responsibility", "signal_responsibility", ".8f"),
    ("Conditional candidate training RMS (Hz)", "conditional_MAP_train_rms_hz", ".2f"),
    ("Conditional candidate held RMS (Hz)", "conditional_MAP_held_rms_hz", ".2f"),
    ("Free training constant offset (Hz)", "conditional_MAP_train_offset_hz", ".1f"),
):
    values = [
        f"{t[key]:{fmt}}" if key else f"{t['training_observations']} / {t['held_observations']}"
        for t in (a, b)
    ]
    lines.append(f"| {title} | {values[0]} | {values[1]} |")
for title, key, fmt in (
    ("Dominant candidate name", "name", None),
    ("NORAD catalogue number", "catalog_number", "d"),
    ("Stored bank index", "bank_index", "d"),
    ("Weight conditional on signal", "training_weight_given_signal", ".8f"),
    ("Maximum training angle (degrees)", "training_max_angle_deg", ".3f"),
    ("Maximum held angle (degrees)", "held_max_angle_deg", ".3f"),
):
    values = [
        f"{t['candidates'][0][key]:{fmt}}" if fmt else t["candidates"][0][key] for t in (a, b)
    ]
    lines.append(f"| {title} | {values[0]} | {values[1]} |")
lines += [
    "",
    "![Frequency and angle inspection](target-curves.png)",
    "",
    "The plotted frequency curves are separately anchored at their first training observation. "
    "The model eliminates a free constant frequency offset, so the visual match is evidence about frequency "
    "change rather than agreement in absolute carrier frequency. RMS figures use the training-selected "
    "dominant candidate and its training-mean residual offset, then apply that same offset to held observations. "
    "They are conditional diagnostics, not new likelihood scores or satellite-identification probabilities.",
    "",
    "## What the bookkeeping establishes",
    "",
    "Both tracks are exported as RX0, channel 1, RF tuning center 10.71 GHz. This exact combination contains "
    "95 of the 1,460 eligible tracks in the nine nonoverlapping DS9 eight-scan panels; two were excluded "
    "throughout the domain at 40°. The small selected sample does not establish a frequency-dependent beam "
    "or a channel fault. Exported receiver labels also do not independently calibrate the physical cable mapping.",
    "",
    "The NPZ candidate IDs are **catalogue row indices**, not NORAD numbers. The pinned, digest-verified "
    "Space-Track baseline snapshots, filtered with the same labelled-debris rule, resolve the dominant "
    "hypotheses to STARLINK-31636 (59747) and STARLINK-34181 (64144). Each reconstructed roster has 11,130 "
    "records, matching its bank manifest. The output retains every candidate's index, catalogue number, "
    "name, weight and angle. These are retained hypotheses, not verified emitters; indices must not be "
    "treated as cross-snapshot satellite identities without resolving their roster.",
    "",
    "Timestamps are strictly increasing within both exported tracks, covering 13.36 and 25.37 seconds. "
    "This does not verify hardware timestamp accuracy, cross-RX alignment or oscillator calibration. "
    "The exports do not establish pilot identity, waveform coherence or calibrated per-observation SNR; "
    "no raw IQ was inspected. The canonical frequency normalization remains unchanged.",
    "",
    "## Modeling consequence",
    "",
    "At 40°, every retained candidate for these two tracks is excluded throughout the declared position/timing "
    "domain. A hard-gated model with an unassociated alternative must therefore assign them to that alternative; "
    "it cannot count them as a complete satellite explanation. At the existing no-cone points, both dominant "
    "hypotheses remain inside 50° over training and held observations. Neither outcome calibrates the true beam.",
    "",
    "Proceed with the previously proposed matched fixed-position hard-40°/50° versus soft-gate scoring check, "
    "retaining the normalized unassociated alternative. It can measure the prediction cost and reassociation "
    "caused by enforcing the boundary before a more expensive discontinuous geographic fit. "
    "Receiver pose error, sidelobe reception, bank incompleteness and incorrect association remain competing "
    "explanations. This inspection produces no new geographic accuracy result.",
    "",
    "## Evidence",
    "",
    "The existing no-cone training and held scores and candidate weights replay within the declared checks. "
    "Candidate angle bounds remain below the actual angles at those unchanged fitted points. "
    "All repository input hashes were checked against published evidence inventories before use and "
    "verified again after inspection. The cached TLE archive was accessed read-only through its reader; "
    "snapshot digests and collection times are retained in the output.",
    "",
    "The single bounded process exited zero in 4.63 s, with peak RSS 385,620 KiB. No optimization, "
    "propagation, provider fetch, raw-waveform access or RF collection was performed. "
    "[Inspection data](inspection.json), [command receipt](launch.json), [resource receipt](resources.txt), "
    "[evidence hashes](evidence-sha256.json), and [preceding domain exclusion](../2026_09_29_cone_feasibility/README.md).",
    "",
]
with (HERE / "README.md").open("x") as f:
    f.write("\n".join(lines))
bindings = dict(data["input_sha256"])
for path in HERE.rglob("*"):
    if path.is_file() and "__pycache__" not in path.parts:
        bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
with (HERE / "evidence-sha256.json").open("x") as f:
    json.dump({"sha256": bindings}, f, indent=2)
print("Reported two target inspections with", len(bindings), "bindings")
