#!/usr/bin/env python3
"""A tiny MCP server that exposes read-only SQLite tools over stdio."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


SERVER_NAME = "mini-mcp-sqlite"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"
DEFAULT_DB = Path(__file__).resolve().parent / "data" / "demo.db"


class McpError(Exception):
    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def write_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def db_path() -> Path:
    return Path(os.environ.get("MINI_MCP_DB", DEFAULT_DB)).expanduser().resolve()


def connect_readonly() -> sqlite3.Connection:
    path = db_path()
    if not path.exists():
        raise McpError(
            -32000,
            "Database not found",
            {"path": str(path), "hint": "Run python3 scripts/seed_db.py first."},
        )
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_readonly_query(sql: str) -> str:
    normalized = sql.strip().lower()
    if not normalized:
        raise McpError(-32602, "sql is required")
    if not (normalized.startswith("select") or normalized.startswith("with")):
        raise McpError(-32602, "Only SELECT or WITH queries are allowed")
    blocked = (";", "insert ", "update ", "delete ", "drop ", "alter ", "create ", "pragma ")
    if any(token in normalized for token in blocked):
        raise McpError(-32602, "Query contains a blocked token")
    return sql.strip()


def tool_get_schema(_: dict[str, Any]) -> dict[str, Any]:
    with connect_readonly() as conn:
        tables = conn.execute(
            """
            select name
            from sqlite_master
            where type = 'table' and name not like 'sqlite_%'
            order by name
            """
        ).fetchall()
        schema: dict[str, list[dict[str, Any]]] = {}
        for table in tables:
            table_name = table["name"]
            columns = conn.execute(f'pragma table_info("{table_name}")').fetchall()
            schema[table_name] = [
                {
                    "name": column["name"],
                    "type": column["type"],
                    "not_null": bool(column["notnull"]),
                    "primary_key": bool(column["pk"]),
                }
                for column in columns
            ]
    return {"database": str(db_path()), "tables": schema}


def tool_query_database(arguments: dict[str, Any]) -> dict[str, Any]:
    sql = ensure_readonly_query(str(arguments.get("sql", "")))
    limit = arguments.get("limit", 50)
    try:
        limit_int = int(limit)
    except (TypeError, ValueError) as exc:
        raise McpError(-32602, "limit must be an integer") from exc
    if limit_int < 1 or limit_int > 200:
        raise McpError(-32602, "limit must be between 1 and 200")

    wrapped_sql = f"select * from ({sql}) limit ?"
    try:
        with connect_readonly() as conn:
            cursor = conn.execute(wrapped_sql, (limit_int,))
            rows = [dict(row) for row in cursor.fetchall()]
            columns = [description[0] for description in cursor.description or []]
    except sqlite3.Error as exc:
        raise McpError(-32001, "SQLite query failed", {"details": str(exc)}) from exc

    return {"columns": columns, "rows": rows, "row_count": len(rows), "limit": limit_int}


TOOLS = {
    "get_schema": {
        "description": "Inspect the SQLite database schema.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": tool_get_schema,
    },
    "query_database": {
        "description": "Run a read-only SELECT/WITH query against the SQLite database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A single SELECT or WITH query. Semicolons and writes are blocked.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return, from 1 to 200.",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 50,
                },
            },
            "required": ["sql"],
            "additionalProperties": False,
        },
        "handler": tool_query_database,
    },
}


def text_result(payload: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, ensure_ascii=False),
            }
        ]
    }


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    if "id" not in message:
        return None

    request_id = message["id"]
    method = message.get("method")
    params = message.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": spec["description"],
                        "inputSchema": spec["inputSchema"],
                    }
                    for name, spec in TOOLS.items()
                ]
            },
        }

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if tool_name not in TOOLS:
            raise McpError(-32601, f"Unknown tool: {tool_name}")
        result = TOOLS[tool_name]["handler"](arguments)
        return {"jsonrpc": "2.0", "id": request_id, "result": text_result(result)}

    raise McpError(-32601, f"Unknown method: {method}")


def error_response(request_id: Any, exc: McpError) -> dict[str, Any]:
    error: dict[str, Any] = {"code": exc.code, "message": exc.message}
    if exc.data is not None:
        error["data"] = exc.data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        request_id: Any = None
        try:
            message = json.loads(line)
            request_id = message.get("id")
            response = handle_request(message)
            if response is not None:
                write_message(response)
        except json.JSONDecodeError as exc:
            write_message(error_response(None, McpError(-32700, "Parse error", str(exc))))
        except McpError as exc:
            write_message(error_response(request_id, exc))
        except Exception as exc:  # pragma: no cover - last-resort protocol guard
            write_message(error_response(request_id, McpError(-32603, "Internal error", str(exc))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

