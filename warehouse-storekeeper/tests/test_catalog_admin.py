# -*- coding: utf-8 -*-
"""Тесты guarded-режима каталога: catalog create/update, admin search, дубликаты.

HTTP подменён MockTransport — без сети и production.
CATALOG_ACCESS_MODE=chief_guarded, CATALOG_CREATE_REQUIRE_CONFIRMATION=true.
"""
import json
import types

import httpx
import pytest

import warehouse_api as wa
from conftest import TEST_USER_TOKEN


def admin_config(**overrides):
    cfg = {
        "SYNC_SERVER_BASE_URL": "https://sync.example.com",
        "SYNC_SERVER_USER_TOKEN": TEST_USER_TOKEN,
        "CATALOG_ACCESS_MODE": "chief_guarded",
        "CATALOG_CREATE_REQUIRE_CONFIRMATION": "true",
        "CATALOG_MERGE_ENABLED": "false",
    }
    cfg.update(overrides)
    return cfg


def admin_client(handler, **overrides):
    transport = httpx.MockTransport(handler)
    return wa.SyncClient(admin_config(**overrides), transport=transport, retry_backoff=(0.0, 0.0))


def args_ns(**kwargs):
    d = dict(input=None, confirmed=False, item_id=None, query=None, page=1, page_size=50)
    d.update(kwargs)
    return types.SimpleNamespace(**d)


# ---------------------------------------------------------------- guarded config

class TestCatalogAdminConfig:
    def test_read_only_mode_blocks_create(self):
        client = admin_client(lambda r: httpx.Response(200, json={}), CATALOG_ACCESS_MODE="read_only")
        with pytest.raises(wa.ConfigError) as exc:
            wa._require_catalog_admin(client)
        assert exc.value.code == "CATALOG_ACCESS_DISABLED"

    def test_merge_enabled_true_is_fatal(self):
        client = admin_client(lambda r: httpx.Response(200, json={}), CATALOG_MERGE_ENABLED="true")
        with pytest.raises(wa.ConfigError) as exc:
            wa._require_catalog_admin(client)
        assert exc.value.code == "CATALOG_MERGE_FORBIDDEN"

    def test_confirmation_required(self):
        client = admin_client(lambda r: httpx.Response(200, json={}), CATALOG_CREATE_REQUIRE_CONFIRMATION="false")
        with pytest.raises(wa.ConfigError) as exc:
            wa._require_confirmation(client)
        assert exc.value.code == "CONFIRMATION_DISABLED"


# ---------------------------------------------------------------- create без подтверждения

class TestCatalogCreateConfirmation:
    def test_unconfirmed_returns_confirmation_required(self, tmp_path):
        def handler(request):
            path = request.url.path
            if "admin/items" in path:
                return httpx.Response(200, json={"items": []})
            return httpx.Response(200, json={"items": []})

        client = admin_client(handler)
        inp = tmp_path / "req.json"
        inp.write_text(json.dumps({"name": "Подшипник новый", "unit_id": 1}), encoding="utf-8")
        data, warnings, errors = wa.cmd_catalog_create(client, args_ns(input=str(inp), confirmed=False))
        assert data is None and errors[0]["code"] == "CONFIRMATION_REQUIRED"

    def test_confirmed_without_dupes_creates(self, tmp_path):
        seen = {}

        def handler(request):
            path = request.url.path
            if "admin/items" in path and request.method == "POST":
                seen["created"] = json.loads(request.content)
                return httpx.Response(200, json={"id": 99, "name": "Подшипник новый"})
            return httpx.Response(200, json={"items": []})

        client = admin_client(handler)
        inp = tmp_path / "req.json"
        inp.write_text(json.dumps({"name": "Подшипник новый", "unit_id": 1, "sku": "PN-001"}), encoding="utf-8")
        data, warnings, errors = wa.cmd_catalog_create(client, args_ns(input=str(inp), confirmed=True))
        assert errors == [] and data["id"] == 99
        assert seen["created"]["name"] == "Подшипник новый"
        assert any(w["code"] == "catalog_item_created" for w in warnings)


