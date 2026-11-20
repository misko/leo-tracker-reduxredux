"""Probe the development-only capture radius for satellite identity."""

import argparse
import csv
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np

from ..__main__ import save_json
from ..scoring import ARMS
from . import cold_scenes, fresh_scenes
from . import identity_oracles as oracle

RADII = (0, 10, 25, 50, 100, 250, 500)
BEARINGS = (0, 90, 180, 270)
PROTOCOL = Path(__file__).resolve().parents[3] / (
    "reports/2026_11_19_short_receiver/observability/DISPLACEMENT_PROTOCOL.md"
)


def _measure(capture, site, satellites, tracks):
    period = capture.sample_rate_hz / cold_scenes.FRAME_HZ
    times = np.array([tr.times.mean() for tr in tracks])
    middle = oracle._states(capture.anchor_utc_ns, satellites, times)
    results = []
    for radius in RADII:
        for bearing in BEARINGS if radius else (0,):
            started = perf_counter()
            point = fresh_scenes._destination(site, radius, np.deg2rad(bearing))
            candidates = oracle._candidates(
                capture, satellites, tracks, point, midpoint_states=middle
            )
            rankings = {
                method: {
                    arm: [
                        row["selected_norad"]
                        for row in oracle.identify(
                            tracks, candidates, period, method, arm == "fitted_c"
                        )["rows"]
                    ]
                    for arm in ARMS
                }
                for method in oracle.METHODS
            }
            results.append(
                dict(
                    radius_km=radius,
                    bearing_deg=bearing,
                    site=point,
                    causal_orbits=len(satellites),
                    valid_orbit_tracklet_pairs=sum(len(c.eligible_ids) for c in candidates),
                    visibility=[c.eligible_ids for c in candidates],
                    shortlist=[c.ids for c in candidates],
                    nominations=rankings,
                    elapsed_s=perf_counter() - started,
                )
            )
    return results


def _score(results, known):
    for trial in results:
        visibility = trial.pop("visibility")
        shortlist = trial.pop("shortlist")
        trial.update(
            tracklets=len(known),
            true_visible=sum(label in pool for label, pool in zip(known, visibility, strict=True)),
            true_shortlisted=sum(
                label in pool for label, pool in zip(known, shortlist, strict=True)
            ),
        )
        methods = {}
        for method, match in trial.pop("nominations").items():
            methods[method] = {}
            for arm, rows in match.items():
                hits = [a for a, b in zip(rows, known, strict=True) if a == b]
                methods[method][arm] = dict(
                    correct_tracklets=len(hits),
                    distinct_planted=len(set(hits)),
                    selected_norads=rows,
                )
        trial["methods"] = methods
        yield trial


def _summarize(results):
    groups = []
    for radius in RADII:
        subset = [trial for trial in results if trial["radius_km"] == radius]
        total = sum(r["tracklets"] for r in subset)
        for method in oracle.METHODS:
            for arm in ARMS:
                calls = [r["methods"][method][arm] for r in subset]
                observations = [r["correct_tracklets"] for r in calls]
                groups.append(
                    dict(
                        radius_km=radius,
                        hypotheses=len(subset),
                        method=method,
                        arm=arm,
                        correct_tracks=sum(observations),
                        total_tracks=total,
                        recall=sum(observations) / total,
                        median_correct_per_site=median(observations),
                        min_correct_per_site=min(observations),
                        max_correct_per_site=max(observations),
                        distinct_planted=sum(r["distinct_planted"] for r in calls),
                        total_planted=12 * len(subset),
                        true_visible=sum(r["true_visible"] for r in subset),
                        true_shortlisted=sum(r["true_shortlisted"] for r in subset),
                        median_wall_s=median(r["elapsed_s"] for r in subset),
                        median_valid_orbit_tracklet_pairs=median(
                            r["valid_orbit_tracklet_pairs"] for r in subset
                        ),
                    )
                )
    return groups


def run(public, output):
    manifest = cold_scenes._read(public / "manifest.json")
    if manifest != cold_scenes._read(oracle.DEV / "manifest.json"):
        raise ValueError("expected corrected development data")
    labels = oracle._labels(oracle.DEV)
    rows = []
    for case in manifest["order"]:
        truth = labels[case]
        if truth["latlon"] is None:
            continue
        capture = cold_scenes._capture(public, case)
        tracks = oracle.tracklets(capture)
        satellites = cold_scenes._constellation(capture.catalog, capture.cutoff_utc_ns)
        sites = _measure(capture, truth["latlon"], satellites, tracks)
        emitter = {(r["block"], r["channel"]): r["norad"] for r in truth["emitters"]}
        known = [emitter[int(np.median(t.times) // 50), t.channel] for t in tracks]
        rows.extend(dict(row, id=case) for row in _score(sites, known))
        print(case, len(sites), "displaced hypotheses finished", flush=True)
    summary = _summarize(rows)
    save_json(
        output / "displacement.json",
        dict(
            predictions=rows,
            summary=summary,
            protocol_sha256=cold_scenes._sha(PROTOCOL.read_bytes()),
            source_sha256=cold_scenes._sha(Path(__file__).read_bytes()),
            oracle_source_sha256=cold_scenes._sha(Path(oracle.__file__).read_bytes()),
            development_manifest_sha256=cold_scenes._sha((public / "manifest.json").read_bytes()),
        ),
    )
    with (output / "displacement.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    plot(output, summary)


def plot(output, summary):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    fig, axis = plt.subplots(figsize=(8.8, 4.7))
    labels = {
        "shape": "Centered shape",
        "absolute_cfo": "Shape + absolute CFO",
        "frame_drift": "Shape + frame drift",
        "joint": "Joint observables",
    }
    for method in labels:
        sample = [r for r in summary if r["method"] == method and r["arm"] == "fitted_c"]
        axis.plot(RADII, [r["recall"] for r in sample], marker="o", label=labels[method])
    joint = [r for r in summary if r["method"] == "joint" and r["arm"] == "fitted_c"]
    axis.fill_between(
        RADII,
        [r["min_correct_per_site"] / 24 for r in joint],
        [r["max_correct_per_site"] / 24 for r in joint],
        alpha=0.15,
        color="#b14531",
        label="Joint site and bearing range",
    )
    axis.set_xscale("symlog", linthresh=10)
    axis.set_xticks(RADII, [str(r) for r in RADII])
    axis.set_ylim(-0.025, 1.025)
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    axis.set(xlabel="Receiver site displacement (km)", ylabel="Correct lane identities")
    axis.spines[["right", "top"]].set_visible(False)
    axis.grid(axis="y", alpha=0.2)
    axis.legend(frameon=False, fontsize=8, loc="upper right")
    fig.suptitle("Identity recall near the planted receiver site · development data")
    fig.tight_layout()
    fig.savefig(output / "displacement.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("public", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.public, args.output)


if __name__ == "__main__":
    main()
