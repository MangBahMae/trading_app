"""
기능1 개편 3a단계: 존(직사각형) 저장/API/신호 보호 검증.

- lines 테이블 마이그레이션(CHECK에 'zone' 추가): 행/id/인덱스/트리거/AUTOINCREMENT 보존,
  재실행 안전, 실패 시 롤백
- POST /api/lines/zone 생성/조회/삭제와 잘못된 값 거부
- 존이 DB에 있어도 /api/dashboard의 signals가 한 건도 달라지지 않는 것

실데이터 manual_lines.db는 건드리지 않는다 - lines_store.DB_PATH를 임시 파일로 바꿔서 쓴다.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app  # app.services.dashboard가 services 경로를 sys.path에 넣는다

import lines_store  # noqa: E402  (dashboard.py가 쓰는 것과 같은 bare 모듈 객체)
import manual_lines  # noqa: E402

OLD_SCHEMA = """
CREATE TABLE lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    line_type TEXT NOT NULL CHECK (line_type IN ('horizontal', 'trend')),
    time1 TEXT,
    price1 REAL NOT NULL,
    time2 TEXT,
    price2 REAL,
    created_at TEXT NOT NULL
)
"""
ROWS = [
    (3, "BTCUSDT", "1d", "horizontal", None, 28662.747709763014, None, None, "2026-09-29T04:45:06+00:00"),
    (7, "BTCUSDT", "1d", "trend", "2026-01-01", 100.5, "2026-02-01", 120.25, "2026-09-30T01:02:03+00:00"),
    (9, "ETHUSDT", "4h", "horizontal", None, 1.5, None, None, "2026-10-01T00:00:00+00:00"),
]


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "manual_lines.db"
    monkeypatch.setattr(lines_store, "DB_PATH", path)
    return path


def _make_old_db(path):
    conn = sqlite3.connect(path)
    conn.execute(OLD_SCHEMA)
    conn.execute("CREATE INDEX idx_lines_symbol ON lines (symbol, interval)")
    conn.execute(
        "CREATE TRIGGER trg_lines_noop AFTER INSERT ON lines BEGIN SELECT 1; END"
    )
    conn.executemany("INSERT INTO lines VALUES (?,?,?,?,?,?,?,?,?)", ROWS)
    # id 9보다 큰 id를 쓰고 지워서 sqlite_sequence가 max(id)보다 커진 상태를 만든다(실데이터도 이 상태)
    conn.execute(
        "INSERT INTO lines (id, symbol, interval, line_type, price1, created_at) VALUES (24, 'x', 'x', 'horizontal', 1, 't')"
    )
    conn.execute("DELETE FROM lines WHERE id = 24")
    conn.commit()
    assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name='lines'").fetchone()[0] == 24
    conn.close()


def _dump(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT * FROM lines ORDER BY id").fetchall()
    finally:
        conn.close()


# --- 마이그레이션 ---

def test_old_schema_rejects_zone_before_migration(tmp_db):
    _make_old_db(tmp_db)
    conn = sqlite3.connect(tmp_db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO lines (symbol, interval, line_type, price1, created_at) VALUES ('a','b','zone',1,'t')")
    conn.close()


def test_migration_preserves_rows_ids_index_trigger_and_sequence(tmp_db):
    _make_old_db(tmp_db)
    before = _dump(tmp_db)

    lines_store._connect().close()

    assert _dump(tmp_db) == before  # 전 컬럼, id 그대로
    conn = sqlite3.connect(tmp_db)
    names = {(r[0], r[1]) for r in conn.execute("SELECT type, name FROM sqlite_master")}
    assert ("index", "idx_lines_symbol") in names and ("trigger", "trg_lines_noop") in names
    assert ("table", "lines_new") not in names
    assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name='lines'").fetchone()[0] == 24
    conn.close()

    # AUTOINCREMENT 카운터를 이어받아 지워진 id(24)가 재사용되지 않는다
    new_id = lines_store.add_zone("BTCUSDT", "1d", "2026-01-01", "2026-02-01", 200.0, 100.0)
    assert new_id == 25


def test_migration_is_idempotent_and_keeps_zone_rows(tmp_db):
    _make_old_db(tmp_db)
    lines_store._connect().close()
    zone_id = lines_store.add_zone("BTCUSDT", "1d", "2026-01-01", "2026-02-01", 200.0, 100.0)
    snapshot = _dump(tmp_db)
    schema_sql = sqlite3.connect(tmp_db).execute("SELECT sql FROM sqlite_master WHERE name='lines'").fetchone()[0]

    for _ in range(3):
        lines_store._connect().close()

    assert _dump(tmp_db) == snapshot
    assert any(r[0] == zone_id and r[3] == "zone" for r in snapshot)
    assert sqlite3.connect(tmp_db).execute("SELECT sql FROM sqlite_master WHERE name='lines'").fetchone()[0] == schema_sql


def test_fresh_db_gets_zone_capable_schema(tmp_db):
    lines_store._connect().close()
    zone_id = lines_store.add_zone("BTCUSDT", "1d", "2026-01-01", "2026-02-01", 200.0, 100.0)
    (row,) = [r for r in lines_store.list_lines("BTCUSDT", "1d") if r["id"] == zone_id]
    assert row["line_type"] == "zone"


def test_empty_old_table_migrates_and_sequence_not_negative(tmp_db):
    conn = sqlite3.connect(tmp_db)
    conn.execute(OLD_SCHEMA)
    conn.commit()
    conn.close()
    lines_store._connect().close()
    assert lines_store.add_zone("BTCUSDT", "1d", "2026-01-01", "2026-02-01", 2.0, 1.0) == 1


def test_failed_migration_rolls_back_and_leaves_old_table_intact(tmp_db, monkeypatch):
    _make_old_db(tmp_db)
    before = _dump(tmp_db)
    monkeypatch.setattr(lines_store, "_COLUMNS", "id, no_such_column")
    with pytest.raises(sqlite3.OperationalError):
        lines_store._connect()
    monkeypatch.undo()  # DB_PATH도 풀리므로 다시 지정
    monkeypatch.setattr(lines_store, "DB_PATH", tmp_db)

    assert _dump(tmp_db) == before
    conn = sqlite3.connect(tmp_db)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "lines_new" not in names
    assert "'zone'" not in conn.execute("SELECT sql FROM sqlite_master WHERE name='lines'").fetchone()[0]
    conn.close()


def test_add_zone_normalizes_corners_and_rejects_degenerate(tmp_db):
    zid = lines_store.add_zone("BTCUSDT", "1d", "2026-02-01", "2026-01-01", 100.0, 200.0)  # 거꾸로 넘김
    (row,) = [r for r in lines_store.list_lines("BTCUSDT", "1d") if r["id"] == zid]
    assert (row["time1"], row["time2"], row["price1"], row["price2"]) == ("2026-01-01", "2026-02-01", 200.0, 100.0)
    with pytest.raises(ValueError):
        lines_store.add_zone("BTCUSDT", "1d", "2026-01-01", "2026-01-01", 200.0, 100.0)
    with pytest.raises(ValueError):
        lines_store.add_zone("BTCUSDT", "1d", "2026-01-01", "2026-02-01", 100.0, 100.0)


# --- API ---

@pytest.fixture
def client(tmp_db):
    return TestClient(app)


ZONE = {"time1": "2026-01-01", "price1": 90000.0, "time2": "2026-02-01", "price2": 80000.0}


def test_zone_create_list_delete(client):
    resp = client.post("/api/lines/zone", json=ZONE)
    assert resp.status_code == 200
    zone_id = resp.json()["id"]

    lines = client.get("/api/dashboard").json()["manual_lines"]
    (zone,) = [ln for ln in lines if ln["id"] == zone_id]
    assert zone["line_type"] == "zone"
    assert (zone["time1"], zone["time2"], zone["price1"], zone["price2"]) == ("2026-01-01", "2026-02-01", 90000.0, 80000.0)
    assert zone["label"].startswith("▭ 존")

    assert client.delete(f"/api/lines/{zone_id}").json() == {"ok": True}
    assert all(ln["id"] != zone_id for ln in client.get("/api/dashboard").json()["manual_lines"])


@pytest.mark.parametrize("patch", [
    {"price1": 80000.0, "price2": 90000.0},        # 상단 < 하단
    {"price1": 85000.0, "price2": 85000.0},        # 상단 == 하단
    {"price1": 0.0},                               # 가격 0
    {"price2": -1.0},                              # 가격 음수
    {"time1": "2026-02-01", "time2": "2026-01-01"},  # 시작 > 끝
    {"time1": "2026-01-01", "time2": "2026-01-01"},  # 시작 == 끝
    {"time1": "2026/01/01"},                       # 날짜 형식
    {"time2": "not-a-date"},
    {"time1": "20260101"},
])
def test_zone_rejects_invalid_values(client, patch):
    resp = client.post("/api/lines/zone", json={**ZONE, **patch})
    assert resp.status_code == 422
    assert client.get("/api/dashboard").json()["manual_lines"] == []


def test_zone_rejects_missing_fields(client):
    assert client.post("/api/lines/zone", json={"price1": 2.0, "price2": 1.0}).status_code == 422


# --- 신호 보호 ---

def test_dashboard_existing_signals_unchanged_when_zone_exists(client):
    """3b부터 존은 source="zone" 신호를 추가로 낸다. 기존 신호(source가 zone이 아닌 것)는
    존이 있어도 내용/순서가 한 건도 달라지면 안 되고, 추가분은 전부 존 신호여야 한다."""
    client.post("/api/lines/horizontal", json={"price": 28662.75})
    without_zone = client.get("/api/dashboard").json()
    assert all(s["source"] != "zone" for v in without_zone["signals"].values() for s in v)

    # 존을 캔들 데이터 범위(2022~) 한가운데에 둬서 가격/시간이 실제 캔들과 겹치게 한다
    zone_ids = []
    for z in (
        {"time1": "2023-01-01", "price1": 30000.0, "time2": "2023-06-01", "price2": 20000.0},
        {"time1": "2022-03-01", "price1": 45000.0, "time2": "2025-01-01", "price2": 15000.0},
    ):
        resp = client.post("/api/lines/zone", json=z)
        assert resp.status_code == 200
        zone_ids.append(resp.json()["id"])
    with_zone = client.get("/api/dashboard").json()

    non_zone = {
        d: [s for s in v if s["source"] != "zone"] for d, v in with_zone["signals"].items()
    }
    non_zone = {d: v for d, v in non_zone.items() if v}
    assert non_zone == without_zone["signals"]

    zone_signals_out = [s for v in with_zone["signals"].values() for s in v if s["source"] == "zone"]
    assert zone_signals_out, "존이 실제 캔들과 겹치는데 존 신호가 하나도 없음"
    created = {ln["id"]: ln["created_at"] for ln in with_zone["manual_lines"] if ln["line_type"] == "zone"}
    for s in zone_signals_out:
        assert s["direction"] in ("long", "short") and s["tier"] is None and s["evidence"] == []
        assert s["ref_id"] in zone_ids and s["ref_created_at"] == created[s["ref_id"]]
        assert s["text"].startswith("존 ")
    assert with_zone["candles"] == without_zone["candles"]
    assert len(with_zone["manual_lines"]) == len(without_zone["manual_lines"]) + 2


def test_non_zone_signals_have_null_refs(client):
    client.post("/api/lines/horizontal", json={"price": 28662.75})
    data = client.get("/api/dashboard").json()
    sigs = [s for v in data["signals"].values() for s in v]
    assert sigs and all(s["ref_id"] is None and s["ref_created_at"] is None for s in sigs)


def _df(rows):
    return pd.DataFrame({
        "open_time": pd.date_range("2025-01-01", periods=len(rows), freq="D", tz="UTC"),
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
    })


def test_manual_line_functions_skip_zone_rows():
    df = _df([(100, 101, 99, 100.5), (100.5, 102, 99.5, 101), (101, 103, 100, 102)])
    hline = {"id": 1, "line_type": "horizontal", "price1": 100.0, "time1": None, "time2": None, "price2": None}
    zone = {"id": 2, "line_type": "zone", "time1": "2025-01-01", "price1": 101.0, "time2": "2025-01-03", "price2": 99.0}

    assert manual_lines.compute_manual_line_signals(df, [hline, zone]) == manual_lines.compute_manual_line_signals(df, [hline])
    assert manual_lines.compute_manual_line_state_signals(df, [hline, zone]) == manual_lines.compute_manual_line_state_signals(df, [hline])
    # 존만 있으면 신호가 하나도 없다(추세선으로 오인하지 않는다)
    only_zone = manual_lines.compute_manual_line_signals(df, [zone])
    assert all(not v for v in only_zone.values())
    assert all(not v for v in manual_lines.compute_manual_line_state_signals(df, [zone]).values())
