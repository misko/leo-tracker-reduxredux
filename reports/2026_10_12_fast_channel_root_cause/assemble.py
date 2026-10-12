"""Export compact auditable results and scientific figures; exclude raw IQ and banks."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.regional_position_score import circular, coordinates
from leo.contracts.regional_position import RegionalPrior


def error(point, reference):
    lat, lon, a, b = np.radians([*point, *reference])
    h = np.sin((lat - a) / 2) ** 2 + np.cos(lat) * np.cos(a) * np.sin((lon - b) / 2) ** 2
    return float(2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(h, 0, 1))))


def summary(doc):
    finals = []
    for arm in doc["methods"][0]["arms"]:
        if arm["selected"]:
            finals.append(
                dict(
                    arm=arm["name"],
                    **{k: v for k, v in arm["selected"].items() if k != "joint_state"},
                )
            )
    reference = (doc["reference_latitude_deg"], doc["reference_longitude_deg"])
    controls = []
    for stage in ("B3", "B4", "B4W"):
        for arm, fit in doc["diagnostics"]["b7"]["attempts"].get(stage, {}).items():
            lat, lon = coordinates(RegionalPrior(), fit["vector"][:2])
            controls.append(
                dict(
                    stage=stage,
                    arm=arm,
                    latitude_deg=lat,
                    longitude_deg=lon,
                    error_m=error((lat, lon), reference),
                    rms_hz=fit["posterior_rms_hz"],
                    objective=fit["objective"],
                    coefficient_hz_per_ghz=fit["vector"][6],
                    converged=fit["converged"],
                )
            )
    return dict(
        windows=doc["windows"],
        finals=finals,
        static_c_controls=controls,
        snapshot_sha256=doc["diagnostics"]["snapshot_sha256"],
        configuration_sha256=doc["configuration_sha256"],
        candidate_bank_count=len(doc["diagnostics"]["bank"]["retained_numbers"]),
        source_basin=doc["methods"][0]["arms"][0]["selected"]["source_basin"],
        regional_points=len(doc["methods"][0]["points"]),
        known_position_used_for_inference=doc["known_position_used_for_inference"],
        position_fix_claimed=doc["position_fix_claimed"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    docs = {
        case: json.loads((args.parent / case / "regional.json").read_text())
        for case in ("ch1-4", "ch5-8", "ch1-8")
    }
    docs["compensated-ch1-8"] = json.loads((args.work / "compensated/regional.json").read_text())
    for doc in docs.values():
        assert doc["configuration_sha256"] == docs["ch1-8"]["configuration_sha256"]
        assert (
            doc["diagnostics"]["snapshot_sha256"] == docs["ch1-8"]["diagnostics"]["snapshot_sha256"]
        )
        assert (
            doc["diagnostics"]["bank"]["retained_numbers"]
            == docs["ch1-8"]["diagnostics"]["bank"]["retained_numbers"]
        )
        assert not doc["known_position_used_for_inference"] and not doc["position_fix_claimed"]
    published = json.loads((args.parent / "input/published-regional.json").read_text())
    assert docs["ch1-8"]["methods"] == published["methods"]
    cases = {name: summary(doc) for name, doc in docs.items()}
    controls = json.loads((args.work / "offset-controls.json").read_text())
    diagnostic = json.loads((args.work / "diagnostics.json").read_text())
    compensated = json.loads((args.work / "compensated/receipt.json").read_text())
    assert compensated["result"]["state"] == "complete"
    assert cases["compensated-ch1-8"]["windows"] == cases["ch1-8"]["windows"]
    final = cases["compensated-ch1-8"]["finals"][0]
    for name in ("ch1-4", "ch5-8", "ch1-8"):
        old = cases[name]["finals"][0]
        sa, sb = set(old["satellites"]), set(final["satellites"])
        cases[name]["satellite_overlap_with_compensated"] = dict(
            shared=sorted(sa & sb), only_original=sorted(sa - sb), only_compensated=sorted(sb - sa)
        )
    result = dict(
        session_id=docs["ch1-8"]["session_id"],
        cases=cases,
        full_reproduction_exact=True,
        offset_diagnostics=diagnostic,
        offset_controls=controls,
        compensation_receipt=compensated,
        scope=(
            "Single recorded scan, conditional RF hypotheses; exploratory causal "
            "counterfactual, not an independently validated position or satellite identity."
        ),
    )
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.output / "offset-controls.json").write_text(json.dumps(controls, indent=2) + "\n")
    source_root = Path(__file__).resolve().parents[2] / "src/leo"
    provenance = {
        "source_base_commit": "32736a415",
        "inputs": {},
        "sources": {},
        "checks": [
            "Exact original full-channel method reproduction.",
            "Identical 3433 physical windows before/after compensation.",
            "Identical 836-satellite candidate banks, TLE and numerical configurations.",
            "No reference used for inference; no position fix claimed.",
            "B4W reconstruction matches published RMS within 1e-6 Hz.",
            "Random whole-block split and training-only nuisance fits.",
        ],
    }
    for path in [
        args.parent / "input/tracking.json",
        args.work / "diagnostic-arrays.npz",
        args.work / "compensated/regional.json",
    ]:
        provenance["inputs"][str(path)] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
    for relative in docs["ch1-8"]["configuration"]["source_digests"]:
        path = source_root / relative
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == docs["ch1-8"]["configuration"]["source_digests"][relative]
        provenance["sources"][relative] = digest
    recipe_root = Path(__file__).resolve().parent
    provenance["recipes"] = {
        name: "sha256:" + hashlib.sha256((recipe_root / name).read_bytes()).hexdigest()
        for name in (
            "diagnose.py",
            "offset_controls.py",
            "replay_compensation.py",
            "assemble.py",
            "test_controls.py",
        )
    }
    (args.output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")

    a = np.load(args.work / "diagnostic-arrays.npz")
    target = np.zeros(len(a["times_s"]))
    support = np.zeros(len(target), dtype=bool)
    for case in ("ch1_4", "ch5_8"):
        ix = a[case + "_rows"]
        resp = a[case + "_responsibilities"]
        best = resp.argmax(axis=1)
        j = np.arange(len(ix))
        prediction = a[case + "_prediction"][j, best]
        target[ix] = circular(a["measured_hz"][ix] - prediction)
        support[ix] = resp[j, best] >= 0.8
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), layout="constrained")
    for rx, ax in enumerate(axes):
        for high, color, label in ((False, "#2678b8", "CH1–4"), (True, "#d47b22", "CH5–8")):
            mask = support & (a["receiver"] == rx) & ((a["channel"] >= 5) == high)
            ax.scatter(
                a["times_s"][mask], target[mask] / 1000, s=6, alpha=0.35, c=color, label=label
            )
        ax.set(
            xlabel="Capture time (s)",
            ylabel="Folded CFO minus candidate Doppler (kHz)",
            title=f"RX{rx}: two distinct frequency baselines",
        )
        ax.grid(alpha=0.2)
        ax.legend()
    fig.suptitle(
        "Offsets inferred from frozen half-channel candidate fits; reference position excluded"
    )
    fig.savefig(args.output / "receiver_offsets.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), layout="constrained")
    labels = ["CH1–4", "CH5–8", "CH1–8", "CH1–8\ncompensated"]
    names = ["ch1-4", "ch5-8", "ch1-8", "compensated-ch1-8"]
    colors = ["#2678b8", "#d47b22", "#bc4545", "#269b70"]
    for idx, name in enumerate(names):
        row = cases[name]["finals"][0]
        for ax, key, scale in (
            (axes[0], "horizontal_error_m", 1000),
            (axes[1], "posterior_rms_hz", 1),
            (axes[2], "signal_windows", 1),
        ):
            bars = ax.bar(idx, row[key] / scale, color=colors[idx])
            ax.bar_label(
                bars, fmt="%.2f" if key == "horizontal_error_m" else "%.1f", padding=3, fontsize=9
            )
            ax.grid(axis="y", alpha=0.2)
            ax.set_axisbelow(True)
    axes[0].set(
        ylabel="Distance to configured reference (km)", title="Position error evaluated separately"
    )
    axes[1].set(ylabel="Posterior RMS (Hz)", title="In-sample frequency fit")
    axes[2].set(
        ylabel="Sum of signal responsibilities", title="How much original evidence is explained"
    )
    for ax in axes:
        ax.set_xticks(range(4), labels)
        ax.margins(y=0.15)
    fig.suptitle(
        "Final fitted-c models on the same scan; compensated full replay uses two frozen offsets"
    )
    fig.savefig(args.output / "counterfactual.png", dpi=170)
    plt.close(fig)
    print(json.dumps(cases, indent=2))


if __name__ == "__main__":
    main()
