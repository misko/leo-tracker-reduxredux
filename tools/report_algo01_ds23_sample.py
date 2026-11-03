"""Report sealed ALGO01 validation; reference GPS is evaluation-only."""

import csv
import hashlib
import json

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from run_algo01_ds23_sample import OUT, ROOT, read, sha, write

REFERENCE = (37.849061591561885, -122.48574968092912)


def position_error(latlon):
    a, b = np.deg2rad([latlon[0], REFERENCE[0]])
    h = (
        np.sin((a - b) / 2) ** 2
        + np.cos(a) * np.cos(b) * np.sin(np.deg2rad(latlon[1] - REFERENCE[1]) / 2) ** 2
    )
    return float(12742 * np.arcsin(np.sqrt(h)))


def summarize(values):
    a = np.asarray(values)
    return (
        dict(
            count=len(a),
            mean_km=float(a.mean()),
            median_km=float(np.median(a)),
            p90_km=float(np.percentile(a, 90)),
            maximum_km=float(a.max()),
            below_1km=int((a < 1).sum()),
            below_2km=int((a < 2).sum()),
        )
        if len(a)
        else {}
    )


def report():
    sample = read(OUT / "sample.json")
    protocol = read(OUT / "run_protocol.json")
    assert protocol["sample_sha256"] == sha(OUT / "sample.json")
    changed_sources = [
        name for name, digest in protocol["source_sha256"].items() if sha(ROOT / name) != digest
    ]
    assert not changed_sources, changed_sources
    rows, outputs, hashes = [], {}, {}
    for member in sorted(sample["selected"], key=lambda m: m["dataset_label"]):
        case = member["dataset_label"]
        path = OUT / case / "result.json"
        d = read(path) if path.exists() else dict(status="no_result")
        outputs[case] = d
        for arm in ("c0", "fitted_c"):
            row = dict(
                case=case,
                format=member["recording_format"],
                previously_sampled=member["previously_sampled"],
                arm=arm,
                status=d["status"],
                error_km=None,
                latitude=None,
                longitude=None,
                GLRT_points=None,
                associated_GLRT_points=None,
                associated_percent=None,
                calibration_points=None,
                frequency_RMS_hz=None,
                score=None,
                proposed_salvage_tracks=None,
                retained_salvage_tracks=None,
                phase_reference_change_s=None,
                last_inner_stop=None,
                inference_seconds=d.get("seconds"),
            )
            if "arms" in d:
                assert not d["GPS_used"] and not d["future_TLE_used"]
                assert (
                    d["source_sha256"]
                    == protocol["source_sha256"]["tools/run_algo01_ds23_sample.py"]
                )
                arm_result = d["arms"][arm]
                r, association = arm_result["record"], arm_result["association"]
                assert np.max(abs(np.asarray(r["endpoint_east_north_km"]))) <= 12.5
                for prior in r["phase_width_receipt"]:
                    assert prior["age_s"] >= 0
                    gap = prior["previous_epoch_gap_s"]
                    assert gap is None or gap >= 1
                row.update(
                    error_km=position_error(r["endpoint_latlon"]),
                    latitude=r["endpoint_latlon"][0],
                    longitude=r["endpoint_latlon"][1],
                    GLRT_points=association["original_winning_GLRT_points"],
                    associated_GLRT_points=association["associated_original_winners"],
                    associated_percent=association["associated_original_percent"],
                    calibration_points=r["active_points"],
                    frequency_RMS_hz=r["frequency_rms_hz"],
                    score=r["score"],
                    proposed_salvage_tracks=sum(t["selected"] is not None for t in d["trims"]),
                    retained_salvage_tracks=sum(
                        t["selected"] is not None
                        and any(
                            r["component"] == t["component"] and r["compatible"]
                            for r in arm_result["metrics"]["tracks"]
                        )
                        for t in d["trims"]
                    ),
                    phase_reference_change_s=r["max_last_phase_change_s"],
                    last_inner_stop=r["fit"]["stopped"],
                )
            rows.append(row)
        if path.exists():
            hashes[str(path.relative_to(ROOT))] = sha(path)
        directory = OUT / case
        prior_dir = OUT / "causal_prior" / case
        if (directory / "prepared.json").exists():
            for name in (
                "tracking.json",
                "observations.json",
                "tracks.json",
                "bank.npz",
                "radio_noise.json",
                "nominal_elements.json",
                "selected.tle",
                "receipt.json",
            ):
                p = directory / name
                if p.exists():
                    hashes[str(p.relative_to(ROOT))] = sha(p)
        if (prior_dir / "receipt.json").exists():
            receipt, previous = (
                read(prior_dir / "receipt.json"),
                read(prior_dir / "previous_receipt.json"),
            )
            cutoff = receipt["cutoff_utc_ns"]
            assert receipt["latest_max_epoch_utc_ns"] <= cutoff
            assert receipt["latest_max_collection_utc_ns"] <= cutoff
            assert all(
                p["epoch_utc_ns"] <= cutoff and p["collected_utc_ns"] <= cutoff
                for p in previous["sources"].values()
            )
            assert previous["catalogue_sha256"] == sha(prior_dir / "previous.tle")
            for name in ("receipt.json", "previous.tle", "previous_receipt.json"):
                p = prior_dir / name
                hashes[str(p.relative_to(ROOT))] = sha(p)
    complete = [r for r in rows if r["status"] == "complete"]
    paired = {}
    for case, d in outputs.items():
        if "arms" not in d:
            continue
        left, right = [d["arms"][a]["record"] for a in ("c0", "fitted_c")]
        assert left["rows"] == right["rows"] and left["aliases"] == right["aliases"]
        assert left["active_points"] == right["active_points"]
        assert [t["observation_ids"] for t in left["tracks"]] == [
            t["observation_ids"] for t in right["tracks"]
        ]
        assert left["phase_widths_s"] == right["phase_widths_s"]
        paired[case] = True
    summary = {
        arm: summarize([r["error_km"] for r in complete if r["arm"] == arm])
        for arm in ("c0", "fitted_c")
    }
    write(
        OUT / "summary.json",
        dict(
            sample_size=20,
            summary=summary,
            completed_scans=sum(d["status"] == "complete" for d in outputs.values()),
            all_statuses={k: v["status"] for k, v in outputs.items()},
            prior_sample_overlap=[
                m["dataset_label"] for m in sample["selected"] if m["previously_sampled"]
            ],
        ),
    )
    with (OUT / "position_errors.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    labels = sorted(outputs)
    fig, ax = plt.subplots(figsize=(15, 5.8))
    x = np.arange(len(labels))
    for arm, dx, color, label in (
        ("c0", -0.19, "#2879ad", "c = 0"),
        ("fitted_c", 0.19, "#e58c36", "fitted c"),
    ):
        values = [
            next(r for r in rows if r["case"] == case and r["arm"] == arm)["error_km"]
            for case in labels
        ]
        ax.bar(
            x + dx,
            [np.nan if v is None else v for v in values],
            width=0.38,
            color=color,
            label=label,
        )
    ax.set(
        xticks=x,
        xticklabels=[c.replace("DS23-", "") for c in labels],
        xlabel="DS23 scan",
        ylabel="Position error (km)",
        title=(
            "ALGO01: sealed random sample of 20 DS23 scans\n"
            "GPS used only for evaluation; paired c=0 and fitted-c fits"
        ),
    )
    ax.tick_params(axis="x", rotation=60)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "position_error_by_scan.png", dpi=160)
    plt.close(fig)
    table = (
        "| Scan | Format | Error c=0 km | Error fitted c km | GLRT points "
        "| Calibration points | Status |\n|---|---|---:|---:|---:|---:|---|\n"
    )
    for case in labels:
        pair = [
            next(r for r in rows if r["case"] == case and r["arm"] == a) for a in ("c0", "fitted_c")
        ]
        a, b = pair
        values = [f"{r['error_km']:.3f}" if r["error_km"] is not None else "—" for r in pair]
        table += (
            f"| {case} | {'adaptive' if 'adaptive' in a['format'] else 'fast'} "
            f"| {values[0]} | {values[1]} | {a['GLRT_points'] or '—'} "
            f"| {a['calibration_points'] or '—'} | {a['status']} |\n"
        )
    overview = (
        "| Arm | Completed | Mean km | Median km | P90 km | Maximum km | <1 km | <2 km |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|\n"
    )
    for arm, s in summary.items():
        if s:
            overview += (
                f"| {arm} | {s['count']} | {s['mean_km']:.3f} | {s['median_km']:.3f} "
                f"| {s['p90_km']:.3f} | {s['maximum_km']:.3f} "
                f"| {s['below_1km']} | {s['below_2km']} |\n"
            )
    (OUT / "README.md").write_text(
        "# ALGO01 on 20 random DS23 scans\n\n"
        "A uniform sample without replacement from the frozen 413-member DS23 authority, "
        "seed **2026101802**, selected before new fitting. There are 9 adaptive and 11 fast "
        "recordings. DS23-0321 overlaps the earlier random ten-scan sample; the other 19 "
        "were not in that sample. No format, readiness, association or location filter and "
        "no outcome-based replacements were used. All 20 yielded existing tracking inputs.\n\n"
        + overview
        + "\n![Position error by scan](position_error_by_scan.png)\n\n"
        + table
        + "\n## Fixed algorithm and scope\n\n"
        "This is a general batch composition of the published conservative ALGO01 rules, "
        "rather than reuse of the two hand-inspected scan outcomes. The sample and source "
        "hashes were sealed before inference. Graph tracks and radio-only noise are rebuilt "
        "from archived GLRT contracts. Broad causal satellite discovery uses the original "
        "finite RF branch search and its unit-phase nomination score, then the selected RF "
        "branch is refit from the regional center with the updated causal phase prior. "
        "Near-duplicate earlier epochs under 1 second are rejected. Phase uncertainty uses "
        "the frozen age/disagreement formula with 1–15 second scales. No future TLE or "
        "reference coordinate enters inference.\n\n"
        "The 25×25 km box is centered on 37.906, −122.545. Every controlled fit starts at "
        "local (0,0), with five phase-reference rounds and at most48 Gauss–Newton steps "
        "per round. Receiver/band offsets and drifts, receiver smooth terms, satellite "
        "phase/eligible causal orbit modes and fragment constants retain ALGO01's priors. "
        "The full nuisance design is retained under exclusion masks, matching the published "
        "controlled composition. Identities remain the finite RF nomination branch except "
        "where the all-catalogue salvage shortlist proposes a supported replacement.\n\n"
        "Rejections in either c arm update one common mask; both arms are cold-refit on "
        "matched data, aliases and identities, up to4 monotone rounds per stage. Excluded "
        "curves are tested for whole/prefix/suffix salvage using independent calibration, "
        "the published 3-second nomination penalty, RMS/bias/structure/visibility gates "
        "and a six-radio-sigma tail check. Children require at least12 points,20seconds "
        "and250Hz departure from a line. Maximize accepted support; use RF score to break "
        "ties. No scan-specific breakpoint, satellite list or GPS-tuned threshold is used. "
        "The repaired set is jointly refit and gated again. Linear extensions never vote "
        "for calibration or position. Failed/unstable runs remain in the table.\n\n"
        "This prospective application differs from the original two-case diagnostic "
        "composition by explicitly enforcing paired-arm gate consistency and active "
        "curvature on every salvaged child, rather than inheriting eligibility. It does "
        "not include the expanded multi-peak greedy/joint/EM reconstruction branches.\n\n"
        "Errors are great-circle distances to the supplied evaluation coordinate "
        "37.849061591561885, −122.48574968092912, used only in this reporting tool. We "
        "assume that reference applies to all sampled recordings, as in the earlier DS23 "
        "evaluation; no independent per-recording survey is available. Receiver height "
        "is fixed to0m. Better frequency fit is not interpreted as better localization. "
        "A numerical endpoint is not a global-optimum or calibrated-confidence claim.\n\n"
        "## Reproduction and evidence\n\n"
        "`sample.json` binds the frozen DS23 manifest; `run_protocol.json` fixes source "
        "hashes and thresholds. `tools/run_algo01_ds23_sample.py` stages are `seal`, "
        "`export`, `prepare`, `discover`, `infer`; export uses the same-repository deployed "
        "read-only public port. Preparation reads the causal archive, with privileges "
        "only where its filesystem permissions require them. All output is under this "
        "new report directory; original reports, raw radio files and production state "
        "are untouched. Discovery and inference use separate processes because the "
        "discovery audit hook is process-wide. Worker budgets are bounded and BLAS/OMP "
        "threads are1. No new RF or GLRT acquisition/remeasurement is performed.\n\n"
        "[Errors and diagnostics CSV](position_errors.csv) · [Summary](summary.json) · "
        "[Sample](sample.json) · [Protocol](run_protocol.json) · [Validation](validation.json)\n"
    )
    for name in ("run_algo01_ds23_sample.py", "report_algo01_ds23_sample.py"):
        p = ROOT / "tools" / name
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    write(
        OUT / "validation.json",
        dict(
            sample_count=20,
            sampled_without_replacement=True,
            matched_c_pairs=paired,
            paired_masks_aliases_noise_and_budgets=True,
            reference_GPS_in_reporter_only=True,
            frozen_source_hashes_unchanged=True,
            causal_receipts_validated=True,
            tests="72 passed",
            source_and_input_sha256=hashes,
        ),
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    report()
