# -*- coding: utf-8 -*-
"""Тесты CLI-клиента: конверт, конфигурация, команды, сетевые сбои.

Все HTTP-вызовы подменены httpx.MockTransport — сеть и production не используются.
"""
import json
import os
import types

import httpx
import pytest

import warehouse_api as wa
from conftest import TEST_USER_TOKEN, load_fixture


def args_ns(**kwargs):
    defaults = dict(
        updated_after=None, limit=1000, query=None, category_id=None, site_id=None,
        page=1, page_size=20, item_id=None, search=None, only_positive=False,
        draft_id=None, input=None, client_request_id=None, status="draft",
        line_number=None, qty=None, comment=None, batch=None,
        file=None, cases_dir=None, sha256=None, case_id=None, state=None,
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


# ---------------------------------------------------------------- конфигурация

class TestConfig:
    def test_parse_env_file(self):
        text = (
            "# комментарий\n"
            "SYNC_SERVER_BASE_URL=https://sync.example.com\n"
            "SYNC_SERVER_USER_TOKEN='abc-123'\n"
            "export SYNC_SERVER_DEVICE_TOKEN=\"def-456\"\n"
            "\n"
            "malformed line without equals\n"
        )
        cfg = wa.parse_env_file(text)
        assert cfg["SYNC_SERVER_BASE_URL"] == "https://sync.example.com"
        assert cfg["SYNC_SERVER_USER_TOKEN"] == "abc-123"
        assert cfg["SYNC_SERVER_DEVICE_TOKEN"] == "def-456"
        assert "malformed line without equals" not in cfg

    def test_missing_base_url(self):
        with pytest.raises(wa.ConfigError) as exc:
            wa.SyncClient({"SYNC_SERVER_USER_TOKEN": TEST_USER_TOKEN})
        assert exc.value.code == "CONFIG_MISSING"

    def test_insecure_http_forbidden_without_flag(self):
        with pytest.raises(wa.ConfigError) as exc:
            wa.SyncClient({
                "SYNC_SERVER_BASE_URL": "http://192.168.10.20:8000",
                "SYNC_SERVER_USER_TOKEN": TEST_USER_TOKEN,
            })
        assert exc.value.code == "INSECURE_URL_FORBIDDEN"

    def test_insecure_http_forbidden_for_public_host(self):
        with pytest.raises(wa.ConfigError) as exc:
            wa.SyncClient({
                "SYNC_SERVER_BASE_URL": "http://sync.example.com",
                "SYNC_SERVER_USER_TOKEN": TEST_USER_TOKEN,
                "SYNC_SERVER_ALLOW_INSECURE_LOCAL": "true",
            })
        assert exc.value.code == "INSECURE_URL_FORBIDDEN"

    def test_https_always_allowed(self, make_client):
        client = make_client(lambda r: httpx.Response(200, json={"status": "ok"}),
                           config={"SYNC_SERVER_BASE_URL": "https://sync.example.com",
                                   "SYNC_SERVER_USER_TOKEN": TEST_USER_TOKEN})
        data, warnings, errors = wa.cmd_health(client, args_ns())
        assert errors == [] and data == {"status": "ok"}

    def test_token_missing_refusal(self, make_client):
        client = make_client(lambda r: httpx.Response(200, json={}),
                           config={"SYNC_SERVER_BASE_URL": "https://sync.example.com"})
        with pytest.raises(wa.ConfigError) as exc:
            wa.cmd_whoami(client, args_ns())
        assert exc.value.code == "TOKEN_MISSING"

    @pytest.mark.skipif(os.name == "nt", reason="POSIX-ветка ACL")
    def test_acl_posix(self, tmp_path):
        path = tmp_path / "syncserver.env"
        path.write_text("A=1", encoding="utf-8")
        os.chmod(path, 0o644)
        safe, _ = wa.check_secrets_acl(path)
        assert not safe
        os.chmod(path, 0o600)
        safe, _ = wa.check_secrets_acl(path)
        assert safe

    def test_acl_missing_file(self, tmp_path):
        safe, detail = wa.check_secrets_acl(tmp_path / "nope.env")
        assert not safe and "не найден" in detail

    def test_parse_icacls_output(self):
        output = (
            "syncserver.env NT AUTHORITY\\SYSTEM:(I)(F)\n"
            "              COMP2\\User:(I)(F)\n"
            "Successfully processed 1 files; Failed processing 0 files\n"
        )
        safe, offenders = wa.parse_icacls_output(output, {"COMP2\\User", "NT AUTHORITY\\SYSTEM"})
        assert safe and offenders == []
        unsafe_output = output.replace("COMP2\\User:(I)(F)", "COMP2\\User:(I)(F)\n              BUILTIN\\Users:(I)(RX)")
        safe, offenders = wa.parse_icacls_output(unsafe_output, {"COMP2\\User", "NT AUTHORITY\\SYSTEM"})
        assert not safe and offenders == ["BUILTIN\\Users"]


# ---------------------------------------------------------------- чтение

class TestReadCommands:
    def test_health(self, make_client):
        def handler(request):
            assert request.url.path == "/api/v1/health"
            return httpx.Response(200, json={"status": "ok"}, headers={"X-Request-Id": "req-42"})
        client = make_client(handler)
        data, _, errors = wa.cmd_health(client, args_ns())
        assert errors == [] and data["status"] == "ok"
        assert client.last_request_id == "req-42"

    def test_whoami_sends_user_token(self, make_client):
        def handler(request):
            assert request.headers["X-User-Token"] == TEST_USER_TOKEN
            assert "X-Device-Token" in request.headers
            return httpx.Response(200, json=load_fixture("auth_me.json"))
        client = make_client(handler)
        data, _, errors = wa.cmd_whoami(client, args_ns())
        assert errors == []
        assert data["user"]["role"] == "storekeeper"

    def test_capabilities(self, make_client):
        client = make_client(lambda r: httpx.Response(200, json=load_fixture("auth_context.json")))
        data, _, errors = wa.cmd_capabilities(client, args_ns())
        assert errors == []
        assert data["permissions_summary"]["can_create_operations"] is True

    def test_sites_list(self, make_client):
        client = make_client(lambda r: httpx.Response(200, json=load_fixture("sites.json")))
        data, _, errors = wa.cmd_sites_list(client, args_ns())
        assert errors == []
        assert data["available_sites"][0]["name"] == "Угдан"

    def test_units_list(self, make_client):
        client = make_client(lambda r: httpx.Response(200, json=load_fixture("units.json")))
        data, _, errors = wa.cmd_units_list(client, args_ns())
        assert errors == [] and len(data["units"]) == 3

    def test_catalog_search_empty(self, make_client):
        client = make_client(lambda r: httpx.Response(200, json=load_fixture("catalog_search_empty.json")))
        data, warnings, errors = wa.cmd_catalog_search(client, args_ns(query="несуществующая"))
        assert errors == [] and data["total_count"] == 0
        assert any(w["code"] == "catalog_empty" for w in warnings)

    def test_catalog_search_ambiguous(self, make_client):
        client = make_client(lambda r: httpx.Response(200, json=load_fixture("catalog_search_many.json")))
        data, warnings, errors = wa.cmd_catalog_search(client, args_ns(query="подшипник 6205"))
        assert errors == [] and data["total_count"] == 3
        assert any(w["code"] == "catalog_ambiguous" for w in warnings)

    def test_catalog_get(self, make_client):
        def handler(request):
            assert request.url.path == "/api/v1/catalog/read/items/10"
            return httpx.Response(200, json=load_fixture("item_10.json"))
        client = make_client(handler)
        data, _, errors = wa.cmd_catalog_get(client, args_ns(item_id=10))
        assert errors == [] and data["name"] == "Подшипник 6205-2RS"

    def test_balances_default_site_from_config(self, make_client):
        seen = {}

        def handler(request):
            seen["site_id"] = request.url.params.get("site_id")
            return httpx.Response(200, json=load_fixture("balances_item10.json"))
        config = {
            "SYNC_SERVER_BASE_URL": "http://192.168.10.20:8000",
            "SYNC_SERVER_USER_TOKEN": TEST_USER_TOKEN,
            "SYNC_SERVER_ALLOW_INSECURE_LOCAL": "true",
            "SYNC_SERVER_SITE_ID": "1",
        }
        client = make_client(handler, config=config)
        data, _, errors = wa.cmd_catalog_balances(client, args_ns())
        assert errors == [] and seen["site_id"] == "1"


# ---------------------------------------------------------------- черновики

class TestDraftCommands:
    def test_draft_create_from_source_document(self, make_client, tmp_path):
        captured = {}

        def handler(request):
            captured["path"] = request.url.path
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=load_fixture("draft_created.json"))
        client = make_client(handler)
        input_file = tmp_path / "draft_request.json"
        input_file.write_text(json.dumps(load_fixture("draft_request_source.json")), encoding="utf-8")
        data, warnings, errors = wa.cmd_draft_create(client, args_ns(input=str(input_file)))
        assert errors == []
        assert captured["path"] == "/api/v1/operations/from-source-document"
        body = captured["body"]
        assert body["source_ref"] == "sha256:deadbeef"
        assert body["source_document_type"] == "ocr_scan"
        assert body["lines"][0]["source_item_name"] == "Подшипник 6205"
        # unresolved-строка не отправлена, но предупреждение есть
        assert len(body["lines"]) == 1
        assert any(w["code"] == "line_unresolved_skipped" for w in warnings)
        # notes собраны из документа
        assert "154" in body["notes"]
        # extra=forbid: никаких лишних полей
        assert set(body.keys()) <= {
            "operation_type", "site_id", "source_ref", "source_document_type",
            "source_document_date", "effective_at", "source_site_id", "destination_site_id",
            "issued_to_user_id", "issued_to_name", "issue_object_id",
            "issue_object_name_snapshot", "lines", "notes", "client_request_id",
        }

    def test_draft_create_generic_has_client_request_id(self, make_client, tmp_path):
        captured = {}

        def handler(request):
            captured["path"] = request.url.path
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=load_fixture("draft_created.json"))
        client = make_client(handler)
        input_file = tmp_path / "draft_request.json"
        input_file.write_text(json.dumps(load_fixture("draft_request_generic.json")), encoding="utf-8")
        data, warnings, errors = wa.cmd_draft_create(client, args_ns(input=str(input_file)))
        assert errors == []
        assert captured["path"] == "/api/v1/operations"
        assert captured["body"]["client_request_id"]
        assert captured["body"]["lines"][0]["comment"] == "Подшипник 6205"
        assert any(w["code"] == "idempotency_key" for w in warnings)

    def test_draft_create_all_lines_unresolved_refused(self, make_client, tmp_path):
        client = make_client(lambda r: httpx.Response(200, json={}))
        payload = {"operation_type": "RECEIVE", "site_id": 1,
                   "lines": [{"line_number": 1, "item_id": None, "qty": 5, "raw_name": "Что-то"}]}
        input_file = tmp_path / "draft_request.json"
        input_file.write_text(json.dumps(payload), encoding="utf-8")
        data, warnings, errors = wa.cmd_draft_create(client, args_ns(input=str(input_file)))
        assert data is None and errors and errors[0]["code"] == "VALIDATION_ERROR"

    def test_draft_create_adjustment_blocked(self, make_client, tmp_path):
        client = make_client(lambda r: httpx.Response(200, json={}))
        payload = {"operation_type": "ADJUSTMENT", "site_id": 1,
                   "lines": [{"line_number": 1, "item_id": 10, "qty": -5}]}
        input_file = tmp_path / "draft_request.json"
        input_file.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(wa.ConfigError) as exc:
            wa.cmd_draft_create(client, args_ns(input=str(input_file)))
        assert exc.value.code == "OPERATION_TYPE_NOT_ALLOWED"

    def test_draft_create_move_validation(self, make_client, tmp_path):
        client = make_client(lambda r: httpx.Response(200, json={}))
        payload = {"operation_type": "MOVE", "site_id": 1,
                   "lines": [{"line_number": 1, "item_id": 10, "qty": 5}]}
        input_file = tmp_path / "draft_request.json"
        input_file.write_text(json.dumps(payload), encoding="utf-8")
        data, _, errors = wa.cmd_draft_create(client, args_ns(input=str(input_file)))
        assert errors and errors[0]["field"] == "source_site_id/destination_site_id"

    def test_draft_create_duplicate_source_conflict_preserved(self, make_client, tmp_path):
        def handler(request):
            return httpx.Response(409, json=load_fixture("error_409_idempotency.json"))
        client = make_client(handler)
        input_file = tmp_path / "draft_request.json"
        input_file.write_text(json.dumps(load_fixture("draft_request_source.json")), encoding="utf-8")
        data, warnings, errors = wa.cmd_draft_create(client, args_ns(input=str(input_file)))
        assert data is None
        assert errors[0]["code"] == "source_document_idempotency_conflict"
        assert client.last_status == 409

    def test_draft_list_own(self, make_client):
        seen = {}

        def handler(request):
            if request.url.path == "/api/v1/auth/me":
                return httpx.Response(200, json=load_fixture("auth_me.json"))
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, json=load_fixture("operations_list_own.json"))
        client = make_client(handler)
        data, _, errors = wa.cmd_draft_list_own(client, args_ns())
        assert errors == []
        assert seen["params"]["created_by_user_id"] == "1fa85f64-5717-4562-b3fc-2c963f66afa6"
        assert seen["params"]["status"] == "draft"
        assert data["total_count"] == 1

    def test_draft_add_lines_merges_and_patches(self, make_client, tmp_path):
        calls = []

        def handler(request):
            calls.append((request.method, request.url.path,
                          json.loads(request.content) if request.content else None))
            if request.method == "GET":
                return httpx.Response(200, json=load_fixture("draft_receive.json"))
            return httpx.Response(200, json=load_fixture("draft_receive.json"))
        client = make_client(handler)
        input_file = tmp_path / "lines.json"
        input_file.write_text(json.dumps(load_fixture("add_lines_input.json")), encoding="utf-8")
        data, warnings, errors = wa.cmd_draft_add_lines(
            client, args_ns(draft_id="3fa85f64-5717-4562-b3fc-2c963f66afa6", input=str(input_file)))
        assert errors == []
        patch = [c for c in calls if c[0] == "PATCH"][0]
        body = patch[2]
        assert body["expected_version"] == 2
        # 2 существующие + 1 добавленная (unresolved пропущена)
        assert len(body["lines"]) == 3
        new_line = body["lines"][-1]
        assert new_line["line_number"] == 3 and new_line["item_id"] == 30
        # raw_name сохранён
        assert new_line["comment"] == "Сальник 25x40x7"
        assert any(w["code"] == "line_skipped" for w in warnings)
        assert any(w["code"] == "lines_replaced" for w in warnings)

    def test_draft_add_lines_refused_for_submitted(self, make_client, tmp_path):
        submitted = load_fixture("draft_receive.json")
        submitted["status"] = "submitted"
        client = make_client(lambda r: httpx.Response(200, json=submitted))
        input_file = tmp_path / "lines.json"
        input_file.write_text(json.dumps(load_fixture("add_lines_input.json")), encoding="utf-8")
        data, _, errors = wa.cmd_draft_add_lines(
            client, args_ns(draft_id="3fa85f64-5717-4562-b3fc-2c963f66afa6", input=str(input_file)))
        assert data is None and errors[0]["code"] == "OPERATION_IN_WRONG_STATE"

    def test_draft_update_line_qty(self, make_client):
        calls = []

        def handler(request):
            calls.append((request.method, json.loads(request.content) if request.content else None))
            return httpx.Response(200, json=load_fixture("draft_receive.json"))
        client = make_client(handler)
        data, _, errors = wa.cmd_draft_update_line(
            client, args_ns(draft_id="3fa85f64-5717-4562-b3fc-2c963f66afa6", line_number=2, qty="70"))
        assert errors == []
        patch_body = [c[1] for c in calls if c[0] == "PATCH"][0]
        line2 = [l for l in patch_body["lines"] if l["line_number"] == 2][0]
        assert line2["qty"] == "70"
        line1 = [l for l in patch_body["lines"] if l["line_number"] == 1][0]
        assert line1["qty"] == 5

    def test_draft_update_line_not_found(self, make_client):
        client = make_client(lambda r: httpx.Response(200, json=load_fixture("draft_receive.json")))
        data, _, errors = wa.cmd_draft_update_line(
            client, args_ns(draft_id="3fa85f64-5717-4562-b3fc-2c963f66afa6", line_number=99, qty="5"))
        assert data is None and errors[0]["code"] == "NOT_FOUND"

    def test_draft_validate_receive(self, make_client):
        def handler(request):
            path = request.url.path
            if path.endswith("/operations/3fa85f64-5717-4562-b3fc-2c963f66afa6"):
                return httpx.Response(200, json=load_fixture("draft_receive.json"))
            if path.endswith("/catalog/read/items/10"):
                return httpx.Response(200, json=load_fixture("item_10.json"))
            if path.endswith("/catalog/read/items/20"):
                item = load_fixture("item_10.json")
                item["id"] = 20
                item["name"] = "Шайба М12"
                return httpx.Response(200, json=item)
            return httpx.Response(404, json={"detail": "not found"})
        client = make_client(handler)
        data, warnings, errors = wa.cmd_draft_validate(
            client, args_ns(draft_id="3fa85f64-5717-4562-b3fc-2c963f66afa6"))
        assert errors == []
        assert data["valid"] is True
        assert data["lines_count"] == 2
        assert data["validation_scope"] == "local"

    def test_draft_validate_unresolved_item(self, make_client):
        draft = load_fixture("draft_receive.json")
        draft["lines"][1]["item_id"] = None
        draft["lines"][1]["resolved_item_id"] = None

        def handler(request):
            if "/catalog/read/items/10" in request.url.path:
                return httpx.Response(200, json=load_fixture("item_10.json"))
            return httpx.Response(200, json=draft)
        client = make_client(handler)
        data, _, errors = wa.cmd_draft_validate(
            client, args_ns(draft_id="3fa85f64-5717-4562-b3fc-2c963f66afa6"))
        assert errors == []
        assert data["valid"] is False
        assert data["unresolved_lines"] == [2]


