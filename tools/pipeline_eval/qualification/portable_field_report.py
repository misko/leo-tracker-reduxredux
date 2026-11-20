"""Render the paired position and stage evidence for the portable field replay."""

import csv

from ..__main__ import save_json, write
from ..scoring import ARMS, ROLES
from . import accelerated_command_results as accelerated
from .portable_field_scores import ARCHIVE, CASE, HISTORICAL, PORTABLE, POSITION
from .prefix_figures import csv_file

PLOT = "field-stages.png"
CHART = "portable-field-ds26-0020"
METHODS = {
    PORTABLE: "Portable live",
    ARCHIVE: "Archived compact",
    "baseline": "v5 baseline",
    "selective-gap": "v5 selective gap",
    "omitted-track-one": "v5 one omitted",
    "omitted-tracks": "v5 two omitted",
}


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def stage_rows(directory, evidence, scores):
    rows = []

    def row(panel, series, value, unit, *, visit=None, arm=None, fraction=None):
        if value is not None:
            rows.append(
                dict(
                    panel=panel,
                    series=series,
                    arm=arm,
                    visit=visit,
                    value=value,
                    unit=unit,
                    fraction=fraction,
                )
            )

    live_visits = directory / "raw-visits.csv"
    controls = [("Accelerated", HISTORICAL / "secondary-raw-visits.csv")]
    if live_visits.is_file() and evidence["raw"]["completed"]:
        controls.insert(0, ("Portable", live_visits))
    for name, path in controls:
        visits = [r for r in read_csv(path) if r["status"] == "processed"]
        for label, field in (("CPU", "cpu_ms"), ("wall", "wall_ms")):
            ordered = sorted((float(r[field]), int(r["visit"])) for r in visits)
            for i, (value, visit) in enumerate(ordered, start=1):
                row("visit", f"{name} {label}", value, "ms", visit=visit, fraction=i / len(ordered))
    row("visit_reference", "Visit budget", 20, "ms")
    for label, elapsed in (
        ("Recorded delivery span", evidence["recorded_delivery_span_s"]),
        ("Portable raw", evidence["raw"].get("wall_s")),
        ("Portable compact fit", accelerated.compact_wall(evidence.get("fit", {}))),
        ("Portable command", command_wall(evidence)),
        ("Accelerated raw", evidence["accelerated_raw"]["wall_s"]),
        ("Accelerated compact fit", accelerated.compact_wall(evidence["accelerated_compact"])),
        ("Accelerated command", evidence["accelerated_command"]["process_elapsed_s"]),
        ("Archived compact fit", accelerated.compact_wall(evidence["archived_compact"])),
    ):
        row("elapsed", label, elapsed, "s")
    for score in scores:
        name = METHODS[score["method"]]
        row("rf", name, score["rf_rms_hz"], "Hz", arm=score["arm"])
        row("objective", name, score["frequency_score"], "score", arm=score["arm"])
    return rows


def command_wall(evidence):
    return evidence.get("command_clock", {}).get(
        "process_elapsed_s", evidence.get("command_wall_s")
    )


