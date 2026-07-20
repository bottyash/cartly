"""
Delivery Agent — handles status_inquiry and delivery_inquiry intents.

Looks up the live order record from the DB and returns a factual,
structured response without any LLM call. Pure data retrieval.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from data.mock_db import order_lookup
from observability.logger import log_event


@dataclass
class DeliveryResult:
    order_id: str
    found: bool
    product_name: str = ""
    delivery_status: str = ""
    courier: str = ""
    tracking_id: str = ""
    estimated_delivery: str = ""
    delivery_notes: str = ""
    draft_response: str = ""
    action_taken: str = "info_provided"
    source_refs: list = None

    def __post_init__(self):
        if self.source_refs is None:
            self.source_refs = []


class DeliveryAgent:
    """
    Handles delivery / tracking queries.
    No LLM required — reads directly from the order DB.
    """

    STATUS_MESSAGES = {
        "delivered": "✅ Your order has been **delivered**.",
        "out_for_delivery": "🚚 Your order is **out for delivery** today.",
        "in_transit": "📦 Your order is **in transit** and on its way.",
        "shipped": "📬 Your order has been **shipped** and is en route.",
        "processing": "⚙️ Your order is currently **being processed**.",
        "pending": "🕐 Your order is **pending** and will be shipped soon.",
        "cancelled": "❌ Your order has been **cancelled**.",
        "not_delivered": "⚠️ Your order shows status **not delivered**. If it's been more than the expected window, please raise a refund request.",
    }

    def resolve(self, ticket_id: str, order_id: str, customer_query: str) -> DeliveryResult:
        t0 = time.monotonic()

        order = order_lookup(order_id)

        if not order:
            latency = (time.monotonic() - t0) * 1000
            log_event(
                ticket_id,
                step="delivery_agent_lookup",
                latency_ms=latency,
                cost_tokens=0,
                decision="order_not_found",
                metadata={"order_id": order_id},
            )
            return DeliveryResult(
                order_id=order_id,
                found=False,
                draft_response=f"I couldn't find order **#{order_id}** in our system. Please check the order ID and try again.",
                action_taken="info_provided",
            )

        status = order.get("delivery_status", "unknown")
        courier = order.get("courier", "")
        tracking = order.get("tracking_id", "")
        product = order.get("product_name", "your item")
        notes = order.get("delivery_notes", "")
        eta = order.get("estimated_delivery", "")

        status_msg = self.STATUS_MESSAGES.get(status, f"Your order status is: **{status}**.")

        # Build a natural, informative response
        parts = [
            f"Here's the latest on your order for **{product}** (#{order_id}):\n",
            status_msg,
        ]
        if courier:
            courier_line = f"\n\n🚚 **Courier:** {courier}"
            if tracking:
                courier_line += f"  |  **Tracking ID:** `{tracking}`"
            parts.append(courier_line)
        if eta:
            parts.append(f"\n📅 **Estimated Delivery:** {eta}")
        if notes:
            parts.append(f"\n📝 **Note:** {notes}")

        if status == "not_delivered":
            parts.append(
                "\n\nIf your item hasn't arrived, you can raise a **refund request** by describing the issue in this chat."
            )
        elif status == "delivered":
            parts.append(
                "\n\nIf there's a problem with the item received (damaged, wrong item, etc.), describe it here and I'll process a refund request for you."
            )

        draft = "".join(parts)

        latency = (time.monotonic() - t0) * 1000
        log_event(
            ticket_id,
            step="delivery_agent_lookup",
            latency_ms=latency,
            cost_tokens=0,
            decision=f"order_found — status={status}, courier={courier or 'N/A'}",
            metadata={
                "order_id": order_id,
                "delivery_status": status,
                "courier": courier,
                "tracking_id": tracking,
            },
        )

        return DeliveryResult(
            order_id=order_id,
            found=True,
            product_name=product,
            delivery_status=status,
            courier=courier,
            tracking_id=tracking,
            estimated_delivery=eta,
            delivery_notes=notes,
            draft_response=draft,
            action_taken="info_provided",
            source_refs=[],
        )
