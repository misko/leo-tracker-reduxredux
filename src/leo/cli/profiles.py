"""Read-only capture-profile discovery for CLI composition."""

from __future__ import annotations

from pathlib import Path

from leo.cli.backend import CliBackendError
from leo.cli.models import (
    ExitCode,
    ProfileListDataV1,
    ProfileShowDataV1,
    ProfileShowDataV2,
    ProfileSummaryV1,
    ProfileValidationDataV1,
    ProfileValidationItemV1,
)
from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileRevisionV2
from leo.domain.profiles import load_profile_revision


class ProfileDirectory:
    def __init__(self, root: Path) -> None:
        self.root = root

    def list_profiles(self) -> ProfileListDataV1:
        revisions = self._valid_revisions()
        return ProfileListDataV1(
            profiles=tuple(
                _summary(path, revision)
                for path, revision in sorted(
                    revisions,
                    key=lambda item: item[1].profile.name,
                )
            )
        )

    def show(self, name: str) -> ProfileShowDataV1 | ProfileShowDataV2:
        matches = [
            (path, revision)
            for path, revision in self._valid_revisions()
            if revision.profile.name == name
        ]
        if not matches:
            raise CliBackendError(f"capture profile not found: {name}", ExitCode.NOT_FOUND)
        if len(matches) > 1:
            raise CliBackendError(
                f"capture profile name is duplicated: {name}",
                ExitCode.INVALID_CONFIGURATION,
            )
        path, revision = matches[0]
        if isinstance(revision, CaptureProfileRevisionV2):
            return ProfileShowDataV2(path=str(path.resolve()), revision=revision)
        return ProfileShowDataV1(path=str(path.resolve()), revision=revision)

    def validate(self, target: str | None) -> ProfileValidationDataV1:
        paths = self._paths()
        items: list[ProfileValidationItemV1] = []
        for path in paths:
            try:
                revision = load_profile_revision(path)
            except Exception as error:
                item = ProfileValidationItemV1(
                    path=str(path.resolve()),
                    valid=False,
                    error=f"{type(error).__name__}: {error}",
                )
            else:
                item = ProfileValidationItemV1(
                    path=str(path.resolve()),
                    name=revision.profile.name,
                    valid=True,
                    revision_digest=revision.revision_digest,
                )
            if target is None or item.name == target or path.stem == target:
                items.append(item)
        if target is not None and not items:
            raise CliBackendError(f"capture profile not found: {target}", ExitCode.NOT_FOUND)
        return ProfileValidationDataV1(
            valid=bool(items) and all(item.valid for item in items),
            items=tuple(items),
        )

    def count_valid(self) -> int:
        return len(self._valid_revisions())

    def _valid_revisions(
        self,
    ) -> list[tuple[Path, CaptureProfileRevisionV1 | CaptureProfileRevisionV2]]:
        validation = self.validate(None)
        invalid = tuple(item for item in validation.items if not item.valid)
        if invalid:
            raise CliBackendError(
                f"{len(invalid)} capture profile document(s) are invalid",
                ExitCode.INVALID_CONFIGURATION,
            )
        revisions = [(path, load_profile_revision(path)) for path in self._paths()]
        names = [revision.profile.name for _, revision in revisions]
        if len(names) != len(set(names)):
            raise CliBackendError(
                "capture profile names must be unique",
                ExitCode.INVALID_CONFIGURATION,
            )
        return revisions

    def _paths(self) -> tuple[Path, ...]:
        if not self.root.is_dir():
            raise CliBackendError(
                f"capture profile directory does not exist: {self.root}",
                ExitCode.INVALID_CONFIGURATION,
            )
        return tuple(sorted((*self.root.glob("*.yaml"), *self.root.glob("*.yml"))))


def _summary(
    path: Path,
    revision: CaptureProfileRevisionV1 | CaptureProfileRevisionV2,
) -> ProfileSummaryV1:
    profile = revision.profile
    return ProfileSummaryV1(
        name=profile.name,
        revision_digest=revision.revision_digest,
        sample_rate_hz=profile.sample_rate_hz,
        sample_count=profile.sample_count,
        duration_seconds=(
            None if profile.duration_seconds is None else str(profile.duration_seconds)
        ),
        receivers=profile.receivers,
        tags=profile.tags,
        path=str(path.resolve()),
    )
