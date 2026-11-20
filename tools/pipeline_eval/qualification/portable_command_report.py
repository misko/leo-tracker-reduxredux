"""Publish geographic and runtime figures from the sealed DS29 command comparison."""

import csv

from ..__main__ import save_json, write
from ..scoring import ARMS, ROLES
from . import portable_command as study
from . import portable_field_scores as checks
from .prefix_figures import csv_file
from .screening_figures import generate

CHART = "portable-command-ds29-0082"
LABEL = {
    study.PORTABLE: "Portable command",
    study.ARCHIVED: "Archived factors, compact fit",
    "baseline": "v5 no-repair",
    "selective-gap": "v5 selective gap",
    "omitted-track-one": "v5 omitted track one",
    "omitted-tracks": "v5 omitted tracks",
}


def stage_rows(output, evidence, scores):
    stage = []

    def row(panel, series, value, unit, arm=None, visit=None, fraction=None):
        if value is not None:
            stage.append(
                dict(
                    panel=panel,
                    series=series,
                    value=value,
                    unit=unit,
                    arm=arm,
                    visit=visit,
                    fraction=fraction,
                )
            )

    for name, path in (
        ("Portable", output / "raw-visits.csv"),
        ("Historical exact", study.HISTORICAL / "timing.csv"),
    ):
        if not path.is_file():
            continue
        with path.open(newline="") as stream:
            rows = [item for item in csv.DictReader(stream) if item["status"] == "processed"]
        for axis in ("CPU", "wall"):
            values = sorted(
                (float(item[axis.lower() + "_ms"]), int(item["visit"])) for item in rows
            )
            for i, (ms, visit) in enumerate(values, start=1):
                row("visit", f"{name} {axis}", ms, "ms", visit=visit, fraction=i / len(values))

    row("threshold", "Visit budget", 20, "ms")
    for name, seconds in (
        ("Signed RF delivery span", evidence["recorded_delivery_span_s"]),
        ("Portable raw", evidence["raw"].get("wall_s")),
        ("Portable compact fit", fit_wall(evidence["fit"])),
        ("Portable whole command", evidence["whole_command"]["elapsed_s"]),
        ("Historical exact raw", evidence["historical_raw"]["wall_s"]),
        ("Historical exact compact fit", evidence["historical_fits"]["actual"]["wall_s"]),
        ("Archived-factor compact fit", evidence["historical_fits"]["archive"]["wall_s"]),
    ):
        row("elapsed", name, seconds, "s")
    for score in scores:
        method, arm = LABEL[score["method"]], score["arm"]
        row("rf", method, score["rf_rms_hz"], "Hz", arm=arm)
        row("objective", method, score["frequency_score"], "score", arm=arm)
    return stage


def plot(stage, path):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(11.7, 8.0), layout="constrained")
    visit, elapsed, rf, objective = axes.ravel()
    for name, color in (("Portable", "#1b766a"), ("Historical exact", "#7a4ba8")):
        for clock, line in (("CPU", "-"), ("wall", "--")):
            series = f"{name} {clock}"
            points = [r for r in stage if r["panel"] == "visit" and r["series"] == series]
            if points:
                visit.step(
                    [r["value"] for r in points],
                    [r["fraction"] for r in points],
                    where="post",
                    color=color,
                    ls=line,
                    label=series,
                )
    (budget,) = [r["value"] for r in stage if r["panel"] == "threshold"]
    visit.axvline(budget, ls=":", color="0.3", label="20 ms visit budget")
    visit.set(
        xscale="log",
        xlabel="Detector duration per valid visit (ms)",
        ylabel="Fraction at or below duration",
        ylim=(0, 1.02),
    )
    visit.legend(loc="lower right", frameon=False, fontsize=8)
    times = [r for r in stage if r["panel"] == "elapsed"]
    elapsed.barh([r["series"] for r in times], [r["value"] for r in times], color="#55786f")
    elapsed.invert_yaxis()
    elapsed.set_xlabel("Elapsed wall time (s)")
    for axis, key, unit in (
        (rf, "rf", "Conditional RF RMS (Hz)"),
        (objective, "objective", "Frequency score"),
    ):
        for i, (method, marker) in enumerate(
            zip(LABEL.values(), ("o", "s", "D", "^", "x", "+"), strict=True)
        ):
            points = [r for r in stage if r["panel"] == key and r["series"] == method]
            if points:
                axis.scatter(
                    [ARMS.index(r["arm"]) + (i - 2) * 0.054 for r in points],
                    [r["value"] for r in points],
                    marker=marker,
                    label=method,
                )
        axis.set(xticks=(0, 1), xticklabels=("c = 0", "Fitted c"), xlim=(-0.3, 1.3), ylabel=unit)
        axis.legend(frameon=False, fontsize=7)
    fig.suptitle("DS29-0082 portable receiver timing and RF fit")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def number(value, digits=2):
    return "Unavailable" if value is None else f"{value:,.{digits}f}"


