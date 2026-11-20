"""Verify, score, and chart sealed waveform cancellation predictions."""

import argparse
import csv
from collections import Counter, defaultdict
from io import BytesIO, StringIO
from pathlib import Path
from statistics import median

import matplotlib
import numpy as np

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..variants import pilot_cancellation as pilot
from ..variants.selective_capture import visit_pairs
from . import pilot_cancellation_trial as trial
from .full_v5_check import _sha

matplotlib.use("Agg")

ARMS = trial.STAGES[1:]
LABELS = {
    "original": "Original GLRT",
    "primary": "Four centers",
    "raw_retry": "No subtraction",
    "wider": "Twelve centers",
    "cancelled": "Cancellation",
    "time_shift": "Shifted subtraction",
    "phase_shuffle": "Shuffled subtraction",
}
TRANSFER = ("raw_retry", "time_shift", "phase_shuffle", "cancelled")


def match(candidate, reference):
    return pilot.relationship(candidate["phase"], candidate["cfo_hz"], *trial.location(reference))


def archive_ranks(probe):
    return sorted(
        (c for c in probe["candidates"] if c[trial.ARCHIVE_GATE]),
        key=lambda row: (-row["fractional_margin"], row["candidate_rank"]),
    )


def choice(candidate, archive):
    if candidate is None:
        return dict(state="empty", literal_ranks=[], alias_ranks=[])
    literal, alias = [], []
    for reference in archive:
        relation = match(candidate, reference)
        if relation == "literal":
            literal.append(reference["candidate_rank"])
        elif relation == "alias":
            alias.append(reference["candidate_rank"])
    return dict(
        state="literal" if literal else ("alias_only" if alias else "uncorroborated"),
        literal_ranks=literal,
        alias_ranks=alias,
    )


def lane_counts(probe, result, baseline):
    refs = archive_ranks(probe)
    winner = refs[0]["candidate_rank"] if refs else None
    primary = choice(result["primary"], refs)
    other = choice(result["secondary"], refs)
    literal = set(primary["literal_ranks"] + other["literal_ranks"])
    alias = set(primary["alias_ranks"] + other["alias_ranks"])
    winner_covered = winner is not None and winner in literal
    winner_base = (
        winner is not None and winner in choice(baseline["primary"], refs)["literal_ranks"]
    )
    winner_route = "no_original_winner"
    if refs:
        reference = refs[0]
        signal = [
            r for r in result["base"] + result["retry"] if match(r["pilot"], reference) == "literal"
        ]
        offered_centers = result["centers"][: pilot.BASE_CENTERS] + result["retry_centers"]
        timing = any(
            abs(pilot.difference(center, 0, trial.location(reference)[0], 0)[0]) <= 2
            for center, _ in offered_centers
        )
        if winner_covered:
            winner_route = "emitted"
        elif signal:
            winner_route = (
                "ranked_behind" if any(r["admitted"] for r in signal) else "held_gate_reject"
            )
        else:
            winner_route = "literal_cfo_miss" if timing else "timing_miss"
    raw = next((r["raw"] for r in result["base"] if r["admitted"]), None)
    return dict(
        archive_candidates=len(probe["candidates"]),
        archive_positives=len(refs),
        archive_winner_rank=winner,
        winner_literal=winner_covered,
        winner_alias_only=winner is not None and winner not in literal and winner in alias,
        winner_rescued=winner_covered and not winner_base,
        winner_route=winner_route,
        primary=primary["state"],
        primary_literal_ranks=primary["literal_ranks"],
        secondary=other["state"],
        secondary_literal_ranks=other["literal_ranks"],
        second_with_literal_primary=other["state"] == "literal" and primary["state"] == "literal",
        emitted_on_original_negative=not refs
        and (result["primary"] is not None or result["secondary"] is not None),
        first_phase=(result["primary"] or {}).get("phase"),
        first_cfo_hz=(result["primary"] or {}).get("cfo_hz"),
        second_phase=(result["secondary"] or {}).get("phase"),
        second_cfo_hz=(result["secondary"] or {}).get("cfo_hz"),
        held_removed=result["held_removal_coherent"],
        held_amplitude_ratio=raw["amplitude_ratio"] if raw else None,
        held_phase_error_rad=raw["phase_error_rad"] if raw else None,
        held_fixed_energy_removal=raw["transfer"] if raw else None,
        tried=result["offered"],
        centers=len(result["centers"]),
        retry_centers=len(result["retry_centers"]),
    )


