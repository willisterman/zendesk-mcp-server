# Zendesk MCP Server - Architecture Documentation

This document provides comprehensive technical documentation of the Zendesk MCP server codebase.

## Project Overview

**Project Name:** zendesk-mcp-server
**Version:** 0.1.0
**License:** Apache 2.0
**Python Version:** >=3.12

A Model Context Protocol (MCP) server providing integration with Zendesk for ticket management, comments, and Help Center knowledge base access.

---

## Source Files

| File | Lines | Purpose |
|------|-------|---------|
| `src/zendesk_mcp_server/__init__.py` | 11 | Package initialization, exports `main()` and `server` |
| `src/zendesk_mcp_server/server.py` | 411 | MCP server implementation (tools, prompts, resources) |
| `src/zendesk_mcp_server/zendesk_client.py` | 283 | Zendesk API client using Zenpy + direct REST |

---

## MCP Capabilities

### Tools (10 total)

| Tool | Required Params | Optional Params | Client Method |
|------|-----------------|-----------------|---------------|
| `get_ticket` | `ticket_id` (int) | - | `get_ticket()` |
| `get_tickets` | - | `page`, `per_page`, `sort_by`, `sort_order` | `get_tickets()` |
| `get_ticket_comments` | `ticket_id` (int) | - | `get_ticket_comments()` |
| `create_ticket` | `subject`, `description` | `requester_id`, `assignee_id`, `priority`, `type`, `tags`, `custom_fields` | `create_ticket()` |
| `create_ticket_comment` | `ticket_id`, `comment` | `public` (default: true) | `post_comment()` |
| `update_ticket` | `ticket_id` | `subject`, `status`, `priority`, `type`, `assignee_id`, `requester_id`, `tags`, `custom_fields`, `due_at` | `update_ticket()` |
| `search_organizations` | `name` | - | `search_organizations()` |
| `get_organization` | `organization_id` (int) | - | `get_organization()` |
| `search_tickets` | - | `organization_name`, `created_after`, `created_before`, `status`, `page`, `per_page` | `search_tickets()` |
| `clear_organization_cache` | - | - | `clear_organization_cache()` |

### Prompts (2 total)

| Prompt | Required Argument | Template Constant | Purpose |
|--------|-------------------|-------------------|---------|
| `analyze-ticket` | `ticket_id` | `TICKET_ANALYSIS_TEMPLATE` | Analyze ticket for insights (summary, status, timeline) |
| `draft-ticket-response` | `ticket_id` | `COMMENT_DRAFT_TEMPLATE` | Draft professional response (acknowledge, address, next steps) |

### Resources (2 total)

| URI | Name | Caching | Response Format |
|-----|------|---------|-----------------|
| `zendesk://knowledge-base` | Zendesk Knowledge Base | TTL 1 hour | JSON with sections, articles, metadata |
| `zendesk://organizations` | Zendesk Organizations | TTL 3 days | JSON with organizations list, count metadata |

---

## ZendeskClient Class

### Constructor

```python
ZendeskClient(subdomain: str, email: str, token: str)
```

Initializes:
- `self.client` - Zenpy instance for object-oriented API access
- `self.base_url` - `https://{subdomain}.zendesk.com/api/v2`
- `self.auth_header` - Basic auth header for direct REST calls

### Methods

#### get_ticket(ticket_id: int) -> Dict[str, Any]
Retrieves single ticket via Zenpy.

**Returns:**
```python
{
    'id': int,
    'subject': str,
    'description': str,
    'status': str,  # new/open/pending/on-hold/solved/closed
    'priority': str,  # low/normal/high/urgent
    'created_at': str,  # ISO8601
    'updated_at': str,  # ISO8601
    'requester_id': int,
    'assignee_id': int | None,
    'organization_id': int | None
}
```

#### get_ticket_comments(ticket_id: int) -> List[Dict[str, Any]]
Retrieves all comments for a ticket via Zenpy.

**Returns:** List of:
```python
{
    'id': int,
    'author_id': int,
    'body': str,
    'html_body': str,
    'public': bool,
    'created_at': str  # ISO8601
}
```

#### post_comment(ticket_id: int, comment: str, public: bool = True) -> str
Posts comment to ticket via Zenpy. Returns the comment text.

