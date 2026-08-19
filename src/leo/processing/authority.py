"""Release authority derived from the code and registry actually loaded by a worker."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from leo.catalog import WorkerReleaseAuthority
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.pipeline import AnalyzerRegistry


@dataclass(frozen=True, slots=True)
class LoadedWorkerRelease:
    """Receipt for one inspected worker runtime, not caller-supplied digest claims."""

    authority: WorkerReleaseAuthority
    registry_document: dict[str, object]
    environment_document: dict[str, object]
    executable_inventory: tuple[tuple[str, str], ...]
    _revalidator: Callable[[], WorkerReleaseAuthority] = field(repr=False, compare=False)

    def revalidate(self) -> WorkerReleaseAuthority:
        """Re-read the deployed runtime; never reuse construction-time digest claims."""

        return self._revalidator()


def derive_loaded_worker_release_for_tests(
    *,
    pipeline_release_id: str,
    code_revision: str,
    registry: AnalyzerRegistry,
    configuration: dict[str, object],
    environment_document: dict[str, object],
    executable_root: Path,
    stage_keys: tuple[str, ...] | None = None,
) -> LoadedWorkerRelease:
    """Test-only constructor for synthetic release trees."""

    resolved = executable_root.resolve(strict=True)
    if not resolved.is_dir() or resolved.is_symlink():
        raise ValueError("worker executable root must be a real staged directory")
    keys = registry.keys if stage_keys is None else tuple(sorted(stage_keys))
    registry_document: dict[str, object] = {
        "stages": [
            registry.get(stage.key).spec.model_dump(mode="json")
            for stage in registry.graph(keys).plan()
        ]
    }
    inventory: list[tuple[str, str]] = []
    for path in sorted(item for item in resolved.rglob("*") if item.is_file()):
        if path.is_symlink():
            raise ValueError(f"worker executable inventory contains a symlink: {path}")
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                digest = sha256_digest(source.read())
        finally:
            os.close(descriptor)
        inventory.append((path.relative_to(resolved).as_posix(), digest))
    if not inventory:
        raise ValueError("worker executable inventory must not be empty")
    authority = WorkerReleaseAuthority(
        pipeline_release_id=pipeline_release_id,
        code_revision=code_revision,
        environment_digest=canonical_digest(environment_document),
        graph_digest=canonical_digest(registry_document),
        configuration_digest=canonical_digest(configuration),
        executable_digest=canonical_digest(inventory),
    )
    return LoadedWorkerRelease(
        authority=authority,
        registry_document=registry_document,
        environment_document=environment_document,
        executable_inventory=tuple(inventory),
        _revalidator=lambda: (
            derive_loaded_worker_release_for_tests(
                pipeline_release_id=pipeline_release_id,
                code_revision=code_revision,
                registry=registry,
                configuration=configuration,
                environment_document=environment_document,
                executable_root=executable_root,
                stage_keys=stage_keys,
            ).authority
        ),
    )


def derive_deployed_worker_release(
    *,
    registry: AnalyzerRegistry,
    configuration: dict[str, object],
    current_link: Path = Path("/opt/leo-tracker/current"),
    deployment_root: Path = Path("/opt/leo-tracker"),
    stage_keys: tuple[str, ...] | None = None,
    validator: object | None = None,
) -> LoadedWorkerRelease:
    """Derive production authority from the validated deployed-current release."""

    from leo.qualification.native_release import load_trusted_current_release

    evidence = load_trusted_current_release(
        pipeline_release="worker-runtime",
        current_link=current_link,
        deployment_root=deployment_root,
        validator=validator,  # type: ignore[arg-type]
    )
    if re.fullmatch(r"[0-9a-f]{40}", evidence.source_revision) is None:
        raise ValueError("validated current release is not an exact Git revision")
    keys = registry.keys if stage_keys is None else tuple(sorted(stage_keys))
    registry_document: dict[str, object] = {
        "stages": [
            registry.get(stage.key).spec.model_dump(mode="json")
            for stage in registry.graph(keys).plan()
        ]
    }
    environment_document: dict[str, object] = {
        "interpreter_digest": evidence.interpreter_digest,
        "runtime_package_tree_digest": evidence.runtime_package_tree_digest,
        "release_metadata_digest": evidence.release_metadata_digest,
    }
    executable_inventory = (
        ("git-source-tree", evidence.source_tree_digest),
        ("native-evidence-worker", evidence.worker_digest),
        ("python-interpreter", evidence.interpreter_digest),
        ("runtime-package-tree", evidence.runtime_package_tree_digest),
    )
    return LoadedWorkerRelease(
        authority=WorkerReleaseAuthority(
            pipeline_release_id=evidence.source_revision,
            code_revision=evidence.source_revision,
            environment_digest=canonical_digest(environment_document),
            graph_digest=canonical_digest(registry_document),
            configuration_digest=canonical_digest(configuration),
            executable_digest=canonical_digest(executable_inventory),
        ),
        registry_document=registry_document,
        environment_document=environment_document,
        executable_inventory=executable_inventory,
        _revalidator=lambda: (
            derive_deployed_worker_release(
                registry=registry,
                configuration=configuration,
                current_link=current_link,
                deployment_root=deployment_root,
                stage_keys=stage_keys,
                validator=validator,
            ).authority
        ),
    )
