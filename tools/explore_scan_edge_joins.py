#!/usr/bin/env python3
"""Read-only exploratory edge-merge and channel-switch analysis for one hop scan."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTracklet,
    PersistentHopTrajectoryConfig,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.persistent_hop_trajectory import (
    project_fractional_persistent_hop_candidates,
)
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2

CANONICAL_RF_HZ = 11_200_000_000.0
EDGE_OVERLAP_MIN_S = 5.0
EDGE_RATE_GATE_HZ_PER_S = 100.0
EDGE_SHARED_RMS_GATE_HZ = 450.0
EDGE_RMS_RATIO_GATE = 2.0
EDGE_DELTA_BIC_GATE = 60.0
SAME_EDGE_OVERLAP_TOLERANCE_S = 1.05
SWITCH_OVERLAP_TOLERANCE_S = 1.05
SWITCH_MAXIMUM_GAP_S = 4.0


@dataclass(frozen=True)
class Series:
    tracklet: PersistentHopTracklet
    t_s: np.ndarray
    y_hz: np.ndarray
    weight: np.ndarray
    segment: np.ndarray

    @property
    def channel(self) -> int:
        return int(self.tracklet.lane_key[0])

    @property
    def edge(self) -> str:
        return str(self.tracklet.lane_key[1].value)

    @property
    def receiver(self) -> int:
        return int(self.tracklet.lane_key[2])

    @property
    def actual_rf_hz(self) -> float:
        return float(self.tracklet.lane_key[3])

    @property
    def start_s(self) -> float:
        return float(np.min(self.t_s))

    @property
    def end_s(self) -> float:
        return float(np.max(self.t_s))


@dataclass(frozen=True)
class Fit:
    degree: int
    t_ref_s: float
    segments: tuple[str, ...]
    coefficients: np.ndarray
    covariance: np.ndarray
    predicted_hz: np.ndarray
    residual_hz: np.ndarray
    rms_hz: float
    weighted_rms_hz: float
    rss_hz2: float
    bic: float
    parameter_count: int

    def dynamic(self, t_s: np.ndarray) -> np.ndarray:
        x = np.asarray(t_s, dtype=float) - self.t_ref_s
        result = np.zeros_like(x)
        offset = len(self.segments)
        for power in range(1, self.degree + 1):
            result += self.coefficients[offset + power - 1] * x**power
        return result

    def derivative(self, t_s: float, order: int = 1) -> tuple[float, float]:
        if order < 1 or order > self.degree:
            return 0.0, math.inf
        x = float(t_s) - self.t_ref_s
        row = np.zeros(self.coefficients.size)
        offset = len(self.segments)
        for power in range(order, self.degree + 1):
            factor = math.factorial(power) / math.factorial(power - order)
            row[offset + power - 1] = factor * x ** (power - order)
        value = float(row @ self.coefficients)
        variance = max(float(row @ self.covariance @ row), 0.0)
        return value, math.sqrt(variance)

    def segment_offset(self, segment: str) -> float:
        return float(self.coefficients[self.segments.index(segment)])


@dataclass
class PhysicalTrack:
    track_id: str
    members: list[Series]

    @property
    def channel(self) -> int:
        return self.members[0].channel

    @property
    def receiver(self) -> int:
        return self.members[0].receiver

    @property
    def start_s(self) -> float:
        return min(item.start_s for item in self.members)

    @property
    def end_s(self) -> float:
        return max(item.end_s for item in self.members)

    @property
    def edges(self) -> tuple[str, ...]:
        return tuple(sorted({item.edge for item in self.members}))

    @property
    def label(self) -> str:
        edge = "LU" if len(self.edges) == 2 else self.edges[0][0].upper()
        return f"CH{self.channel}{edge} RX{self.receiver}"


@dataclass
class ChannelEpisode:
    episode_id: str
    tracks: list[PhysicalTrack]

    @property
    def track_id(self) -> str:
        return self.episode_id

    @property
    def members(self) -> list[Series]:
        return [member for track in self.tracks for member in track.members]

    @property
    def channel(self) -> int:
        return self.tracks[0].channel

    @property
    def receivers(self) -> tuple[int, ...]:
        return tuple(sorted({item.receiver for item in self.tracks}))

    @property
    def start_s(self) -> float:
        return min(item.start_s for item in self.tracks)

    @property
    def end_s(self) -> float:
        return max(item.end_s for item in self.tracks)

    @property
    def edges(self) -> tuple[str, ...]:
        return tuple(sorted({edge for item in self.tracks for edge in item.edges}))

    @property
    def label(self) -> str:
        edge = "LU" if len(self.edges) == 2 else self.edges[0][0].upper()
        receivers = "+".join(str(item) for item in self.receivers)
        return f"CH{self.channel}{edge} RX{receivers}"


def _arrays(series: list[Series]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    return (
        np.concatenate([item.t_s for item in series]),
        np.concatenate([item.y_hz for item in series]),
        np.concatenate([item.weight for item in series]),
        np.concatenate([item.segment for item in series]),
    )


def _fit(
    series: list[Series],
    degree: int,
    *,
    t_ref_s: float | None = None,
) -> Fit:
    t_s, y_hz, evidence_weight, segment = _arrays(series)
    segments = tuple(sorted(set(str(item) for item in segment)))
    if t_ref_s is None:
        t_ref_s = float(np.average(t_s, weights=evidence_weight))
    x = t_s - t_ref_s
    design = np.zeros((t_s.size, len(segments) + degree), dtype=float)
    for index, name in enumerate(segments):
        design[:, index] = segment == name
    for power in range(1, degree + 1):
        design[:, len(segments) + power - 1] = x**power

    robust_weight = np.ones(t_s.size)
    coefficients = np.zeros(design.shape[1])
    for _ in range(8):
        total_weight = np.maximum(evidence_weight * robust_weight, 1e-9)
        scaled = design * np.sqrt(total_weight)[:, None]
        target = y_hz * np.sqrt(total_weight)
        coefficients, *_ = np.linalg.lstsq(scaled, target, rcond=None)
        residual = y_hz - design @ coefficients
        center = float(np.median(residual))
        scale = 1.4826 * float(np.median(np.abs(residual - center)))
        if not math.isfinite(scale) or scale < 1e-6:
            break
        normalized = np.abs(residual - center) / (1.5 * scale)
        robust_weight = np.ones_like(normalized)
        outside = normalized > 1.0
        robust_weight[outside] = 1.0 / normalized[outside]

    predicted = design @ coefficients
    residual = y_hz - predicted
    final_weight = np.maximum(evidence_weight * robust_weight, 1e-9)
    rss = float(np.sum(residual**2))
    weighted_rss = float(np.sum(final_weight * residual**2))
    parameter_count = design.shape[1]
    dof = max(t_s.size - parameter_count, 1)
    sigma2 = weighted_rss / dof
    information = design.T @ (final_weight[:, None] * design)
    covariance = np.linalg.pinv(information, rcond=1e-12) * sigma2
    bic = t_s.size * math.log(max(rss / t_s.size, 1e-12)) + parameter_count * math.log(t_s.size)
    return Fit(
        degree=degree,
        t_ref_s=t_ref_s,
        segments=segments,
        coefficients=coefficients,
        covariance=covariance,
        predicted_hz=predicted,
        residual_hz=residual,
        rms_hz=math.sqrt(rss / t_s.size),
        weighted_rms_hz=math.sqrt(weighted_rss / float(np.sum(final_weight))),
        rss_hz2=rss,
        bic=bic,
        parameter_count=parameter_count,
    )


def _independent_fit(series_groups: list[list[Series]], degree: int) -> dict[str, object]:
    fits = [_fit(group, degree) for group in series_groups]
    count = sum(sum(item.t_s.size for item in group) for group in series_groups)
    rss = sum(item.rss_hz2 for item in fits)
    parameters = sum(item.parameter_count for item in fits)
    bic = count * math.log(max(rss / count, 1e-12)) + parameters * math.log(count)
    return {
        "fits": fits,
        "rms_hz": math.sqrt(rss / count),
        "rss_hz2": rss,
        "bic": bic,
        "parameter_count": parameters,
    }


def _overlap(left: Series, right: Series) -> float:
    return min(left.end_s, right.end_s) - max(left.start_s, right.start_s)


def _edge_candidates(series: list[Series]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for left_index, left in enumerate(series):
        for right in series[left_index + 1 :]:
            if (
                left.channel != right.channel
                or left.receiver != right.receiver
                or left.edge == right.edge
            ):
                continue
            overlap_s = _overlap(left, right)
            rate_difference = abs(
                left.tracklet.normalized_rate_hz_per_s - right.tracklet.normalized_rate_hz_per_s
            )
            if overlap_s < EDGE_OVERLAP_MIN_S or rate_difference > EDGE_RATE_GATE_HZ_PER_S:
                continue
            shared = _fit([left, right], 3)
            independent = _independent_fit([[left], [right]], 3)
            delta_bic = shared.bic - float(independent["bic"])
            if (
                shared.rms_hz > EDGE_SHARED_RMS_GATE_HZ
                or shared.rms_hz > EDGE_RMS_RATIO_GATE * float(independent["rms_hz"])
                or delta_bic > EDGE_DELTA_BIC_GATE
            ):
                continue
            overlap_mid = (max(left.start_s, right.start_s) + min(left.end_s, right.end_s)) / 2
            shared_rate, shared_rate_se = shared.derivative(overlap_mid, 1)
            individual_rates = []
            for fit in independent["fits"]:
                value, standard_error = fit.derivative(overlap_mid, 1)
                individual_rates.append((value, standard_error))
            finite_individual_se = [item[1] for item in individual_rates if math.isfinite(item[1])]
            resolution_gain = (
                float(np.mean(finite_individual_se)) / shared_rate_se
                if finite_individual_se and shared_rate_se > 0
                else math.nan
            )
            output.append(
                {
                    "left": left,
                    "right": right,
                    "overlap_s": overlap_s,
                    "rate_difference_hz_per_s": rate_difference,
                    "shared_rms_hz": shared.rms_hz,
                    "independent_rms_hz": float(independent["rms_hz"]),
                    "delta_bic": delta_bic,
                    "shared_rate_hz_per_s": shared_rate,
                    "shared_rate_se_hz_per_s": shared_rate_se,
                    "resolution_gain": resolution_gain,
                    "score": delta_bic + shared.rms_hz / 100.0 + rate_difference / 100.0,
                }
            )
    return sorted(output, key=lambda item: (float(item["score"]), float(item["shared_rms_hz"])))


def _build_physical_tracks(
    series: list[Series], candidates: list[dict[str, object]]
) -> tuple[list[PhysicalTrack], list[dict[str, object]]]:
    index_by_id = {item.tracklet.tracklet_id: index for index, item in enumerate(series)}
    parent = list(range(len(series)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    accepted: list[dict[str, object]] = []
    for candidate in candidates:
        left = candidate["left"]
        right = candidate["right"]
        assert isinstance(left, Series) and isinstance(right, Series)
        left_root = root(index_by_id[left.tracklet.tracklet_id])
        right_root = root(index_by_id[right.tracklet.tracklet_id])
        if left_root == right_root:
            continue
        left_members = [series[index] for index in range(len(series)) if root(index) == left_root]
        right_members = [series[index] for index in range(len(series)) if root(index) == right_root]
        if any(
            a.edge == b.edge and _overlap(a, b) > SAME_EDGE_OVERLAP_TOLERANCE_S
            for a in left_members
            for b in right_members
        ):
            continue
        parent[right_root] = left_root
        accepted.append(candidate)

    components: dict[int, list[Series]] = {}
    for index, item in enumerate(series):
        components.setdefault(root(index), []).append(item)
    ordered = sorted(
        components.values(),
        key=lambda members: (min(item.start_s for item in members), members[0].channel),
    )
    tracks = [PhysicalTrack(f"P{index:02d}", members) for index, members in enumerate(ordered, 1)]
    return tracks, accepted


def _build_channel_episodes(
    tracks: list[PhysicalTrack],
) -> tuple[list[ChannelEpisode], list[dict[str, object]]]:
    pair_candidates: list[dict[str, object]] = []
    for left_index, left in enumerate(tracks):
        for right in tracks[left_index + 1 :]:
            if left.channel != right.channel or left.receiver == right.receiver:
                continue
            overlap_s = min(left.end_s, right.end_s) - max(left.start_s, right.start_s)
            if overlap_s < 8.0:
                continue
            midpoint = (max(left.start_s, right.start_s) + min(left.end_s, right.end_s)) / 2
            left_fit = _fit(left.members, 3)
            right_fit = _fit(right.members, 3)
            left_rate, _ = left_fit.derivative(midpoint, 1)
            right_rate, _ = right_fit.derivative(midpoint, 1)
            rate_difference = abs(left_rate - right_rate)
            if rate_difference > 250.0:
                continue
            shared = _fit(left.members + right.members, 3)
            independent = _independent_fit([left.members, right.members], 3)
            delta_bic = shared.bic - float(independent["bic"])
            if (
                shared.rms_hz > 450.0
                or shared.rms_hz > 2.0 * float(independent["rms_hz"])
                or delta_bic > 60.0
            ):
                continue
            pair_candidates.append(
                {
                    "left": left,
                    "right": right,
                    "overlap_s": overlap_s,
                    "rate_difference_hz_per_s": rate_difference,
                    "shared_rms_hz": shared.rms_hz,
                    "independent_rms_hz": independent["rms_hz"],
                    "delta_bic": delta_bic,
                    "score": delta_bic + shared.rms_hz / 100.0 + rate_difference / 100.0,
                }
            )
    pair_candidates.sort(key=lambda item: float(item["score"]))

    index_by_id = {item.track_id: index for index, item in enumerate(tracks)}
    parent = list(range(len(tracks)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    accepted: list[dict[str, object]] = []
    for candidate in pair_candidates:
        left = candidate["left"]
        right = candidate["right"]
        assert isinstance(left, PhysicalTrack) and isinstance(right, PhysicalTrack)
        left_root = root(index_by_id[left.track_id])
        right_root = root(index_by_id[right.track_id])
        if left_root == right_root:
            continue
        left_members = [tracks[index] for index in range(len(tracks)) if root(index) == left_root]
        right_members = [tracks[index] for index in range(len(tracks)) if root(index) == right_root]
        if any(
            a.receiver == b.receiver
            and min(a.end_s, b.end_s) - max(a.start_s, b.start_s) > SAME_EDGE_OVERLAP_TOLERANCE_S
            for a in left_members
            for b in right_members
        ):
            continue
        parent[right_root] = left_root
        accepted.append(candidate)

    components: dict[int, list[PhysicalTrack]] = {}
    for index, item in enumerate(tracks):
        components.setdefault(root(index), []).append(item)
    ordered = sorted(
        components.values(),
        key=lambda members: (min(item.start_s for item in members), members[0].channel),
    )
    episodes = [
        ChannelEpisode(f"E{index:02d}", members) for index, members in enumerate(ordered, 1)
    ]
    return episodes, accepted


def _switch_candidates(tracks: list[ChannelEpisode]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for left_index, first in enumerate(tracks):
        for second in tracks[left_index + 1 :]:
            if first.channel == second.channel:
                continue
            if first.end_s <= second.start_s + SWITCH_OVERLAP_TOLERANCE_S:
                left, right = first, second
            elif second.end_s <= first.start_s + SWITCH_OVERLAP_TOLERANCE_S:
                left, right = second, first
            else:
                continue
            gap_s = right.start_s - left.end_s
            if gap_s < -SWITCH_OVERLAP_TOLERANCE_S or gap_s > SWITCH_MAXIMUM_GAP_S:
                continue
            degree_rows = []
            for degree in (1, 2, 3):
                shared = _fit(left.members + right.members, degree)
                independent = _independent_fit([left.members, right.members], degree)
                boundary_s = (left.end_s + right.start_s) / 2
                left_fit, right_fit = independent["fits"]
                left_rate, left_rate_se = left_fit.derivative(boundary_s, 1)
                right_rate, right_rate_se = right_fit.derivative(boundary_s, 1)
                acceleration_difference = None
                if degree >= 2:
                    left_acceleration, _ = left_fit.derivative(boundary_s, 2)
                    right_acceleration, _ = right_fit.derivative(boundary_s, 2)
                    acceleration_difference = abs(left_acceleration - right_acceleration)
                degree_rows.append(
                    {
                        "degree": degree,
                        "shared": shared,
                        "independent": independent,
                        "delta_bic": shared.bic - float(independent["bic"]),
                        "rate_difference_hz_per_s": abs(left_rate - right_rate),
                        "rate_difference_se_hz_per_s": math.hypot(left_rate_se, right_rate_se),
                        "acceleration_difference_hz_per_s2": acceleration_difference,
                    }
                )
            best = min(degree_rows, key=lambda item: float(item["shared"].bic))
            output.append(
                {
                    "left": left,
                    "right": right,
                    "gap_s": gap_s,
                    "degrees": degree_rows,
                    "best": best,
                }
            )
    return sorted(
        output,
        key=lambda item: (
            float(item["best"]["delta_bic"]),
            float(item["best"]["shared"].rms_hz),
        ),
    )


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 180,
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "axes.grid": True,
            "grid.alpha": 0.2,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def _plot_residuals(tracks: list[PhysicalTrack], output: Path) -> dict[str, dict[str, float]]:
    _style()
    fig, axes = plt.subplots(4, 3, figsize=(16, 12), sharex=True)
    colors = {"lower": "#2878a5", "upper": "#d95f73"}
    markers = {"lower": "o", "upper": "x"}
    aggregate: dict[str, dict[str, float]] = {}
    for channel in range(1, 5):
        aggregate[f"CH{channel}"] = {}
        selected = [item for item in tracks if item.channel == channel]
        for column, degree in enumerate((1, 2, 3)):
            ax = axes[channel - 1, column]
            residuals = []
            for track in selected:
                fit = _fit(track.members, degree)
                cursor = 0
                for member in track.members:
                    count = member.t_s.size
                    values = fit.residual_hz[cursor : cursor + count]
                    cursor += count
                    residuals.extend(values.tolist())
                    ax.scatter(
                        member.t_s,
                        values,
                        s=8,
                        alpha=0.62,
                        c=colors[member.edge],
                        marker=markers[member.edge],
                        linewidths=0.55,
                    )
            rms = math.sqrt(float(np.mean(np.square(residuals)))) if residuals else math.nan
            aggregate[f"CH{channel}"][str(degree)] = rms
            ax.axhline(0, color="#333333", linewidth=0.7)
            ax.set_title(f"CH{channel} · degree {degree} · aggregate RMS {rms:.0f} Hz")
            if column == 0:
                ax.set_ylabel("fit residual (Hz)")
            if channel == 4:
                ax.set_xlabel("device time since scan start (s)")
            ax.set_xlim(0, 300)
    handles = [
        plt.Line2D([], [], color=colors["lower"], marker="o", linestyle="", label="lower edge"),
        plt.Line2D([], [], color=colors["upper"], marker="x", linestyle="", label="upper edge"),
    ]
    fig.legend(handles=handles, loc="upper right", ncol=2, frameon=False)
    fig.suptitle(
        "RF-normalized, per-track offset linear/quadratic/cubic residuals",
        fontsize=14,
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return aggregate


def _plot_edge_merges(
    tracks: list[PhysicalTrack], accepted: list[dict[str, object]], output: Path
) -> None:
    _style()
    merged = [item for item in tracks if len(item.edges) == 2]
    fig, axes = plt.subplots(4, 1, figsize=(16, 11), sharex=True)
    palette = plt.get_cmap("tab10")
    edge_marker = {"lower": "o", "upper": "x"}
    for channel, ax in enumerate(axes, 1):
        selected = [item for item in merged if item.channel == channel]
        for index, track in enumerate(selected):
            fit = _fit(track.members, 3)
            color = palette(index % 10)
            cursor = 0
            for member in track.members:
                count = member.t_s.size
                aligned = member.y_hz - fit.segment_offset(str(member.segment[0]))
                cursor += count
                ax.scatter(
                    member.t_s,
                    aligned,
                    s=11,
                    alpha=0.7,
                    color=color,
                    marker=edge_marker[member.edge],
                    linewidths=0.65,
                )
            grid = np.linspace(track.start_s, track.end_s, 180)
            ax.plot(
                grid,
                fit.dynamic(grid),
                color=color,
                linewidth=1.2,
                label=f"{track.track_id} {track.label} · {fit.rms_hz:.0f} Hz",
            )
        ax.set_ylabel(f"CH{channel}\naligned CFO (Hz)")
        if selected:
            ax.legend(loc="best", ncol=min(3, len(selected)), frameon=False)
        else:
            ax.text(0.5, 0.5, "no accepted lower/upper merge", transform=ax.transAxes, ha="center")
        ax.set_xlim(0, 300)
    axes[-1].set_xlabel("device time since scan start (s)")
    strong = sum(float(item["delta_bic"]) <= -10 for item in accepted)
    fig.suptitle(
        "Lower/upper evidence after RF normalization and segment offsets · "
        f"{len(accepted)} merges ({strong} strong by ΔBIC≤−10)",
        fontsize=14,
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def _plot_edge_metrics(accepted: list[dict[str, object]], output: Path) -> None:
    _style()
    fig, axes = plt.subplots(2, 1, figsize=(15, 8), sharex=True)
    labels = [
        f"CH{item['left'].channel} RX{item['left'].receiver}\n{index + 1}"
        for index, item in enumerate(accepted)
    ]
    x = np.arange(len(accepted))
    independent = np.asarray([item["independent_rms_hz"] for item in accepted], dtype=float)
    shared = np.asarray([item["shared_rms_hz"] for item in accepted], dtype=float)
    gain = np.asarray([item["resolution_gain"] for item in accepted], dtype=float)
    width = 0.38
    axes[0].bar(x - width / 2, independent, width, label="separate cubic fits", color="#8ea6b4")
    axes[0].bar(
        x + width / 2, shared, width, label="shared cubic + segment offsets", color="#2a9d8f"
    )
    axes[0].set_ylabel("descriptive RMS (Hz)")
    axes[0].legend(frameon=False)
    axes[0].set_title(
        "Pooling may raise descriptive RMS while improving the common Doppler estimate"
    )
    axes[1].bar(x, gain, width=0.65, color="#e9a03b")
    axes[1].axhline(1.0, color="#333333", linewidth=0.8)
    axes[1].set_ylabel("rate-SE resolution gain (×)")
    axes[1].set_xticks(x, labels, rotation=45, ha="right")
    axes[1].set_xlabel("accepted opposite-edge association")
    fig.suptitle("Lower/upper shared-fit cost and model-based Doppler-rate resolution", fontsize=14)
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def _plot_switches(candidates: list[dict[str, object]], output: Path) -> None:
    _style()
    shown = candidates[:6]
    rows = max(len(shown), 1)
    fig, axes = plt.subplots(rows, 2, figsize=(16, max(4, 3.1 * rows)), squeeze=False)
    if not shown:
        axes[0, 0].text(0.5, 0.5, "No exclusivity-compatible cross-channel joins", ha="center")
        axes[0, 1].axis("off")
    for row, candidate in enumerate(shown):
        left = candidate["left"]
        right = candidate["right"]
        best = candidate["best"]
        assert isinstance(left, ChannelEpisode) and isinstance(right, ChannelEpisode)
        shared = best["shared"]
        assert isinstance(shared, Fit)
        ax, residual_ax = axes[row]
        colors = {left.track_id: "#2878a5", right.track_id: "#d95f73"}
        cursor = 0
        for track in (left, right):
            for member in track.members:
                count = member.t_s.size
                aligned = member.y_hz - shared.segment_offset(str(member.segment[0]))
                residual = shared.residual_hz[cursor : cursor + count]
                cursor += count
                ax.scatter(member.t_s, aligned, s=12, alpha=0.72, color=colors[track.track_id])
                residual_ax.scatter(
                    member.t_s, residual, s=12, alpha=0.72, color=colors[track.track_id]
                )
        grid = np.linspace(left.start_s, right.end_s, 250)
        ax.plot(grid, shared.dynamic(grid), color="#222222", linewidth=1.25)
        ax.set_ylabel("aligned CFO (Hz)")
        residual_ax.axhline(0, color="#222222", linewidth=0.7)
        residual_ax.set_ylabel("residual (Hz)")
        delta_bic = float(best["delta_bic"])
        title = (
            f"{left.label} → {right.label} · gap {candidate['gap_s']:.2f}s · "
            f"degree {best['degree']} · ΔBIC {delta_bic:+.1f} · RMS {shared.rms_hz:.0f} Hz"
        )
        ax.set_title(title)
        residual_ax.set_title("shared shape residual")
        if row == rows - 1:
            ax.set_xlabel("device time since scan start (s)")
            residual_ax.set_xlabel("device time since scan start (s)")
    fig.suptitle(
        "Best exclusivity-compatible cross-channel joins after lower/upper merging",
        fontsize=14,
        y=0.998,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def _plot_top_switch_model_orders(candidates: list[dict[str, object]], output: Path) -> None:
    _style()
    supported = [
        item
        for item in candidates
        if float(item["best"]["delta_bic"]) <= -10.0
        and item["best"]["shared"].rms_hz <= 1.25 * float(item["best"]["independent"]["rms_hz"])
    ]
    selected = supported[0] if supported else (candidates[0] if candidates else None)
    fig, axes = plt.subplots(2, 3, figsize=(16, 7.5), sharex="col")
    if selected is None:
        for ax in axes.ravel():
            ax.axis("off")
        axes[0, 0].text(
            0.5,
            0.5,
            "No exclusivity-compatible cross-channel candidate",
            transform=axes[0, 0].transAxes,
            ha="center",
        )
        fig.savefig(output, bbox_inches="tight")
        plt.close(fig)
        return

    left = selected["left"]
    right = selected["right"]
    assert isinstance(left, ChannelEpisode) and isinstance(right, ChannelEpisode)
    colors = {left.track_id: "#2878a5", right.track_id: "#d95f73"}
    for column, degree_row in enumerate(selected["degrees"]):
        degree = int(degree_row["degree"])
        shared = degree_row["shared"]
        independent = degree_row["independent"]
        assert isinstance(shared, Fit)
        signal_ax = axes[0, column]
        residual_ax = axes[1, column]
        cursor = 0
        for episode in (left, right):
            first_member = True
            for member in episode.members:
                count = member.t_s.size
                aligned = member.y_hz - shared.segment_offset(str(member.segment[0]))
                residual = shared.residual_hz[cursor : cursor + count]
                cursor += count
                label = episode.label if first_member else None
                first_member = False
                signal_ax.scatter(
                    member.t_s,
                    aligned,
                    s=17,
                    alpha=0.72,
                    color=colors[episode.track_id],
                    label=label,
                )
                residual_ax.scatter(
                    member.t_s,
                    residual,
                    s=17,
                    alpha=0.72,
                    color=colors[episode.track_id],
                )
        grid = np.linspace(left.start_s, right.end_s, 280)
        signal_ax.plot(grid, shared.dynamic(grid), color="#202020", linewidth=1.3)
        residual_ax.axhline(0.0, color="#202020", linewidth=0.75)
        signal_ax.set_title(
            f"degree {degree} · shared RMS {shared.rms_hz:.1f} Hz\n"
            f"separate RMS {float(independent['rms_hz']):.1f} Hz · "
            f"ΔBIC {float(degree_row['delta_bic']):+.1f}"
        )
        signal_ax.legend(loc="best", frameon=False)
        residual_ax.set_xlabel("device time since scan start (s)")
        if column == 0:
            signal_ax.set_ylabel("offset-aligned CFO (Hz)")
            residual_ax.set_ylabel("shared-fit residual (Hz)")
    fig.suptitle(
        f"Top cross-channel candidate: {left.label} → {right.label} · "
        f"transition near {(left.end_s + right.start_s) / 2:.2f} s",
        fontsize=14,
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def _plain_edge(candidate: dict[str, object]) -> dict[str, object]:
    left = candidate["left"]
    right = candidate["right"]
    assert isinstance(left, Series) and isinstance(right, Series)
    return {
        "channel": left.channel,
        "receiver": left.receiver,
        "left_edge": left.edge,
        "left_tracklet_id": left.tracklet.tracklet_id,
        "right_edge": right.edge,
        "right_tracklet_id": right.tracklet.tracklet_id,
        "overlap_s": candidate["overlap_s"],
        "rate_difference_hz_per_s": candidate["rate_difference_hz_per_s"],
        "shared_cubic_rms_hz": candidate["shared_rms_hz"],
        "independent_cubic_rms_hz": candidate["independent_rms_hz"],
        "shared_minus_independent_bic": candidate["delta_bic"],
        "shared_rate_standard_error_hz_per_s": candidate["shared_rate_se_hz_per_s"],
        "rate_resolution_gain": candidate["resolution_gain"],
    }


def _plain_switch(candidate: dict[str, object], rank: int) -> dict[str, object]:
    left = candidate["left"]
    right = candidate["right"]
    best = candidate["best"]
    assert isinstance(left, ChannelEpisode) and isinstance(right, ChannelEpisode)
    shared = best["shared"]
    independent = best["independent"]
    assert isinstance(shared, Fit)
    model_orders = []
    for degree_row in candidate["degrees"]:
        degree_shared = degree_row["shared"]
        degree_independent = degree_row["independent"]
        assert isinstance(degree_shared, Fit)
        model_orders.append(
            {
                "degree": degree_row["degree"],
                "shared_rms_hz": degree_shared.rms_hz,
                "independent_rms_hz": degree_independent["rms_hz"],
                "shared_bic": degree_shared.bic,
                "independent_bic": degree_independent["bic"],
                "shared_minus_independent_bic": degree_row["delta_bic"],
                "rate_disagreement_hz_per_s": degree_row["rate_difference_hz_per_s"],
                "rate_disagreement_standard_error_hz_per_s": degree_row[
                    "rate_difference_se_hz_per_s"
                ],
                "acceleration_disagreement_hz_per_s2": degree_row[
                    "acceleration_difference_hz_per_s2"
                ],
            }
        )
    return {
        "rank": rank,
        "left_track_id": left.track_id,
        "left_label": left.label,
        "left_support_s": [left.start_s, left.end_s],
        "right_track_id": right.track_id,
        "right_label": right.label,
        "right_support_s": [right.start_s, right.end_s],
        "gap_s": candidate["gap_s"],
        "degree": best["degree"],
        "shared_rms_hz": shared.rms_hz,
        "independent_rms_hz": independent["rms_hz"],
        "shared_minus_independent_bic": best["delta_bic"],
        "rate_disagreement_hz_per_s": best["rate_difference_hz_per_s"],
        "rate_disagreement_standard_error_hz_per_s": best["rate_difference_se_hz_per_s"],
        "acceleration_disagreement_hz_per_s2": best["acceleration_difference_hz_per_s2"],
        "left_receivers": left.receivers,
        "right_receivers": right.receivers,
        "receiver_corroborated": len(left.receivers) == 2 and len(right.receivers) == 2,
        "model_orders": model_orders,
        "supported": (
            float(best["delta_bic"]) <= -10.0
            and shared.rms_hz <= 1.25 * float(independent["rms_hz"])
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    captures = PersistentHopIqStore.open_read_only(args.bulk_root)
    analyses = PersistentHopAnalysisStoreV2.open_read_only(args.bulk_root)
    capture = captures.inspect(args.session_id)
    chunks = analyses.published_chunks(args.session_id)
    projection = project_fractional_persistent_hop_candidates(
        capture.manifest,
        chunks,
        input_manifest_sha256=capture.manifest_sha256,
    )
    config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(projection.candidates, config=config)
    primary_ids = set(trajectory.hypotheses[0].tracklet_ids)
    tracklets = [item for item in trajectory.tracklets if item.tracklet_id in primary_ids]
    candidate_by_id = {item.candidate_id: item for item in projection.candidates}
    start_utc_ns = capture.manifest.timing.first_sample_estimate_utc_ns
    series: list[Series] = []
    for tracklet in tracklets:
        candidates = [candidate_by_id[item.candidate_id] for item in tracklet.points]
        t_s = np.asarray(
            [(item.support_center_utc_ns - start_utc_ns) / 1e9 for item in candidates],
            dtype=float,
        )
        y_hz = np.asarray(
            [item.normalized_dealiased_cfo_hz for item in tracklet.points], dtype=float
        )
        weight = np.asarray(
            [
                min(max(item.margin, 0.0) / max(item.control_score, 0.02), 16.0)
                for item in candidates
            ],
            dtype=float,
        )
        segment_name = tracklet.tracklet_id
        segment = np.asarray([segment_name] * len(candidates), dtype=object)
        series.append(Series(tracklet, t_s, y_hz, weight, segment))

    edge_candidates = _edge_candidates(series)
    tracks, accepted_edges = _build_physical_tracks(series, edge_candidates)
    episodes, accepted_receiver_merges = _build_channel_episodes(tracks)
    switches = _switch_candidates(episodes)

    residual_summary = _plot_residuals(
        tracks, args.output_dir / "01-linear-quadratic-cubic-residuals.png"
    )
    _plot_edge_merges(tracks, accepted_edges, args.output_dir / "02-upper-lower-merged-tracks.png")
    _plot_edge_metrics(accepted_edges, args.output_dir / "03-upper-lower-rms-resolution.png")
    _plot_switches(switches, args.output_dir / "04-cross-channel-join-candidates.png")
    _plot_top_switch_model_orders(switches, args.output_dir / "05-top-candidate-model-orders.png")

    physical = []
    for track in tracks:
        fit_rows = {}
        for degree in (1, 2, 3):
            fit = _fit(track.members, degree)
            midpoint = (track.start_s + track.end_s) / 2
            rate, rate_se = fit.derivative(midpoint, 1)
            acceleration, acceleration_se = fit.derivative(midpoint, 2)
            jerk, jerk_se = fit.derivative(midpoint, 3)
            fit_rows[str(degree)] = {
                "rms_hz": fit.rms_hz,
                "weighted_rms_hz": fit.weighted_rms_hz,
                "bic": fit.bic,
                "midpoint_rate_hz_per_s": rate,
                "midpoint_rate_standard_error_hz_per_s": rate_se,
                "midpoint_acceleration_hz_per_s2": acceleration if degree >= 2 else None,
                "midpoint_acceleration_standard_error_hz_per_s2": (
                    acceleration_se if degree >= 2 else None
                ),
                "jerk_hz_per_s3": jerk if degree >= 3 else None,
                "jerk_standard_error_hz_per_s3": jerk_se if degree >= 3 else None,
            }
        best_degree = min((1, 2, 3), key=lambda degree: fit_rows[str(degree)]["bic"])
        physical.append(
            {
                "track_id": track.track_id,
                "label": track.label,
                "channel": track.channel,
                "receiver": track.receiver,
                "edges": track.edges,
                "support_s": [track.start_s, track.end_s],
                "point_count": sum(item.t_s.size for item in track.members),
                "member_tracklet_ids": [item.tracklet.tracklet_id for item in track.members],
                "best_degree_by_bic": best_degree,
                "fits": fit_rows,
            }
        )

    accepted_plain = [_plain_edge(item) for item in accepted_edges]
    switch_plain = [_plain_switch(item, rank) for rank, item in enumerate(switches, 1)]
    finite_gains = [
        float(item["rate_resolution_gain"])
        for item in accepted_plain
        if math.isfinite(float(item["rate_resolution_gain"]))
    ]
    output = {
        "schema_version": 1,
        "session_id": args.session_id,
        "candidate_only": True,
        "identity_claimed": False,
        "method": (
            "fractional GLRT64, actual-RF normalization to 11.2 GHz, "
            "robust shared polynomial with one fixed offset per source tracklet"
        ),
        "fractional_epoch_required": True,
        "canonical_rf_hz": CANONICAL_RF_HZ,
        "capture": {
            "sample_rate_hz": capture.manifest.plan.sample_rate_hz,
            "bandwidth_hz": capture.manifest.plan.bandwidth_hz,
            "valid_duty_ppm": capture.manifest.receipt.valid_duty_ppm,
            "visit_count": len(capture.manifest.receipt.visits),
        },
        "projected_candidate_count": len(projection.candidates),
        "production_tracklet_count": len(trajectory.tracklets),
        "primary_source_disjoint_tracklet_count": len(series),
        "physical_track_count": len(tracks),
        "accepted_upper_lower_merge_count": len(accepted_edges),
        "strong_upper_lower_merge_count": sum(
            float(item["delta_bic"]) <= -10.0 for item in accepted_edges
        ),
        "median_rate_resolution_gain": (float(np.median(finite_gains)) if finite_gains else None),
        "residual_rms_by_channel_and_degree_hz": residual_summary,
        "accepted_upper_lower_merges": accepted_plain,
        "accepted_receiver_replica_merge_count": len(accepted_receiver_merges),
        "channel_episode_count": len(episodes),
        "physical_tracks": physical,
        "channel_episodes": [
            {
                "episode_id": item.episode_id,
                "label": item.label,
                "channel": item.channel,
                "receivers": item.receivers,
                "support_s": [item.start_s, item.end_s],
                "physical_track_ids": [track.track_id for track in item.tracks],
                "point_count": sum(member.t_s.size for member in item.members),
            }
            for item in episodes
        ],
        "cross_channel_candidate_count": len(switches),
        "supported_cross_channel_candidate_count": sum(
            bool(item["supported"]) for item in switch_plain
        ),
        "cross_channel_candidates": switch_plain,
        "gates": {
            "upper_lower_minimum_overlap_s": EDGE_OVERLAP_MIN_S,
            "upper_lower_rate_gate_hz_per_s": EDGE_RATE_GATE_HZ_PER_S,
            "upper_lower_shared_rms_gate_hz": EDGE_SHARED_RMS_GATE_HZ,
            "upper_lower_shared_to_independent_rms_ratio": EDGE_RMS_RATIO_GATE,
            "upper_lower_delta_bic_gate": EDGE_DELTA_BIC_GATE,
            "switch_overlap_tolerance_s": SWITCH_OVERLAP_TOLERANCE_S,
            "switch_maximum_gap_s": SWITCH_MAXIMUM_GAP_S,
            "supported_switch_delta_bic": -10.0,
            "supported_switch_shared_to_independent_rms_ratio": 1.25,
        },
    }
    (args.output_dir / "analysis.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: output[key]
                for key in (
                    "session_id",
                    "projected_candidate_count",
                    "production_tracklet_count",
                    "primary_source_disjoint_tracklet_count",
                    "physical_track_count",
                    "accepted_upper_lower_merge_count",
                    "strong_upper_lower_merge_count",
                    "median_rate_resolution_gain",
                    "accepted_receiver_replica_merge_count",
                    "channel_episode_count",
                    "cross_channel_candidate_count",
                    "supported_cross_channel_candidate_count",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
