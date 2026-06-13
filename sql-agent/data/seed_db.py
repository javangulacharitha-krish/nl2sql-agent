"""
Seed the ecommerce SQLite database with realistic data.
"""
import sqlite3
import random
from datetime import datetime, timedelta
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "ecommerce.db")

FIRST_NAMES = ["Alice", "Bob", "Carol", "David", "Eve", "Frank", "Grace", "Hank",
               "Ivy", "Jack", "Karen", "Leo", "Mia", "Nathan", "Olivia", "Paul",
               "Quinn", "Rachel", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xander",
               "Yara", "Zane"]
LAST_NAMES  = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
               "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson",
               "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee"]

CATEGORIES  = ["Electronics", "Clothing", "Books", "Home & Garden", "Sports",
               "Beauty", "Toys", "Automotive", "Food & Beverage", "Office Supplies"]

PRODUCTS    = [
    ("Wireless Headphones", "Electronics", 79.99),
    ("Bluetooth Speaker", "Electronics", 49.99),
    ("4K Smart TV", "Electronics", 499.99),
    ("Laptop Stand", "Electronics", 29.99),
    ("USB-C Hub", "Electronics", 39.99),
    ("Running Shoes", "Clothing", 89.99),
    ("Winter Jacket", "Clothing", 129.99),
    ("Cotton T-Shirt", "Clothing", 19.99),
    ("Denim Jeans", "Clothing", 59.99),
    ("Python Programming Book", "Books", 34.99),
    ("Machine Learning Guide", "Books", 44.99),
    ("Garden Hose", "Home & Garden", 24.99),
    ("Yoga Mat", "Sports", 29.99),
    ("Protein Powder", "Sports", 54.99),
    ("Face Moisturizer", "Beauty", 22.99),
    ("LEGO Set", "Toys", 59.99),
    ("Car Phone Mount", "Automotive", 14.99),
    ("Coffee Beans 1kg", "Food & Beverage", 18.99),
    ("Desk Organizer", "Office Supplies", 16.99),
    ("Mechanical Keyboard", "Electronics", 119.99),
]

STATUSES = ["delivered", "shipped", "processing", "cancelled", "returned"]


def seed():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # ── Tables ────────────────────────────────────────────────────────────────
    cur.executescript("""
        DROP TABLE IF EXISTS reviews;
        DROP TABLE IF EXISTS order_items;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS users;

        CREATE TABLE users (
            user_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            email      TEXT UNIQUE NOT NULL,
            city       TEXT,
            country    TEXT DEFAULT 'USA',
            created_at TEXT
        );

        CREATE TABLE products (
            product_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            category    TEXT,
            price       REAL NOT NULL,
            stock       INTEGER DEFAULT 100
        );

        CREATE TABLE orders (
            order_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES users(user_id),
            status      TEXT,
            total       REAL,
            created_at  TEXT
        );

        CREATE TABLE order_items (
            item_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id   INTEGER REFERENCES orders(order_id),
            product_id INTEGER REFERENCES products(product_id),
            quantity   INTEGER,
            unit_price REAL
        );

        CREATE TABLE reviews (
            review_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER REFERENCES products(product_id),
            user_id    INTEGER REFERENCES users(user_id),
            rating     INTEGER CHECK(rating BETWEEN 1 AND 5),
            comment    TEXT,
            created_at TEXT
        );
    """)

    # ── Users ─────────────────────────────────────────────────────────────────
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
              "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose"]
    users = []
    for i in range(50):
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        email = f"{fn.lower()}.{ln.lower()}{i}@example.com"
        city  = random.choice(cities)
        created = (datetime(2023, 1, 1) + timedelta(days=random.randint(0, 500))).isoformat()
        users.append((fn + " " + ln, email, city, "USA", created))
    cur.executemany("INSERT INTO users (name,email,city,country,created_at) VALUES (?,?,?,?,?)", users)

    # ── Products ──────────────────────────────────────────────────────────────
    cur.executemany("INSERT INTO products (name,category,price,stock) VALUES (?,?,?,?)",
                    [(p[0], p[1], p[2], random.randint(10, 200)) for p in PRODUCTS])

    # ── Orders + Items ────────────────────────────────────────────────────────
    for order_id_idx in range(200):
        user_id    = random.randint(1, 50)
        status     = random.choices(STATUSES, weights=[60, 15, 10, 10, 5])[0]
        n_items    = random.randint(1, 4)
        created    = (datetime(2023, 6, 1) + timedelta(days=random.randint(0, 365))).isoformat()
        total      = 0.0
        items      = []
        for _ in range(n_items):
            pid   = random.randint(1, len(PRODUCTS))
            qty   = random.randint(1, 3)
            price = PRODUCTS[pid - 1][2]
            total += qty * price
            items.append((pid, qty, price))
        cur.execute("INSERT INTO orders (user_id,status,total,created_at) VALUES (?,?,?,?)",
                    (user_id, status, round(total, 2), created))
        oid = cur.lastrowid
        cur.executemany("INSERT INTO order_items (order_id,product_id,quantity,unit_price) VALUES (?,?,?,?)",
                        [(oid, it[0], it[1], it[2]) for it in items])

    # ── Reviews ───────────────────────────────────────────────────────────────
    comments = [
        "Excellent product!", "Good value for money.", "Arrived quickly.",
        "Not what I expected.", "Would buy again.", "Decent quality.",
        "Fast shipping, happy with purchase.", "A bit overpriced but works well.",
        "Five stars!", "Works as described."
    ]
    for _ in range(150):
        pid     = random.randint(1, len(PRODUCTS))
        uid     = random.randint(1, 50)
        rating  = random.choices([1,2,3,4,5], weights=[5,5,15,35,40])[0]
        comment = random.choice(comments)
        created = (datetime(2023, 6, 1) + timedelta(days=random.randint(0, 365))).isoformat()
        cur.execute("INSERT INTO reviews (product_id,user_id,rating,comment,created_at) VALUES (?,?,?,?,?)",
                    (pid, uid, rating, comment, created))

    conn.commit()
    conn.close()
    print(f"[seed_db] Database seeded → {DB_PATH}")


if __name__ == "__main__":
    seed()
