# -*- coding: utf-8 -*-
"""Тесты маппинга серверных ошибок в конверт: все 4 формата SyncServer.

Доменные коды сервера сохраняются, а не заменяются общим «что-то пошло не так».
"""
import json

import warehouse_api as wa
from conftest import load_fixture


class TestServerErrorShapes:
    def test_shape_a_canonical_envelope(self):
        body = json.dumps({
            "error": {"code": "CONFLICT", "message": "cannot update operation with status submitted",
                      "details": {"status": "submitted"}},
            "request_id": "req-1",
        }).encode()
        errors = wa.map_error_response(409, body, [])
        assert errors[0]["code"] == "CONFLICT"
        assert "submitted" in errors[0]["message"]
        assert errors[0]["details"] == {"status": "submitted"}

    def test_shape_b_detail_string(self):
        errors = wa.map_error_response(401, b'{"detail": "invalid X-User-Token"}', [])
        assert errors[0]["code"] == "UNAUTHORIZED"
        assert errors[0]["message"] == "invalid X-User-Token"

    def test_shape_b_403(self):
        errors = wa.map_error_response(403, b'{"detail": "catalog read access denied"}', [])
        assert errors[0]["code"] == "FORBIDDEN"

    def test_shape_b_404(self):
        errors = wa.map_error_response(404, b'{"detail": "operation not found"}', [])
        assert errors[0]["code"] == "NOT_FOUND"

    def test_shape_c_domain_409_preserved(self):
        body = json.dumps(load_fixture("error_409_idempotency.json")).encode()
        errors = wa.map_error_response(409, body, [])
        # доменный код НЕ заменён общим CONFLICT
        assert errors[0]["code"] == "source_document_idempotency_conflict"
        assert "sha256:deadbeef" in errors[0]["message"]

    def test_shape_c_generic_idempotency(self):
        body = json.dumps({"detail": {"code": "idempotency_payload_conflict",
                                      "message": "Idempotency conflict: client_request_id 'x' reused"}}).encode()
        errors = wa.map_error_response(409, body, [])
        assert errors[0]["code"] == "idempotency_payload_conflict"

    def test_shape_d_pydantic_422(self):
        body = json.dumps(load_fixture("error_422_pydantic.json")).encode()
        errors = wa.map_error_response(422, body, [])
        assert errors[0]["code"] == "VALIDATION_ERROR"
        assert errors[0]["field"] == "lines.0.qty"
        assert errors[0]["details"]["type"] == "greater_than"

    def test_500(self):
        errors = wa.map_error_response(500, b'{"detail": "internal server error"}', [])
        assert errors[0]["code"] == "INTERNAL_SERVER_ERROR"

    def test_429(self):
        errors = wa.map_error_response(429, b'{"detail": "rate limit exceeded"}', [])
        assert errors[0]["code"] == "RATE_LIMIT_EXCEEDED"

    def test_empty_body(self):
        errors = wa.map_error_response(503, b"", [])
        assert errors[0]["code"] == "HTTP_503"

    def test_invalid_json(self):
        errors = wa.map_error_response(502, b"<html>Bad Gateway</html>", [])
        assert errors[0]["code"] == "INVALID_JSON"
        assert "Bad Gateway" in errors[0]["details"]["snippet"]

    def test_unknown_status_code_fallback(self):
        errors = wa.map_error_response(418, b'{"detail": "teapot"}', [])
        assert errors[0]["code"] == "HTTP_418"


class TestBusinessErrorsIn200:
    def test_errors_array_in_200_body_fails(self):
        import httpx
        from conftest import TEST_USER_TOKEN
        client = wa.SyncClient(
            {"SYNC_SERVER_BASE_URL": "https://sync.example.com",
             "SYNC_SERVER_USER_TOKEN": TEST_USER_TOKEN},
            transport=httpx.MockTransport(lambda r: httpx.Response(
                200, json={"errors": [{"code": "business_fail", "message": "доменная ошибка"}]})),
            retry_backoff=(0.0, 0.0),
        )
        status, payload, errors = client.request("GET", "/api/v1/health", with_auth=False)
        assert status == 200 and payload is None
        assert errors[0]["code"] == "business_fail"