#### get_tickets(page=1, per_page=25, sort_by='created_at', sort_order='desc') -> Dict[str, Any]
Fetches paginated tickets via **direct REST API** (not Zenpy).

**Parameters:**
- `page` - 1-based page number
- `per_page` - Max 100
- `sort_by` - `created_at`, `updated_at`, `priority`, `status`
- `sort_order` - `asc` or `desc`

**Returns:**
```python
{
    'tickets': [...],  # List of ticket dicts
    'page': int,
    'per_page': int,
    'count': int,
    'sort_by': str,
    'sort_order': str,
    'has_more': bool,
    'next_page': int | None,
    'previous_page': int | None
}
```

#### get_all_articles() -> Dict[str, Any]
Fetches Help Center articles grouped by section via Zenpy.

**Returns:**
```python
{
    "Section Name": {
        "section_id": int,
        "description": str,
        "articles": [
            {
                "id": int,
                "title": str,
                "body": str,
                "updated_at": str,
                "url": str
            }
        ]
    }
}
```

#### create_ticket(...) -> Dict[str, Any]
Creates new ticket via Zenpy.

**Parameters:**
- `subject` (required)
- `description` (required)
- `requester_id`, `assignee_id`, `priority`, `type`, `tags`, `custom_fields` (optional)

**Returns:** Ticket dict with 12 fields including `id`, `status`, `tags`.

#### update_ticket(ticket_id: int, **fields) -> Dict[str, Any]
Updates ticket fields via Zenpy. Accepts any valid ticket field as keyword argument.

**Returns:** Updated ticket dict.

#### search_organizations(name: str) -> List[Dict[str, Any]]
Searches for organizations by name via **direct REST API**.

**Returns:** List of:
```python
{
    'id': int,
    'name': str,
    'domain_names': list[str]
}
```

#### get_organization(organization_id: int) -> Dict[str, Any]
Retrieves single organization by ID via Zenpy.

**Returns:**
```python
{
    'id': int,
    'name': str,
    'domain_names': list[str],
    'created_at': str,  # ISO8601
    'updated_at': str   # ISO8601
}
```

#### get_all_organizations() -> List[Dict[str, Any]]
Retrieves all organizations via Zenpy iterator.

**Returns:** List of organization dicts (same format as `get_organization`).

#### search_tickets(...) -> Dict[str, Any]
Searches tickets with filters via Zenpy search API.

**Parameters:**
- `organization_name` - Filter by organization name (exact match)
- `created_after` - Filter tickets created after date (YYYY-MM-DD)
- `created_before` - Filter tickets created before date (YYYY-MM-DD)
- `status` - Filter by status (new, open, pending, on-hold, solved, closed)
- `page` - Page number (1-based)
- `per_page` - Max 100

**Returns:**
```python
{
    'tickets': [...],       # List of ticket dicts
    'page': int,
    'per_page': int,
    'count': int,           # Count on current page
    'total_count': int,     # Total matching tickets
    'query': str,           # The Zendesk query used
    'has_more': bool,
    'next_page': int | None,
    'previous_page': int | None
}
```

---

## Server Handlers

### Prompt Handlers

```python
@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]

@server.get_prompt()
async def handle_get_prompt(name: str, arguments: Dict[str, str] | None) -> types.GetPromptResult
```

### Tool Handlers

```python
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]
```

### Resource Handlers

```python
@server.list_resources()
async def handle_list_resources() -> list[types.Resource]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str
```

### Caching

**Knowledge Base Cache (1 hour TTL):**
```python
@ttl_cache(ttl=3600)
def get_cached_kb():
    return zendesk_client.get_all_articles()
```

**Organization Cache (3 day TTL with manual clear):**
```python
from cachetools import TTLCache

ORGANIZATION_CACHE_TTL = 259200  # 3 days
_organization_cache: TTLCache = TTLCache(maxsize=1, ttl=ORGANIZATION_CACHE_TTL)
_ORGS_CACHE_KEY = "all_organizations"

def get_cached_organizations():
    if _ORGS_CACHE_KEY not in _organization_cache:
        _organization_cache[_ORGS_CACHE_KEY] = zendesk_client.get_all_organizations()
    return _organization_cache[_ORGS_CACHE_KEY]

def clear_organization_cache():
    _organization_cache.clear()
    return True
```

---

## Data Structures

