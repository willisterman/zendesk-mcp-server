import asyncio
import json
import logging
import os
from typing import Any, Dict

from cachetools import TTLCache
from cachetools.func import ttl_cache
from dotenv import load_dotenv
from mcp.server import InitializationOptions, NotificationOptions
from mcp.server import Server, types
from mcp.server.stdio import stdio_server
from pydantic import AnyUrl

from zendesk_mcp_server.zendesk_client import ZendeskClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("zendesk-mcp-server")
logger.info("zendesk mcp server started")

load_dotenv()
zendesk_client = ZendeskClient(
    subdomain=os.getenv("ZENDESK_SUBDOMAIN"),
    email=os.getenv("ZENDESK_EMAIL"),
    token=os.getenv("ZENDESK_API_KEY")
)

# Organization cache with 3-day TTL (259200 seconds)
ORGANIZATION_CACHE_TTL = 259200
_organization_cache: TTLCache = TTLCache(maxsize=1, ttl=ORGANIZATION_CACHE_TTL)
_ORGS_CACHE_KEY = "all_organizations"


def get_cached_organizations():
    """Get all organizations from cache or fetch from API."""
    if _ORGS_CACHE_KEY not in _organization_cache:
        _organization_cache[_ORGS_CACHE_KEY] = zendesk_client.get_all_organizations()
    return _organization_cache[_ORGS_CACHE_KEY]


def clear_organization_cache():
    """Clear the organization cache."""
    _organization_cache.clear()
    return True


# Views cache with 3-day TTL (same as organizations)
VIEWS_CACHE_TTL = 259200
_views_cache: TTLCache = TTLCache(maxsize=1, ttl=VIEWS_CACHE_TTL)
_VIEWS_CACHE_KEY = "all_views"


def get_cached_views():
    """Get all active views from cache or fetch from API."""
    if _VIEWS_CACHE_KEY not in _views_cache:
        _views_cache[_VIEWS_CACHE_KEY] = zendesk_client.get_views()
    return _views_cache[_VIEWS_CACHE_KEY]


def clear_views_cache():
    """Clear the views cache."""
    _views_cache.clear()
    return True


# Load custom field mappings from environment
# Format: JSON object {"friendly_name": field_id, ...}
_custom_field_config: Dict[str, int] = {}
_custom_fields_env = os.getenv("ZENDESK_CUSTOM_FIELDS")
if _custom_fields_env:
    try:
        _custom_field_config = json.loads(_custom_fields_env)
    except json.JSONDecodeError:
        logger.warning("Invalid ZENDESK_CUSTOM_FIELDS JSON, ignoring")


server = Server("Zendesk Server")

TICKET_ANALYSIS_TEMPLATE = """
You are a helpful Zendesk support analyst. You've been asked to analyze ticket #{ticket_id}.

Please fetch the ticket info and comments to analyze it and provide:
1. A summary of the issue
2. The current status and timeline
3. Key points of interaction

Remember to be professional and focus on actionable insights.
"""

COMMENT_DRAFT_TEMPLATE = """
You are a helpful Zendesk support agent. You need to draft a response to ticket #{ticket_id}.

Please fetch the ticket info, comments and knowledge base to draft a professional and helpful response that:
1. Acknowledges the customer's concern
2. Addresses the specific issues raised
3. Provides clear next steps or ask for specific details need to proceed
4. Maintains a friendly and professional tone
5. Ask for confirmation before commenting on the ticket

The response should be formatted well and ready to be posted as a comment.
"""


@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """List available prompts"""
    return [
        types.Prompt(
            name="analyze-ticket",
            description="Analyze a Zendesk ticket and provide insights",
            arguments=[
                types.PromptArgument(
                    name="ticket_id",
                    description="The ID of the ticket to analyze",
                    required=True,
                )
            ],
        ),
        types.Prompt(
            name="draft-ticket-response",
            description="Draft a professional response to a Zendesk ticket",
            arguments=[
                types.PromptArgument(
                    name="ticket_id",
                    description="The ID of the ticket to respond to",
                    required=True,
                )
            ],
        )
    ]


