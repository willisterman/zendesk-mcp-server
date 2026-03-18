"""Tests for the unified search_tickets tool — no duplicate names, correct query building, proper routing."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest


# Patch env vars before importing server (it reads them at module level)
@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "test")
    monkeypatch.setenv("ZENDESK_EMAIL", "test@example.com")
    monkeypatch.setenv("ZENDESK_API_KEY", "fake-token")


# ---------------------------------------------------------------------------
# Helpers to import server components with mocked Zenpy
# ---------------------------------------------------------------------------

@pytest.fixture
def server_module(_mock_env):
    """Import server.py with Zenpy mocked out so no real connection is made."""
    with patch.dict(os.environ, {
        "ZENDESK_SUBDOMAIN": "test",
        "ZENDESK_EMAIL": "test@example.com",
        "ZENDESK_API_KEY": "fake-token",
    }):
        with patch("zendesk_mcp_server.zendesk_client.Zenpy"):
            import importlib
            import zendesk_mcp_server.server as srv
            importlib.reload(srv)
            yield srv


@pytest.fixture
def server_with_custom_fields(_mock_env, monkeypatch):
    """Import server.py with ZENDESK_CUSTOM_FIELDS configured."""
    monkeypatch.setenv("ZENDESK_CUSTOM_FIELDS", json.dumps({
        "product": 12345,
        "region": 67890,
    }))
    with patch("zendesk_mcp_server.zendesk_client.Zenpy"):
        import importlib
        import zendesk_mcp_server.server as srv
        importlib.reload(srv)
        yield srv


# ===========================================================================
# 1. No duplicate tool names
# ===========================================================================

class TestNoDuplicateToolNames:
    async def test_tool_names_are_unique(self, server_module):
        tools = await server_module.handle_list_tools()
        names = [t.name for t in tools]
        assert len(names) == len(set(names)), f"Duplicate tool names found: {[n for n in names if names.count(n) > 1]}"

    async def test_search_tickets_appears_exactly_once(self, server_module):
        tools = await server_module.handle_list_tools()
        search_tools = [t for t in tools if t.name == "search_tickets"]
        assert len(search_tools) == 1


# ===========================================================================
# 2. Schema generation
# ===========================================================================

class TestSchemaGeneration:
    async def test_schema_includes_query_and_structured_params(self, server_module):
        tools = await server_module.handle_list_tools()
        search_tool = next(t for t in tools if t.name == "search_tickets")
        props = search_tool.inputSchema["properties"]

        assert "query" in props
        assert "organization_name" in props
        assert "created_after" in props
        assert "created_before" in props
        assert "status" in props
        assert "sort_by" in props
        assert "sort_order" in props

    async def test_schema_has_no_required_fields(self, server_module):
        tools = await server_module.handle_list_tools()
        search_tool = next(t for t in tools if t.name == "search_tickets")
        assert search_tool.inputSchema.get("required") == []

    async def test_schema_includes_custom_fields(self, server_with_custom_fields):
        tools = await server_with_custom_fields.handle_list_tools()
        search_tool = next(t for t in tools if t.name == "search_tickets")
        props = search_tool.inputSchema["properties"]

        assert "product" in props
        assert "region" in props


# ===========================================================================
# 3. Query building (client-level)
# ===========================================================================

class TestQueryBuilding:
    """Test the ZendeskClient.search_tickets query construction by intercepting the URL."""

    def _make_client(self):
        with patch("zendesk_mcp_server.zendesk_client.Zenpy"):
            from zendesk_mcp_server.zendesk_client import ZendeskClient
            return ZendeskClient(subdomain="test", email="a@b.com", token="tok")

    def _capture_query(self, client, **kwargs):
        """Call search_tickets and capture the query param sent to the API."""
        import urllib.parse
        captured = {}

        def mock_urlopen(req):
            url = req.full_url if hasattr(req, 'full_url') else req.get_full_url()
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            captured["query"] = params.get("query", [""])[0]
            # Return a mock response
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"results": [], "count": 0}).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            client.search_tickets(**kwargs)

        return captured["query"]

    def test_raw_query_only(self):
        client = self._make_client()
        q = self._capture_query(client, query="status:open reporting")
        assert "status:open reporting" in q
        assert "type:ticket" in q

    def test_structured_params_only(self):
        client = self._make_client()
        q = self._capture_query(client, organization_name="Acme Corp", status="open")
        assert 'organization:"Acme Corp"' in q
        assert "status:open" in q
        assert "type:ticket" in q

    def test_combined_query_and_structured(self):
        client = self._make_client()
        q = self._capture_query(client, query="priority:urgent", organization_name="Acme Corp")
        assert "priority:urgent" in q
        assert 'organization:"Acme Corp"' in q
        assert "type:ticket" in q

    def test_no_params_defaults_to_type_ticket(self):
        client = self._make_client()
        q = self._capture_query(client)
        assert q == "type:ticket"

    def test_custom_fields_in_query(self):
        client = self._make_client()
        q = self._capture_query(client, custom_fields={12345: "Widget"})
        assert 'custom_field_12345:"Widget"' in q

    def test_no_duplicate_type_ticket(self):
        client = self._make_client()
        q = self._capture_query(client, query="type:ticket status:open")
        assert q.count("type:ticket") == 1

    def test_date_filters(self):
        client = self._make_client()
        q = self._capture_query(client, created_after="2024-01-01", created_before="2024-12-31")
        assert "created>=2024-01-01" in q
        assert "created<=2024-12-31" in q

    def test_org_name_with_spaces_is_quoted(self):
        client = self._make_client()
        q = self._capture_query(client, organization_name="My Organisation Name")
        assert 'organization:"My Organisation Name"' in q


# ===========================================================================
# 4. Handler routing
# ===========================================================================

class TestHandlerRouting:
    """Test that the server handler passes all params through to the client."""

    async def test_query_only_handler(self, server_module):
        mock_result = {"tickets": [], "total_count": 0, "page": 1, "per_page": 25,
                       "query": "type:ticket status:open", "sort_by": "updated_at",
                       "sort_order": "desc", "has_more": False, "next_page": None,
                       "previous_page": None}
        with patch.object(server_module.zendesk_client, "search_tickets", return_value=mock_result) as mock_search:
            result = await server_module.handle_call_tool("search_tickets", {"query": "status:open"})
            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["query"] == "status:open"

    async def test_structured_only_handler(self, server_module):
        mock_result = {"tickets": [], "total_count": 0, "page": 1, "per_page": 25,
                       "query": "type:ticket", "sort_by": "updated_at",
                       "sort_order": "desc", "has_more": False, "next_page": None,
                       "previous_page": None}
        with patch.object(server_module.zendesk_client, "search_tickets", return_value=mock_result) as mock_search:
            result = await server_module.handle_call_tool("search_tickets", {
                "organization_name": "Acme",
                "status": "open",
            })
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["organization_name"] == "Acme"
            assert call_kwargs["status"] == "open"
            assert call_kwargs["query"] is None

    async def test_combined_handler(self, server_module):
        mock_result = {"tickets": [], "total_count": 0, "page": 1, "per_page": 25,
                       "query": "type:ticket", "sort_by": "updated_at",
                       "sort_order": "desc", "has_more": False, "next_page": None,
                       "previous_page": None}
        with patch.object(server_module.zendesk_client, "search_tickets", return_value=mock_result) as mock_search:
            result = await server_module.handle_call_tool("search_tickets", {
                "query": "priority:high",
                "organization_name": "Acme",
                "created_after": "2024-01-01",
            })
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["query"] == "priority:high"
            assert call_kwargs["organization_name"] == "Acme"
            assert call_kwargs["created_after"] == "2024-01-01"

    async def test_custom_field_mapping_in_handler(self, server_with_custom_fields):
        mock_result = {"tickets": [], "total_count": 0, "page": 1, "per_page": 25,
                       "query": "type:ticket", "sort_by": "updated_at",
                       "sort_order": "desc", "has_more": False, "next_page": None,
                       "previous_page": None}
        with patch.object(server_with_custom_fields.zendesk_client, "search_tickets", return_value=mock_result) as mock_search:
            result = await server_with_custom_fields.handle_call_tool("search_tickets", {
                "product": "Widget",
                "region": "EMEA",
            })
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["custom_fields"] == {12345: "Widget", 67890: "EMEA"}

    async def test_no_args_handler(self, server_module):
        mock_result = {"tickets": [], "total_count": 0, "page": 1, "per_page": 25,
                       "query": "type:ticket", "sort_by": "updated_at",
                       "sort_order": "desc", "has_more": False, "next_page": None,
                       "previous_page": None}
        with patch.object(server_module.zendesk_client, "search_tickets", return_value=mock_result) as mock_search:
            result = await server_module.handle_call_tool("search_tickets", None)
            mock_search.assert_called_once()
