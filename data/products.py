"""
Product Catalog — Cartly's product inventory with policy metadata.

Provides:
  get_all_products()   -> list[dict]
  get_product(id)      -> dict | None
  search_products(q)   -> list[dict]
"""

from __future__ import annotations

PRODUCTS: list[dict] = [
    # Electronics
    {
        "id": "PRD-001",
        "name": "Bluetooth Speaker — SoundMax Pro",
        "category": "electronics",
        "sub_category": "audio",
        "price": 1200,
        "is_returnable": False,
        "return_window_days": 7,
        "return_condition": "Only if defective on arrival (Dead on Arrival)",
        "warranty_months": 12,
        "rating": 4.3,
        "in_stock": True,
        "tags": ["speaker", "bluetooth", "wireless", "audio", "soundmax"],
        "description": "360° surround sound, 12-hour battery, IPX5 water resistant. Perfect for outdoor use.",
        "badge": "Non-Returnable",
    },
    {
        "id": "PRD-002",
        "name": "Wireless Earbuds — SoundBuds Lite",
        "category": "electronics",
        "sub_category": "audio",
        "price": 450,
        "is_returnable": False,
        "return_window_days": 7,
        "return_condition": "Only if defective on arrival",
        "warranty_months": 6,
        "rating": 4.1,
        "in_stock": True,
        "tags": ["earbuds", "wireless", "audio", "tws"],
        "description": "True wireless stereo earbuds with 20-hour total playback, touch controls.",
        "badge": "Non-Returnable",
    },
    {
        "id": "PRD-003",
        "name": "Smart Watch — TimeFit X1",
        "category": "electronics",
        "sub_category": "wearables",
        "price": 2499,
        "is_returnable": False,
        "return_window_days": 7,
        "return_condition": "Only if defective on arrival",
        "warranty_months": 12,
        "rating": 4.5,
        "in_stock": True,
        "tags": ["smartwatch", "wearable", "fitness", "watch"],
        "description": "1.7\" AMOLED display, heart rate monitor, SpO2, 100+ sport modes, 7-day battery.",
        "badge": "Non-Returnable",
    },
    {
        "id": "PRD-004",
        "name": "USB-C Fast Charger — 65W GaN",
        "category": "electronics",
        "sub_category": "accessories",
        "price": 799,
        "is_returnable": False,
        "return_window_days": 7,
        "return_condition": "Only if defective on arrival",
        "warranty_months": 12,
        "rating": 4.6,
        "in_stock": True,
        "tags": ["charger", "usb-c", "gan", "fast charging", "accessories"],
        "description": "65W GaN charger, 3-port (USB-C + 2x USB-A), charges laptop, phone, tablet simultaneously.",
        "badge": "Non-Returnable",
    },
    # Clothing
    {
        "id": "PRD-005",
        "name": "Men's Slim Fit T-Shirt — Pack of 3",
        "category": "clothing",
        "sub_category": "mens",
        "price": 599,
        "is_returnable": True,
        "return_window_days": 30,
        "return_condition": "Unused, unwashed, with tags intact",
        "warranty_months": 0,
        "rating": 4.2,
        "in_stock": True,
        "tags": ["tshirt", "clothing", "mens", "casual"],
        "description": "100% cotton, pre-shrunk, available in S/M/L/XL/XXL. Assorted colours.",
        "badge": "Free Returns",
    },
    {
        "id": "PRD-006",
        "name": "Women's Kurta Set — Festive Collection",
        "category": "clothing",
        "sub_category": "womens",
        "price": 1299,
        "is_returnable": True,
        "return_window_days": 30,
        "return_condition": "Unused, unwashed, with tags intact",
        "warranty_months": 0,
        "rating": 4.4,
        "in_stock": True,
        "tags": ["kurta", "clothing", "womens", "ethnic", "festive"],
        "description": "Embroidered cotton kurta with palazzo pants and dupatta. Sizes XS-XXL.",
        "badge": "Free Returns",
    },
    # Home & Kitchen
    {
        "id": "PRD-007",
        "name": "Stainless Steel Water Bottle — 1 Litre",
        "category": "home",
        "sub_category": "kitchen",
        "price": 349,
        "is_returnable": True,
        "return_window_days": 30,
        "return_condition": "Unused, in original packaging",
        "warranty_months": 0,
        "rating": 4.7,
        "in_stock": True,
        "tags": ["bottle", "water bottle", "stainless steel", "kitchen", "home"],
        "description": "BPA-free, double-wall insulated, keeps cold 24 hrs / hot 12 hrs. Leak-proof lid.",
        "badge": "30-Day Returns",
    },
    {
        "id": "PRD-008",
        "name": "Non-Stick Cookware Set — 5 Piece",
        "category": "home",
        "sub_category": "kitchen",
        "price": 1899,
        "is_returnable": True,
        "return_window_days": 30,
        "return_condition": "Unused, in original packaging",
        "warranty_months": 12,
        "rating": 4.3,
        "in_stock": True,
        "tags": ["cookware", "pan", "kitchen", "non-stick", "home"],
        "description": "PFOA-free granite coating, induction compatible, includes 3 pans + 1 kadai + 1 tawa.",
        "badge": "30-Day Returns",
    },
    # Books
    {
        "id": "PRD-009",
        "name": "Atomic Habits — James Clear",
        "category": "books",
        "sub_category": "self-help",
        "price": 299,
        "is_returnable": True,
        "return_window_days": 30,
        "return_condition": "Unread, no damage, with original packaging",
        "warranty_months": 0,
        "rating": 4.8,
        "in_stock": True,
        "tags": ["book", "habits", "self-help", "james clear", "productivity"],
        "description": "Bestselling guide to building good habits and breaking bad ones. Paperback.",
        "badge": "30-Day Returns",
    },
    # Sports
    {
        "id": "PRD-010",
        "name": "Yoga Mat — Anti-Slip 6mm",
        "category": "sports",
        "sub_category": "fitness",
        "price": 549,
        "is_returnable": True,
        "return_window_days": 30,
        "return_condition": "Unused, clean, rolled in original packaging",
        "warranty_months": 0,
        "rating": 4.5,
        "in_stock": True,
        "tags": ["yoga", "mat", "fitness", "sports", "exercise"],
        "description": "Extra-thick 6mm TPE foam, anti-slip texture, carrying strap included. 183cm x 61cm.",
        "badge": "30-Day Returns",
    },
    # Beauty
    {
        "id": "PRD-011",
        "name": "Vitamin C Face Serum — 30ml",
        "category": "beauty",
        "sub_category": "skincare",
        "price": 399,
        "is_returnable": True,
        "return_window_days": 30,
        "return_condition": "Sealed/unopened only",
        "warranty_months": 0,
        "rating": 4.2,
        "in_stock": True,
        "tags": ["serum", "vitamin c", "skincare", "beauty", "face"],
        "description": "20% Vitamin C + Hyaluronic Acid, brightening formula, dermatologist tested.",
        "badge": "Sealed Only Returns",
    },
    {
        "id": "PRD-012",
        "name": "Hair Dryer — 2000W Professional",
        "category": "electronics",
        "sub_category": "personal_care",
        "price": 899,
        "is_returnable": False,
        "return_window_days": 7,
        "return_condition": "Only if defective on arrival",
        "warranty_months": 12,
        "rating": 4.0,
        "in_stock": False,
        "tags": ["hair dryer", "electronics", "personal care", "2000w"],
        "description": "2000W with ionic technology, 3 heat settings, 2 speed settings, cool shot button.",
        "badge": "Non-Returnable",
    },
]

CATEGORIES = sorted(set(p["category"] for p in PRODUCTS))


def get_all_products() -> list[dict]:
    return PRODUCTS


def get_product(product_id: str) -> dict | None:
    for p in PRODUCTS:
        if p["id"] == product_id:
            return p
    return None


def search_products(query: str) -> list[dict]:
    """Simple keyword search across name, tags, description, category."""
    q = query.lower()
    results = []
    for p in PRODUCTS:
        score = 0
        if q in p["name"].lower():
            score += 3
        for tag in p["tags"]:
            if q in tag or tag in q:
                score += 2
        if q in p["description"].lower():
            score += 1
        if q in p["category"]:
            score += 1
        if score > 0:
            results.append((score, p))
    results.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in results]


def get_products_by_category(category: str) -> list[dict]:
    return [p for p in PRODUCTS if p["category"] == category]
