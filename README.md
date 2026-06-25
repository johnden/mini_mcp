# Mini MCP SQLite Server

A tiny, dependency-free MCP server that wraps a real SQLite database query tool.
It is intentionally small enough to read in one sitting while still showing the
core MCP protocol flow:

1. JSON-RPC over stdio
2. `initialize`
3. `tools/list`
4. `tools/call`
5. structured tool results and MCP errors

The included test client acts like an MCP-capable host such as Claude Desktop or
a GPT/agent runtime: it starts the server process, performs the handshake, lists
available tools, and calls the database tools.

## What It Wraps

The server exposes two real tools backed by SQLite:

- `get_schema`: inspect tables and columns in the configured database.
- `query_database`: run a read-only SQL query and return rows as JSON.

Only `SELECT` and `WITH` statements are allowed. The server also opens SQLite in
read-only mode and applies a row limit so the tool is safe enough for demos and
interviews.

## Quick Start

```bash
python3 scripts/seed_db.py
python3 scripts/test_mcp_client.py
```

Expected result:

- the database is created at `data/demo.db`
- the client completes MCP initialization
- the client lists both tools
- the client calls `get_schema`
- the client calls `query_database` against demo order data

You can also run the server directly:

```bash
python3 server.py
```

Direct execution waits for newline-delimited JSON-RPC messages on stdin, which
is what MCP stdio hosts send.

## Claude Desktop Setup

After seeding the database, add this server to Claude Desktop's MCP config:

```json
{
  "mcpServers": {
    "mini-sqlite": {
      "command": "python3",
      "args": ["/Users/john/Projects/mini_mcp/server.py"],
      "env": {
        "MINI_MCP_DB": "/Users/john/Projects/mini_mcp/data/demo.db"
      }
    }
  }
}
```

Restart Claude Desktop, then ask something like:

```text
Use mini-sqlite to show the top 5 customers by total order amount.
```

## GPT / Agent Runtime Test

For GPT-style agent integration, use the same stdio contract demonstrated in
`scripts/test_mcp_client.py`:

1. spawn `python3 server.py`
2. send `initialize`
3. send `notifications/initialized`
4. call `tools/list`
5. call `tools/call`

That script is deliberately plain Python so the transport and JSON-RPC envelopes
are visible instead of hidden inside an SDK.

## Example Tool Call

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "query_database",
    "arguments": {
      "sql": "select customer, sum(total_cents) as total_cents from orders group by customer order by total_cents desc",
      "limit": 5
    }
  }
}
```

## Project Layout

```text
.
├── data/
│   └── demo.db
├── scripts/
│   ├── seed_db.py
│   └── test_mcp_client.py
├── server.py
└── README.md
```

