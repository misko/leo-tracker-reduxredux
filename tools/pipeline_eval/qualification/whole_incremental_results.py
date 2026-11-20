"""Seal actual incremental-rescue whole-IQ work, then score matched positions."""

import argparse
import gzip
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from statistics import mean, median

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS
from . import diagnostic_whole_results as comparison
from . import frontier_whole_replay_results as traces
from . import whole_band_results as complete
from . import whole_center_union as parent
from . import whole_incremental_trial as trial
from .exact_wide_iq_results import detector_rows, timing_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .oracle_start import target_matches
from .phase_support_results import pack
from .prefix_figures import csv_file
from .screening_figures import generate
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
METHOD = {"stock": parent.BASELINE, "full_fifth": parent.METHOD, "incremental": trial.METHOD}
PROBES = "probe-audit.json"
VISITS = "visits.jsonl.gz"
POS = "positions.jsonl.gz"
RESOURCE = "resources.json"


def selected(candidates):
    return max(
        (p for p in candidates if p["passed_fractional_margin_gate"] is True),
        default=None,
        key=lambda p: (p["fractional_margin"], -p["candidate_rank"]),
    )


def compare_lane(stock, fifth, rescue):
    before, full, after = (selected(x["candidates"]) for x in (stock, fifth, rescue))
    old_positive, new_positive = before is not None, after is not None
    stock_positive_packet_changed = old_positive and stock != rescue
    return dict(
        lanes=1,
        stock_positive=old_positive,
        stock_positive_packet_changed=stock_positive_packet_changed,
        stock_lost=old_positive and not new_positive,
        stock_winner_changed=old_positive and new_positive and before != after,
        stock_negative_packet_changed=not old_positive and stock != rescue,
        also_negative_packet_changed=not old_positive and not new_positive and stock != rescue,
        rescue_new=not old_positive and new_positive,
        full_fifth_new=not old_positive and full is not None,
        rescue_new_and_fifth_new=not old_positive and new_positive and full is not None,
        rescue_new_and_fifth_winner_exact=not old_positive and new_positive and after == full,
        rescue_new_and_fifth_physical_match=(
            not old_positive
            and new_positive
            and full is not None
            and target_matches(after, full, exact_cfo=True)
        ),
    )


def compare_visits(stock, fifth, rescue):
    counts = Counter()
    for original, union, incremental in zip(stock, fifth, rescue, strict=True):
        common = [
            {k: v for k, v in row.items() if k != "probes"}
            for row in (original, union, incremental)
        ]
        if common.count(common[0]) != 3:
            raise ValueError("retune, source IQ, original validity or delivery clock differs")
        counts["recorded_visits"] += 1
        if original["status"] != "processed":
            if any(row["probes"] for row in (original, union, incremental)):
                raise ValueError("invalid capture unexpectedly entered a detector")
            counts["invalid_visits"] += 1
            continue
        if any(len(row["probes"]) != 2 for row in (original, union, incremental)):
            raise ValueError("a dual visit lost receiver lanes")
        for a, b, c in zip(*(row["probes"] for row in (original, union, incremental)), strict=True):
            footprint = [{k: v for k, v in p.items() if k != "candidates"} for p in (a, b, c)]
            if footprint.count(footprint[0]) != 3:
                raise ValueError("a physical receiver/RF probe header changed")
            counts.update(compare_lane(a, b, c))
    return dict(counts)


def staged_cost(ident, visits):
    data = [row["differential"] for row in visits if row["status"] == "processed"]
    if not data:
        return None
    lanes = [lane for row in data for lane in row["incremental_lanes"]]
    if len(lanes) != 2 * len(data):
        raise ValueError("incremental receipts must cover both physical receivers")
    counts = Counter(str(lane["decision"]) for lane in lanes)
    observed = {
        f"{stage}_{clock}": [row[f"{stage}_{clock}_ns"] / 1e9 for row in data]
        for stage in ("stock", "scout", "rescue")
        for clock in ("cpu", "wall")
    }
    return dict(
        id=ident,
        observed_calls=len(data),
        lane_decisions=dict(counts),
        totals_s={key: sum(value) for key, value in observed.items()},
        mean_ms={key: 1e3 * mean(value) for key, value in observed.items()},
        median_ms={key: 1e3 * median(value) for key, value in observed.items()},
    )


