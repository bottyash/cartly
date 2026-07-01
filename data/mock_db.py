"""
Mock Order DB — PostgreSQL-backed order lookup.

Provides a single public function:
  order_lookup(order_id: str) -> dict | None
"""

from __future__ import annotations

import os
from typing import Any

import psycopg2
import psycopg2.extras

_DSN = os.getenv("POSTGRES_DSN", "postgresql://cartly:cartly_secret@localhost:5432/cartly")


def _get_connection():
    return psycopg2.connect(_DSN)


def order_lookup(order_id: str) -> dict[str, Any] | None:
    """
    Look up an order by ID. Returns a plain dict or None if not found.

    The returned dict fields match the orders table schema:
      order_id, buyer_name, product_name, product_category,
      order_status, delivery_status, order_date, expected_delivery,
      actual_delivery, order_amount, payment_status, courier,
      is_electronic, notes
    """
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM orders WHERE order_id = %s", (order_id,)
                )
                row = cur.fetchone()
                if row is None:
                    return None
                record = dict(row)
                # Convert date objects to ISO strings for JSON serialisability
                for field in ("order_date", "expected_delivery", "actual_delivery"):
                    if record.get(field) is not None:
                        record[field] = record[field].isoformat()
                # Decimal → float
                if record.get("order_amount") is not None:
                    record["order_amount"] = float(record["order_amount"])
                return record
    except psycopg2.Error as exc:
        raise RuntimeError(f"Mock DB lookup failed for order {order_id}: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_orders_by_buyer(buyer_id: str) -> list[dict]:
    """
    Return all orders where buyer_name ILIKE the buyer_id string,
    or where order_id = buyer_id (POC: buyer_id is the order_id itself).
    """
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM orders
                    WHERE order_id = %s
                       OR LOWER(buyer_name) LIKE LOWER(%s)
                    ORDER BY order_date DESC
                    """,
                    (buyer_id, f"%{buyer_id}%"),
                )
                rows = cur.fetchall()
                results = []
                for row in rows:
                    record = dict(row)
                    for field in ("order_date", "expected_delivery", "actual_delivery"):
                        if record.get(field) is not None:
                            record[field] = record[field].isoformat()
                    if record.get("order_amount") is not None:
                        record["order_amount"] = float(record["order_amount"])
                    results.append(record)
                return results
    except psycopg2.Error as exc:
        raise RuntimeError(f"Mock DB buyer lookup failed for {buyer_id}: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass
