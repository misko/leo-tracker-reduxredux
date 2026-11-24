"""Render paired runtime and all-assigned position-error distributions."""

from collections import Counter
from collections.abc import Mapping
import csv
import math
from pathlib import Path


ROLES = ("installed", "successor")
NAMES = {"installed": "Installed ALGO08v3", "successor": "Successor"}
COLORS = {"installed": "#176084", "successor": "#af451d"}
OUTCOMES = {"complete", "withheld", "solver_failed", "worker_failed", "invalid_publication"}
COLUMNS = {
    "case", "first", "release_100", "algorithm", "outcome", "elapsed_s", "cpu_s",
    "c0_error_km", "fitted_c_error_km", "c0_fix", "fitted_c_fix",
}


def _measure(value, *, positive):
    if not value:
        if positive:
            raise ValueError("Missing through-exit clock")
        return None
    number = float(value)
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        raise ValueError(f"Invalid scored measurement {value!r}")
    return number


def _fix(value):
    if value.lower() in {"1", "true"}:
        return True
    if value.lower() in {"0", "false"}:
        return False
    raise ValueError(f"Invalid scored fix flag {value!r}")


def _read_pairs(path, enrollment):
    pairs = {}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if not COLUMNS <= set(fields) or len(fields) != len(set(fields)):
            raise ValueError("Missing or duplicated scored CSV columns")
        for line, raw in enumerate(reader, start=2):
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"Ragged scored CSV row {line}")
            case, first, release, role, outcome = (raw[key].strip() for key in
                                                   ("case", "first", "release_100", "algorithm", "outcome"))
            if (case not in enrollment or role not in ROLES or first not in ROLES or outcome not in OUTCOMES
                    or release != str(int(enrollment[case]))):
                raise ValueError(f"Unenrolled case or invalid scored role, outcome or subset on row {line}")
            pair = pairs.setdefault(case, dict(first=first, release_100=release == "1"))
            if role in pair or pair["first"] != first:
                raise ValueError(f"Duplicate role or inconsistent first launch for {case}")
            row = {key: _measure(raw[key].strip(), positive=True) for key in ("elapsed_s", "cpu_s")}
            row["outcome"] = outcome
            for arm in ("c0", "fitted_c"):
                error = _measure(raw[arm+"_error_km"].strip(), positive=False)
                fix = _fix(raw[arm+"_fix"].strip())
                if fix != (outcome == "complete"):
                    raise ValueError(f"Position fix disagrees with terminal outcome for {case}/{role}/{arm}")
                if error is not None and not fix:
                    raise ValueError(f"Position error without a fix for {case}/{role}/{arm}")
                row.update({arm+"_error_km": error, arm+"_fix": fix})
            pair[role] = row
    if set(pairs) != set(enrollment) or any(not all(role in pair for role in ROLES) for pair in pairs.values()):
        raise ValueError("Both scored roles are required for every assigned recording")
    return [pairs[case] for case in sorted(pairs)]


def _percent_ecdf(values, denominator, left, right):
    counts = Counter(values)
    x, y = [left], [0.0]
    total = 0
    for value in sorted(counts):
        total += counts[value]
        x.append(value)
        y.append(100*total/denominator)
    return [*x, right], [*y, y[-1]]


