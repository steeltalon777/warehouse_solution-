# -*- coding: utf-8 -*-
"""Общие фикстуры и хелперы тестов warehouse-storekeeper.

Тесты НЕ обращаются к сети и production: HTTP подменяется httpx.MockTransport.
"""
import json
import os
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import warehouse_api as wa  # noqa: E402

FIXTURES = TESTS_DIR / "fixtures"

TEST_USER_TOKEN = "11111111-2222-3333-4444-555555555555"
TEST_DEVICE_TOKEN = "66666666-7777-8888-9999-000000000000"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture()
def fixture_loader():
    return load_fixture


@pytest.fixture()
def base_config(tmp_path):
    return {
        "SYNC_SERVER_BASE_URL": "http://192.168.10.20:8000",
        "SYNC_SERVER_USER_TOKEN": TEST_USER_TOKEN,
        "SYNC_SERVER_DEVICE_TOKEN": TEST_DEVICE_TOKEN,
        "SYNC_SERVER_ALLOW_INSECURE_LOCAL": "true",
    }


@pytest.fixture()
def make_client(base_config):
    import httpx

    def _factory(handler, config=None):
        transport = httpx.MockTransport(handler)
        return wa.SyncClient(config or base_config, transport=transport, retry_backoff=(0.0, 0.0))

    return _factory


@pytest.fixture()
def secrets_file(tmp_path):
    """Временный env-файл с безопасными POSIX-правами (для CLI-тестов)."""
    path = tmp_path / "syncserver.env"
    path.write_text(
        "SYNC_SERVER_BASE_URL=http://192.168.10.20:8000\n"
        f"SYNC_SERVER_USER_TOKEN={TEST_USER_TOKEN}\n"
        f"SYNC_SERVER_DEVICE_TOKEN={TEST_DEVICE_TOKEN}\n"
        "SYNC_SERVER_ALLOW_INSECURE_LOCAL=true\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return path
