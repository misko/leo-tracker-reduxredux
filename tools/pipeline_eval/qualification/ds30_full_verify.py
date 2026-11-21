"""Verify the published DS30 tables and independently recompute the position errors."""

import csv
import hashlib
import math

import numpy as np

from .blind_compact_roster import seal
from .ds30_full_inputs import METHODS, OUT
from .reverse_glrt_report import read


def csv_rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def unit(lat, lon):
    phi, lam = np.radians([float(lat), float(lon)])
    return [np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)]


def angle_distance_km(a, b):
    return 6371.0088 * math.atan2(np.linalg.norm(np.cross(a, b)), np.dot(a, b))


def verify(folder=OUT):
    from .ds30_full_score import GROUPS, belongs

    roster = {r["id"]: r for r in read(folder / "cohort.json")["members"]}
    lock = read(folder / "prediction-lock.json")
    fingerprints = {(r["case"], r["method"]): r["prediction_sha256"] for r in lock["predictions"]}
    reference = {
        r["dataset_label"]: r["reference"] for r in read(folder / "reference-audit.json")["cases"]
    }
    outcomes = csv_rows(folder / "recordings.csv")
    keyed = {(r["case"], r["method"], r["calibration"]): r for r in outcomes}
    if (
        len(keyed) != 4 * len(roster)
        or len(outcomes) != len(keyed)
        or len(fingerprints) != 2 * len(roster)
        or set(roster) != set(reference)
    ):
        raise ValueError("incomplete or duplicate exported measurements")
    fixed = 0
    for case, assignment in roster.items():
        for method in METHODS:
            for arm in ("c0", "fitted_c"):
                r = keyed[case, method, arm]
                if (
                    r["prediction_sha256"] != fingerprints[case, method]
                    or r["recording_state"] != assignment["recording_state"]
                ):
                    raise ValueError("CSV identity differs from the locked roster")
                if (r["fix"] == "True") != bool(r["latitude"] and r["longitude"]):
                    raise ValueError("inconsistent published endpoint")
                truth = reference[case]
                if truth and r["fix"] == "True":
                    distance = angle_distance_km(
                        unit(truth["latitude_deg"], truth["longitude_deg"]),
                        unit(r["latitude"], r["longitude"]),
                    )
                    if not math.isclose(distance, float(r["error_km"]), abs_tol=2e-8):
                        raise ValueError(
                            "position error differs from independent great-circle distance"
                        )
                    fixed += 1
                elif r["error_km"]:
                    raise ValueError("distance published without a fix and reference")
    summaries = csv_rows(folder / "summary.csv")
    if len(summaries) != len(GROUPS) * 4:
        raise ValueError("incomplete calibration and recording-group summaries")
    for s in summaries:
        sample = [
            keyed[k, s["method"], s["calibration"]]
            for k, v in roster.items()
            if belongs(v, s["group"])
        ]
        km = [float(r["error_km"]) for r in sample if r["error_km"]]
        if (
            len(sample) != int(s["assigned"])
            or len(km) != int(s["scored_fixes"])
            or sum(r["fix"] == "True" for r in sample) != int(s["fixes"])
        ):
            raise ValueError("summary denominator or fix count differs")
        for limit in (1, 2, 5):
            if sum(e <= limit for e in km) != int(s[f"within_{limit}km"]):
                raise ValueError("unconditional accuracy threshold count differs")
        if km:
            for percentile in (50, 90, 95, 99):
                if not math.isclose(
                    float(np.percentile(km, percentile)),
                    float(s[f"p{percentile}_km"]),
                    abs_tol=1e-10,
                ):
                    raise ValueError("conditional error percentile differs")
        times = [float(r["end_to_end_wall_s"]) for r in sample if r["end_to_end_wall_s"]]
        if len(times) != int(s["end_to_end_wall_s_n"]) or (
            times
            and not math.isclose(np.median(times), float(s["end_to_end_wall_s_p50"]), abs_tol=1e-8)
        ):
            raise ValueError("end-to-end timing count or median differs")
    files = (
        "cohort.json",
        "build.json",
        "prediction-lock.json",
        "reference-audit.json",
        "recordings.csv",
        "summary.csv",
        "paired.csv",
        "paired-summary.csv",
        "repeated-panel.csv",
        "position-error.png",
        "runtime.png",
    )
    checksums = {f: hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in files}
    if (folder / "failures.csv").exists():
        checksums["failures.csv"] = hashlib.sha256(
            (folder / "failures.csv").read_bytes()
        ).hexdigest()
    seal(
        folder / "verification.json",
        dict(
            verified=True,
            members=len(roster),
            pipeline_outcomes=len(fingerprints),
            calibration_rows=len(outcomes),
            independently_verified_distances=fixed,
            artifacts=checksums,
        ),
    )
    return fixed


if __name__ == "__main__":
    print("Verified horizontal distances:", verify())
