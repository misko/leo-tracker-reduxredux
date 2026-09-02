#!/usr/bin/env python3
"""Verify the five-capture PSS/GLRT/TLE study and its report are complete."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--tle", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_artifact(root: Path, artifact: dict[str, Any], label: str) -> None:
    path = root / artifact["path"]
    require(path.is_file(), f"{label} is missing: {path}")
    require(sha256(path) == artifact["sha256"], f"{label} digest mismatch: {path}")


def main() -> None:
    args = arguments()
    cohort = json.loads(args.cohort.read_text(encoding="utf-8"))
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    tle = json.loads(args.tle.read_text(encoding="utf-8"))
    report = args.report.read_text(encoding="utf-8")

    selected_ids = [item["session_id"] for item in cohort["selected"]]
    require(len(selected_ids) == 5, "cohort does not contain exactly five captures")
    require(len(set(selected_ids)) == 5, "cohort capture IDs are not unique")
    require(
        cohort["selection_policy"]["minimum_native25_observed_density"] == 0.5,
        "native-25 density gate changed",
    )
    require(
        cohort["selection_policy"]["rank_order"]
        == [
            "descending best receiver passing fraction",
            "descending best receiver median passing margin",
            "descending longest Hough span",
            "ascending session ID",
        ],
        "cohort ranking policy changed",
    )
    for selected in cohort["selected"]:
        require(
            selected["stream_25m"]["observed_density"] >= 0.5,
            f"{selected['session_id']} violates the native-density gate",
        )
        require(
            len(selected["glrt_2p5m"]) == 2,
            f"{selected['session_id']} does not have dual GLRT products",
        )

    require(
        analysis["analysis_kind"] == "five-paired-native25-pss-vs-dual2p5-glrt",
        "unexpected PSS/GLRT analysis kind",
    )
    analysis_source = Path(analysis["source"]["path"])
    require(analysis_source.is_file(), "PSS/GLRT analysis source is missing")
    require(
        sha256(analysis_source) == analysis["source"]["sha256"],
        "PSS/GLRT analysis source changed after evidence generation",
    )
    require(analysis["cohort"]["sha256"] == sha256(args.cohort), "cohort digest mismatch")
    analysis_ids = [item["capture_id"] for item in analysis["captures"]]
    require(analysis_ids == selected_ids, "analysis capture order does not match the cohort")
    require(
        analysis["method"]["pss_search_rate"]
        == "native 25 MS/s; decimation factor 1; no edge trim",
        "analysis is not native-rate PSS",
    )
    for capture in analysis["captures"]:
        capture_id = capture["capture_id"]
        pss_path = Path(capture["pss_input"]["path"])
        require(pss_path.is_file(), f"{capture_id} PSS replay is missing")
        require(
            sha256(pss_path) == capture["pss_input"]["sha256"],
            f"{capture_id} PSS replay digest mismatch",
        )
        pss = json.loads(pss_path.read_text(encoding="utf-8"))
        projection = pss["projection"]
        require(projection["input_sample_rate_hz"] == 25_000_000, "wrong PSS input rate")
        require(projection["output_sample_rate_hz"] == 25_000_000, "wrong PSS output rate")
        require(projection["decimation_factor"] == 1, "PSS replay was decimated")
        require(projection["edge_trim_output_samples"] == 0, "PSS replay was edge trimmed")
        require(
            projection["input_center_frequency_hz"] == capture["native25"]["center_frequency_hz"],
            "PSS replay input center does not match the native stream",
        )
        require(
            projection["output_center_frequency_hz"] == projection["input_center_frequency_hz"],
            "PSS replay translated the native capture",
        )
        require(
            pss["configuration"]["maximum_block_duration_s"] == 0.25,
            "wrong PSS block duration",
        )
        require(
            pss["configuration"]["block_stride_duration_s"] == 0.125,
            "wrong PSS stride",
        )
        verify_artifact(args.analysis.parent, capture["figure"], f"{capture_id} diagnostic")
        track = capture["pss"]["independent_track"]
        if track is not None:
            require(track["mode_count"] >= 6, f"{capture_id} track is below minimum support")
            require(track["span_s"] >= 2.0, f"{capture_id} track is below minimum span")
            require(
                track["absolute_utc_phase"]["unique_absolute_frame_cycle_resolved"] is False,
                f"{capture_id} unexpectedly claims an absolute frame cycle",
            )
            require(
                track["coverage"]["unique_strong_frame_epoch_count"] > 0,
                f"{capture_id} has no dense frame evidence",
            )
            for key in (
                "quadratic_physical_equivalent_doppler_hz_at_reference",
                "quadratic_physical_equivalent_doppler_rate_hz_s_at_reference",
            ):
                require(
                    math.isfinite(float(track[key])),
                    f"{capture_id} has no finite PSS Doppler estimate: {key}",
                )
            verify_artifact(
                args.analysis.parent,
                capture["frame_offset_figure"],
                f"{capture_id} frame offset",
            )
            comparison = capture["comparison"]
            require(comparison is not None, f"{capture_id} omits PSS/GLRT comparison")
            alignments = comparison["integrated_phase_alignment_by_receiver"]
            require(alignments, f"{capture_id} has no common-support integrated alignment")
            for alignment in alignments:
                require(
                    alignment["measurement_count"] >= 6,
                    f"{capture_id} integrated alignment has insufficient PSS support",
                )
                for model_name in (
                    "physical_pss_vs_recorded_glrt_iq",
                    "same_sign_pss_vs_recorded_glrt_iq_control",
                ):
                    require(
                        alignment[model_name]["holdout_rms_ratio_to_affine_null"] >= 0.0,
                        f"{capture_id} has invalid integrated alignment score",
                    )
            for rate_row in comparison["rate_rows"]:
                for key in (
                    "glrt_cfo_rate_hz_s",
                    "glrt_fractional_cfo_rate_s_inverse",
                    "pss_physical_equivalent_doppler_rate_hz_s_at_glrt_rf",
                ):
                    require(
                        math.isfinite(float(rate_row[key])),
                        f"{capture_id} has no finite common-rate estimate: {key}",
                    )
    verify_artifact(
        args.analysis.parent,
        analysis["artifacts"]["rate_and_fitness_figure"],
        "cohort rate/fitness figure",
    )
    pss_track_count = sum(
        item["pss"]["independent_track"] is not None for item in analysis["captures"]
    )
    require(pss_track_count > 0, "none of the five native-25 replays produced a PSS track")
    for capture in analysis["captures"]:
        if capture["pss"]["independent_track"] is not None:
            continue
        capture_id = capture["capture_id"]
        sensitivity_path = args.analysis.parent / f"{capture_id}-pss-association-sensitivity.json"
        require(
            sensitivity_path.is_file(),
            f"{capture_id} post-hoc association sensitivity is missing",
        )
        sensitivity = json.loads(sensitivity_path.read_text(encoding="utf-8"))
        require(
            sensitivity["analysis_kind"] == "post-hoc-pss-only-association-gate-sensitivity",
            f"{capture_id} has the wrong sensitivity analysis kind",
        )
        sensitivity_source = Path(sensitivity["source"]["path"])
        require(
            sensitivity_source.is_file()
            and sha256(sensitivity_source) == sensitivity["source"]["sha256"],
            f"{capture_id} sensitivity source changed after evidence generation",
        )
        require(
            sensitivity["input"]["sha256"] == capture["pss_input"]["sha256"],
            f"{capture_id} sensitivity used the wrong PSS input",
        )
        require(
            sensitivity["published_track_count"] == 0,
            f"{capture_id} sensitivity is not for a primary no-track result",
        )
        require(
            "exploratory" in sensitivity["interpretation_guard"],
            f"{capture_id} sensitivity lacks an interpretation guard",
        )
        default = sensitivity["results"][0]
        require(
            default["label"] == "published_default"
            and default["selected_mode_count"] > 0
            and default["would_publish"] is False,
            f"{capture_id} is not a documented default near miss",
        )
        require(
            any(result.get("would_publish") for result in sensitivity["results"][1:]),
            f"{capture_id} has no publishing exploratory sensitivity",
        )
        sensitivity_figure_path = Path(sensitivity["figure"]["path"])
        require(
            sensitivity_figure_path.is_file(),
            f"{capture_id} association sensitivity figure is missing",
        )
        require(
            sha256(sensitivity_figure_path) == sensitivity["figure"]["sha256"],
            f"{capture_id} association sensitivity figure digest mismatch",
        )
        require(
            sensitivity_path.name in report and Path(sensitivity["figure"]["path"]).name in report,
            f"report does not link {capture_id} association sensitivity evidence",
        )

    require(
        tle["analysis_kind"] == "five-capture-independent-and-joint-pss-glrt-causal-tle-ranking",
        "unexpected TLE analysis kind",
    )
    tle_source = Path(tle["source"]["path"])
    require(tle_source.is_file(), "TLE association source is missing")
    require(
        sha256(tle_source) == tle["source"]["sha256"],
        "TLE association source changed after evidence generation",
    )
    require(tle["input"]["sha256"] == sha256(args.analysis), "TLE input digest mismatch")
    require(tle["method"]["fixed_capture_time"] is True, "TLE time is not fixed")
    require(tle["method"]["time_shift_fitted"] is False, "TLE time shift was fitted")
    require(tle["method"]["doppler_scale_fitted"] is False, "TLE scale was fitted")
    require(
        tle["method"]["slope_or_curvature_fitted_to_tle"] is False,
        "TLE slope/curvature was fitted",
    )
    tle_ids = [item["capture_id"] for item in tle["captures"]]
    require(tle_ids == selected_ids, "TLE capture order does not match the cohort")
    analysis_by_capture = {item["capture_id"]: item for item in analysis["captures"]}
    for capture in tle["captures"]:
        capture_id = capture["capture_id"]
        require(
            capture["tle"]["collection_utc_ns"] <= capture["first_sample_estimate_utc_ns"],
            f"{capture_id} uses a future TLE snapshot",
        )
        tle_path = Path(capture["tle"]["path"])
        require(tle_path.is_file(), f"{capture_id} causal TLE snapshot is missing")
        require(
            sha256(tle_path) == capture["tle"]["sha256"],
            f"{capture_id} causal TLE snapshot digest mismatch",
        )
        require(
            capture["accounting"]["horizon_visible_candidate_count"] > 1,
            f"{capture_id} has no meaningful TLE ranking",
        )
        expected_receivers = {
            str(path["receiver_id"])
            for path in analysis_by_capture[capture_id]["glrt"]["paths"]
            if path["stitched_family"] is not None
        }
        require(
            set(capture["headline"]["glrt_physical_best_by_receiver"]) == expected_receivers,
            f"{capture_id} omits a usable GLRT receiver ranking",
        )
        require(
            capture["headline"]["glrt_all_receiver_physical_best"] is not None,
            f"{capture_id} omits the dual-receiver GLRT consensus ranking",
        )
        require(
            capture["headline"]["glrt_all_receiver_anchor_sensitivity_best"] is not None,
            f"{capture_id} omits the dual-receiver anchor sensitivity ranking",
        )
        require(
            set(capture["headline"]["glrt_anchor_sensitivity_best_by_receiver"])
            == expected_receivers,
            f"{capture_id} omits the single-episode GLRT sensitivity ranking",
        )
        require(
            set(capture["specificity"]["glrt_anchor_sensitivity"]) == expected_receivers,
            f"{capture_id} omits GLRT anchor sensitivity specificity",
        )
        pss_track = analysis_by_capture[capture_id]["pss"]["independent_track"]
        if pss_track is None:
            require(
                capture["headline"]["pss_physical_best"] is None,
                f"{capture_id} claims a PSS ranking without a PSS track",
            )
            require(
                capture["headline"]["joint_all_receiver_physical_best"] is None,
                f"{capture_id} claims a joint ranking without a PSS track",
            )
        else:
            require(
                capture["accounting"]["pss_block_median_count"] == pss_track["mode_count"],
                f"{capture_id} TLE ranking used the wrong PSS measurements",
            )
            require(
                capture["headline"]["pss_physical_best"] is not None,
                f"{capture_id} omits independent PSS ranking",
            )
            require(
                capture["headline"]["joint_all_receiver_physical_best"] is not None,
                f"{capture_id} omits joint PSS/dual-GLRT ranking",
            )
        verify_artifact(
            args.tle.parent,
            capture["figure"],
            f"{capture_id} TLE ranking",
        )
        verify_artifact(
            args.tle.parent,
            capture["fit_figure"],
            f"{capture_id} TLE fit diagnostic",
        )
    verify_artifact(
        args.tle.parent,
        tle["artifacts"]["cohort_summary"],
        "cohort TLE summary",
    )

    require("**Status:** complete" in report, "report is not marked complete")
    require("<!-- Populated" not in report, "report still contains a result placeholder")
    for capture_id in selected_ids:
        require(capture_id in report, f"report omits {capture_id}")
    for capture in analysis["captures"]:
        capture_id = capture["capture_id"]
        require(
            capture["figure"]["path"] in report,
            f"report does not link {capture_id} PSS/GLRT diagnostic",
        )
        if capture["frame_offset_figure"] is not None:
            require(
                capture["frame_offset_figure"]["path"] in report,
                f"report does not link {capture_id} frame-offset figure",
            )
    require(
        analysis["artifacts"]["rate_and_fitness_figure"]["path"] in report,
        "report does not link the cohort rate/fitness figure",
    )
    for capture in tle["captures"]:
        capture_id = capture["capture_id"]
        require(
            capture["figure"]["path"] in report,
            f"report does not link {capture_id} TLE ranking figure",
        )
        require(
            capture["fit_figure"]["path"] in report,
            f"report does not link {capture_id} TLE fit diagnostic",
        )
        receiver = str(capture["primary_best_receiver_id"])
        glrt_best = capture["headline"]["glrt_physical_best_by_receiver"][receiver]
        glrt_dual_best = capture["headline"]["glrt_all_receiver_physical_best"]
        require(
            f"{glrt_best['object_name']} / {glrt_best['norad_id']}" in report,
            f"report omits {capture_id} primary GLRT TLE candidate",
        )
        require(
            f"{glrt_dual_best['object_name']} / {glrt_dual_best['norad_id']}" in report,
            f"report omits {capture_id} dual-receiver GLRT TLE candidate",
        )
        if capture["headline"]["pss_physical_best"] is not None:
            pss_best = capture["headline"]["pss_physical_best"]
            joint_best = capture["headline"]["joint_all_receiver_physical_best"]
            require(
                f"{pss_best['object_name']} / {pss_best['norad_id']}" in report,
                f"report omits {capture_id} independent PSS TLE candidate",
            )
            require(joint_best is not None, f"{capture_id} joint candidate is missing")
            require(
                f"{joint_best['object_name']} / {joint_best['norad_id']}" in report,
                f"report omits {capture_id} joint physical TLE candidate",
            )
    require(
        tle["artifacts"]["cohort_summary"]["path"] in report,
        "report does not link the cohort TLE summary figure",
    )
    require(args.analysis.name in report, "report does not link PSS/GLRT evidence JSON")
    require(args.tle.name in report, "report does not link TLE evidence JSON")
    required_phrases = (
        "Five-capture results",
        "Common-rate Doppler comparison and sign",
        "Causal-TLE association",
        "Artifact interpretation guide",
        "Completion audit",
    )
    for phrase in required_phrases:
        require(phrase in report, f"report omits required section: {phrase}")

    print(
        json.dumps(
            {
                "verified": True,
                "capture_count": len(selected_ids),
                "pss_track_count": sum(
                    item["pss"]["independent_track"] is not None for item in analysis["captures"]
                ),
                "report": str(args.report),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
