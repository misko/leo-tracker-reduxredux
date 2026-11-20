"""Verify and plot complete-epoch replay receipts without the IQ archive or release binaries."""

import argparse
import io
from collections import Counter
from pathlib import Path
from statistics import median

from ..__main__ import encoded, save_json, write
from . import complete_epoch_proxy_eval as run
from . import scout_stage_figures as stage
from .full_v5_check import ALIAS_HZ, CFO_TOLERANCE_HZ, EPOCH_TOLERANCE_SAMPLES, _wrapped
from .thinned_capture_results import positives, primary_acquisitions

ROLES = {"capture": "capture", "proxy18": "thinned", "wide": "wide"}
PLANTED = {"weak": (735, 48_000), "high": (731, 720_000), "negative_high": (731, -720_000)}


def basin_counts(rows):
    ranks = [Counter() for _ in range(8)]
    for row in rows:
        roles = row["pairs"][0]["modes"]
        original = primary_acquisitions(roles["capture"]["acquisitions"])
        sparse = primary_acquisitions(roles["thinned"]["acquisitions"])
        if original.keys() != sparse.keys():
            raise ValueError("matched primary acquisition receiver identifiers changed")
        for rx, base in original.items():
            trial = sparse[rx]
            if (base["anchors"], base["cfo_lanes"]) != (trial["anchors"], trial["cfo_lanes"]):
                raise ValueError("matched primary acquisition geometry changed")
            selected = set(map(tuple, trial["peaks"]))
            for rank, (epoch, cfo) in enumerate(base["peaks"]):
                ranks[rank].update(
                    original=1,
                    covered_cap32=any(
                        lo <= epoch < hi for lo, hi in trial["cap32_eligible_ranges"]
                    ),
                    covered_cap96=any(lo <= epoch < hi for lo, hi in trial["eligible_ranges"]),
                    exact_keys_retained=(epoch, cfo) in selected,
                )
    pooled = Counter()
    for rank in ranks:
        pooled.update(rank)
    return dict(pooled, by_original_rank=[dict(rank) for rank in ranks])


def plant_counts(name, probes):
    epoch, cfo = PLANTED[name]
    matched = raw = 0
    for probe in probes:
        alias_close, raw_close = False, False
        for candidate in probe["candidates"]:
            if not candidate["passed_fractional_margin_gate"]:
                continue
            time_error = (
                candidate["integer_epoch_sample"]
                + candidate["fractional_epoch_offset_samples"]
                - epoch
            )
            if abs(_wrapped(time_error, 13_333)) <= EPOCH_TOLERANCE_SAMPLES:
                frequency_error = candidate["fractional_tracking_cfo_hz"] - cfo
                alias_close |= abs(_wrapped(frequency_error, ALIAS_HZ)) <= CFO_TOLERANCE_HZ
                raw_close |= abs(frequency_error) <= CFO_TOLERANCE_HZ
        matched += alias_close
        raw += raw_close
    return dict(
        receiver_count=len(probes), plant_alias_match_rx=matched, plant_unfolded_match_rx=raw
    )


def control(name, document):
    modes = document["pairs"][0]["modes"]
    return {
        role: dict(
            cpu_ms=modes[mode]["cpu_ms"],
            positive_candidates=sum(
                c["passed_fractional_margin_gate"]
                for p in modes[mode]["probes"]
                for c in p["candidates"]
            ),
            **(plant_counts(name, modes[mode]["probes"]) if name in PLANTED else {}),
            **(
                {"reference_positive_matches": positives(document["positives"][mode])}
                if mode != "capture"
                else {}
            ),
        )
        for role, mode in ROLES.items()
    }


def validate_rows(ident, lock, source, case):
    roster = lock["roster"][ident]
    if case["id"] != ident or case["locked_sha256"] != run.parent._digest(encoded(lock)):
        raise ValueError("measurement does not bind the complete-epoch source freeze")
    if case["provenance"] != source["provenance"] or len(case["rows"]) != len(roster):
        raise ValueError("measurement differs from authenticated source or roster length")
    old_rows = {row["visit"]: row for row in source["rows"]}
    rows = []
    for row, bound in zip(case["rows"], roster, strict=True):
        if any(row[k] != value for k, value in bound.items()):
            raise ValueError("visit status or actual IQ differs from the frozen roster")
        old = old_rows[row["visit"]]
        if row["status"] == "processed":
            if len(row["pairs"]) != 2 or any(
                set(pair["modes"]) != set(ROLES.values())
                or pair["modes"]["capture"]["probes"]
                != old["pairs"][0]["modes"]["capture"]["probes"]
                or pair["modes"]["wide"]["probes"] != old["pairs"][0]["modes"]["wide"]["probes"]
                for pair in row["pairs"]
            ):
                raise ValueError("measured pair is incomplete or differs from sealed controls")
            rows.append(row)
        elif "pairs" in row:
            raise ValueError("an excluded visit unexpectedly entered the detector")
    expected_controls = {"empty", "noise", *PLANTED} if ident in run.parent.CONTROLS else set()
    if set(case["controls"]) != expected_controls:
        raise ValueError("the frozen signed/weak/negative controls were not all measured")
    return rows