### Ticket Object (Full)

```json
{
  "id": 123,
  "subject": "Help needed",
  "description": "Ticket body text",
  "status": "open",
  "priority": "normal",
  "type": "question",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T12:45:00Z",
  "requester_id": 456,
  "assignee_id": 789,
  "organization_id": 101,
  "tags": ["billing", "urgent"]
}
```

### Tool Response Format

All tools return `list[types.TextContent]`:
```python
[types.TextContent(type="text", text=json.dumps(result))]
```

Error format:
```python
[types.TextContent(type="text", text=f"Error: {str(e)}")]
```

---

## API Integration

### Zenpy Library (Primary)

Used for:
- `get_ticket()` - `self.client.tickets(id=...)`
- `get_ticket_comments()` - `self.client.tickets.comments(ticket=...)`
- `post_comment()` - `self.client.tickets.update(ticket)`
- `create_ticket()` - `self.client.tickets.create(ticket)`
- `update_ticket()` - `self.client.tickets.update(ticket)`
- `get_all_articles()` - `self.client.help_center.sections()` + `sections.articles()`
- `get_organization()` - `self.client.organizations(id=...)`
- `get_all_organizations()` - `self.client.organizations()` iterator
- `search_tickets()` - `self.client.search(query, type='ticket')`

### Direct REST API (Secondary)

Used for:
- `get_tickets()` - `GET /api/v2/tickets.json` (better pagination support)
- `search_organizations()` - `GET /api/v2/organizations/search.json?name={name}`

Auth: Basic auth header
Library: `urllib.request`

---

## Error Handling

### Client Layer
```python
try:
    # API operation
except Exception as e:
    raise Exception(f"Failed to {operation}: {str(e)}")
```

### Tool Layer
```python
try:
    result = client.method()
    return [types.TextContent(type="text", text=json.dumps(result))]
except Exception as e:
    return [types.TextContent(type="text", text=f"Error: {str(e)}")]
```

### Logging

```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("zendesk-mcp-server")
```

---

## Dependencies

### Direct (pyproject.toml)

| Package | Version | Purpose |
|---------|---------|---------|
| `mcp` | >=1.1.2 | Model Context Protocol SDK |
| `python-dotenv` | >=1.0.1 | Environment variable loading |
| `zenpy` | >=2.0.56 | Zendesk Python SDK |

### Key Transitive

- `httpx` - Async HTTP client (MCP)
- `pydantic` - Data validation (MCP types)
- `cachetools` - TTL caching for knowledge base
- `requests` - HTTP client (Zenpy)

---

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `ZENDESK_SUBDOMAIN` | Zendesk account subdomain |
| `ZENDESK_EMAIL` | Zendesk account email |
| `ZENDESK_API_KEY` | Zendesk API token |

### Loading

```python
from dotenv import load_dotenv
load_dotenv()  # Loads from .env file
os.getenv("ZENDESK_SUBDOMAIN")
```

---

## Entry Points

### Package Entry

```python
# __init__.py
def main():
    asyncio.run(server.main())
```

### pyproject.toml Script

```toml
[project.scripts]
zendesk = "zendesk_mcp_server:main"
```

### Server Main

```python
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream=read_stream,
            write_stream=write_stream,
            initialization_options=InitializationOptions(
                server_name="Zendesk",
                server_version="0.1.0",
                capabilities=server.get_capabilities(...)
            )
        )
```

---

## Deployment

### Local (uv)

```bash
uv venv && uv pip install -e .
uv run zendesk
```

### Docker

```bash
docker build -t zendesk-mcp-server .
docker run --rm -i --env-file .env zendesk-mcp-server
```

### Claude Desktop Integration

```json
{
  "mcpServers": {
    "zendesk": {
      "command": "uv",
      "args": ["--directory", "/path/to/zendesk-mcp-server", "run", "zendesk"]
    }
  }
}
```

---

## Limitations

### Organization-Aware Ticket Queries

- **Single organization per query**: The `search_tickets` tool filters by one organization at a time
- **Search API limit**: Zendesk Search API returns max 1000 results per query
- **Organization cache**: Cached for 3 days; use `clear_organization_cache` tool to refresh if organizations are added/removed
- **Date format**: Date filters must use YYYY-MM-DD format (e.g., "2024-01-15")