# ---------------------------------------------------------------- сеть

class TestNetwork:
    def test_timeout_retries_get(self, make_client):
        attempts = []

        def handler(request):
            attempts.append(1)
            if len(attempts) < 3:
                raise httpx.ConnectTimeout("timed out")
            return httpx.Response(200, json={"status": "ok"})
        client = make_client(handler)
        data, _, errors = wa.cmd_health(client, args_ns())
        assert errors == [] and len(attempts) == 3

    def test_no_retry_for_post(self, make_client, tmp_path):
        attempts = []

        def handler(request):
            attempts.append(1)
            raise httpx.ConnectError("connection refused")
        client = make_client(handler)
        input_file = tmp_path / "draft_request.json"
        input_file.write_text(json.dumps(load_fixture("draft_request_generic.json")), encoding="utf-8")
        with pytest.raises(httpx.ConnectError):
            wa.cmd_draft_create(client, args_ns(input=str(input_file)))
        assert len(attempts) == 1

    def test_invalid_json_response(self, make_client):
        client = make_client(lambda r: httpx.Response(200, content=b"<html>proxy error</html>"))
        data, _, errors = wa.cmd_health(client, args_ns())
        assert data is None and errors[0]["code"] == "INVALID_JSON"

    def test_classify_network_errors(self):
        code, _ = wa.classify_network_error(httpx.ConnectError("[Errno 111] Connection refused"))
        assert code == "CONNECT_REFUSED"
        code, _ = wa.classify_network_error(httpx.ConnectError("[Errno -2] Name or service not known"))
        assert code == "DNS_ERROR"
        code, _ = wa.classify_network_error(httpx.ReadTimeout("timeout"))
        assert code == "TIMEOUT"