def _plot_curves(ax, series, *, mode):
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter, PercentFormatter

    all_values = [value for _, _, values, _ in series for value in values]
    if mode == "error":
        left, right = 0, max(.1, max(all_values, default=0)*1.12)
        ax.set_xscale("symlog", linthresh=.1)
    else:
        extent = all_values + ([1.0] if mode == "speedup" else [])
        left, right = min(extent, default=1.0)/1.12, max(extent, default=1.0)*1.12
        ax.set_xscale("log")
    ax.set_xlim(left, right)
    ax.set_ylim(0, 103)
    ax.set_yticks((0, 25, 50, 75, 100))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.grid(axis="y", color="#dbe1e5", linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)
    if mode == "speedup":
        ax.axvline(1, color="#666", linestyle=":", linewidth=1, zorder=1)
        ax.xaxis.set_major_locator(LogLocator(base=2, numticks=7))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}×"))
        ax.xaxis.set_minor_formatter(NullFormatter())
    for i, (name, role, values, denominator) in enumerate(series):
        x, y = _percent_ecdf(values, denominator, left, right) if denominator else ([], [])
        ax.step(x, y, where="post", color=COLORS[role], linestyle=("-" if i == 0 else "--"),
                linewidth=1.8, label=name, zorder=2+i)
    if not all_values:
        ax.text(.5, .56, "No scored errors" if mode == "error" else "No timed pairs",
                transform=ax.transAxes, ha="center", va="center", fontsize=9)
    ax.legend(loc="upper left", bbox_to_anchor=(-.03, -.21), frameon=False, fontsize=8,
              borderaxespad=0, labelspacing=.5)


def _runtime_series(pairs, metric):
    return [(f"{NAMES[role]}\n{len(pairs)} paired exits", role, [p[role][metric] for p in pairs], len(pairs))
            for role in ROLES]


def _order_series(pairs, metric):
    series = []
    for first in ROLES:
        ratios = [p["installed"][metric]/p["successor"][metric] for p in pairs if p["first"] == first]
        if any(not math.isfinite(ratio) or ratio <= 0 for ratio in ratios):
            raise ValueError("Non-finite matched speedup")
        series.append((f"{NAMES[first]} first\n{len(ratios)} paired exits", first, ratios, len(ratios)))
    return series


def _error_series(pairs, arm):
    series = []
    for role in ROLES:
        rows = [p[role] for p in pairs]
        errors = [row[arm+"_error_km"] for row in rows if row[arm+"_error_km"] is not None]
        fixes = sum(row[arm+"_fix"] for row in rows)
        series.append((f"{NAMES[role]}\n{len(errors)} scored, {fixes} fixes of {len(pairs)} assigned",
                       role, errors, len(pairs)))
    return series


def _figure(pairs, *, runtime):
    from matplotlib.figure import Figure

    columns = 4 if runtime else 2
    figure = Figure(figsize=(14.3 if runtime else 10.2, 8.4), dpi=150, layout="constrained")
    title = ("DS30 runtime distributions" if runtime else "DS30 position error across assigned recordings")
    figure.suptitle(title, fontsize=19, fontweight="bold")
    historical = [pair for pair in pairs if pair["release_100"]]
    for row, (cohort, subset) in zip(figure.subfigures(nrows=2, ncols=1), (
        ("Full DS30", pairs), ("Historical release subset", historical)
    ), strict=True):
        row.suptitle(f"{cohort} · {len(subset)} assigned recordings", fontsize=13, fontweight="bold")
        axes = row.subplots(nrows=1, ncols=columns)
        if runtime:
            for ax, metric, title in zip(axes[:2], ("elapsed_s", "cpu_s"), ("Wall time", "CPU time"), strict=True):
                _plot_curves(ax, _runtime_series(subset, metric), mode="runtime")
                ax.set(title=f"{title} through exit", xlabel="Seconds (log scale)", ylabel="Share of timed pairs")
            for ax, metric, title in zip(axes[2:], ("elapsed_s", "cpu_s"), ("Wall speedup", "CPU speedup"), strict=True):
                _plot_curves(ax, _order_series(subset, metric), mode="speedup")
                ax.set(title=f"{title} by launch order", xlabel="Installed / successor (log scale)",
                       ylabel="Share of timed pairs in order")
        else:
            for ax, arm, title in zip(axes, ("c0", "fitted_c"), ("Fixed c = 0", "Fitted c"), strict=True):
                _plot_curves(ax, _error_series(subset, arm), mode="error")
                ax.set(title=title, xlabel="Horizontal error (km, log scale above 0.1 km)",
                       ylabel="Share of assigned recordings")
    return figure


