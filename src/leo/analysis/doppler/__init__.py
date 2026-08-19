"""Doppler and locked-integration numerical contracts."""

from leo.analysis.doppler.tracking import (
    DopplerFitConfig,
    DopplerFitResult,
    LockedFrame,
    LockedIntegrationConfig,
    LockedIntegrationResult,
    MotionClass,
    TleAssociationResult,
    TleAssociationStatus,
    TlePrediction,
    associate_tle_candidate,
    dedoppler_locked_integration,
    fit_doppler,
)

__all__ = [
    "DopplerFitConfig",
    "DopplerFitResult",
    "LockedFrame",
    "LockedIntegrationConfig",
    "LockedIntegrationResult",
    "MotionClass",
    "TleAssociationResult",
    "TleAssociationStatus",
    "TlePrediction",
    "associate_tle_candidate",
    "dedoppler_locked_integration",
    "fit_doppler",
]
