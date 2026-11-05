"""Application composition with public adapters loaded only when requested.

Importing an independent numerical application must not initialize acquisition,
database or concrete storage adapters belonging to unrelated applications.
"""

from importlib import import_module

_EXPORT_MODULES = {
    "calibration_catalog": (
        "AuthoritativeCalibrationPublication",
        "AuthoritativeCalibrationResolverPort",
        "CalibrationCatalogPort",
        "PostgresCalibrationCatalogAdapter",
        "ResolvedFrequencyCalibration",
    ),
    "capture_control": ("CaptureControlAuthorityPort", "OperatorCaptureControl"),
    "presentation": ("CatalogPresentationRepository",),
    "research_reprocess": (
        "AnalysisControlStatusV2",
        "ResearchReprocessor",
        "ResearchReprocessResultV1",
        "ResearchReprocessService",
    ),
    "standard_native_presentation": (
        "CatalogStandardNativePresentationRepository",
        "DefinitionDispatchedStandardPresentationRepository",
    ),
    "standard_presentation": (
        "CatalogStandardPresentationRepository",
        "StandardPresentationNotReady",
        "StandardPresentationUnavailable",
    ),
    "standard_reprocess": (
        "StandardControlStatusV1",
        "StandardNativeEvidenceReprocessor",
        "StandardNativeEvidenceResultV1",
        "StandardReprocessError",
        "StandardReprocessNotFound",
        "StandardReprocessor",
        "StandardReprocessResultV1",
        "StandardReprocessService",
        "StandardReprocessUnavailable",
    ),
    "trusted_campaign_production": (
        "TrustedCampaignProductionSettings",
        "TrustedCampaignService",
        "open_trusted_campaign_service",
    ),
}
_MODULE_BY_NAME = {name: module for module, names in _EXPORT_MODULES.items() for name in names}


def __getattr__(name):
    try:
        module = _MODULE_BY_NAME[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(f"{__name__}.{module}"), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


__all__ = [
    "AuthoritativeCalibrationPublication",
    "AuthoritativeCalibrationResolverPort",
    "CalibrationCatalogPort",
    "CaptureControlAuthorityPort",
    "CatalogPresentationRepository",
    "CatalogStandardPresentationRepository",
    "CatalogStandardNativePresentationRepository",
    "DefinitionDispatchedStandardPresentationRepository",
    "PostgresCalibrationCatalogAdapter",
    "OperatorCaptureControl",
    "ResolvedFrequencyCalibration",
    "AnalysisControlStatusV2",
    "ResearchReprocessResultV1",
    "ResearchReprocessService",
    "ResearchReprocessor",
    "StandardPresentationNotReady",
    "StandardPresentationUnavailable",
    "StandardControlStatusV1",
    "StandardNativeEvidenceReprocessor",
    "StandardNativeEvidenceResultV1",
    "StandardReprocessError",
    "StandardReprocessNotFound",
    "StandardReprocessResultV1",
    "StandardReprocessor",
    "StandardReprocessService",
    "StandardReprocessUnavailable",
    "TrustedCampaignProductionSettings",
    "TrustedCampaignService",
    "open_trusted_campaign_service",
]
