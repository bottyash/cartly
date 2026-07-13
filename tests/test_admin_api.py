"""
Tests for Sprint 2 API endpoints:
  - Admin auth (403 without token)
  - Admin stats structure validation
  - User-facing order lookup
  - Buyer-scoped order list
  - FR8 coverage assertion

Uses FastAPI TestClient — no external services required.
LLM and DB calls are mocked at the function level.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app, ADMIN_TOKEN

client = TestClient(app)


# ── Health ────────────────────────────────────────────────────────────────

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


# ── Admin auth ────────────────────────────────────────────────────────────

def test_admin_stats_no_token():
    """GET /admin/stats without token → 403."""
    r = client.get("/admin/stats")
    assert r.status_code == 403


def test_admin_stats_wrong_token():
    """GET /admin/stats with wrong token → 403."""
    r = client.get("/admin/stats", headers={"x-admin-token": "wrong-token"})
    assert r.status_code == 403


def test_admin_tickets_no_token():
    """GET /admin/tickets without token → 403."""
    r = client.get("/admin/tickets")
    assert r.status_code == 403


def test_admin_stats_correct_token_returns_structure():
    """GET /admin/stats with valid token → 200 with correct schema."""
    r = client.get("/admin/stats", headers={"x-admin-token": ADMIN_TOKEN})
    assert r.status_code == 200
    data = r.json()

    # Required top-level fields
    for field in [
        "total_tickets", "resolved", "escalated", "resolution_rate",
        "avg_latency_ms", "total_tokens", "escalation_triggers",
        "tickets_by_day", "avg_latency_by_day", "fr_coverage",
    ]:
        assert field in data, f"Missing field: {field}"

    # FR coverage must contain all 8 FRs
    fr = data["fr_coverage"]
    for i in range(1, 9):
        assert f"FR{i}" in fr, f"FR{i} missing from fr_coverage"

    # Resolution rate in [0, 1]
    assert 0.0 <= data["resolution_rate"] <= 1.0


def test_admin_tickets_correct_token_returns_list():
    """GET /admin/tickets with valid token → 200, list (possibly empty)."""
    r = client.get("/admin/tickets", headers={"x-admin-token": ADMIN_TOKEN})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── User-facing order lookup ──────────────────────────────────────────────

def test_order_lookup_found():
    """GET /orders/1042 with mocked DB → 200 with order data."""
    mock_order = {
        "order_id": "1042",
        "buyer_name": "Priya Sharma",
        "product_name": "Ceramic Coffee Mug Set",
        "product_category": "kitchen",
        "delivery_status": "delivered",
        "order_amount": 350.0,
        "courier": "BlueDart",
        "is_electronic": False,
    }
    with patch("api.main.order_lookup", return_value=mock_order):
        r = client.get("/orders/1042")
    assert r.status_code == 200
    data = r.json()
    assert data["order_id"] == "1042"
    assert data["buyer_name"] == "Priya Sharma"


def test_order_lookup_not_found():
    """GET /orders/99999 with mocked DB returning None → 404."""
    with patch("api.main.order_lookup", return_value=None):
        r = client.get("/orders/99999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_buyer_orders_found():
    """GET /orders/buyer/1042 with mocked DB → 200 with orders list."""
    mock_orders = [
        {
            "order_id": "1042",
            "buyer_name": "Priya Sharma",
            "product_name": "Ceramic Coffee Mug Set",
            "order_amount": 350.0,
        }
    ]
    with patch("api.main.get_orders_by_buyer", return_value=mock_orders):
        r = client.get("/orders/buyer/1042")
    assert r.status_code == 200
    data = r.json()
    assert data["buyer_id"] == "1042"
    assert len(data["orders"]) == 1


def test_buyer_orders_not_found():
    """GET /orders/buyer/unknown → 404 when no orders returned."""
    with patch("api.main.get_orders_by_buyer", return_value=[]):
        r = client.get("/orders/buyer/unknown_buyer_xyz")
    assert r.status_code == 404


# ── FR8 coverage invariant ────────────────────────────────────────────────

def test_fr8_count_equals_total_tickets():
    """FR8 count should equal total_tickets — every ticket must be logged."""
    r = client.get("/admin/stats", headers={"x-admin-token": ADMIN_TOKEN})
    assert r.status_code == 200
    data = r.json()
    total    = data["total_tickets"]
    fr8_count = data["fr_coverage"].get("FR8", 0)
    assert fr8_count == total, (
        f"FR8 count ({fr8_count}) != total_tickets ({total}). "
        "Every ticket must have at least one logged event."
    )


# ── Admin stats type safety ───────────────────────────────────────────────

def test_admin_stats_types():
    """All numeric fields in AdminStatsResponse must be correct types."""
    r = client.get("/admin/stats", headers={"x-admin-token": ADMIN_TOKEN})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["total_tickets"],    int)
    assert isinstance(data["resolved"],         int)
    assert isinstance(data["escalated"],        int)
    assert isinstance(data["resolution_rate"],  float)
    assert isinstance(data["avg_latency_ms"],   float)
    assert isinstance(data["total_tokens"],     int)
    assert isinstance(data["tickets_by_day"],   dict)
    assert isinstance(data["escalation_triggers"], dict)
