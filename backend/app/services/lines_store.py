"""
기능 1-A. 수동 지지선/저항선/추세선 저장소 (SQLite)

자동 검출은 하지 않음 - 전부 사용자가 차트 위에서 직접 그은 선만 다룬다.
세션이 끝나도 유지되도록 로컬 SQLite 파일에 저장 (기획서 5번 데이터 저장 파트).

라인 종류(line_type):
- "horizontal" : 수평선. 지지/저항을 타입으로 고정하지 않음 - 캔들이 선 위에 있으면
                 지지, 아래 있으면 저항으로 그때그때 동적으로 판정 (manual_lines.py 참고)
- "trend"      : 추세선, 두 점(time1,price1)-(time2,price2)으로 정의
                 (근접 시 매도 후보 신호로 취급 - 기획서 스펙)
- "zone"       : 존(가격 구간 직사각형). 새 컬럼 없이 기존 컬럼을 재사용한다:
                 time1=시작 시간, time2=끝 시간, price1=구간 상단, price2=구간 하단
                 (항상 price1 > price2, time1 < time2). 지금은 저장/그리기/삭제만 하고
                 신호 판정에는 쓰이지 않는다(manual_lines.py가 건너뜀).
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# [이식 시 기계적 수정] config.py와 동일한 이유로 parent 4번 - Streamlit(scripts/)
# 쪽과 완전히 같은 manual_lines.db 파일을 가리킨다(DB 파일/스키마 자체는 무변경).
DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "merged" / "manual_lines.db"

_TABLE_SQL = """
CREATE TABLE {name} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    line_type TEXT NOT NULL CHECK (line_type IN ('horizontal', 'trend', 'zone')),
    time1 TEXT,       -- trend: 시작점 / zone: 시작 시간 (YYYY-MM-DD)
    price1 REAL NOT NULL,  -- zone: 구간 상단 가격
    time2 TEXT,       -- trend: 끝점 / zone: 끝 시간
    price2 REAL,      -- trend: 끝점 가격 / zone: 구간 하단 가격
    created_at TEXT NOT NULL
)
"""
_SCHEMA = _TABLE_SQL.format(name="IF NOT EXISTS lines") + ";"
_COLUMNS = "id, symbol, interval, line_type, time1, price1, time2, price2, created_at"


def _lines_table_sql(conn) -> str | None:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'lines'").fetchone()
    return row[0] if row else None


def _needs_zone_migration(conn) -> bool:
    sql = _lines_table_sql(conn)
    return sql is not None and "'zone'" not in sql


def _migrate_allow_zone(conn) -> None:
    """구 lines 테이블(CHECK가 horizontal/trend만 허용)을 zone도 허용하는 새 테이블로 교체.

    SQLite는 CHECK를 ALTER로 못 바꿔서 새 테이블 생성 -> 행 복사(id 유지) -> 구 테이블
    삭제 -> 이름 변경 순서로 한 트랜잭션에서 처리한다. 이미 zone이 허용된 DB면 아무것도
    안 하므로 여러 번 호출해도 안전하다. 구 테이블의 인덱스/트리거는 새 테이블에 같은
    SQL로 다시 만들고, AUTOINCREMENT 카운터(sqlite_sequence)도 이어받아 삭제된 id가
    재사용되지 않게 한다.
    """
    if not _needs_zone_migration(conn):
        return
    conn.commit()
    conn.isolation_level = None  # 명시적 BEGIN/COMMIT으로 DDL까지 한 트랜잭션에 묶는다
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if not _needs_zone_migration(conn):  # 락을 기다리는 사이 다른 연결이 이미 마이그레이션함
                conn.execute("ROLLBACK")
                return
            aux_sql = [
                r[0] for r in conn.execute(
                    "SELECT sql FROM sqlite_master WHERE tbl_name = 'lines' "
                    "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
                )
            ]
            seq_row = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'lines'").fetchone()
            old_seq = seq_row[0] if seq_row else 0

            conn.execute(_TABLE_SQL.format(name="lines_new"))
            conn.execute(f"INSERT INTO lines_new ({_COLUMNS}) SELECT {_COLUMNS} FROM lines")
            conn.execute("DROP TABLE lines")
            conn.execute("ALTER TABLE lines_new RENAME TO lines")

            cur = conn.execute("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'lines'", (old_seq,))
            if cur.rowcount == 0:
                conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('lines', ?)", (old_seq,))
            for sql in aux_sql:
                conn.execute(sql)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = ""  # 기본(암시적 트랜잭션) 동작으로 복귀


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    _migrate_allow_zone(conn)
    conn.execute(_SCHEMA)
    return conn


def add_horizontal_line(symbol: str, interval: str, price: float) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO lines (symbol, interval, line_type, price1, created_at) VALUES (?, ?, 'horizontal', ?, ?)",
            (symbol, interval, price, datetime.now(timezone.utc).isoformat()),
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


def add_zone(symbol: str, interval: str, time1: str, time2: str, price1: float, price2: float) -> int:
    """존 저장. 호출 순서와 무관하게 항상 price1(상단) > price2(하단), time1 < time2로
    정규화해서 저장한다(YYYY-MM-DD 문자열은 사전순 = 시간순)."""
    top, bottom = max(price1, price2), min(price1, price2)
    start, end = min(time1, time2), max(time1, time2)
    if top == bottom or start == end:
        raise ValueError("존의 가격 구간과 시간 구간은 0보다 커야 함")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO lines (symbol, interval, line_type, time1, price1, time2, price2, created_at) "
            "VALUES (?, ?, 'zone', ?, ?, ?, ?, ?)",
            (symbol, interval, start, top, end, bottom, datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def update_trend(line_id: int, time1: str, price1: float, time2: str, price2: float) -> bool:
    """추세선 두 점을 수정한다(끝점 드래그). id는 그대로 두고 created_at은 "수정한 시각"으로
    갱신한다 - 신호의 ref_created_at이 "이 모양이 정해진 시점"을 뜻하게 하기 위함(존과 동일).
    값은 있는 그대로 저장한다(정규화/검증은 API 계층). 대상이 추세선이 아니거나 없으면
    False(아무것도 안 바꿈)."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE lines SET time1 = ?, price1 = ?, time2 = ?, price2 = ?, created_at = ? "
            "WHERE id = ? AND line_type = 'trend'",
            (time1, price1, time2, price2, datetime.now(timezone.utc).isoformat(), line_id),
        )
        return cur.rowcount > 0


def update_zone(line_id: int, time1: str, time2: str, price1: float, price2: float) -> bool:
    """존 모양(시간/가격 구간)을 수정한다. id는 그대로 두고 created_at은 "수정한 시각"으로
    갱신한다 - 존 신호의 ref_created_at이 "이 모양이 정해진 시점"을 뜻하게 해서, 백테스트가
    사후 신호를 걸러내는 기준으로 쓰기 위함. add_zone과 같은 정규화(price1 > price2,
    time1 < time2)를 한다. 대상이 존이 아니거나 없으면 False(아무것도 안 바꿈)."""
    top, bottom = max(price1, price2), min(price1, price2)
    start, end = min(time1, time2), max(time1, time2)
    if top == bottom or start == end:
        raise ValueError("존의 가격 구간과 시간 구간은 0보다 커야 함")
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE lines SET time1 = ?, price1 = ?, time2 = ?, price2 = ?, created_at = ? "
            "WHERE id = ? AND line_type = 'zone'",
            (start, top, end, bottom, datetime.now(timezone.utc).isoformat(), line_id),
        )
        return cur.rowcount > 0


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
