"""Post-seal state diagnostics and report; no objectives, fits or selection."""
# ruff: noqa: E501

import sys

import control
import matplotlib
import numpy as np
from leo.analysis.regional_position_score import coordinates, zero_sum_basis
from leo.contracts.regional_position import RegionalPrior

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = control.HERE


def distance_km(lat, lon, reference):
    a, b = np.radians([lat, lon])
    ra, rb = np.radians([reference["latitude_deg"], reference["longitude_deg"]])
    hav = np.sin((a - ra) / 2) ** 2 + np.cos(a) * np.cos(ra) * np.sin((b - rb) / 2) ** 2
    return float(2 * 6371.0088 * np.arcsin(np.sqrt(hav)))


def summarize_states():
    # Evaluation proves all four raw fits and both pairs of predictions sealed.
    evaluation = control.read(HERE / "evaluation.json")
    for path, sha in evaluation["source_seals"].items():
        if control.digest(path) != sha:
            raise ValueError("Post-seal authority changed")
    ports = control.public_ports()
    source = ports.qualifier
    terminal = control.read(source.ATTEMPT / "output/terminal.json")
    prior = RegionalPrior(**terminal["provenance"]["prior"])
    reference_path = control.REPORTS.parent / "deploy/station/gauss-r20-lt3d-004b-20261001-v1.json"
    reference = control.read(reference_path)
    derivation = control.read(source.ATTEMPT / "derivation.json")
    recorded = control.read(source.ATTEMPT / "training-input.json")["source"]
    if recorded["radio_id"] != reference["radio_serial"]:
        raise ValueError("Radio identity differs")
    if (
        not reference["valid_from_utc_ns"]
        <= derivation["origin_utc_ns"]
        < reference["valid_until_utc_ns"]
    ):
        raise ValueError("Reference applicability interval differs")
    center = np.array(
        control.read(source.ATTEMPT / "output/stages/shape-all.json")["result"]["winner"]["theta"][
            :2
        ]
    )
    states = []
    corrections = {}
    for arm in ("fitted-c", "zero-c"):
        for family, directory, prefix in (
            ("legacy", HERE / "inference_results", "old_"),
            ("new_point", control.RESULTS, "independent_"),
        ):
            key = prefix + arm
            fit = control.read(directory / ("fit_" + key + ".json"))
            with np.load(directory / ("predictions_" + key + ".npz"), allow_pickle=False) as z:
                p = dict(z)
            v, n = np.asarray(fit["result"]["vector"]), np.asarray(fit["result"]["nuisance"])
            seed_n = np.asarray(fit["original_seed"]["nuisance"])
            lat, lon = coordinates(prior, v[:2])
            relative = zero_sum_basis(len(p["number"])) @ v[8:]
            # This source has clock + K-1 q contrasts + two free RX bands.
            clock_count = len(n) - (len(p["number"]) - 1) - 2
            if clock_count != 18:
                raise ValueError("Qualified original nuisance layout differs")
            states.append(
                dict(
                    family=family,
                    arm=arm,
                    latitude_deg=lat,
                    longitude_deg=lon,
                    configured_reference_distance_km=distance_km(lat, lon, reference),
                    inside_old_production25km_disk=bool(
                        np.linalg.norm(v[:2] - center) <= 25 + 1e-9
                    ),
                    broad_research_audit=fit["independent_endpoint_status"],
                    common_timing_s=float(v[7]),
                    relative_timing_s=relative,
                    relative_timing_rms_s=float(np.sqrt(np.mean(relative**2))),
                    total_timing_s=v[7] + relative,
                    q=p["detection_probability"],
                    calibration_five_coefficients=v[2:7],
                    clock_coordinates_hz=n[:clock_count],
                    absolute_band_offsets_hz=n[-2:],
                    band_updates_from_common_seed_hz=n[-2:] - seed_n[-2:],
                    cost=fit["cost"],
                    diagnostics=fit["result"]["diagnostics"],
                )
            )
            corrections[family, arm] = p
    contrasts = []
    for arm in ("fitted-c", "zero-c"):
        old, new = corrections["legacy", arm], corrections["new_point", arm]
        for field in ("observation_id", "times_s", "receiver", "channel", "rf_hz"):
            np.testing.assert_array_equal(old[field], new[field])
        for rx in (0, 1):
            for band, mask in (("low", old["channel"] <= 4), ("high", old["channel"] >= 5)):
                use = mask & (old["receiver"] == rx)
                delta = new["correction_hz"][use] - old["correction_hz"][use]
                contrasts.append(
                    dict(
                        arm=arm,
                        receiver_human=rx + 1,
                        receiver_native=rx,
                        band=band,
                        observations=int(use.sum()),
                        mean_hz=float(delta.mean()),
                        rms_hz=float(np.sqrt(np.mean(delta**2))),
                        minimum_hz=float(delta.min()),
                        maximum_hz=float(delta.max()),
                    )
                )
    control.save(
        HERE / "state_diagnostics.json",
        dict(
            rows=states,
            correction_function_contrasts=contrasts,
            correction_semantics="New minus legacy evaluated at the same recorded times/RFs and common frame; not hardware truth",
            reference_sha256=control.digest(reference_path),
            reference_evidence=reference["position_evidence"],
            reference_usage="Post-seal descriptive only; never seed, selection or gate",
            no_new_objectives=True,
            fits=0,
        ),
    )