# ---------------------------------------------------------------- дубликаты

class TestDuplicateBlocking:
    def test_exact_name_duplicate_blocks(self, tmp_path):
        def handler(request):
            path = request.url.path
            if "catalog/read/items" in path and "admin" not in path:
                return httpx.Response(200, json={"items": [{"id": 10, "name": "Подшипник новый"}]})
            return httpx.Response(200, json={"items": []})

        client = admin_client(handler)
        inp = tmp_path / "req.json"
        inp.write_text(json.dumps({"name": "Подшипник новый", "unit_id": 1}), encoding="utf-8")
        data, warnings, errors = wa.cmd_catalog_create(client, args_ns(input=str(inp), confirmed=True))
        assert errors[0]["code"] == "DUPLICATE_CANDIDATES"
        assert any(w["code"] == "duplicate_exact_name" for w in warnings)

    def test_sku_match_blocks(self, tmp_path):
        def handler(request):
            path = request.url.path
            if "admin/items" in path or "catalog/read/items" in path:
                return httpx.Response(200, json={
                    "items": [{"id": 5, "sku": "PN-001", "name": "Старый подшипник"}]
                })
            return httpx.Response(200, json={"items": []})

        client = admin_client(handler)
        inp = tmp_path / "req.json"
        inp.write_text(json.dumps({"name": "Подшипник новый", "unit_id": 1, "sku": "PN-001"}), encoding="utf-8")
        data, warnings, errors = wa.cmd_catalog_create(client, args_ns(input=str(inp), confirmed=True))
        assert errors[0]["code"] == "DUPLICATE_CANDIDATES"
        assert any(w["code"] == "duplicate_sku" for w in warnings)

    def test_similar_name_blocks(self, tmp_path):
        def handler(request):
            path = request.url.path
            if "admin/items" in path:
                return httpx.Response(200, json={
                    "items": [{"id": 11, "name": "Подшипник-новый-модельный", "is_active": False}]
                })
            return httpx.Response(200, json={"items": []})

        client = admin_client(handler)
        inp = tmp_path / "req.json"
        inp.write_text(json.dumps({"name": "Подшипник новый модельный", "unit_id": 1}), encoding="utf-8")
        data, warnings, errors = wa.cmd_catalog_create(client, args_ns(input=str(inp), confirmed=True))
        assert errors[0]["code"] == "DUPLICATE_CANDIDATES"
        assert any(w["code"] == "duplicate_similar" for w in warnings)


# ---------------------------------------------------------------- запрещённые операции

class TestForbiddenCatalogOps:
    def test_merge_still_forbidden_in_allowlist(self):
        client = admin_client(lambda r: httpx.Response(200, json={}))
        with pytest.raises(wa.EndpointNotAllowed):
            client.request("POST", "/api/v1/catalog/admin/items/merge", json_body={"source_item_id": 1, "target_item_id": 2})

    def test_delete_still_forbidden(self):
        client = admin_client(lambda r: httpx.Response(200, json={}))
        with pytest.raises(wa.EndpointNotAllowed):
            client.request("DELETE", "/api/v1/catalog/admin/items/1")

    def test_categories_create_not_allowed(self):
        client = admin_client(lambda r: httpx.Response(200, json={}))
        with pytest.raises(wa.EndpointNotAllowed):
            client.request("POST", "/api/v1/catalog/admin/categories", json_body={"name": "Test"})

    def test_submit_still_forbidden(self):
        client = admin_client(lambda r: httpx.Response(200, json={}))
        with pytest.raises(wa.EndpointNotAllowed):
            client.request("POST", "/api/v1/operations/3fa85f64-5717-4562-b3fc-2c963f66afa6/submit", json_body={"submit": True})

    def test_admin_users_blocked(self):
        client = admin_client(lambda r: httpx.Response(200, json={}))
        with pytest.raises(wa.EndpointNotAllowed):
            client.request("GET", "/api/v1/admin/users")


