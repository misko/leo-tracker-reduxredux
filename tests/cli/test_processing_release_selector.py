from pathlib import Path

from leo.cli.processing import ProcessingBackendSettings


def test_processing_release_authority_uses_worker_component_selector() -> None:
    settings = ProcessingBackendSettings(
        database_url="postgresql+psycopg:///leo_test",
        bulk_root=Path("/srv/bulk/leo"),
        corpus_root=Path("/srv/bulk/leo/test-corpus"),
    )

    assert settings.current_release_link == Path("/opt/leo-tracker/current-worker")