@server.get_prompt()
async def handle_get_prompt(name: str, arguments: Dict[str, str] | None) -> types.GetPromptResult:
    """Handle prompt requests"""
    if not arguments or "ticket_id" not in arguments:
        raise ValueError("Missing required argument: ticket_id")

    ticket_id = int(arguments["ticket_id"])
    try:
        if name == "analyze-ticket":
            prompt = TICKET_ANALYSIS_TEMPLATE.format(
                ticket_id=ticket_id
            )
            description = f"Analysis prompt for ticket #{ticket_id}"

        elif name == "draft-ticket-response":
            prompt = COMMENT_DRAFT_TEMPLATE.format(
                ticket_id=ticket_id
            )
            description = f"Response draft prompt for ticket #{ticket_id}"

        else:
            raise ValueError(f"Unknown prompt: {name}")

        return types.GetPromptResult(
            description=description,
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text=prompt.strip()),
                )
            ],
        )

    except Exception as e:
        logger.error(f"Error generating prompt: {e}")
        raise


def _build_search_tickets_description() -> str:
    """Build the search_tickets tool description, including any configured custom fields."""
    base_desc = "Search for tickets with filters (organization, date range, status)."
    if _custom_field_config:
        field_names = ", ".join(_custom_field_config.keys())
        return f"{base_desc} Custom field filters available: {field_names}."
    return base_desc


