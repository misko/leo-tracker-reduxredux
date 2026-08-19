"""Scientific controls and small summary projectors."""

from leo.analysis.controls.evidence import (
    CandidateControlEvidence,
    ControlConfig,
    ControlResult,
    evaluate_candidate_controls,
)
from leo.analysis.controls.summary import (
    CandidateOverlayPoint,
    ScientificSummary,
    TrackOverlay,
    build_scientific_summary,
)

__all__ = [
    "CandidateControlEvidence",
    "CandidateOverlayPoint",
    "ControlConfig",
    "ControlResult",
    "ScientificSummary",
    "TrackOverlay",
    "build_scientific_summary",
    "evaluate_candidate_controls",
]
