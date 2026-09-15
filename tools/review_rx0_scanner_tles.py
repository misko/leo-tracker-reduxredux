"""Review a frozen scanner cohort against causal archived TLEs without RF or production writes."""

import argparse
import csv
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.persistent_hop_trajectory import (
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.analysis.research.scanner_tle_screen import rank_curves, sample_grid
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.sky import ObserverSiteV1
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid
from leo.sky.sites import resolve_preset
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def screen_source(source, site, destination):
    # Freeze all measured trajectories before opening the catalogue.
    trajectory = reconstruct_persistent_hop_trajectories(project_scanner_candidates(source))
    start = source.timing.first_sample_estimate_utc_ns
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(start - 505_000_000_000)
    raw = archive.read(snapshot)
    catalogue = parse_element_sets(raw)
    indices = [i for i, n in enumerate(catalogue.names) if n.upper().startswith("STARLINK")]
    grid = SamplingGrid(tuple(start + k * 1_000_000_000 for k in range(-507, 809)), 507, 1.0)
    propagated = propagate_grid(catalogue, grid, indices)
    observed = observe_grid(propagated, site, grid)
    good = observed.usable & (np.min(observed.altitude_km, axis=1) > 120)
    exclusions = []
    for local, i in enumerate(indices):
        if not good[local] or catalogue.names[i].upper().endswith(" DEB"):
            good[local] = False
            exclusions.append(
                {
                    "catalog_number": catalogue.satellite_numbers[i],
                    "name": catalogue.names[i],
                    "sgp4_error_codes": sorted(
                        set(int(x) for x in propagated.error_code[local] if x)
                    ),
                    "minimum_altitude_km": (
                        float(np.nanmin(observed.altitude_km[local]))
                        if np.any(np.isfinite(observed.altitude_km[local]))
                        else None
                    ),
                }
            )
    visible = good & (np.max(observed.elevation_deg, axis=1) >= -1)
    local_rows = np.flatnonzero(visible)
    numbers = np.array([catalogue.satellite_numbers[indices[i]] for i in local_rows])
    names = [catalogue.names[indices[i]] for i in local_rows]
    elevations = observed.elevation_deg[local_rows]
    taus = np.arange(-5.0, 6.0)
    tracks, seen, panels = [], set(), []
    by_id = {t.tracklet_id: t for t in trajectory.tracklets}
    for hypothesis in trajectory.hypotheses:
        for tid in hypothesis.tracklet_ids:
            if tid in seen:
                continue
            seen.add(tid)
            graph = persistent_hop_tracklet_graph(hypothesis, tid)
            rows = sorted(graph.observations, key=lambda o: o.support_center_utc_ns)
            t = np.array([(o.support_center_utc_ns - start) / 1e9 for o in rows])
            if len(t) < 20 or t[-1] - t[0] < 20:
                continue
            y = np.array([o.measured_cfo_hz for o in rows])
            split = int(len(t) * 0.6)
            fields = {}
            nominal = None
            for delta in (-500, 0, 500):
                times = t[None, :] + taus[:, None] + delta
                elev = sample_grid(elevations, -507, 1, times)
                eligible = np.flatnonzero(np.max(elev, axis=(1, 2)) >= -0.1)
                if not len(eligible):
                    fields[str(delta)] = {"candidate_count": 0}
                    continue
                # Exact center-time propagation for all candidate/tau pairs.
                # The coarse grid only preselects possible horizon visibility.
                exact_times = tuple(start + round(float(ti) * 1e9) for ti in times.ravel())
                exact_grid = SamplingGrid(exact_times, len(exact_times) // 2, 1.0)
                exact_indices = [indices[local_rows[i]] for i in eligible]
                exact = observe_grid(
                    propagate_grid(catalogue, exact_grid, exact_indices), site, exact_grid
                )
                bank = doppler_shift_hz(11_200_000_000.0, exact.range_rate_km_s).reshape(
                    len(eligible), len(taus), len(t)
                )
                exact_elev = exact.elevation_deg.reshape(bank.shape)
                visible_exact = exact.usable & (np.max(exact_elev, axis=(1, 2)) >= 0)
                eligible = eligible[visible_exact]
                bank = bank[visible_exact]
                if not len(eligible):
                    fields[str(delta)] = {"candidate_count": 0}
                    continue
                ranking = rank_curves(y, bank, training_count=split)
                order = ranking["order"]

                def candidate(i, eligible=eligible, ranking=ranking):
                    return {
                        "catalog_number": int(numbers[eligible[i]]),
                        "name": names[eligible[i]],
                        "tau_s": float(taus[ranking["tau_indices"][i]]),
                        "offset_hz": float(ranking["offsets"][i]),
                        "training_rms_hz": float(ranking["training_rms"][i]),
                        "heldout_rms_hz": float(ranking["heldout_rms"][i]),
                    }

                fields[str(delta)] = {
                    "candidate_count": len(eligible),
                    "winner_heldout_rank": ranking["winner_heldout_rank"],
                    "top_training": [candidate(i) for i in order[:5]],
                    "top_heldout": [candidate(i) for i in ranking["held_order"][:5]],
                }
                if delta == 0:
                    nominal = (bank, ranking, eligible)
            centered = t - t[0]
            nulls = []
            for degree in (1, 2):
                fit = np.polyfit(centered[:split], y[:split], degree)
                prediction = np.polyval(fit, centered)
                nulls.append(
                    {
                        "degree": degree,
                        "training_rms_hz": float(
                            np.sqrt(np.mean((y[:split] - prediction[:split]) ** 2))
                        ),
                        "heldout_rms_hz": float(
                            np.sqrt(np.mean((y[split:] - prediction[split:]) ** 2))
                        ),
                    }
                )
            null = min(nulls, key=lambda r: r["training_rms_hz"])
            track = by_id[tid]
            record = {
                "tracklet_id": tid,
                "channel": track.lane_key[0],
                "edge": track.lane_key[1].value,
                "observations": len(t),
                "span_s": float(t[-1] - t[0]),
                "training_count": split,
                "time_s": t.tolist(),
                "cfo_hz": y.tolist(),
                "fields": fields,
                "radio_polynomials": nulls,
                "training_selected_radio_degree": null["degree"],
                "candidate_only": True,
                "identity_claimed": False,
            }
            if nominal is not None:
                bank, ranking, eligible = nominal
                winner = fields["0"]["top_training"][0]
                reasons = ["exploratory-screen-not-calibrated-identification"]
                if exclusions:
                    reasons.append("original-catalogue-has-exclusions")
                if fields["0"]["winner_heldout_rank"] != 1:
                    reasons.append("leader-changes-on-heldout")
                if abs(winner["tau_s"]) == 5:
                    reasons.append("time-shift-boundary")
                if winner["heldout_rms_hz"] >= null["heldout_rms_hz"]:
                    reasons.append("radio-polynomial-not-worse")
                for delta in ("-500", "500"):
                    if not fields[delta]["candidate_count"]:
                        reasons.append("wrong-time-population-empty")
                    elif (
                        winner["heldout_rms_hz"]
                        >= fields[delta]["top_training"][0]["heldout_rms_hz"]
                    ):
                        reasons.append("wrong-time-" + delta + "-not-worse")
                record["reasons"] = reasons
                curves = []
                for i in ranking["order"][:3]:
                    curves.append(
                        (
                            int(numbers[eligible[i]]),
                            bank[i, ranking["tau_indices"][i]] + ranking["offsets"][i],
                        )
                    )
                panels.append((record, t, y, curves))
            tracks.append(record)
    panels.sort(key=lambda p: -p[0]["span_s"])
    if panels:
        fig, axes = plt.subplots(
            min(6, len(panels)), 1, figsize=(13, 3 * min(6, len(panels))), squeeze=False
        )
        for ax, (rec, t, y, curves) in zip(axes[:, 0], panels[:6], strict=True):
            ax.plot(t, y, ".", color="black", ms=3, label="Measured GLRT CFO")
            for number, curve in curves:
                ax.plot(t, curve, label=f"NORAD {number} (candidate)")
            ax.axvline(t[rec["training_count"]], color="gray", ls="--", label="Heldout begins")
            ax.set_title(
                f"CH{rec['channel']} {rec['edge']} · {rec['span_s']:.1f} s · "
                + ", ".join(rec["reasons"][1:])
            )
            ax.set_ylabel("CFO at 11.2 GHz (Hz)")
            ax.legend(fontsize=7)
            ax.grid(alpha=0.2)
        axes[-1, 0].set_xlabel("Seconds since recording start")
        fig.suptitle(source.session_id + " · TLE candidates, no identity claim")
        fig.tight_layout()
        fig.savefig(destination / (source.session_id + ".png"), dpi=120)
        plt.close(fig)
    return {
        "protocol": "all-unique-eligible-tracklets-exact-center-rms-screen-v2",
        "snapshot_digest": snapshot.digest,
        "snapshot_path": str(snapshot.path),
        "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
        "observer": site.model_dump(mode="json"),
        "capture_digest": source.input_manifest_sha256,
        "analysis_digest": source.analysis_manifest_sha256,
        "exclusions": exclusions,
        "unique_tracklets": len(seen),
        "eligible_tracklets": len(tracks),
        "tracks": tracks,
        "candidate_only": True,
        "identity_claimed": False,
    }


def review(job):
    row, output, analysis_root = job
    sid = row["session_id"]
    destination = Path(output)
    result_path = destination / (sid + ".json")
    if result_path.exists():
        saved = json.loads(result_path.read_text())
        if saved.get("screen"):
            return saved
    started = time.monotonic()
    sources = ScannerTrackingInputStore(
        Path("/srv/bulk/leo"), adaptive_analysis_root=Path(analysis_root) if analysis_root else None
    )
    result = dict(row)
    try:
        captures = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
        try:
            capture = captures.inspect(sid)
        finally:
            captures.close()
        receipt = capture.manifest.receipt
        if (
            receipt.radio_serial != "104000bac4950008230026001b440a003a"
            or receipt.plan.geometry.sample_rate_hz != 10_000_000
            or receipt.plan.geometry.receiver_ids != (0,)
        ):
            raise ValueError("capture is not the authorized RX0 10 MS/s source")
        preset = resolve_preset("spinnaker-sausalito")
        site = ObserverSiteV1(
            latitude_deg=preset.latitude_deg,
            longitude_deg=preset.longitude_deg,
            altitude_m=preset.altitude_m,
            label=preset.label,
        )
        source = sources.load(sid)
        if source.timing is None or not source.timing.qualified:
            raise ValueError("qualified UTC is required for this review")
        result["screen"] = screen_source(source, site, destination)
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        sources.close()
    result["elapsed_s"] = time.monotonic() - started
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--analysis-root", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    out = args.output.resolve()
    if (
        out == Path("/mnt/qnap01")
        or Path("/mnt/qnap01") in out.parents
        or out == Path("/srv/bulk/leo")
    ):
        parser.error("output must be a separate research directory outside QNAP")
    if not 1 <= args.workers <= 2:
        parser.error("invalid bounded work configuration")
    out.mkdir(parents=True, exist_ok=True)
    with args.sessions.open() as stream:
        rows = list(csv.DictReader(stream))
    if args.limit:
        rows = rows[: args.limit]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(review, (row, str(out), args.analysis_root)) for row in rows]
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            product = result.get("screen", {})
            print(
                json.dumps(
                    {
                        "completed": index,
                        "total": len(rows),
                        "session": result["session_id"],
                        "error": result.get("error"),
                        "eligible_tracklets": product.get("eligible_tracklets"),
                        "elapsed_s": result["elapsed_s"],
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
