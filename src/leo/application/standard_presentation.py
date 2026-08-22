"""Authoritative Standard-v2 projection over sealed catalog products."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from leo.analysis.research.analyzers import research_product_kind
from leo.analysis.standard.codecs import decode_standard_product
from leo.analysis.standard.products import (
    ALTERNATE_CFO_TRACK_BANK_PRODUCT,
    ALTERNATE_CFO_TRACKS_PNG_PRODUCT,
    CFO_TRAJECTORIES_PNG_PRODUCT,
    DEALIASED_CFO_TRAJECTORIES_PNG_PRODUCT,
    FINAL_CFO_TRAJECTORIES_PNG_PRODUCT,
    PATH_PRESENTATION_PRODUCT,
    PILOT_METHODS_PNG_PRODUCT,
    TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_PRODUCT,
    TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_V1_PRODUCT,
    WATERFALL_PNG_PRODUCT,
)
from leo.artifacts import AnalysisArtifactStore, AnalysisRunManifestV2, parse_analysis_run_manifest
from leo.catalog import CatalogRepository
from leo.catalog.types import CatalogJobRecord, CatalogProductRecord, CatalogSessionReadSnapshot
from leo.contracts.alternate_cfo_tracks import AlternateCfoTrackV1, AlternateCfoTrackV2
from leo.contracts.digests import canonical_digest
from leo.contracts.pipeline_lanes import PipelineLane
from leo.contracts.research_pipeline import ResearchProductEnvelopeV1
from leo.contracts.standard_pipeline import StandardPathInputBindV3
from leo.pipeline.scopes import ScopeIdentityV1, ScopeKind
from leo.presentation.standard_pipeline import (
    StandardAlternateCfoTrackRowV2,
    StandardAxisBoundsV2,
    StandardCfoObservationV2,
    StandardComputationDispositionV2,
    StandardLaneSourceExtremaV2,
    StandardMetricSeriesV2,
    StandardPathEvidenceV2,
    StandardPipelineReleaseV2,
    StandardPlotViewV2,
    StandardReceiverPathRefV2,
    StandardReplayAuditRowV1,
    StandardReplayAuditV1,
    StandardReuseSummaryV2,
    StandardSeriesPointV2,
    StandardSourceAxisExtremaV2,
    StandardSourceAxisIdV2,
    StandardSourceExtremaProofV2,
    StandardSourceTypeV2,
    StandardStageStatusV2,
    StandardSubjectDetailV2,
    StandardSubjectHierarchyV2,
    StandardSubjectKindV2,
    StandardSubjectStateV2,
    StandardSubjectSummaryV2,
    StandardTimeDomainV2,
    StandardTrackGateAuditV1,
    StandardTrackGateCellV1,
    StandardTrackGateRowV1,
    StandardTrackGateStageV1,
    StandardTrajectoryCurveV2,
    StandardTrajectoryRowV2,
    StandardUnitV2,
    StandardViewDescriptorV2,
    StandardViewKindV2,
    StandardViewStateV2,
    StandardWaterfallCellV2,
    standard_eligibility_v2,
    standard_source_extrema_from_lanes_v2,
)


class StandardPresentationUnavailable(RuntimeError):
    """The selected run or one of its immutable presentation inputs is invalid."""


class StandardPresentationNotReady(RuntimeError):
    """The selected run has not sealed presentation products yet."""


_TRACK_GATE_STAGE_ORDER = (
    "trajectory-fit",
    "trajectory-feedback",
    "alias-map",
    "dealias-refinement",
    "lift-replay",
    "final-selection",
)


def _gate_cell(
    key: str,
    label: str,
    value: object,
    criterion: str,
    verdict: str,
) -> StandardTrackGateCellV1:
    if isinstance(value, float):
        rendered = f"{value:.6g}"
    elif isinstance(value, bool):
        rendered = "yes" if value else "no"
    elif value is None:
        rendered = "unavailable"
    else:
        rendered = str(value)
    return StandardTrackGateCellV1(
        gate_key=key,
        label=label,
        value=rendered,
        criterion=criterion,
        verdict=cast(Any, verdict),
    )


def _track_gate_stages(
    receiver_path_id: str, document: dict[str, Any]
) -> tuple[StandardTrackGateStageV1, ...]:
    """Project persisted track decisions without rerunning scientific gates."""

    stages: list[StandardTrackGateStageV1] = []
    bank = cast(dict[str, Any], document["trajectory_bank"])
    table = cast(dict[str, Any], document["trajectory_table"])
    glrt_rows = [
        cast(dict[str, Any], row)
        for row in cast(list[Any], bank["trajectories"])
        if row["method"] == "glrt64"
    ]
    table_by_id = {
        str(row["trajectory_id"]): cast(dict[str, Any], row)
        for row in cast(list[dict[str, Any]], table["trajectories"])
    }
    fit_gate = float(table["fit_gate_hz"])
    hough_bank = int(bank.get("schema_version", 0)) == 3
    fit_rows = tuple(
        StandardTrackGateRowV1(
            receiver_path_id=receiver_path_id,
            track_id=str(row["trajectory_id"]),
            disposition="passed",
            reason="retained in the immutable fitted-trajectory bank",
            gates=(
                _gate_cell(
                    "start-time",
                    "Start",
                    float(row["start_s"]),
                    "persisted segment boundary (s)",
                    "audit",
                ),
                _gate_cell(
                    "end-time",
                    "End",
                    float(row["end_s"]),
                    "persisted segment boundary (s)",
                    "audit",
                ),
                *(
                    (
                        _gate_cell(
                            "slope",
                            "Slope",
                            float(row["coefficients_hz"][0]),
                            "Hz/s; original Hough segment coefficient",
                            "audit",
                        ),
                        _gate_cell(
                            "intercept",
                            "CFO at reference",
                            float(row["coefficients_hz"][-1]),
                            f"Hz at t={float(row['reference_time_s']):.6g} s",
                            "audit",
                        ),
                    )
                    if int(row["polynomial_degree"]) == 1
                    else (
                        _gate_cell(
                            "model-order",
                            "Legacy model order",
                            int(row["polynomial_degree"]),
                            "persisted historical polynomial order",
                            "audit",
                        ),
                    )
                ),
                _gate_cell(
                    "support",
                    "Support",
                    int(row["point_count"]),
                    "retained fit support",
                    "pass",
                ),
                _gate_cell(
                    "high-threshold",
                    "High threshold",
                    float(row["high_gate"]),
                    "data-derived detection threshold (audit)",
                    "audit",
                ),
                _gate_cell(
                    "fit-residual",
                    "Fit residual RMS",
                    float(row["residual_rms_hz"]),
                    f"≤ {fit_gate:.6g} Hz",
                    "pass" if float(row["residual_rms_hz"]) <= fit_gate else "fail",
                ),
            ),
        )
        for row in glrt_rows
    )
    stages.append(
        StandardTrackGateStageV1(
            stage_key="trajectory-fit",
            label="Original Hough segments" if hough_bank else "Legacy fitted trajectories",
            description=(
                "Accepted initial and residual-Hough line segments before alias selection "
                "or robust coefficient refinement."
                if hough_bank
                else "Tracks retained by the persisted legacy polynomial fitter."
            ),
            source_track_count=len(fit_rows),
            rows=fit_rows,
            truncated=False,
            limitation=(
                "Rejected pre-fit seeds are not persisted, so this is the complete "
                "survivor inventory; "
                "it cannot reconstruct rows for discarded seed attempts."
            ),
        )
    )

    representatives = {
        str(row["trajectory_id"])
        for row in cast(list[dict[str, Any]], bank["replayed_representatives"])
    }
    feedback_rows = tuple(
        StandardTrackGateRowV1(
            receiver_path_id=receiver_path_id,
            track_id=str(row["trajectory_id"]),
            disposition="passed" if str(row["trajectory_id"]) in representatives else "dropped",
            reason=(
                "selected as a family representative for trajectory feedback"
                if str(row["trajectory_id"]) in representatives
                else "retained as fitted geometry but not selected as a feedback representative"
            ),
            gates=(
                _gate_cell(
                    "fit-quality",
                    "Fit quality",
                    bool(table_by_id[str(row["trajectory_id"])]["fit_matches_well"]),
                    f"residual RMS ≤ {fit_gate:.6g} Hz",
                    "pass"
                    if bool(table_by_id[str(row["trajectory_id"])]["fit_matches_well"])
                    else "fail",
                ),
                _gate_cell(
                    "family-representative",
                    "Family representative",
                    str(row["trajectory_id"]) in representatives,
                    "selected within bounded replay-family inventory",
                    "pass" if str(row["trajectory_id"]) in representatives else "fail",
                ),
            ),
        )
        for row in glrt_rows
        if str(row["trajectory_id"]) in table_by_id
    )
    stages.append(
        StandardTrackGateStageV1(
            stage_key="trajectory-feedback",
            label="Trajectory feedback selection",
            description="Fitted GLRT64 tracks considered for the bounded first feedback replay.",
            source_track_count=len(feedback_rows),
            rows=feedback_rows,
            truncated=False,
        )
    )

    alias_map = cast(dict[str, Any], document["cfo_alias_map"])
    components = {
        str(item["component_id"]): cast(dict[str, Any], item)
        for item in cast(list[dict[str, Any]], alias_map["components"])
    }
    pairs = cast(list[dict[str, Any]], alias_map["pair_decisions"])
    alias_rows: list[StandardTrackGateRowV1] = []
    for member in cast(list[dict[str, Any]], alias_map["members"]):
        track_id = str(member["trajectory_id"])
        component = components[str(member["component_id"])]
        related = [
            pair
            for pair in pairs
            if track_id in (str(pair["left_trajectory_id"]), str(pair["right_trajectory_id"]))
        ]
        statuses: dict[str, int] = defaultdict(int)
        for pair in related:
            statuses[str(pair["status"])] += 1
        resolved = str(component["status"]) == "resolved"
        alias_rows.append(
            StandardTrackGateRowV1(
                receiver_path_id=receiver_path_id,
                track_id=track_id,
                disposition="passed" if resolved else "dropped",
                reason=str(component["reason"]),
                gates=(
                    _gate_cell(
                        "pair-decisions",
                        "Pair decisions",
                        ", ".join(f"{key}: {statuses[key]}" for key in sorted(statuses)) or "none",
                        "persisted pairwise overlap/alias-residual decisions",
                        "audit",
                    ),
                    _gate_cell(
                        "component-consistency",
                        "Component consistency",
                        int(component["contradictory_edge_count"]),
                        "contradictory edges = 0",
                        "pass" if resolved else "fail",
                    ),
                ),
            )
        )
    stages.append(
        StandardTrackGateStageV1(
            stage_key="alias-map",
            label="Alias-graph resolution",
            description="Raw representative tracks grouped by integer CFO-alias relationships.",
            source_track_count=int(alias_map["source_representative_count"]),
            rows=tuple(alias_rows),
            truncated=int(alias_map["truncated_representative_count"]) > 0,
        )
    )

    dealiased = cast(dict[str, Any], document["dealiased_trajectory_bank"])
    if "seed_dispositions" in dealiased:
        branch_by_seed = {
            str(branch["seed_trajectory_id"]): cast(dict[str, Any], branch)
            for branch in cast(list[dict[str, Any]], dealiased["branches"])
            if "seed_trajectory_id" in branch
        }
        dealias_row_values: list[StandardTrackGateRowV1] = []
        for row in cast(list[dict[str, Any]], dealiased["seed_dispositions"]):
            seed_id = str(row["seed_trajectory_id"])
            gates: list[StandardTrackGateCellV1] = []
            branch = branch_by_seed.get(seed_id)
            if branch is not None:
                model = cast(dict[str, Any], branch["model"])
                gates.extend(
                    (
                        _gate_cell(
                            "start-time",
                            "Start",
                            float(model["start_s"]),
                            "final segment boundary (s)",
                            "audit",
                        ),
                        _gate_cell(
                            "end-time",
                            "End",
                            float(model["end_s"]),
                            "final segment boundary (s)",
                            "audit",
                        ),
                        _gate_cell(
                            "huber-slope",
                            "Huber slope",
                            float(model["coefficients_hz"][0]),
                            "MAD-scaled Huber IRLS coefficient (Hz/s)",
                            "audit",
                        ),
                        _gate_cell(
                            "huber-intercept",
                            "CFO at reference",
                            float(model["coefficients_hz"][1]),
                            f"Hz at t={float(model['reference_time_s']):.6g} s",
                            "audit",
                        ),
                        _gate_cell(
                            "huber-mad-scale",
                            "Huber MAD scale",
                            float(model["mad_scale_hz"]),
                            "max(100 Hz, 1.4826 × residual MAD)",
                            "audit",
                        ),
                        _gate_cell(
                            "huber-median-residual",
                            "Median |residual|",
                            float(model["median_absolute_residual_hz"]),
                            "final seed-preserving robust residual (Hz)",
                            "audit",
                        ),
                        _gate_cell(
                            "huber-convergence",
                            "Huber converged",
                            bool(model["converged"]),
                            "MAD-scaled Huber IRLS, c=1.345",
                            "pass" if bool(model["converged"]) else "fail",
                        ),
                    )
                )
            gates.extend(
                (
                    _gate_cell(
                        "seed-closure",
                        "Seed closure",
                        str(row["output_branch_id"])[7:19],
                        "exactly one output branch per input seed",
                        "pass",
                    ),
                    _gate_cell(
                        "probe-retention",
                        "Probe retention",
                        f"{row['selected_probe_count']} / {row['source_observation_count']}",
                        "one candidate and alias per represented seed probe",
                        "audit",
                    ),
                    _gate_cell(
                        "alias-convergence",
                        "Alias EM converged",
                        bool(row["converged"]),
                        f"within {row['iteration_count']} recorded iteration(s)",
                        "audit",
                    ),
                    _gate_cell(
                        "refined-residual",
                        "Refined residual RMS",
                        float(row["residual_rms_hz"]),
                        "persisted final robust refinement metric",
                        "audit",
                    ),
                )
            )
            dealias_row_values.append(
                StandardTrackGateRowV1(
                    receiver_path_id=receiver_path_id,
                    track_id=seed_id,
                    disposition="retained",
                    reason=str(row["reason"]),
                    gates=tuple(gates),
                )
            )
        dealias_rows = tuple(dealias_row_values)
        dealias_limitation = None
    else:
        dealias_rows = tuple(
            StandardTrackGateRowV1(
                receiver_path_id=receiver_path_id,
                track_id=str(row["branch_id"]),
                disposition="retained",
                reason="retained canonical branch",
                gates=(
                    _gate_cell(
                        "observations",
                        "Observations",
                        len(row["observation_ids"]),
                        "persisted canonical support",
                        "audit",
                    ),
                    _gate_cell(
                        "selected-model",
                        "Selected model",
                        str(row["selected_model_id"])[7:19],
                        "persisted model choice",
                        "audit",
                    ),
                ),
            )
            for row in cast(list[dict[str, Any]], dealiased["branches"])
        )
        dealias_limitation = "This legacy product predates per-seed refinement dispositions."
    stages.append(
        StandardTrackGateStageV1(
            stage_key="dealias-refinement",
            label=(
                "Huber residual refinement"
                if int(dealiased.get("schema_version", 0)) == 4
                else "Seed-preserving de-alias refinement"
            ),
            description=(
                "Each Hough seed retains fixed segment membership while alias selection is "
                "followed by MAD-scaled Huber IRLS with c=1.345."
                if int(dealiased.get("schema_version", 0)) == 4
                else "Each upstream seed is refined into exactly one canonical modulo-alias branch."
            ),
            source_track_count=int(dealiased["source_branch_count"]),
            rows=dealias_rows,
            truncated=bool(dealiased["truncated_branch_count"]),
            limitation=dealias_limitation,
        )
    )

    replay = cast(dict[str, Any], document["cfo_lift_replay"])
    if int(replay["schema_version"]) != 4:
        legacy_rows = tuple(
            StandardTrackGateRowV1(
                receiver_path_id=receiver_path_id,
                track_id=f"{row['branch_id']}:{row['alias_index']}",
                disposition="passed" if row["status"] == "supported" else "dropped",
                reason=str(row["reason"]),
                gates=(
                    _gate_cell(
                        "probe-count",
                        "Replay probes",
                        int(row["evaluated_probe_count"]),
                        "legacy replay inventory",
                        "audit",
                    ),
                    _gate_cell(
                        "margin-delta",
                        "Median margin delta",
                        row["median_margin_delta"],
                        "legacy relative-evidence decision",
                        "pass" if row["status"] == "supported" else "fail",
                    ),
                ),
            )
            for row in cast(list[dict[str, Any]], replay["rows"])
        )
        stages.append(
            StandardTrackGateStageV1(
                stage_key="lift-replay",
                label="Legacy absolute-lift replay",
                description="Persisted replay disposition from a pre-V4 product.",
                source_track_count=int(replay["source_lift_count"]),
                rows=legacy_rows,
                truncated=int(replay["truncated_lift_count"]) > 0,
                limitation="Exact V4 gate columns are unavailable for this legacy product.",
            )
        )
        final = cast(dict[str, Any], document["final_trajectory_bank"])
        legacy_final_rows = tuple(
            StandardTrackGateRowV1(
                receiver_path_id=receiver_path_id,
                track_id=str(row["trajectory_id"]),
                disposition="retained",
                reason="retained in the persisted legacy final inventory",
                gates=(
                    _gate_cell(
                        "final-retention",
                        "Final retention",
                        True,
                        "persisted legacy final decision",
                        "pass",
                    ),
                ),
            )
            for row in cast(list[dict[str, Any]], final["trajectories"])
        )
        stages.append(
            StandardTrackGateStageV1(
                stage_key="final-selection",
                label="Legacy final trajectory selection",
                description="Tracks retained by the persisted pre-V4 final selector.",
                source_track_count=int(final["source_trajectory_count"]),
                rows=legacy_final_rows,
                truncated=int(final["truncated_trajectory_count"]) > 0,
                limitation="Legacy products do not retain excluded final-selection rows.",
            )
        )
        return tuple(stages)
    replay_gate = cast(dict[str, Any], replay["gate_config"])
    final_bank = cast(dict[str, Any], document["final_trajectory_bank"])
    final_keys = {
        (str(item["branch_id"]), int(item["alias_index"]))
        for item in cast(list[dict[str, Any]], final_bank["trajectories"])
    }
    replay_rows: list[StandardTrackGateRowV1] = []
    for row in cast(list[dict[str, Any]], replay["rows"]):
        automatic = bool(row["automatic_correction_eligible"])
        margin = row["median_block_corrected_margin"]
        cells = (
            _gate_cell(
                "observations",
                "Observations",
                int(row["observation_count"]),
                f"≥ {replay_gate['minimum_observation_count']}",
                "pass"
                if int(row["observation_count"]) >= int(replay_gate["minimum_observation_count"])
                else "fail",
            ),
            _gate_cell(
                "duration",
                "Duration",
                float(row["duration_s"]),
                f"≥ {replay_gate['minimum_duration_s']} s",
                "pass"
                if float(row["duration_s"]) >= float(replay_gate["minimum_duration_s"])
                else "fail",
            ),
            _gate_cell(
                "residual-rms",
                "Geometry RMS",
                float(row["residual_rms_hz"]),
                f"≤ {replay_gate['maximum_geometry_residual_rms_hz']} Hz",
                "pass"
                if float(row["residual_rms_hz"])
                <= float(replay_gate["maximum_geometry_residual_rms_hz"])
                else "fail",
            ),
            _gate_cell(
                "residual-max",
                "Geometry maximum",
                float(row["residual_max_hz"]),
                f"≤ {replay_gate['maximum_geometry_residual_hz']} Hz",
                "pass"
                if float(row["residual_max_hz"])
                <= float(replay_gate["maximum_geometry_residual_hz"])
                else "fail",
            ),
            _gate_cell(
                "probe-count",
                "Replay probes",
                int(row["evaluated_probe_count"]),
                f"≥ {replay_gate['minimum_probe_count']}",
                "pass"
                if int(row["evaluated_probe_count"]) >= int(replay_gate["minimum_probe_count"])
                else "fail",
            ),
            _gate_cell(
                "coverage",
                "Block coverage",
                float(row["block_coverage_ratio"]),
                f"≥ {replay_gate['minimum_block_coverage_ratio']}",
                "pass"
                if float(row["block_coverage_ratio"])
                >= float(replay_gate["minimum_block_coverage_ratio"])
                else "fail",
            ),
            _gate_cell(
                "absolute-margin",
                "Corrected margin",
                margin,
                "audit only; never vetoes V4",
                "audit",
            ),
            _gate_cell(
                "harmful-blocks",
                "Harmful blocks",
                f"{row['harmful_block_count']} (run {row['maximum_consecutive_harmful_blocks']})",
                "audit only; never vetoes V4",
                "audit",
            ),
        )
        replay_rows.append(
            StandardTrackGateRowV1(
                receiver_path_id=receiver_path_id,
                track_id=f"{row['branch_id']}:{row['alias_index']}",
                disposition="passed"
                if automatic
                else ("display_only" if bool(row["geometry_display_eligible"]) else "dropped"),
                reason="; ".join(str(reason) for reason in row["reasons"]),
                gates=cells,
            )
        )
    stages.append(
        StandardTrackGateStageV1(
            stage_key="lift-replay",
            label="Lift replay gates",
            description=(
                "Each branch/alias lift is dechirped and classified from geometry and "
                "replay support; corrected-margin metrics are audit-only."
            ),
            source_track_count=int(replay["source_lift_count"]),
            rows=tuple(replay_rows),
            truncated=int(replay["truncated_lift_count"]) > 0,
        )
    )

    replay_by_branch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cast(list[dict[str, Any]], replay["rows"]):
        replay_by_branch[str(row["branch_id"])].append(row)
    final_rows: list[StandardTrackGateRowV1] = []
    for row in cast(list[dict[str, Any]], replay["rows"]):
        key = (str(row["branch_id"]), int(row["alias_index"]))
        retained = key in final_keys
        branch_has_automatic = any(
            bool(peer["automatic_correction_eligible"])
            for peer in replay_by_branch[str(row["branch_id"])]
        )
        margin = row["median_block_corrected_margin"]
        support_ok = int(row["evaluated_probe_count"]) >= int(
            replay_gate["minimum_probe_count"]
        ) and float(row["block_coverage_ratio"]) >= float(
            replay_gate["minimum_block_coverage_ratio"]
        )
        fallback_eligible = (
            not branch_has_automatic
            and str(row["tier"]) == "geometry_only"
            and bool(row["geometry_display_eligible"])
            and support_ok
        )
        final_rows.append(
            StandardTrackGateRowV1(
                receiver_path_id=receiver_path_id,
                track_id=f"{row['branch_id']}:{row['alias_index']}",
                disposition="retained" if retained else "dropped",
                reason=(
                    "retained in the final correction/display inventory"
                    if retained
                    else "not selected by automatic-or-ranked-fallback policy"
                ),
                gates=(
                    _gate_cell(
                        "automatic",
                        "Automatic replay",
                        bool(row["automatic_correction_eligible"]),
                        "automatic replay tier",
                        "pass" if bool(row["automatic_correction_eligible"]) else "fail",
                    ),
                    _gate_cell(
                        "fallback-support",
                        "Fallback support",
                        support_ok,
                        "replay probes and coverage pass",
                        "pass" if support_ok else "fail",
                    ),
                    _gate_cell(
                        "fallback-margin",
                        "Fallback margin ranking",
                        margin,
                        "audit only; ranks eligible aliases",
                        "audit",
                    ),
                    _gate_cell(
                        "fallback-eligible",
                        "Fallback eligible",
                        fallback_eligible,
                        "geometry and replay support pass; branch has no automatic lift",
                        "pass"
                        if fallback_eligible
                        else "not_applicable"
                        if branch_has_automatic
                        else "fail",
                    ),
                    _gate_cell(
                        "final-retention",
                        "Final retention",
                        retained,
                        "branch policy followed by the persisted global-cap decision",
                        "pass" if retained else "fail",
                    ),
                ),
            )
        )
    stages.append(
        StandardTrackGateStageV1(
            stage_key="final-selection",
            label="Final trajectory selection",
            description=(
                "Automatic replay passes are retained; otherwise at most one "
                "geometry-qualified fallback is ranked per branch before "
                "the global cap."
            ),
            source_track_count=int(replay["source_lift_count"]),
            rows=tuple(final_rows),
            truncated=(
                int(replay["truncated_lift_count"]) > 0
                or int(final_bank["truncated_trajectory_count"]) > 0
            ),
        )
    )
    return tuple(stages)


@dataclass(frozen=True, slots=True)
class _PathSource:
    product: CatalogProductRecord
    binding: StandardPathInputBindV3
    document: dict[str, Any]
    reference: StandardReceiverPathRefV2


@dataclass(frozen=True, slots=True)
class _Projection:
    snapshot: CatalogSessionReadSnapshot
    run_id: str
    manifest_digest: str
    release: StandardPipelineReleaseV2
    paths: tuple[_PathSource, ...]
    jobs: tuple[CatalogJobRecord, ...]
    products: tuple[CatalogProductRecord, ...]
    hierarchy: StandardSubjectHierarchyV2
    subjects: dict[str, StandardSubjectSummaryV2]


class CatalogStandardPresentationRepository:
    """Read sealed Standard products without consulting IQ or fixture data."""

    def __init__(
        self,
        catalog: CatalogRepository,
        artifacts: AnalysisArtifactStore,
        *,
        pipeline_lane: PipelineLane = PipelineLane.STANDARD,
    ) -> None:
        self._catalog = catalog
        self._artifacts = artifacts
        self._pipeline_lane = pipeline_lane
        self._subject_collection = (
            "standard-subjects" if pipeline_lane is PipelineLane.STANDARD else "research-subjects"
        )

    def _kind(self, standard_kind: str) -> str:
        return (
            standard_kind
            if self._pipeline_lane is PipelineLane.STANDARD
            else research_product_kind(standard_kind)
        )

    def _presentation_snapshot(self, session_id: str) -> CatalogSessionReadSnapshot | None:
        if self._pipeline_lane is PipelineLane.STANDARD:
            return self._catalog.presentation_snapshot(session_id)
        return self._catalog.presentation_snapshot(session_id, self._pipeline_lane)

    def subject_hierarchy(self, session_id: str) -> StandardSubjectHierarchyV2 | None:
        loaded = self._load(session_id)
        return None if loaded is None else loaded.hierarchy

    def subject_detail(self, session_id: str, subject_id: str) -> StandardSubjectDetailV2 | None:
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        subject = loaded.subjects[subject_id]
        selected = self._subject_paths(loaded, subject)
        domain = _time_domain(selected)
        trajectories = _trajectory_rows(selected)
        alternate_tracks = self._alternate_tracks(loaded, selected)
        stages = _stage_rows(loaded, subject, selected)
        views = tuple(
            StandardViewDescriptorV2(
                view_kind=kind,
                state=StandardViewStateV2.AVAILABLE,
                href=(
                    f"/api/v2/recordings/{session_id}/{self._subject_collection}/"
                    f"{subject_id}/views/{kind.value}"
                ),
                source_point_count=_source_count(selected, kind),
                reason="Bounded registered presentation is available",
            )
            for kind in StandardViewKindV2
        )
        path_subjects = tuple(loaded.subjects[path.reference.subject_id] for path in selected)
        return StandardSubjectDetailV2(
            subject=subject,
            time_domain=domain,
            receiver_path_expansions=path_subjects,
            receiver_path_evidence=tuple(_path_evidence(path) for path in selected),
            stage_source_count=len(stages),
            stages=stages,
            stages_truncated=False,
            trajectory_source_count=len(trajectories),
            trajectories=trajectories[:256],
            trajectories_truncated=len(trajectories) > 256,
            alternate_track_source_count=len(alternate_tracks),
            alternate_tracks=alternate_tracks[:64],
            alternate_tracks_truncated=len(alternate_tracks) > 64,
            views=views,
            limitations=(
                "Candidate evidence only; source identity is unassessed; "
                "no payload recovery is claimed",
                "Cross-radio evidence is score/trajectory-level and is not phase coherent",
            ),
        )

    def subject_replay_audit(
        self, session_id: str, subject_id: str
    ) -> StandardReplayAuditV1 | None:
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        selected = self._subject_paths(loaded, loaded.subjects[subject_id])
        rows: list[StandardReplayAuditRowV1] = []
        for path in selected:
            final_keys = {
                (item["branch_id"], int(item["alias_index"]))
                for item in path.document["final_trajectory_table"]["trajectories"]
            }
            for item in path.document["cfo_lift_replay"]["rows"]:
                rows.append(
                    StandardReplayAuditRowV1(
                        receiver_path_id=path.reference.path_id,
                        branch_id=item["branch_id"],
                        alias_index=item["alias_index"],
                        tier=item["tier"],
                        automatic_correction_eligible=item["automatic_correction_eligible"],
                        geometry_display_eligible=item["geometry_display_eligible"],
                        evaluated_probe_count=item["evaluated_probe_count"],
                        evaluated_block_count=item["evaluated_block_count"],
                        block_coverage_ratio=item["block_coverage_ratio"],
                        median_block_corrected_margin=item["median_block_corrected_margin"],
                        harmful_block_count=item["harmful_block_count"],
                        maximum_consecutive_harmful_blocks=item[
                            "maximum_consecutive_harmful_blocks"
                        ],
                        reasons=tuple(item["reasons"]),
                        retained_in_final=(item["branch_id"], int(item["alias_index"]))
                        in final_keys,
                    )
                )
        ordered = sorted(
            rows, key=lambda row: (row.receiver_path_id, row.branch_id, row.alias_index)
        )
        return StandardReplayAuditV1(
            session_id=session_id,
            subject_id=subject_id,
            source_row_count=len(ordered),
            rows=tuple(ordered[:1280]),
            truncated=len(ordered) > 1280,
        )

    def subject_track_gate_audit(
        self, session_id: str, subject_id: str
    ) -> StandardTrackGateAuditV1 | None:
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        selected = self._subject_paths(loaded, loaded.subjects[subject_id])
        by_stage: dict[str, list[StandardTrackGateStageV1]] = defaultdict(list)
        for path in selected:
            for stage in _track_gate_stages(path.reference.path_id, path.document):
                by_stage[stage.stage_key].append(stage)
        stages: list[StandardTrackGateStageV1] = []
        for stage_key in _TRACK_GATE_STAGE_ORDER:
            parts = by_stage.get(stage_key, [])
            if not parts:
                continue
            rows = tuple(row for part in parts for row in part.rows)
            stages.append(
                StandardTrackGateStageV1(
                    stage_key=stage_key,
                    label=parts[0].label,
                    description=parts[0].description,
                    source_track_count=sum(part.source_track_count for part in parts),
                    rows=rows[:1280],
                    truncated=any(part.truncated for part in parts) or len(rows) > 1280,
                    limitation=parts[0].limitation,
                )
            )
        return StandardTrackGateAuditV1(
            session_id=session_id,
            subject_id=subject_id,
            stages=tuple(stages),
        )

    def subject_view(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        maximum_points: int,
    ) -> StandardPlotViewV2 | None:
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        subject = loaded.subjects[subject_id]
        return _build_view(
            loaded,
            subject,
            self._subject_paths(loaded, subject),
            view_kind,
            maximum_points=maximum_points,
        )

    def subject_png_artifact(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
    ) -> bytes | None:
        """Return the run-registered PNG without invoking a renderer."""

        standard_kind = {
            StandardViewKindV2.WATERFALL: WATERFALL_PNG_PRODUCT.kind,
            StandardViewKindV2.GLRT64: PILOT_METHODS_PNG_PRODUCT.kind,
            StandardViewKindV2.CFO_TRAJECTORY: CFO_TRAJECTORIES_PNG_PRODUCT.kind,
        }.get(view_kind)
        if standard_kind is None:
            return None
        return self._subject_png_artifact(session_id, subject_id, self._kind(standard_kind))

    def subject_named_png_artifact(
        self,
        session_id: str,
        subject_id: str,
        artifact_name: str,
    ) -> bytes | None:
        """Return one immutable trajectory-stage PNG by its closed public name."""

        product = {
            "cfo-raw": CFO_TRAJECTORIES_PNG_PRODUCT,
            "cfo-dealiased": DEALIASED_CFO_TRAJECTORIES_PNG_PRODUCT,
            "cfo-final": FINAL_CFO_TRAJECTORIES_PNG_PRODUCT,
            "cfo-alternate": ALTERNATE_CFO_TRACKS_PNG_PRODUCT,
            "trajectory-accounting": TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_PRODUCT,
        }.get(artifact_name)
        if product is None:
            return None
        artifact = self._subject_png_artifact(
            session_id,
            subject_id,
            self._kind(product.kind),
            schema_version=product.schema_version,
        )
        if artifact is not None or artifact_name != "trajectory-accounting":
            return artifact
        return self._subject_png_artifact(
            session_id,
            subject_id,
            self._kind(TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_V1_PRODUCT.kind),
            schema_version=TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_V1_PRODUCT.schema_version,
        )

    def _alternate_tracks(
        self, loaded: _Projection, selected: tuple[_PathSource, ...]
    ) -> tuple[StandardAlternateCfoTrackRowV2, ...]:
        if self._pipeline_lane is not PipelineLane.STANDARD:
            return ()
        rows: list[StandardAlternateCfoTrackRowV2] = []
        for path in selected:
            matches = tuple(
                product
                for product in loaded.products
                if product.kind == ALTERNATE_CFO_TRACK_BANK_PRODUCT.kind
                and product.schema_version == ALTERNATE_CFO_TRACK_BANK_PRODUCT.schema_version
                and product.role == "scientific"
                and product.available
                and product.scope == path.reference.scope
            )
            if not matches:
                continue
            if len(matches) != 1:
                raise StandardPresentationUnavailable(
                    "sealed run duplicates an alternate CFO track product"
                )
            raw = self._artifacts.read_json(matches[0].logical_uri, matches[0].digest)
            document = decode_standard_product(ALTERNATE_CFO_TRACK_BANK_PRODUCT, raw)
            rows.extend(
                _alternate_track_row(path.reference.path_id, track) for track in document["tracks"]
            )
        return tuple(sorted(rows, key=lambda row: (row.receiver_path_id, row.track_id)))

    def _subject_png_artifact(
        self,
        session_id: str,
        subject_id: str,
        kind: str,
        *,
        schema_version: int = 1,
    ) -> bytes | None:
        loaded = self._load(session_id, include_documents=False)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        subject = loaded.subjects[subject_id]
        matches = tuple(
            product
            for product in loaded.products
            if product.kind == kind
            and product.schema_version == schema_version
            and product.media_type == "image/png"
            and product.role == "presentation"
            and product.available
            and product.scope is not None
            and _png_scope_matches(subject, product.scope)
        )
        if not matches:
            return None
        if len(matches) != 1:
            raise StandardPresentationUnavailable(
                "sealed Standard run lacks one exact registered PNG for the subject"
            )
        product = matches[0]
        return self._artifacts.read_bytes(product.logical_uri, product.digest)

    def verify_source_extrema(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        proof: StandardSourceExtremaProofV2,
    ) -> bool:
        loaded = self._load(session_id, include_documents=False)
        if loaded is None or subject_id not in loaded.subjects:
            return False
        subject = loaded.subjects[subject_id]
        selected = self._subject_paths(loaded, subject)
        expected_content = _digest(
            canonical_digest(
                {
                    "view_kind": view_kind.value,
                    "products": [item.product.digest for item in selected],
                }
            )
        )
        return (
            proof.source_artifact_digest == loaded.manifest_digest
            and proof.source_content_digest == expected_content
        )

    @staticmethod
    def _subject_paths(
        loaded: _Projection, subject: StandardSubjectSummaryV2
    ) -> tuple[_PathSource, ...]:
        wanted = {item.path_id for item in subject.receiver_paths}
        return tuple(item for item in loaded.paths if item.reference.path_id in wanted)

    def _load(self, session_id: str, *, include_documents: bool = True) -> _Projection | None:
        try:
            snapshot = self._presentation_snapshot(session_id)
            if snapshot is None or snapshot.analysis is None:
                return None
            analysis = snapshot.analysis
            source_type = StandardSourceTypeV2(snapshot.source_type.upper())
            if analysis.state in {"queued", "pending", "running"}:
                lane_label = (
                    "Standard" if self._pipeline_lane is PipelineLane.STANDARD else "Research"
                )
                raise StandardPresentationNotReady(
                    f"{lane_label} analysis is still processing; "
                    "no sealed image artifacts are available yet"
                )
            if analysis.state != "succeeded":
                raise StandardPresentationUnavailable("Standard analysis run did not succeed")
            if source_type is StandardSourceTypeV2.TEST:
                if analysis.promotion_policy != "evidence_only" or analysis.is_current:
                    raise StandardPresentationUnavailable(
                        "TEST Standard evidence must be sealed evidence-only and non-current"
                    )
            elif not analysis.is_current or analysis.promotion_policy != "current":
                raise StandardPresentationUnavailable(
                    "ordinary Standard presentation requires the exact current run"
                )
            if (
                analysis.sealed_at is None
                or analysis.manifest_uri is None
                or analysis.manifest_digest is None
            ):
                raise StandardPresentationUnavailable("Standard analysis run is not sealed")
            reference = self._catalog.run_manifest_reference(analysis.run_id)
            if (
                reference.logical_uri != analysis.manifest_uri
                or reference.digest != analysis.manifest_digest
            ):
                raise StandardPresentationUnavailable("catalog run-manifest authority drifted")
            manifest = parse_analysis_run_manifest(
                self._artifacts.read_json(reference.logical_uri, reference.digest)
            )
            if isinstance(manifest, AnalysisRunManifestV2):
                if manifest.pipeline_lane != self._pipeline_lane.value:
                    raise StandardPresentationUnavailable(
                        "sealed manifest belongs to another pipeline lane"
                    )
            elif self._pipeline_lane is not PipelineLane.STANDARD:
                raise StandardPresentationUnavailable(
                    "Research presentation requires an explicit lane manifest"
                )
            execution = self._catalog.run_execution_info(analysis.run_id)
            seal = self._catalog.run_seal_snapshot(analysis.run_id)
            if (
                manifest.run_id != analysis.run_id
                or manifest.session_id != session_id
                or manifest.pipeline_release_id != analysis.pipeline_release_id
                or manifest.input_manifest_digest != analysis.input_manifest_digest
                or execution.session_id != session_id
                or execution.pipeline_lane != self._pipeline_lane.value
            ):
                raise StandardPresentationUnavailable("sealed Standard manifest identity drifted")
            manifest_products = {
                (
                    item.product_id,
                    item.stage_key,
                    item.scope_key,
                    item.kind,
                    item.product_schema_version,
                    item.role,
                    item.status,
                    item.media_type,
                    item.logical_uri,
                    item.digest,
                    item.byte_size,
                    item.coverage,
                )
                for item in manifest.products
            }
            catalog_products = {
                (
                    item.product_id,
                    item.stage_key,
                    item.scope_key,
                    item.kind,
                    item.schema_version,
                    item.role,
                    item.status,
                    item.media_type,
                    item.logical_uri,
                    item.digest,
                    item.byte_size,
                    item.coverage,
                )
                for item in seal.products
            }
            if manifest_products != catalog_products:
                raise StandardPresentationUnavailable(
                    "sealed Standard manifest product inventory drifted"
                )
            manifest_jobs = {
                (item.job_id, item.stage_key, item.scope_key, item.outcome)
                for item in manifest.jobs
            }
            catalog_jobs = {
                (item.job_id, item.stage_key, item.scope_key, item.outcome) for item in seal.jobs
            }
            if manifest_jobs != catalog_jobs:
                raise StandardPresentationUnavailable(
                    "sealed Standard manifest job inventory drifted"
                )
            if (
                not execution.code_revision
                or execution.code_revision != analysis.pipeline_release_id
            ):
                raise StandardPresentationUnavailable(
                    "Standard release is not exact source authority"
                )
            release = StandardPipelineReleaseV2(
                authoritative_pipeline_release_id=execution.pipeline_release_id,
                source_revision=execution.code_revision,
                display_version=str(
                    execution.pipeline_configuration.get("display_version", "2.0.0")
                ),
                graph_digest=_digest(execution.graph_digest),
                configuration_digest=_digest(execution.configuration_digest),
                environment_digest=_digest(execution.environment_digest),
            )
            research_definition_id = None
            if self._pipeline_lane is PipelineLane.RESEARCH:
                raw_definition_id = execution.pipeline_configuration.get("research_definition_id")
                if not isinstance(raw_definition_id, str):
                    raise StandardPresentationUnavailable(
                        "Research release lacks its exact pipeline definition"
                    )
                _digest(raw_definition_id)
                research_definition_id = raw_definition_id
            candidates = tuple(
                item
                for item in seal.products
                if item.kind == self._kind(PATH_PRESENTATION_PRODUCT.kind)
                and item.schema_version
                == (
                    PATH_PRESENTATION_PRODUCT.schema_version
                    if self._pipeline_lane is PipelineLane.STANDARD
                    else 1
                )
                and item.role == "presentation"
                and item.available
            )
            if not candidates:
                raise StandardPresentationUnavailable(
                    "sealed run has no Standard path presentation products"
                )
            if any(job.state != "succeeded" for job in seal.jobs):
                raise StandardPresentationUnavailable(
                    "sealed Standard run contains a nonterminal job"
                )
            paths = tuple(
                self._load_path(
                    analysis.run_id,
                    item,
                    include_document=include_documents,
                    research_definition_id=research_definition_id,
                )
                for item in candidates
            )
            paths = tuple(
                sorted(
                    paths,
                    key=lambda item: (
                        item.binding.stream_id,
                        item.binding.receiver_id,
                    ),
                )
            )
            if len(paths) != len({item.reference.scope_digest for item in paths}) or len(paths) > 4:
                raise StandardPresentationUnavailable(
                    "Standard path presentation inventory is duplicated or unbounded"
                )
            streams = {item.binding.stream_id for item in paths}
            radio_products = tuple(
                item
                for item in seal.products
                if item.kind == self._kind("standard.radio-report")
                and item.schema_version
                == (2 if self._pipeline_lane is PipelineLane.STANDARD else 1)
                and item.available
                and item.scope is not None
                and item.scope.kind is ScopeKind.RADIO
            )
            paired_products = tuple(
                item
                for item in seal.products
                if item.kind == self._kind("standard.paired-report")
                and item.schema_version
                == (2 if self._pipeline_lane is PipelineLane.STANDARD else 1)
                and item.available
                and item.scope is not None
                and item.scope.kind is ScopeKind.PAIRED
            )
            if {
                item.scope.stream_id for item in radio_products if item.scope is not None
            } != streams:
                raise StandardPresentationUnavailable(
                    "sealed Standard run lacks exact radio reducers"
                )
            if (len(streams) == 2 and len(paired_products) != 1) or (
                len(streams) == 1 and paired_products
            ):
                raise StandardPresentationUnavailable(
                    "sealed Standard run lacks the exact paired reducer inventory"
                )
            paths = _normalize_path_labels(paths)
            hierarchy, subjects = _hierarchy(snapshot, analysis.sealed_at, release, paths)
            return _Projection(
                snapshot=snapshot,
                run_id=analysis.run_id,
                manifest_digest=_digest(analysis.manifest_digest),
                release=release,
                paths=paths,
                jobs=seal.jobs,
                products=seal.products,
                hierarchy=hierarchy,
                subjects=subjects,
            )
        except (StandardPresentationNotReady, StandardPresentationUnavailable):
            raise
        except Exception as error:
            raise StandardPresentationUnavailable(
                "Standard presentation authority or artifact is unavailable"
            ) from error

    def _load_path(
        self,
        run_id: str,
        product: CatalogProductRecord,
        *,
        include_document: bool,
        research_definition_id: str | None,
    ) -> _PathSource:
        scope = product.scope
        if scope is None or scope.kind is not ScopeKind.RECEIVER_PATH:
            raise StandardPresentationUnavailable("path presentation lacks typed path scope")
        binding = StandardPathInputBindV3.model_validate(
            self._catalog.run_subject_binding(run_id, scope).document
        )
        document: dict[str, Any]
        if include_document:
            raw_document = self._artifacts.read_json(product.logical_uri, product.digest)
            if self._pipeline_lane is PipelineLane.RESEARCH:
                envelope = ResearchProductEnvelopeV1.model_validate(raw_document)
                if (
                    envelope.pipeline_definition_id != research_definition_id
                    or envelope.payload_kind != PATH_PRESENTATION_PRODUCT.kind
                    or envelope.payload_schema_version != PATH_PRESENTATION_PRODUCT.schema_version
                ):
                    raise StandardPresentationUnavailable(
                        "Research path presentation envelope disagrees with its payload"
                    )
                raw_document = cast(dict[str, Any], envelope.payload)
            document = decode_standard_product(PATH_PRESENTATION_PRODUCT, raw_document)
        else:
            document = {}
        if (
            binding.session_id != scope.session_id
            or binding.stream_id != scope.stream_id
            or binding.receiver_id != scope.receiver_id
        ):
            raise StandardPresentationUnavailable("path presentation source binding drifted")
        if include_document and (
            document["sample_rate_hz"] != binding.sample_rate_hz
            or document["declared_sample_count"] != binding.declared_sample_count
        ):
            raise StandardPresentationUnavailable("path presentation source binding drifted")
        path_id = f"{binding.radio_id}:rx{binding.receiver_id}"
        return _PathSource(
            product=product,
            binding=binding,
            document=document,
            reference=StandardReceiverPathRefV2(
                subject_id=f"path:{path_id}",
                path_id=path_id,
                radio_id=binding.radio_id,
                radio_label="Radio0",  # replaced by the canonical hierarchy label
                receiver_id=binding.receiver_id,
                receiver_label=f"RX{binding.receiver_id}",
                scope=scope,
                scope_digest=_digest(scope.canonical_digest),
            ),
        )


def _alternate_track_row(
    receiver_path_id: str, track_document: dict[str, Any]
) -> StandardAlternateCfoTrackRowV2:
    """Project the persisted track explicitly, excluding its contract envelope version."""

    track = (
        AlternateCfoTrackV2.model_validate(track_document)
        if track_document.get("schema_version") == 2
        else AlternateCfoTrackV1.model_validate(track_document)
    )
    return StandardAlternateCfoTrackRowV2(
        receiver_path_id=receiver_path_id,
        track_id=track.track_id,
        start_s=track.start_s,
        end_s=track.end_s,
        span_s=track.span_s,
        support_count=track.support_count,
        weighted_support=track.weighted_support,
        slope_hz_per_s=track.slope_hz_per_s,
        acceleration_hz_per_s2=track.acceleration_hz_per_s2,
        intercept_mod_alias_hz=track.intercept_mod_alias_hz,
        residual_rms_hz=track.residual_rms_hz,
        residual_max_hz=track.residual_max_hz,
        maximum_gap_s=track.maximum_gap_s,
        confidence=track.confidence,
        status=track.status,
    )


def _hierarchy(
    snapshot: CatalogSessionReadSnapshot,
    generated_at: datetime,
    release: StandardPipelineReleaseV2,
    sources: tuple[_PathSource, ...],
) -> tuple[StandardSubjectHierarchyV2, dict[str, StandardSubjectSummaryV2]]:
    source_type = StandardSourceTypeV2(snapshot.source_type.upper())
    eligibility = standard_eligibility_v2(
        source_type,
        snapshot.tags,
        capture_committed=snapshot.state == "committed",
        capture_healthy=snapshot.state == "committed",
    )
    streams = tuple(sorted({item.binding.stream_id for item in sources}))
    if not 1 <= len(streams) <= 2:
        raise StandardPresentationUnavailable("Standard hierarchy requires one or two radios")
    radio_labels = {stream: f"Radio{index}" for index, stream in enumerate(streams)}
    state = (
        StandardSubjectStateV2.COMPLETE
        if eligibility.evidence_only
        else StandardSubjectStateV2.CURRENT
    )

    def subject(
        subject_id: str,
        kind: StandardSubjectKindV2,
        label: str,
        paths: tuple[StandardReceiverPathRefV2, ...],
        children: tuple[str, ...],
    ) -> StandardSubjectSummaryV2:
        return StandardSubjectSummaryV2(
            subject_id=subject_id,
            session_id=snapshot.session_id,
            subject_kind=kind,
            label=label,
            derived=kind is not StandardSubjectKindV2.RECEIVER_PATH,
            receiver_paths=paths,
            expected_path_count=len(paths),
            completed_path_count=len(paths),
            child_subject_ids=children,
            state=state,
            ordinary_current=not eligibility.evidence_only,
            state_reasons=(),
            pipeline_release=release,
            desired_pipeline_release_id=release.authoritative_pipeline_release_id,
            reuse=StandardReuseSummaryV2(
                computed_stage_count=1,
                reused_stage_count=0,
                recompute_stage_count=0,
                reason="Rendered for this run",
            ),
            eligibility=eligibility,
        )

    path_subjects = tuple(
        subject(
            item.reference.subject_id,
            StandardSubjectKindV2.RECEIVER_PATH,
            f"{item.reference.radio_label} {item.reference.receiver_label}",
            (item.reference,),
            (),
        )
        for item in sources
    )
    radios = tuple(
        subject(
            f"radio:{stream}",
            StandardSubjectKindV2.RADIO,
            radio_labels[stream],
            tuple(item.reference for item in sources if item.binding.stream_id == stream),
            tuple(
                item.reference.subject_id for item in sources if item.binding.stream_id == stream
            ),
        )
        for stream in streams
    )
    rows: tuple[StandardSubjectSummaryV2, ...]
    all_subjects = (*path_subjects, *radios)
    if len(radios) == 2:
        pair = subject(
            f"pair:{streams[0]}:{streams[1]}",
            StandardSubjectKindV2.PAIRED,
            "Paired Radio0 + Radio1",
            tuple(path for radio in radios for path in radio.receiver_paths),
            tuple(radio.subject_id for radio in radios),
        )
        rows = (pair, *radios)
        all_subjects = (*all_subjects, pair)
    else:
        rows = radios
    hierarchy = StandardSubjectHierarchyV2(
        session_id=snapshot.session_id,
        source_type=source_type,
        eligibility=eligibility,
        generated_at=generated_at,
        rows=rows,
    )
    return hierarchy, {item.subject_id: item for item in all_subjects}


def _normalize_path_labels(sources: tuple[_PathSource, ...]) -> tuple[_PathSource, ...]:
    streams = tuple(sorted({item.binding.stream_id for item in sources}))
    labels = {stream: f"Radio{index}" for index, stream in enumerate(streams)}
    return tuple(
        _PathSource(
            product=item.product,
            binding=item.binding,
            document=item.document,
            reference=item.reference.model_copy(
                update={"radio_label": labels[item.binding.stream_id]}
            ),
        )
        for item in sources
    )


def _time_domain(paths: tuple[_PathSource, ...]) -> StandardTimeDomainV2:
    first = min(item.binding.timing.first_estimate_utc_ns for item in paths)
    last = max(item.binding.timing.last_estimate_utc_ns for item in paths)
    uncertainty_ns = max(
        max(
            item.binding.timing.first_estimate_utc_ns - item.binding.timing.first_earliest_utc_ns,
            item.binding.timing.first_latest_utc_ns - item.binding.timing.first_estimate_utc_ns,
            item.binding.timing.last_estimate_utc_ns - item.binding.timing.last_earliest_utc_ns,
            item.binding.timing.last_latest_utc_ns - item.binding.timing.last_estimate_utc_ns,
        )
        for item in paths
    )
    duration = (last - first) / 1_000_000_000
    return StandardTimeDomainV2(
        absolute_start_utc=datetime.fromtimestamp(first / 1_000_000_000, UTC),
        absolute_end_utc=datetime.fromtimestamp(last / 1_000_000_000, UTC),
        elapsed_end_s=duration,
        # Python datetimes retain microseconds while receiver timing is in
        # nanoseconds.  Account for that representation boundary explicitly.
        timing_uncertainty_s=uncertainty_ns / 1_000_000_000 + 1e-6,
    )


def _path_evidence(path: _PathSource) -> StandardPathEvidenceV2:
    timeline = path.document["power_timeline"]
    declared = path.binding.declared_sample_count / path.binding.sample_rate_hz
    analyzed = timeline["observed_sample_count"] / path.binding.sample_rate_hz
    frequency = path.binding.frequency_reference
    applicable = frequency.reference.value == "calibrated"
    return StandardPathEvidenceV2(
        receiver_path=path.reference,
        coverage_fraction=min(1.0, analyzed / declared),
        analyzed_seconds=analyzed,
        declared_seconds=declared,
        quality_state="complete" if analyzed == declared else "partial",
        clipped_fraction=None,
        continuity_gap_count=int(timeline["uncovered_region_count"]),
        calibration_state="applicable" if applicable else "unavailable",
        calibration_id=(
            f"calibration:{_digest(frequency.calibration_digest)}" if applicable else None
        ),
        calibration_digest=_digest(frequency.calibration_digest) if applicable else None,
        frequency_uncertainty_hz=frequency.uncertainty_hz if applicable else None,
        reason=(
            "Full path coverage with capture-epoch calibration"
            if applicable and analyzed == declared
            else "Candidate analysis state projected exactly"
        ),
    )


def _stage_rows(
    loaded: _Projection,
    subject: StandardSubjectSummaryV2,
    paths: tuple[_PathSource, ...],
) -> tuple[StandardStageStatusV2, ...]:
    scopes = {item.reference.scope.canonical_digest for item in paths}
    rows = []
    path_products = {item.product.scope_key: item.product for item in paths}
    for job in loaded.jobs:
        if job.scope is None:
            continue
        if job.scope.kind is ScopeKind.RECEIVER_PATH:
            if job.scope.canonical_digest not in scopes:
                continue
        elif job.scope.kind is ScopeKind.RADIO:
            if subject.subject_kind is StandardSubjectKindV2.RECEIVER_PATH or (
                subject.subject_kind is StandardSubjectKindV2.RADIO
                and job.scope.stream_id not in {item.binding.stream_id for item in paths}
            ):
                continue
        elif subject.subject_kind is not StandardSubjectKindV2.PAIRED:
            continue
        digest = path_products.get(job.scope_key)
        rows.append(
            StandardStageStatusV2(
                stage_key=job.stage_key,
                subject_id=subject.subject_id,
                disposition=StandardComputationDispositionV2.COMPUTED,
                output_digest=None if digest is None else _digest(digest.digest),
                reason="Rendered for this run",
            )
        )
    return tuple(rows[:256])


def _trajectory_rows(paths: tuple[_PathSource, ...]) -> tuple[StandardTrajectoryRowV2, ...]:
    rows = []
    for path in paths:
        offset_s = _path_time_offset_s(path, paths)
        canonical_models: dict[str, dict[str, Any]] = {}
        for branch in path.document["dealiased_trajectory_bank"]["branches"]:
            models = branch.get("models")
            if models is None and "model" in branch:
                models = [branch["model"]]
            for model in models or []:
                canonical_models[model["model_id"]] = model
        for item in path.document["final_trajectory_table"]["trajectories"]:
            model = canonical_models[item["canonical_model_id"]]
            is_v2 = int(item.get("schema_version", 1)) >= 2
            automatic = bool(item.get("automatic_correction_eligible", True))
            replay_tier = str(item.get("replay_tier", "supported"))
            alias_index = int(item["alias_index"])
            lift_label = (
                f"p{alias_index}"
                if alias_index > 0
                else f"m{abs(alias_index)}"
                if alias_index < 0
                else "z0"
            )
            rows.append(
                StandardTrajectoryRowV2(
                    trajectory_id=item["trajectory_id"],
                    receiver_path_id=path.reference.path_id,
                    algorithm=(
                        f"glrt64-final-lift-{lift_label}-{replay_tier}"
                        if is_v2
                        else f"glrt64-final-lift-{lift_label}"
                    ),
                    degree=item["polynomial_degree"],
                    reference_time_s=item["reference_time_s"] + offset_s,
                    coefficients_hz=tuple(item["absolute_coefficients_hz"]),
                    support_count=len(item["observation_ids"]),
                    residual_rms_hz=model["residual_rms_hz"],
                    bic=model["bic"],
                    selected_for_correction=automatic,
                    corrected_glrt64_gain=item.get(
                        "median_block_margin_delta" if is_v2 else "median_margin_delta"
                    ),
                    status="selected" if automatic else "retained",
                )
            )
    return tuple(rows)


def _build_view(
    loaded: _Projection,
    subject: StandardSubjectSummaryV2,
    paths: tuple[_PathSource, ...],
    kind: StandardViewKindV2,
    *,
    maximum_points: int,
) -> StandardPlotViewV2:
    if maximum_points < len(paths) or maximum_points > 2048:
        raise ValueError("maximum_points must cover every receiver path and be at most 2,048")
    if kind is StandardViewKindV2.WATERFALL:
        return _waterfall_view(loaded, subject, paths, maximum_points)
    if kind is StandardViewKindV2.CFO_TRAJECTORY:
        return _cfo_view(loaded, subject, paths, maximum_points)
    return _metric_view(loaded, subject, paths, kind, maximum_points)


def _source_count(paths: tuple[_PathSource, ...], kind: StandardViewKindV2) -> int:
    count = 0
    for path in paths:
        document = path.document
        detections = document["pilot_scan"]["detections"]
        if kind in {StandardViewKindV2.QUALITY, StandardViewKindV2.POWER}:
            count += len(document["power_timeline"]["timeline"])
        elif kind is StandardViewKindV2.WATERFALL:
            waterfall = document["waterfall"]
            count += len(waterfall["tiles"]) * len(waterfall["frequency_bin_centers_hz"])
        elif kind is StandardViewKindV2.QAM:
            count += 2 * len(detections)
        elif kind is StandardViewKindV2.GLRT64:
            count += sum(
                any(score["method"] == "glrt64" for score in item["scores"]) for item in detections
            )
            count += len(document["trajectory_feedback"]["results"])
        else:
            count += sum(
                any(score["method"] == "glrt64" for score in item["scores"]) for item in detections
            )
            count += 17 * len(document["final_trajectory_table"]["trajectories"])
    return count


def _metric_view(
    loaded: _Projection,
    subject: StandardSubjectSummaryV2,
    paths: tuple[_PathSource, ...],
    kind: StandardViewKindV2,
    maximum_points: int,
) -> StandardPlotViewV2:
    entries: list[tuple[str, str, str, StandardUnitV2, float, float]] = []
    for path in paths:
        lane = path.reference.path_id
        document = path.document
        offset_s = _path_time_offset_s(path, paths)
        if kind is StandardViewKindV2.POWER:
            for item in document["power_timeline"]["timeline"]:
                entries.append(
                    (
                        lane,
                        "window",
                        "Window power",
                        "dBFS",
                        offset_s + (item["time_start_s"] + item["time_stop_s"]) / 2,
                        item["mean_power_dbfs"],
                    )
                )
        elif kind is StandardViewKindV2.QUALITY:
            for item in document["power_timeline"]["timeline"]:
                fraction = item["observed_sample_count"] / max(
                    1, item["sample_stop"] - item["sample_start"]
                )
                entries.append(
                    (
                        lane,
                        "valid",
                        "Valid sample fraction",
                        "fraction",
                        offset_s + item["time_start_s"],
                        fraction,
                    )
                )
        elif kind is StandardViewKindV2.QAM:
            for item in document["pilot_scan"]["detections"]:
                time_s = offset_s + item["time_s"]
                if item["qam_accuracy"] is not None:
                    entries.append(
                        (
                            lane,
                            "accuracy",
                            "Known-pilot QAM accuracy",
                            "accuracy",
                            time_s,
                            item["qam_accuracy"],
                        )
                    )
                margin = next(
                    (
                        score["margin"]
                        for score in item["scores"]
                        if score["method"] == "symbolwise"
                    ),
                    None,
                )
                if margin is not None:
                    entries.append(
                        (
                            lane,
                            "pilot-margin",
                            "Pilot verify minus control margin",
                            "response",
                            time_s,
                            margin,
                        )
                    )
        else:
            for item in document["pilot_scan"]["detections"]:
                score = next(
                    (score for score in item["scores"] if score["method"] == "glrt64"), None
                )
                if score is not None:
                    entries.append(
                        (
                            lane,
                            "initial",
                            "Initial GLRT64 detector response",
                            "response",
                            offset_s + item["time_s"],
                            score["exact_score"],
                        )
                    )
            for item in document["trajectory_feedback"]["results"]:
                entries.append(
                    (
                        lane,
                        "corrected",
                        "Trajectory-corrected GLRT64 candidate redetection response",
                        "response",
                        offset_s + item["time_s"],
                        item["corrected_margin"],
                    )
                )
    selected = _select_by_lane(entries, maximum_points, lambda item: item[0])
    if {item[0] for item in selected} != {path.reference.path_id for path in paths}:
        raise StandardPresentationUnavailable(f"{kind.value} has no evidence for every path")
    groups: dict[tuple[str, str, str, StandardUnitV2], list[tuple[float, float]]] = defaultdict(
        list
    )
    full_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for lane, metric, _label, _unit, _time_s, value in entries:
        full_groups[(lane, metric)].append(value)
    for lane, metric, label, unit, time_s, value in selected:
        groups[(lane, metric, label, unit)].append((time_s, value))
    series = tuple(
        StandardMetricSeriesV2(
            series_id=f"{kind.value}:{metric}:{lane}",
            receiver_path_id=lane,
            label=label,
            unit=unit,
            source_point_count=len(full_groups[(lane, metric)]),
            points=tuple(
                StandardSeriesPointV2(time_s=time_s, value=value) for time_s, value in values
            ),
            truncated=len(full_groups[(lane, metric)]) > len(values),
            source_min=min(full_groups[(lane, metric)]),
            source_max=max(full_groups[(lane, metric)]),
        )
        for (lane, metric, label, unit), values in groups.items()
    )
    lanes = tuple(
        _lane_extrema(
            path.reference.path_id,
            ("metric_value",),
            [item[5] for item in entries if item[0] == path.reference.path_id],
        )
        for path in paths
    )
    proof = _proof(loaded, paths, kind, lanes)
    returned = sum(len(item.points) for item in series)
    values = [item[5] for item in entries]
    return StandardPlotViewV2(
        session_id=loaded.snapshot.session_id,
        subject_id=subject.subject_id,
        view_kind=kind,
        state=StandardViewStateV2.AVAILABLE,
        time_domain=_time_domain(paths),
        receiver_path_ids=tuple(path.reference.path_id for path in paths),
        horizontal_axis=_time_axis(paths),
        vertical_axis=StandardAxisBoundsV2(
            axis_id="metric_value",
            label=_metric_axis_label(kind),
            unit="mixed" if len({item[3] for item in entries}) > 1 else entries[0][3],
            full_source_min=min(values),
            full_source_max=max(values),
        ),
        source_extrema=proof,
        source_point_count=proof.source_point_count,
        returned_point_count=returned,
        truncated=proof.source_point_count > returned,
        series=series,
        reason="Bounded aligned-time metric series",
    )


def _waterfall_view(
    loaded: _Projection,
    subject: StandardSubjectSummaryV2,
    paths: tuple[_PathSource, ...],
    maximum_points: int,
) -> StandardPlotViewV2:
    entries: list[tuple[str, float, float, float]] = []
    lanes = []
    for path in paths:
        waterfall = path.document["waterfall"]
        offset_s = _path_time_offset_s(path, paths)
        receiver_ids = tuple(waterfall["receiver_ids"])
        try:
            receiver_index = receiver_ids.index(path.binding.receiver_id)
        except ValueError as error:
            raise StandardPresentationUnavailable("waterfall receiver inventory drifted") from error
        frequencies = waterfall["frequency_bin_centers_hz"]
        values = []
        for tile in waterfall["tiles"]:
            time_s = offset_s + (tile["sample_start"] + tile["sample_stop"]) / (
                2 * path.binding.sample_rate_hz
            )
            powers = tile["receiver_power_dbfs"][receiver_index]
            for frequency, power in zip(frequencies, powers, strict=True):
                entries.append((path.reference.path_id, time_s, frequency, power))
                values.append((frequency, power))
        lanes.append(_lane_extrema(path.reference.path_id, ("frequency_hz", "power_db"), values))
    selected = _select_waterfall_grid(entries, maximum_points)
    proof = _proof(loaded, paths, StandardViewKindV2.WATERFALL, tuple(lanes))
    frequencies = [item[2] for item in entries]
    powers = [item[3] for item in entries]
    cells = tuple(
        StandardWaterfallCellV2(
            receiver_path_id=lane, time_s=time_s, frequency_hz=frequency, power_db=power
        )
        for lane, time_s, frequency, power in selected
    )
    return StandardPlotViewV2(
        session_id=loaded.snapshot.session_id,
        subject_id=subject.subject_id,
        view_kind=StandardViewKindV2.WATERFALL,
        state=StandardViewStateV2.AVAILABLE,
        time_domain=_time_domain(paths),
        receiver_path_ids=tuple(path.reference.path_id for path in paths),
        horizontal_axis=StandardAxisBoundsV2(
            axis_id="frequency_hz",
            label="Baseband frequency",
            unit="Hz",
            full_source_min=min(frequencies),
            full_source_max=max(frequencies),
        ),
        vertical_axis=_time_axis(paths),
        color_axis=StandardAxisBoundsV2(
            axis_id="power_db",
            label="Power",
            unit="dB",
            full_source_min=min(powers),
            full_source_max=max(powers),
        ),
        source_extrema=proof,
        source_point_count=proof.source_point_count,
        returned_point_count=len(cells),
        truncated=proof.source_point_count > len(cells),
        waterfall_cells=cells,
        reason="Frequency-horizontal/time-vertical waterfall tiles",
    )


def _cfo_view(
    loaded: _Projection,
    subject: StandardSubjectSummaryV2,
    paths: tuple[_PathSource, ...],
    maximum_points: int,
) -> StandardPlotViewV2:
    observations: list[StandardCfoObservationV2] = []
    curves: list[StandardTrajectoryCurveV2] = []
    lane_values: dict[str, list[float]] = defaultdict(list)
    for path in paths:
        lane = path.reference.path_id
        offset_s = _path_time_offset_s(path, paths)
        for index, item in enumerate(path.document["pilot_scan"]["detections"]):
            score = next((score for score in item["scores"] if score["method"] == "glrt64"), None)
            if score is None:
                continue
            observations.append(
                StandardCfoObservationV2(
                    observation_id=f"obs:{lane}:{index}",
                    receiver_path_id=lane,
                    algorithm="glrt64",
                    time_s=offset_s + item["time_s"],
                    baseband_cfo_hz=score["tracking_cfo_hz"],
                    glrt64_response=score["exact_score"],
                )
            )
            lane_values[lane].append(score["tracking_cfo_hz"])
        for item in path.document["final_trajectory_table"]["trajectories"]:
            automatic = bool(item.get("automatic_correction_eligible", True))
            count = 17
            local_times = tuple(
                item["start_s"] + (item["end_s"] - item["start_s"]) * index / (count - 1)
                for index in range(count)
            )
            values = tuple(
                _polynomial(item["absolute_coefficients_hz"], time_s - item["reference_time_s"])
                for time_s in local_times
            )
            times = tuple(offset_s + time_s for time_s in local_times)
            lane_values[lane].extend(values)
            curves.append(
                StandardTrajectoryCurveV2(
                    trajectory_id=item["trajectory_id"],
                    receiver_path_id=lane,
                    degree=item["polynomial_degree"],
                    selected_for_correction=automatic,
                    points=tuple(
                        StandardSeriesPointV2(time_s=time_s, value=value)
                        for time_s, value in zip(times, values, strict=True)
                    ),
                )
            )
    flattened = [
        ("observation", item.receiver_path_id, index, -1, item.time_s, item.baseband_cfo_hz)
        for index, item in enumerate(observations)
    ] + [
        ("curve", curve.receiver_path_id, curve_index, point_index, point.time_s, point.value)
        for curve_index, curve in enumerate(curves)
        for point_index, point in enumerate(curve.points)
    ]
    selected = _select_by_lane(flattened, maximum_points, lambda item: item[1])
    observation_ids = {item[2] for item in selected if item[0] == "observation"}
    curve_ids = {(item[2], item[3]) for item in selected if item[0] == "curve"}
    bounded_observations = tuple(
        item for index, item in enumerate(observations) if index in observation_ids
    )
    bounded_curves = tuple(
        curve.model_copy(
            update={
                "points": tuple(
                    point
                    for point_index, point in enumerate(curve.points)
                    if (curve_index, point_index) in curve_ids
                )
            }
        )
        for curve_index, curve in enumerate(curves)
        if any(index == curve_index for index, _ in curve_ids)
    )
    lanes = tuple(
        _lane_extrema(
            path.reference.path_id, ("frequency_hz",), lane_values[path.reference.path_id]
        )
        for path in paths
    )
    proof = _proof(loaded, paths, StandardViewKindV2.CFO_TRAJECTORY, lanes)
    returned = len(bounded_observations) + sum(len(item.points) for item in bounded_curves)
    all_values = [value for values in lane_values.values() for value in values]
    return StandardPlotViewV2(
        session_id=loaded.snapshot.session_id,
        subject_id=subject.subject_id,
        view_kind=StandardViewKindV2.CFO_TRAJECTORY,
        state=StandardViewStateV2.AVAILABLE,
        time_domain=_time_domain(paths),
        receiver_path_ids=tuple(path.reference.path_id for path in paths),
        horizontal_axis=_time_axis(paths),
        vertical_axis=StandardAxisBoundsV2(
            axis_id="frequency_hz",
            label="Baseband CFO",
            unit="Hz",
            full_source_min=min(all_values),
            full_source_max=max(all_values),
        ),
        source_extrema=proof,
        source_point_count=proof.source_point_count,
        returned_point_count=returned,
        truncated=proof.source_point_count > returned,
        cfo_observations=bounded_observations,
        trajectory_curves=bounded_curves,
        reason="GLRT64 CFO observations with fitted candidate trajectories",
    )


def _proof(
    loaded: _Projection,
    paths: tuple[_PathSource, ...],
    kind: StandardViewKindV2,
    lanes: tuple[StandardLaneSourceExtremaV2, ...],
) -> StandardSourceExtremaProofV2:
    content = canonical_digest(
        {"view_kind": kind.value, "products": [item.product.digest for item in paths]}
    )
    return standard_source_extrema_from_lanes_v2(
        source_artifact_digest=loaded.manifest_digest,
        source_content_digest=_digest(content),
        lanes=lanes,
    )


def _lane_extrema(
    path_id: str, axes: tuple[StandardSourceAxisIdV2, ...], values: Iterable[Any]
) -> StandardLaneSourceExtremaV2:
    rows = list(values)
    if not rows:
        raise StandardPresentationUnavailable("Standard view has an empty receiver-path lane")
    columns: tuple[list[Any], ...]
    if len(axes) == 1:
        columns = (rows,)
    else:
        columns = tuple([row[index] for row in rows] for index in range(len(axes)))
    return StandardLaneSourceExtremaV2(
        receiver_path_id=path_id,
        source_point_count=len(rows),
        axes=tuple(
            StandardSourceAxisExtremaV2(
                axis_id=axis, source_min=min(column), source_max=max(column)
            )
            for axis, column in zip(axes, columns, strict=True)
        ),
    )


def _select_by_lane(items: list[Any], maximum: int, lane) -> list[Any]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for item in items:
        grouped[lane(item)].append(item)
    if maximum < len(grouped):
        raise ValueError("maximum_points does not cover every source-backed lane")
    selected = [values[0] for values in grouped.values()]
    remaining = maximum - len(selected)
    candidates = [item for values in grouped.values() for item in values[1:]]
    if remaining and candidates:
        if len(candidates) <= remaining:
            selected.extend(candidates)
        else:
            selected.extend(
                candidates[round(index * (len(candidates) - 1) / (remaining - 1))]
                for index in range(remaining)
            ) if remaining > 1 else selected.append(candidates[-1])
    positions = {id(item): index for index, item in enumerate(items)}
    return sorted(selected, key=lambda item: positions[id(item)])


def _select_waterfall_grid(
    items: list[tuple[str, float, float, float]], maximum: int
) -> list[tuple[str, float, float, float]]:
    """Select a rectangular time/frequency grid per lane, never diagonal stripes."""

    grouped: dict[str, list[tuple[str, float, float, float]]] = defaultdict(list)
    for item in items:
        grouped[item[0]].append(item)
    if maximum < len(grouped):
        raise ValueError("maximum_points does not cover every source-backed lane")
    per_lane = maximum // len(grouped)
    selected: list[tuple[str, float, float, float]] = []
    for values in grouped.values():
        times = tuple(sorted({item[1] for item in values}))
        frequencies = tuple(sorted({item[2] for item in values}))
        time_count = min(
            len(times),
            max(1, round(math.sqrt(per_lane * len(times) / max(1, len(frequencies))))),
        )
        frequency_count = min(len(frequencies), max(1, per_lane // time_count))
        chosen_times = set(_evenly_spaced_values(times, time_count))
        chosen_frequencies = set(_evenly_spaced_values(frequencies, frequency_count))
        selected.extend(
            item for item in values if item[1] in chosen_times and item[2] in chosen_frequencies
        )
    positions = {id(item): index for index, item in enumerate(items)}
    return sorted(selected, key=lambda item: positions[id(item)])


def _evenly_spaced_values[ValueT](values: tuple[ValueT, ...], count: int) -> tuple[ValueT, ...]:
    if count >= len(values):
        return values
    if count == 1:
        return (values[0],)
    return tuple(values[round(index * (len(values) - 1) / (count - 1))] for index in range(count))


def _time_axis(paths: tuple[_PathSource, ...]) -> StandardAxisBoundsV2:
    domain = _time_domain(paths)
    return StandardAxisBoundsV2(
        axis_id="time",
        label="Shared elapsed time",
        unit="s",
        full_source_min=domain.elapsed_start_s,
        full_source_max=domain.elapsed_end_s,
    )


def _path_time_offset_s(path: _PathSource, paths: tuple[_PathSource, ...]) -> float:
    first = min(item.binding.timing.first_estimate_utc_ns for item in paths)
    return (path.binding.timing.first_estimate_utc_ns - first) / 1_000_000_000


def _png_scope_matches(subject: StandardSubjectSummaryV2, scope: ScopeIdentityV1) -> bool:
    if subject.subject_kind is StandardSubjectKindV2.RECEIVER_PATH:
        return scope == subject.receiver_paths[0].scope
    if subject.subject_kind is StandardSubjectKindV2.RADIO:
        return (
            scope.kind is ScopeKind.RADIO
            and scope.radio_id == subject.receiver_paths[0].radio_id
            and scope.stream_id == subject.receiver_paths[0].scope.stream_id
        )
    return scope.kind is ScopeKind.PAIRED and scope.session_id == subject.session_id


def _metric_axis_label(kind: StandardViewKindV2) -> str:
    return {
        StandardViewKindV2.QUALITY: "Quality metrics",
        StandardViewKindV2.POWER: "Power",
        StandardViewKindV2.GLRT64: "GLRT64 detector response",
        StandardViewKindV2.QAM: "Known-pilot QAM metrics",
    }[kind]


def _polynomial(coefficients: list[float], offset_s: float) -> float:
    result = 0.0
    for coefficient in coefficients:
        result = result * offset_s + coefficient
    return result


def _digest(value: str | None) -> str:
    if value is None:
        raise StandardPresentationUnavailable("required digest is absent")
    normalized = value.removeprefix("sha256:")
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise StandardPresentationUnavailable("required digest is invalid")
    return normalized
