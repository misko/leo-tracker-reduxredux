"""Emit the source-bound receipt for the completed DS13 soft-geometry audit."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "ds13-soft-geometry-audit/v1"
SOURCE_HASHES = {
    "reports/2026_10_02_coherent_localization/common.py": (
        "7e6e80e90af921b6ee25a503cdda8d8cd50ca020589545a30286d1b087725150"
    ),
    "reports/2026_10_02_ds13_timing_em/prepare_scans.py": (
        "ae54ae02bcfb870254f92cfbaf9caeeabd7ffccff39ddb49bc4044203cedca2d"
    ),
    "reports/2026_10_02_ds13_timing_em/protocol-soft.json": (
        "255ad51a23a77b5c7ed9e7039e885abb947ff6553bcedb884bec2e5a7a26bc1e"
    ),
    "reports/2026_10_02_ds13_timing_em/soft_likelihood.py": (
        "f39e55e905db7b563cb9b5a69b5182e01e9894cbd584cfba3496e8dcafb6a8fc"
    ),
    "reports/2026_10_02_ds13_timing_em/timing_model.py": (
        "417a2df103845eabfd0864d64c192b396d786582966a71a18146516fbe8b97d1"
    ),
    "reports/2026_10_02_localization_benchmark/bundle.py": (
        "7450d8f76fddf4cda9a5e35c8a76a0e6dda6f4bb644840b9319e59b27d31f0c2"
    ),
    "reports/2026_10_02_multiscan_localization/finite_set_alias_family.py": (
        "a67cde3fdd21d4e9d183758f8c4242dfbd9709b163a8490ca802c93e01352aa7"
    ),
    "reports/2026_10_02_multiscan_localization/finite_set_likelihood.py": (
        "8b1cdb20230ad25f76bb6e79550c97978f991781b268d9c6f710d86fc42aac66"
    ),
    "reports/2026_10_02_multiscan_localization/joint_inputs.py": (
        "3df86b767c5f6f7173c47db6f7ce34b0200c814b516a0a3d8da0a0059eed5d91"
    ),
    "reports/2026_10_02_multiscan_localization/prediction_jacobian.py": (
        "057e0b9e4a21361c7de31d64206bcd9635179fa649ce4a8f2d494112fe1a7da1"
    ),
    "reports/2026_10_02_multiscan_localization/prediction_plan.py": (
        "52d0dd5d2864c275456d19a9f7f5f8e2089b447c3d9eb8c5d3cbdb300f3a00fc"
    ),
    "reports/2026_10_02_ds13_timing_em/scans/scan-fw-911c4e5db9243281/bundle.json": (
        "4a969537aab3af525a22120dd782048c32a0d80e85e9b16476f411a0cd9c3572"
    ),
    "reports/2026_10_02_ds13_timing_em/scans/scan-fw-911c4e5db9243281/bundle.npz": (
        "2b119508d8a602640d76ea158955471be6d588377e0cc5156ef61fcbb9fae6a4"
    ),
    "reports/2026_10_02_ds13_timing_em/scans/scan-fw-911c4e5db9243281/seed.json": (
        "65d6286685d2c8905b44f6e87ec19dd1ad963eb451bb6ed04621996884bc6fed"
    ),
    "reports/2026_10_02_ds13_timing_em/scans/scan-fw-ffa1cc19d8d7c09f/bundle.json": (
        "8fc67342142000ca7b0d7de2ba92608b5385c4f4cdb81f84f525971640370d7f"
    ),
    "reports/2026_10_02_ds13_timing_em/scans/scan-fw-ffa1cc19d8d7c09f/bundle.npz": (
        "1acb06e66cb29d1c58861f2ec2406146b85b5fb7cfeaa22d2ba5e14b425240f7"
    ),
    "reports/2026_10_02_ds13_timing_em/scans/scan-fw-ffa1cc19d8d7c09f/seed.json": (
        "35e1e98bda9d055a7233307428fa18da47e7bcb6c9c6fa623f30734b3238b28b"
    ),
}


RECEIPT = {
    "schema": SCHEMA,
    "scope": {
        "fits_run": False,
        "reference_or_evaluation_read": False,
        "measurement_point": "Each scan's frozen seed TimingObjective.initial_vector",
        "interpretation": (
            "Read-only local derivative, visibility, and Fisher-conditioning audit; "
            "not a fit, covariance calibration, or accuracy evaluation."
        ),
    },
    "collection": {
        "shell_envelope": (
            "timeout 30s sudo -n env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "
            "MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "
            "PYTHONPATH=reports/2026_10_02_ds13_timing_em:"
            "reports/2026_10_02_multiscan_localization "
            "/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/"
            ".venv/bin/python -"
        ),
        "runs": 2,
        "maximum_wall_time_s_each": 30,
        "parallelism": "single-thread",
        "receipt_command": (
            ".venv/bin/python reports/2026_10_02_ds13_timing_em/audit_soft_geometry.py "
            "--verify-sources"
        ),
        "note": (
            "The numerical values are a transcription of the completed bounded "
            "read-only checks; this command verifies provenance and emits them "
            "without repeating scientific computation."
        ),
    },
    "definitions": {
        "alias_hz": 1.0 / 4.4e-6,
        "sigma_hz": 200.0,
        "detection_probability": "0.8 / selected_satellite_count",
        "clutter_rate": 2.0,
        "prediction_grid_spacing_s": 0.25,
        "timing_finite_difference_steps_s": [1e-4, 1e-3, 1e-2],
        "position_finite_difference_step_km": 1e-3,
        "objective_scaled_coordinate_step": 1e-6,
        "optimizer_scale": [20.0, 20.0, 1000.0, 10.0, 1000.0, 10.0, 1.0],
        "optimizer_scale_tail": "one for global-timing contrast coordinates",
        "timing_cross_knot": (
            "A centered timing stencil whose two endpoints do not retain the "
            "same lower 0.25 s interpolation node as the seed query."
        ),
        "visibility_margin": (
            "Absolute dot product between line of sight and observer up vector."
        ),
        "visibility_perturbations": {
            "east_or_north_km": [1.0, 20.0, 200.0],
            "common_selected_timing_s": [0.1, 1.0, 10.0],
            "signs": [-1, 1],
        },
        "posterior_knot_mass": (
            "Sum of row/satellite association posterior for orbit queries within "
            "the stated distance of an interpolation node."
        ),
        "fisher": (
            "Complete-data prediction_precision normal matrix transformed to the "
            "TimingObjective vector, optimizer-scaled, with global timing variance "
            "100 s^2 and unit individual timing variances added once."
        ),
        "profiled_position_fisher": (
            "Schur complement for east/north after profiling RX and timing columns."
        ),
    },
    "scans": {
        "scan-fw-911c4e5db9243281": {
            "family_rows": 7404,
            "selected_satellites": 13,
            "visibility": {
                "selected_pair_fraction": 1.0,
                "minimum_absolute_margin": 0.057626,
                "flips_under_declared_perturbations": 0,
            },
            "interpolation": {
                "minimum_query_to_knot_s": 1.5035e-5,
                "pairs_within_1e-4_s": 143,
                "pairs_within_1e-3_s": 793,
            },
            "timing_jacobian": {
                "median_absolute_hz_per_s": 969.742,
                "maximum_absolute_hz_per_s": 4431.865,
                "finite_difference": {
                    "1e-4": {
                        "maximum_absolute_difference_all_hz_per_s": 0.1842658,
                        "maximum_absolute_difference_interior_hz_per_s": 3.639e-6,
                        "rms_difference_interior_hz_per_s": 6.996e-7,
                        "cross_knot_pairs": 143,
                    },
                    "1e-3": {
                        "maximum_absolute_difference_all_hz_per_s": 0.2136109,
                        "maximum_absolute_difference_interior_hz_per_s": 6.701e-7,
                        "rms_difference_interior_hz_per_s": 1.562e-7,
                        "cross_knot_pairs": 258,
                    },
                    "1e-2": {
                        "maximum_absolute_difference_all_hz_per_s": 0.2201387,
                        "maximum_absolute_difference_interior_hz_per_s": 5.269e-5,
                        "rms_difference_interior_hz_per_s": 1.477e-5,
                    },
                },
            },
            "position_jacobian": {
                "maximum_absolute_difference_east_hz_per_km": 3.64e-7,
                "maximum_absolute_difference_north_hz_per_km": 7.14e-7,
            },
            "soft_likelihood": {
                "expected_signal_peaks": 1202.474,
                "satellites_with_positive_support": 13,
                "posterior_knot_mass": {
                    "1e-4": {"mass": 1.90095, "fraction": 0.00158086},
                    "1e-3": {"mass": 13.2004, "fraction": 0.0109777},
                    "1e-2": {"mass": 81.4231, "fraction": 0.067713},
                },
            },
            "objective_gradient": {
                "objective": 93396.9655,
                "analytic_scaled_infinity_norm": 20376.81997,
                "numeric_scaled_infinity_norm": 20376.41494,
                "maximum_absolute_raw_difference": 0.0202515,
                "maximum_absolute_scaled_difference": 0.40503,
                "worst_coordinate": "north_km",
            },
            "fisher": {
                "minimum_eigenvalue": 79.1905,
                "maximum_eigenvalue": 1827350.56,
                "condition_number": 23075.38,
                "weakest_eigenvector_block_norms": {
                    "position": 0.13591,
                    "rx": 0.08326,
                    "global_timing": 0.07105,
                    "individual_timing": 0.98466,
                },
                "profiled_position_eigenvalues": [10.14094, 24.87657],
            },
        },
        "scan-fw-ffa1cc19d8d7c09f": {
            "family_rows": 6784,
            "selected_satellites": 15,
            "visibility": {
                "selected_pair_fraction": 1.0,
                "minimum_absolute_margin": 0.0512278,
                "flips_under_declared_perturbations": 0,
            },
            "interpolation": {
                "minimum_query_to_knot_s": 8.4975e-6,
                "pairs_within_1e-4_s": 90,
                "pairs_within_1e-3_s": 1155,
            },
            "timing_jacobian": {
                "median_absolute_hz_per_s": 955.640,
                "maximum_absolute_hz_per_s": 4559.993,
                "finite_difference": {
                    "1e-4": {
                        "maximum_absolute_difference_all_hz_per_s": 0.1910913,
                        "maximum_absolute_difference_interior_hz_per_s": 3.959e-6,
                        "rms_difference_interior_hz_per_s": 7.048e-7,
                        "cross_knot_pairs": 90,
                    },
                    "1e-3": {
                        "maximum_absolute_difference_all_hz_per_s": 0.2070601,
                        "maximum_absolute_difference_interior_hz_per_s": 6.975e-7,
                        "rms_difference_interior_hz_per_s": 1.659e-7,
                        "cross_knot_pairs": 260,
                    },
                    "1e-2": {
                        "maximum_absolute_difference_all_hz_per_s": 0.2247541,
                        "maximum_absolute_difference_interior_hz_per_s": 5.825e-5,
                        "rms_difference_interior_hz_per_s": 1.470e-5,
                    },
                },
            },
            "position_jacobian": {
                "maximum_absolute_difference_east_hz_per_km": 2.242e-7,
                "maximum_absolute_difference_north_hz_per_km": 2.262e-7,
            },
            "soft_likelihood": {
                "expected_signal_peaks": 1014.926,
                "satellites_with_positive_support": 15,
                "posterior_knot_mass": {
                    "1e-4": {"mass": 0.53090, "fraction": 0.00052309},
                    "1e-3": {"mass": 7.30836, "fraction": 0.00720088},
                    "1e-2": {"mass": 89.6256, "fraction": 0.0883076},
                },
            },
            "objective_gradient": {
                "objective": 84400.68145,
                "analytic_scaled_infinity_norm": 23279.35423,
                "numeric_scaled_infinity_norm": 23279.17035,
                "maximum_absolute_raw_difference": 0.0497795,
                "maximum_absolute_scaled_difference": 0.995591,
                "worst_coordinate": "east_km",
            },
            "fisher": {
                "minimum_eigenvalue": 26.9885,
                "maximum_eigenvalue": 1760374.38,
                "condition_number": 65226.79,
                "weakest_eigenvector_block_norms": {
                    "position": 0.11524,
                    "rx": 0.08046,
                    "global_timing": 0.00512,
                    "individual_timing": 0.99006,
                },
                "profiled_position_eigenvalues": [4.99438, 7.91681],
            },
        },
    },
    "conclusion": {
        "derivative_blocker_found": False,
        "finite_difference_absolute_1e-3_certification_supported": False,
        "reason": (
            "Interior paired derivatives agree closely, while complete-objective "
            "centered differences have an observed scaled absolute floor of "
            "0.405 to 0.996 at the seed and timing derivatives kink at orbit nodes."
        ),
        "action": (
            "Use analytic projected gradients for optimization status and treat "
            "finite differences as relative or directional audits with knot-crossing "
            "counts, not as an absolute 1e-3 stationarity certificate."
        ),
    },
    "source_hashes": SOURCE_HASHES,
}


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def verify_sources(root=ROOT):
    root = Path(root)
    mismatches = {}
    for relative, expected in SOURCE_HASHES.items():
        path = root / relative
        actual = digest(path) if path.is_file() else None
        if actual != expected:
            mismatches[relative] = {"expected": expected, "actual": actual}
    return {"available": not mismatches, "mismatches": mismatches}


def receipt():
    return copy.deepcopy(RECEIPT)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-sources", action="store_true")
    args = parser.parse_args(argv)
    result = receipt()
    if args.verify_sources:
        result["source_verification"] = verify_sources()
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