def _build_search_tickets_schema() -> dict:
    """Build the search_tickets tool schema, including any configured custom fields."""
    properties = {
        "organization_name": {
            "type": "string",
            "description": "Filter by organization name (exact match)"
        },
        "created_after": {
            "type": "string",
            "description": "Filter tickets created after this date (YYYY-MM-DD format)"
        },
        "created_before": {
            "type": "string",
            "description": "Filter tickets created before this date (YYYY-MM-DD format)"
        },
        "status": {
            "type": "string",
            "description": "Filter by ticket status (new, open, pending, on-hold, solved, closed)"
        },
        "page": {
            "type": "integer",
            "description": "Page number (1-based)",
            "default": 1
        },
        "per_page": {
            "type": "integer",
            "description": "Number of tickets per page (max 100)",
            "default": 25
        }
    }

    # Add configured custom fields to the schema
    for field_name in _custom_field_config.keys():
        properties[field_name] = {
            "type": "string",
            "description": f"Filter by {field_name.replace('_', ' ')}"
        }

    return {
        "type": "object",
        "properties": properties,
        "required": []
    }


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available Zendesk tools"""
    return [
        types.Tool(
            name="get_ticket",
            description="Retrieve a Zendesk ticket by its ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the ticket to retrieve"
                    }
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="create_ticket",
            description="Create a new Zendesk ticket",
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Ticket subject"},
                    "description": {"type": "string", "description": "Ticket description"},
                    "requester_id": {"type": "integer"},
                    "assignee_id": {"type": "integer"},
                    "priority": {"type": "string", "description": "low, normal, high, urgent"},
                    "type": {"type": "string", "description": "problem, incident, question, task"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "custom_fields": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["subject", "description"],
            }
        ),
        types.Tool(
            name="get_tickets",
            description="Fetch the latest tickets with pagination support",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "description": "Page number",
                        "default": 1
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Number of tickets per page (max 100)",
                        "default": 25
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (created_at, updated_at, priority, status)",
                        "default": "created_at"
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order (asc or desc)",
                        "default": "desc"
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="search_tickets",
            description="Search Zendesk tickets using query syntax. Supports filters like status:open, priority:urgent, subject:\"text\", tags:tag_name, assignee:name, created>2024-01-01, and free-text search.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Zendesk search query. Examples: 'status:open reporting', 'status:open priority:urgent', 'subject:\"dashboard\" status:open', 'tags:bug created>2024-01-01'"
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number",
                        "default": 1
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (max 100)",
                        "default": 25
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (updated_at, created_at, priority, status, ticket_type)",
                        "default": "updated_at"
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order (asc or desc)",
                        "default": "desc"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_ticket_comments",
            description="Retrieve all comments for a Zendesk ticket by its ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the ticket to get comments for"
                    }
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="create_internal_note",
            description="Add a private/internal note to a Zendesk ticket (not visible to the customer). Supports file attachments.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the ticket to add an internal note to"
                    },
                    "comment": {
                        "type": "string",
                        "description": "The internal note text/content"
                    },
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of absolute file paths to attach"
                    }
                },
                "required": ["ticket_id", "comment"]
            }
        ),
        types.Tool(
            name="create_public_comment",
            description="Post a PUBLIC comment on a Zendesk ticket that IS VISIBLE TO THE CUSTOMER. Use create_internal_note for private notes instead. Supports file attachments.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the ticket to comment on"
                    },
                    "comment": {
                        "type": "string",
                        "description": "The public comment text/content (visible to customer)"
                    },
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of absolute file paths to attach"
                    }
                },
                "required": ["ticket_id", "comment"]
            }
        ),
        types.Tool(
            name="update_ticket",
            description="Update fields on an existing Zendesk ticket (e.g., status, priority, assignee_id)",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "integer", "description": "The ID of the ticket to update"},
                    "subject": {"type": "string"},
                    "status": {"type": "string", "description": "new, open, pending, on-hold, solved, closed"},
                    "priority": {"type": "string", "description": "low, normal, high, urgent"},
                    "type": {"type": "string"},
                    "assignee_id": {"type": "integer"},
                    "requester_id": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "custom_fields": {"type": "array", "items": {"type": "object"}},
                    "due_at": {"type": "string", "description": "ISO8601 datetime"}
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="search_organizations",
            description="Search for Zendesk organizations by name",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Organization name to search for"
                    }
                },
                "required": ["name"]
            }
        ),
        types.Tool(
            name="get_organization",
            description="Get details of a specific Zendesk organization by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "organization_id": {
                        "type": "integer",
                        "description": "The ID of the organization to retrieve"
                    }
                },
                "required": ["organization_id"]
            }
        ),
        types.Tool(
            name="search_tickets",
            description=_build_search_tickets_description(),
            inputSchema=_build_search_tickets_schema()
        ),
        types.Tool(
            name="list_views",
            description="List all available Zendesk views",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="get_view_tickets",
            description="Get tickets from a Zendesk view. Accepts view ID (integer) or view name (string). Can optionally filter by status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "view": {
                        "type": ["integer", "string"],
                        "description": "View ID (integer) or view name (string)"
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by ticket status (new, open, pending, on-hold, solved, closed)"
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number (1-based)",
                        "default": 1
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Number of tickets per page (max 100)",
                        "default": 25
                    }
                },
                "required": ["view"]
            }
        ),
        types.Tool(
            name="clear_organization_cache",
            description="Clear the cached organization list. Use this if organizations have been added/removed and you need fresh data.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="clear_views_cache",
            description="Clear the cached views list. Use this if views have been added/modified and you need fresh data.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="get_server_config",
            description="Get the current MCP server configuration including Zendesk subdomain and email. Useful for verifying which Zendesk instance is connected.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(
        name: str,
        arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    """Handle Zendesk tool execution requests"""
    try:
        if name == "get_ticket":
            if not arguments:
                raise ValueError("Missing arguments")
            ticket = zendesk_client.get_ticket(arguments["ticket_id"])
            return [types.TextContent(
                type="text",
                text=json.dumps(ticket)
            )]

        elif name == "create_ticket":
            if not arguments:
                raise ValueError("Missing arguments")
            created = zendesk_client.create_ticket(
                subject=arguments.get("subject"),
                description=arguments.get("description"),
                requester_id=arguments.get("requester_id"),
                assignee_id=arguments.get("assignee_id"),
                priority=arguments.get("priority"),
                type=arguments.get("type"),
                tags=arguments.get("tags"),
                custom_fields=arguments.get("custom_fields"),
            )
            return [types.TextContent(
                type="text",
                text=json.dumps({"message": "Ticket created successfully", "ticket": created}, indent=2)
            )]

        elif name == "get_tickets":
            page = arguments.get("page", 1) if arguments else 1
            per_page = arguments.get("per_page", 25) if arguments else 25
            sort_by = arguments.get("sort_by", "created_at") if arguments else "created_at"
            sort_order = arguments.get("sort_order", "desc") if arguments else "desc"

            tickets = zendesk_client.get_tickets(
                page=page,
                per_page=per_page,
                sort_by=sort_by,
                sort_order=sort_order
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(tickets, indent=2)
            )]

        elif name == "search_tickets":
            if not arguments or "query" not in arguments:
                raise ValueError("Missing required argument: query")
            results = zendesk_client.search_tickets(
                query=arguments["query"],
                page=arguments.get("page", 1),
                per_page=arguments.get("per_page", 25),
                sort_by=arguments.get("sort_by", "updated_at"),
                sort_order=arguments.get("sort_order", "desc"),
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )]

        elif name == "get_ticket_comments":
            if not arguments:
                raise ValueError("Missing arguments")
            comments = zendesk_client.get_ticket_comments(
                arguments["ticket_id"])
            return [types.TextContent(
                type="text",
                text=json.dumps(comments)
            )]

        elif name == "create_internal_note":
            if not arguments:
                raise ValueError("Missing arguments")
            result = zendesk_client.post_comment(
                ticket_id=arguments["ticket_id"],
                comment=arguments["comment"],
                public=False,
                file_paths=arguments.get("file_paths")
            )
            attachments = arguments.get("file_paths", [])
            msg = "Internal note added successfully"
            if attachments:
                msg += f" with {len(attachments)} attachment(s)"
            return [types.TextContent(
                type="text",
                text=msg
            )]

        elif name == "create_public_comment":
            if not arguments:
                raise ValueError("Missing arguments")
            result = zendesk_client.post_comment(
                ticket_id=arguments["ticket_id"],
                comment=arguments["comment"],
                public=True,
                file_paths=arguments.get("file_paths")
            )
            attachments = arguments.get("file_paths", [])
            msg = "Public comment posted successfully"
            if attachments:
                msg += f" with {len(attachments)} attachment(s)"
            return [types.TextContent(
                type="text",
                text=msg
            )]

        elif name == "update_ticket":
            if not arguments:
                raise ValueError("Missing arguments")
            ticket_id = arguments.get("ticket_id")
            if ticket_id is None:
                raise ValueError("ticket_id is required")
            update_fields = {k: v for k, v in arguments.items() if k != "ticket_id"}
            updated = zendesk_client.update_ticket(ticket_id=int(ticket_id), **update_fields)
            return [types.TextContent(
                type="text",
                text=json.dumps({"message": "Ticket updated successfully", "ticket": updated}, indent=2)
            )]

        elif name == "search_organizations":
            if not arguments or "name" not in arguments:
                raise ValueError("Missing required argument: name")
            organizations = zendesk_client.search_organizations(arguments["name"])
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "organizations": organizations,
                    "count": len(organizations)
                }, indent=2)
            )]

        elif name == "get_organization":
            if not arguments or "organization_id" not in arguments:
                raise ValueError("Missing required argument: organization_id")
            organization = zendesk_client.get_organization(arguments["organization_id"])
            return [types.TextContent(
                type="text",
                text=json.dumps(organization, indent=2)
            )]

        elif name == "search_tickets":
            organization_name = arguments.get("organization_name") if arguments else None
            created_after = arguments.get("created_after") if arguments else None
            created_before = arguments.get("created_before") if arguments else None
            status = arguments.get("status") if arguments else None
            page = arguments.get("page", 1) if arguments else 1
            per_page = arguments.get("per_page", 25) if arguments else 25

            # Extract custom field values and map to IDs
            custom_fields = {}
            for field_name, field_id in _custom_field_config.items():
                if arguments and field_name in arguments:
                    custom_fields[field_id] = arguments[field_name]

            tickets = zendesk_client.search_tickets(
                organization_name=organization_name,
                created_after=created_after,
                created_before=created_before,
                status=status,
                custom_fields=custom_fields if custom_fields else None,
                page=page,
                per_page=per_page
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(tickets, indent=2)
            )]

        elif name == "list_views":
            views = get_cached_views()
            return [types.TextContent(
                type="text",
                text=json.dumps({"views": views, "count": len(views)}, indent=2)
            )]

        elif name == "get_view_tickets":
            if not arguments or "view" not in arguments:
                raise ValueError("Missing required argument: view")

            view_param = arguments["view"]
            status_filter = arguments.get("status")
            page = arguments.get("page", 1)
            per_page = arguments.get("per_page", 25)

            # Resolve view name to ID if string provided
            if isinstance(view_param, str):
                views = get_cached_views()
                view_id = None
                for view in views:
                    if view["title"].lower() == view_param.lower():
                        view_id = view["id"]
                        break
                if view_id is None:
                    raise ValueError(f"View not found: {view_param}")
            else:
                view_id = int(view_param)

            tickets = zendesk_client.get_view_tickets(
                view_id=view_id,
                page=page,
                per_page=per_page
            )

            # Filter by status if provided
            if status_filter:
                filtered_tickets = [t for t in tickets["tickets"] if t.get("status") == status_filter.lower()]
                tickets["tickets"] = filtered_tickets
                tickets["count"] = len(filtered_tickets)
                tickets["status_filter"] = status_filter

            return [types.TextContent(
                type="text",
                text=json.dumps(tickets, indent=2)
            )]

        elif name == "clear_views_cache":
            clear_views_cache()
            return [types.TextContent(
                type="text",
                text=json.dumps({"message": "Views cache cleared successfully"})
            )]

        elif name == "clear_organization_cache":
            clear_organization_cache()
            return [types.TextContent(
                type="text",
                text=json.dumps({"message": "Organization cache cleared successfully"})
            )]

        elif name == "get_server_config":
            # Determine source of environment variables
            env_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
            env_file_vars = set()
            if os.path.exists(env_file_path):
                with open(env_file_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            var_name = line.split("=")[0].strip()
                            env_file_vars.add(var_name)

            def get_var_source(var_name):
                if var_name in env_file_vars:
                    return "from .env file"
                elif os.getenv(var_name):
                    return "from environment variable"
                return "not set"

            config = {
                "server_path": os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "env_file_path": env_file_path if os.path.exists(env_file_path) else "not found",
                "zendesk_subdomain": {
                    "value": os.getenv("ZENDESK_SUBDOMAIN"),
                    "source": get_var_source("ZENDESK_SUBDOMAIN")
                },
                "zendesk_email": {
                    "value": os.getenv("ZENDESK_EMAIL"),
                    "source": get_var_source("ZENDESK_EMAIL")
                },
                "zendesk_api_key": {
                    "value": "***" if os.getenv("ZENDESK_API_KEY") else None,
                    "source": get_var_source("ZENDESK_API_KEY")
                },
                "zendesk_url": f"https://{os.getenv('ZENDESK_SUBDOMAIN')}.zendesk.com",
                "custom_fields_configured": list(_custom_field_config.keys()) if _custom_field_config else [],
                "custom_fields_source": get_var_source("ZENDESK_CUSTOM_FIELDS")
            }
            return [types.TextContent(
                type="text",
                text=json.dumps(config, indent=2)
            )]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    logger.debug("Handling list_resources request")
    return [
        types.Resource(
            uri=AnyUrl("zendesk://knowledge-base"),
            name="Zendesk Knowledge Base",
            description="Access to Zendesk Help Center articles and sections",
            mimeType="application/json",
        ),
        types.Resource(
            uri=AnyUrl("zendesk://organizations"),
            name="Zendesk Organizations",
            description="List of all Zendesk organizations (cached for 3 days)",
            mimeType="application/json",
        ),
        types.Resource(
            uri=AnyUrl("zendesk://views"),
            name="Zendesk Views",
            description="List of all active Zendesk views (cached for 3 days)",
            mimeType="application/json",
        )
    ]


@ttl_cache(ttl=3600)
def get_cached_kb():
    return zendesk_client.get_all_articles()


@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    logger.debug(f"Handling read_resource request for URI: {uri}")
    if uri.scheme != "zendesk":
        logger.error(f"Unsupported URI scheme: {uri.scheme}")
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    path = str(uri).replace("zendesk://", "")

    if path == "knowledge-base":
        try:
            kb_data = get_cached_kb()
            return json.dumps({
                "knowledge_base": kb_data,
                "metadata": {
                    "sections": len(kb_data),
                    "total_articles": sum(len(section['articles']) for section in kb_data.values()),
                }
            }, indent=2)
        except Exception as e:
            logger.error(f"Error fetching knowledge base: {e}")
            raise

    elif path == "organizations":
        try:
            org_data = get_cached_organizations()
            return json.dumps({
                "organizations": org_data,
                "metadata": {
                    "count": len(org_data),
                    "cache_ttl_seconds": ORGANIZATION_CACHE_TTL
                }
            }, indent=2)
        except Exception as e:
            logger.error(f"Error fetching organizations: {e}")
            raise

    elif path == "views":
        try:
            views_data = get_cached_views()
            return json.dumps({
                "views": views_data,
                "metadata": {
                    "count": len(views_data),
                    "cache_ttl_seconds": VIEWS_CACHE_TTL
                }
            }, indent=2)
        except Exception as e:
            logger.error(f"Error fetching views: {e}")
            raise

    else:
        logger.error(f"Unknown resource path: {path}")
        raise ValueError(f"Unknown resource path: {path}")


async def main():
    # Run the server using stdin/stdout streams
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream=read_stream,
            write_stream=write_stream,
            initialization_options=InitializationOptions(
                server_name="Zendesk",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
