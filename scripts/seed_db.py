#!/usr/bin/env python3
"""Create a small demo SQLite database for the MCP server."""

from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "demo.db"


def main() -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            drop table if exists orders;
            drop table if exists customers;

            create table customers (
                id integer primary key,
                name text not null,
                segment text not null,
                city text not null
            );

            create table orders (
                id integer primary key,
                customer_id integer not null references customers(id),
                customer text not null,
                product text not null,
                total_cents integer not null,
                status text not null,
                created_at text not null
            );
            """
        )
        conn.executemany(
            "insert into customers (id, name, segment, city) values (?, ?, ?, ?)",
            [
                (1, "Acme Robotics", "enterprise", "Shanghai"),
                (2, "Northwind Studio", "startup", "Beijing"),
                (3, "Blue Harbor Retail", "mid-market", "Shenzhen"),
                (4, "Vertex Labs", "enterprise", "Hangzhou"),
            ],
        )
        conn.executemany(
            """
            insert into orders
                (id, customer_id, customer, product, total_cents, status, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1, "Acme Robotics", "MCP audit package", 128000, "paid", "2026-01-05"),
                (2, 2, "Northwind Studio", "Agent prototype", 56000, "paid", "2026-01-18"),
                (3, 3, "Blue Harbor Retail", "Data connector", 72000, "trial", "2026-02-02"),
                (4, 1, "Acme Robotics", "SQLite analytics", 88000, "paid", "2026-02-20"),
                (5, 4, "Vertex Labs", "Internal API bridge", 164000, "paid", "2026-03-10"),
                (6, 2, "Northwind Studio", "Crawler pipeline", 42000, "cancelled", "2026-03-14"),
                (7, 4, "Vertex Labs", "Agent ops dashboard", 93000, "paid", "2026-04-01"),
            ],
        )
    print(f"Seeded {DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

