#!/usr/bin/env python3
"""End-to-end MCP stdio test client for the mini SQLite server."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server.py"
DB_PATH = ROOT / "data" / "demo.db"


class Client:
    def __init__(self) -> None:
        env = os.environ.copy()
        env["MINI_MCP_DB"] = str(DB_PATH)
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self.next_id = 1

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        response = json.loads(self.proc.stdout.readline())
        if response.get("id") != request_id:
            raise AssertionError(f"Unexpected response id: {response}")
        if "error" in response:
            raise AssertionError(response["error"])
        return response["result"]

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def parse_tool_text(result: dict[str, Any]) -> Any:
    return json.loads(result["content"][0]["text"])


def main() -> int:
    if not DB_PATH.exists():
        raise SystemExit("Database is missing. Run python3 scripts/seed_db.py first.")

    client = Client()
    try:
        initialized = client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mini-local-client", "version": "0.1.0"},
            },
        )
        client.notify("notifications/initialized")

        tools = client.request("tools/list")
        tool_names = {tool["name"] for tool in tools["tools"]}
        assert {"get_schema", "query_database"}.issubset(tool_names)

        schema = parse_tool_text(client.request("tools/call", {"name": "get_schema", "arguments": {}}))
        assert "orders" in schema["tables"]

        query = parse_tool_text(
            client.request(
                "tools/call",
                {
                    "name": "query_database",
                    "arguments": {
                        "sql": """
                            select customer, sum(total_cents) as total_cents
                            from orders
                            where status = 'paid'
                            group by customer
                            order by total_cents desc
                        """,
                        "limit": 5,
                    },
                },
            )
        )
        assert query["rows"][0]["customer"] == "Vertex Labs"

        print("Initialized:", initialized["serverInfo"])
        print("Tools:", ", ".join(sorted(tool_names)))
        print("Top paid customer:", query["rows"][0])
        print("MCP stdio test passed")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

