"""
Mock Order DB — PostgreSQL-backed order lookup.

Provides public functions:
  order_lookup(order_id: str) -> dict | None
  get_orders_by_buyer(buyer_name: str) -> list[dict]
  owns_order(buyer_name: str, order_id: str) -> bool
  create_live_ticket(...) -> dict
  get_live_tickets(status) -> list[dict]
  get_live_ticket(ticket_id) -> dict | None
  add_live_message(ticket_id, sender, sender_name, message) -> dict
  resolve_live_ticket(ticket_id) -> bool
  set_ticket_active(ticket_id) -> bool
  set_ticket_verdict(ticket_id, verdict_type, verdict_decision, comment) -> dict
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



def get_orders_by_buyer(buyer_name: str) -> list[dict]:
    """
    Return all orders belonging to the given buyer.
    Supports both first-name-only ("Rahul") and full-name ("Rahul Mehta") lookup.
    Matches buyer_name exactly or where buyer_name starts with the given name
    followed by a space (i.e. first name match), case-insensitive.
    """
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Escape LIKE metacharacters to prevent wildcard DB dump (F-01)
                safe_name = buyer_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                cur.execute(
                    """
                    SELECT * FROM orders
                    WHERE LOWER(buyer_name) = LOWER(%s)
                       OR LOWER(buyer_name) LIKE LOWER(%s) ESCAPE '\\'
                    ORDER BY order_date DESC
                    """,
                    (buyer_name, f"{safe_name} %"),
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
        raise RuntimeError(f"DB buyer lookup failed for '{buyer_name}': {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass


def owns_order(buyer_name: str, order_id: str) -> bool:
    """
    Return True iff the order belongs to the given buyer.
    Supports first-name or full-name matching.
    """
    order = order_lookup(order_id)
    if order is None:
        return False
    db_name = order.get("buyer_name", "").strip().lower()
    query = buyer_name.strip().lower()
    # Exact full-name match OR first-name prefix match
    return db_name == query or db_name.startswith(query + " ")


# ─────────────────────────────────────────────────────────────────────────────
# LIVE CHAT  —  human-agent tickets
# ─────────────────────────────────────────────────────────────────────────────

def _ts(row: dict, *fields: str) -> dict:
    """Convert timestamp fields to ISO strings in-place."""
    for f in fields:
        if row.get(f) is not None:
            row[f] = row[f].isoformat()
    return row


def create_live_ticket(
    order_id: str,
    buyer_name: str,
    product_name: str,
    issue_summary: str,
) -> dict:
    """Open a new live-chat ticket (status='waiting')."""
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO live_chat_tickets
                      (order_id, buyer_name, product_name, issue_summary, status)
                    VALUES (%s, %s, %s, %s, 'waiting')
                    RETURNING *
                    """,
                    (order_id, buyer_name, product_name, issue_summary),
                )
                row = dict(cur.fetchone())
        return _ts(row, "created_at", "updated_at")
    except psycopg2.Error as exc:
        raise RuntimeError(f"create_live_ticket failed: {exc}") from exc
    finally:
        try: conn.close()
        except Exception: pass


def get_live_tickets(status: str | None = None) -> list[dict]:
    """Return all live tickets, optionally filtered by status."""
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if status:
                    cur.execute(
                        "SELECT * FROM live_chat_tickets WHERE status = %s ORDER BY created_at DESC",
                        (status,),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM live_chat_tickets WHERE status != 'resolved' ORDER BY created_at DESC"
                    )
                rows = cur.fetchall()
        return [_ts(dict(r), "created_at", "updated_at") for r in rows]
    except psycopg2.Error as exc:
        raise RuntimeError(f"get_live_tickets failed: {exc}") from exc
    finally:
        try: conn.close()
        except Exception: pass


def get_live_ticket(ticket_id: int) -> dict | None:
    """Return a single ticket with its full message history."""
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM live_chat_tickets WHERE id = %s", (ticket_id,))
                row = cur.fetchone()
                if row is None:
                    return None
                ticket = _ts(dict(row), "created_at", "updated_at")

                cur.execute(
                    "SELECT * FROM live_chat_messages WHERE ticket_id = %s ORDER BY created_at ASC",
                    (ticket_id,),
                )
                msgs = [_ts(dict(m), "created_at") for m in cur.fetchall()]
        ticket["messages"] = msgs
        return ticket
    except psycopg2.Error as exc:
        raise RuntimeError(f"get_live_ticket failed: {exc}") from exc
    finally:
        try: conn.close()
        except Exception: pass


