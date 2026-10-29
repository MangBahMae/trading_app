"""
GET /api/dashboard (일봉) - 고정 일봉(tests/fixtures) + 선/존 스냅샷으로 네트워크/캐시/실제 DB 없이 검증한다.
(test_weekly_api.py에서 빼 두었던 일봉 엔드포인트 테스트를 되살린 것 + 스냅샷 선/존이 신호를 만드는지)
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

import lines_store  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(lines_store, "DB_PATH", tmp_path / "manual_lines.db")
    return TestClient(app)


def test_daily_response_uses_the_frozen_daily_candles(client):
    data = client.get("/api/dashboard").json()
    candles = data["candles"]
    assert len(candles) == 1762
    assert data["date_range"] == {"min": "2022-01-01", "max": "2026-10-28"}
    assert candles[0]["date"] == "2022-01-01" and candles[-1]["date"] == "2026-10-28"
    assert candles[198]["ema200"] is None and candles[199]["ema200"] is not None       # EMA200은 200번째 캔들부터
    assert data["manual_lines"] == []                                                  # 임시 DB는 비어 있다(실제 DB 아님)


def test_daily_signals_have_no_weekly_texts(client):
    data = client.get("/api/dashboard").json()
    items = [s for v in data["signals"].values() for s in v]
    assert items and not any(s["text"].startswith("주봉 ") for s in items)


def test_weekly_is_much_shorter_than_daily_and_independent_of_daily_lines(client, weekly_offline, seed_snapshot_db):
    daily = client.get("/api/dashboard").json()
    weekly = client.get("/api/dashboard/weekly").json()
    assert len(weekly["candles"]) < len(daily["candles"]) / 5
    assert weekly["signals"] and all(s["text"].startswith("주봉 ") for v in weekly["signals"].values() for s in v)
    assert [ln["id"] for ln in weekly["manual_lines"]] == [ln["id"] for ln in daily["manual_lines"]] == [27, 28, 54, 9001, 9002]
    # 선/존을 지워도 주봉 신호는 그대로(주봉 신호는 선/존을 쓰지 않는다)
    for line_id in (27, 28, 54, 9001, 9002):
        lines_store.delete_line(line_id)
    assert client.get("/api/dashboard/weekly").json()["signals"] == weekly["signals"]


def test_snapshot_lines_are_listed_with_labels_and_make_every_kind_of_signal(client, seed_snapshot_db):
    data = client.get("/api/dashboard").json()
    lines = {ln["id"]: ln for ln in data["manual_lines"]}
    assert {i: ln["line_type"] for i, ln in lines.items()} == {
        27: "zone", 28: "zone", 54: "zone", 9001: "horizontal", 9002: "trend"}
    assert all(ln["label"] for ln in lines.values())
    texts = [(date, s) for date, v in data["signals"].items() for s in v]

    horizontal = [(d, s["text"]) for d, s in texts if s["text"].startswith("수평선")]
    assert any("근접" in t for _, t in horizontal)
    assert any(t.endswith("진입") for _, t in horizontal) and any(t.endswith("유지 중") for _, t in horizontal)

    trend = [(d, s) for d, s in texts if s["text"].startswith("추세선")]
    assert trend and all(s["ref_id"] == 9002 for _, s in trend)
    assert any("근접" in s["text"] for d, s in trend if d > "2023-11-14")                  # 오른쪽 연장 구간(time2 이후) 근접 신호
    assert any(s["text"].endswith("진입") for d, s in trend) and any(s["text"].endswith("유지 중") for d, s in trend)
    assert min(d for d, _ in trend) >= "2023-10-27"                                         # time1 이전에는 신호가 없다

    zone_refs = {s["ref_id"] for _, s in texts if s["source"] == "zone"}
    assert zone_refs == {27, 28, 54}
    assert all(d <= "2026-10-04" for d, s in texts if s["source"] == "zone" and s["ref_id"] == 27)   # 존은 time1~time2 범위만
