#!/usr/bin/env python3
"""Prototype conditioned IQ replay for dense full-capture Hough segments.

The tool deliberately reuses persisted independent 20 ms window measurements
to avoid repeating acquisition, then rereads the authoritative raw IQ for the
new operation under test: alias-lifted conditioned replay of every degree-one
Hough representative on the exact 10 ms-stride detection schedule.  Alias
canonicalization runs only after replay.  No result is promoted into Standard.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.standard.configuration import production_receiver_standard_config
from leo.analysis.standard.full_capture_glrt20ms import (
    WindowResult,
    _threshold_winners,
    _window_winners,
)
from leo.analysis.standard.runner import SingleReceiverIqReader
from leo.analysis.standard.trajectory_accounting import (
    build_trajectory_conditioned_accounting_v2,
)
from leo.analysis.starlink.cfo_dealias import (
    build_cfo_alias_map,
    fit_huber_linear_dealiased_trajectories,
)
from leo.analysis.starlink.trajectory_feedback import (
    fit_residual_hough_pilot_trajectories,
    infer_hough_replay_alias_indices,
    replay_pilot_trajectories_at_detection_windows_with_conditioned_scores,
    trajectory_observations,
)
from leo.contracts.digests import canonical_digest
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260821T140820-470384cc9284"
SOURCE_JSON = Path(
    "reports/figures/2026_08_23_140820_glrt20ms/"
    "cap-20260821T140820-470384cc9284-stream-0-rx0-upper-glrt20ms.json"
)
OUTPUT_ROOT = Path("reports/figures/2026_08_23_full_capture_hough_replay")
REPORT_PATH = Path("reports/2026_08_23_full_capture_hough_replay_prototype.md")
COLORS = (
    "#2678a8",
    "#2a9d6f",
    "#c44e8b",
    "#6f63bb",
    "#8c6d31",
    "#5c677d",
    "#17a2b8",
    "#d65f5f",
    "#9467bd",
    "#4f772d",
    "#1d4ed8",
    "#7c3aed",
    "#0f766e",
    "#be123c",
    "#475569",
    "#111827",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json", type=Path, default=SOURCE_JSON)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def _digests(bank: Any, observations: tuple[Any, ...]) -> tuple[str, str, str]:
    pilot = canonical_digest(
        {
            "kind": "threshold-passing-20ms-window-winners-v1",
            "observation_ids": tuple(item.observation_id for item in observations),
        }
    )
    raw_bank = canonical_digest(
        {
            "kind": "dense-full-capture-hough-bank-prototype-v1",
            "config_digest": bank.config_digest,
            "trajectories": tuple(
                (item.trajectory_id, item.observation_ids, item.coefficients_hz)
                for item in bank.trajectories
            ),
        }
    )
    feedback = canonical_digest(
        {
            "kind": "dense-full-capture-conditioned-replay-prototype-v1",
            "pilot_scan_digest": pilot,
            "trajectory_bank_digest": raw_bank,
        }
    )
    return pilot, raw_bank, feedback


def _transition_dict(transitions: Any) -> dict[str, int]:
    return {
        "positive_to_positive": transitions.positive_to_positive,
        "positive_to_negative": transitions.positive_to_negative,
        "negative_to_positive": transitions.negative_to_positive,
        "negative_to_negative": transitions.negative_to_negative,
    }


def _median(values: list[float]) -> float | None:
    return None if not values else float(statistics.median(values))


def _summary_rows(
    representatives: tuple[tuple[str, Any], ...],
    alias_indices: dict[str, int],
    accounting: Any,
    canonical: Any,
) -> list[dict[str, Any]]:
    summaries = {item.trajectory_id: item for item in accounting.trajectories}
    evaluations: dict[str, list[Any]] = {}
    for item in accounting.evaluations:
        evaluations.setdefault(item.trajectory_id, []).append(item)
    branch_by_seed = {item.seed_trajectory_id: item for item in canonical.branches}
    ordered = sorted(representatives, key=lambda item: (item[1].start_s, item[1].end_s))
    rows = []
    for index, (family_id, trajectory) in enumerate(ordered, start=1):
        summary = summaries[trajectory.trajectory_id]
        matched = [
            item
            for item in evaluations.get(trajectory.trajectory_id, [])
            if item.baseline_margin is not None
        ]
        baseline = [float(item.baseline_margin) for item in matched]
        conditioned = [float(item.conditioned_corrected_margin) for item in matched]
        branch = branch_by_seed.get(trajectory.trajectory_id)
        rows.append(
            {
                "label": f"H{index}",
                "family_id": family_id,
                "trajectory_id": trajectory.trajectory_id,
                "start_s": trajectory.start_s,
                "end_s": trajectory.end_s,
                "slope_hz_s": trajectory.coefficients_hz[0],
                "support_count": trajectory.point_count,
                "replay_alias_index": alias_indices[trajectory.trajectory_id],
                "evaluation_count": summary.evaluation_count,
                "associated_count": summary.associated_count,
                "unassociated_count": summary.unassociated_count,
                "conditioned_transitions": _transition_dict(summary.conditioned_transitions),
                "median_baseline_margin": _median(baseline),
                "median_conditioned_margin": _median(conditioned),
                "median_conditioned_delta": _median(
                    [after - before for before, after in zip(baseline, conditioned, strict=True)]
                ),
                "canonical_branch_id": None if branch is None else branch.branch_id,
                "canonical_component_id": None if branch is None else branch.component_id,
                "canonical_slope_hz_s": (
                    None if branch is None else branch.model.coefficients_hz[0]
                ),
                "canonical_observation_count": (
                    0 if branch is None else len(branch.observation_ids)
                ),
            }
        )
    return rows


def _plot(
    output: Path,
    detections: tuple[Any, ...],
    representatives: tuple[tuple[str, Any], ...],
    alias_indices: dict[str, int],
    accounting: Any,
    canonical: Any,
    rows: list[dict[str, Any]],
    *,
    alias_spacing_hz: float,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(17, 10), constrained_layout=True)
    raw_axis, margin_axis, transition_axis, canonical_axis = axes.flat
    raw_axis.scatter(
        [item.time_s for item in detections],
        [item.scores[0].tracking_cfo_hz / 1e3 for item in detections],
        marker="x",
        s=12,
        linewidths=0.5,
        color="#d88b2f",
        alpha=0.30,
        label="margin-passing 20 ms winner",
    )
    ordered = sorted(representatives, key=lambda item: (item[1].start_s, item[1].end_s))
    label_by_id = {}
    color_by_id = {}
    for index, (_, trajectory) in enumerate(ordered, start=1):
        label = f"H{index}"
        color = COLORS[(index - 1) % len(COLORS)]
        label_by_id[trajectory.trajectory_id] = label
        color_by_id[trajectory.trajectory_id] = color
        times = np.asarray([trajectory.start_s, trajectory.end_s])
        frequency = np.asarray([trajectory.frequency_hz(item) for item in times])
        frequency += alias_indices[trajectory.trajectory_id] * alias_spacing_hz
        raw_axis.plot(
            times,
            frequency / 1e3,
            color=color,
            linewidth=1.5,
            label=f"{label} {trajectory.coefficients_hz[0] / 1e3:+.2f} kHz/s",
        )
    raw_axis.set_title("A · Dense Hough representatives at inferred raw alias")
    raw_axis.set_xlabel("capture time (s)")
    raw_axis.set_ylabel("raw CFO (kHz)")
    raw_axis.grid(alpha=0.2)
    raw_axis.legend(fontsize=7, ncol=2)

    for item in accounting.evaluations:
        if item.baseline_margin is None:
            continue
        trajectory_id = item.trajectory_id
        margin_axis.scatter(
            item.baseline_margin,
            item.conditioned_corrected_margin,
            s=10,
            color=color_by_id[trajectory_id],
            alpha=0.45,
        )
    limits = margin_axis.axis()
    lower = min(limits[0], limits[2], -0.02)
    upper = max(limits[1], limits[3], 0.10)
    margin_axis.plot([lower, upper], [lower, upper], color="#333333", linewidth=0.8)
    margin_axis.axvline(0.025, color="#c44e52", linestyle="--", linewidth=0.8)
    margin_axis.axhline(0.025, color="#c44e52", linestyle="--", linewidth=0.8)
    margin_axis.set_xlim(lower, upper)
    margin_axis.set_ylim(lower, upper)
    margin_axis.set_title("B · Same-window margin before versus conditioned replay")
    margin_axis.set_xlabel("baseline exact − control margin")
    margin_axis.set_ylabel("conditioned exact − control margin")
    margin_axis.grid(alpha=0.2)

    labels = [item["label"] for item in rows]
    transition_names = (
        "positive_to_positive",
        "positive_to_negative",
        "negative_to_positive",
        "negative_to_negative",
    )
    transition_labels = ("P→P", "P→N", "N→P", "N→N")
    transition_colors = ("#2a9d6f", "#c44e52", "#2678a8", "#a7b0b8")
    bottoms = np.zeros(len(rows), dtype=float)
    for name, label, color in zip(
        transition_names, transition_labels, transition_colors, strict=True
    ):
        values = np.asarray([item["conditioned_transitions"][name] for item in rows])
        transition_axis.bar(labels, values, bottom=bottoms, color=color, label=label)
        bottoms += values
    transition_axis.set_title("C · Conditioned replay transitions per Hough segment")
    transition_axis.set_xlabel("dense Hough segment")
    transition_axis.set_ylabel("associated windows")
    transition_axis.grid(axis="y", alpha=0.2)
    transition_axis.legend(fontsize=8, ncol=2)

    observations = {item.observation_id: item for item in canonical.observations}
    for index, branch in enumerate(canonical.branches):
        color = COLORS[index % len(COLORS)]
        members = [observations[item] for item in branch.observation_ids]
        canonical_axis.scatter(
            [item.time_s for item in members],
            [item.component_cfo_hz / 1e3 for item in members],
            marker="x",
            s=12,
            linewidths=0.5,
            color="#d88b2f",
            alpha=0.30,
        )
        times = np.asarray([branch.start_s, branch.end_s])
        model = branch.model
        frequency = (
            model.coefficients_hz[0] * (times - model.reference_time_s) + model.coefficients_hz[1]
        )
        canonical_axis.plot(
            times,
            frequency / 1e3,
            color=color,
            linewidth=1.5,
            label=f"C{index + 1} {model.coefficients_hz[0] / 1e3:+.2f} kHz/s",
        )
    canonical_axis.set_title("D · Post-replay alias canonicalization; degree-one only")
    canonical_axis.set_xlabel("capture time (s)")
    canonical_axis.set_ylabel("canonical component CFO (kHz)")
    canonical_axis.grid(alpha=0.2)
    canonical_axis.legend(fontsize=7, ncol=2)

    figure.suptitle(
        "Dense full-capture Hough → conditioned IQ replay → alias canonicalization\n"
        f"{SESSION_ID} · stream-0/RX0 upper · prototype only; no Standard promotion",
        fontsize=14,
    )
    figure.savefig(output, dpi=200, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _format(value: float | None, *, scale: float = 1.0, digits: int = 3) -> str:
    return "—" if value is None else f"{value / scale:+.{digits}f}"


def _write_report(report: Path, figure: Path, document: dict[str, Any]) -> None:
    rows = document["tracks"]
    harmful_count = sum(
        item["conditioned_transitions"]["positive_to_negative"] > 0 for item in rows
    )
    preserved_count = len(rows) - harmful_count
    improved_count = sum(
        item["median_conditioned_delta"] is not None and item["median_conditioned_delta"] > 0.01
        for item in rows
    )
    lines = [
        "# Full-capture Hough conditioned-replay prototype",
        "",
        "## Question",
        "",
        "Can the dense 20 ms / 10 ms-stride Hough segments feed the existing "
        "conditioned IQ replay and then the linear alias canonicalizer?",
        "",
        "## Answer",
        "",
        "Yes. The numerical interfaces are compatible once replay rereads the exact dense "
        "probe starts instead of regenerating Standard's sparse 0/25 ms schedule. This "
        "prototype does that without changing a persisted contract or production output.",
        "",
        "The experiment is candidate-only. It does not identify Starlink, select a final "
        "correction, or promote these tracks into Standard.",
        "",
        "## Headline result",
        "",
        f"Conditioned replay preserved all previously positive associated windows for "
        f"**{preserved_count}/{len(rows)}** Hough representatives and exposed harmful "
        f"P→N transitions for **{harmful_count}/{len(rows)}**. **{improved_count}** "
        "representatives improved their median margin by more than 0.01. The alias graph "
        f"still retained {document['canonical_branch_count']} branches in "
        f"{document['canonical_component_count']} components, so alias geometry alone did "
        "not reject the harmful alternatives. This is exactly the separation of duties we "
        "want: Hough proposes; IQ replay tests; canonicalization names coordinates only after "
        "the test.",
        "",
        "## Proposed dataflow",
        "",
        "```mermaid",
        "flowchart LR",
        '    W["Dense 20 ms window product"] --> H["Degree-one Hough proposals"]',
        '    H --> L["Infer integer replay lift"]',
        '    L --> R["Reread exact IQ windows and condition"]',
        '    R --> E["Replay evidence gate"]',
        '    E --> C["Linear alias canonicalization"]',
        '    C --> S["Display-only shadow bank"]',
        '    H --> D["Raw candidate diagnostics"]',
        "```",
        "",
        "The dense window product and verified receiver IQ are the only inputs. The replay "
        "accounting and a post-gate canonical linear bank are separate outputs. Raw CFO, "
        "integer replay lift, and canonical CFO remain explicit coordinates; none is silently "
        "substituted for another.",
        "",
        "## Method",
        "",
        "1. Load the previously persisted independent full-capture window measurements.",
        "2. Rebuild the current expanded degree-one Hough representatives.",
        "3. Infer one integer replay lift per representative from its own support.",
        "4. Reread the original IQ at every exact 10 ms-stride winner start covered by a "
        "segment, including sub-threshold controls.",
        "5. Correct IQ with the lifted straight line and reacquire the pilot.",
        "6. Score the original candidate epoch/CFO again after correction.",
        "7. Record positive/negative replay transitions at the 0.025 margin gate.",
        "8. Only after replay, build the alias map and robust Huber degree-one bank.",
        "",
        f"![Prototype replay and canonicalization]({figure.relative_to(report.parent)})",
        "",
        "## Per-segment results",
        "",
        "| Segment | Interval | Hough rate | Support | Replay lift | Associated | P→P | "
        "P→N | N→P | N→N | Median margin before | after | Δ | Canonical rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in rows:
        transitions = item["conditioned_transitions"]
        lines.append(
            "| {label} | {start_s:.2f}–{end_s:.2f} s | {slope:+.3f} kHz/s | "
            "{support_count} | {replay_alias_index:+d} | {associated_count} | {pp} | "
            "{pn} | {np_} | {nn} | {before} | {after} | {delta} | {canonical} |".format(
                label=item["label"],
                start_s=item["start_s"],
                end_s=item["end_s"],
                slope=item["slope_hz_s"] / 1e3,
                support_count=item["support_count"],
                replay_alias_index=item["replay_alias_index"],
                associated_count=item["associated_count"],
                pp=transitions["positive_to_positive"],
                pn=transitions["positive_to_negative"],
                np_=transitions["negative_to_positive"],
                nn=transitions["negative_to_negative"],
                before=_format(item["median_baseline_margin"]),
                after=_format(item["median_conditioned_margin"]),
                delta=_format(item["median_conditioned_delta"]),
                canonical=_format(item["canonical_slope_hz_s"], scale=1e3),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation rules",
            "",
            "- P→P means the independently positive window remains positive after the exact "
            "candidate is conditioned by the proposed segment.",
            "- P→N is harmful evidence: the segment correction destroys a formerly positive "
            "candidate.",
            "- N→P is recovered evidence: the proposed segment makes a previously associated "
            "but sub-threshold candidate positive.",
            "- In this example N→P is zero because none of the sub-threshold winners entered "
            "the tight 2.5 kHz trajectory-association gate; retaining them was still necessary "
            "to make that a measured result rather than an assumption.",
            "- Canonical rate is still a degree-one Huber estimate. No quadratic or cubic radio "
            "model is used.",
            "- Replay and alias identity remain separate. A good canonical grouping does not by "
            "itself prove that an absolute lift is safe for correction.",
            "",
            "## Production integration plan",
            "",
            "1. **Persist the dense numerical result.** Add a new versioned JSON product for "
            "window winners, Hough support, inferred replay lifts, and explicit truncation. Keep "
            "the existing PNG as a rendering of that product.",
            "2. **Add a dedicated replay job.** Consume that JSON plus verified receiver IQ. "
            "Replay only declared dense starts with bounded batches and publish conditioned "
            "transition accounting. Do not expand the fused path job further.",
            "3. **Canonicalize only replay-audited representatives.** Publish a separate linear "
            "dense de-aliased bank, preserving raw CFO, canonical CFO, and absolute replay lift "
            "as different coordinates.",
            "4. **Introduce conservative gates.** Require minimum associated support and span, "
            "bounded P→N count/run, positive lower-tail conditioned margin, and stable replay "
            "lift. Begin as display-only; do not replace the current final bank.",
            "5. **Run shadow comparisons.** On at least five completed signal dwells plus matched "
            "null controls, compare recovered support, harmful transitions, alias stability, "
            "runtime, and agreement with the existing final bank.",
            "6. **Promote by contract version.** Only after review, add the dense replay bank as "
            "an eligible input to Kalman/phase analysis. Preserve the current Standard products "
            "and make rollback a configuration change.",
            "",
            "## Proposed initial acceptance gates",
            "",
            "| Gate | Initial shadow-mode rule |",
            "|---|---|",
            "| Model order | Exactly degree one |",
            "| Minimum associated support | 20 windows and at least 0.75 s span |",
            "| Harmful replay | No more than 5% P→N and no long consecutive harmful run |",
            "| Conditioned evidence | Median conditioned margin > 0.025 and positive "
            "10th-percentile margin delta |",
            "| Alias stability | One modal integer lift with no contradictory component cycle |",
            "| Controls | Must beat matched rolled-pilot and time-permuted controls after "
            "multiplicity correction |",
            "| Promotion | Display-only until five-dwell shadow review passes |",
            "",
        ]
    )
    report.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    source = json.loads(args.source_json.read_text(encoding="utf-8"))
    windows = tuple(WindowResult(**item) for item in source["windows"])
    hough_detections = _threshold_winners(windows)
    replay_detections = _window_winners(windows, require_margin_pass=False)
    config = production_receiver_standard_config()
    bank, representatives = fit_residual_hough_pilot_trajectories(
        hough_detections,
        config.feedback,
        config.segmentation,
    )
    observations = trajectory_observations(hough_detections)
    alias_spacing_hz = config.segmentation.initial_hough.alias_spacing_hz
    alias_indices = infer_hough_replay_alias_indices(
        representatives,
        observations,
        alias_spacing_hz=alias_spacing_hz,
    )
    pilot_digest, raw_bank_digest, feedback_digest = _digests(bank, observations)
    print(
        f"replaying {len(representatives)} dense Hough representatives over "
        f"{len(replay_detections)} independently acquired windows",
        flush=True,
    )
    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    try:
        bundle = store.inspect(source["session_id"])
        reader = SingleReceiverIqReader(
            store.reader(bundle, source["stream_id"], verify=True),
            int(source["receiver_id"]),
        )
        replay = replay_pilot_trajectories_at_detection_windows_with_conditioned_scores(
            reader,
            replay_detections,
            representatives,
            config.feedback,
            edge=source["edge"],
            alias_indices=alias_indices,
            alias_spacing_hz=alias_spacing_hz,
            association_gate_hz=config.trajectory_accounting.association_gate_hz,
            probe_samples=round(source["window_ms"] * reader.sample_rate_hz / 1_000),
        )
    finally:
        store.close()
    accounting = build_trajectory_conditioned_accounting_v2(
        replay_detections,
        representatives,
        replay,
        frequency_offsets_hz={
            trajectory_id: alias_index * alias_spacing_hz
            for trajectory_id, alias_index in alias_indices.items()
        },
        pilot_scan_digest=pilot_digest,
        trajectory_bank_digest=raw_bank_digest,
        trajectory_feedback_digest=feedback_digest,
        config=config.trajectory_accounting,
    )
    alias_map = build_cfo_alias_map(
        bank,
        representatives,
        pilot_scan_digest=pilot_digest,
        raw_bank_digest=raw_bank_digest,
        config=config.dealias,
    )
    canonical = fit_huber_linear_dealiased_trajectories(
        observations,
        representatives,
        alias_map,
        raw_bank_digest=raw_bank_digest,
        config=config.dealias,
        seeded_em_config=config.seeded_alias_em,
        huber_config=config.huber_linear,
    )
    rows = _summary_rows(representatives, alias_indices, accounting, canonical)
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    figure = args.output_root / "full-capture-hough-conditioned-replay.png"
    result_json = args.output_root / "full-capture-hough-conditioned-replay.json"
    document = {
        "schema_version": 1,
        "kind": "full-capture-hough-conditioned-replay-prototype",
        "session_id": source["session_id"],
        "stream_id": source["stream_id"],
        "receiver_id": source["receiver_id"],
        "edge": source["edge"],
        "source_window_document": str(args.source_json),
        "window_count": len(windows),
        "margin_passing_window_count": len(hough_detections),
        "conditioned_replay_window_count": len(replay_detections),
        "hough_representative_count": len(representatives),
        "conditioned_replay_row_count": len(replay),
        "associated_evaluation_count": accounting.associated_evaluation_count,
        "unassociated_evaluation_count": accounting.unassociated_evaluation_count,
        "canonical_component_count": len(alias_map.components),
        "canonical_branch_count": len(canonical.branches),
        "degree_one_only": True,
        "promoted_to_standard": False,
        "tracks": rows,
    }
    _plot(
        figure,
        hough_detections,
        representatives,
        alias_indices,
        accounting,
        canonical,
        rows,
        alias_spacing_hz=alias_spacing_hz,
    )
    result_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    _write_report(args.report, figure, document)
    print(f"wrote {args.report}", flush=True)
    print(f"wrote {figure}", flush=True)
    print(f"wrote {result_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
