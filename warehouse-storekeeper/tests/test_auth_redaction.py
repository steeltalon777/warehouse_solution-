# -*- coding: utf-8 -*-
"""Тесты маскирования секретов: токены не должны попадать в вывод, логи и ошибки."""
import json

import httpx

import warehouse_api as wa
from conftest import TEST_DEVICE_TOKEN, TEST_USER_TOKEN


class TestRedaction:
    def test_redact_token_values(self):
        text = f"error: token {TEST_USER_TOKEN} rejected"
        assert wa.redact_text(text, [TEST_USER_TOKEN]) == "error: token *** rejected"

    def test_redact_auth_headers(self):
        text = f"X-User-Token: {TEST_USER_TOKEN}, Authorization=Bearer abc123"
        result = wa.redact_text(text, [])
        assert TEST_USER_TOKEN not in result
        assert "abc123" not in result
        assert "X-User-Token" in result  # имя заголовка остаётся, значение маскируется

    def test_redact_short_values_ignored(self):
        # короткие строки не маскируем, чтобы не испортить текст
        text = "qty = 123"
        assert wa.redact_text(text, ["123"]) == "qty = 123"

    def test_error_body_with_token_is_masked(self):
        body = json.dumps({"detail": f"invalid X-User-Token '{TEST_USER_TOKEN}'"}).encode()
        errors = wa.map_error_response(401, body, [TEST_USER_TOKEN])
        assert TEST_USER_TOKEN not in json.dumps(errors, ensure_ascii=False)
        assert errors[0]["code"] == "UNAUTHORIZED"

    def test_non_json_snippet_masked(self):
        body = f"<html>token={TEST_DEVICE_TOKEN}</html>".encode()
        errors = wa.map_error_response(502, body, [TEST_DEVICE_TOKEN])
        assert TEST_DEVICE_TOKEN not in json.dumps(errors, ensure_ascii=False)

    def test_secret_values_from_config(self):
        config = {
            "SYNC_SERVER_USER_TOKEN": TEST_USER_TOKEN,
            "SYNC_SERVER_DEVICE_TOKEN": TEST_DEVICE_TOKEN,
            "SYNC_SERVER_BASE_URL": "https://x",
        }
        values = wa.secret_values_from_config(config)
        assert TEST_USER_TOKEN in values and TEST_DEVICE_TOKEN in values
        assert "https://x" not in values

    def test_config_check_contains_no_token_values(self, tmp_path, capsys=None):
        env_file = tmp_path / "syncserver.env"
        env_file.write_text(
            "SYNC_SERVER_BASE_URL=https://sync.example.com\n"
            f"SYNC_SERVER_USER_TOKEN={TEST_USER_TOKEN}\n",
            encoding="utf-8")
        envelope = wa.cmd_config_check(env_file)
        rendered = json.dumps(envelope, ensure_ascii=False)
        assert TEST_USER_TOKEN not in rendered
        assert envelope["data"]["user_token_present"] is True

    def test_headers_do_not_echo_in_verbose_errors(self):
        config = {
            "SYNC_SERVER_BASE_URL": "https://sync.example.com",
            "SYNC_SERVER_USER_TOKEN": TEST_USER_TOKEN,
        }
        client = wa.SyncClient(config, transport=httpx.MockTransport(
            lambda r: httpx.Response(500, json={"detail": "internal server error"})))
        _, _, errors = client.request("GET", "/api/v1/health", with_auth=False, idempotent=False)
        assert TEST_USER_TOKEN not in json.dumps(errors, ensure_ascii=False)
