"""Replay and plot the missing RX1 CH1 tail, without changing ALGO01 inputs."""

import hashlib
import itertools
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from evaluate_ds22_merged_tracks import CONFIG, write
from leo.analysis import graph_tracklets as graph
from leo.analysis.polynomial_tracklets import TrackConfig, _best_piece, _piece, _predict, _refine
from leo.analysis.research.public_tracking_points import public_tracking_points
from leo.analysis.research.visible_arc_variants import deduplicate
from report_ds23_phase_refreshed import polynomial

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/2026_10_18_algo01_ds23_random20/DS23-0217"
OUT = ROOT / "reports/2026_10_18_algo01_ds23_0217_rx1_ch1_tail"


def accepted_ids(associations, tracks):
    """Keep partial acceptance masks, rather than accepting whole track keys."""
    full = {t["key"]: t["observation_ids"] for t in tracks}
    return {oid for a in associations if a["compatible"]
            for oid in (a["observation_ids"] if "observation_ids" in a else full[a["component"]])}


def candidate_rows(document, lo=230, hi=300):
    """Retain all gated alternatives with exact public-adapter midpoint times."""
    fs = document["sample_rate_hz"]
    origin = document["timing"]["session_start_device_sample_counter"]
    first_rx = min(p["receiver_id"] for p in document["probes"])
    rows = []
    for i, p in enumerate(document["probes"]):
        start = p["valid_start_counter"] + round(p["probe_start_ms"] * fs / 1000)
        t = (start - origin) / fs + document["probe_ms"] / 2000
        if p["receiver_id"] != first_rx or p["channel"] != 1 or not lo <= t <= hi:
            continue
        eligible = [c for c in p["candidates"] if c["passed_fractional_margin_gate"]]
        winner = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None)
        for c in eligible:
            rows.append(dict(time_s=t, cfo_hz=c["fractional_tracking_cfo_hz"],
                             margin=c["fractional_margin"], probe=i,
                             rank=c["candidate_rank"], winner=c is winner))
    return rows