def add_live_message(
    ticket_id: int,
    sender: str,      # 'user' | 'admin'
    sender_name: str,
    message: str,
) -> dict:
    """Append a message and bump ticket.updated_at."""
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO live_chat_messages (ticket_id, sender, sender_name, message)
                    VALUES (%s, %s, %s, %s) RETURNING *
                    """,
                    (ticket_id, sender, sender_name, message),
                )
                msg = _ts(dict(cur.fetchone()), "created_at")
                cur.execute(
                    "UPDATE live_chat_tickets SET updated_at=NOW() WHERE id=%s",
                    (ticket_id,),
                )
        return msg
    except psycopg2.Error as exc:
        raise RuntimeError(f"add_live_message failed: {exc}") from exc
    finally:
        try: conn.close()
        except Exception: pass


def set_ticket_active(ticket_id: int) -> bool:
    """Mark a ticket as active (admin joined)."""
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE live_chat_tickets SET status='active', updated_at=NOW() WHERE id=%s",
                    (ticket_id,),
                )
                return cur.rowcount == 1
    except psycopg2.Error as exc:
        raise RuntimeError(f"set_ticket_active failed: {exc}") from exc
    finally:
        try: conn.close()
        except Exception: pass


def resolve_live_ticket(ticket_id: int) -> bool:
    """Mark a ticket as resolved."""
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE live_chat_tickets SET status='resolved', updated_at=NOW() WHERE id=%s",
                    (ticket_id,),
                )
                return cur.rowcount == 1
    except psycopg2.Error as exc:
        raise RuntimeError(f"resolve_live_ticket failed: {exc}") from exc
    finally:
        try: conn.close()
        except Exception: pass


def set_ticket_verdict(
    ticket_id: int,
    verdict_type: str,      # refund | replacement | exchange | complaint | other
    verdict_decision: str,  # approved | denied
    comment: str,
) -> dict:
    """
    Record a human agent verdict on a live chat ticket:
    1. Saves verdict fields (type, decision, comment) on the ticket.
    2. Updates the linked order's notes with a resolution summary.
    3. Appends a formatted system message visible to the customer.
    4. Marks the ticket as resolved.
    Returns the updated ticket dict.
    """
    # Build human-readable verdict message for the customer
    type_label = {
        "refund":      "Refund",
        "replacement": "Replacement",
        "exchange":    "Exchange",
        "complaint":   "Complaint",
        "other":       "Request",
    }.get(verdict_type, verdict_type.title())

    if verdict_decision == "approved":
        msg = (
            f"✅ {type_label} Approved\n\n"
            f"Your {type_label.lower()} request has been approved by our support team.\n"
            f"Agent note: {comment}"
        )
        order_note = f"[RESOLVED] {type_label} approved by support agent. Note: {comment}"
    else:
        msg = (
            f"❌ {type_label} Request Declined\n\n"
            f"After review, we are unable to approve this {type_label.lower()} request.\n"
            f"Agent note: {comment}"
        )
        order_note = f"[RESOLVED] {type_label} denied by support agent. Note: {comment}"

    try:
        conn = _get_connection()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 1. Fetch ticket to get order_id
                cur.execute("SELECT * FROM live_chat_tickets WHERE id = %s", (ticket_id,))
                ticket = cur.fetchone()
                if not ticket:
                    raise RuntimeError(f"Ticket {ticket_id} not found")

                # 2. Save verdict on ticket + resolve
                cur.execute(
                    """
                    UPDATE live_chat_tickets
                    SET verdict_type=%s, verdict_decision=%s, verdict_comment=%s,
                        status='resolved', updated_at=NOW()
                    WHERE id=%s
                    """,
                    (verdict_type, verdict_decision, comment, ticket_id),
                )

                # 3. Update order notes (visible in customer's My Orders)
                cur.execute(
                    "UPDATE orders SET notes=%s WHERE order_id=%s",
                    (order_note, str(ticket["order_id"])),
                )

                # 4. Add system message to chat (customer sees this live)
                cur.execute(
                    """
                    INSERT INTO live_chat_messages (ticket_id, sender, sender_name, message)
                    VALUES (%s, 'system', 'Cartly Support', %s)
                    RETURNING id, ticket_id, sender, sender_name, message, created_at
                    """,
                    (ticket_id, msg),
                )
                new_msg = dict(cur.fetchone())
                new_msg["created_at"] = new_msg["created_at"].isoformat()

        return {
            "ticket_id":       ticket_id,
            "verdict_type":    verdict_type,
            "verdict_decision": verdict_decision,
            "verdict_comment": comment,
            "system_message":  new_msg,
        }
    except psycopg2.Error as exc:
        raise RuntimeError(f"set_ticket_verdict failed: {exc}") from exc
    finally:
        try: conn.close()
        except Exception: pass