def audit_execution(stock, actual, staged):
    """Establish true native search scope and gate behavior on matched real lanes."""
    counts = Counter()
    for before, after, trace in zip(stock, actual, staged, strict=True):
        if trace["status"] != "processed":
            continue
        diag = trace["differential"]
        for rx, (old, new, lane) in enumerate(
            zip(before["probes"], after["probes"], diag["incremental_lanes"], strict=True)
        ):
            had = selected(old["candidates"]) is not None
            has = selected(new["candidates"]) is not None
            hint = lane["hint"]
            want = (
                list(range(max(0, hint - 1), min(13_332, hint + 1) + 1)) if hint is not None else []
            )
            executed = lane["evaluated_epochs"]
            seen = {i for center in lane["ordinary"] for i in range(center - 1, center + 2)}
            if (
                lane["rx"] != rx
                or hint != diag["hints"][rx]
                or lane["requested_epochs"] != want
                or (executed and executed != want)
                or seen.intersection(executed)
            ):
                raise ValueError("native input does not certify one disjoint differential region")
            counts["paired_stock_and_native_gate_disagree"] += had != lane["stock_positive"]
            counts["returned_positive_and_native_gate_disagree"] += has != (
                lane["stock_positive"] or lane["donor_positive"]
            )
            counts["actual_stock_positive_lane_scout_calls"] += had and bool(lane["scout_wall_ns"])
            counts["actual_stock_positive_lane_region_calls"] += had and bool(executed)
            counts["actual_negative_lane_scout_calls"] += not had and bool(lane["scout_wall_ns"])
            counts["actual_new_regions"] += bool(executed)
            counts["actual_new_epochs"] += len(executed)
            counts["actual_new_region_positive"] += lane["donor_positive"]
            counts["stock_positive_lanes"] += had
    return dict(counts)


def parents(lock):
    pins = trial.checked_receipt()
    previous = rows_from(whole_iq.checked(parent.REPORT / POS, pins["files"][POS]))
    previous = {(row["id"], row["method"]): row for row in previous}
    specs = ("control", "candidate")
    for ident in lock["cases"]:
        for role, method in zip(specs, (parent.BASELINE, parent.METHOD), strict=True):
            row = previous[ident, method]
            authority = lock["control"][ident][role]
            source = Path(authority["path"])
            for name, digest in authority["files"].items():
                whole_iq.checked(source / name, digest)
            if whole_iq.read(source / "position.json") != row["result"]:
                raise ValueError("historical raw result differs from the parent prediction archive")
            path = parent.REPORT / f"native/{role}/{ident}.json.gz"
            if sha256(gzip.decompress(path.read_bytes())).hexdigest() != row["native_sha256"]:
                raise ValueError("historical compressed factors do not bind the measured result")
            whole_iq.checked(source / "recording/native.json", row["native_sha256"])
    return previous


def native_log(run):
    """Copy partial lines as observed, including raw timeouts without a footer."""
    rows = []
    for lane in range(2):
        path = run / f"recording/replayed-{lane}.log"
        if path.is_file():
            prefix = "differential-visit: "
            rows.extend(
                dict(raw_lane=lane, telemetry=json.loads(line[len(prefix) :]))
                for line in path.read_text().splitlines()
                if line.startswith(prefix)
            )
    return rows