# ---------------------------------------------------------------- дело (case)

class TestCaseCommands:
    def test_case_init_and_duplicate(self, tmp_path):
        source = tmp_path / "invoice.pdf"
        source.write_bytes(b"%PDF-1.4 fake")
        cases_dir = tmp_path / "cases"
        a = args_ns(file=str(source), cases_dir=str(cases_dir))
        data, _, errors = wa.cmd_case_init(None, a)
        assert errors == [] and data["duplicate"] is False
        assert len(data["sha256"]) == 64
        state = json.loads((cases_dir / data["case_id"] / "case_state.json").read_text(encoding="utf-8"))
        assert state["state"] == "RECEIVED"
        assert (cases_dir / data["case_id"] / "source" / "invoice.pdf").is_file()
        # повторная отправка того же файла — дубликат, второе дело не создаётся
        data2, _, errors2 = wa.cmd_case_init(None, a)
        assert errors2 == [] and data2["duplicate"] is True
        assert data2["case_id"] == data["case_id"]
        assert len(list(cases_dir.iterdir())) == 1

    def test_case_find(self, tmp_path):
        source = tmp_path / "doc.jpg"
        source.write_bytes(b"jpeg-data")
        cases_dir = tmp_path / "cases"
        data, _, _ = wa.cmd_case_init(None, args_ns(file=str(source), cases_dir=str(cases_dir)))
        found, _, errors = wa.cmd_case_find(None, args_ns(sha256=data["sha256"], cases_dir=str(cases_dir)))
        assert errors == [] and found["found"] and found["matches"][0]["case_id"] == data["case_id"]
        not_found, _, _ = wa.cmd_case_find(None, args_ns(sha256="0" * 64, cases_dir=str(cases_dir)))
        assert not_found["found"] is False

    def test_case_set_state_and_draft_link(self, tmp_path):
        source = tmp_path / "doc.jpg"
        source.write_bytes(b"jpeg-data")
        cases_dir = tmp_path / "cases"
        data, _, _ = wa.cmd_case_init(None, args_ns(file=str(source), cases_dir=str(cases_dir)))
        updated, _, errors = wa.cmd_case_set_state(None, args_ns(
            case_id=data["case_id"], state="DRAFT_READY",
            draft_id="3fa85f64-5717-4562-b3fc-2c963f66afa6", cases_dir=str(cases_dir)))
        assert errors == []
        assert updated["state"] == "DRAFT_READY"
        assert updated["draft_id"] == "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        with pytest.raises(wa.ConfigError):
            wa.cmd_case_set_state(None, args_ns(case_id=data["case_id"], state="BOGUS", cases_dir=str(cases_dir)))


