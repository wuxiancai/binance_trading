import sqlite3
import os
from typing import Optional, List, Tuple, Dict, Any

from config import config

os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS klines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    interval TEXT, -- 可为空以兼容旧数据
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    pnl REAL DEFAULT 0,
    simulate INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL, -- long / short / flat
    qty REAL NOT NULL,
    entry_price REAL NOT NULL,
    ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_profits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE, -- e.g. '2024-09-22'
    trade_count INTEGER DEFAULT 0,
    profit REAL DEFAULT 0.0,
    profit_rate REAL DEFAULT 0.0,
    loss_count INTEGER DEFAULT 0,
    profit_count INTEGER DEFAULT 0
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    # 确保基础表存在
    cur.executescript(SCHEMA)
    # 迁移：旧库无 interval 列时新增
    cur.execute("PRAGMA table_info(klines)")
    cols = {r[1] for r in cur.fetchall()}
    if "interval" not in cols:
        cur.execute("ALTER TABLE klines ADD COLUMN interval TEXT")
    # 补建索引（此时 interval 一定存在）
    cur.execute("CREATE INDEX IF NOT EXISTS idx_klines_sym_itv_time ON klines(symbol, interval, open_time)")
    conn.commit()


def init_db():
    conn = get_conn()
    _migrate_schema(conn)
    
    # 数据库迁移：为现有表添加新字段
    cur = conn.cursor()
    try:
        # 检查daily_profits表字段
        cur.execute("PRAGMA table_info(daily_profits)")
        daily_columns = [row[1] for row in cur.fetchall()]
        
        if 'loss_count' not in daily_columns:
            cur.execute("ALTER TABLE daily_profits ADD COLUMN loss_count INTEGER DEFAULT 0")
            
        if 'profit_count' not in daily_columns:
            cur.execute("ALTER TABLE daily_profits ADD COLUMN profit_count INTEGER DEFAULT 0")
            
        if 'total_fees' not in daily_columns:
            cur.execute("ALTER TABLE daily_profits ADD COLUMN total_fees REAL DEFAULT 0.0")
            
        if 'initial_balance' not in daily_columns:
            cur.execute("ALTER TABLE daily_profits ADD COLUMN initial_balance REAL DEFAULT 0.0")
        
        # 检查trades表字段
        cur.execute("PRAGMA table_info(trades)")
        trade_columns = [row[1] for row in cur.fetchall()]
        
        if 'fee' not in trade_columns:
            cur.execute("ALTER TABLE trades ADD COLUMN fee REAL DEFAULT 0.0")
            
        conn.commit()
    except Exception as e:
        print(f"数据库迁移警告: {e}")
    
    conn.close()


def insert_kline(rows: List[Tuple]):
    """插入K线。
    兼容两种元组长度：
    - 9列: (symbol, interval, open_time, open, high, low, close, volume, close_time)
    - 8列: (symbol, open_time, open, high, low, close, volume, close_time) -> 自动补上当前 config.INTERVAL
    """
    conn = get_conn()
    cur = conn.cursor()
    # 统一扩展为包含 interval 的9列
    normalized: List[Tuple] = []
    for r in rows:
        if len(r) == 9:
            normalized.append(r)
        elif len(r) == 8:
            symbol, open_time, o, h, l, c, v, ct = r
            normalized.append((symbol, config.INTERVAL, open_time, o, h, l, c, v, ct))
        else:
            raise ValueError("insert_kline expects tuple of len 8 or 9")
    cur.executemany(
        """
        INSERT INTO klines(symbol, interval, open_time, open, high, low, close, volume, close_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        normalized,
    )
    conn.commit()
    conn.close()


def latest_kline_time(symbol: str, interval: Optional[str] = None) -> Optional[int]:
    itv = interval or config.INTERVAL
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT MAX(open_time) AS t FROM klines WHERE symbol=? AND interval=?", (symbol, itv))
    row = cur.fetchone()
    conn.close()
    return row["t"] if row and row["t"] is not None else None


def fetch_klines(symbol: str, limit: int = 500, interval: Optional[str] = None) -> List[Dict[str, Any]]:
    itv = interval or config.INTERVAL
    conn = get_conn()
    cur = conn.cursor()
    # 取最近 limit 条（DESC），再反转为时间升序给指标使用
    cur.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines WHERE symbol=? AND interval=? ORDER BY open_time DESC LIMIT ?",
        (symbol, itv, limit),
    )
    rows = cur.fetchall()
    conn.close()
    ordered = list(reversed([dict(r) for r in rows]))
    return ordered


def log(level: str, message: str):
    conn = get_conn()
    cur = conn.cursor()
    import time

    cur.execute("INSERT INTO logs(ts, level, message) VALUES (?, ?, ?)", (int(time.time() * 1000), level, message))
    conn.commit()
    conn.close()


def add_trade(ts: int, symbol: str, side: str, qty: float, price: float, pnl: float = 0.0, simulate: bool = True, fee: float = 0.0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO trades(ts, symbol, side, qty, price, pnl, simulate, fee) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, symbol, side, qty, price, pnl, 1 if simulate else 0, fee),
    )
    conn.commit()
    conn.close()


def set_position(symbol: str, side: str, qty: float, entry_price: float, ts: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
    cur.execute(
        "INSERT INTO positions(symbol, side, qty, entry_price, ts) VALUES (?, ?, ?, ?, ?)",
        (symbol, side, qty, entry_price, ts),
    )
    conn.commit()
    conn.close()


def get_position(symbol: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol, side, qty, entry_price, ts FROM positions WHERE symbol=?", (symbol,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def close_position(symbol: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
    conn.commit()
    conn.close()


def get_daily_profit(date: str) -> Optional[Dict[str, Any]]:
    """获取指定日期的盈利记录"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM daily_profits WHERE date=?", (date,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_daily_profits(limit: int = 30) -> List[Dict[str, Any]]:
    """获取最近的盈利记录，按日期降序排列"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM daily_profits ORDER BY date DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_daily_profit(date: str, trade_count: int, profit: float, profit_rate: float, loss_count: int = 0, profit_count: int = 0, total_fees: float = 0.0, initial_balance: float = 0.0):
    """更新或创建指定日期的盈利记录"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM daily_profits WHERE date=?", (date,))
    row = cur.fetchone()
    
    if row:
        cur.execute(
            "UPDATE daily_profits SET trade_count=?, profit=?, profit_rate=?, loss_count=?, profit_count=?, total_fees=?, initial_balance=? WHERE date=?",
            (trade_count, profit, profit_rate, loss_count, profit_count, total_fees, initial_balance, date)
        )
    else:
        cur.execute(
            "INSERT INTO daily_profits(date, trade_count, profit, profit_rate, loss_count, profit_count, total_fees, initial_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (date, trade_count, profit, profit_rate, loss_count, profit_count, total_fees, initial_balance)
        )
    
    conn.commit()
    conn.close()