def exhaustive_paths(t, y, cfg):
    """Exact tiny-window enumeration under the graph's existing additive cost."""
    g = graph._graph(t, y, cfg)
    edges = {(a, b): i for i, (a, b) in enumerate(zip(g[0], g[1], strict=True))}
    # This lane's slope/horizon admits exactly one alias branch per edge.
    assert len(edges) == len(g[0])
    best = {}
    for n in range(2, len(t) + 1):
        for path in itertools.combinations(range(len(t)), n):
            pairs = list(zip(path[:-1], path[1:], strict=True))
            if any(pair not in edges for pair in pairs):
                continue
            ix = np.array([edges[p] for p in pairs])
            dt, v = g[2][ix], g[3][ix]
            a, b = dt[:-1], dt[1:]
            variance = 2 * cfg.noise_sigma_hz**2 * (1 / a**2 + 1 / b**2 + 1 / (a * b))
            variance += (20 * (a + b) / 2)**2
            score = n * cfg.association_sigma**2 - cfg.track_penalty - .05 * dt.sum()
            score -= np.sum(2 * np.diff(v)**2 / variance)
            if str(n) not in best or score > best[str(n)]["score"]:
                best[str(n)] = dict(score=float(score), times_s=t[list(path)])
    return best


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    read = lambda name: json.loads((SOURCE / (name + ".json")).read_text())
    observations, tracks, result, document = [read(n) for n in ("observations", "tracks", "result", "tracking")]
    replay_rows, _ = public_tracking_points(document)
    assert replay_rows == observations
    associations = result["arms"]["c0"]["association_tracks"]
    accepted = accepted_ids(associations, tracks)
    raw = {r["observation_id"]: r for r in observations}
    lane = [r for r in observations if (r["receiver"], r["channel"]) == (1, 1)]
    t = np.array([r["time_s"] for r in lane])
    y = np.array([r["measured_cfo_hz"] for r in lane])
    target = np.array([i for i, r in enumerate(lane) if 230 <= t[i] <= 300 and r["observation_id"] not in accepted])
    cfg = TrackConfig(**json.loads(CONFIG.read_text())["config"])
    path_events, model_events, refine_events = [], [], []
    original_best, original_models = graph._best_path, graph._path_models

    def traced_best(*args, **kwargs):
        output = original_best(*args, **kwargs)
        path_events.append(dict(indices=output[0].copy(), score=output[3],
                                target_indices=np.intersect1d(output[0], target)))
        return output

    def traced_models(*args, **kwargs):
        output = original_models(*args, **kwargs)
        model_events.append(dict(proposed_indices=np.array(args[2]),
                                 proposed_target_indices=np.intersect1d(args[2], target),
                                 retained_target_indices=[np.intersect1d(m["indices"], target) for m in output]))
        return output

    def traced_refine(*args, **kwargs):
        output = _refine(*args, **kwargs)
        if len(np.intersect1d(args[2], target)):
            refine_events.append(dict(grow=kwargs.get("grow", True),
                                      proposed_target_indices=np.intersect1d(args[2], target),
                                      retained_target_indices=[] if output is None else np.intersect1d(output["indices"], target),
                                      output_points=0 if output is None else len(output["indices"]),
                                      output_degree=None if output is None else output["degree"]))
        return output

    with (patch.object(graph, "_best_path", traced_best),
          patch.object(graph, "_path_models", traced_models),
          patch.object(graph, "_refine", traced_refine)):
        replay = graph.fit_lane(t, y, cfg)
    saved = [tr for tr in tracks if (tr["receiver"], tr["channel"]) == (1, 1)]
    assert [tr["indices"] for tr in saved] == [tr["indices"].tolist() for tr in replay["tracks"]]
    local_t, local_y = t[target], y[target]
    leftover = graph.fit_lane(local_t, local_y, cfg)
    arc = target[t[target] >= 240]
    at, ay = t[arc], y[arc]
    ix = np.arange(len(arc))
    piece = _best_piece(at, ay, ix, ay, cfg)
    residual = ay - _predict(piece, at)
    refinement = _refine(at, ay, ix, ay, cfg, grow=False)
    assert refinement is None
    unconstrained_degrees = []
    for degree in range(1, 5):
        diagnostic_piece = _piece(at, ay, ix, degree)
        rr = ay - _predict(diagnostic_piece, at)
        unconstrained_degrees.append(dict(degree=degree, rms_hz=float(np.sqrt(np.mean(rr**2))),
                                         maximum_abs_residual_hz=float(np.max(abs(rr))),
                                         support_sufficient=len(ix) >= cfg.points_per_coefficient * (degree + 1)))
    candidates = candidate_rows(document)
    reps, clusters = deduplicate([c["cfo_hz"] for c in candidates],
                                [c["margin"] for c in candidates], [c["probe"] for c in candidates])
    canonical = [candidates[i] for i in reps]
    audit = dict(
        case="DS23-0217", lane="RX1 CH1", inference_changed=False, config=asdict(cfg),
        input_sha256={n: hashlib.sha256((SOURCE / (n + ".json")).read_bytes()).hexdigest()
                      for n in ("observations", "tracks", "result", "tracking")},
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        public_adapter_replayed_exactly=True, full_lane_memberships_replayed_exactly=True,
        target_unassociated_winners=[lane[i] for i in target],
        unassociated_winners_250_300=int(np.sum((local_t >= 250) & (local_t <= 300))),
        path_events=path_events, model_events=model_events, refine_events=refine_events,
        leftover_graph_diagnostics=leftover["diagnostics"],
        exhaustive_best_path_by_length=exhaustive_paths(local_t, local_y, cfg),
        arc_240_300=dict(points=len(arc), degree=piece["degree"],
                         rms_hz=float(np.sqrt(np.mean(residual**2))),
                         residual_hz=residual, time_s=at, refine_accepted=False),
        diagnostic_degree_sweep=unconstrained_degrees,
        all_peak_230_300=dict(gate_passing_candidates=len(candidates),
                             heuristic_representatives=len(reps),
                             physical_probes=len({c["probe"] for c in candidates}),
                             caveat="300 Hz circular clustering is heuristic; representatives can still be alias/timing replicas"),
        candidates=candidates, representative_indices=reps, dedup_clusters=clusters,
    )
    write(OUT / "audit.json", audit)
    fig, axes = plt.subplots(3, 1, figsize=(13, 12), constrained_layout=True)
    ax = axes[0]
    ax.scatter(t, y / 1000, s=16, color=".75", label="All winning GLRT")
    ax.scatter(local_t, local_y / 1000, s=42, color="crimson", label="Unassociated winning GLRT", zorder=5)
    for tr, color in zip(saved[:3], ["#1477b8", "#00a6a6", "#8a65ab"], strict=True):
        polynomial(ax, tr, raw, color)
        pts = [raw[k] for k in tr["observation_ids"]]
        ax.scatter([r["time_s"] for r in pts], [r["measured_cfo_hz"] / 1000 for r in pts],
                   s=18, color=color, label=tr["key"].split("-CH1-")[1].split("-RF")[0] + " (associated)")
    ax.axvspan(250, 300, color="gold", alpha=.08)
    ax.set(xlim=(230, 300), ylim=(-220, 20), ylabel="Native measured CFO (kHz)",
           title="DS23-0217 · ALGO01 c=0 · RX1 CH1: winning GLRT and existing graph tracks")
    ax.legend(fontsize=9, ncol=2)
    ax = axes[1]
    secondary = [c for c in canonical if not c["winner"]]
    ax.scatter([c["time_s"] for c in secondary], [c["cfo_hz"] / 1000 for c in secondary],
               marker="x", s=45, color="#bd8400", label="Secondary gated GLRT (heuristically deduplicated)")
    ax.scatter(at, ay / 1000, s=45, color="crimson", label="Unassociated winners", zorder=4)
    grid = np.linspace(at.min(), at.max(), 150)
    ax.plot(grid, _predict(piece, grid) / 1000, "k--", lw=1, label="Supported-degree fit: fails residual gate")
    last_label = -np.inf
    for tt, yy in zip(at, ay, strict=True):
        if tt - last_label > .4:
            ax.annotate(f"{tt:.2f}s", (tt, yy / 1000), xytext=(5, 6), textcoords="offset points", fontsize=8)
            last_label = tt
    ax.set(xlim=(240, 275), ylim=(-220, -105), ylabel="Native measured CFO (kHz)",
           title="Missing-fragment zoom: secondary alternatives persist to ~270 s; identity is unproven")
    ax.legend(fontsize=8, loc="lower left")
    ax = axes[2]
    ax.axhspan(-450, 450, color="green", alpha=.12, label="Existing ±450 Hz membership gate")
    ax.axhline(0, color="k", lw=.7)
    ax.scatter(at, residual, color="crimson", s=45)
    ax.set(xlim=(240, 275), xlabel="Device time (s)", ylabel="Polynomial residual (Hz)",
           title=f"Ten unassociated winners: supported degree {piece['degree']}, RMS {np.sqrt(np.mean(residual**2)):.1f} Hz; refinement rejects")
    ax.legend(fontsize=9)
    for ax in axes:
        ax.grid(alpha=.2)
    fig.savefig(OUT / "missing_fragment_zoom.png", dpi=170)
    plt.close(fig)
    # Replace gray context with explicit ownership colors for the screenshot audit.
    fig, ax = plt.subplots(figsize=(11, 4.8), constrained_layout=True)
    window = [r for r in lane if 250 <= r["time_s"] <= 300]
    for is_accepted, color, label in ((True, "#1477b8", "50 associated winners · satellite hypothesis 65201"),
                                      (False, "crimson", "6 unassociated winners · missing fragment")):
        selected = [r for r in window if (r["observation_id"] in accepted) == is_accepted]
        ax.scatter([r["time_s"] for r in selected], [r["measured_cfo_hz"] / 1000 for r in selected],
                   s=40, color=color, label=label, zorder=4)
    for tr in saved[:2]:
        polynomial(ax, tr, raw, "#1477b8")
    ax.set(xlim=(249.5, 300.5), ylim=(-185, 0), xlabel="Device time (s)",
           ylabel="Native measured CFO (kHz)",
           title="DS23-0217 RX1 CH1 · gray context from the original plot recolored by ownership")
    ax.grid(alpha=.2)
    ax.legend(loc="upper right", fontsize=9)
    fig.savefig(OUT / "ownership_clarification.png", dpi=160)
    plt.close(fig)
    print(json.dumps(dict(output=str(OUT), target_points=len(target),
                          paths_touching_target=[e for e in path_events if len(e["target_indices"])],
                          arc_rms_hz=audit["arc_240_300"]["rms_hz"]), default=lambda x: x.tolist(), indent=2))


if __name__ == "__main__":
    run()
