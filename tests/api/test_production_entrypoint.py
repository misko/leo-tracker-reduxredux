from __future__ import annotations

import sys

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
