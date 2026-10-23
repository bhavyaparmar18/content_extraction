"""Shared test setup."""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolated_app_db(monkeypatch, tmp_path):
    """``get_settings()`` (and so the app's startup) uses a database under tmp_path, never data/app.db."""
    monkeypatch.setenv("SOP_DB_PATH", str(tmp_path / "app.db"))


@pytest.fixture(autouse=True)
def _no_word_layout(monkeypatch):
    """Rendering never drives Microsoft Word for TOC page numbers unless Word tests are asked for."""
    if os.environ.get("SOP_RUN_WORD_TESTS") != "1":
        monkeypatch.setenv("SOP_RENDER_TOC_PAGES", "off")
