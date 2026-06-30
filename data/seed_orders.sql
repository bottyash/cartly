-- ============================================================
-- Cartly POC — Mock Order Database Seed Data (Sprint 2 Extended)
-- Covers demo tickets + additional buyers for admin dashboard
-- ============================================================

CREATE TABLE IF NOT EXISTS orders (
    order_id        VARCHAR(20)     PRIMARY KEY,
    buyer_name      VARCHAR(100)    NOT NULL,
    product_name    VARCHAR(200)    NOT NULL,
    product_category VARCHAR(50)   NOT NULL,
    order_status    VARCHAR(50)     NOT NULL,
    delivery_status VARCHAR(50)     NOT NULL,
    order_date      DATE            NOT NULL,
    expected_delivery DATE          NOT NULL,
    actual_delivery DATE,
    order_amount    DECIMAL(10,2)   NOT NULL,
    payment_status  VARCHAR(50)     NOT NULL,
    courier         VARCHAR(50),
    is_electronic   BOOLEAN         DEFAULT FALSE,
    notes           TEXT
);

-- ── Sprint 1 Demo Tickets ────────────────────────────────────────────────

INSERT INTO orders VALUES ('1042','Priya Sharma','Ceramic Coffee Mug Set (6 pieces)','kitchen','delivered','delivered','2026-06-25','2026-06-28','2026-06-29',350.00,'paid','BlueDart',FALSE,'Customer reported item arrived with 3 cracked mugs due to poor packaging') ON CONFLICT DO NOTHING;
INSERT INTO orders VALUES ('1077','Rahul Mehta','Bluetooth Speaker — SoundMax Pro','electronics','shipped','not_delivered','2026-07-01','2026-07-05',NULL,1200.00,'paid','Delhivery',TRUE,'Package marked out-for-delivery for 5 days with no update from courier') ON CONFLICT DO NOTHING;
INSERT INTO orders VALUES ('1090','Ananya Patel','Wireless Earbuds — SoundBuds Lite','electronics','delivered','delivered','2026-07-03','2026-07-06','2026-07-07',450.00,'paid','DTDC',TRUE,'Buyer claims 30-day return window; electronics are non-returnable per §5.4') ON CONFLICT DO NOTHING;
INSERT INTO orders VALUES ('1099','Vikram Singh','Sports Running Shoes','footwear','delivered','delivered','2026-07-05','2026-07-08','2026-07-09',300.00,'paid','Ekart',FALSE,'Ticket contains legal threat language — auto-escalation mandatory per §8.1') ON CONFLICT DO NOTHING;

-- ── Sprint 2 Extended Data — More buyers for admin dashboard ─────────────

-- Meera Nair (buyer005)
INSERT INTO orders VALUES ('1100','Meera Nair','Cotton Saree — Handloom Premium','clothing','delivered','delivered','2026-07-07','2026-07-10','2026-07-11',899.00,'paid','Ekart',FALSE,'Wrong colour received, different from listing') ON CONFLICT DO NOTHING;
INSERT INTO orders VALUES ('1101','Meera Nair','Yoga Mat — Extra Thick 8mm','fitness','delivered','delivered','2026-07-09','2026-07-12','2026-07-13',480.00,'paid','BlueDart',FALSE,'Item defective, surface peeling after first use') ON CONFLICT DO NOTHING;

-- Arjun Reddy (buyer006)
INSERT INTO orders VALUES ('1102','Arjun Reddy','Mechanical Keyboard — RGB Pro','electronics','delivered','delivered','2026-07-06','2026-07-09','2026-07-10',2200.00,'paid','Delhivery',TRUE,'Keys sticking, manufacturing defect on arrival') ON CONFLICT DO NOTHING;
INSERT INTO orders VALUES ('1103','Arjun Reddy','USB-C Hub 7-in-1','electronics','delivered','delivered','2026-07-08','2026-07-11','2026-07-12',349.00,'paid','DTDC',TRUE,'HDMI port not working on arrival') ON CONFLICT DO NOTHING;

-- Sneha Gupta (buyer007)
INSERT INTO orders VALUES ('1104','Sneha Gupta','Steel Water Bottle 1L','kitchen','delivered','delivered','2026-07-10','2026-07-12','2026-07-13',299.00,'paid','Ekart',FALSE,'Dent on the body, looks like it was dropped during transit') ON CONFLICT DO NOTHING;
INSERT INTO orders VALUES ('1105','Sneha Gupta','Face Serum — Vitamin C 30ml','beauty','delivered','delivered','2026-07-11','2026-07-13','2026-07-14',650.00,'paid','BlueDart',FALSE,'Wrong product delivered, different brand') ON CONFLICT DO NOTHING;

-- Karthik Iyer (buyer008)
INSERT INTO orders VALUES ('1106','Karthik Iyer','LED Desk Lamp — Foldable','home','shipped','not_delivered','2026-07-12','2026-07-15',NULL,420.00,'paid','Delhivery',FALSE,'Tracking stuck for 4 days') ON CONFLICT DO NOTHING;
INSERT INTO orders VALUES ('1107','Karthik Iyer','Wireless Mouse — Ergonomic','electronics','delivered','delivered','2026-07-10','2026-07-13','2026-07-14',580.00,'paid','DTDC',TRUE,'Right click not functioning') ON CONFLICT DO NOTHING;

-- Deepika Sharma (buyer009)
INSERT INTO orders VALUES ('1108','Deepika Sharma','Stainless Steel Cookware Set','kitchen','delivered','delivered','2026-07-08','2026-07-11','2026-07-12',1450.00,'paid','Ekart',FALSE,'Two pots missing from the set') ON CONFLICT DO NOTHING;
INSERT INTO orders VALUES ('1109','Deepika Sharma','Air Fryer — 4.5L Capacity','kitchen','delivered','delivered','2026-07-13','2026-07-15','2026-07-16',3200.00,'paid','BlueDart',TRUE,'Does not heat up, DOA') ON CONFLICT DO NOTHING;

-- Rohan Verma (buyer010)
INSERT INTO orders VALUES ('1110','Rohan Verma','Cricket Bat — Kashmir Willow','sports','delivered','delivered','2026-07-09','2026-07-12','2026-07-13',750.00,'paid','Delhivery',FALSE,'Crack near the toe of the bat') ON CONFLICT DO NOTHING;
INSERT INTO orders VALUES ('1111','Rohan Verma','Protein Powder — Whey 1kg','fitness','delivered','delivered','2026-07-14','2026-07-16','2026-07-17',1800.00,'paid','DTDC',FALSE,'Seal broken, product may be tampered') ON CONFLICT DO NOTHING;
