"""Add existing fractional GLRT products and matched downsampled refinement."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from compare_paired_pss_bandwidth import product, windows, write
from summarize_paired_glrt_tle import compare, polynomial_diagnostics

from leo.analysis.research.tle_shape_comparison import unwrap_cfo
from leo.contracts.standard_native_glrt_fractional import StandardNativeGlrtFractionalEpochV1


def phase_ns(epoch_s):
    return np.unwrap((epoch_s % (1 / 750)) * 750 * 2 * np.pi) / (750 * 2 * np.pi) * 1e9


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output
    if out.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    cs = json.loads((out / "selection.json").read_text())["selected"]
    original = json.loads((out / "comparison.json").read_text())
    records = []
    sources = []
    for c in cs:
        audit = json.loads((out / c["capture_id"] / "tle-candidates.json").read_text())
        predictions = np.load(out / c["capture_id"] / "tle-predictions.npz")
        for lane, source in (
            ("native25", "native"),
            ("derived2p5", None),
            ("recorded2p5", "recorded"),
        ):
            old = next(
                r
                for r in original
                if r["capture_id"] == c["capture_id"]
                and r["method"] == "GLRT"
                and r["lane"] == lane
            )
            if source is not None:
                root = Path("/srv/bulk/leo")
                glrt = product(root, c[source])
                path = (root / c[source]["logical_uri"].removeprefix("bulk://")).parent
                fp = path / "standard.glrt-fractional-epoch.v1.json"
                raw = fp.read_bytes()
                frac = StandardNativeGlrtFractionalEpochV1.model_validate_json(raw).model_dump(
                    mode="json"
                )
                if frac["source_glrt_product_digest"] != c[source]["digest"]:
                    raise ValueError("fractional companion does not bind selected GLRT product")
                if frac["source_glrt_result_digest"] != glrt["result_digest"]:
                    raise ValueError("fractional companion result digest mismatch")
                sources.append(
                    dict(
                        path=str(fp),
                        sha256=hashlib.sha256(raw).hexdigest(),
                        method=frac["interpolation_method"],
                    )
                )
                v2p = path / "standard.glrt-fractional-epoch.v2.json"
                v2raw = v2p.read_bytes()
                v2 = json.loads(v2raw)
                sources.append(
                    dict(
                        path=str(v2p),
                        sha256=hashlib.sha256(v2raw).hexdigest(),
                        method=v2["interpolation_method"],
                        selection_policy=v2["selection_policy"],
                        used_in_timing_table=False,
                    )
                )
                start, rate = c[source + "_start_s"], c[source]["binding"]["sample_rate_hz"]
                ws = [
                    w
                    for w in windows(glrt)
                    if w["global_start_time_s"] >= start - 1e-9
                    and w["global_end_time_s"] <= start + 2.25 + 1e-9
                ]
                ids = {w["opportunity_index"] for w in ws}
                selected = [r for r in frac["refinements"] if r["opportunity_index"] in ids]
                good = [r for r in selected if r["status"] == "complete"]
                epochs = np.array([r["fractional_global_epoch_device_sample"] / rate for r in good])
                integers = np.array([r["integer_global_epoch_device_sample"] / rate for r in good])
                carrier = dict(
                    time_s=old["time_s"], value=old["value"], diagnostics=old["diagnostics"]
                )
            else:
                docs = [
                    json.loads(p.read_text())
                    for p in sorted(
                        (out / "fractional-glrt" / c["capture_id"]).glob("derived-glrt-*.json")
                    )
                ]
                if len(docs) != 9:
                    raise ValueError("fractional downsampled replay is incomplete")
                pairs = [(d["output_device_sample_start"], w) for d in docs for w in d["windows"]]
                selected = [w for _, w in pairs if w["passed_margin_gate"]]
                good = [(s, w) for s, w in pairs if w["fractional_epoch_status"] == "complete"]
                rate, start = 2_500_000, c["native_start_s"]
                integers = np.array(
                    [(s + w["sample_start"] + w["epoch_sample"]) / rate for s, w in good]
                )
                epochs = integers + np.array(
                    [w["fractional_epoch_offset_samples"] / rate for _, w in good]
                )
                cfo_pairs = [
                    (s, w)
                    for s, w in pairs
                    if w["passed_margin_gate"] and w["robust_line_available"]
                ]
                ct = np.array(
                    [s / rate + w["robust_reference_time_s"] - start for s, w in cfo_pairs]
                )
                cy = unwrap_cfo(np.array([w["robust_cfo_at_reference_hz"] for _, w in cfo_pairs]))
                carrier = dict(
                    time_s=ct.tolist(),
                    value=cy.tolist(),
                    diagnostics=polynomial_diagnostics(ct, cy),
                )
            t, y = epochs - start, phase_ns(epochs)
            rec = dict(
                capture_id=c["capture_id"],
                lane=lane,
                method="GLRT-fractional",
                units="ns",
                window_count=len(selected),
                complete_count=len(good),
                unsupported_count=len(selected) - len(good),
                time_s=t.tolist(),
                value=y.tolist(),
                diagnostics=polynomial_diagnostics(t, y),
                integer_same_subset_diagnostics=polynomial_diagnostics(
                    integers - start, phase_ns(integers)
                ),
            )
            rec["primary"] = compare(
                rec,
                predictions["time_s"],
                predictions["delay_ns"],
                audit["candidates"],
                degree=1,
                mask=10,
            )
            rec["clock_drift_sensitivity"] = compare(
                rec,
                predictions["time_s"],
                predictions["delay_ns"],
                audit["candidates"],
                degree=2,
                mask=10,
            )
            rec["carrier"] = carrier
            carrier["primary"] = compare(
                carrier,
                predictions["time_s"],
                predictions["cfo_hz"],
                audit["candidates"],
                degree=0,
                mask=10,
            )
            print(
                c["capture_id"][-6:],
                lane,
                "complete",
                len(good),
                "RMS ns",
                rec["diagnostics"]["alternate_rms"],
                "curvature",
                rec["diagnostics"]["second_derivative"],
                "carrier RMS Hz",
                carrier["diagnostics"]["alternate_rms"],
                flush=True,
            )
            records.append(rec)
    write(out / "fractional-glrt-comparison.json", records)
    write(out / "fractional-glrt-inputs.json", sources)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    for j, (lane, color) in enumerate(
        zip(
            ("native25", "derived2p5", "recorded2p5"),
            ("#157f91", "#c76524", "#7d58a0"),
            strict=True,
        )
    ):
        subset = [r for r in records if r["lane"] == lane]
        x = np.arange(5) + (j - 1) * 0.24
        axes[0].bar(
            x,
            [r["diagnostics"]["alternate_rms"] for r in subset],
            width=0.22,
            color=color,
            label=lane,
        )
        axes[1].scatter(
            np.arange(5),
            [r["diagnostics"]["second_derivative"] for r in subset],
            color=color,
            label=lane,
        )
    for ax in axes:
        ax.set_xticks(range(5), [c["capture_id"][-6:] for c in cs])
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Fractional GLRT timing residual RMS (ns)")
    axes[0].set_title("Completed refinements · alternate-observation quadratic check")
    axes[0].legend(fontsize=8)
    axes[1].set_ylabel("Measured timing curvature (ns/s²)")
    axes[1].axhline(0, color="gray", lw=1)
    axes[1].set_title("Fractional refinement preserves negative timing curvature")
    fig.suptitle("Existing fractional GLRT, applied to all three paths in the same five dwells")
    fig.savefig(out / "fractional-glrt-timing-comparison.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
