"""Lossless post-association joining under shared satellite phase and hardware."""

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write

from leo.analysis.research.identified_track_merging import consolidate
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid


def consolidate_fit(
    recording, bank, fit, association, *, max_gap_s=10.0, check_joined_residual=False
):
    return consolidate_tracks(
        load_tracks(recording),
        bank,
        fit,
        association,
        max_gap_s=max_gap_s,
        check_joined_residual=check_joined_residual,
    )


def consolidate_tracks(
    tracks, bank, fit, association, *, max_gap_s=10.0, check_joined_residual=False
):
    """Join a supplied measurement population without loading a different one."""
    mapping = {t["key"]: t for t in tracks}
    admitted = [r for r in association["rows"] if r["compatible"]]
    rows = []
    if admitted:
        ids = sorted({r["candidate_norad"] for r in admitted})
        lookup = {int(n): i for i, n in enumerate(bank["norad"])}
        indexes = [lookup[n] for n in ids]
        sky = dict(
            time_s=bank["time_s"],
            position_km=bank["position_km"][indexes],
            velocity_km_s=bank["velocity_km_s"][indexes],
        )
        phases = np.asarray(fit["phases_s"])[indexes]
        times = np.unique(np.concatenate([mapping[r["component"]]["times"] for r in admitted]))
        frequency, _ = phase_frequency_grid(
            sky, times, fit["latitude_deg"], fit["longitude_deg"], phase_seconds=phases
        )
        beta = np.asarray(fit["beta"])
        for row in admitted:
            t = mapping[row["component"]]
            ix = np.searchsorted(times, t["times"])
            g = matching.group(t)
            prediction = t["rf_hz"] / 11.5e9 * frequency[ids.index(row["candidate_norad"]), ix]
            prediction += beta[g] + beta[g + 4] * (t["times"] - 150) / 150
            if len(beta) == 9:
                prediction += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
            alias = np.rint(np.mean(prediction - t["values"]) / matching.PERIOD)
            rows.append(
                dict(
                    key=t["key"],
                    candidate_norad=row["candidate_norad"],
                    time_s=t["times"],
                    native_residual_hz=t["values"] + alias * matching.PERIOD - prediction,
                    observation_ids=t["observation_ids"],
                )
            )

    def accept(residual, times):
        return bool(
            np.sqrt(np.mean(residual**2)) <= 450
            and matching.noise_screen(residual, times)["noise_screen_pass"]
        )

    result = consolidate(
        rows,
        accept,
        max_gap_s=max_gap_s,
        accept_joined_residual=accept if check_joined_residual else None,
    )
    if (
        result["points"] != association["compatible_points"]
        or result["points_dropped"]
        or result["identities_changed"]
    ):
        raise ValueError(
            "consolidation changed its fixed admitted population or identity proposals"
        )
    members = [m for g in result["groups"] for m in g["members"]]
    if len(members) != len(set(members)) or set(members) != {r["component"] for r in admitted}:
        raise ValueError("consolidation changed original fragment ownership")
    return result


def run(root, recordings, output, *, search=False):
    output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for path in sorted(root.glob("*/*/fit.json" if search else "*/*/diagnosis.json")):
        case, variant = path.parent.parent.name, path.parent.name
        recording = recordings / ("cohort" if case.startswith("DS22") else "dsx01_adapter") / case
        with np.load(Path("/tmp") / f"ds22-shared-phase-bank-{case}" / "bank.npz") as archive:
            bank = {k: archive[k] for k in archive.files}
        studies = (
            [
                dict(
                    site="blind_endpoint",
                    fit=json.loads(path.read_text())["endpoint"],
                    association=json.loads(path.with_name("association.json").read_text()),
                )
            ]
            if search
            else json.loads(path.read_text())
        )
        for row in studies:
            result = consolidate_fit(recording, bank, row["fit"], row["association"])
            folder = output / case / variant
            folder.mkdir(parents=True, exist_ok=True)
            write(folder / (row["site"] + ".json"), result)
            summaries.append(
                dict(
                    case=case,
                    variant=variant,
                    site=row["site"],
                    **{
                        k: result[k]
                        for k in (
                            "input_tracks",
                            "output_tracks",
                            "points",
                            "points_dropped",
                            "identities_changed",
                        )
                    },
                    input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
    write(output / "summary.json", summaries)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            original_points_preserved=True,
            proposed_identities_preserved=True,
            no_additional_calibration=True,
        ),
    )
    print(
        json.dumps(
            dict(arms=len(summaries), points_dropped=sum(r["points_dropped"] for r in summaries))
        ),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--recordings", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--search", action="store_true")
    a = p.parse_args()
    q = Path("/mnt/qnap01")
    if a.output.resolve() == q or q in a.output.resolve().parents:
        p.error("QNAP is read-only")
    run(a.input, a.recordings, a.output, search=a.search)