def plot(stage, path):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12.8, 8.9), layout="constrained")
    a, b, c, d = axes.ravel()
    for label, colour in (("Portable", "#1b766a"), ("Accelerated", "#7a4ba8")):
        for mode, line in (("CPU", "-"), ("wall", "--")):
            points = [
                r for r in stage if r["panel"] == "visit" and r["series"] == f"{label} {mode}"
            ]
            if points:
                a.step(
                    [r["value"] for r in points],
                    [r["fraction"] for r in points],
                    label=points[0]["series"],
                    color=colour,
                    ls=line,
                    where="post",
                )
    (budget,) = [r for r in stage if r["panel"] == "visit_reference"]
    a.axvline(budget["value"], color="0.3", ls=":", label=f"{budget['value']} ms")
    a.set(
        xscale="log",
        xlabel="Detector duration per valid visit (ms)",
        ylabel="Share at or below duration",
        ylim=(0, 1.03),
    )
    a.legend(frameon=False, fontsize=8)

    elapsed = [r for r in stage if r["panel"] == "elapsed"]
    b.barh(
        [r["series"] for r in elapsed],
        [r["value"] for r in elapsed],
        color=[
            "#1b766a"
            if r["series"].startswith("Portable")
            else "#7a4ba8"
            if r["series"].startswith("Accelerated")
            else "#59707e"
            for r in elapsed
        ],
    )
    b.invert_yaxis()
    b.set(xlabel="Elapsed wall time (s)")

    markers = ("o", "s", "D", "x", "^", "+")
    colours = ("#1b766a", "#59707e", "#20262f", "#855519", "#7141a2", "#aa371d")
    for axis, panel, unit in (
        (c, "rf", "Fitted CFO RMS (Hz)"),
        (d, "objective", "Compact frequency score"),
    ):
        for i, (name, marker, colour) in enumerate(
            zip(METHODS.values(), markers, colours, strict=True)
        ):
            points = [r for r in stage if r["panel"] == panel and r["series"] == name]
            if points:
                axis.scatter(
                    [ARMS.index(r["arm"]) + (i - 2) * 0.055 for r in points],
                    [r["value"] for r in points],
                    marker=marker,
                    color=colour,
                    label=name,
                )
        axis.set(xticks=(0, 1), xticklabels=("c = 0", "Fitted c"), xlim=(-0.30, 1.30), ylabel=unit)
        axis.ticklabel_format(axis="y", useOffset=False, style="plain")
        axis.legend(frameon=False, fontsize=8)
    fig.suptitle("DS26-0020 replay timing and RF fit")
    fig.savefig(path, dpi=145)
    plt.close(fig)


def value(number, digits=3):
    return "Unavailable" if number is None else f"{number:,.{digits}f}"


def terminal_result(number, status, digits):
    return value(number, digits) if number is not None else status.replace("_", " ").capitalize()


