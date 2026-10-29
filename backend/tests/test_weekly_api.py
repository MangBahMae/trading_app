"""
GET /api/dashboard/weekly - 주봉 차트 + 주봉 신호. 선/존은 일봉에서 그린 것을 표시용으로만 내려주고 신호 판정에는 쓰지 않는다.
일봉 /api/dashboard는 그대로다.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

import lines_store  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "services"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(lines_store, "DB_PATH", tmp_path / "manual_lines.db")
    return TestClient(app)


def test_weekly_response_shape_and_range(client):
    data = client.get("/api/dashboard/weekly").json()
    assert set(data) == {"candles", "date_range", "signals", "divergence_markers", "manual_lines"}
    candles = data["candles"]
    assert candles[0]["date"] == "2022-01-03" and data["date_range"]["min"] == "2022-01-03"
    assert data["date_range"]["max"] == candles[-1]["date"]
    import datetime as dt
    assert all(dt.date.fromisoformat(c["date"]).weekday() == 0 for c in candles)          # 전부 월요일 시작
    assert [c["date"] for c in candles] == sorted(c["date"] for c in candles)
    assert len(candles) >= 251
    # EMA200은 2017년부터 받은 워밍업 덕에 첫 표시 주부터 값이 있다
    assert candles[0]["ema200"] is not None and candles[0]["ema20"] is not None and candles[0]["ema9"] is not None
    assert candles[0]["rsi"] is not None
    assert data["divergence_markers"] == []


def test_weekly_signals_are_weekly_only_and_inside_the_range(client):
    data = client.get("/api/dashboard/weekly").json()
    dates = {c["date"] for c in data["candles"]}
    assert data["signals"] and set(data["signals"]) <= dates
    items = [s for v in data["signals"].values() for s in v]
    assert all(s["text"].startswith("주봉 ") for s in items)
    assert all(s["near_zone"] is None and s["next_bar"] is None for s in items)
    assert {s["direction"] for s in items} == {"long", "short", "reference"}


def test_in_progress_week_is_not_included(client):
    import pandas as pd
    data = client.get("/api/dashboard/weekly").json()
    last_open = pd.Timestamp(data["candles"][-1]["date"], tz="UTC")
    assert last_open + pd.Timedelta(days=7) - pd.Timedelta(milliseconds=1) <= pd.Timestamp.now(tz="UTC")


def test_daily_lines_are_shown_but_do_not_change_weekly_signals(client):
    before = client.get("/api/dashboard/weekly").json()
    client.post("/api/lines/horizontal", json={"price": 60000.0})
    zone_id = client.post("/api/lines/zone", json={
        "time1": "2024-01-01", "price1": 70000.0, "time2": "2024-12-31", "price2": 60000.0}).json()["id"]
    client.post("/api/lines/trend", json={"time1": "2023-01-01", "price1": 16500.0, "time2": "2023-12-31", "price2": 44000.0})
    after = client.get("/api/dashboard/weekly").json()
    assert [ln["line_type"] for ln in after["manual_lines"]] == ["horizontal", "zone", "trend"]
    assert any(ln["id"] == zone_id and ln["label"] for ln in after["manual_lines"])
    assert after["signals"] == before["signals"] and after["candles"] == before["candles"]   # 신호/캔들은 선과 무관


def test_daily_endpoint_is_unchanged_and_has_daily_candles(client):
    daily = client.get("/api/dashboard").json()
    weekly = client.get("/api/dashboard/weekly").json()
    assert daily["candles"][0]["date"] == "2022-01-01" and len(daily["candles"]) > 1700
    assert not any(s["text"].startswith("주봉 ") for v in daily["signals"].values() for s in v)
    assert len(weekly["candles"]) < len(daily["candles"]) / 5