def seal(work):
    if (REPORT / "prediction-lock.json").exists():
        raise FileExistsError("the complete candidate attempts are already sealed")
    lock, _ = trial.configured(work)
    previous = parents(lock)
    archived_resources = whole_iq.read(parent.REPORT / RESOURCE)
    positions, visits, aud, resources, files = [], [], {}, {}, []
    for ident in lock["cases"]:
        row, resource, native = complete.attempt(
            work, ident, "candidate", lock, method=trial.METHOD
        )
        owned = work / ident / "candidate"
        older = [previous[ident, method] for method in (parent.BASELINE, parent.METHOD)]
        if any(
            old[key] != row[key] for old in older for key in (*comparison.PHYSICAL_KEYS, "mode")
        ):
            raise ValueError("new fit did not keep the original matched request and offer")
        positions += [*older, row]
        resources[ident] = {
            "stock": archived_resources[ident]["control"],
            "full_fifth": archived_resources[ident]["candidate"],
            "incremental": resource,
        }
        stock, union = (detector_rows(parent.WORK / ident / r) for r in ("control", "candidate"))
        for measured, role in zip((stock, union), ("stock", "full_fifth"), strict=True):
            visits.extend(dict(item, id=ident, role=role) for item in measured[1])
        aud[ident] = dict(raw_complete=native is not None)
        if native is not None:
            comparison.matched_physical(resources[ident]["stock"], resource, lock["cases"][ident])
            actual = detector_rows(owned)
            aud[ident].update(compare_visits(stock[0], union[0], actual[0]))
            staged = list(traces.trace_rows(ident, "incremental", actual))
            aud[ident]["lane_footer"] = traces.scout_trace(owned, staged)
            aud[ident]["stage_clocks"] = staged_cost(ident, staged)
            aud[ident]["execution"] = audit_execution(stock[0], actual[0], staged)
            visits.extend(stage for stage in staged if stage["status"] == "processed")
            name = ident + "-native.json.gz"
            write(REPORT / name, gzip.compress(native.read_bytes(), mtime=0))
            files.append(name)
        else:
            name = ident + "-partial-trace.jsonl.gz"
            pack(REPORT / name, native_log(owned))
            files.append(name)
        log = owned / "service.log"
        if log.is_file():
            name = ident + ".service.log"
            whole_iq.checked(log, resource["service"]["log_sha256"])
            write(REPORT / name, log.read_bytes())
            files.append(name)
        diagnostic = work / f"preflight-{ident}"
        for source in ("fixtures.json", "installed.json", "same-core-plan.json", "same-core.json"):
            path = diagnostic / source
            if path.is_file() and path.stat().st_size:
                name = f"{ident}-{source}"
                write(REPORT / name, path.read_bytes())
                files.append(name)
    traces.protect_resources(resources)
    save_json(REPORT / PROBES, aud)
    save_json(REPORT / RESOURCE, resources)
    pack(REPORT / POS, positions)
    pack(REPORT / VISITS, visits)
    files += [
        PROBES,
        RESOURCE,
        POS,
        VISITS,
        "PROTOCOL.md",
        "input-lock.json",
        "candidate-lock.json",
    ]
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(lock["cases"]),
            files={name: _sha(REPORT / name) for name in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def score():
    lock = whole_iq.read(REPORT / "prediction-lock.json")
    for name, digest in lock["files"].items():
        whole_iq.checked(REPORT / name, digest)
    positions = rows_from(REPORT / POS)
    _, refs = held_references("roof16", lock["cases"])
    scores = comparison.geographic(positions, {row["id"]: row for row in refs})
    csv_file(REPORT / "scores.csv", scores)
    save_json(
        REPORT / "summary.json",
        {
            role: {
                arm: dict(
                    published=sum(
                        r["error_km"] is not None
                        for r in scores
                        if r["method"] == method and r["arm"] == arm
                    ),
                    within_10pct=sum(
                        r["within_10pct"]
                        for r in scores
                        if r["method"] == method and r["arm"] == arm
                    ),
                )
                for arm in ARMS
            }
            for role, method in METHOD.items()
        },
    )
    timings = rows_from(REPORT / VISITS)
    resources = whole_iq.read(REPORT / RESOURCE)
    rows = timing_rows(resources, timings)
    csv_file(REPORT / "deadlines.csv", rows)
    paired_host = []
    for ident in lock["cases"]:
        name = f"{ident}-same-core.json"
        if name not in lock["files"]:
            continue
        plan = whole_iq.read(REPORT / f"{ident}-same-core-plan.json")
        for run in whole_iq.read(REPORT / name):
            paired_host.append(dict(id=ident, cpu=plan["cpu"], **run))
    if paired_host:
        csv_file(REPORT / "paired-host-detector.csv", paired_host)
        stage_figure(paired_host, lock)
    cert = (POS, "scores.csv", "deadlines.csv", "prediction-lock.json", PROBES, RESOURCE)
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=lock["cases"], files={f: _sha(REPORT / f) for f in cert}),
    )

    def series(role, key, label):
        return dict(
            value=METHOD[role],
            key=key,
            label=label,
            file=POS,
            native_field="paired_capture_sha256",
            match=list(comparison.PHYSICAL_KEYS),
        )

    save_json(
        REPORT / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="whole-incremental-rescue",
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="figure-lock.json",
                    provenance=cert[1:],
                    title="One extra differential region after a stock-negative lane",
                    caption=(
                        "Fresh saved-IQ rescue with matched stock and fifth-center controls. "
                        "Both calibration arms use the same causal receiver."
                    ),
                    series=[
                        series("incremental", "one", "Stock-first incremental rescue"),
                        series("stock", "stock", "Earlier complete stock wide"),
                        series(
                            "full_fifth", "one_native_factors", "Earlier unconditional fifth center"
                        ),
                    ],
                )
            ],
        ),
    )
    generate(REPORT / "charts", evidence=REPORT)