# ---------------------------------------------------------------- CLI end-to-end

class TestCliEnvelope:
    def _run_cli(self, monkeypatch, capsys, transport_handler, argv, secrets_file):
        import warehouse_api

        original = warehouse_api.SyncClient

        def factory(config):
            return original(config, transport=httpx.MockTransport(transport_handler), retry_backoff=(0.0, 0.0))

        monkeypatch.setattr(warehouse_api, "SyncClient", factory)
        code = warehouse_api.main(["--secrets-path", str(secrets_file)] + argv)
        out = capsys.readouterr().out
        return code, json.loads(out)

    def test_cli_health_envelope(self, monkeypatch, capsys, secrets_file):
        code, env = self._run_cli(
            monkeypatch, capsys,
            lambda r: httpx.Response(200, json={"status": "ok"}, headers={"X-Request-Id": "req-1"}),
            ["health"], secrets_file)
        assert code == 0
        assert env["ok"] is True
        assert env["command"] == "health"
        assert env["request_id"] == "req-1"
        assert env["status_code"] == 200
        assert env["data"] == {"status": "ok"}
        assert env["warnings"] == [] and env["errors"] == []

    def test_cli_error_envelope_401(self, monkeypatch, capsys, secrets_file):
        code, env = self._run_cli(
            monkeypatch, capsys,
            lambda r: httpx.Response(401, json={"detail": "invalid X-User-Token"}),
            ["whoami"], secrets_file)
        assert code == 1
        assert env["ok"] is False
        assert env["status_code"] == 401
        assert env["errors"][0]["code"] == "UNAUTHORIZED"
        assert TEST_USER_TOKEN not in json.dumps(env)

    def test_cli_network_error_exit_code(self, monkeypatch, capsys, secrets_file):
        def handler(request):
            raise httpx.ConnectError("[Errno 111] Connection refused")
        code, env = self._run_cli(monkeypatch, capsys, handler, ["health"], secrets_file)
        assert code == 3
        assert env["errors"][0]["code"] == "CONNECT_REFUSED"

    def test_cli_config_check_no_secrets_leak(self, capsys, secrets_file):
        code = wa.main(["--secrets-path", str(secrets_file), "config", "check"])
        out = capsys.readouterr().out
        env = json.loads(out)
        assert code == 0 and env["ok"] is True
        assert env["data"]["user_token_present"] is True
        assert env["data"]["secrets_acl_safe"] is True
        assert TEST_USER_TOKEN not in out

    def test_cli_acl_refusal(self, capsys, tmp_path):
        bad = tmp_path / "syncserver.env"
        bad.write_text(
            "SYNC_SERVER_BASE_URL=http://192.168.10.20:8000\n"
            f"SYNC_SERVER_USER_TOKEN={TEST_USER_TOKEN}\n"
            "SYNC_SERVER_ALLOW_INSECURE_LOCAL=true\n",
            encoding="utf-8")
        if os.name != "nt":
            os.chmod(bad, 0o644)
            code = wa.main(["--secrets-path", str(bad), "health"])
            env = json.loads(capsys.readouterr().out)
            assert code == 2
            assert env["errors"][0]["code"] == "SECRETS_ACL_UNSAFE"
