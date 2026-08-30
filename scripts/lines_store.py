"""
기능 1-A. 수동 지지선/저항선/추세선 저장소 (SQLite)

자동 검출은 하지 않음 - 전부 사용자가 차트 위에서 직접 그은 선만 다룬다.
세션이 끝나도 유지되도록 로컬 SQLite 파일에 저장 (기획서 5번 데이터 저장 파트).

라인 종류(line_type):
- "support"    : 수평 지지선 (근접 시 매수 후보 신호)
- "resistance" : 수평 저항선 (근접 시 매도 후보 신호)
- "trend"      : 추세선, 두 점(time1,price1)-(time2,price2)으로 정의
                 (근접 시 매도 후보 신호로 취급 - 기획서 스펙)
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "manual_lines.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    line_type TEXT NOT NULL CHECK (line_type IN ('support', 'resistance', 'trend')),
    time1 TEXT,       -- trend 라인만 사용 (YYYY-MM-DD)
    price1 REAL NOT NULL,
    time2 TEXT,       -- trend 라인만 사용
    price2 REAL,      -- trend 라인만 사용
    created_at TEXT NOT NULL
);
"""


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def add_horizontal_line(symbol: str, interval: str, line_type: str, price: float) -> int:
    assert line_type in ("support", "resistance")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO lines (symbol, interval, line_type, price1, created_at) VALUES (?, ?, ?, ?, ?)",
            (symbol, interval, line_type, price, datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def add_trend_line(symbol: str, interval: str, time1: str, price1: float, time2: str, price2: float) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO lines (symbol, interval, line_type, time1, price1, time2, price2, created_at) "
            "VALUES (?, ?, 'trend', ?, ?, ?, ?, ?)",
            (symbol, interval, time1, price1, time2, price2, datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def list_lines(symbol: str, interval: str) -> list:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM lines WHERE symbol = ? AND interval = ? ORDER BY id",
            (symbol, interval),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_line(line_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM lines WHERE id = ?", (line_id,))


if __name__ == "__main__":
    print(f"DB 경로: {DB_PATH}")
    print(f"현재 저장된 라인: {list_lines('BTCUSDT', '1d')}")