def render():
    d = control.read(HERE / "evaluation.json")
    states = control.read(HERE / "state_diagnostics.json")["rows"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for col, arm in enumerate(("fitted-c", "zero-c")):
        blocks = [b for b in d["blocks"] if b["arm"] == arm]
        vals = [b["delta_original_shared_nll"] for b in blocks]
        axes[0, col].bar(
            [b["start_s"] for b in blocks],
            vals,
            width=14,
            color=["#25816c" if v < 0 else "#b85c4f" for v in vals],
        )
        axes[0, col].axhline(0, color="black", lw=0.7)
        axes[0, col].set(
            title=arm + ": new point minus legacy",
            xlabel="Held block start (s)",
            ylabel="Original shared predictive NLL change",
        )
        for off, score in enumerate(("original_shared", "new_singleton")):
            m = d["rows"][arm][score]["held"]
            axes[1, col].bar(
                np.arange(2) + (off - 0.5) * 0.32,
                [m["original"], m["associated"]],
                width=0.32,
                label="Original shared" if off == 0 else "New singleton",
            )
        axes[1, col].set(
            xticks=[0, 1],
            xticklabels=["Legacy density", "New point density"],
            ylabel="Assigned / 1909 held",
            title=arm + ": separate classifiers",
        )
        axes[1, col].legend(fontsize=8)
    fig.savefig(HERE / "paired_predictive_comparison.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    labels = [r["family"] + "_" + r["arm"] for r in states]
    axes[0, 0].bar(
        np.arange(4), [r["configured_reference_distance_km"] for r in states], color="#5b80a5"
    )
    for i, r in enumerate(states):
        axes[0, 0].scatter(
            i,
            r["configured_reference_distance_km"],
            color="black",
            marker="o" if r["broad_research_audit"]["accepted"] else "x",
            zorder=3,
        )
    axes[0, 0].set(
        xticks=range(4),
        xticklabels=labels,
        ylabel="Configured distance (km)",
        title="Post-seal location: o strict, x nonstrict",
    )
    axes[0, 0].tick_params(axis="x", rotation=25)
    bins = np.linspace(0, max(max(r["q"]) for r in states) * 1.05, 25)
    for r, label in zip(states, labels, strict=True):
        axes[0, 1].hist(
            r["relative_timing_s"],
            bins=np.arange(-24, 26, 2),
            histtype="step",
            label=f"{label}; common {r['common_timing_s']:.2f}s",
        )
        axes[1, 0].hist(r["q"], bins=bins, histtype="step", label=label)
    axes[0, 1].set(
        xlabel="Relative timing (s)",
        ylabel="Candidates (45 per state)",
        title="Same 2s relative / 3s common priors",
    )
    axes[0, 1].legend(fontsize=7)
    axes[1, 0].set(
        xlabel="Full-bank detection q",
        ylabel="Candidates (45 per state)",
        title="Same total budget 1.6",
    )
    axes[1, 0].legend(fontsize=7)
    for rx in (0, 1):
        axes[1, 1].bar(
            np.arange(4) + (rx - 0.5) * 0.32,
            [r["band_updates_from_common_seed_hz"][rx] / 1000 for r in states],
            width=0.32,
            label=f"RX{rx + 1} (native {rx}) high-band constant",
        )
    axes[1, 1].set(
        xticks=range(4),
        xticklabels=labels,
        ylabel="Update from same seed (kHz)",
        title="Free receiver-band constants",
    )
    axes[1, 1].tick_params(axis="x", rotation=25)
    axes[1, 1].legend(fontsize=7)
    fig.savefig(HERE / "state_parameter_comparison.png", dpi=160)
    plt.close(fig)
    lines = [
        "# Matched point-density control: negative broadening gate",
        "",
        "With fitted c, both matched endpoints are strict. The new point density improves primary held "
        "NLL by only1.91, improves3/7 blocks and changes original-classifier coverage810→806/1909 "
        "while requested coverage rises72→73/80. This fails the frozen gate; no all-five expansion follows.",
        "",
        "| c arm | Same evaluation PDF | Legacy held NLL | New-point held NLL | Held legacy→new /1909 | "
        "Requested legacy→new /80 | New/lost held |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    paired_prose = []
    for arm, row in d["rows"].items():
        for score in ("original_shared", "new_singleton"):
            m, w = row[score]["held"], row[score]["requested_held"]
            lines.append(
                f"| {arm} | {score} | {m['original_nll']:.3f} | {m['current_nll']:.3f} | "
                f"{m['original']}→{m['associated']} | {w['original']}→{w['associated']} | {m['new']}/{m['lost']} |"
            )
            paired_prose += [
                "",
                f"{arm}, {score}: {m['retained']} held points retained, "
                f"{m['retained_identity_changes']} model-ID changes. On that same intersection RMS "
                f"changes {m['intersection_original_rms_hz']:.3f}→{m['intersection_current_rms_hz']:.3f}Hz; "
                f"changing-set RMS is {m['original_associated_rms_hz']:.3f}→{m['current_associated_rms_hz']:.3f}Hz.",
                "",
            ]
    lines += paired_prose
    lines += [
        "The table and paired residuals use the same score/classifier within each row. The primary "
        "score is the original shared normalized PDF; the new proper singleton PDF is secondary. "
        "Neither is an emitter-identity truth test. Both PDFs are normalized: this experiment changes "
        "odds/signal/clutter weighting as a density family, not a broken normalizer.",
        "",
        "The reused new-point endpoints are immutable iteration8 results. Exactly two legacy-density "
        "controls were added, with the same public TRAIN terminal complete seed,45 ordered candidates, "
        "2073 TRAIN rows, free bands, priors, broad regional domain and1000-call/120s allowance. "
        "Newpoint c0 remains nonstrict; it was not repaired or retried. Both legacy controls are strict. "
        "c0 is conditional after fitted-c upstream discovery and is not a selection arm.",
        "",
        "This is a posthoc control motivated by already inspected S03 outcomes, not unseen validation. "
        "The gate and metrics were frozen in PROTOCOL before outcomes. Evaluator source freeze occurred "
        "after the short control fits completed but before any new held scores were read; only their "
        "convergence and costs were known. All raw states and all predictions sealed before held scoring. "
        "No state, hyperparameter, window or source winner was selected from held measurements.",
        "",
        "| State | KKT | Strict | Calls + audit | Configured distance km | Inside old25km disk |",
        "|---|---:|---|---:|---:|---|",
    ]
    for r in states:
        audit, diag = r["broad_research_audit"], r["diagnostics"]
        lines.append(
            f"| {r['family']}_{r['arm']} | {audit['stationarity']:.6g} | {audit['accepted']} | "
            f"{diag['evaluations']} +1 | {r['configured_reference_distance_km']:.6f} | {r['inside_old_production25km_disk']} |"
        )
    lines += [
        "",
        "Configured station coordinates enter only these post-seal descriptive diagnostics; "
        "survey uncertainty is unknown. The common broad regional domain does not impose the original "
        "extra25km local production constraint. Correction functions use the same recorded times/RFs in "
        "state_diagnostics.json; coefficients alone are not hardware evidence. Plot RX1/RX2 are native0/1.",
        "",
        "TRAIN2073, HELD1909 and boundary6 remain separate. Requested HELD80 spans windows007/008/009 "
        "with26/28/26 denominators. The other four sources and555 requested observations are untested. "
        "All rows, losses, model-ID changes, per-window metrics, seven blocks and changing versus "
        "retained-pair RMS remain in evaluation.json/NPZ. No held grouping, new RF, position seed, "
        "all-five fit, promotion or reference-based selection occurred.",
        "",
        "![Paired held forecasts](paired_predictive_comparison.png)",
        "",
        "![Complete state diagnostics](state_parameter_comparison.png)",
    ]
    lines += ["", "| c arm | Requested held window | Legacy original-classifier /N | New point /N |",
              "|---|---|---:|---:|"]
    for arm, row in d["rows"].items():
        for rid, roles in row["original_shared"]["windows"].items():
            m = roles["held"]
            lines.append(f"| {arm} | {rid} | {m['original']}/{m['observations']} | "
                         f"{m['associated']}/{m['observations']} |")
    lines += ["", "The frozen test docstring's phrase 'Pre-outcome gate direction' describes the "
        "already prespecified gate logic; evaluator implementation and its tests were completed after "
        "control fits and before held scoring. This chronology is retained in evaluation_source_freeze.json, "
        "not retroactively relabelled as pre-outcome implementation.", "",
        "The original cold fitted-c endpoint's795/1909 held and66/80 requested assignments is a "
        "descriptive anchor. The matched legacy free-band continuation reaches810 and72; the new "
        "point-density continuation reaches806 and73. Thus gains over the original pipeline are largely "
        "also achievable with free-band continuation of the legacy density. This does not isolate "
        "normalization, establish geographic improvement or justify choosing either state by position."]
    with (HERE / "README.md").open("x") as stream:
        stream.write("\n".join(lines) + "\n")


def seal():
    for name in ("README.md", "evaluation.json", "state_diagnostics.json"):
        if not (HERE / name).is_file():
            raise ValueError("Complete report required")
    rows = [
        dict(path=str(p.relative_to(HERE)), sha256=control.digest(p))
        for p in sorted(HERE.rglob("*"))
        if p.is_file() and p.name != "FINAL_SEAL.json"
    ]
    inputs = control.read(HERE / "evaluation_source_freeze.json")["files"]
    control.io.verify_bindings(inputs)
    control.save(
        HERE / "FINAL_SEAL.json",
        dict(
            files=rows,
            input_source_bindings=inputs,
            sealed=True,
            scope="Two posthoc legacy controls versus immutable point-density states; no expansion",
        ),
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["states"]:
        summarize_states()
    elif sys.argv[1:] == ["report"]:
        render()
    elif sys.argv[1:] == ["seal"]:
        seal()
    else:
        raise ValueError("states, report or seal required")
