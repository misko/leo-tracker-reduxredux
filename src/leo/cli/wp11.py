"""Thin typed CLI adapter for operational WP11 campaigns."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from leo.application.frequency_calibration import (
    ImmutableDocumentRefV1,
    NativeReleaseCalibrationEvidenceAdapter,
)
from leo.application.wp11_legacy import (
    WP11LegacyOracleCampaignRunner,
    publish_current_wp11_config,
)
from leo.application.wp11_operations import WP11Operations
from leo.application.wp11_production import WP11RunConflict
from leo.catalog import ActiveRunExistsError, CatalogNotFoundError, ProductConflictError
from leo.cli.backend import CliBackendError
from leo.cli.models import (
    ExitCode,
    WP11ConfigDataV1,
    WP11CreateDataV1,
    WP11FinalizeDataV1,
    WP11LegacyDataV1,
    WP11QueueDataV1,
    WP11ShowDataV1,
)
from leo.contracts.scientific import MatchedPilotAcceptanceConfigV1
from leo.qualification.trusted_campaign_store import TrustedCampaignPublicationConflict
from leo.qualification.wp11_plan_store import WP11PlanConflict


class WP11CliBackend:
    def __init__(
        self,
        operations: WP11Operations,
        legacy: WP11LegacyOracleCampaignRunner | None = None,
        releases: NativeReleaseCalibrationEvidenceAdapter | None = None,
    ) -> None:
        self._operations = operations
        self._legacy = legacy
        self._releases = releases

    def wp11_config(self, *, output_path: Path) -> WP11ConfigDataV1:
        if self._releases is None:
            raise CliBackendError(
                "WP11 deployed release authority is not configured",
                ExitCode.INVALID_CONFIGURATION,
            )
        try:
            return WP11ConfigDataV1(
                result=publish_current_wp11_config(self._releases, output_path)
            )
        except FileExistsError as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        except (OSError, ValueError) as error:
            raise CliBackendError(str(error), ExitCode.INVALID_CONFIGURATION) from error

    def wp11_create(
        self,
        *,
        campaign_id: str,
        capture_uri: str,
        capture_digest: str,
        config_path: Path,
    ) -> WP11CreateDataV1:
        try:
            config = MatchedPilotAcceptanceConfigV1.model_validate_json(config_path.read_bytes())
            return WP11CreateDataV1(
                result=self._operations.create(
                    campaign_id=campaign_id,
                    capture=ImmutableDocumentRefV1(
                        logical_uri=capture_uri,
                        digest=capture_digest,
                    ),
                    processing_config=config,
                )
            )
        except FileNotFoundError as error:
            raise CliBackendError(str(error), ExitCode.NOT_FOUND) from error
        except (OSError, ValidationError) as error:
            raise CliBackendError(str(error), ExitCode.INVALID_CONFIGURATION) from error
        except WP11PlanConflict as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        except ValueError as error:
            raise CliBackendError(str(error), ExitCode.UNHEALTHY) from error

    def wp11_queue(self, campaign_id: str) -> WP11QueueDataV1:
        try:
            if self._legacy is None:
                raise CliBackendError(
                    "WP11 legacy campaign runner is not configured",
                    ExitCode.INVALID_CONFIGURATION,
                )
            self._legacy.require_complete(campaign_id)
            return WP11QueueDataV1(result=self._operations.queue(campaign_id))
        except CliBackendError:
            raise
        except (FileNotFoundError, CatalogNotFoundError) as error:
            raise CliBackendError(
                "WP11 plan or legacy evidence is incomplete; run wp11 legacy before queue",
                ExitCode.NOT_FOUND,
            ) from error
        except (ActiveRunExistsError, ProductConflictError, WP11RunConflict) as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        except ValueError as error:
            raise CliBackendError(str(error), ExitCode.UNHEALTHY) from error

    def wp11_legacy(
        self,
        campaign_id: str,
        *,
        ordinals: tuple[int, ...],
    ) -> WP11LegacyDataV1:
        if self._legacy is None:
            raise CliBackendError(
                "WP11 legacy campaign runner is not configured",
                ExitCode.INVALID_CONFIGURATION,
            )
        try:
            return WP11LegacyDataV1(
                result=self._legacy.run(campaign_id, ordinals=ordinals)
            )
        except (FileNotFoundError, CatalogNotFoundError) as error:
            raise CliBackendError(str(error), ExitCode.NOT_FOUND) from error
        except ValueError as error:
            raise CliBackendError(str(error), ExitCode.UNHEALTHY) from error

    def wp11_finalize(self, campaign_id: str) -> WP11FinalizeDataV1:
        try:
            return WP11FinalizeDataV1(publication=self._operations.finalize(campaign_id))
        except (FileNotFoundError, CatalogNotFoundError) as error:
            raise CliBackendError(str(error), ExitCode.NOT_FOUND) from error
        except TrustedCampaignPublicationConflict as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        except ValueError as error:
            raise CliBackendError(str(error), ExitCode.UNHEALTHY) from error

    def wp11_show(self, campaign_id: str) -> WP11ShowDataV1:
        try:
            return WP11ShowDataV1(summary=self._operations.show(campaign_id))
        except (FileNotFoundError, CatalogNotFoundError) as error:
            raise CliBackendError(str(error), ExitCode.NOT_FOUND) from error
        except ValueError as error:
            raise CliBackendError(str(error), ExitCode.UNHEALTHY) from error
