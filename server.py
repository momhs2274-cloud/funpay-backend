from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import random
import string
from datetime import datetime

app = FastAPI(title="FunPay Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "funpay.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id TEXT PRIMARY KEY,
            type TEXT, currency TEXT, amount REAL, description TEXT,
            step INTEGER DEFAULT 1,
            buyer_username TEXT, buyer_tg_id INTEGER,
            seller_username TEXT, seller_tg_id INTEGER,
            created_at TEXT, creator_role TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rating INTEGER, nickname TEXT, gift TEXT, text TEXT,
            tg_id INTEGER, published INTEGER DEFAULT 1, created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER, currency TEXT, network TEXT, address TEXT,
            updated_at TEXT,
            UNIQUE(tg_id, currency, network)
        )
    """)
    conn.commit()
    conn.close()

init_db()


class CreateDeal(BaseModel):
    type: str; currency: str; amount: float
    description: str; username: str; tg_id: int

class JoinDeal(BaseModel):
    username: str; tg_id: int

class UpdateStep(BaseModel):
    step: int

class CreateReview(BaseModel):
    rating: int; nickname: str; gift: str; text: str; tg_id: int

class SeedReview(BaseModel):
    rating: int; nickname: str; gift: str; text: str; created_at: str

class SaveWallet(BaseModel):
    tg_id: int; currency: str; network: str; address: str


def generate_deal_id():
    chars = string.ascii_uppercase + string.digits
    while True:
        deal_id = ''.join(random.choice(chars) for _ in range(8))
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM deals WHERE id = ?", (deal_id,))
        exists = c.fetchone()
        conn.close()
        if not exists:
            return deal_id


def row_to_dict(row):
    if not row: return None
    keys = ['id', 'type', 'currency', 'amount', 'description', 'step',
            'buyer_username', 'buyer_tg_id', 'seller_username', 'seller_tg_id',
            'created_at', 'creator_role']
    return dict(zip(keys, row))


def review_to_dict(row):
    if not row: return None
    keys = ['id', 'rating', 'nickname', 'gift', 'text', 'tg_id', 'published', 'created_at']
    return dict(zip(keys, row))


@app.get("/")
def root():
    return {"status": "ok", "service": "FunPay Backend"}


# ===== DEALS =====
@app.post("/deals")
def create_deal(data: CreateDeal):
    deal_id = generate_deal_id()
    created_at = datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
    if data.type == 'buy':
        buyer_username, buyer_tg_id = data.username, data.tg_id
        seller_username, seller_tg_id = None, None
        creator_role = 'buyer'
    else:
        seller_username, seller_tg_id = data.username, data.tg_id
        buyer_username, buyer_tg_id = None, None
        creator_role = 'seller'
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO deals (id, type, currency, amount, description, step,
                           buyer_username, buyer_tg_id, seller_username, seller_tg_id,
                           created_at, creator_role)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
    """, (deal_id, data.type, data.currency, data.amount, data.description,
          buyer_username, buyer_tg_id, seller_username, seller_tg_id,
          created_at, creator_role))
    conn.commit(); conn.close()
    return {"ok": True, "deal_id": deal_id}


@app.get("/deals/user/{tg_id}")
def get_user_deals(tg_id: int):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT * FROM deals WHERE buyer_tg_id = ? OR seller_tg_id = ? ORDER BY rowid DESC", (tg_id, tg_id))
    rows = c.fetchall(); conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/deals/{deal_id}")
