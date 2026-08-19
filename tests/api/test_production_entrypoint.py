from __future__ import annotations

import sys
from pathlib import Path

import pytest

from leo.api import production


def test_api_entrypoint_check_validates_settings_without_starting_server(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(sys, "argv", ["leo-api", "--check"])

    def unexpected_run(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("entrypoint check must not start uvicorn")

    monkeypatch.setattr(production.uvicorn, "run", unexpected_run)
    production.main()

    assert capsys.readouterr().out.startswith("leo-api entrypoint ok:")


def test_production_composition_rejects_qnap_before_database_or_filesystem_writes(
    monkeypatch,
) -> None:
    def unexpected_engine(_url):
        raise AssertionError("QNAP rejection must precede database composition")

    monkeypatch.setattr(production, "create_catalog_engine", unexpected_engine)
    with pytest.raises(ValueError, match="absolute local storage"):
        production.create_production_app(
            production.ProductionSettings(
                database_url="postgresql+psycopg:///unused",
                bulk_root=Path("/mnt/qnap01/leo-api-forbidden"),
                qualification_root=Path("/mnt/qnap01/leo-api-forbidden/qualification"),
            )
        )