def original_agreement(row, valid, excluded):
    if "failure" in row:
        return False
    status = row["original"]["public"]
    visit = row["visit"]
    if visit in excluded:
        match_keys = ("reason", "iq_sha256", "sample_start", "sample_end", "visit")
        return (
            status["status"] == "invalid_capture"
            and not row["original"]["probes"]
            and all(status[key] == excluded[visit][key] for key in match_keys)
        )
    return status["status"] == "processed" and row["original"]["probes"] == list(valid[visit])


def aggregate(counts):
    total = Counter()
    for row in counts:
        total.update(
            {
                "lanes": 1,
                "archive_positive_lanes": row["archive_winner_rank"] is not None,
                "archive_positive_ranks": row["archive_positives"],
                "tried": row["tried"],
                "primary_literal": row["primary"] == "literal",
                "primary_alias_only": row["primary"] == "alias_only",
                "primary_uncorroborated": row["primary"] == "uncorroborated",
                "second_literal": row["secondary"] == "literal",
                "second_alias_only": row["secondary"] == "alias_only",
                "second_uncorroborated": row["secondary"] == "uncorroborated",
                "second_with_literal_primary": row["second_with_literal_primary"],
                "winner_literal": row["winner_literal"],
                "winner_alias_only": row["winner_alias_only"],
                "winner_rescued": row["winner_rescued"],
                "emitted_on_original_negative": row["emitted_on_original_negative"],
            }
        )
    return dict(total)


def summarize(folder):
    prediction = whole_iq.read(folder / "prediction-lock.json")
    for name, digest in prediction["files"].items():
        whole_iq.checked(folder / name, digest)
    lockfile = folder / "input-lock.json"
    lock = whole_iq.read(lockfile)
    gates, lanes, timings, nulls = [], [], [], []
    for ident, plan in lock["cases"].items():
        prediction = trial.read_receipt(folder / f"{ident}-predictions.json.gz")
        if prediction["input_lock_sha256"] != _sha(lockfile) or prediction["cpu"] != plan["cpu"]:
            raise ValueError("predictions do not belong to this roster and pinned CPU")
        archive = whole_iq.read(whole_iq.checked(Path(plan["archive"]), plan["archive_sha256"]))
        valid = dict(visit_pairs(archive["source"]["probes"]))
        excluded = {r["visit"]: r for r in archive["provenance"]["excluded_windows"]}
        for spec, row in zip(plan["rows"], prediction["rows"], strict=True):
            if any(row[key] != value for key, value in spec.items()):
                raise ValueError("returned visits differ from the planned roster")
            key = dict(
                case=ident, visit=row["visit"], cohort=spec["cohort"], stratum=spec["stratum"]
            )
            agrees = original_agreement(row, valid, excluded)
            gate = dict(
                key,
                original_agrees=agrees,
                original_status=row.get("original", {}).get("public", {}).get("status"),
                failure=row.get("failure"),
            )
            gates.append(gate)
            if "failure" in row:
                continue
            if not all(mode["status"] == gate["original_status"] for mode in row["modes"].values()):
                raise ValueError("candidate stage changed the capture quality gate")
            for time in row["timing"]:
                parts = time.get("parts", ())
                timings.append(
                    dict(
                        key,
                        mode=time["mode"],
                        cpu=plan["cpu"],
                        repeat=time["repeat"],
                        order=time["order"],
                        cpu_ms=time["cpu_ns"] / 1e6,
                        wall_ms=time["wall_ns"] / 1e6,
                        stable=time["stable"],
                        status=gate["original_status"],
                        scout_ms=sum(x["scout"] for x in parts) / 1e6,
                        primary_ms=sum(x["primary"] for x in parts) / 1e6,
                        retry_ms=sum(x["retry"] for x in parts) / 1e6,
                    )
                )
            if row["visit"] not in valid or gate["original_status"] != "processed":
                continue
            for rx, probe in enumerate(valid[row["visit"]]):
                baseline = row["modes"]["primary"]["lanes"][rx]
                modes = row["modes"] | {k: row["controls"][k] for k in TRANSFER[1:-1]}
                for mode, values in modes.items():
                    lanes.append(
                        dict(
                            key,
                            rx=rx,
                            mode=mode,
                            **lane_counts(probe, values["lanes"][rx], baseline),
                        )
                    )
                facts = row["controls"]["diagnostic"]["lanes"][rx]["null_at_primary"]
                nulls.extend(dict(key, rx=rx, mode=mode, **value) for mode, value in facts.items())

    control_rows = trial.read_receipt(folder / "controls.json.gz")
    plants = []
    for row in control_rows:
        expected = row["targets"]
        for mode, out in row["modes"].items():
            candidates = [c for k in ("primary", "secondary") if (c := out[k]) is not None]
            found = []
            for c in candidates:
                match_indices = [
                    i
                    for i, target in enumerate(expected)
                    if pilot.relationship(
                        c["phase"],
                        c["cfo_hz"],
                        target["phase"],
                        target["cfo_hz"],
                    )
                    == "literal"
                ]
                found.append(match_indices[0] if match_indices else None)
            plants.append(
                dict(
                    edge=row["edge"],
                    condition=row["condition"],
                    mode=mode,
                    target_count=len(expected),
                    found=found,
                    false=len(candidates) - len(set(found) - {None}),
                    held_removed=out["held_removal_coherent"],
                )
            )
    return gates, lanes, timings, nulls, plants