def render_markdown(evidence, proof, rows, quality, receipts):
    raw = evidence["raw"]
    archive_raw = evidence["accelerated_raw"]
    raw_complete = raw["complete"]
    expected = evidence["inventory"]["scheduled"]
    coverage = (
        f"{raw['completed']:,}/{expected:,} signed visits in "
        f"{raw['completed_chunks']:,} closed chunks"
    )
    verdict = quality["primary"]["within_5_percent"]
    wider = quality["primary"]["within_10_percent"]
    if verdict or wider:
        target = 5 if verdict else 10
        geographic = (
            f"Both calibration arms met the {target}% geographic error target against the "
            "original v5 baseline on this recording."
        )
    elif wider is False:
        geographic = (
            "The portable receiver missed the 10% geographic error target against the "
            "original v5 baseline on this recording."
        )
    else:
        geographic = (
            "At least one calibration arm did not publish. The paired verdict is unavailable."
        )
    if raw_complete:
        change_cpu = 100 * (raw["detector_cpu_s"] / archive_raw["detector_cpu_s"] - 1)
        direction = "less" if change_cpu < 0 else "more"
        run_cost = (
            f"The detector used **{abs(change_cpu):.2f}% {direction} CPU time** than the "
            "historical accelerated replay."
        )
    else:
        run_cost = "The incomplete raw run gives no paired detector CPU verdict."
    lines = [
        "# Portable C receiver on DS26-0020",
        "",
        "The experiment tests whether the portable acquisition and GLRT verifier can retain v5 "
        "accuracy while reducing processing cost on the preselected passive recording. "
        f"The portable run covered **{coverage}**. {geographic} {run_cost} "
        "[Scoring protocol](SCORING-PROTOCOL.md) · [Prediction seal](prediction-lock.json) · "
        "[Score seal](score-lock.json)",
        "",
        "## Geographic error and RF fit",
        "",
        "| Run | `c = 0` error (km) | Fitted `c` error (km) | `c = 0` CFO RMS (Hz) | "
        "Fitted `c` CFO RMS (Hz) | `c = 0` frequency score | Fitted `c` frequency score |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for method, label in METHODS.items():
        arms = [next(r for r in rows if (r["method"], r["arm"]) == (method, arm)) for arm in ARMS]
        fields = [terminal_result(r["error_km"], r["status"], 5) for r in arms]
        fields += [value(r["rf_rms_hz"], 5) for r in arms]
        fields += [value(r["frequency_score"], 3) for r in arms]
        lines.append("| " + " | ".join([label, *fields]) + " |")
    change = quality["fitted_c_minus_c0"][PORTABLE]
    ratios = quality["comparison_by_control"]
    fit_comparison = evidence.get("archive_position_comparison", {})
    lines.extend(
        [
            "",
            "| v5 comparison | `c = 0` relative error change | Fitted `c` relative error change |",
            "| --- | ---: | ---: |",
        ]
    )
    for method in ROLES:
        fields = []
        for arm in ARMS:
            pct = ratios[method][arm]["degradation_percent"]
            fields.append("Unavailable" if pct is None else f"{pct:+.2f}%")
        lines.append("| " + " | ".join([METHODS[method], *fields]) + " |")
    one_omitted = ratios["omitted-track-one"]
    strongest = ""
    if all(one_omitted[arm]["within_10_percent"] for arm in ARMS):
        strongest = "Both portable arms also met the 10% target against v5 one omitted. "
        if not any(one_omitted[arm]["within_5_percent"] for arm in ARMS):
            strongest += "Both exceeded the 5% margin. "
    timeout = receipts["omitted-tracks"]
    ablation = "The portable pair supplied no complete geographic calibration ablation. "
    if change["error_km"] is not None:
        ablation = (
            f"Fitting `c` changed the portable error by **{value(change['error_km'], 5)} km**, "
            f"the CFO RMS by **{value(change['rf_rms_hz'], 5)} Hz**, and the compact frequency "
            f"score by **{value(change['frequency_score'], 5)}**. Both arms used the same raw "
            "factors, causal snapshots, region, track settings and compact solver invocation. "
            "The archived original v5 requests lack a comparable frequency objective. "
        )
    lines.extend(
        [
            "",
            strongest
            + ablation
            + f"The original v5 two-omitted process reached its {value(timeout['timeout_s'], 0)} s "
            f"deadline and ended after {value(timeout['wall_s'], 2)} s. [Scores](scores.csv) · "
            "[Four original v5 execution receipts](original-v5-receipts.json) · "
            "[`c = 0` chart](charts/c0/portable-field-ds26-0020.png) · "
            "[Fitted `c` chart](charts/fitted_c/portable-field-ds26-0020.png)",
        ]
    )
    if fit_comparison.get("available"):
        separation = fit_comparison["paired_endpoint_separation_km"]
        sep = {
            arm: value(km * 1e6 if km is not None else None, 5) for arm, km in separation.items()
        }
        lines.extend(
            [
                "",
                "Endpoint separation from the independently timed archived compact fit was "
                f"**{sep['c0']} mm** at `c = 0` and **{sep['fitted_c']} mm** with fitted `c`. "
                "[Fit and request receipts](field-evidence.json)",
            ]
        )
    lines.extend(
        [
            "",
            "## Timing",
            "",
            "| Measurement | Portable | Accelerated completion |",
            "| --- | ---: | ---: |",
        ]
    )
    in_scope = (raw, archive_raw)
    for label, keys in (
        ("Raw pipeline wall (s)", ("wall_s",)),
        ("Closed valid visits, detector CPU sum (s)", ("detector_cpu_s",)),
        ("Terminal raw workers, cgroup CPU sum (s)", ("raw_worker_cpu_s",)),
        ("Valid visit CPU p50 (ms)", ("per_valid_visit", "cpu_ms", "p50")),
        ("Valid visit CPU p95 (ms)", ("per_valid_visit", "cpu_ms", "p95")),
        ("Valid visit wall p50 (ms)", ("per_valid_visit", "wall_ms", "p50")),
        ("Valid visit wall p95 (ms)", ("per_valid_visit", "wall_ms", "p95")),
    ):
        nums = []
        for item in in_scope:
            for key in keys:
                item = (item or {}).get(key)
            nums.append(value(item, 2))
        lines.append(f"| {label} | {nums[0]} | {nums[1]} |")
    for clock, label in (("cpu", "CPU"), ("wall", "wall")):
        counts = [r.get("per_valid_visit", {}).get(f"{clock}_ms") for r in in_scope]
        text = ["Unavailable" if not t else f"{t['within_20_ms']:,}/{t['n']:,}" for t in counts]
        lines.append(f"| Valid visit {label} at or below 20 ms | {text[0]} | {text[1]} |")
    for label, numbers in (
        (
            "Compact service wall (s)",
            [
                accelerated.compact_wall(evidence.get("fit", {})),
                accelerated.compact_wall(evidence["accelerated_compact"]),
            ],
        ),
        (
            "Compact worker CPU (s)",
            [
                evidence.get("fit", {}).get("worker_cpu_s"),
                evidence["accelerated_compact"]["worker_cpu_s"],
            ],
        ),
        (
            "Whole command wall (s)",
            [command_wall(evidence), evidence["accelerated_command"]["process_elapsed_s"]],
        ),
    ):
        lines.append(f"| {label} | {value(numbers[0], 2)} | {value(numbers[1], 2)} |")
    delivery = evidence["recorded_delivery_span_s"]
    archived = evidence["archived_compact"]
    archived_wall = accelerated.compact_wall(archived)
    cpus = ", ".join(map(str, evidence.get("cpus", []))) or "unavailable"
    lines.extend(
        [
            "",
            (
                f"The signed delivery timeline spanned **{value(delivery, 2)} s**. The archived "
                f"compact service took **{value(archived_wall, 2)} s** of wall "
                f"and **{value(archived['worker_cpu_s'], 2)} s** of worker CPU on CPU 19. "
                "Per-visit detector clocks exclude compressed IQ decode and compact fitting. "
                "Raw pipeline clocks include read and decode. Worker CPU aggregates span "
                f"concurrent workers. The accelerated completion used CPUs 0 to 7. The portable "
                f"CPU set was {cpus}. The runs occurred at different times on a shared host. "
                "Embedded end-to-end throughput remains unmeasured. "
                "[Timing and CPU receipts](field-evidence.json) · [Stage plot data](stage.csv)"
            ),
            "",
            "![Per-visit CPU and wall timing, service wall, and RF fit](field-stages.png)",
        ]
    )
    if raw_complete:
        clock = evidence.get("command_clock")
        exposure = raw["valid"] * 0.020
        peak_mib = raw["largest_worker_peak_bytes"] / 2**20
        workspace_mib = (
            max(
                worker["terminal"]["portable_workspace_bytes"] for worker in raw["workers"].values()
            )
            / 2**20
        )
        lines.extend(
            [
                "",
                (
                    f"The {raw['valid']:,} valid visits carried **{value(exposure, 2)} s** of IQ "
                    f"at 20 ms each. Each C detector reserved **{value(workspace_mib, 2)} MiB** of "
                    "workspace per worker. The portable raw services reached a maximum cgroup "
                    f"peak of **{value(peak_mib, 2)} MiB** including file cache. "
                    + (
                        "The full command uses the independent boot clock through pidfd exit. "
                        if clock
                        else "The portable command clock ends at the terminal runner interval. "
                    )
                    + "[Run receipt](field-evidence.json)"
                ),
            ]
        )
    lines.extend(["", "## Detector parity", ""])
    if proof["compared_visits"]:
        ranks = proof["rank_counts"]
        gates = proof["gate_counts"]
        physical = proof["physical_neighbourhood"]
        scope = (
            "the complete native handoff"
            if proof["coverage"] == "complete_native"
            else "closed signed chunks"
        )
        exclusions = "matched" if proof["exclusion_rows_match"] else "differed"
        limits = physical["matched_absolute_error"]
        cfo = limits["circular_cfo_hz"]["max"]
        epoch = limits["epoch_samples"]["max"]
        cfo_text = f"{cfo:.4g} Hz" if cfo is not None else "unavailable"
        epoch_text = f"{epoch:.4g} sample" if epoch is not None else "unavailable"
        proof_detail = (
            f"Parity covers {scope} with **{proof['measured_probes']:,}** portable and "
            f"**{proof['archived_probes']:,}** archived physical probes. Canonical JSON matched "
            f"at **{proof['exact_probes']:,}** probes and differed at "
            f"**{proof['different_probes']:,}**. There were **{proof['measured_candidates']:,}** "
            f"portable and **{proof['archived_candidates']:,}** archived candidates. Physical "
            f"correspondence left **{ranks['unmatched_measured']:,}** portable and "
            f"**{ranks['unmatched_archived']:,}** archived candidates unmatched. Matched peaks "
            f"differed by at most **{cfo_text}** circular CFO and **{epoch_text}** in epoch. "
            f"There were **{ranks['matched_rank_changed']:,}** matched rank changes and "
            f"**{gates['matched_gate_changed']:,}** matched fractional gate changes. "
            f"**{physical['ambiguous_probes']:,}** probes admitted alternative peak matches. "
            f"Delivery clocks differed at **{len(proof['delivery_clock_mismatches']):,}** visits. "
            f"The exclusions {exclusions}. [Native parity](native-parity.json) · "
            "[Changed probe fields](native-differences.jsonl.gz) · "
            "[Equivalent peaks](equivalent-peaks.jsonl.gz) · "
            "[C acquisition and refinement attempts](portable-attempts.jsonl.gz)"
        )
    else:
        proof_detail = (
            "The run produced no authenticated closed portable visits for detector comparison. "
            "[Coverage receipt](field-evidence.json)"
        )
    lines.append(proof_detail)
    if raw_complete and evidence.get("native_sha256"):
        details = evidence.get("attempt_ledger_summary", {})
        stage = details.get("total_detector_stage_s", {})
        lines.extend(
            [
                "",
                f"Coarse search consumed **{value(stage.get('coarse_cpu_s'), 2)} CPU s** and "
                f"verification consumed **{value(stage.get('verify_cpu_s'), 2)} CPU s** across "
                "all attempted C groups. The source lock binds the rolling coarse implementation "
                "and the verifier build. [C and TLE source bindings](field-evidence.json)",
            ]
        )
    if trace := evidence.get("visit_931_coarse_diagnostic"):
        first, second = trace["eighth_coarse_cell"]
        lines.extend(
            [
                "",
                (
                    f"At visit {trace['visit']} on RX0, seven retained coarse cells agreed in "
                    f"order. A maximum coarse-grid score delta of "
                    f"**{trace['max_absolute_grid_error']:.3g}** reversed the eighth slot between "
                    f"epochs {first['epoch']} and {second['epoch']}. The archived candidate had a "
                    f"fractional margin of **{first['fractional_margin']:.6f}** against a gate of "
                    f"**{trace['fractional_margin_gate']:.3f}**. The substituted portable attempt "
                    "did not bracket a fractional epoch. "
                    "[Signed single-visit diagnostic](visit-931-coarse.json)"
                ),
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_report(directory, evidence, proof, scores, quality, receipts):
    stage = stage_rows(directory, evidence, scores)
    csv_file(directory / "stage.csv", stage)
    plot(stage, directory / PLOT)
    save_json(
        directory / "stage-figure.json",
        dict(
            version=1,
            id=CHART + "-stages",
            title="Portable field replay timing and RF fit",
            sample="One signed 6,764-visit lower-edge capture, with historical accelerated raw "
            "replay and the archive-only compact fit.",
            boundary="Detector visits, raw pipeline, compact fit and command use distinct clocks.",
            note="The RF panel shows in-sample fitted CFO RMS. The paired charts show geography.",
            seal="score-lock.json",
            image=PLOT,
            csv="stage.csv",
        ),
    )
    save_json(
        directory / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id=CHART,
                    method=PORTABLE,
                    scope="roof",
                    title="Portable acquisition and verifier on DS26-0020",
                    caption="Signed original-schedule replay versus archived compact fit and all "
                    "four original v5 decisions. Same survey, causal catalogue and 25 km tile.",
                    cases=[CASE],
                    seal="score-lock.json",
                    provenance=["prediction-lock.json", "original-v5-receipts.json"],
                    series=[
                        dict(
                            key="one",
                            label="Portable live",
                            value=PORTABLE,
                            file=POSITION,
                            native_field="archived_native_sha256",
                        ),
                        dict(
                            key="stock",
                            label="Archived compact",
                            value=ARCHIVE,
                            file=POSITION,
                            native_field="archived_native_sha256",
                            match=list(accelerated.BINDINGS),
                        ),
                    ],
                )
            ],
        ),
    )
    write(
        directory / "README.md",
        render_markdown(evidence, proof, scores, quality, receipts).encode(),
    )
    return ("stage.csv", PLOT, "stage-figure.json", "figures.json", "README.md")


def render_paired(directory):
    from .screening_figures import generate

    generate(directory / "charts", evidence=directory)