def summarize():
    folder = run.REPORT
    prior_folder = run.parent.REPORT
    prior_files = stage.verify(prior_folder, "evidence-lock.json")
    previous = stage.read(prior_folder / "qualification.json")
    lock = stage.read(folder / "source-lock.json")
    for path, digest in lock["proxy_sources"].items():
        if stage.sha(run.ROOT / path) != digest:
            raise ValueError("source freeze changed after the replay")
    rows, cases = [], {}
    for ident in run.CASES:
        case = stage.read(folder / f"{ident}.json.gz")
        kept = validate_rows(ident, lock, stage.read(prior_folder / f"{ident}.json.gz"), case)
        rows.extend(kept)
        cases[ident] = dict(
            processed=len(kept),
            excluded=[row for row in case["rows"] if row["status"] != "processed"],
            harness_peak_rss_kib=case["peak_rss_kib"],
            basins=basin_counts(kept),
            controls={name: control(name, data) for name, data in case["controls"].items()},
        )
    pairs = [pair for row in rows for pair in row["pairs"]]
    timing = {}
    for role, mode in ROLES.items():
        values = [p["modes"][mode] for p in pairs]
        timing[role] = dict(
            timed_calls=len(values),
            cpu_elapsed_ms=[v["cpu_ms"] for v in values],
            median_cpu_ms=median(v["cpu_ms"] for v in values),
            median_wall_ms=median(v["wall_ms"] for v in values),
            cpu_at_most_20_ms=sum(v["cpu_ms"] <= 20 for v in values),
            wall_at_most_20_ms=sum(v["wall_ms"] <= 20 for v in values),
        )
    primary = [a for p in pairs for a in p["modes"]["thinned"]["acquisitions"]]
    proxy = [p["modes"]["thinned"] for p in pairs]
    clocks = [p["stage_cpu_ms"] for p in proxy]
    totals = dict(
        score_calls=len(primary),
        full_geometry_cells=sum(a["original_cells"] for a in primary),
        short_proxy_cells=sum(a["proposal_cells"] for a in primary),
        full_rescore_cells=sum(a["rescored_cells"] for a in primary),
        bit_exact_comparable_rescore_cells=sum(p["bit_exact_rescored_cells"] for p in pairs),
        maximum_explicit_numpy_peak_bytes=max(a["coarse_numpy_buffer_peak_bytes"] for a in primary),
        frame_anchor_geometry=sorted(
            {
                (
                    len(a["coarse_frames"]),
                    len(a["coarse_anchors"]),
                    a["original_anchor_taps"],
                    a["proposal_anchor_taps"],
                )
                for a in primary
            }
        ),
    )
    timing["proxy18"].update(
        **{
            f"median_{key}": median(sum(a[key] for a in p["acquisitions"]) for p in proxy)
            for key in ("proposal_cpu_ms", "nomination_cpu_ms", "rescore_cpu_ms")
        },
        median_remaining_after_coarse_cpu_ms=median(
            p["cpu_ms"] - clock.get("coarse_grid", 0) - clock.get("final_peak_select", 0)
            for p, clock in zip(proxy, clocks, strict=True)
        ),
        median_fractional_cpu_ms=median(c.get("fractional_glrt", 0) for c in clocks),
    )
    summary = dict(
        position_attempted=False,
        real_visits=len(rows),
        cases=cases,
        timing=timing,
        candidate_gate_matches={
            role: positives([p for row in rows for p in row["positives"][mode]])
            for role, mode in ROLES.items()
            if mode != "capture"
        },
        exact_candidate_payload_rx=sum(
            left == right
            for row in rows
            for left, right in zip(
                row["pairs"][0]["modes"]["capture"]["probes"],
                row["pairs"][0]["modes"]["thinned"]["probes"],
                strict=True,
            )
        ),
        basins=basin_counts(rows),
        compute=totals,
        earlier_thinned32=dict(
            basins=previous["held_basin_keys"],
            positives=previous["held_positives"]["thinned"],
            detector_cpu_ms=previous["timing"]["thinned"]["median_cpu_ms"],
        ),
    )
    links = {str(p.relative_to(run.ROOT)): stage.sha(p) for p in prior_files}
    return summary, links