# ---------------------------------------------------------------- catalog update

class TestCatalogUpdate:
    def test_deactivation_blocked(self, tmp_path):
        inp = tmp_path / "upd.json"
        inp.write_text(json.dumps({"is_active": False}), encoding="utf-8")
        client = admin_client(lambda r: httpx.Response(200, json={"items": []}))
        data, _, errors = wa.cmd_catalog_update(client, args_ns(item_id=99, input=str(inp)))
        assert errors[0]["code"] == "DEACTIVATION_FORBIDDEN"

    def test_update_name_works(self, tmp_path):
        seen = {}

        def handler(request):
            path = request.url.path
            if request.method == "PATCH":
                seen["patch"] = json.loads(request.content)
                return httpx.Response(200, json={"id": 99, "name": "New Name"})
            return httpx.Response(200, json={"id": 99, "name": "Old Name", "is_active": True})

        client = admin_client(handler)
        inp = tmp_path / "upd.json"
        inp.write_text(json.dumps({"name": "New Name"}), encoding="utf-8")
        data, _, errors = wa.cmd_catalog_update(client, args_ns(item_id=99, input=str(inp)))
        assert errors == [] and seen["patch"]["name"] == "New Name"

    def test_unit_id_change_warned_and_ignored(self, tmp_path):
        seen = {}

        def handler(request):
            path = request.url.path
            if request.method == "PATCH":
                seen["patch"] = json.loads(request.content)
                return httpx.Response(200, json={"id": 99})
            return httpx.Response(200, json={"id": 99, "is_active": True})

        client = admin_client(handler)
        inp = tmp_path / "upd.json"
        inp.write_text(json.dumps({"name": "X", "unit_id": 5}), encoding="utf-8")
        data, warnings, errors = wa.cmd_catalog_update(client, args_ns(item_id=99, input=str(inp)))
        assert errors == []
        assert "unit_id" not in seen["patch"]
        assert any(w["code"] == "update_limited" for w in warnings)


# ---------------------------------------------------------------- admin search

class TestCatalogAdminSearch:
    def test_admin_search_includes_inactive(self):
        def handler(request):
            assert "admin/items" in request.url.path
            return httpx.Response(200, json={"items": [{"id": 1, "is_active": False, "name": "Archive"}]})

        client = admin_client(handler)
        data, _, errors = wa.cmd_catalog_admin_search(client, args_ns(query="Archive"))
        assert errors == [] and data["items"][0]["is_active"] is False

    def test_admin_get(self):
        client = admin_client(
            lambda r: httpx.Response(200, json={"id": 42, "is_active": False, "name": "Hidden"}))
        data, _, errors = wa.cmd_catalog_admin_get(client, args_ns(item_id=42))
        assert errors == [] and data["name"] == "Hidden"


# ---------------------------------------------------------------- categories read

class TestCategoriesRead:
    def test_categories_read(self):
        client = admin_client(lambda r: httpx.Response(200, json={"categories": [{"id": 1, "name": "Подшипники"}]}))
        data, _, errors = wa.cmd_catalog_categories(client, args_ns(query="подш"))
        assert errors == [] and data["categories"][0]["name"] == "Подшипники"


# ---------------------------------------------------------------- error on missing name

class TestValidation:
    def test_create_without_name_fails(self, tmp_path):
        inp = tmp_path / "req.json"
        inp.write_text(json.dumps({"unit_id": 1}), encoding="utf-8")
        client = admin_client(lambda r: httpx.Response(200, json={"items": []}))
        data, _, errors = wa.cmd_catalog_create(client, args_ns(input=str(inp), confirmed=True))
        assert errors[0]["code"] == "VALIDATION_ERROR"
