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


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