def csv_file(path, rows):
    stream = StringIO(newline="")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write(path, stream.getvalue().encode())


def panel_values(gates, lanes, timings):
    clocks = defaultdict(list)
    for t in timings:
        if t["status"] == "processed":
            clocks[t["mode"], t["case"], t["visit"]].append(t["cpu_ms"])
    plots = []
    for mode in trial.STAGES:
        values = [median(times) for (arm, _, _), times in clocks.items() if arm == mode]
        if values:
            plots.append(
                dict(
                    panel="cpu",
                    mode=mode,
                    median=median(values),
                    low=min(values),
                    high=max(values),
                    denominator=len(values),
                )
            )
    for cohort in ("systematic", "targeted"):
        for mode in ARMS:
            data = aggregate(r for r in lanes if r["cohort"] == cohort and r["mode"] == mode)
            plots.append(
                dict(
                    panel="support",
                    mode=mode,
                    cohort=cohort,
                    winner_literal=data.get("winner_literal", 0),
                    winner_rescued=data.get("winner_rescued", 0),
                    second_literal=data.get("second_literal", 0),
                    second_uncorroborated=data.get("second_uncorroborated", 0),
                    denominator=data.get("archive_positive_lanes", 0),
                )
            )
    for mode in TRANSFER:
        values = [
            r["held_removed"] for r in lanes if r["mode"] == mode and r["held_removed"] is not None
        ]
        if values:
            low, high = np.percentile(values, (10, 90))
            plots.append(
                dict(
                    panel="held",
                    mode=mode,
                    median=median(values),
                    low=float(low),
                    high=float(high),
                    denominator=len(values),
                )
            )
    if not gates:
        raise ValueError("empty trial")
    return plots


