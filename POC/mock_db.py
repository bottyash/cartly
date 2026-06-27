"""
mock_db.py
----------
Mock order/customer data store for the Cartly POC.

Stands in for a live marketplace order API. All tool calls in the POC are
backed by deterministic, seeded mock data rather than a real Cartly backend
(per PDLC Stage 3, Tool Specifications: "All tools are backed by mock
services seeded from the primary dataset").

This module intentionally has NO LLM calls in it. It is a pure data layer
so the orchestrator's deterministic checks (e.g. the refund threshold gate)
can run against it without touching a model.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class OrderRecord:
    order_id: str
    customer_id: str
    seller_id: str
    items: list
    amount_inr: float
    order_date: date
    delivery_eta: Optional[str]
    fulfilment_state: str  # delivered, in_transit, cancelled
    payment_ref: str
    is_returnable: bool
    return_window_days: int


# Seeded mock order data. Amounts and dates are chosen deliberately to
# exercise every branch of the refund-eligibility flow.
_ORDERS = {
    "ORD-1001": OrderRecord(
        order_id="ORD-1001",
        customer_id="CUST-501",
        seller_id="SELL-12",
        items=["Hand-knit wool scarf"],
        amount_inr=350.0,
        order_date=date(2026, 6, 15),
        delivery_eta=None,
        fulfilment_state="delivered",
        payment_ref="PAY-9001",
        is_returnable=True,
        return_window_days=30,
    ),
    "ORD-1002": OrderRecord(
        order_id="ORD-1002",
        customer_id="CUST-502",
        seller_id="SELL-07",
        items=["Espresso machine, dual boiler"],
        amount_inr=2200.0,
        order_date=date(2026, 6, 10),
        delivery_eta=None,
        fulfilment_state="delivered",
        payment_ref="PAY-9002",
        is_returnable=True,
        return_window_days=30,
    ),
    "ORD-1003": OrderRecord(
        order_id="ORD-1003",
        customer_id="CUST-503",
        seller_id="SELL-03",
        items=["Pierced earrings (hygiene item)"],
        amount_inr=180.0,
        order_date=date(2026, 6, 18),
        delivery_eta=None,
        fulfilment_state="delivered",
        payment_ref="PAY-9003",
        is_returnable=False,  # non-returnable category
        return_window_days=0,
    ),
    "ORD-1004": OrderRecord(
        order_id="ORD-1004",
        customer_id="CUST-504",
        seller_id="SELL-12",
        items=["Ceramic plant pot, medium"],
        amount_inr=210.0,
        order_date=date(2026, 4, 1),  # well outside any return window
        delivery_eta=None,
        fulfilment_state="delivered",
        payment_ref="PAY-9004",
        is_returnable=True,
        return_window_days=30,
    ),
    "ORD-1005": OrderRecord(
        order_id="ORD-1005",
        customer_id="CUST-505",
        seller_id="SELL-19",
        items=["Cast-iron skillet, 12 inch"],
        amount_inr=480.0,
        order_date=date(2026, 6, 20),
        delivery_eta=None,
        fulfilment_state="delivered",
        payment_ref="PAY-9005",
        is_returnable=True,
        return_window_days=30,
    ),
}

# Today, fixed for deterministic demo output rather than wall-clock date.
TODAY = date(2026, 6, 25)


def get_order(order_id: str) -> Optional[OrderRecord]:
    """Look up an order by ID. Returns None if not found (simulates a
    bad/garbled order ID in a ticket, which must escalate rather than guess).
    """
    return _ORDERS.get(order_id)


def days_since_order(order: OrderRecord) -> int:
    return (TODAY - order.order_date).days


def refund_action(order_id: str, amount_inr: float) -> dict:
    """Mock refund execution tool. Only ever called after eligibility AND
    the autonomy threshold have both cleared -- never called speculatively.
    """
    order = get_order(order_id)
    if order is None:
        return {"success": False, "transaction_ref": None, "reason": "order_not_found"}
    return {
        "success": True,
        "transaction_ref": f"RFND-{order_id[-4:]}-{int(amount_inr)}",
        "estimated_settlement": "3-5 business days",
    }
