# Views and Custom Fields Guide

This guide explains how to use Zendesk Views and Custom Field search features with the MCP server.

## Views

Views allow you to retrieve tickets from predefined Zendesk views (e.g., "My Open Tickets", "Unassigned", or custom views your team has created).

### Listing Available Views

To see all available views:

```
Show me all available Zendesk views
```

```
List all views
```

```
What views do I have access to in Zendesk?
```

### Getting Tickets from a View

You can reference views by name or ID:

**By name (case-insensitive):**
```
Show me tickets in the "Unassigned Tickets" view
```

```
Get the first 10 tickets from the QA view
```

**By ID:**
```
Get tickets from view 12345678
```

**With pagination:**
```
Show me page 2 of tickets in the "Open Tickets" view, 50 per page
```

**Filtered by status:**
```
Show me open tickets in Craig's view
```

```
Get pending tickets from the Support Queue view
```

### Example Queries

| Query | What it does |
|-------|--------------|
| "List all views" | Shows available Zendesk views |
| "Get tickets from the Support Queue view" | Retrieves tickets from a view by name |
| "Show me the first 25 tickets in view 360123456789" | Gets tickets by view ID |
| "What tickets are in our Urgent view?" | Fetches tickets from a named view |
| "Show me open tickets in Craig's view" | Gets only open tickets from a view |
| "Get pending tickets from the QA view" | Filters view tickets by status |

### Cache Behavior

Views are cached for 3 days. If you've added or modified views in Zendesk and need fresh data:

```
Clear the views cache and then show me all views
```

---

## Custom Fields

Custom fields allow you to search tickets by Zendesk custom field values using friendly names instead of field IDs.

### Configuration

1. Find your custom field IDs in Zendesk Admin > Objects and rules > Tickets > Fields

2. Add the mapping to your `.env` file:

```env
ZENDESK_CUSTOM_FIELDS={"support_team_member": 12345678, "product": 87654321, "region": 11223344}
```

**Format:** JSON object where keys are friendly names and values are Zendesk field IDs.

3. Restart the MCP server to load the new configuration.

### Example Configuration

If your Zendesk has these custom fields:
- "Support Team Member" (ID: 360012345678)
- "Product Area" (ID: 360087654321)
- "Customer Tier" (ID: 360011223344)

Configure them as:
```env
ZENDESK_CUSTOM_FIELDS={"support_team_member": 360012345678, "product_area": 360087654321, "customer_tier": 360011223344}
```

### Searching by Custom Fields

Once configured, you can search using the friendly names:

```
Find tickets where support_team_member is "Craig"
```

```
Search for tickets with product_area "Billing" created after 2024-01-01
```

```
Show me open tickets where customer_tier is "Enterprise"
```

### Combining Filters

Custom fields can be combined with other search filters:

```
Find tickets for Acme Corp where support_team_member is "Sarah" and status is open
```

```
Search for tickets with product_area "API" created in the last week
```

```
Get pending tickets where region is "EMEA" and customer_tier is "Premium"
```

### Example Queries

| Query | What it does |
|-------|--------------|
| "Find tickets where support_team_member is Craig" | Searches by custom field value |
| "Show open tickets with product_area Billing" | Combines status and custom field |
| "Tickets for Open University where region is UK" | Combines organization and custom field |
| "Search tickets created after 2024-01-01 with customer_tier Enterprise" | Combines date and custom field |

---

## Troubleshooting

### Verify server configuration

If something seems wrong, verify which Zendesk instance the server is connected to:

```
What Zendesk instance am I connected to?
```

```
Show me the server configuration
```

This will display the subdomain, email, and configured custom fields.

### View not found

If you get "View not found" errors:
1. Check the exact view name in Zendesk
2. View names are case-insensitive but must match exactly otherwise
3. Try clearing the views cache: "Clear the views cache"
4. Use the view ID instead of name

### Custom field not working

If custom field searches aren't being used or return no results:

1. **Verify `.env` configuration** - Check the JSON syntax is valid:
   ```env
   ZENDESK_CUSTOM_FIELDS={"root_cause": 4416459398801, "product": 12345678}
   ```

2. **Restart Claude Desktop** - The MCP server only reads configuration at startup

3. **Verify the field is loaded** - Ask Claude:
   ```
   Show me the server configuration
   ```
   The response should list your custom field in `custom_fields_configured`

4. **Use the exact field name** - If your field is configured as `root_cause`, use that exact name in your query:
   ```
   Find tickets with root_cause "training issue"
   ```

5. **Check the field ID** - Verify the ID is correct in Zendesk Admin > Objects and rules > Tickets > Fields

6. **Exact match only** - Custom field search uses exact match (Zendesk limitation)

### Stale data

Both views and organizations are cached for 3 days. To refresh:
- Views: "Clear the views cache"
- Organizations: "Clear the organization cache"

---

## Quick Reference

### View Commands

| Action | Example Query |
|--------|---------------|
| List views | "Show me all Zendesk views" |
| Get view tickets | "Get tickets from the [View Name] view" |
| Filter by status | "Show me open tickets in [View Name] view" |
| Paginate results | "Show page 2 of the [View Name] view, 50 per page" |
| Clear cache | "Clear the views cache" |

### Search with Custom Fields

| Action | Example Query |
|--------|---------------|
| Single field | "Find tickets where [field_name] is [value]" |
| With organization | "Tickets for [Org] where [field_name] is [value]" |
| With date range | "Tickets created after [date] with [field_name] [value]" |
| With status | "Open tickets where [field_name] is [value]" |
| Multiple fields | "Tickets where [field1] is [value1] and [field2] is [value2]" |
