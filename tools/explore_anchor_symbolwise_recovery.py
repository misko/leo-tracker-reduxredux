#!/usr/bin/env python3
"""Compare segment-recovery policies for Anchor-8 and current symbolwise.

The policies deliberately stay outside the Standard pipeline:

* the current fixed score gate;
* a five-sigma gate estimated only from the negative side of the control margin;
* seeded hysteresis, where high-score points authorize neighboring low-score
  points inside the same conservative CFO component; and
* Anchor/Symbolwise consensus, where either method may seed a common segment;
  and
* a GLRT-64-seeded robust CFO corridor, which tolerates acquisition jitter
  without lowering the method score across the whole recording.

All outputs are exploratory candidate segments. Thresholds are displayed on the
plots and are not production-calibrated.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

DEFAULT_INPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-pilot-methods.csv"
)


@dataclass(frozen=True, slots=True)
class RecoveryPolicy:
    key: str
    label: str
    selection: np.ndarray
    tracker_kind: str = "continuity"


def _module(name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-directory", type=Path, default=Path("artifacts"))
    return parser.parse_args()


def _negative_side_sigma(scores: np.ndarray) -> float:
    negative = np.abs(scores[scores < 0])
    if not negative.size:
        raise ValueError("a negative control-margin tail is required")
    # median(|N(0,sigma)|) = 0.67448975 sigma, including either half.
    return float(np.median(negative) / 0.6744897501960817)


def _tracklets(tracker, candidates, selection, *, minimum_points=3):
    return tracker.continuity_tracks(
        candidates,
        selection,
        maximum_gap_s=0.30,
        base_frequency_gate_hz=3_000.0,
        maximum_slope_hz_per_s=30_000.0,
        minimum_points=minimum_points,
    )


def _hysteresis_selection(
    tracker,
    candidates,
    scores: np.ndarray,
    *,
    high: float,
    low: float,
    minimum_high_points: int,
) -> np.ndarray:
    low_selection = scores >= low
    high_selection = scores >= high
    retained = np.zeros(len(candidates), dtype=bool)
    for track in _tracklets(tracker, candidates, low_selection):
        if (
            sum(bool(high_selection[index]) for index in track.candidate_indexes)
            < minimum_high_points
        ):
            continue
        retained[np.asarray(track.candidate_indexes, dtype=int)] = True
    return retained


def _policies(
    tracker,
    method: str,
    candidates,
    anchor_scores: np.ndarray,
    symbolwise_scores: np.ndarray,
    glrt64_scores: np.ndarray,
) -> tuple[RecoveryPolicy, ...]:
    scores = anchor_scores if method == "anchor8" else symbolwise_scores
    baseline = 0.40 if method == "anchor8" else 0.05
    sigma = _negative_side_sigma(scores)
    noise_gate = 5 * sigma
    if method == "anchor8":
        hysteresis = _hysteresis_selection(
            tracker,
            candidates,
            scores,
            high=0.15,
            low=0.05,
            minimum_high_points=3,
        )
        hysteresis_label = "Seeded hysteresis · high 0.15 / low 0.05 / 3 seeds"
    else:
        hysteresis = _hysteresis_selection(
            tracker,
            candidates,
            scores,
            high=0.02,
            low=0.007,
            minimum_high_points=3,
        )
        hysteresis_label = "Seeded hysteresis · high 0.020 / low 0.007 / 3 seeds"
    consensus = (anchor_scores >= 0.15) | (symbolwise_scores >= 0.05)
    return (
        RecoveryPolicy("baseline", f"Current fixed gate ≥ {baseline:.3f}", scores >= baseline),
        RecoveryPolicy(
            "negative_noise",
            f"Negative-tail noise model · 5σ ≥ {noise_gate:.4f}",
            scores >= noise_gate,
        ),
        RecoveryPolicy("hysteresis", hysteresis_label, hysteresis),
        RecoveryPolicy(
            "consensus",
            "Cross-method seed · Anchor ≥ 0.15 or Symbolwise ≥ 0.05",
            consensus,
        ),
        RecoveryPolicy(
            "glrt64_corridor",
            "GLRT-64 seeds ≥ 0.18 · robust ±8 kHz corridor / 0.6 s gap",
            glrt64_scores >= 0.18,
            "robust_corridor",
        ),
    )


def _tracks_for_policy(tracker, candidates, policy: RecoveryPolicy):
    if policy.tracker_kind == "continuity":
        return _tracklets(tracker, candidates, policy.selection)
    if policy.tracker_kind == "robust_corridor":
        return tracker.robust_quadratic_tracks(
            candidates,
            policy.selection,
            residual_gate_hz=8_000.0,
            maximum_gap_s=0.60,
            minimum_points=8,
            iterations=5_000,
            maximum_tracks=12,
        )
    raise ValueError(f"unsupported tracker kind: {policy.tracker_kind}")


def _render_panel(axis, candidates, scores, policy, tracks, method_label):
    times = np.asarray([item.time_s for item in candidates])
    frequency = np.asarray([item.refined_cfo_hz for item in candidates]) / 1_000
    axis.scatter(times, frequency, s=5, color="#aaaaaa", alpha=0.12)
    selected = policy.selection
    if np.any(selected):
        axis.scatter(
            times[selected],
            frequency[selected],
            c=scores[selected],
            s=10,
            cmap="viridis",
            alpha=0.72,
        )
    colors = ("#d1495b", "#0077b6", "#f77f00", "#6a4c93", "#2a9d8f", "#bc6c25")
    for track in tracks:
        grid = np.linspace(track.start_s, track.end_s, 200)
        color = colors[(track.track_id - 1) % len(colors)]
        axis.plot(grid, track.predict(grid) / 1_000, color=color, linewidth=1.8)
        axis.text(
            track.start_s,
            float(track.predict(track.start_s)) / 1_000,
            f" T{track.track_id}",
            color=color,
            fontsize=8,
            va="bottom",
        )
    axis.set_title(policy.label, loc="left", fontweight="bold")
    axis.set_ylabel(f"{method_label} tracking CFO (kHz)")
    axis.grid(alpha=0.2)


def _render(output, method_label, candidates, scores, policies, results):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise SystemExit(
            "run with: uv run --with 'matplotlib>=3.10,<4' python "
            "tools/explore_anchor_symbolwise_recovery.py"
        ) from error
    figure, axes = plt.subplots(
        len(policies),
        1,
        figsize=(16, 4 * len(policies)),
        sharex=True,
        constrained_layout=True,
    )
    for axis, policy, tracks in zip(axes, policies, results, strict=True):
        _render_panel(axis, candidates, scores, policy, tracks, method_label)
    axes[-1].set_xlabel("Elapsed recording time (s)")
    figure.suptitle(
        f"{method_label} segment-recovery experiments · candidate-only",
        fontweight="bold",
    )
    figure.savefig(output, dpi=160, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def main() -> int:
    args = _arguments()
    tracker = _module("anchor_symbolwise_tracker", "explore_glrt64_tracks.py")
    family = _module("anchor_symbolwise_family", "explore_all_pilot_method_tracks.py")
    with args.input.open("r", encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source))
    anchor_spec = next(spec for spec in family.METHODS if spec.key == "anchor8")
    symbolwise_spec = next(spec for spec in family.METHODS if spec.key == "symbolwise")
    anchor_candidates = family._candidates(tracker, rows, anchor_spec)
    symbolwise_candidates = family._candidates(tracker, rows, symbolwise_spec)
    if tuple(item.time_s for item in anchor_candidates) != tuple(
        item.time_s for item in symbolwise_candidates
    ):
        raise ValueError("Anchor-8 and Symbolwise candidate timelines differ")
    anchor_scores = np.asarray([item.glrt64_margin for item in anchor_candidates])
    symbolwise_scores = np.asarray([item.glrt64_margin for item in symbolwise_candidates])
    glrt64_scores = np.asarray([float(row["glrt64_margin"]) for row in rows])
    if len(glrt64_scores) != len(symbolwise_candidates):
        raise ValueError("GLRT-64 and Symbolwise candidate timelines differ")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    stem = args.input.stem.removesuffix("-pilot-methods")
    outputs = []
    for key, label, candidates, scores in (
        ("anchor8", "Anchor-8", anchor_candidates, anchor_scores),
        ("symbolwise", "Current symbolwise", symbolwise_candidates, symbolwise_scores),
    ):
        policies = _policies(
            tracker,
            key,
            candidates,
            anchor_scores,
            symbolwise_scores,
            glrt64_scores,
        )
        results = tuple(_tracks_for_policy(tracker, candidates, policy) for policy in policies)
        output = args.output_directory / f"{stem}-{key}-segment-recovery.png"
        _render(output, label, candidates, scores, policies, results)
        document = {
            "method": key,
            "input": str(args.input.resolve()),
            "input_sha256": _sha256(args.input),
            "production_calibrated": False,
            "one_candidate_per_timestamp_limitation": True,
            "policies": [
                {
                    "key": policy.key,
                    "label": policy.label,
                    "tracker_kind": policy.tracker_kind,
                    "selected_count": int(np.count_nonzero(policy.selection)),
                    "tracks": [asdict(track) for track in tracks],
                }
                for policy, tracks in zip(policies, results, strict=True)
            ],
            "png": str(output.resolve()),
            "png_sha256": _sha256(output),
        }
        metadata = output.with_suffix(".json")
        metadata.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        outputs.append(
            {
                "method": key,
                "png": str(output.resolve()),
                "metadata": str(metadata.resolve()),
                "policies": {
                    policy.key: len(tracks)
                    for policy, tracks in zip(policies, results, strict=True)
                },
            }
        )
    print(json.dumps({"outputs": outputs}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