def fit_wall(fit):
    service = fit.get("service") or {}
    return service.get("service_wall_s", service.get("wall_s"))


def markdown(evidence, proof, scores, quality):
    raw, fit, external = (evidence[key] for key in ("raw", "fit", "whole_command"))
    hist, old_fit = evidence["historical_raw"], evidence["historical_fits"]["actual"]
    ranks, gates = proof["rank_counts"], proof["gate_counts"]
    exact = proof["exact_probes"] == proof["measured_probes"] and raw["complete"]
    parity = "passed" if exact else "failed" if raw["complete"] else "has partial coverage"
    exclusions = "matched" if proof["exclusion_rows_match"] else "differed"
    ambiguous = proof["physical_neighbourhood"]["ambiguous_probes"]
    primary = quality["primary"]
    decision = (
        "pass"
        if primary["within_5_percent"]
        else "fail"
        if primary["within_5_percent"] is False
        else "unavailable"
    )
    wide = (
        "pass"
        if primary["within_10_percent"]
        else "fail"
        if primary["within_10_percent"] is False
        else "unavailable"
    )
    lines = [
        "# Portable saved-recording receiver on DS29-0082",
        "",
        f"The command authenticated **{raw['completed']:,} / {raw['scheduled']:,} visits** on the "
        f"upper-edge recording and reached `{evidence['status']}` "
        f"in **{external['elapsed_s']:.2f} s**. Exact native probe parity {parity}. "
        "Both-arm geographic "
        f"targets versus v5 no-repair were **{decision} at 5%** and **{wide} at 10%**. "
        "[Protocol](PROTOCOL.md) · [Sealed prediction comparison](prediction-lock.json) · "
        "[Score lock](score-lock.json) · [Report seal](report-seal.json)",
        "",
        "## Geographic and RF outcomes",
        "",
        "| Fit | Error at `c = 0` (km) | Error with fitted `c` (km) | "
        "RF RMS, zero / fitted (Hz) | Frequency score, zero / fitted |",
        "|---|---:|---:|---:|---:|",
    ]
    for method, name in LABEL.items():
        a, b = [
            next(r for r in scores if r["method"] == method and r["arm"] == arm) for arm in ARMS
        ]
        cells = [
            number(r["error_km"], 5) if r["error_km"] is not None else r["status"] for r in (a, b)
        ]
        cells.extend(
            " / ".join(number(r[key], 5) for r in (a, b))
            for key in ("rf_rms_hz", "frequency_score")
        )
        lines.append("| " + " | ".join([name, *cells]) + " |")
    lines.extend(
        [
            "",
            "| v5 control | Relative error, `c = 0` | Relative error, fitted `c` |",
            "|---|---:|---:|",
        ]
    )
    for role in ROLES:
        ratios = quality["comparison_by_control"][role]
        cells = []
        for arm in ARMS:
            values = ratios[arm]
            change = values["degradation_percent"]
            if change is None:
                cells.append("Unavailable")
            else:
                decisions = "/".join(
                    "pass" if values[f"within_{n}_percent"] else "fail" for n in (5, 10)
                )
                cells.append(f"{change:+.2f}% ({decisions})")
        lines.append("| " + " | ".join([LABEL[role], *cells]) + " |")
    lines.extend(
        [
            "",
            "The paired decisions are for the 5% and 10% degradation ceilings respectively. "
            "[Numeric position and RF data](scores.csv) · "
            "[Original v5 execution receipts](original-v5-receipts.json) · "
            f"[`c = 0` chart](charts/c0/{CHART}.png) · "
            f"[Fitted `c` chart](charts/fitted_c/{CHART}.png)",
        ]
    )
    for method, key in ((study.PORTABLE, checks.PORTABLE), (study.ARCHIVED, checks.ARCHIVE)):
        a = quality["fitted_c_minus_c0"][key]
        lines.extend(
            [
                "",
                f"For the {LABEL[method].lower()}, fitted `c` moved the endpoint "
                f"**{number(a['endpoint_separation_km'], 5)} km**, changed survey error by "
                f"**{number(a['error_km'], 5)} km**, changed conditional RF RMS by "
                f"**{number(a['rf_rms_hz'], 5)} Hz**, and changed the frequency score by "
                f"**{number(a['frequency_score'], 5)}**. The two arms shared factors, "
                "candidate sets, priors, causal catalogue, tile and search budget.",
            ]
        )
    comparison = evidence["archive_fit_comparison"]
    separation = comparison.get("paired_endpoint_separation_km", {})
    a, b = (separation.get(arm) for arm in ARMS)
    if a is not None and b is not None:
        lines.extend(
            [
                "",
                f"The fresh and independently produced archived-factor endpoints were "
                f"**{number(a * 1e6, 5)} mm** apart at `c = 0` and "
                f"**{number(b * 1e6, 5)} mm** apart with fitted `c`. "
                "The arm and frequency score fields were compared at full precision. "
                "[Compact fits and requests](command-evidence.json)",
            ]
        )

    lines.extend(
        [
            "",
            "## Detector parity",
            "",
            f"The command authenticated **{raw['completed_chunks']:,} signed chunks** and "
            f"**{raw['invalid']:,} exclusions**. Exclusions {exclusions} in compared coverage. "
            f"Delivery clocks differed for {len(proof['delivery_clock_mismatches']):,} visits. "
            f"The ordered output had **{proof['exact_probes']:,} exact** and "
            f"**{proof['different_probes']:,} differing** shared probe records. "
            f"There were **{proof['measured_candidates']:,} fresh** and "
            f"**{proof['archived_candidates']:,} archived** candidates, with "
            f"{ranks['unmatched_measured']:,} / {ranks['unmatched_archived']:,} unmatched under "
            f"the physical tolerance. The comparison found "
            f"{ranks['matched_rank_changed']:,} matched rank changes and "
            f"{gates['matched_gate_changed']:,} matched gate changes. "
            f"Fresh and archived outputs had {gates['measured']:,} / {gates['archived']:,} passes "
            f"and {gates['measured_probes']:,} / {gates['archived_probes']:,} positive probes. "
            f"{ambiguous:,} probes admitted more than one physical matching edge. "
            "[Exact per-field and gate audit](native-parity.json) · "
            "[Changed rows](native-differences.jsonl.gz) · "
            "[Ambiguous peaks](equivalent-peaks.jsonl.gz) · "
            "[C candidate attempts and near-tie flags](portable-attempts.jsonl.gz)",
        ]
    )
    maxima = proof["maximum_matched_peak_delta"]
    if raw["complete"] and maxima:
        attempts = evidence["attempts"]["attempt_counts"]["published"]
        ties = attempts.get("equivalent_acquisition_tie", 0)
        epoch = maxima.get("fractional_epoch_offset_samples", 0)
        cfo = maxima.get("fractional_tracking_cfo_hz", 0)
        margin = maxima.get("fractional_margin", 0)
        clocks = "differed" if proof["schema_and_clock_fields_changed"] else "matched exactly"
        order = "matched exactly" if proof["probe_order_exact"] else "differed"
        lines.extend(
            [
                "",
                f"Maximum matched drift was {epoch:.3g} sample, {cfo:.3g} Hz CFO, and "
                f"{margin:.3g} fractional margin. The clock and sample-counter fields {clocks}. "
                f"Published probe order {order}. The published C groups recorded "
                f"{ties:,} equivalent acquisition tie flags "
                f"and {attempts.get('conditioned_tie', 0):,} conditioned tie flags. "
                "[Native parity](native-parity.json)",
            ]
        )
    lines.extend(
        [
            "",
            "## Host measurements",
            "",
            "| Boundary | Portable CPUs 3–7 | Historical exact replay |",
            "|---|---:|---:|",
        ]
    )
    old_cpu = hist["valid_detector"]["cpu_ms"]
    fit_service = fit.get("service") or {}
    for label, live, old in (
        ("Raw elapsed (s)", raw["wall_s"], hist["wall_s"]),
        (
            "Detector CPU across valid visits (s)",
            raw["detector_cpu_s"],
            old_cpu["n"] * old_cpu["mean"] / 1000,
        ),
        ("Raw worker cgroup CPU (s)", raw["raw_worker_cpu_s"], hist["completed_worker_cpu_s"]),
        (
            "Raw worker charged peak (MiB)",
            mib(raw["largest_worker_peak_bytes"]),
            mib(hist["largest_worker_peak_bytes"]),
        ),
        (
            "Raw worker process RSS (MiB)",
            mib(raw["largest_worker_rss_kib"], 2**10),
            mib(hist["largest_worker_process_rss_kib"], 2**10),
        ),
        ("Compact fit elapsed (s)", fit_wall(fit), old_fit["wall_s"]),
        (
            "Compact service cgroup CPU (s)",
            cpu_accounted(fit_service),
            old_fit["end"]["cpu.stat.usage_usec"] / 1e6,
        ),
        (
            "Compact fit charged peak (MiB)",
            mib(fit.get("memory_peak_bytes")),
            mib(old_fit["end"]["memory.peak"]),
        ),
        ("Full command elapsed, through exit (s)", external["elapsed_s"], None),
        ("Command supervisor peak RSS (MiB)", mib(external["supervisor_rss_kib"], 2**10), None),
    ):
        lines.append(f"| {label} | {number(live)} | {number(old)} |")
    for name in ("cpu_ms", "wall_ms"):
        label = "CPU" if name == "cpu_ms" else "wall"
        live, old = raw["per_valid_visit"][name], hist["valid_detector"][name]
        for key in ("p50", "p95", "p99", "max"):
            lines.append(
                f"| Detector {label} {key} per valid visit (ms) | "
                f"{number(live[key])} | {number(old[key])} |"
            )
        lines.append(
            f"| Valid visits at or under 20 ms detector {label} | "
            f"{live['within_20_ms']:,} / {live['n']:,} | {old['within_20']:,} / {old['n']:,} |"
        )
    lines.extend(
        [
            "",
            f"Signed delivery spanned **{evidence['recorded_delivery_span_s']:.3f} s**, "
            "including exclusions. "
            f"Valid windows account for **{raw['valid'] * 0.02:.2f} s** of detector exposure. "
            "Each service had a 512 MiB memory limit and zero swap. The external clock includes "
            "startup, build, raw replay, factor assembly, fitting and sealing. Its RSS covers the "
            "supervisor and local subprocesses. The service receipts measure detached workers. "
            "The earlier exact replay used eight workers on CPUs 0, 1, 4–7, 20 and 21. This single "
            "run supplies absolute timing on a shared host. "
            "[Whole command clock](whole-command.time) · "
            "[Timing CSV](stage.csv) · [Per-visit timings](raw-visits.csv)",
            "",
            "![DS29 detector, position-service and RF measurements](stage.png)",
            "",
            "## Reproduce",
            "",
            "```bash",
            ".venv/bin/python -B -m tools.pipeline_eval.portable_receiver --case DS29-0082 \\",
            "  --out /var/tmp/ds29-portable-full --cpus 3 4 5 6 7 "
            "--raw-limit 600 --position-limit 180",
            "```",
            "",
            "The same command accepts `--input` with `--input-sha256` for an authenticated "
            "saved-recording locator. The first attempt stopped before decoding because the "
            "archive interpreter lacked a reporting dependency. Reporting imports now stay "
            "in the supervisor. "
            "[Public receiver command](../../../../tools/pipeline_eval/portable_receiver.py)",
            "",
        ]
    )
    return "\n".join(lines)