def get_deal(deal_id: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
    row = c.fetchone(); conn.close()
    if not row: raise HTTPException(status_code=404, detail="Deal not found")
    return row_to_dict(row)


@app.post("/deals/{deal_id}/join")
def join_deal(deal_id: str, data: JoinDeal):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
    row = c.fetchone()
    if not row:
        conn.close(); raise HTTPException(status_code=404, detail="Deal not found")
    deal = row_to_dict(row)
    if deal['creator_role'] == 'buyer':
        if deal['seller_tg_id'] and deal['seller_tg_id'] != data.tg_id:
            conn.close(); raise HTTPException(status_code=400, detail="Deal already has seller")
        c.execute("UPDATE deals SET seller_username = ?, seller_tg_id = ? WHERE id = ?",
                  (data.username, data.tg_id, deal_id))
    else:
        if deal['buyer_tg_id'] and deal['buyer_tg_id'] != data.tg_id:
            conn.close(); raise HTTPException(status_code=400, detail="Deal already has buyer")
        c.execute("UPDATE deals SET buyer_username = ?, buyer_tg_id = ? WHERE id = ?",
                  (data.username, data.tg_id, deal_id))
    conn.commit(); conn.close()
    return {"ok": True}


@app.post("/deals/{deal_id}/step")
def update_step(deal_id: str, data: UpdateStep):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("UPDATE deals SET step = ? WHERE id = ?", (data.step, deal_id))
    conn.commit(); conn.close()
    return {"ok": True}


@app.delete("/deals/{deal_id}")
def delete_deal(deal_id: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
    conn.commit(); conn.close()
    return {"ok": True}


# ===== REVIEWS =====
@app.post("/reviews")
def create_review(data: CreateReview):
    if data.rating < 1 or data.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")
    published = 1 if data.rating >= 4 else 0
    created_at = datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("""INSERT INTO reviews (rating, nickname, gift, text, tg_id, published, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (data.rating, data.nickname, data.gift, data.text, data.tg_id, published, created_at))
    conn.commit(); conn.close()
    return {"ok": True, "published": published}


@app.get("/reviews")
def get_reviews():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT * FROM reviews WHERE published = 1 ORDER BY id DESC")
    rows = c.fetchall()
    c.execute("SELECT rating, COUNT(*) FROM reviews GROUP BY rating")
    stats_raw = c.fetchall()
    conn.close()
    stats = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total = 0; total_sum = 0
    for rating, count in stats_raw:
        stats[rating] = count; total += count; total_sum += rating * count
    average = round(total_sum / total, 1) if total > 0 else 0.0
    return {
        "reviews": [review_to_dict(r) for r in rows],
        "stats": {"average": average, "total": total,
                  "5": stats[5], "4": stats[4], "3": stats[3], "2": stats[2], "1": stats[1]}
    }


@app.post("/admin/seed-reviews")
def seed_reviews(reviews: list[SeedReview]):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    added = 0
    for r in reviews:
        published = 1 if r.rating >= 4 else 0
        c.execute("""INSERT INTO reviews (rating, nickname, gift, text, tg_id, published, created_at)
                     VALUES (?, ?, ?, ?, 0, ?, ?)""",
                  (r.rating, r.nickname, r.gift, r.text, published, r.created_at))
        added += 1
    conn.commit(); conn.close()
    return {"ok": True, "added": added}


@app.delete("/admin/reviews")
def clear_reviews():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM reviews")
    conn.commit(); conn.close()
    return {"ok": True}


# ===== WALLETS =====
@app.get("/wallets/{tg_id}")
def get_wallets(tg_id: int):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT tg_id, currency, network, address, updated_at FROM wallets WHERE tg_id = ?", (tg_id,))
    rows = c.fetchall(); conn.close()
    keys = ['tg_id', 'currency', 'network', 'address', 'updated_at']
    return [dict(zip(keys, r)) for r in rows]


@app.post("/wallets")
def save_wallet(data: SaveWallet):
    updated_at = datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    if not data.address.strip():
        c.execute("DELETE FROM wallets WHERE tg_id = ? AND currency = ? AND network = ?",
                  (data.tg_id, data.currency, data.network))
    else:
        c.execute("""INSERT INTO wallets (tg_id, currency, network, address, updated_at)
                     VALUES (?, ?, ?, ?, ?)
                     ON CONFLICT(tg_id, currency, network) DO UPDATE SET
                         address = excluded.address,
                         updated_at = excluded.updated_at""",
                  (data.tg_id, data.currency, data.network, data.address.strip(), updated_at))
    conn.commit(); conn.close()
    return {"ok": True}
