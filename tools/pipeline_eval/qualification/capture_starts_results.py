"""Check capture parity, attribute missing starts, and aggregate four-center outcomes."""

import argparse
import csv
import gzip
import json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from statistics import median

import matplotlib
import numpy as np

from ..__main__ import encoded, save_json
from ..variants import iq_stream
from . import capture_starts as trial
from . import oracle_start
from .full_v5_check import ALIAS_HZ, BULK, _load_case, _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def load(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def basin_index(attempt, acquired):
    keys = [
        i
        for i, row in enumerate(attempt["centers"], 1)
        if (row["epoch"], row["residual_cfo_hz"], row["score"])
        == (
            acquired["coarse_epoch_sample"],
            acquired["coarse_residual_cfo_hz"],
            acquired["coarse_score"],
        )
    ]
    if len(keys) != 1:
        raise ValueError("a captured acquisition row does not bind to one coarse basin")
    return keys[0]


def near(items, epoch, cfo, epoch_fn, cfo_fn):
    """Expose nearest actual RF predecessor without declaring physical identity at coarse CFO."""
    distances = [
        (oracle_start.distance(epoch_fn(row), epoch), abs(cfo_fn(row) - cfo), index)
        for index, row in enumerate(items)
    ]
    if not distances:
        return None
    e, f, index = min(distances)
    return dict(
        index=index,
        distance_samples=e,
        literal_cfo_difference_hz=f,
        folded_cfo_difference_hz=oracle_start.distance(cfo_fn(items[index]), cfo, ALIAS_HZ),
    )


def grid_peaks_search(entries, calibration):
    out = []
    for item in entries:
        bins = zip(item["cfo_grid_hz"], item["scores"], strict=True)
        best = max(bins, key=lambda pair: (pair[1], -abs(pair[0] - calibration), -pair[0]))
        out.append(dict(epoch=item["epoch"], cfo_hz=best[0], score=best[1]))
    return out


def attribution(attempts, target):
    final = attempts[-1]
    matches = [
        r for r in final["final_candidates"] if r["candidate_rank"] == target["candidate_rank"]
    ]
    acquisitions = [r for r in final["acquired"] if r["rank"] == target["candidate_rank"]]
    if len(matches) != 1 or len(acquisitions) != 1:
        raise ValueError("archived winner did not originate in one installed attempt")
    end, begin = matches[0], acquisitions[0]
    rank = basin_index(final, begin)
    if (
        end["epoch_sample"] != target["integer_epoch_sample"]
        or end["fractional_margin"] != target["fractional_margin"]
        or end["fractional_epoch_status"] != "complete"
    ):
        raise ValueError("archived reference does not authenticate the installed attempt winner")
    primary = attempts[0]
    actual = oracle_start.exact_epoch(target)
    calibration = begin["absolute_cfo_hz"] - begin["residual_cfo_hz"]
    fine_peak = grid_peaks_search(final["fine_search"], calibration)[rank - 1]
    conditional_peak = grid_peaks_search(final["conditioned_search"], calibration)[rank - 1]
    first = [
        i
        for i, p in enumerate(primary["centers"], 1)
        if oracle_start.distance(p["epoch"], actual) <= 2
    ]
    refined = [
        i + 1
        for i, p in enumerate(primary["acquired"])
        if oracle_start.distance(p["refined_epoch_sample"], actual) <= 2
    ]
    return dict(
        origin=final["attempt"],
        anchor_count=len(final["anchors"]),
        capture_source_coarse_rank=rank,
        capture_source_epoch=begin["coarse_epoch_sample"],
        capture_source_coarse_residual_hz=begin["coarse_residual_cfo_hz"],
        capture_refined_epoch=begin["refined_epoch_sample"],
        capture_fine_grid_cfo_hz=fine_peak["cfo_hz"],
        capture_conditioned_grid_cfo_hz=conditional_peak["cfo_hz"],
        capture_acquired_cfo_hz=begin["absolute_cfo_hz"],
        capture_integer_margin=end["margin"],
        capture_fractional_margin=end["fractional_margin"],
        primary_has_near_coarse=bool(first),
        primary_first_near_rank=min(first, default=None),
        primary_has_near_refined=bool(refined),
        primary_fractional_gate=primary["passes"],
    )


def compare_lanes(lanes, attempts):
    out = []
    for receiver, lane in enumerate(lanes):
        history = [r for r in attempts if r["receiver"] == receiver]
        for rank, candidate in enumerate(lane["candidates"]):
            fractional = candidate["fractional_epoch"]
            epoch = candidate["epoch"] + (fractional["offset_samples"] or 0)
            cfo = (
                fractional["tracking_cfo_hz"]
                if fractional["tracking_cfo_hz"] is not None
                else candidate["tracking_cfo_hz"]
            )
            stage = []
            for attempt in history:
                got = attempt.get("acquired", [])
                calibrated_center = (
                    got[0]["absolute_cfo_hz"] - got[0]["residual_cfo_hz"] if got else 0
                )
                raw = near(
                    attempt["centers"],
                    epoch,
                    cfo,
                    lambda r: r["epoch"],
                    lambda r, center=calibrated_center: r["residual_cfo_hz"] + center,
                )
                fine = near(
                    got,
                    epoch,
                    cfo,
                    lambda r: r["refined_epoch_sample"],
                    lambda r: r["absolute_cfo_hz"],
                )
                fine_grid = near(
                    grid_peaks_search(attempt.get("fine_search", []), calibrated_center),
                    epoch,
                    cfo,
                    lambda r: r["epoch"],
                    lambda r: r["cfo_hz"],
                )
                conditioned_grid = near(
                    grid_peaks_search(attempt.get("conditioned_search", []), calibrated_center),
                    epoch,
                    cfo,
                    lambda r: r["epoch"],
                    lambda r: r["cfo_hz"],
                )
                final = near(
                    attempt["final_candidates"],
                    epoch,
                    cfo,
                    lambda r: r["epoch_sample"] + (r["fractional_epoch_offset_samples"] or 0),
                    lambda r: (
                        r["fractional_tracking_cfo_hz"]
                        if r["fractional_tracking_cfo_hz"] is not None
                        else r["tracking_cfo_hz"]
                    ),
                )
                stage.append(
                    dict(
                        attempt=attempt["attempt"],
                        coarse=raw,
                        fine_grid=fine_grid,
                        conditioned_grid=conditioned_grid,
                        acquired=fine,
                        fractional=final,
                    )
                )
            out.append(
                dict(
                    receiver=receiver,
                    rank=rank,
                    epoch=epoch,
                    cfo_hz=cfo,
                    fractional_status=fractional["status"],
                    capture_stages=stage,
                )
            )
    return out


def gather(work):
    plans, original = trial.plan(work)
    names = [
        "input-lock.json",
        *(f"{c}-{stage}.json.gz" for c in trial.CASES for stage in ("capture", "wide")),
    ]
    sources = {name: _sha(work / name) for name in names}
    save_json(work / "prediction-lock.json", dict(files=sources))
    summary, links = [], {}
    for ident in trial.CASES:
        case = _load_case(ident)
        expected = trial.hinted_glrt_trial.checked_json(
            BULK / case["native"]["path"], plans[ident]["archived_native_sha256"]
        )
        reference = {(p["visit_index"], p["receiver_id"]): p for p in expected["source"]["probes"]}
        capture_path = work / f"{ident}-capture.json.gz"
        observed = load(capture_path)
        wide = load(work / f"{ident}-wide.json.gz")
        if wide["capture_sha256"] != sources[capture_path.name]:
            raise ValueError("wide prefixes differ from capture traces")
        known = {r["visit"]: r for r in load(trial.ORACLE / f"{ident}.json.gz")}
        for row, raw, native in zip(
            original[ident]["selected"], observed["capture"], wide["outputs"], strict=True
        ):
            visit, rx, label = row["visit"], row["receiver"], row["target"]
            if visit != raw["visit"] or visit != native["visit"]:
                raise ValueError("saved diagnostic row order changed")
            matched = [
                encoded(probe) == encoded(reference[visit, i])
                for i, probe in enumerate(raw["capture"]["probes"])
            ]
            if matched != [True, True]:
                raise ValueError(f"capture archive parity failed {ident}/{visit}: {matched}")
            attempts = raw["capture"]["attempts"]
            history = [packet for packet in attempts if packet["receiver"] == rx]
            stock = native["result"]["payloads"]["stock"]["rows"]
            stage_links = compare_lanes(stock, attempts)
            links[f"{ident}:{visit}"] = stage_links
            endpoints = {}
            for source, mode in (("stock", "stock"), ("prefix", "causal"), ("sham", "sham")):
                out = native["result"]["payloads"][mode]["rows"][rx]
                endpoints[source] = oracle_start.endpoints(label, native["probes"][mode][rx], out)
            prior = known[visit]
            if prior["status"] == "processed":
                endpoints["oracle"] = oracle_start.endpoints(
                    label,
                    prior["probes"]["oracle"][rx],
                    prior["result"]["payloads"]["oracle"]["rows"][rx],
                )
            else:
                endpoints["oracle"] = None
            hint = native["hints"][rx]
            own = native["result"]["traces"]["causal"][rx]
            prefix_time = raw["prefix"]
            times = native["result"]["timings"]
            ctimes = Counter()
            for attempt in attempts:
                ctimes.update(attempt["stage_cpu_ns"])
            summary.append(
                dict(
                    case=ident,
                    visit=visit,
                    edge=plans[ident]["edge"],
                    receiver=rx,
                    kind=row["kind"],
                    stratum=row["stratum"],
                    target_epoch=oracle_start.exact_epoch(label),
                    target_cfo_hz=label["fractional_tracking_cfo_hz"],
                    hint=hint,
                    hint_error_samples=oracle_start.distance(hint, oracle_start.exact_epoch(label))
                    if hint is not None
                    else None,
                    prefix_activated=own["ordinary"] != own["selected"],
                    capture_factor_parity=all(matched),
                    stock_has_near_public_epoch=any(
                        oracle_start.distance(c["epoch"], oracle_start.exact_epoch(label)) <= 2
                        for c in stock[rx]["candidates"]
                    ),
                    capture_full_cpu_ms=raw["capture"]["cpu_ns"] / 1e6,
                    capture_full_wall_ms=raw["capture"]["wall_ns"] / 1e6,
                    prefix_coarse_cpu_ms=prefix_time["cpu_ns"] / 1e6,
                    prefix_coarse_wall_ms=prefix_time["wall_ns"] / 1e6,
                    prefix_lanes=[r["cpu_ns"] / 1e6 for r in prefix_time["choices"]],
                    wide_cpu_ms=median(t["detector_ms"] for t in times["stock"]),
                    wide_with_prefix_cpu_ms=median(t["detector_ms"] for t in times["causal"]),
                    capture_stage_cpu_ms={k: v / 1e6 for k, v in ctimes.items()},
                    **attribution(history, label),
                    endpoints=endpoints,
                )
            )
    save_json(work / "summary.json", dict(rows=summary, stock_candidate_links=links))


def render(work):
    summary = json.loads((work / "summary.json").read_bytes())["rows"]
    rows = [
        dict(
            {
                k: v
                for k, v in r.items()
                if k not in ("endpoints", "capture_stage_cpu_ms", "prefix_lanes")
            },
            **{
                f"{m}_{k}": value
                for m, end in r["endpoints"].items()
                if end is not None
                for k, value in end.items()
            },
            **{f"capture_{key}_cpu_ms": value for key, value in r["capture_stage_cpu_ms"].items()},
            **{f"prefix_rx{rx}_cpu_ms": value for rx, value in enumerate(r["prefix_lanes"])},
        )
        for r in summary
    ]
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with (work / "capture-starts.csv").open("w", newline="") as stream:
        output = csv.DictWriter(stream, fieldnames=columns)
        output.writeheader()
        output.writerows(rows)
    misses = [r for r in summary if r["kind"] == "miss"]
    stages = (
        ("Capture primary retained set", lambda r: r["primary_has_near_coarse"]),
        ("Found only in 22-anchor fallback", lambda r: r["origin"] == "fallback"),
        (
            "Primary coarse rank 1",
            lambda r: r["hint_error_samples"] is not None and r["hint_error_samples"] <= 2,
        ),
        ("Rank 1 → wide, gated", lambda r: r["endpoints"]["prefix"]["passes"]),
        ("Known start → wide, gated", lambda r: r["endpoints"]["oracle"]["passes"]),
    )
    ids = list(dict.fromkeys(r["case"] for r in summary))
    fig, (left, right) = plt.subplots(1, 2, figsize=(11.1, 4.6))
    bars = [sum(test(r) for r in misses) for _, test in stages]
    left.barh(
        range(len(stages)), bars, color=("#42677c", "#42677c", "#6d8797", "#147b72", "#78afa1")
    )
    left.set_yticks(range(len(stages)), [label for label, _ in stages], fontsize=9)
    left.invert_yaxis()
    left.set_xlim(0, len(misses) + 1.7)
    left.set_title("On the 16 originally missed targets", loc="left", fontweight="bold")
    for i, k in enumerate(bars):
        left.text(k + 0.2, i, str(k), va="center", fontsize=10)
    scopes = (
        ("Installed capture", "capture_full_cpu_ms", "#42677c", "o"),
        ("Coarse prefix only", "prefix_coarse_cpu_ms", "#147b72", "s"),
        ("Wide detector only", "wide_cpu_ms", "#bc6940", "^"),
    )
    for label, key, color, marker in scopes:
        right.scatter(
            range(len(ids)),
            [median(r[key] for r in summary if r["case"] == case) for case in ids],
            label=label,
            color=color,
            marker=marker,
            s=38,
        )
    right.set_yscale("log")
    right.set_xticks(range(len(ids)), ids, fontsize=9, rotation=16)
    right.set_title("Median detector CPU, both receivers", loc="left", fontweight="bold")
    right.set_ylabel("Host milliseconds, log scale")
    right.legend(loc="upper center", bbox_to_anchor=(0.5, -0.23), frameon=False, ncol=2, fontsize=9)
    fig.suptitle(
        "Capture-era coarse starts explain part of the wide GLRT gap",
        x=0.09,
        y=0.985,
        ha="left",
        fontweight="bold",
        fontsize=15,
    )
    fig.text(
        0.09,
        0.89,
        "Saved-IQ stage trace. Only the known-start arm reads the target timing label.",
        fontsize=10,
    )
    for ax in (left, right):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.18)
    fig.subplots_adjust(left=0.22, right=0.98, top=0.81, bottom=0.28, wspace=0.36)
    fig.savefig(work / "capture-starts.png", dpi=170)
    fig.savefig(work / "capture-starts.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    parents = json.loads((work / "prediction-lock.json").read_bytes())["files"]
    files = (
        *parents,
        "prediction-lock.json",
        "summary.json",
        "sanity.json",
        "capture-starts.csv",
        "capture-starts.png",
        "capture-starts.pdf",
    )
    save_json(
        work / "result-lock.json",
        dict(files={name: _sha(work / name) for name in files}, source_sha256=_sha(Path(__file__))),
    )


def sanity(work):
    """Replay the two signed and two noise controls through hinted wide."""
    from leo.analysis.starlink import templates

    plans, _ = trial.plan(work)
    libs = json.loads(oracle_start.ABI.read_bytes())["paths"]
    results = {}
    for ident in trial.CONTROL_CASES:
        scope = plans[ident]
        archived = Path(scope["producer"]) / "leo/analysis/starlink/templates.py"
        if _sha(Path(templates.__file__)) != scope["sources"][str(archived)]:
            raise ValueError("control template bytes differ from the initial capture run")
        record = load(work / f"{ident}-capture.json.gz")
        metadata = record["capture"][-1]["metadata"]
        geometry = iq_stream.IQWindow(samples=np.zeros((200000, 2, 2), dtype="<i2"), **metadata)
        with ExitStack() as stack:
            stock, hinted = trial.hinted_glrt_trial.bound(stack, libs, scope["edge"])
            for label, control in record["controls"].items():
                plant = trial._test_signal(geometry, control["plants"], 78201)
                hints = tuple(r["hint"] for r in control["prefix"]["choices"])
                result = trial.hinted_glrt_trial.measure(
                    plant.samples, stock, hinted, dict(causal=hints), 0, reps=1
                )
                positive = trial.hinted_glrt_trial.ordinary_front_eval.positive
                endpoints = {mode: positive(v) for mode, v in result["payloads"].items()}
                compared = [lane for mode in ("stock", "causal") for lane in endpoints[mode]]
                if control["plants"]:
                    epoch, hz, _ = control["plants"][0]
                    center = (
                        geometry.target["rf_center_hz"]
                        - geometry.target["lnb_lo_hz"]
                        - geometry.acquisition["actual_if_center_hz"]
                    )
                    if not all(
                        any(
                            abs(e - epoch) <= 2 and abs(f - hz - center) <= 1000
                            for _, e, f, _ in lane
                        )
                        for lane in compared
                    ):
                        raise ValueError("signed control lost its declared physical endpoint")
                elif any(compared):
                    raise ValueError("synthetic noise emitted a gated wide detection")
                results[f"{ident}:{label}"] = dict(
                    plants=control["plants"],
                    iq_sha256=plant.iq_sha256,
                    hints=hints,
                    native_positives=endpoints,
                    capture_positives=[
                        sum(c["passed_fractional_margin_gate"] for c in row["candidates"])
                        for row in control["capture"]["probes"]
                    ],
                )
    save_json(work / "sanity.json", results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    gather(args.work)
    sanity(args.work)
    render(args.work)
