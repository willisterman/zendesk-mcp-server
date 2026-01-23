# Zendesk MCP Server

![ci](https://github.com/reminia/zendesk-mcp-server/actions/workflows/ci.yml/badge.svg)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A Model Context Protocol server for Zendesk.

This server provides a comprehensive integration with Zendesk. It offers:

- Tools for retrieving and managing Zendesk tickets and comments
- Specialized prompts for ticket analysis and response drafting
- Full access to the Zendesk Help Center articles as knowledge base

![demo](https://res.cloudinary.com/leecy-me/image/upload/v1736410626/open/zendesk_yunczu.gif)

## Switching from the Original Repository

If you previously cloned the original repository:

```bash
git clone https://github.com/reminia/zendesk-mcp-server.git
```

You can switch to this fork by updating your git remote:

```bash
cd zendesk-mcp-server
git remote set-url origin https://github.com/willisterman/zendesk-mcp-server.git
git fetch origin
git pull origin main
```

Alternatively, for a fresh clone of this fork:

```bash
git clone https://github.com/willisterman/zendesk-mcp-server.git
```

## Setup

- build: `uv venv && uv pip install -e .` or `uv build` in short.
- setup zendesk credentials in `.env` file, refer to [.env.example](.env.example).
- configure in Claude desktop:

```json
{
  "mcpServers": {
      "zendesk": {
          "command": "uv",
          "args": [
              "--directory",
              "/path/to/zendesk-mcp-server",
              "run",
              "zendesk"
          ]
      }
  }
}
```

### Docker

You can containerize the server if you prefer an isolated runtime:

1. Copy `.env.example` to `.env` and fill in your Zendesk credentials. Keep this file outside version control.
2. Build the image:

   ```bash
   docker build -t zendesk-mcp-server .
   ```

3. Run the server, providing the environment file:

   ```bash
   docker run --rm --env-file /path/to/.env zendesk-mcp-server
   ```

   Add `-i` when wiring the container to MCP clients over STDIN/STDOUT (Claude Code uses this mode). For daemonized runs, add `-d --name zendesk-mcp`.

The image installs dependencies from `requirements.lock`, drops privileges to a non-root user, and expects configuration exclusively via environment variables.

#### Claude MCP Integration

To use the Dockerized server from Claude Code/Desktop, add an entry to Claude Code's `settings.json` similar to:

```json
{
  "mcpServers": {
    "zendesk": {
      "command": "/usr/local/bin/docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/path/to/zendesk-mcp-server/.env",
        "zendesk-mcp-server"
      ]
    }
  }
}
```

Adjust the paths to match your environment. After saving the file, restart Claude for the new MCP server to be detected.

## Resources

- `zendesk://knowledge-base` - Access to Help Center articles (cached 1 hour)
- `zendesk://organizations` - List of all organizations (cached 3 days)
- `zendesk://views` - List of all active views (cached 3 days)

## Prompts

### analyze-ticket

Analyze a Zendesk ticket and provide a detailed analysis of the ticket.

### draft-ticket-response

Draft a response to a Zendesk ticket.

## Tools

### get_tickets

Fetch the latest tickets with pagination support

- Input:
  - `page` (integer, optional): Page number (defaults to 1)
  - `per_page` (integer, optional): Number of tickets per page, max 100 (defaults to 25)
  - `sort_by` (string, optional): Field to sort by - created_at, updated_at, priority, or status (defaults to created_at)
  - `sort_order` (string, optional): Sort order - asc or desc (defaults to desc)

- Output: Returns a list of tickets with essential fields including id, subject, status, priority, description, timestamps, and assignee information, along with pagination metadata

### get_ticket

Retrieve a Zendesk ticket by its ID

- Input:
  - `ticket_id` (integer): The ID of the ticket to retrieve

### get_ticket_comments

Retrieve all comments for a Zendesk ticket by its ID

- Input:
  - `ticket_id` (integer): The ID of the ticket to get comments for

### create_ticket_comment

Create a new comment on an existing Zendesk ticket

- Input:
  - `ticket_id` (integer): The ID of the ticket to comment on
  - `comment` (string): The comment text/content to add
  - `public` (boolean, optional): Whether the comment should be public (defaults to true)

### create_ticket

Create a new Zendesk ticket

- Input:
  - `subject` (string): Ticket subject
  - `description` (string): Ticket description
  - `requester_id` (integer, optional)
  - `assignee_id` (integer, optional)
  - `priority` (string, optional): one of `low`, `normal`, `high`, `urgent`
  - `type` (string, optional): one of `problem`, `incident`, `question`, `task`
  - `tags` (array[string], optional)
  - `custom_fields` (array[object], optional)

### update_ticket

Update fields on an existing Zendesk ticket (e.g., status, priority, assignee)

- Input:
  - `ticket_id` (integer): The ID of the ticket to update
  - `subject` (string, optional)
  - `status` (string, optional): one of `new`, `open`, `pending`, `on-hold`, `solved`, `closed`
  - `priority` (string, optional): one of `low`, `normal`, `high`, `urgent`
  - `type` (string, optional)
  - `assignee_id` (integer, optional)
  - `requester_id` (integer, optional)
  - `tags` (array[string], optional)
  - `custom_fields` (array[object], optional)
  - `due_at` (string, optional): ISO8601 datetime

### search_tickets

Search for tickets with filters

- Input:
  - `organization_name` (string, optional): Filter by organization name
  - `created_after` (string, optional): Filter tickets created after date (YYYY-MM-DD)
  - `created_before` (string, optional): Filter tickets created before date (YYYY-MM-DD)
  - `status` (string, optional): Filter by status
  - `page` (integer, optional): Page number (defaults to 1)
  - `per_page` (integer, optional): Results per page, max 100 (defaults to 25)
  - Plus any configured custom fields (see [Custom Fields Guide](docs/VIEWS_AND_CUSTOM_FIELDS.md))

### list_views

List all available Zendesk views

### get_view_tickets

Get tickets from a Zendesk view

- Input:
  - `view` (integer or string): View ID or view name (case-insensitive)
  - `status` (string, optional): Filter by status (new, open, pending, on-hold, solved, closed)
  - `page` (integer, optional): Page number (defaults to 1)
  - `per_page` (integer, optional): Results per page, max 100 (defaults to 25)

### search_organizations

Search for organizations by name

- Input:
  - `name` (string): Organization name to search for

### get_organization

Get organization details by ID

- Input:
  - `organization_id` (integer): The organization ID

### clear_organization_cache

Clear the cached organization list (use when organizations have changed)

### clear_views_cache

Clear the cached views list (use when views have changed)

## Documentation

- [Architecture Documentation](ARCHITECTURE.md) - Technical details of the codebase
- [Views and Custom Fields Guide](docs/VIEWS_AND_CUSTOM_FIELDS.md) - How to use views and configure custom field search