def render(summary, out):
    basin, gate, clock = summary["basins"], summary["candidate_gate_matches"], summary["timing"]
    old = summary["earlier_thinned32"]
    fig, (coverage, runtime) = stage.canvas(
        "Complete-epoch proposal for capture acquisition",
        f"Dual-RX detector stage · {summary['real_visits']} saved visits · two repeats",
        "The 18-tap proposal keeps all epochs, CFOs, frames and anchors. A fixed 96-nomination "
        f"shortlist receives exact full-tap scoring. At the same 32-nomination cap, its covered "
        f"count is {basin['covered_cap32']}/{basin['original']}. Final matches allow epoch and CFO "
        "aliases. The dotted line is 20 ms. No positioning was run.",
    )
    fig.subplots_adjust(bottom=0.281)
    labels = (
        "Original coarse keys\nin scored interior",
        "Exactly retained\ncoarse keys",
        "Matched final\ngate-positive candidates",
    )
    counts = [
        [old["basins"]["original_in_scored_interior"], basin["covered_cap96"]],
        [old["basins"]["retained"], basin["exact_keys_retained"]],
        [old["positives"]["matched"], gate["proxy18"]["matched"]],
    ]
    denominators = [basin["original"], basin["original"], gate["proxy18"]["original"]]
    stage.header(
        coverage,
        "Recovery at measured shortlist caps",
        "Share of installed control (%)",
        labels,
        100,
    )
    for index, (values, denominator) in enumerate(zip(counts, denominators, strict=True)):
        for offset, value, color in zip(
            (-0.16, 0.16), values, (stage.BASE, stage.CANDIDATE), strict=True
        ):
            percentage = 100 * value / denominator
            coverage.barh(index + offset, percentage, height=0.24, color=color)
            coverage.text(
                percentage + 1.5, index + offset, f"{value}/{denominator}", va="center", fontsize=9
            )
    stage.key(fig, "Earlier frame/anchor thinned · cap 32", "Complete-epoch 18 taps · cap 96")
    fig.legends[-1].set_bbox_to_anchor((0.052, 0.147))
    modes = ("capture", "proxy18", "wide")
    samples = [clock[role]["cpu_elapsed_ms"] for role in modes]
    right_edge = max(max(group) for group in samples) * 1.40
    stage.header(
        runtime,
        "Full detector call",
        "Host CPU (ms, log scale)",
        ("Installed capture", "Complete-epoch proxy", "Compiled wide"),
        right_edge,
    )
    runtime.set_xscale("log")
    runtime.set_xlim(min(min(group) for group in samples) * 0.75, right_edge)
    runtime.set_xticks((20, 100, 1000), ("20", "100", "1,000"))
    runtime.axvline(20, color=stage.INK, linewidth=1, linestyle=":")
    for index, (group, color) in enumerate(
        zip(
            samples,
            (stage.BASE, stage.CANDIDATE, stage.DIAGNOSTIC),
            strict=True,
        )
    ):
        runtime.scatter(
            group,
            [index + (n % 5 - 2) * 0.045 for n in range(len(group))],
            c=color,
            s=15,
            alpha=0.55,
            linewidths=0,
        )
        middle = clock[modes[index]]["median_cpu_ms"]
        runtime.vlines(middle, index - 0.15, index + 0.15, color=color, linewidth=2)
        runtime.annotate(
            f"{middle:.1f} ms",
            (middle, index),
            (0, -21),
            textcoords="offset points",
            ha="center",
            va="center",
            fontsize=9,
        )
    for extension in ("png", "pdf"):
        data = io.BytesIO()
        options = {"metadata": {"CreationDate": None}} if extension == "pdf" else {"dpi": 165}
        fig.savefig(data, format=extension, facecolor="white", **options)
        write(out / f"complete-epoch-proxy.{extension}", data.getvalue())
    stage.plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=run.REPORT)
    args = parser.parse_args()
    summary, sources = summarize()
    out = run.local_output(args.out)
    save_json(out / "qualification.json", summary)
    render(summary, out)
    names = ["qualification.json", "complete-epoch-proxy.png", "complete-epoch-proxy.pdf"]
    if out == run.REPORT:
        names.extend(
            ("PROTOCOL.md", "source-lock.json", *(f"{case}.json.gz" for case in run.CASES))
        )
    save_json(
        out / "evidence-lock.json",
        dict(
            cases=list(run.CASES),
            files={name: stage.sha(out / name) for name in names},
            earlier_thinned_evidence=sources,
            scorer_sha256=stage.sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    main()