def stage_figure(data, lock):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.9), layout="constrained", sharey=True)
    for ax, ident in zip(axes, lock["cases"], strict=True):
        for role, label, color, offset in (
            ("stock", "Stock", "#536d86", -0.22),
            ("full_fifth", "Unconditional fifth", "#b2653f", 0),
            ("incremental", "Stock-first rescue", "#128172", 0.22),
        ):
            values = []
            for n in range(3):
                selected_rows = [
                    r["wall_ns"] / 1e6
                    for r in data
                    if r["id"] == ident and r["role"] == role and r["stock_positive_lanes"] == n
                ]
                values.append(median(selected_rows))
            ax.bar([n + offset for n in range(3)], values, width=0.20, label=label, color=color)
        ax.axhline(20, color="#8e3640", linestyle="--", linewidth=1, label="20 ms")
        ax.set(title=ident, xlabel="Stock-positive physical receivers")
        ax.set_xticks([0, 1, 2])
        ax.set_ylim(0, 51)
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.35)
    axes[0].set_ylabel("Median paired detector wall (ms)")
    axes[1].legend(frameon=False, loc="upper right", fontsize=8, ncols=2)
    fig.suptitle("One-region rescue adds work only on negative lanes")
    fig.savefig(REPORT / "paired-host-detector.png", dpi=175)
    fig.savefig(
        REPORT / "paired-host-detector.pdf", metadata={"CreationDate": None, "ModDate": None}
    )
    plt.close(fig)
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="whole-incremental-rescue-paired-host",
            title="Matched incremental detector wall",
            boundary="Same saved CI16 window to public native detector output on one host CPU",
            sample="Three saved windows per recording, six counterbalanced repeats each",
            image="paired-host-detector.png",
            pdf="paired-host-detector.pdf",
            csv="paired-host-detector.csv",
            seal="paired-host-lock.json",
            note="Held-window diagnostic. Full replay timing measured separately.",
        ),
    )
    names = (
        "stage-figure.json",
        "paired-host-detector.png",
        "paired-host-detector.pdf",
        "paired-host-detector.csv",
        "prediction-lock.json",
    )
    save_json(
        REPORT / "paired-host-lock.json",
        dict(
            cases=lock["cases"],
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    seal(args.work) if args.action == "seal" else score()
