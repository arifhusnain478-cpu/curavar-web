"""Test configuration: put the repo root on sys.path so ``web.api`` imports, and
expose a FastAPI TestClient bound to the app (offline replay mode throughout)."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

# repo root = …/files (16), which contains both the `web` package and `curavar/`
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from web.api.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def offline_by_default(monkeypatch):
    """Run the web suite offline by default — its documented contract is "no API
    key, no network". With server-side auto-routing, an ambient ANTHROPIC_API_KEY
    (e.g. loaded from web/api/.env) would otherwise send unmatched variants down
    the live path and hit the real network. Live-path tests opt back in with
    ``monkeypatch.setenv("ANTHROPIC_API_KEY", ...)``.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