def chart(folder, plots):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, MaxNLocator, ScalarFormatter

    fig, axes = plt.subplots(2, 2, figsize=(12, 7.3), layout="constrained")
    fig.suptitle("Qin pilot cancellation on saved stereo I/Q", fontsize=17, fontweight="bold")
    ax = axes[0, 0]
    cpu = [p for p in plots if p["panel"] == "cpu"]
    for i, row in enumerate(cpu):
        ax.hlines(i, row["low"], row["high"], color="#8ca8bc", lw=2)
        ax.scatter(row["median"], i, color="#164b6d", zorder=2)
    ax.set(
        yticks=range(len(cpu)),
        yticklabels=[LABELS[r["mode"]] for r in cpu],
        xlabel="CPU ms per valid stereo visit",
        title="Host CPU, median and observed range",
    )
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator((100, 250, 500, 1000, 2500, 5000)))
    ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.invert_yaxis()

    support = [p for p in plots if p["panel"] == "support"]
    ax = axes[0, 1]
    xs = np.arange(len(ARMS))
    for shift, cohort, color in ((-0.2, "systematic", "#164b6d"), (0.2, "targeted", "#df8354")):
        data = [r for r in support if r["cohort"] == cohort]
        weights = [r["winner_literal"] for r in data]
        ax.bar(
            xs + shift,
            weights,
            width=0.37,
            color=color,
            label=f"{cohort} ({data[0]['denominator']})",
        )
    ax.set(
        xticks=xs,
        xticklabels=[LABELS[m] for m in ARMS],
        ylabel="Original winning lanes matched",
        title="Literal winner coverage",
    )
    ax.tick_params(axis="x", labelrotation=16)
    ax.set_ylim(0, 15)
    ax.legend(frameon=False, loc="upper left", ncols=2)

    ax = axes[1, 0]
    for shift, cohort, color in ((-0.2, "systematic", "#164b6d"), (0.2, "targeted", "#df8354")):
        data = [r for r in support if r["cohort"] == cohort]
        weights = [r["second_literal"] for r in data]
        ax.bar(xs + shift, weights, width=0.37, color=color, label=cohort)
    ax.set(
        xticks=xs,
        xticklabels=[LABELS[m] for m in ARMS],
        ylabel="Secondary lanes matched",
        title="Added literal candidates",
    )
    ax.tick_params(axis="x", labelrotation=16)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))

    ax = axes[1, 1]
    held = [p for p in plots if p["panel"] == "held"]
    for i, row in enumerate(held):
        ax.hlines(i, row["low"], row["high"], color="#8ca8bc", lw=2)
        ax.scatter(row["median"], i, color="#164b6d", zorder=2)
    ax.axvline(0, color="#c2c9ce", lw=1)
    ax.set(
        yticks=range(len(held)),
        yticklabels=[LABELS[r["mode"]] for r in held],
        xlabel="Fraction of normalized held power removed",
        title="Median and 10th–90th percentiles",
    )
    ax.invert_yaxis()
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
    for extension in ("png", "pdf"):
        output = BytesIO()
        fig.savefig(
            output,
            format=extension,
            dpi=160,
            metadata={"CreationDate": None} if extension == "pdf" else None,
        )
        write(folder / f"stage.{extension}", output.getvalue())
    plt.close(fig)


def publish(folder):
    gates, lanes, timings, nulls, plants = summarize(folder)
    overlap = trial.read_receipt(folder / "overlap.json.gz")
    overlap_protocol = folder / "OVERLAP.md"
    if not overlap_protocol.exists():
        write(overlap_protocol, (trial.REPORT / overlap_protocol.name).read_bytes())
    plots = panel_values(gates, lanes, timings)
    chart(folder, plots)
    csv_file(folder / "stage.csv", plots)
    csv_file(folder / "lanes.csv", lanes)
    csv_file(folder / "timings.csv", timings)
    stats = {
        cohort: {
            mode: aggregate(r for r in lanes if r["cohort"] == cohort and r["mode"] == mode)
            for mode in (*ARMS, *TRANSFER[1:-1])
        }
        for cohort in ("systematic", "targeted")
    }
    stats.update(
        gates=gates,
        nulls=nulls,
        plants=plants,
        plot_values=plots,
        unstable_repeats=sum(not t["stable"] for t in timings),
        overlap={
            cohort: {
                mode: {
                    "pairs": sum(r.get("cohort") == cohort and r["mode"] == mode for r in overlap),
                    "supported": sum(
                        r.get("cohort") == cohort and r["mode"] == mode and r["supported"]
                        for r in overlap
                    ),
                }
                for mode in ("original", "missed_winner", *ARMS, *TRANSFER[1:-1])
            }
            for cohort in ("systematic", "targeted")
        },
    )
    save_json(folder / "qualification.json", stats)
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="qin-pilot-cancellation",
            title="Qin pilot cancellation on saved stereo I/Q",
            sample=f"{len(gates)} gate-balanced and collision-targeted visits, three producers",
            boundary="Resident host CI16 through stereo detection and held waveform checks",
            note="Position accuracy is unmeasured. Winner and secondary matches use literal CFO.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="stage-figure-lock.json",
        ),
    )
    names = (
        "stage.png",
        "stage.pdf",
        "stage.csv",
        "stage-figure.json",
        "lanes.csv",
        "timings.csv",
        "qualification.json",
        "prediction-lock.json",
        "overlap.json.gz",
        "OVERLAP.md",
    )
    save_json(
        folder / "stage-figure-lock.json",
        dict(
            files={name: _sha(folder / name) for name in names},
            publisher_sha256=_sha(Path(__file__)),
            overlap_sha256=_sha(Path(__file__).with_name("pilot_cancellation_overlap.py")),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, nargs="?", default=trial.REPORT)
    args = parser.parse_args()
    publish(local_output(args.folder))
