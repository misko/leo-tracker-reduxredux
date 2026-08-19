from __future__ import annotations

from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.pipeline import AnalyzerRegistry, ProductSpec, StageOutcome, StageResult, StageSpec
from leo.processing import derive_loaded_worker_release_for_tests


class _Analyzer:
    spec = StageSpec(
        key="authority-test",
        algorithm_version="1",
        configuration_schema="authority-test.v1",
        output_products=(ProductSpec(kind="authority.output"),),
    )

    def analyze(self, _context, _iq, _products, _outputs) -> StageResult:
        return StageResult(outcome=StageOutcome.COMPLETE)


def test_loaded_worker_authority_is_derived_from_registry_config_and_executable(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "release"
    executable.mkdir()
    (executable / "worker.py").write_text("release bytes\n", encoding="utf-8")
    registry = AnalyzerRegistry((_Analyzer(),))
    configuration = {"stages": {"authority-test": {"chunk": 1}}}
    environment = {"python": "3.13", "numpy": "pinned"}

    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id="1" * 40,
        code_revision="2" * 40,
        registry=registry,
        configuration=configuration,
        environment_document=environment,
        executable_root=executable,
    )

    assert loaded.authority.configuration_digest == canonical_digest(configuration)
    assert loaded.authority.environment_digest == canonical_digest(environment)
    original = loaded.authority.executable_digest
    (executable / "worker.py").write_text("changed release bytes\n", encoding="utf-8")
    assert loaded.revalidate().executable_digest != original
    changed = derive_loaded_worker_release_for_tests(
        pipeline_release_id="1" * 40,
        code_revision="2" * 40,
        registry=registry,
        configuration=configuration,
        environment_document=environment,
        executable_root=executable,
    )
    assert changed.authority.executable_digest != original