def _write_figures(pairs, output_dir):
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    runtime, error = _figure(pairs, runtime=True), _figure(pairs, runtime=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = output_dir/"runtime.png", output_dir/"position-error.png"
    for figure, path in zip((runtime, error), paths, strict=True):
        FigureCanvasAgg(figure).print_png(path)
    return paths


def _histogram_edges(values, *, runtime):
    from numpy import geomspace, linspace, unique

    if runtime:
        low, high = min(values, default=1.), max(values, default=1.)
        if low == high:
            low, high = low / 1.12, high * 1.12
        return unique(geomspace(low, high, 23))

    # Keep exact zero and small errors visible before switching to logarithmic bins.
    linear = linspace(0., .1, 5)
    high = max(.1, max(values, default=0.))
    return linear if high == .1 else unique([*linear, *geomspace(.1, high, 19)[1:]])


def _histogram_series(pairs, metric, *, runtime):
    for role in ROLES:
        rows = [pair[role] for pair in pairs]
        if runtime:
            yield role, [row[metric] for row in rows], f"{NAMES[role]} · {len(rows)} timed exits"
        else:
            errors = [row[metric + "_error_km"] for row in rows if row[metric + "_error_km"] is not None]
            counts = Counter(row["outcome"] for row in rows)
            failed = len(rows) - counts["complete"] - counts["withheld"]
            unscored = counts["complete"] - len(errors)
            label = (f"{NAMES[role]} · {len(errors)}/{len(rows)} scored\n"
                     f"{counts['withheld']} withheld · {failed} failed · {unscored} unscored fixes")
            yield role, errors, label


def _histogram_figure(pairs, *, runtime):
    from matplotlib.colors import to_rgba
    from matplotlib.figure import Figure
    from matplotlib.ticker import MaxNLocator
    from numpy import histogram

    metrics = (("elapsed_s", "Wall time through exit"), ("cpu_s", "CPU time through exit")) if runtime else (
        ("c0", "Fixed c = 0"), ("fitted_c", "Fitted c"))
    figure = Figure(figsize=(10.2, 8.4), dpi=150, layout="constrained")
    figure.suptitle("DS30 runtime histograms" if runtime else "DS30 horizontal error histograms",
                    fontsize=19, fontweight="bold")
    edges = {metric: _histogram_edges([value for _, values, _ in _histogram_series(pairs, metric, runtime=runtime)
                                       for value in values], runtime=runtime) for metric, _ in metrics}
    historical = [pair for pair in pairs if pair["release_100"]]
    for row, (cohort, subset) in zip(figure.subfigures(nrows=2, ncols=1),
                                     (("Full DS30", pairs), ("Historical release subset", historical)), strict=True):
        row.suptitle(f"{cohort} · {len(subset)} assigned recordings", fontsize=13, fontweight="bold")
        for ax, (metric, title) in zip(row.subplots(nrows=1, ncols=2), metrics, strict=True):
            included = 0
            for role, values, label in _histogram_series(subset, metric, runtime=runtime):
                counts, _ = histogram(values, bins=edges[metric])
                included += len(values)
                ax.stairs(counts, edges[metric], label=label, fill=True, edgecolor=COLORS[role],
                          facecolor=to_rgba(COLORS[role], .16), linewidth=1.4,
                          linestyle="-" if role == "installed" else "--")
            if runtime:
                ax.set_xscale("log")
                ax.set(xlabel="Seconds (log scale)", ylabel="Timed exits per bin")
            else:
                ax.set_xscale("symlog", linthresh=.1)
                ax.set(xlabel="Horizontal error (km, log scale above 0.1 km)", ylabel="Scored fixes per bin")
            ax.set(title=title, xlim=(edges[metric][0], edges[metric][-1]), ylim=(0, None))
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax.grid(axis="y", color="#dbe1e5", linewidth=.7)
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
            ax.tick_params(labelsize=8)
            ax.legend(loc="upper left", bbox_to_anchor=(0, -.22), frameon=False, fontsize=8, borderaxespad=0)
            if not included:
                ax.text(.5, .55, "No timed exits" if runtime else "No scored fixes",
                        transform=ax.transAxes, ha="center", va="center", fontsize=9)
    return figure


def _write_histograms(pairs, output_dir):
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    for runtime, name in ((True, "runtime-histogram.png"), (False, "position-error-histogram.png")):
        FigureCanvasAgg(_histogram_figure(pairs, runtime=runtime)).print_png(output_dir / name)


def paired_speed_errors(pairs, arms):
    """Return wall speedup and largest signed error change across the requested calibration arms."""
    keys = [arm + "_error_km" for arm in arms]
    return [(base["elapsed_s"] / candidate["elapsed_s"], max(candidate[k] - base[k] for k in keys))
            for base, candidate in pairs if all(base[k] is not None and candidate[k] is not None for k in keys)]


def paired_change_figure(pairs, title):
    from matplotlib.figure import Figure
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

    panels = [(name, paired_speed_errors(pairs, (arm,))) for name, arm in
              (("Fixed c = 0", "c0"), ("Fitted c", "fitted_c"))]
    speeds = [1., 2.] + [x for _, points in panels for x, _ in points]
    limit = max([.1] + [abs(y) for _, points in panels for _, y in points]) * 1.15
    xmin, xmax = min(speeds) / 1.09, max(speeds) * 1.09
    figure = Figure(figsize=(10.5, 5.5), dpi=145, layout="constrained")
    figure.suptitle(title, fontsize=16, fontweight="bold")
    axes = figure.subplots(1, 2, sharex=True, sharey=True)
    for ax, (name, points) in zip(axes, panels, strict=True):
        ax.set_xscale("log", base=2)
        ax.set_yscale("symlog", linthresh=.1)
        ax.set(xlim=(xmin, xmax), ylim=(-limit, limit), xlabel="ALGO08v3 / candidate wall time",
               title=f"{name}  ·  {len(points)}/{len(pairs)} pairs with two scored fixes")
        ax.axhline(0, linewidth=1, color="#415360")
        ax.axvline(2, linewidth=1, linestyle="--", color="#415360")
        ax.fill_between([2, xmax], -limit, 0, color="#e1f2eb", zorder=0)
        ax.xaxis.set_major_locator(LogLocator(base=2, subs=(1, 1.5), numticks=12))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}×"))
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.18)
        ax.scatter([x for x, _ in points], [y for _, y in points], s=26, alpha=.66, color="#215675",
                   edgecolor="white", linewidth=.4, zorder=3)
        if not points:
            ax.text(.5, .6, "No pairs with two scored fixes", ha="center", transform=ax.transAxes)
    axes[0].set_ylabel("Candidate minus ALGO08v3 horizontal error (km)")
    figure.supxlabel("Shading marks recordings at least 2× faster with equal or smaller error.", fontsize=10)
    return figure


def render_distribution_figures(
    scored_csv: Path, output_dir: Path, *, enrollment: Mapping[str, bool],
) -> tuple[Path, Path]:
    """Write the ECDFs and companion histograms using the exact sealed enrollment."""
    if (len(enrollment) != 455 or any(type(flag) is not bool for flag in enrollment.values())
            or sum(enrollment.values()) != 100):
        raise ValueError("Full DS30 figures require the exact 455-case and historical 100-case enrollment")
    pairs = _read_pairs(scored_csv, enrollment)
    ecdfs = _write_figures(pairs, output_dir)
    _write_histograms(pairs, output_dir)
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    change = paired_change_figure([(p["installed"], p["successor"]) for p in pairs],
                                  "Runtime and position error on the same DS30 recordings")
    FigureCanvasAgg(change).print_png(output_dir / "paired-speed-and-error.png")
    return ecdfs
