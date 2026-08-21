from types import SimpleNamespace

import pytest

from leo.cli.backend import CliBackendError
from leo.cli.models import ExitCode
from leo.cli.processing import LocalProcessingBackend

CURRENT = "a" * 40


class _CatalogMustNotRun:
    def stop_and_fence_release(self, **kwargs):
        raise AssertionError(f"catalog mutation unexpectedly reached: {kwargs!r}")


def _backend() -> LocalProcessingBackend:
    return LocalProcessingBackend(
        SimpleNamespace(catalog=_CatalogMustNotRun(), pipeline_release_id=CURRENT)
    )


def test_current_release_fence_requires_separate_explicit_override() -> None:
    with pytest.raises(CliBackendError) as caught:
        _backend().stop_and_fence(
            operation_id="deploy-1",
            pipeline_release_id=CURRENT,
            operator_id="operator",
            reason="cutover",
            expected_run_ids=None,
            allow_current_release=False,
        )

    assert caught.value.exit_code == ExitCode.CONFIRMATION_REQUIRED
    assert "--allow-current-release" in str(caught.value)


def test_non_exact_release_is_refused_before_catalog_mutation() -> None:
    with pytest.raises(CliBackendError) as caught:
        _backend().stop_and_fence(
            operation_id="deploy-1",
            pipeline_release_id="old-release",
            operator_id="operator",
            reason="cutover",
            expected_run_ids=None,
            allow_current_release=True,
        )

    assert caught.value.exit_code == ExitCode.INVALID_CONFIGURATION
