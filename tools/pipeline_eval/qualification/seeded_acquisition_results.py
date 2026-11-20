"""Freeze development choices and score the held saved-IQ tracking experiment."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import distribution
from ..variants import seeded_acquisition as seeded
from . import scout_stage_figures as plot
from . import seeded_acquisition_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

PREFIX = "seeded-acquisition: "
MATCH_EPOCH = 2.0
MATCH_CFO = 2_000.0


def positive(probe):
    return [c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]


def compatible(left, right, *, alias=False):
    epoch = (
        left["integer_epoch_sample"]
        + left["fractional_epoch_offset_samples"]
        - right["integer_epoch_sample"]
        - right["fractional_epoch_offset_samples"]
    )
    frequency = left["fractional_tracking_cfo_hz"] - right["fractional_tracking_cfo_hz"]
    if alias:
        frequency = seeded.wrapped(frequency, seeded.ALIAS)
    return abs(seeded.wrapped(epoch)) <= MATCH_EPOCH and abs(frequency) <= MATCH_CFO


def loaded(work, case):
    _, lock, _ = trial.configure(work, case)
    source = _sha(work / "source-lock.json")
    log = work / f"{case}.log"
    (receipt,) = [
        json.loads(line.removeprefix(PREFIX))
        for line in log.read_text().splitlines()
        if line.startswith(PREFIX)
    ]
    if (
        whole_iq.read(work / f"{case}-exit.json")["exit_code"]
        or receipt["case"] != case
        or receipt["source_lock_sha256"] != source
        or receipt["tune_sha256"] != (_sha(work / "tune-lock.json") if case == trial.HELD else None)
        or receipt["start"]["cgroup"] != receipt["end"]["cgroup"]
        or len(receipt["compressed_bytes"]) != 2
        or any(x <= 0 for x in receipt["compressed_bytes"])
        or [r["visit"] for r in receipt["rows"]] != list(map(int, lock["reference"]))
    ):
        raise ValueError("worker does not bind the frozen raw scope or selection")
    for edge in ("start", "end"):
        r = receipt[edge]
        if (
            r["cpus"] != [lock["cpu"]]
            or r["memory.max"] != whole_iq.MEMORY
            or r["memory.swap.max"]
            or r["memory.swap.current"]
            or r["memory.events.oom_kill"]
        ):
            raise ValueError("capped waveform worker left its resource envelope")
    return lock, receipt


def score(lock, receipt, mode, *, native_fraction=1.0):
    counts, rf_visits, follow_visits = Counter(), Counter(), Counter()
    follow_cpu, follow_wall, all_cpu, all_wall = [], [], [], []
    anchor_cpu, coarse_cpu, anchor_state = 0, 0, 0
    for row in receipt["rows"]:
        expected = lock["reference"][str(row["visit"])]
        if row["clock"] != expected["clock"] or (row["status"] != "processed") != (
            expected["exclusion"] is not None
        ):
            raise ValueError("measurement pass changed physical capture validity or clock")
        validation = row["validation"]
        if row["status"] != "processed":
            if "anchor" in row or "follow" in row:
                raise ValueError("physical exclusion entered original or local acquisition")
            counts["invalid"] += 1
            continue
        rf = (row["generation"], row["rf"])
        ordinal = rf_visits[rf]
        rf_visits[rf] += 1
        if ordinal != row["ordinal"] or ("anchor" in row) != (ordinal % trial.CADENCE == 0):
            raise ValueError("reacquisition schedule depended on signal outcomes")
        if "anchor" in row:
            a = row["anchor"]
            if a["probes"] != expected["probes"] or a["grids"] < 2:
                raise ValueError("anchor factors do not bind real original acquisition")
            counts.update(
                anchor_visits=1,
                original_anchor_grids=a["grids"],
                anchor_positive_probes=sum(bool(positive(p)) for p in a["probes"]),
                anchor_gate_miss_probes=sum(not positive(p) for p in a["probes"]),
            )
            anchor_cpu += a["clocks"]["cpu_ns"]
            state = a["state_cpu_ns"] / 2 if mode != "native" else 0
            anchor_state += state
            all_cpu.append(validation["cpu_ns"] + a["clocks"]["cpu_ns"] + state)
            all_wall.append(validation["wall_ns"] + a["clocks"]["wall_ns"])
            continue
        counts["follow_visits"] += 1
        counts["positive_reference_probes"] += sum(bool(positive(p)) for p in expected["probes"])
        index = follow_visits[rf]
        follow_visits[rf] += 1
        actual = row["follow"].get(mode)
        expected_native = trial.native_selected(native_fraction, index)
        if (mode != "native" and actual is None) or (
            mode == "native" and (actual is not None) != expected_native
        ):
            raise ValueError("recorded follow calls disagree with the predeclared RF cadence")
        cpu, wall = validation["cpu_ns"], validation["wall_ns"]
        if actual is not None:
            counts["follow_calls"] += 1
            c, w = actual["clocks"]["cpu_ns"], actual["clocks"]["wall_ns"]
            follow_cpu.append(c)
            follow_wall.append(w)
            cpu += c
            wall += w
            for lane in actual.get("lanes", []):
                counts["searched_probes"] += lane["status"] == "searched"
                counts["no_seed_probes"] += lane["status"] == "no_seed"
                counts["accepted_updates"] += bool(lane.get("updated"))
                coarse_cpu += lane.get("coarse_cpu_ns", 0)
            for reference, measured in zip(expected["probes"], actual["probes"], strict=True):
                if {k: v for k, v in measured.items() if k != "candidates"} != {
                    k: v for k, v in reference.items() if k != "candidates"
                }:
                    raise ValueError("candidate output changed the physical probe geometry")
                left, right = positive(measured), positive(reference)
                counts["positive_follow_probes"] += bool(left)
                counts["positive_follow_candidates"] += len(left)
                counts["follow_candidates"] += len(measured["candidates"])
                counts["signed_matches"] += any(compatible(x, y) for x in left for y in right)
                counts["alias_matches"] += any(
                    compatible(x, y, alias=True) for x in left for y in right
                )
            counts["executed_within_20ms"] += wall <= 20_000_000
        else:
            counts["budget_skipped_visits"] += 1
        all_cpu.append(cpu)
        all_wall.append(wall)
    counts["unmatched_positive_probes"] = (
        counts["positive_follow_probes"] - counts["signed_matches"]
    )
    counts["scheduled_slots"] = len(receipt["rows"])
    counts["valid_slots"] = len(all_cpu)
    return dict(
        counts=dict(counts),
        rf_valid_counts={str(k[1]): n for k, n in rf_visits.items()},
        follow_cpu_ns=sum(follow_cpu),
        follow_wall_ns=sum(follow_wall),
        anchor_cpu_ns=anchor_cpu,
        tracker_anchor_update_cpu_ns=anchor_state,
        follow_local_coarse_cpu_ns=coarse_cpu,
        total_cpu_ns=sum(all_cpu),
        total_wall_ns=sum(all_wall),
        follow_cpu_ms=distribution([x / 1e6 for x in follow_cpu]),
        follow_wall_ms=distribution([x / 1e6 for x in follow_wall]),
    )


def tune(work):
    lock, dev = loaded(work, trial.DEVELOPMENT)
    rows = {str(rate): score(lock, dev, str(rate)) for rate in trial.DEVRATES}
    native = score(lock, dev, "native")

    def quality(name):
        q = rows[name]
        return (
            q["counts"].get("signed_matches", 0),
            -q["counts"]["unmatched_positive_probes"],
            -q["follow_cpu_ns"],
        )

    winner = max(rows, key=quality)
    fraction = min(1.0, rows[winner]["follow_cpu_ns"] / native["follow_cpu_ns"])
    receipt = dict(
        rate=int(winner),
        native_follow_fraction=fraction,
        ranks=rows,
        development_native=native,
        source_lock_sha256=_sha(work / "source-lock.json"),
        development_raw_sha256=_sha(work / f"{trial.DEVELOPMENT}.log"),
        scoring_sha256=_sha(Path(__file__)),
    )
    for path in (work / "tune-lock.json", trial.REPORT / "tune-lock.json"):
        if path.exists() and whole_iq.read(path) != receipt:
            raise ValueError("development choices already frozen")
        save_json(path, receipt)
        path.chmod(0o644)
    print("Frozen dev choice", winner, "native follow fraction", fraction, flush=True)


def render(out, results):
    fig, axes = plot.canvas(
        "Causal seeded pilot acquisition on held saved IQ",
        "DS29-0082 upper edge · 128 chronological slots · one state per physical receiver and RF",
        "The three policies share identical original anchor scans. The native follow-call "
        "fraction was set from development CPU costs.",
    )
    labels = ["Seeded local search", "Half-frame shifted", "Native budget control"]
    rows = [results[k] for k in ("seeded", "shifted", "native")]
    plot.paired(
        axes[0],
        labels,
        [(x["follow_cpu_ms"]["p50"] or 0, x["follow_cpu_ms"]["p95"] or 0) for x in rows],
        title="Follow detector CPU",
        xlabel="Milliseconds",
    )
    plot.paired(
        axes[1],
        labels,
        [(x["follow_wall_ms"]["p50"] or 0, x["follow_wall_ms"]["p95"] or 0) for x in rows],
        title="Follow detector wall",
        xlabel="Milliseconds",
    )
    plot.key(fig, "Median", "95th percentile")
    fig.savefig(out / "stage.png", dpi=165, facecolor="white")
    fig.savefig(out / "stage.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)


def publish(work):
    out = trial.REPORT
    frozen = whole_iq.read(whole_iq.checked(work / "tune-lock.json", _sha(out / "tune-lock.json")))
    lock, held = loaded(work, trial.HELD)
    if (
        frozen["source_lock_sha256"] != _sha(work / "source-lock.json")
        or frozen["scoring_sha256"] != _sha(Path(__file__))
        or frozen["development_raw_sha256"] != _sha(work / f"{trial.DEVELOPMENT}.log")
    ):
        raise ValueError("held experiment or scoring changed after development freeze")
    names = ["seeded", "shifted", "native"]
    results = {
        m: score(lock, held, m, native_fraction=frozen["native_follow_fraction"]) for m in names
    }
    save_json(
        out / "audit.json",
        dict(held=results, resources={k: v for k, v in held.items() if k != "rows"}),
    )
    cols = (
        "scheduled_slots",
        "valid_slots",
        "invalid",
        "anchor_visits",
        "follow_visits",
        "follow_calls",
        "budget_skipped_visits",
        "searched_probes",
        "no_seed_probes",
        "accepted_updates",
        "positive_reference_probes",
        "positive_follow_probes",
        "signed_matches",
        "alias_matches",
        "unmatched_positive_probes",
        "executed_within_20ms",
    )
    csv_file(
        out / "stage.csv",
        [
            dict(
                policy=m,
                **{k: row["counts"].get(k, 0) for k in cols},
                follow_cpu_s=row["follow_cpu_ns"] / 1e9,
                total_cpu_s=row["total_cpu_ns"] / 1e9,
                cpu_p50_ms=row["follow_cpu_ms"]["p50"],
                cpu_p95_ms=row["follow_cpu_ms"]["p95"],
                wall_p50_ms=row["follow_wall_ms"]["p50"],
                wall_p95_ms=row["follow_wall_ms"]["p95"],
            )
            for m, row in results.items()
        ],
    )
    render(out, results)
    files = [
        "PROTOCOL.md",
        "source-lock.json",
        "tune-lock.json",
        "audit.json",
        "stage.csv",
        "stage.png",
        "stage.pdf",
    ]
    for case in (trial.DEVELOPMENT, trial.HELD):
        for name in (f"{case}.log", f"{case}.json", f"{case}-launch.json", f"{case}-exit.json"):
            target = f"receipts/{name}.gz"
            write(out / target, gzip.compress((work / name).read_bytes(), compresslevel=5, mtime=0))
            files.append(target)
    save_json(out / "stage-lock.json", dict(files={name: _sha(out / name) for name in files}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="seeded-pilot-acquisition",
            title="Causal seeded pilot acquisition",
            sample="128 upper-edge slots with search width and budget chosen on the lower edge",
            boundary="Resident CI16 through original anchors, local search, and factor projection",
            note="Follow timing covers actual calls. Anchor timing and native control coverage "
            "are in the sealed evidence.",
            seal="stage-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("tune", "publish"))
    parser.add_argument("work", type=local_output, nargs="?", default=trial.WORK)
    args = parser.parse_args()
    (tune if args.action == "tune" else publish)(args.work)