def mib(value, divisor=2**20):
    return None if value is None else value / divisor


def cpu_accounted(service):
    value = (service.get("systemd") or {}).get("CPUUsageNSec")
    return int(value) / 1e9 if value else None


def publish(output, scores, quality):
    evidence = study.read(output / "command-evidence.json")
    proof = study.read(output / "native-parity.json")
    stage = stage_rows(output, evidence, scores)
    csv_file(output / "stage.csv", stage)
    plot(stage, output / "stage.png")
    save_json(
        output / "stage-figure.json",
        dict(
            version=1,
            id=CHART + "-stages",
            title="Portable receiver timing and RF fit",
            sample="Complete signed DS29-0082 upper-edge recording",
            image="stage.png",
            csv="stage.csv",
            boundary="Detector visits, services, end-to-end command, and frequency diagnostics",
            note="The earlier exact replay used a different CPU roster and host interval.",
            seal="score-lock.json",
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id=CHART,
                    method=study.PORTABLE,
                    scope="roof",
                    cases=[study.CASE],
                    seal="score-lock.json",
                    title="Portable receiver from DS29-0082 saved I/Q",
                    caption="Fresh portable C factors, independent archived-factor compact fit and "
                    "four original v5 roles. Same causal catalogue, 25 km tile and survey.",
                    provenance=["prediction-lock.json", "original-v5-receipts.json", "scores.csv"],
                    series=[
                        dict(
                            key="one",
                            label="Portable command",
                            value=study.PORTABLE,
                            file=study.POSITION,
                            native_field="archived_native_sha256",
                        ),
                        dict(
                            key="stock",
                            label="Archived compact",
                            value=study.ARCHIVED,
                            file=study.POSITION,
                            native_field="archived_native_sha256",
                            match=list(study.controls.BINDINGS),
                        ),
                    ],
                )
            ],
        ),
    )
    write(output / "README.md", markdown(evidence, proof, scores, quality).encode())
    return "stage.csv", "stage.png", "stage-figure.json", "figures.json", "README.md"


def render(output):
    generate(output / "charts", evidence=output)
